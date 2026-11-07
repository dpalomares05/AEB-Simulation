"""Corre un ensayo de ensayos/ en CARLA y guarda log.csv, meta.json y video.

Uso (con CarlaUE4.exe abierto):
    python run_scenario.py PROPIO_FRENA_18_3453                # radar
    python run_scenario.py ENCAP_CCRb_6_12 --entrada lider     # datos del líder
    python run_scenario.py ENCAP_CCRb_6_12 --sin-aeb

Columnas de log.csv: *_gt = verdad del simulador (solo para evaluar), radar_* = radar simulado,
*_est = estimado por la percepción.
"""

import argparse
import csv
import json
import math
import os
import time
from dataclasses import asdict
from datetime import datetime

import carla
import cv2
import numpy as np

import config as C
import escenario as E
import sim_utils as U
from actuator import BrakeActuator, VirtualBrake
from aeb_core import BRAKING_STATES, AebPipeline, LeadState
from analyze import results_root
from overlay import draw_hud, draw_schematic
from traffic import RoadFrame, in_path_threat, lateral_reference, make_scripted, maneuver_events
from agents.navigation.controller import VehiclePIDController

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
LIVE_WINDOW = "AEB El Fantastico"
VARIANTS = ("sinaeb", "ttc", "btn")


def attach_sensors(world, ego, record_video, radar_pitch_deg):
    bpl = world.get_blueprint_library()
    ext, off = ego.bounding_box.extent, ego.bounding_box.location

    radar_bp = bpl.find("sensor.other.radar")
    for key in ("range", "horizontal_fov", "vertical_fov", "points_per_second", "sensor_tick"):
        radar_bp.set_attribute(key, str(C.RADAR[key]))
    radar_tf = carla.Transform(carla.Location(x=off.x + ext.x + C.RADAR["mount_x_offset"], z=C.RADAR["mount_z"]),
                               carla.Rotation(pitch=radar_pitch_deg))
    radar = world.spawn_actor(radar_bp, radar_tf, attach_to=ego)

    collision = world.spawn_actor(bpl.find("sensor.other.collision"), carla.Transform(), attach_to=ego)

    camera = None
    if record_video:
        cam_bp = bpl.find("sensor.camera.rgb")
        cam_bp.set_attribute("image_size_x", str(C.VIDEO["width"]))
        cam_bp.set_attribute("image_size_y", str(C.VIDEO["height"]))
        cam_bp.set_attribute("fov", str(C.VIDEO["fov"]))
        cam_tf = carla.Transform(carla.Location(x=-7.0, z=2.8), carla.Rotation(pitch=-10))
        camera = world.spawn_actor(cam_bp, cam_tf, attach_to=ego)
    return radar, collision, camera


def resolve_blueprint(bpl, spec, index):
    """Modelo de CARLA del actor: el que diga el ensayo, o el primero de config.TRAFFIC (el líder)."""
    pool = C.TRAFFIC["blueprints"]
    bp_id = spec.blueprint or pool[index % len(pool)]
    return bpl.find(bp_id if bpl.filter(bp_id) else C.TARGET_BLUEPRINT)


def spawn_scenario_actors(world, frame, ego, sc):
    bpl = world.get_blueprint_library()
    scripted = []
    for i, spec in enumerate(sc.actors):
        bp = resolve_blueprint(bpl, spec, i)
        if bp.has_attribute("role_name"):
            bp.set_attribute("role_name", spec.name)
        # posición aproximada; la exacta se fija en la aproximación previa
        half = {"peaton": 0.3, "objeto": 0.7}.get(spec.kind, 2.5)
        s = (ego.bounding_box.extent.x + spec.gap + half) if spec.gap >= 0 else (spec.gap - ego.bounding_box.extent.x - half)
        tf = frame.transform_at(s, spec.lane * frame.lane_width)
        tf.location.z += {"peaton": 1.0, "objeto": 0.1}.get(spec.kind, 0.5)
        tf.rotation.roll = spec.roll
        actor = world.try_spawn_actor(bp, tf)
        if actor is None:
            raise RuntimeError(f"No se pudo crear '{spec.name}' ({bp.id}) en s={s:.1f} m, lateral {spec.lane:+.2f}")
        scripted.append(make_scripted(spec, actor, frame))
    return scripted


def rel_speed(v1, v2):
    return math.sqrt((v1.x - v2.x) ** 2 + (v1.y - v2.y) ** 2 + (v1.z - v2.z) ** 2)


ACTUATORS = {"modelo": C.ACTUATOR, "ideal": C.ACTUATOR}


