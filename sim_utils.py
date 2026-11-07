"""Utilidades comunes de CARLA: conexión, modo síncrono, spawn y verdad del simulador."""

import math
import os
import queue
import sys

import carla
import numpy as np

import config as C
from aeb_core.interfaces import Detections, EgoState

# Permite reutilizar los controladores de PythonAPI/carla/agents
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "PythonAPI", "carla"))


def connect():
    client = carla.Client(C.HOST, C.PORT)
    client.set_timeout(120.0)
    world = client.get_world()
    if not world.get_map().name.endswith(C.TOWN):
        print(f"Cargando {C.TOWN}...")
        world = client.load_world(C.TOWN)
    world.set_weather(carla.WeatherParameters.ClearNoon)
    return client, world


class SyncMode:
    """Activa el modo síncrono con paso fijo y lo restaura al salir."""

    def __init__(self, world):
        self.world = world
        self._original = None

    def __enter__(self):
        self._original = self.world.get_settings()
        s = self.world.get_settings()
        s.synchronous_mode = True
        s.fixed_delta_seconds = C.FIXED_DT
        self.world.apply_settings(s)
        return self

    def __exit__(self, *exc):
        self.world.apply_settings(self._original)


class SensorQueue:
    """Recoge las mediciones de un sensor y entrega la del frame pedido."""

    def __init__(self, sensor):
        self.q = queue.Queue()
        sensor.listen(self.q.put)

    def get(self, frame, timeout=5.0):
        while True:
            data = self.q.get(timeout=timeout)
            if data.frame >= frame:
                return data


def start_waypoint(world):
    return world.get_map().get_waypoint(carla.Location(*C.START_LOCATION))


def spawn_vehicle(world, blueprint_id, waypoint, ahead=0.0, role="vehicle"):
    bp = world.get_blueprint_library().find(blueprint_id)
    bp.set_attribute("role_name", role)
    wp = waypoint.next(ahead)[0] if ahead > 0 else waypoint
    tf = wp.transform
    tf.location.z += 0.3
    return world.spawn_actor(bp, tf)


def ego_setup(vehicle):
    """Auto de CARLA y física del perfil (solo los parámetros que no son None)."""
    veh = C.VEHICLES[vehicle]
    physics = {k: v for k, v in (veh.get("physics") or {}).items() if v is not None}
    return veh["ego_blueprint"], physics


def carla_brake_map(vehicle):
    """carla_brake_map del perfil; error si no está definida."""
    veh = C.VEHICLES[vehicle]
    if not veh.get("carla_brake_map"):
        raise RuntimeError(f"Falta 'carla_brake_map' del perfil '{vehicle}' en config.py. "
                           f"Mídela con: python calibrate_brake.py")
    return veh["carla_brake_map"]


def spawn_ego(world, waypoint, vehicle):
    """Crea el ego del perfil y le aplica su física."""
    blueprint, physics = ego_setup(vehicle)
    ego = spawn_vehicle(world, blueprint, waypoint, role="hero")
    apply_physics(ego, physics)
    return ego


def apply_physics(vehicle, physics):
    """Aplica al auto de CARLA la física del perfil (solo lo que no es None).
    El wheelbase, la trocha y el área frontal no se pueden cambiar por la API.
    """
    if not physics:
        return
    pc = vehicle.get_physics_control()
    if "mass_kg" in physics:
        pc.mass = float(physics["mass_kg"])
    if "center_of_mass_m" in physics:
        pc.center_of_mass = carla.Vector3D(*physics["center_of_mass_m"])
    if "drag_coefficient" in physics:
        pc.drag_coefficient = float(physics["drag_coefficient"])
    wheels = pc.wheels
    for w in wheels:
        if "wheel_radius_cm" in physics:
            w.radius = float(physics["wheel_radius_cm"])
        if "tire_friction" in physics:
            w.tire_friction = float(physics["tire_friction"])
        if "max_brake_torque_nm" in physics:
            w.max_brake_torque = float(physics["max_brake_torque_nm"])
    pc.wheels = wheels
    vehicle.apply_physics_control(pc)


def lane_keep_waypoint(carla_map, vehicle):
    v = forward_speed(vehicle)
    return carla_map.get_waypoint(vehicle.get_location()).next(max(5.0, 0.5 * v))[0]


