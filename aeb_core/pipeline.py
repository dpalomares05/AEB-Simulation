"""Cadena del AEB: objetivo + estado propio -> demanda de freno [%].

source = "radar" (perception.RadarTarget) o "lider" (lead.LeadTracker).
Interfaz de nodo: on_ego, on_radar, on_lead y tick.
Sin objetivo el freno se libera; sin estado propio la demanda es 0 y fault queda activo.
"""

import math

from aeb_core.interfaces import AebOutput, Detections
from aeb_core.lead import LeadTracker
from aeb_core.logic import INACTIVO, RequiredDecelAEB, StagedTTCAEB, time_to_collision
from aeb_core.perception import RadarTarget

NAN = float("nan")


class AebPipeline:
    def __init__(self, perception, logic, target_timeout, ego_timeout, source="radar"):
        self.perception = perception
        self.logic = logic
        self.target_timeout = target_timeout
        self.ego_timeout = ego_timeout
        self.source = source
        self._missing = Detections.empty() if source == "radar" else None
        self._ego = self._ego_stamp = None
        self._meas = self._target_stamp = None
        self._has_meas = False

    @classmethod
    def from_config(cls, cfg, logic="btn", vehicle=None, source="radar"):
        """Arma la cadena con los parámetros de config.py."""
        veh = cfg.VEHICLES[vehicle or cfg.VEHICLE]
        if source == "radar":
            perception = RadarTarget(cfg.PERCEPTION, cfg.RADAR["mount_z"], cfg.RADAR["min_range"],
                                     math.radians(veh["radar_pitch_deg"]))
        else:
            perception = LeadTracker(cfg.PERCEPTION)
        if logic == "btn":
            decision = RequiredDecelAEB(dict(cfg.AEB_BTN, btn_on=veh["btn_on"]), d_max=veh["d_max"])
        else:
            decision = StagedTTCAEB(cfg.AEB_TTC)
        return cls(perception, decision, cfg.INPUTS["target_timeout"], cfg.INPUTS["ego_timeout"], source)

    def on_ego(self, stamp, ego):
        self._ego, self._ego_stamp = ego, stamp

    def on_radar(self, stamp, detections):
        self._meas, self._target_stamp, self._has_meas = detections, stamp, True

    def on_lead(self, stamp, lead):
        self._meas, self._target_stamp, self._has_meas = lead, stamp, True

    def tick(self, stamp):
        ego_ok = (self._ego is not None and self._ego.is_valid()
                  and stamp - self._ego_stamp <= self.ego_timeout)
        if not ego_ok or self._ego.driver_override:
            self.logic.reset()
            return self._output(INACTIVO, 0.0, NAN, time_to_collision(None, None), "" if ego_ok else "ego")

        target_ok = self._target_stamp is not None and stamp - self._target_stamp <= self.target_timeout
        ego, per = self._ego, self.perception
        if self._has_meas:
            per.update(stamp, self._meas, ego.speed, ego.pitch)
            self._has_meas = False
        elif not target_ok:
            per.update(stamp, self._missing, ego.speed, ego.pitch)

        if isinstance(self.logic, RequiredDecelAEB):
            a_ego = ego.accel if math.isfinite(ego.accel) else 0.0
            state, demand, ttc = self.logic.step(per.valid, per.distance, per.closing_speed,
                                                 ego.speed, a_ego, per.target_accel)   # demanda = BTN × 100
            d_cmd = self.logic.d_cmd
        else:
            state, demand, ttc = self.logic.step(per.valid, per.distance, per.closing_speed, ego.speed)
            d_cmd = NAN
        return self._output(state, demand, d_cmd, ttc, "" if target_ok else self.source)

    def _output(self, state, demand, d_cmd, ttc, fault):
        per, logic = self.perception, self.logic
        valid = per.valid
        continuous = isinstance(logic, RequiredDecelAEB)
        return AebOutput(
            state=state, demand_pct=demand, d_cmd=d_cmd,
            d_req=logic.d_req if continuous else NAN, btn=logic.btn if continuous else NAN, ttc=ttc,
            target_valid=valid,
            distance=per.distance if valid else NAN, closing_speed=per.closing_speed if valid else NAN,
            target_speed=per.target_speed if valid else NAN, target_accel=per.target_accel if valid else NAN,
            fault=fault)