def veredicto(evaluar, impact):
    """Criterio del ensayo: evaluar(velocidad de impacto en km/h, o None si no hubo contacto)."""
    return evaluar(impact["vrel_mps"] * 3.6 if impact else None)


def run(world, sc, evaluar, variant="btn", actuator_mode="modelo", record_video=True, live=False,
        vehicle=C.VEHICLE, source="radar", out_dir=None):
    use_aeb = variant != "sinaeb"
    logic = "ttc" if variant == "ttc" else "btn"   # modo sombra
    run_name = f"{sc.run_id}_{variant}" + ("" if actuator_mode == "modelo" else f"_actuador-{actuator_mode}")
    out_dir = out_dir or os.path.join(results_root(vehicle, source), "ensayos", run_name)
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n=== {run_name} (perfil {vehicle}, entrada {source}) ===")

    carla_brake_map = U.carla_brake_map(vehicle)
    to_destroy = []
    writer_video = None
    try:
        carla_map = world.get_map()
        wp0 = U.start_waypoint(world)
        frame = RoadFrame(wp0)
        ego = U.spawn_ego(world, wp0, vehicle)
        to_destroy.append(ego)
        scripted = spawn_scenario_actors(world, frame, ego, sc)
        to_destroy += [sa.actor for sa in scripted]
        by_id = {sa.actor.id: sa for sa in scripted}

        radar, collision, camera = attach_sensors(world, ego, record_video, C.VEHICLES[vehicle]["radar_pitch_deg"])
        to_destroy += [radar, collision, camera]
        radar_q = U.SensorQueue(radar)
        cam_q = U.SensorQueue(camera) if camera else None
        collisions = []
        collision.listen(lambda e: collisions.append(e))

        if record_video:
            writer_video = cv2.VideoWriter(os.path.join(out_dir, "video.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                           1.0 / C.FIXED_DT, (C.VIDEO["width"], C.VIDEO["height"]))

        # asentamiento (1 s) y condiciones iniciales
        for sa in scripted:
            if sa.spec.kind == "vehiculo":
                sa.actor.apply_control(carla.VehicleControl(hand_brake=True))
        for _ in range(int(1.0 / C.FIXED_DT)):
            world.tick()
        for sa in scripted:
            sa.start()

        driver = VehiclePIDController(ego, args_lateral=C.LATERAL_PID, args_longitudinal=C.LONGITUDINAL_PID,
                                      max_throttle=0.75, max_brake=0.0, max_steering=0.8)
        ego_half = ego.bounding_box.extent.x

        # en la aproximación previa los actores mantienen su distancia relativa
        def hold_all():
            ego_s = frame.s_of(ego.get_location())
            v_ego = U.forward_speed(ego)
            for sa in scripted:
                sa.hold(ego_s, ego_half, (v_ego - (0.0 if sa.stopped else sa.v)) * C.FIXED_DT)

        gear = U.run_up(world, carla_map, ego, driver, sc.ego_speed, on_tick=hold_all,
                        queues=[q for q in (radar_q, cam_q) if q])

        gap_at_start = in_path_threat(ego, scripted)[0]
        pipeline = AebPipeline.from_config(C, logic=logic, vehicle=vehicle, source=source)
        perception = pipeline.perception
        actuator = BrakeActuator(ACTUATORS[actuator_mode], C.FIXED_DT, ideal=actuator_mode == "ideal")
        brake = VirtualBrake(C.VEHICLES[vehicle]["d_max"], carla_brake_map, C.FIXED_DT, C.VIRTUAL_BRAKE)

        rows = []
        impact = None
        n_seen = 0
        prev_vel = {}
        t, t_end = 0.0, None
        aeb_braked = False
        verdict = None             # (cumple, texto)
        last_shown = time.perf_counter()
        while t < sc.duration:
            frame_id = world.tick()
            t += C.FIXED_DT

            # Observación
            ego_state = U.ego_state(ego)
            v_ego, a_ego = ego_state.speed, ego_state.accel
            pipeline.on_ego(t, ego_state)
            scan = U.radar_detections(radar_q.get(frame_id))
            if source == "radar":
                pipeline.on_radar(t, scan)
            else:
                d_lead, v_lead, a_lead, lead_name = in_path_threat(ego, scripted)
                pipeline.on_lead(t, LeadState(d_lead, v_lead, a_lead) if lead_name else None)

            # Decisión
            out = pipeline.tick(t)
            state, demand = out.state, out.demand_pct

            # Actuación
            position = actuator.step(demand if use_aeb else 0.0)
            aeb_braked |= use_aeb and state in BRAKING_STATES
            lat_ref = lateral_reference(0, sc.ego_maneuvers, t, frame.lane_width)
            ego_s = frame.s_of(ego.get_location())
            ctrl = driver.run_step(sc.ego_speed * 3.6, frame.target(ego_s + max(5.0, 0.5 * v_ego), lat_ref))
            if aeb_braked:
                ctrl.throttle = 0.0   # el AEB anula al conductor virtual una vez que interviene
            elif gear:
                ctrl.manual_gear_shift, ctrl.gear = True, gear   # crucero en marcha fija
            ctrl.brake = brake.to_carla_brake(position, -a_ego)   # lazo cerrado con la desaceleración medida
            ego.apply_control(ctrl)

            # Actores del escenario
            for sa in scripted:
                sa.step(t, C.FIXED_DT)

            # Verdad del simulador (evaluación)
            gap, v_tgt, a_tgt, threat = in_path_threat(ego, scripted)
            v_rel = v_ego - v_tgt
            hits = [(by_id.get(ev.other_actor.id), ev.other_actor) for ev in collisions[n_seen:]]
            if gap <= 0.0 and threat:       # respaldo geométrico (p. ej., objetos sin colisión física)
                hits.append((next(sa for sa in scripted if sa.spec.name == threat), None))
            for sa, other in hits:
                actor = sa.actor if sa else other
                if impact is None:
                    ego_v = prev_vel.get(ego.id, ego.get_velocity())
                    oth_v = prev_vel.get(actor.id, actor.get_velocity())
                    impact = {"vrel_mps": rel_speed(ego_v, oth_v), "with": sa.spec.name if sa else other.type_id}
                if sa:
                    sa.release()
            n_seen = len(collisions)
            prev_vel = {a.id: a.get_velocity() for a in [ego] + [sa.actor for sa in scripted]}
            collided = impact is not None

            row = {
                "t": round(t, 3), "frame": frame_id,
                "v_ego": v_ego, "a_ego": a_ego, "pitch_ego_deg": math.degrees(ego_state.pitch), "lat_ref_ego": lat_ref,
                "threat_gt": threat, "v_target_gt": v_tgt, "a_target_gt": a_tgt, "gap_gt": gap, "v_rel_gt": v_rel,
                "ttc_gt": gap / v_rel if v_rel > 0.1 else math.inf,
                "radar_valid": int(out.target_valid), "radar_points": perception.n_points,
                "radar_distance": out.distance, "radar_closing_speed": out.closing_speed,
                "v_target_est": out.target_speed, "a_target_est": out.target_accel,
                "ttc_radar": out.ttc, "d_req": out.d_req, "btn": out.btn, "d_cmd": out.d_cmd,
                "aeb_state": state, "demand_pct": demand if use_aeb else 0.0,
                "shadow_demand_pct": demand, "actuator_pct": position, "brake_target_decel": brake.target, "brake_limited": int(brake.limited),
                "brake_cmd": ctrl.brake, "throttle_cmd": ctrl.throttle,
                "collision": int(collided),
            }
            rows.append(row)

            U.follow_with_spectator(world, ego)
            if cam_q:
                image = cam_q.get(frame_id)
                img = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(image.height, image.width, 4)[:, :, :3].copy()
                inset = draw_schematic(frame, ego, scripted, radar, perception, threat)
                draw_hud(img, inset, sc, variant, row, len(scripted), collided, verdict)
                writer_video.write(img)
                if live:
                    cv2.imshow(LIVE_WINDOW, img)
                    cv2.waitKey(1)
                    # a velocidad real
                    time.sleep(max(0.0, C.FIXED_DT - (time.perf_counter() - last_shown)))
                    last_shown = time.perf_counter()

            # Fin del ensayo
            if t_end is None:
                stopped = v_ego < 0.1 and t > 3.0
                matched = aeb_braked and (math.isnan(v_rel) or v_rel <= 0.05)
                if collided or stopped or matched:
                    t_end = t + 1.5
                    verdict = veredicto(evaluar, impact)
            elif t >= t_end:
                break
            if t_end is None and t >= sc.duration - 1.5:
                verdict = veredicto(evaluar, impact)   # termina por tiempo: se muestra el resultado

        with open(os.path.join(out_dir, "log.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

        meta = {
            "run": run_name, "scenario": asdict(sc), "variant": variant, "aeb_enabled": use_aeb, "aeb_logic": logic,
            "vehicle": vehicle, "target_source": source, "radar_pitch_deg": C.VEHICLES[vehicle]["radar_pitch_deg"],
            "actuator": actuator_mode, "town": C.TOWN, "dt": C.FIXED_DT,
            "ego_blueprint": ego.type_id, "ego_physics_profile": U.ego_setup(vehicle)[1],
            "carla_brake_map": carla_brake_map,
            "actors": {sa.spec.name: sa.actor.type_id for sa in scripted},
            "events": maneuver_events(sc),
            "radar": C.RADAR, "perception": C.PERCEPTION,
            "aeb": pipeline.logic.p, "d_max": C.VEHICLES[vehicle]["d_max"],
            "actuator_params": ACTUATORS[actuator_mode], "virtual_brake": C.VIRTUAL_BRAKE,
            "ego_physics": U.physics_summary(ego),
            "gap_at_start_m": gap_at_start,
            "collision": impact is not None,
            "impact_vrel_mps": impact["vrel_mps"] if impact else None,
            "collision_with": impact["with"] if impact else None,
        }
        verdict = veredicto(evaluar, impact)
        meta["ensayo_cumple"], meta["ensayo_resultado"] = verdict
        with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        braked = any(r["aeb_state"] in BRAKING_STATES for r in rows)
        outcome = (f"COLISIÓN con {impact['with']} a {impact['vrel_mps'] * 3.6:.1f} km/h" if impact
                   else "sin colisión")
        gaps = [r["gap_gt"] for r in rows if not math.isnan(r["gap_gt"])]
        print(f"  {outcome} | AEB {'intervino' if braked else 'no intervino'}"
              f"{'' if use_aeb else ' (sombra)'} | gap mínimo {min(gaps) if gaps else math.nan:.2f} m | {len(rows)} ciclos")
        print(f"  {sc.norma}\n  Criterio: {sc.criterio}\n  >>> {verdict[1]}")
        return out_dir
    finally:
        if live:
            cv2.destroyAllWindows()
        if writer_video:
            writer_video.release()
        U.destroy(to_destroy)
        world.tick()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ensayo", choices=E.disponibles(), help="archivo de ensayos/ (sin .py)")
    ap.add_argument("--entrada", choices=["radar", "lider"], default="radar",
                    help="radar: detecciones crudas; lider: distancia y velocidad del líder ya conocidas")
    ap.add_argument("--logica", choices=["btn", "ttc"], default=C.AEB_LOGIC, help="lógica AEB de una corrida")
    ap.add_argument("--sin-aeb", action="store_true", help="AEB en modo sombra (calcula pero no frena)")
    ap.add_argument("--actuador", choices=sorted(ACTUATORS), default="modelo",
                    help="modelo: retardo 0.1 s y rampa 0.3 s; ideal: sin retardo ni rampa")
    ap.add_argument("--sin-video", action="store_true")
    ap.add_argument("--ver", action="store_true", help="muestra el video y la telemetría en vivo, en una ventana")
    ap.add_argument("--abrir", action="store_true", help="al terminar genera las gráficas y abre el video y las gráficas")
    ap.add_argument("--descargas", action="store_true",
                    help="guarda la corrida en Descargas, en una carpeta con la fecha y hora (AAAA-MM-DD_HH-MM-SS)")
    ap.add_argument("--graficas", action="store_true", help="al terminar genera las gráficas, sin abrirlas")
    args = ap.parse_args()

    # Ensayo -> escenario
    ensayo = E.cargar(args.ensayo)
    esc = ensayo.escenario()
    print(E.describir(esc))
    sc = E.a_simulacion(esc)

    out_dir = None
    if args.descargas:
        out_dir = os.path.join(os.path.expanduser("~"), "Downloads", datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))

    # Simulación en CARLA
    client, world = U.connect()
    with U.SyncMode(world):
        out_dir = run(world, sc, ensayo.evaluar, variant="sinaeb" if args.sin_aeb else args.logica,
                      actuator_mode=args.actuador, record_video=args.ver or not args.sin_video, live=args.ver,
                      source=args.entrada, out_dir=out_dir)

    if args.abrir or args.graficas:
        import analyze
        analyze.plot_one(out_dir)
    if args.abrir:
        for name in ("graficas.png", "video.mp4"):
            if os.path.exists(os.path.join(out_dir, name)):
                os.startfile(os.path.join(out_dir, name))

    # ensayo.bat muestra solo las líneas que empiezan con >>>
    with open(os.path.join(out_dir, "meta.json"), encoding="utf-8") as f:
        print(f">>> Resultado: {json.load(f)['ensayo_resultado']}")
    print(f">>> Archivos en: {out_dir}")


if __name__ == "__main__":
    main()
