"""Movimiento de los vehículos del escenario y verdad del simulador.

Se mueven con la física de CARLA (no por teletransporte) para que el radar mida bien su velocidad Doppler.
"""

import math

import carla

import config as C
from agents.navigation.controller import PIDLateralController


def quintic(tau):
    """Perfil 0 → 1 con velocidad y aceleración nulas en los extremos."""
    tau = min(max(tau, 0.0), 1.0)
    return 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5


def lateral_reference(base_lane, maneuvers, t, lane_width):
    """Desplazamiento lateral de referencia [m] respecto del carril inicial del ego."""
    lat = base_lane * lane_width
    for m in maneuvers:
        if m.kind == "lane_change" and t >= m.t:
            start, end = lat, m.to_lane * lane_width
            lat = start + (end - start) * quintic((t - m.t) / m.duration)
    return lat


class _Target:
    def __init__(self, transform):
        self.transform = transform


class RoadFrame:
    """Coordenadas a lo largo del carril inicial del ego: s (longitudinal) y lat (positiva a la derecha)."""

    def __init__(self, start_wp):
        self.wp0 = start_wp
        self.origin = start_wp.transform.location
        self.fwd = start_wp.transform.get_forward_vector()
        self.right = start_wp.transform.get_right_vector()
        self.lane_width = start_wp.lane_width

    def s_of(self, location):
        d = location - self.origin
        return d.x * self.fwd.x + d.y * self.fwd.y

    def transform_at(self, s, lat):
        wp = self.wp0.next(s)[0] if s > 0.01 else (self.wp0.previous(-s)[0] if s < -0.01 else self.wp0)
        tf = wp.transform
        r = tf.get_right_vector()
        loc = tf.location + carla.Location(x=r.x * lat, y=r.y * lat)
        return carla.Transform(loc, carla.Rotation(yaw=tf.rotation.yaw))

    def target(self, s, lat):
        return _Target(self.transform_at(s, lat))


class ScriptedActor:

    def __init__(self, spec, actor, frame):
        self.spec, self.actor, self.frame = spec, actor, frame
        self.v = spec.speed
        self.free = False          # True tras chocar: deja de seguir el guion
        self.stopped = spec.speed <= 0.0
        self.z = None
        self.lat_pid = PIDLateralController(actor, **C.LATERAL_PID)

    @property
    def half_length(self):
        return self.actor.bounding_box.extent.x

    def hold(self, ego_s, ego_half_length, closing_step=0.0):
        if self.z is None:
            self.z = self.actor.get_location().z
        if self.spec.gap >= 0:
            s = ego_s + ego_half_length + self.spec.gap + self.half_length + closing_step
        else:
            s = ego_s - ego_half_length + self.spec.gap - self.half_length
        tf = self.frame.transform_at(s, self.spec.lane * self.frame.lane_width)
        tf.location.z = self.z
        tf.rotation.roll = self.spec.roll
        self.actor.set_transform(tf)

    def start(self):
        """t = 0: arranca con su velocidad inicial (física)."""
        if self.stopped:
            self.actor.apply_control(carla.VehicleControl(hand_brake=True))
        else:
            self.actor.apply_control(carla.VehicleControl(hand_brake=False))
            self.actor.enable_constant_velocity(carla.Vector3D(self.v, 0.0, 0.0))

    def step(self, t, dt):
        if self.free or self.stopped:
            return
        for m in self.spec.maneuvers:
            if m.kind == "brake" and t >= m.t:
                self.v = max(m.v_final, self.v - m.decel * dt)
        if self.v <= 0.0:
            self.actor.disable_constant_velocity()
            self.actor.set_target_velocity(carla.Vector3D(0.0, 0.0, 0.0))
            self.actor.apply_control(carla.VehicleControl(hand_brake=True))
            self.stopped = True
            return
        self.actor.enable_constant_velocity(carla.Vector3D(self.v, 0.0, 0.0))
        lat = lateral_reference(self.spec.lane, self.spec.maneuvers, t, self.frame.lane_width)
        s = self.frame.s_of(self.actor.get_location())
        steer = self.lat_pid.run_step(self.frame.target(s + max(5.0, 0.5 * self.v), lat))
        self.actor.apply_control(carla.VehicleControl(steer=float(steer)))

    def release(self):
        """Tras una colisión el vehículo deja de seguir el guion."""
        if not self.free:
            self.free = True
            self.actor.disable_constant_velocity()
            self.actor.apply_control(carla.VehicleControl(brake=1.0))


class ScriptedWalker(ScriptedActor):
    """Peatón: camina con WalkerControl según sus maniobras "walk" (o hacia adelante desde t = 0)."""

    def start(self):
        self._walk(self.frame.fwd, self.spec.speed)

    def _walk(self, direction, speed):
        self.actor.apply_control(carla.WalkerControl(direction=carla.Vector3D(direction.x, direction.y, 0.0),
                                                     speed=float(speed)))

    def step(self, t, dt):
        if self.free:
            return
        for m in self.spec.maneuvers:
            if m.kind == "walk" and t >= m.t:
                f, r = self.frame.fwd, self.frame.right
                d = {"izquierda": r * -1.0, "derecha": r, "adelante": f}[m.direction]
                self._walk(d, m.speed)

    def release(self):
        if not self.free:
            self.free = True
            self._walk(self.frame.fwd, 0.0)


class ScriptedProp(ScriptedActor):
    """Objeto estático: solo se posiciona; no tiene maniobras."""

    def start(self):
        pass

    def step(self, t, dt):
        pass

    def release(self):
        self.free = True


def make_scripted(spec, actor, frame):
    cls = {"peaton": ScriptedWalker, "objeto": ScriptedProp}.get(spec.kind, ScriptedActor)
    return cls(spec, actor, frame)


def in_path_threat(ego, actors):
    e_tf = ego.get_transform()
    f, r = e_tf.get_forward_vector(), e_tf.get_right_vector()
    e_c = e_tf.transform(ego.bounding_box.location)
    e_ext = ego.bounding_box.extent
    best = (math.nan, math.nan, math.nan, "")
    for sa in actors:
        a = sa.actor
        verts = a.bounding_box.get_world_vertices(a.get_transform())
        along = [(p.x - e_c.x) * f.x + (p.y - e_c.y) * f.y for p in verts]
        lat = [(p.x - e_c.x) * r.x + (p.y - e_c.y) * r.y for p in verts]
        if max(along) <= 0 or min(lat) >= e_ext.y or max(lat) <= -e_ext.y:
            continue
        gap = min(along) - e_ext.x
        if math.isnan(best[0]) or gap < best[0]:
            v, acc = a.get_velocity(), a.get_acceleration()
            best = (gap, v.x * f.x + v.y * f.y + v.z * f.z, acc.x * f.x + acc.y * f.y + acc.z * f.z, sa.spec.name)
    return best


def maneuver_events(scenario):
    """Lista (t, texto) de las maniobras guionadas, para marcarlas en las gráficas."""
    ev = [(m.t, f"ego: cambio a carril {m.to_lane:+d}") for m in scenario.ego_maneuvers]
    for a in scenario.actors:
        for m in a.maneuvers:
            if m.kind == "lane_change":
                txt = f"{a.name}: cambio a carril {m.to_lane:+d}"
            elif m.kind == "brake":
                txt = f"{a.name}: frena {m.decel:g} m/s²"
            else:
                txt = f"{a.name}: camina hacia la {m.direction} a {m.speed * 3.6:.0f} km/h"
            ev.append((round(m.t, 2), txt))
    return sorted(ev)
