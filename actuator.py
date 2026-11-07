"""Actuador de freno y freno de CARLA (solo simulación).

BrakeActuator: retardo puro y rampa de recorrido.
VirtualBrake: brake de CARLA que da la desaceleración correspondiente a la posición del actuador.
"""

from collections import deque

import numpy as np


class BrakeActuator:
    def __init__(self, params, dt, ideal=False):
        self.ideal = ideal
        n_delay = 0 if ideal else int(round(params["delay_s"] / dt))
        self._queue = deque([0.0] * n_delay)
        self._max_step = 100.0 if ideal else 100.0 * dt / params["ramp_full_s"]
        self.position_pct = 0.0

    def step(self, demand_pct):
        """Avanza un paso de simulación y devuelve la posición actual [%]."""
        self._queue.append(demand_pct)
        target = self._queue.popleft()
        delta = max(-self._max_step, min(self._max_step, target - self.position_pct))
        self.position_pct += delta
        return self.position_pct


class VirtualBrake:
    """Desaceleración objetivo = posición del actuador [%] / 100 × D_max.

    Brake de CARLA = prealimentación + corrección PI contra una referencia de primer orden (ref_tau).
    Si la desaceleración medida pasa D_max, el ciclo siguiente escala el brake por D_max / medida.
    """

    def __init__(self, d_max, carla_table, dt, params):
        self.carla_pct = np.array([p for p, _ in carla_table], float)
        self.carla_decel = np.array([a for _, a in carla_table], float)
        self.dt = dt
        self.kp, self.ki = params["kp"], params["ki"]
        self.i_lim = params["i_limit"]
        self.alpha = params["meas_alpha"]
        self.ref_tau = params["ref_tau"]
        self.ref = 0.0             # [m/s²]
        self.d_max = d_max                       # [m/s²]
        self.u_last = 0.0
        self.limited = False
        self.integral = 0.0
        self.meas = 0.0
        self.target = 0.0          # [m/s²]

    def to_carla_brake(self, position_pct, measured_decel):
        """position_pct [%]; measured_decel [m/s², positiva al frenar]."""
        self.meas = self.alpha * measured_decel + (1 - self.alpha) * self.meas
        self.limited = measured_decel > self.d_max
        self.target = position_pct / 100.0 * self.d_max
        self.ref += (self.target - self.ref) * self.dt / self.ref_tau
        if self.target <= 0.0:
            self.integral = self.ref = self.u_last = 0.0
            return 0.0
        error = self.ref - self.meas
        if not self.limited:
            self.integral = max(-self.i_lim, min(self.i_lim, self.integral + self.ki * error * self.dt))
        feedforward = float(np.interp(self.target, self.carla_decel, self.carla_pct)) / 100.0
        u = feedforward + self.kp * error + self.integral
        if self.limited:
            u = min(u, self.u_last * self.d_max / measured_decel)
            self.integral = min(self.integral, u - feedforward)
        self.u_last = max(0.0, min(1.0, u))
        return self.u_last
