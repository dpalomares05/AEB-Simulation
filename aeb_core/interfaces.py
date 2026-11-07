"""Entradas y salidas del núcleo AEB (unidades SI)."""

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Detections:
    """Detecciones del radar en el marco del sensor."""
    depth: np.ndarray       # distancia [m]
    azimuth: np.ndarray     # [rad]
    altitude: np.ndarray    # elevación [rad], negativa bajo el sensor
    velocity: np.ndarray    # velocidad radial (Doppler) [m/s], negativa si se acerca

    @classmethod
    def empty(cls):
        e = np.empty(0)
        return cls(e, e, e, e)


@dataclass
class LeadState:
    """Líder ya identificado: distancia, velocidad y aceleración."""
    distance: float                 # [m] de paragolpes a paragolpes
    speed: float                    # velocidad del líder respecto del piso [m/s]
    accel: float = float("nan")     # [m/s²], nan si no llega


@dataclass
class EgoState:
    """Estado propio (/v2x/kinematics/speed, /v2x/imu/accel_set)."""
    speed: float                    # [m/s]
    accel: float                    # [m/s²], nan si no llega
    pitch: float = 0.0              # cabeceo [rad], negativo con la nariz hacia abajo
    driver_override: bool = False   # el conductor retoma el control

    def is_valid(self):
        return math.isfinite(self.speed) and math.isfinite(self.pitch)


@dataclass
class AebOutput:
    state: str
    demand_pct: float       # [%]
    d_cmd: float            # [m/s²]
    d_req: float            # [m/s²]
    btn: float
    ttc: float              # [s]
    target_valid: bool
    distance: float         # [m], nan sin objetivo
    closing_speed: float    # [m/s], nan sin objetivo
    target_speed: float     # [m/s], nan sin objetivo
    target_accel: float     # [m/s²], nan sin objetivo
    fault: str = ""         # "", "radar", "lider" o "ego": entrada faltante o vencida
