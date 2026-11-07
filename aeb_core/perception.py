"""Objetivo en el carril propio a partir de las detecciones del radar.

1. Coordenadas cartesianas y filtro de altura corregido por el cabeceo del radar.
2. Corredor lateral del carril propio.
3. Detección más cercana y las que están a menos de cluster_depth: distancia mínima y mediana del Doppler.
4. Filtro exponencial y retención breve si se pierde el objetivo.
5. Velocidad y aceleración del objetivo con un filtro α-β; se reinicia si la distancia salta más de new_track_jump.
"""

import numpy as np


class RadarTarget:
    def __init__(self, params, mount_z, min_range, mount_pitch=0.0):
        self.p = params
        self.mount_z = mount_z
        self.min_range = min_range
        self.mount_pitch = mount_pitch      # cabeceo estático del radar [rad]
        self._stamp = None
        self.alpha = params["ab_alpha"]
        self.beta = self.alpha ** 2 / (2 - self.alpha)
        self.distance = None
        self.closing_speed = None
        self.target_speed = None
        self.target_accel = 0.0
        self.valid = False
        self.n_points = 0
        self.points_xy, self.points_in_lane = np.empty((0, 2)), np.empty(0, dtype=bool)
        self._missed = 0

    def update(self, stamp, detections, ego_speed, ego_pitch=0.0):
        """`stamp` [s] da el paso real entre mediciones; `ego_pitch` [rad] es el cabeceo actual."""
        p = self.p
        dt = stamp - self._stamp if self._stamp is not None else 0.0
        if self._stamp is not None and dt <= 0.0:
            return self                     # medición repetida o fuera de orden
        self._stamp = stamp
        vel, azi, alt, depth = detections.velocity, detections.azimuth, detections.altitude, detections.depth
        x = depth * np.cos(alt) * np.cos(azi)
        y = depth * np.cos(alt) * np.sin(azi)
        h = self.mount_z + depth * np.sin(alt + self.mount_pitch + ego_pitch)

        valid_h = (depth > self.min_range) & (h > p["min_height"]) & (h < p["max_height"])
        mask = valid_h & (np.abs(y) < p["lane_half_width"])
        self.n_points = int(mask.sum())
        # para el video
        self.points_xy, self.points_in_lane = np.c_[x[valid_h], y[valid_h]], mask[valid_h]

        if self.n_points == 0:
            self._missed += 1
            if self._missed > p["hold_frames"]:
                self.valid = False
                self.distance = self.closing_speed = self.target_speed = None
                self.target_accel = 0.0
            return self

        x, vel = x[mask], vel[mask]
        d_min = float(x.min())
        cluster = x < d_min + p["cluster_depth"]
        closing = float(-np.median(vel[cluster]))
        v_obj = ego_speed - closing

        same_track = (self.valid and self.distance is not None
                      and abs(d_min - (self.distance - self.closing_speed * dt)) < p["new_track_jump"])
        if same_track:
            a = p["ema_alpha"]
            self.distance = a * d_min + (1 - a) * self.distance
            self.closing_speed = a * closing + (1 - a) * self.closing_speed
            # Filtro α-β
            v_pred = self.target_speed + self.target_accel * dt
            r = v_obj - v_pred
            self.target_speed = v_pred + self.alpha * r
            lo, hi = p["a_lead_limits"]
            self.target_accel = min(max(self.target_accel + self.beta / dt * r, lo), hi)
        else:
            self.distance, self.closing_speed = d_min, closing
            self.target_speed, self.target_accel = v_obj, 0.0
        self.valid = True
        self._missed = 0
        return self
