"""
Extrae de las pruebas de manejo lo que sirve al AEB y genera la figura de DATOS_VEHICULO.md.

Uso:  python analizar_datos_vehiculo.py [carpeta_de_csv]
"""

import csv
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config as C
from aeb_core.logic import required_deceleration

# Valores con que se analizaron las pruebas de manejo (solo para DATOS_VEHICULO.md)
AMAROK = {
    "d_max": 7.7,               # ESTIMADO: mayor aceleración horizontal medida (7.67 m/s², doble cambio de carril)
    "radar_pitch_deg": -0.35,   # MEDIDO: cabeceo del chasis casi sin aceleración lateral (ISO 4138)
    "btn_on": 0.68,             # umbral de frenado con que se evaluó el falso objeto del piso
}
CARLA_ORIGINAL_MAX = 10.47      # frenada máxima medida del auto original de CARLA (fricción 3.5)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(HERE, "..", "csv-20261102T002350Z-1-001", "csv")
OUT_DIR = os.path.join(HERE, "results", "datos_vehiculo")

INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#b9b8b2"


def read(folder, prefix):
    name = next(f for f in os.listdir(folder) if f.startswith(prefix) and f.endswith(".csv"))
    with open(os.path.join(folder, name), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows


def series(rows, kind=None, colour=None):
    keep = [r for r in rows if (kind is None or r["kind"] == kind) and (colour is None or r["colour"] == colour)]
    return np.array([[float(r["x"]), float(r["y"])] for r in keep])


def metric(folder, prefix, name, col):
    return next(float(r[col]) for r in read(folder, prefix) if r["metric"] == name)


def analyze(folder):
    steady = series(read(folder, "p11_"), "measured")
    pitch = series(read(folder, "p16_"), "measured")
    bit_low = np.vstack([series(read(folder, "p27_"), colour=c) for c in ("red", "blue")])
    bit_high = np.vstack([series(read(folder, "p30_"), colour=c) for c in ("red", "blue")])
    slip_low = {c: series(read(folder, "p28_"), colour=c) for c in ("red", "blue")}
    slip_high = {c: series(read(folder, "p31_"), colour=c) for c in ("red", "blue")}
    dev_high = {c: series(read(folder, "p32_"), colour=c) for c in ("red", "blue")}
    small = np.abs(pitch[:, 0]) < 1.5
    res = {
        "ay_estacionaria": float(np.abs(steady[:, 0]).max()),
        "ay_dlc_esp_on": max(metric(folder, "p35_", "Lateral acceleration", c) for c in ("MAX_1", "MAX_2")),
        "ay_dlc_esp_on_min": min(metric(folder, "p35_", "Lateral acceleration", c) for c in ("MIN_1", "MIN_2")),
        "ay_dlc_esp_off": max(metric(folder, "p44_", "Lateral acceleration", c) for c in ("MAX_1", "MAX_2")),
        "ax_curva_1": float(-bit_low[:, 0].min()),
        "ax_curva_2": float(-bit_high[:, 0].min()),
        "pitch_izq": float(np.median(pitch[small & (pitch[:, 0] > 0), 1])),
        "pitch_der": float(np.median(pitch[small & (pitch[:, 0] < 0), 1])),
        "pitch_max": float(pitch[:, 1].min()),
        "deriva_max_serie1_der": float(np.abs(slip_low["red"][:, 1]).max()),
        "deriva_max_serie1_izq": float(np.abs(slip_low["blue"][:, 1]).max()),
        "deriva_max_serie2_der": float(np.abs(slip_high["red"][:, 1]).max()),
        "deriva_max_serie2_izq": float(np.abs(slip_high["blue"][:, 1]).max()),
        "desvio_serie2_der": float(dev_high["red"][:, 1].max()),
        "desvio_serie2_izq": float(dev_high["blue"][:, 1].max()),
    }
    return res, pitch


def false_ground(pitch_deg, d_max, btn_on, v):
    """Distancia a la que el piso pasa el filtro de altura sin corregir el cabeceo, y BTN que produciría."""
    z = C.RADAR["mount_z"]
    depth = np.arange(1.0, 150.0, 0.1)
    height = z + depth * np.sin(np.arcsin(-z / depth) - math.radians(pitch_deg))
    above = depth[height > C.PERCEPTION["min_height"]]
    d = float(above[0]) if above.size else math.inf
    d_req = required_deceleration(d, v, v, 0.0, 0.0, C.AEB_BTN["tau"], C.AEB_BTN["d0"], d_max)
    return depth, height, d, d_req / d_max


def figure(res, pitch, depth, height, d_false):
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "text.color": INK, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlelocation": "left", "axes.titlesize": 11})
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))

    ax = axes[0]
    bars = [("Frenada en curva, Amarok (no es su límite)", res["ax_curva_2"], GREY),
            ("Lateral estacionaria, Amarok", res["ay_estacionaria"], BLUE),
            ("Doble cambio de carril, Amarok", -res["ay_dlc_esp_on_min"], BLUE),
            ("Frenada máxima del auto original de CARLA", CARLA_ORIGINAL_MAX, ORANGE)]
    y = np.arange(len(bars))
    ax.barh(y, [b[1] for b in bars], color=[b[2] for b in bars], height=0.55)
    for yi, (label, val, _) in zip(y, bars):
        ax.text(0.15, yi + 0.36, label, fontsize=9, color=INK, va="bottom")
        ax.text(val + 0.12, yi, f"{val:.2f}", va="center", fontsize=9, color=INK)
    ax.set(yticks=[], xlim=(0, 12), ylim=(-0.5, len(bars) - 0.1), xlabel="Aceleración horizontal [m/s²]")
    ax.set_title("El auto de CARLA frena 36 % más de lo medido")
    ax.xaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)

    ax = axes[1]
    ax.scatter(pitch[:, 0], pitch[:, 1], s=2, color=GREY, rasterized=True)
    ax.axhline(AMAROK["radar_pitch_deg"], color=BLUE, lw=2)
    ax.text(8, AMAROK["radar_pitch_deg"] + 0.012, "−0.35° (valor medido)", fontsize=9, color=INK, ha="right")
    ax.set(xlabel="Aceleración lateral [m/s²]", ylabel="Cabeceo [°]", ylim=(-0.7, -0.2))
    ax.set_title("El chasis mide un cabeceo constante, aun sin girar")
    ax.grid(True, color=GRID)
    ax.set_axisbelow(True)

    ax = axes[2]
    ax.plot(depth, height, color=ORANGE, lw=2)
    ax.plot(depth, np.zeros_like(depth), color=BLUE, lw=2)
    ax.axhline(C.PERCEPTION["min_height"], color=MUTED, lw=1, ls="--")
    ax.text(1, C.PERCEPTION["min_height"] + 0.012, "filtro de altura: 0.25 m", fontsize=9, color=MUTED)
    ax.text(70, 0.455, "sin corregir", fontsize=9, color=INK, ha="right")
    ax.text(70, 0.015, "corrigiendo el cabeceo", fontsize=9, color=INK, ha="right")
    ax.plot([d_false], [C.PERCEPTION["min_height"]], "o", color=ORANGE, ms=8, mec="white", mew=2)
    ax.annotate(f"falso objeto a {d_false:.0f} m", (d_false, C.PERCEPTION["min_height"]), xytext=(8, -14),
                textcoords="offset points", fontsize=9, color=INK)
    ax.set(xlim=(0, 100), ylim=(-0.02, 0.62), xlabel="Distancia al piso [m]", ylabel="Altura aparente del piso [m]")
    ax.set_title("Sin corregirlo, el radar confunde el piso con un objeto")
    ax.grid(True, color=GRID)
    ax.set_axisbelow(True)

    fig.tight_layout()
    path = os.path.join(OUT_DIR, "datos_vehiculo.png")
    fig.savefig(path, dpi=130, facecolor="white")
    plt.close(fig)
    return path


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    os.makedirs(OUT_DIR, exist_ok=True)
    res, pitch = analyze(folder)
    veh = AMAROK
    d_max = veh["d_max"]
    for k, v in res.items():
        print(f"{k:26s} {v:8.3f}")
    print(f"{'mu_estimado':26s} {max(res['ay_dlc_esp_on'], -res['ay_dlc_esp_on_min']) / 9.81:8.3f}")
    depth, height, d_false, _ = false_ground(veh["radar_pitch_deg"], d_max, veh["btn_on"], 22.0)
    for v in (10.0, 16.0, 18.0, 20.0, 22.0):
        print(f"Piso a {d_false:.1f} m sin corregir, ego a {v * 3.6:3.0f} km/h: "
              f"BTN {false_ground(veh['radar_pitch_deg'], d_max, veh['btn_on'], v)[3]:.2f} (activa con {veh['btn_on']})")
    print(figure(res, pitch, depth, height, d_false))


if __name__ == "__main__":
    main()