def run_up(world, carla_map, ego, driver, speed, on_tick=None, queues=()):
    """Aproximación previa: acelera hasta mantener `speed` durante RUNUP_STABLE_TIME.

    No usa set_target_velocity: deja la caja en neutro y produce un freno motor irreal al engranar.
    Devuelve la marcha fijada.
    """
    driver.max_throt, max_throt = 1.0, driver.max_throt
    stable = 0
    gear = last_gear = None
    try:
        for _ in range(int(C.RUNUP_MAX_TIME / C.FIXED_DT)):
            v = forward_speed(ego)
            ctrl = driver.run_step(speed * 3.6, lane_keep_waypoint(carla_map, ego))
            # fija la marcha: cerca de un punto de cambio la caja automática oscila
            current = ego.get_control().gear
            last_gear = current if current > 0 else last_gear
            if gear is None and v > speed - C.RUNUP_SPEED_TOL and last_gear:
                gear = last_gear
            if gear:
                ctrl.manual_gear_shift, ctrl.gear = True, gear
            ego.apply_control(ctrl)
            if on_tick:
                on_tick()
            follow_with_spectator(world, ego)
            frame = world.tick()
            for q in queues:
                q.get(frame)
            stable = stable + 1 if abs(v - speed) < C.RUNUP_SPEED_TOL else 0
            if stable * C.FIXED_DT >= C.RUNUP_STABLE_TIME:
                return gear
        print("  Aviso: la velocidad del ego no se estabilizó durante la aproximación previa")
        return gear
    finally:
        driver.max_throt = max_throt


def forward_speed(vehicle):
    v = vehicle.get_velocity()
    f = vehicle.get_transform().get_forward_vector()
    return v.x * f.x + v.y * f.y + v.z * f.z


def forward_accel(vehicle):
    a = vehicle.get_acceleration()
    f = vehicle.get_transform().get_forward_vector()
    return a.x * f.x + a.y * f.y + a.z * f.z


def radar_detections(radar_data):
    """Medición de sensor.other.radar -> entrada del núcleo. Columnas: velocidad, azimut, altitud, profundidad."""
    pts = np.frombuffer(radar_data.raw_data, dtype=np.float32).reshape(-1, 4)
    return Detections(depth=pts[:, 3], azimuth=pts[:, 1], altitude=pts[:, 2], velocity=pts[:, 0])


def ego_state(vehicle):
    """Estado del actor -> entrada del núcleo. El cabeceo de CARLA es positivo con la nariz arriba."""
    return EgoState(speed=forward_speed(vehicle), accel=forward_accel(vehicle),
                    pitch=math.radians(vehicle.get_transform().rotation.pitch))


def physics_summary(vehicle):
    pc = vehicle.get_physics_control()
    return {
        "mass_kg": pc.mass,
        "drag_coefficient": pc.drag_coefficient,
        "max_rpm": pc.max_rpm,
        "wheels_max_brake_torque_Nm": [w.max_brake_torque for w in pc.wheels],
        "wheels_tire_friction": [w.tire_friction for w in pc.wheels],
        "bbox_extent_m": [vehicle.bounding_box.extent.x, vehicle.bounding_box.extent.y,
                          vehicle.bounding_box.extent.z],
        "blueprint": vehicle.type_id,
        "center_of_mass_m": [pc.center_of_mass.x, pc.center_of_mass.y, pc.center_of_mass.z],
        "wheels_radius_cm": [w.radius for w in pc.wheels],
        **wheel_geometry(vehicle, pc),
    }


def wheel_geometry(vehicle, pc=None):
    """Wheelbase y trocha [m] a partir de la posición de las ruedas (CARLA la da en cm, en el mundo)."""
    pc = pc or vehicle.get_physics_control()
    tf = vehicle.get_transform()
    f, r = tf.get_forward_vector(), tf.get_right_vector()
    p = [(w.position.x / 100.0, w.position.y / 100.0) for w in pc.wheels]   # orden: DI, DD, TI, TD
    lon = [x * f.x + y * f.y for x, y in p]
    lat = [x * r.x + y * r.y for x, y in p]
    return {"wheelbase_m": abs((lon[0] + lon[1]) - (lon[2] + lon[3])) / 2,
            "track_front_m": abs(lat[0] - lat[1]), "track_rear_m": abs(lat[2] - lat[3])}


def follow_with_spectator(world, vehicle):
    tf = vehicle.get_transform()
    f = tf.get_forward_vector()
    loc = tf.location - carla.Location(x=8 * f.x, y=8 * f.y) + carla.Location(z=4)
    world.get_spectator().set_transform(carla.Transform(loc, carla.Rotation(pitch=-15, yaw=tf.rotation.yaw)))


def destroy(actors):
    for a in actors:
        if a is not None and a.is_alive:
            if isinstance(a, carla.Sensor):
                a.stop()
            a.destroy()


def fmt_inf(x, fmt="{:.2f}"):
    return "inf" if x is None or math.isinf(x) else fmt.format(x)
