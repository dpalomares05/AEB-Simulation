"""Gráficas de cada corrida (velocidad, BTN y % de frenado) y resumen.csv.

Uso:  python analyze.py
"""

import argparse
import csv
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config as C
from aeb_core.logic import BRAKING_STATES

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

STATE_COLORS = {"ALERTA": "#ffe08a", "FRENADO_PARCIAL": "#ffb366", "FRENADO_TOTAL": "#ff7b7b",
                "FRENANDO": "#ff9a9a", "DETENIDO": "#a8dba8"}
VARIANTS = {"sinaeb": ("Sin AEB", "#d9534f"), "ttc": ("TTC escalonado", "#f0ad4e"), "btn": ("BTN continuo", "#5cb85c")}


def load(run_dir):
    with open(os.path.join(run_dir, "log.csv")) as f:
        rows = list(csv.DictReader(f))
    with open(os.path.join(run_dir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    cols = {k: np.array([r[k] for r in rows]) for k in rows[0]}
    log = {k: (v if k in ("aeb_state", "threat_gt") else v.astype(float)) for k, v in cols.items()}
    return log, meta


def rnd(x, nd):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def first(mask):
    idx = np.flatnonzero(mask)
    return int(idx[0]) if idx.size else None


def t_aeb(t, a):
    """Inicio del frenado según Euro NCAP: cruce de −1 m/s² previo al primer −3 m/s²."""
    i3 = first(a < -3.0)
    if i3 is None:
        return None
    above = np.flatnonzero(a[:i3] > -1.0)
    return float(t[above[-1] + 1]) if above.size else float(t[0])


def metrics(log, meta):
    t, state = log["t"], log["aeb_state"]
    variant = meta.get("variant", "btn" if meta["aeb_enabled"] else "sinaeb")
    i_col = first(log["collision"] == 1)
    before = np.arange(len(t)) < (i_col if i_col is not None else len(t))
    braking = np.isin(state, BRAKING_STATES)
    # solo antes del impacto: después, el cabeceo del choque genera detecciones del suelo
    i_warn, i_brake = first((state == "ALERTA") & before), first(braking & before)
    valid = (log["radar_valid"] == 1) & (log["gap_gt"] > 0.5) & before
    err = log["radar_distance"][valid] - log["gap_gt"][valid]
    a_err = (log["a_target_est"] - log["a_target_gt"])[valid & np.isfinite(log["a_target_est"])]
    sc = meta["scenario"]
    expect = sc.get("expect_brake", True)
    gaps = log["gap_gt"][np.isfinite(log["gap_gt"])]
    demand = log["demand_pct"] if meta["aeb_enabled"] else log["shadow_demand_pct"]
    dem_on = demand[braking & (log["v_ego"] > 0.5)]
    a_smooth = np.convolve(log["a_ego"], np.ones(3) / 3, mode="same")
    # desaceleración media del AEB; se excluye v < 3 m/s (pico espurio de CARLA al detenerse)
    acting = (log["actuator_pct"] > 0) & (log["v_ego"] > 3.0) & before
    tb = t_aeb(t, a_smooth) if meta["aeb_enabled"] else None
    if not meta["aeb_enabled"]:
        verdict = "—"
    elif expect:
        verdict = "Colisión" if meta["collision"] else "OK"
    else:
        verdict = "Falsa activación" if i_brake is not None else ("OK (solo alerta)" if i_warn is not None else "OK")
    return {
        "corrida": meta["run"],
        "perfil": meta.get("vehicle", ""),
        "escenario": sc["name"],
        "v_ego_kmh": round(sc["ego_speed"] * 3.6),
        "actores": len(sc.get("actors", [])),
        "variante": variant,
        "logica": VARIANTS[variant][0],
        "esperado": "Frenar" if expect else "No frenar",
        "intervencion": "Sí" if i_brake is not None else "No",
        "veredicto": verdict,
        "colision": "Sí" if meta["collision"] else "No",
        "colision_con": meta.get("collision_with") or "",
        "v_impacto_rel_kmh": round(meta["impact_vrel_mps"] * 3.6, 1) if meta["collision"] else 0.0,
        "gap_minimo_m": round(float(max(gaps.min(), 0.0)), 2) if gaps.size else None,
        "t_alerta_s": rnd(t[i_warn], 2) if i_warn is not None else None,
        "t_freno_s": rnd(t[i_brake], 2) if i_brake is not None else None,
        "t_aeb_s": rnd(tb, 2),
        "adelanto_fcw_s": rnd(tb - t[i_warn], 2) if tb is not None and i_warn is not None else None,
        "ttc_al_frenar_s": rnd(log["ttc_radar"][i_brake], 2) if i_brake is not None else None,
        "gap_al_frenar_m": rnd(log["gap_gt"][i_brake], 1) if i_brake is not None else None,
        "demanda_min_pct": rnd(dem_on.min(), 0) if dem_on.size else None,
        "demanda_max_pct": rnd(dem_on.max(), 0) if dem_on.size else None,
        "decel_media_mps2": rnd(-log["a_ego"][acting].mean(), 1) if acting.any() else None,
        "error_radar_medio_m": round(float(err.mean()), 2) if err.size else None,
        "error_acel_obj_rms": round(float(np.sqrt(np.mean(a_err ** 2))), 2) if a_err.size else None,
    }


def state_spans(ax, t, state):
    """Sombrea el fondo según el estado del AEB."""
    start = 0
    for i in range(1, len(state) + 1):
        if i == len(state) or state[i] != state[start]:
            color = STATE_COLORS.get(state[start])
            if color:
                ax.axvspan(t[start], t[min(i, len(t) - 1)], color=color, alpha=0.45, lw=0)
            start = i


def run_title(meta, m):
    title = f"{meta['scenario']['name']} — ego {m['v_ego_kmh']} km/h — {m['logica']}"
    if meta["collision"]:
        outcome = f"COLISIÓN con {m['colision_con']} a {m['v_impacto_rel_kmh']} km/h"
    elif m["esperado"] == "No frenar":
        outcome = f"Sin colisión — intervención del AEB: {m['intervencion']} (esperado: no frenar)"
    else:
        outcome = f"Sin colisión — distancia mínima {m['gap_minimo_m']} m"
    desc = meta["scenario"].get("description", "")
    return f"{title}\n{outcome}" + (f"\n{desc}" if desc else "")


def decorate(axes, t, log, meta):
    """Fondo por estado del AEB, línea de colisión, eventos del guion, rejilla y leyendas."""
    i_col = first(log["collision"] == 1)
    events = [(et, txt) for et, txt in meta.get("events", []) if et <= t[-1]]
    for ax in axes:
        state_spans(ax, t, log["aeb_state"])
        if i_col is not None:
            ax.axvline(t[i_col], color="red", lw=2)
        for et, _ in events:
            ax.axvline(et, color="black", lw=1, ls=":")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)
    for k, (et, txt) in enumerate(events):
        axes[0].annotate(txt, (et, 1.0), xycoords=("data", "axes fraction"), xytext=(3, -12 - 11 * k),
                         textcoords="offset points", fontsize=7, va="top")
    present = [s for s in STATE_COLORS if s in set(log["aeb_state"])]   # solo los estados de esta corrida
    handles = [plt.Rectangle((0, 0), 1, 1, color=STATE_COLORS[s], alpha=0.45) for s in present]
    axes[0].legend(handles + axes[0].get_legend_handles_labels()[0],
                   present + axes[0].get_legend_handles_labels()[1], loc="lower left", fontsize=7, ncol=3)


def plot_run(run_dir, log, meta, m):
    """graficas.png: velocidad del ego, BTN y porcentaje de frenado, contra el tiempo."""
    t = log["t"]
    btn_logic = meta.get("aeb_logic", "ttc") == "btn"
    fig, axes = plt.subplots(3, 1, figsize=(11, 9.5), sharex=True)
    fig.suptitle(run_title(meta, m), fontsize=12, fontweight="bold")

    ax = axes[0]
    ax.plot(t, log["v_ego"] * 3.6, label="Ego (El Fantástico)", lw=2, color="tab:blue")
    ax.set_ylabel("Velocidad del ego [km/h]")
    ax.set_ylim(bottom=0)

    ax = axes[1]
    th = meta["aeb"]
    if btn_logic:
        ax.plot(t, log["btn"], label="BTN = D_req / D_max", lw=2, color="tab:purple")
        for key, name in (("btn_fcw", "Alerta"), ("btn_on", "Frenado")):
            ax.axhline(th[key], color="gray", ls=":", lw=1)
            ax.text(t[-1], th[key], f" {name} {th[key]}", va="center", fontsize=8, color="gray")
        ax.set_ylabel("BTN")
        ax.set_ylim(0, 1.05)
    else:   # la lógica por TTC no calcula BTN
        ax.plot(t, np.clip(log["ttc_radar"], 0, 6), label="TTC (esta lógica no usa BTN)", lw=2, color="tab:purple")
        ax.set_ylabel("TTC [s]")
        ax.set_ylim(0, 6.2)

    ax = axes[2]
    demand = log["demand_pct"] if meta["aeb_enabled"] else log["shadow_demand_pct"]
    ax.step(t, demand, where="post", lw=2, color="tab:red",
            label="Demanda de freno del AEB" + ("" if meta["aeb_enabled"] else " (sombra, no aplicada)"))
    ax.set_ylabel("Frenado [%]")
    ax.set_ylim(-5, 105)
    ax.set_xlabel("Tiempo [s]")

    decorate(axes, t, log, meta)
    axes[2].legend(loc="center left", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(run_dir, "graficas.png"), dpi=120)
    plt.close(fig)


def results_root(vehicle, source="radar"):
    """results/<perfil>/; las corridas con entrada «lider» van en una subcarpeta lider/."""
    root = os.path.join(RESULTS_DIR, vehicle)
    return root if source == "radar" else os.path.join(root, "lider")


def plot_one(run_dir):
    """Gráficas de una sola corrida; devuelve sus métricas."""
    log, meta = load(run_dir)
    m = metrics(log, meta)
    plot_run(run_dir, log, meta, m)
    return m


def main():
    ap = argparse.ArgumentParser(description="Regenera las gráficas de todas las corridas.")
    ap.add_argument("--entrada", choices=["radar", "lider"], default="radar")
    args = ap.parse_args()
    folder = os.path.join(results_root(C.VEHICLE, args.entrada), "ensayos")
    summary = []
    for run_dir in sorted(glob.glob(os.path.join(folder, "*"))):
        if not os.path.exists(os.path.join(run_dir, "log.csv")):
            continue
        m = plot_one(run_dir)
        summary.append(m)
        gap_min = "  —  " if m["gap_minimo_m"] is None else f"{m['gap_minimo_m']:5.2f}"
        print(f"{m['corrida']:40s} colisión={m['colision']:2s} v_impacto={m['v_impacto_rel_kmh']:5.1f} km/h "
              f"dist_min={gap_min} m  intervino={m['intervencion']}")
    if not summary:
        print(f"No hay corridas en {folder}. Ejecute primero run_scenario.py")
        return
    with open(os.path.join(folder, "resumen.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    print(f"\nResumen en {os.path.join(folder, 'resumen.csv')}")


if __name__ == "__main__":
    main()
