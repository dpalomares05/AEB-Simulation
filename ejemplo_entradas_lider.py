"""Ejemplo paso a paso: de las entradas del líder a la demanda de freno, comparado con aeb_core.

Uso:  python ejemplo_entradas_lider.py [d] [v_ego_kmh] [v_lider_kmh] [a_lider] [a_ego]
      python ejemplo_entradas_lider.py 30 79 58 -6 0
"""

import math
import sys

import config as C
from aeb_core import AebPipeline, EgoState, LeadState


def main():
    d, v_ego_kmh, v_lead_kmh, a_lead, a_ego = ([float(x) for x in sys.argv[1:6]] + [30, 79.2, 57.6, -6, 0][len(sys.argv) - 1:])[:5]
    v_e, v_l = v_ego_kmh / 3.6, v_lead_kmh / 3.6
    p = C.AEB_BTN
    veh = C.VEHICLES[C.VEHICLE]
    tau, d0 = p["tau"], p["d0"]

    print(f"PASO 0 · Entradas")
    print(f"  d = {d:.2f} m   v_ego = {v_e:.2f} m/s ({v_ego_kmh:.1f} km/h)   v_líder = {v_l:.2f} m/s ({v_lead_kmh:.1f} km/h)")
    print(f"  a_líder = {a_lead:.2f} m/s²   a_ego = {a_ego:.2f} m/s²   perfil {C.VEHICLE}")

    # Núcleo
    pipeline = AebPipeline.from_config(C, source="lider")
    pipeline.on_ego(0.0, EgoState(v_e, a_ego))
    pipeline.on_lead(0.0, LeadState(d, v_l, a_lead))
    out = pipeline.tick(0.0)
    d_max = pipeline.logic.d_max

    # Cálculo a mano
    v_c = v_e - v_l
    a_e = p["a_ego_alpha"] * a_ego          # primer ciclo del filtro exponencial (parte de 0)
    print(f"\nPASO 1 · Velocidad de cierre y aceleraciones (aeb_core/lead.py)")
    print(f"  v_c = v_ego − v_líder = {v_c:.2f} m/s;  a_ego filtrada = {a_e:.2f} m/s²;  a_líder = {a_lead:.2f} m/s²")

    dp = d - v_c * tau - 0.5 * (a_e - a_lead) * tau ** 2 - d0
    vep = max(v_e + a_e * tau, 0.0)
    vlp = max(v_l + a_lead * tau, 0.0)
    d_l = max(-a_lead, 0.0)
    vr = vep - vlp
    print(f"\nPASO 2 · Predicción al final del retardo τ = {tau} s (CAMP, logic.py:39-42)")
    print(f"  d' = d − v_c·τ − ½(a_e − a_l)·τ² − d₀ = {d:.2f} − {v_c * tau:.2f} − {0.5 * (a_e - a_lead) * tau ** 2:.2f} − {d0} = {dp:.2f} m")
    print(f"  v_e' = {vep:.2f} m/s   v_l' = {vlp:.2f} m/s   v_rel' = {vr:.2f} m/s   D_líder = {d_l:.2f} m/s²")

    print(f"\nPASO 3 · Deceleración requerida (Jansson, logic.py:44-58)")
    if dp <= 0.05:
        d_req, case = d_max, "distancia agotada: D_max"
    elif vep <= 0:
        d_req, case = 0.0, "el ego ya está detenido"
    elif vlp <= 0:
        d_req, case = vep ** 2 / (2 * dp), "objeto detenido: v_e'²/(2d')"
    else:
        d_s = vep ** 2 / (2 * (dp + vlp ** 2 / (2 * d_l))) if d_l > 1e-3 else 0.0
        if vr <= 0:
            d_req, case = d_s, "el líder no se acerca: solo cuenta si se detiene"
        else:
            d_m = d_l + vr ** 2 / (2 * dp)
            print(f"  Líder que se detiene:   D_S = v_e'²/(2(d' + v_l'²/(2D_l))) = {d_s:.3f} m/s²")
            print(f"  Líder en movimiento:    D_M = D_l + v_rel'²/(2d')          = {d_m:.3f} m/s²")
            if d_l > 1e-3 and 2 * dp / vr > vlp / d_l:
                print(f"  2d'/v_rel' = {2 * dp / vr:.2f} s > v_l'/D_l = {vlp / d_l:.2f} s: el líder se detiene antes de alcanzarlo")
                d_req, case = d_s, "se usa D_S"
            else:
                d_req, case = d_m, "se usa D_M"
    d_req = min(d_req, d_max) if dp <= 0.05 else d_req
    print(f"  D_req = {d_req:.3f} m/s²  ({case})")

    btn = min(d_req / d_max, 1.0)
    print(f"\nPASO 4 · Brake Threat Number (logic.py:90) y estado (logic.py:96-108)")
    print(f"  BTN = D_req / D_max = {d_req:.3f} / {d_max:.2f} = {btn:.3f}")
    print(f"  Umbrales: alerta BTN ≥ {p['btn_fcw']} o TTC < {p['ttc_fcw']} s; frenado BTN ≥ {veh['btn_on']}"
          f";  TTC = d / v_c = {d / v_c if v_c > 0.1 else math.inf:.2f} s")
    print(f"  Estado: {out.state}")

    braking = out.state == "FRENANDO"
    demand = 100.0 * btn if braking else 0.0
    d_cmd = demand / 100.0 * d_max
    print(f"\nPASO 5 · Demanda de freno (logic.py:110-116)")
    print(f"  Demanda = BTN × 100 = {demand:.1f} %" if braking else "  No frena: demanda = 0 %")
    print(f"  Equivale a {d_cmd:.3f} m/s² (= demanda / 100 × D_max)")

    ok = (abs(out.d_req - d_req) < 1e-9 and abs(out.btn - btn) < 1e-9 and abs(out.d_cmd - d_cmd) < 1e-9
          and abs(out.demand_pct - demand) < 1e-9)
    print(f"\nComprobación contra el núcleo: D_req {out.d_req:.3f}, BTN {out.btn:.3f}, demanda {out.demand_pct:.1f} % "
          f"-> {'coincide' if ok else 'NO COINCIDE'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
