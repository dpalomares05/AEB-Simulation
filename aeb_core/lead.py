"""Objetivo dado directamente (distancia, velocidad y aceleración del líder), sin radar.

Misma interfaz que perception.RadarTarget. Si no llega la aceleración del líder, se estima de su
velocidad con un filtro α-β.
"""

import math

import numpy as np


class LeadTracker:
    def __init__(self, params):
        self.p = params
        self.alpha = params["ab_alpha"]
        self.beta = self.alpha ** 2 / (2 - self.alpha)
        self.distance = None
        self.closing_speed = None
        self.target_speed = None
        self.target_accel = 0.0
        self.accel_measured = False
        self.valid = False
        self.n_points = 0
        self.points_xy, self.points_in_lane = np.empty((0, 2)), np.empty(0, dtype=bool)   # para el video
        self._stamp = None
        self._missed = 0

    def update(self, stamp, lead, ego_speed, ego_pitch=0.0):
        """`lead` es un interfaces.LeadState, o None si no hay líder."""
        p = self.p
        dt = stamp - self._stamp if self._stamp is not None else 0.0
        if self._stamp is not None and dt <= 0.0:
            return self                     # medición repetida o fuera de orden
        self._stamp = stamp

        if lead is None or not (math.isfinite(lead.distance) and math.isfinite(lead.speed)):
            self._missed += 1
            if self._missed > p["hold_frames"]:
                self.valid = False
                self.distance = self.closing_speed = self.target_speed = None
                self.target_accel = 0.0
            return self

        closing = ego_speed - lead.speed
        same_track = (self.valid and self.distance is not None
                      and abs(lead.distance - (self.distance - self.closing_speed * dt)) < p["new_track_jump"])
        lo, hi = p["a_lead_limits"]
        self.accel_measured = math.isfinite(lead.accel)
        if not same_track:
            self.target_speed = lead.speed
            self.target_accel = min(max(lead.accel, lo), hi) if self.accel_measured else 0.0
        elif self.accel_measured:
            a = p["a_lead_alpha"]
            self.target_speed = lead.speed
            self.target_accel = min(max(a * lead.accel + (1 - a) * self.target_accel, lo), hi)
        else:
            # Filtro α-β
            v_pred = self.target_speed + self.target_accel * dt
            r = lead.speed - v_pred
            self.target_speed = v_pred + self.alpha * r
            self.target_accel = min(max(self.target_accel + self.beta / dt * r, lo), hi)
        self.distance, self.closing_speed = lead.distance, closing
        self.valid = True
        self.n_points = 1
        self._missed = 0
        return self
