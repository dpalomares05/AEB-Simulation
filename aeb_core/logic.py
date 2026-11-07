import math

INACTIVO = "INACTIVO"
ALERTA = "ALERTA"
FRENANDO = "FRENANDO"
FRENADO_PARCIAL = "FRENADO_PARCIAL"
FRENADO_TOTAL = "FRENADO_TOTAL"
DETENIDO = "DETENIDO"

BRAKING_STATES = (FRENANDO, FRENADO_PARCIAL, FRENADO_TOTAL, DETENIDO)


def time_to_collision(distance, closing_speed):
    """TTC a velocidad constante. Infinito si el objetivo no se acerca."""
    if distance is None or closing_speed is None or closing_speed <= 0.1:
        return math.inf
    return max(distance, 0.0) / closing_speed


def required_deceleration(d, v_c, v_e, a_e, a_l, tau, d0, d_max):
    """
    Deceleración del ego [m/s², positiva] que evita la colisión, suponiendo
    aceleraciones constantes del ego (durante τ) y del objetivo.

    d   : distancia al objetivo [m]          v_c : velocidad de cierre [m/s] (> 0 se acerca)
    v_e : velocidad del ego [m/s]            a_e : aceleración del ego [m/s²] (con signo)
    a_l : aceleración del objetivo [m/s²] (con signo)
    """
    v_l = max(v_e - v_c, 0.0)
    # Paso 1: estado predicho al final del retardo τ (CAMP)
    dp = d - v_c * tau - 0.5 * (a_e - a_l) * tau ** 2 - d0
    vep = max(v_e + a_e * tau, 0.0)
    vlp = max(v_l + a_l * tau, 0.0)
    d_l = max(-a_l, 0.0)            # solo cuenta la frenada del objetivo
    vr = vep - vlp
    if dp <= 0.05:
        return d_max
    if vep <= 0.0:
        # Con la frenada actual se detiene dentro de τ: hace falta MANTENERLA (no soltar). Devolver 0
        # hacía que el freno se soltara y se volviera a aplicar en ciclos alternos justo antes de parar.
        return max(-a_e, 0.0)
    # Paso 2: casos de Jansson / CAMP invertidos
    if vlp <= 0.0:                                          # objeto estático o líder ya detenido
        return vep ** 2 / (2 * dp)
    d_s = vep ** 2 / (2 * (dp + vlp ** 2 / (2 * d_l))) if d_l > 1e-3 else 0.0   # el líder se detendrá
    if vr <= 0.0:
        return d_s                                          # 0 si el líder no frena
    d_m = d_l + vr ** 2 / (2 * dp)                          # el líder sigue en movimiento
    if d_l > 1e-3 and (2 * dp / vr) > (vlp / d_l):          # se detiene antes de igualar velocidades
        return d_s
    return d_m


class RequiredDecelAEB:
    """Lógica continua: activación por BTN y mando = deceleración requerida."""

    def __init__(self, params, d_max):
        self.p = params
        self.d_max = d_max
        self.state = INACTIVO
        self._conf = 0
        self._a_e = 0.0
        self.d_req = 0.0
        self.btn = self.d_cmd = 0.0    # d_cmd: desaceleración que corresponde a la demanda [m/s²]

    def reset(self):
        """Vuelve al reposo; también libera la retención en parada (DETENIDO)."""
        self.state = INACTIVO
        self._conf = 0
        self.d_req = self.btn = self.d_cmd = 0.0

    def step(self, target_valid, distance, closing_speed, ego_speed, ego_accel, target_accel):
        """Devuelve (estado, demanda [%], ttc)."""
        p = self.p
        a_meas = min(max(ego_accel, p["a_ego_limits"][0]), p["a_ego_limits"][1])
        self._a_e = a_e = p["a_ego_alpha"] * a_meas + (1 - p["a_ego_alpha"]) * self._a_e
        if target_valid:
            self.d_req = required_deceleration(distance, closing_speed, ego_speed, a_e, target_accel,
                                               p["tau"], p["d0"], self.d_max)
            ttc = time_to_collision(distance, closing_speed)
        else:
            self.d_req, ttc = 0.0, math.inf
        self.btn = min(self.d_req / self.d_max, 1.0)

        static = target_valid and abs(ego_speed - closing_speed) < p["static_speed"]
        n_conf = p["n_conf_static"] if static else p["n_conf_moving"]
        self._conf = self._conf + 1 if self.btn >= p["btn_on"] else 0

        if self.state in (FRENANDO, DETENIDO):
            # Ante un objeto estático el freno se mantiene hasta la parada; con un objetivo
            # en movimiento se libera cuando ya no se acerca y casi no hace falta frenar.
            if ego_speed < p["standstill_speed"]:
                self.state = DETENIDO
            elif self.state == FRENANDO and (not target_valid or (not static and self.d_req < p["d_off"]
                                                                  and closing_speed <= p["release_closing_speed"])):
                self.state = INACTIVO
        elif ego_speed >= p["min_ego_speed"] and self._conf >= n_conf:
            self.state = FRENANDO
        elif ego_speed >= p["min_ego_speed"] and (self.btn >= p["btn_fcw"] or ttc < p["ttc_fcw"]):
            self.state = ALERTA
        else:
            self.state = INACTIVO

        if self.state == FRENANDO:
            demand = 100.0 * self.btn                           # lo que hace falta, hasta el 100 % (D_max)
        elif self.state == DETENIDO:
            demand = 100.0                                      # retención en parada
        else:
            demand = 0.0
        self.d_cmd = demand / 100.0 * self.d_max
        return self.state, demand, ttc


class StagedTTCAEB:
    """Lógica anterior: umbrales fijos de TTC con demanda 0 / 50 / 100 %."""

    def __init__(self, params):
        self.p = params
        self.state = INACTIVO

    def reset(self):
        self.state = INACTIVO

    def step(self, target_valid, distance, closing_speed, ego_speed):
        """Devuelve (estado, demanda [%], ttc)."""
        p = self.p
        ttc = time_to_collision(distance, closing_speed) if target_valid else math.inf

        # Una vez frenando, el freno se mantiene enclavado hasta detenerse
        # o hasta que el objetivo deja de acercarse.
        if self.state in BRAKING_STATES:
            if ego_speed < p["standstill_speed"]:
                self.state = DETENIDO
            elif self.state != DETENIDO and (not target_valid or closing_speed < p["release_closing_speed"]):
                self.state = INACTIVO
            elif self.state == FRENADO_PARCIAL and ttc < p["ttc_full"]:
                self.state = FRENADO_TOTAL
        elif ego_speed < p["min_ego_speed"]:
            self.state = INACTIVO
        elif ttc < p["ttc_full"]:
            self.state = FRENADO_TOTAL
        elif ttc < p["ttc_partial"]:
            self.state = FRENADO_PARCIAL
        elif ttc < p["ttc_warning"]:
            self.state = ALERTA
        else:
            self.state = INACTIVO

        demand = {
            FRENADO_PARCIAL: p["partial_demand_pct"],
            FRENADO_TOTAL: p["full_demand_pct"],
            DETENIDO: p["full_demand_pct"],
        }.get(self.state, 0.0)
        return self.state, demand, ttc
