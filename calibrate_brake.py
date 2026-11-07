"""Mide la desaceleración del ego de CARLA con demanda de freno fija (20 … 100 %) desde 16 m/s.

Métrica: MFDD (ECE R13-H), entre 0.8·v0 y 0.1·v0. Imprime el carla_brake_map del perfil.

Uso (con CarlaUE4.exe abierto):  python calibrate_brake.py
"""

import argparse
import csv
import json
import os

import carla
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as C
import sim_utils as U
from agents.navigation.controller import VehiclePIDController

V0 = 16.0                       # [m/s]
DEMANDS = [20, 40, 60, 80, 100]  # [%]
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def mfdd(rows, v0):
    """Desaceleración media entre 0.8·v0 y 0.1·v0 a partir de la distancia recorrida."""
    vb, ve = 0.8 * v0, 0.1 * v0
    sb = next(r["s"] for r in rows if r["v"] <= vb)
    se = next(r["s"] for r in rows if r["v"] <= ve)
    return (vb ** 2 - ve ** 2) / (2.0 * (se - sb))


def brake_test(world, carla_map, demand, vehicle):
    ego = U.spawn_ego(world, U.start_waypoint(world), vehicle)   # auto y física del perfil
    try:
        for _ in range(int(1.0 / C.FIXED_DT)):
            world.tick()
        driver = VehiclePIDController(ego, args_lateral=C.LATERAL_PID, args_longitudinal=C.LONGITUDINAL_PID,
                                      max_throttle=0.75, max_brake=0.0, max_steering=0.8)
        U.run_up(world, carla_map, ego, driver, V0)

        rows, t, s = [], 0.0, 0.0
        v0 = U.forward_speed(ego)
        while t < 20.0:
            ctrl = driver.run_step(0.0, U.lane_keep_waypoint(carla_map, ego))
            ctrl.throttle, ctrl.brake = 0.0, demand / 100.0
            ego.apply_control(ctrl)
            U.follow_with_spectator(world, ego)
            world.tick()
            t += C.FIXED_DT
            v = U.forward_speed(ego)
            s += max(v, 0.0) * C.FIXED_DT
            rows.append({"demand_pct": demand, "t": round(t, 3), "v": v, "a": U.forward_accel(ego), "s": s})
            if v < 0.05:
                break
        result = {"demand_pct": demand, "v0_mps": v0, "stop_time_s": t, "stop_distance_m": s,
                  "mfdd_mps2": mfdd(rows, v0)}
        return rows, result, U.physics_summary(ego)
    finally:
        U.destroy([ego])
        world.tick()


def main():
    ap = argparse.ArgumentParser(description="Curva demanda -> desaceleración del auto de CARLA.")
    ap.add_argument("--perfil", choices=sorted(C.VEHICLES), default=C.VEHICLE,
                    help="perfil de config.VEHICLES (por defecto, el Porsche)")
    args = ap.parse_args()
    OUT_DIR = os.path.join(RESULTS, args.perfil, "calibracion_freno")
    os.makedirs(OUT_DIR, exist_ok=True)
    client, world = U.connect()
    carla_map = world.get_map()
    all_rows, results, physics = [], [], None
    with U.SyncMode(world):
        for d in DEMANDS:
            rows, res, physics = brake_test(world, carla_map, d, args.perfil)
            all_rows += rows
            results.append(res)
            print(f"Demanda {d:3d} %: MFDD = {res['mfdd_mps2']:5.2f} m/s²  "
                  f"distancia = {res['stop_distance_m']:5.1f} m  tiempo = {res['stop_time_s']:4.2f} s")

    with open(os.path.join(OUT_DIR, "series.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    with open(os.path.join(OUT_DIR, "curva_demanda_desaceleracion.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"perfil": args.perfil, "vehicle": physics["blueprint"], "v0_target_mps": V0,
                   "physics": physics, "results": results},
                  f, indent=2, ensure_ascii=False)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    for d in DEMANDS:
        r = [x for x in all_rows if x["demand_pct"] == d]
        ax1.plot([x["t"] for x in r], [x["v"] * 3.6 for x in r], label=f"{d} %")
    ax1.set(xlabel="Tiempo [s]", ylabel="Velocidad [km/h]", title=f"Frenadas a demanda fija desde {V0 * 3.6:.0f} km/h")
    ax1.legend(title="Demanda")
    ax1.grid(alpha=0.3)
    ax2.plot(DEMANDS, [r["mfdd_mps2"] for r in results], "o-", label="Vehículo virtual (CARLA)")
    ax2.set(xlabel="Demanda de freno [%]", ylabel="MFDD [m/s²]", title="Curva demanda → desaceleración",
            xlim=(0, 105), ylim=(0, None))
    ax2.text(0.03, 0.95, "Pendiente: misma prueba en el Porsche real", transform=ax2.transAxes, va="top",
             fontsize=9, color="gray")
    ax2.legend(loc="lower right")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "calibracion_freno.png"), dpi=150)
    curve = [(0.0, 0.0)] + [(float(r["demand_pct"]), round(r["mfdd_mps2"], 2)) for r in results]
    print(f"Resultados en {OUT_DIR}")
    print(f"Auto: {physics['blueprint']}, masa {physics['mass_kg']:.0f} kg, wheelbase {physics['wheelbase_m']:.2f} m")
    if args.perfil:
        print(f'Copia en config.py, perfil "{args.perfil}":')
        print(f'    "carla_brake_map": {curve},')
        d_max = C.VEHICLES[args.perfil]["d_max"]
        if curve[-1][1] < d_max:
            print(f"AVISO: el auto de CARLA frena como máximo {curve[-1][1]:.2f} m/s² y el perfil pide "
                  f"D_max = {d_max:.2f} m/s². El freno virtual no podrá llegar a D_max.")


if __name__ == "__main__":
    main()
