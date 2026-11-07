"""
Genera la presentación técnica de la simulación AEB (python-pptx).

Uso:  python presentacion/generar_presentacion.py
Lee   results/resumen.csv y results/calibracion_freno/curva_demanda_desaceleracion.csv
Crea  presentacion/AEB_El_Fantastico_Simulacion.pptx
"""

import csv
import os
import re
import sys

from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import config as CFG  # noqa: E402
from actuator import BrakeActuator  # noqa: E402

RESULTS = os.path.join(ROOT, "results")
IMG = os.path.join(HERE, "img")
OUT = os.path.join(HERE, "AEB_El_Fantastico_Simulacion.pptx")

# --- Paleta: grafito + rojo de competición ---------------------------------
DARK = RGBColor(0x16, 0x19, 0x1D)
INK = RGBColor(0x1F, 0x23, 0x28)
SLATE = RGBColor(0x5B, 0x66, 0x70)
MUTED = RGBColor(0x8A, 0x94, 0x9E)
CARD = RGBColor(0xF1, 0xF3, 0xF5)
LINE = RGBColor(0xD5, 0xDA, 0xDF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RED = RGBColor(0xC8, 0x10, 0x2E)
AMBER = RGBColor(0xE0, 0xA1, 0x00)
ORANGE = RGBColor(0xE8, 0x6A, 0x1C)
GREEN = RGBColor(0x2E, 0x8B, 0x57)
STEEL = RGBColor(0x3A, 0x6E, 0xA5)
CODE_BG = RGBColor(0x1E, 0x22, 0x27)
CODE_FG = RGBColor(0xE6, 0xE8, 0xEB)
CODE_COMMENT = RGBColor(0x8F, 0xBC, 0x8F)

BODY = "Calibri"
MONO = "Consolas"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
SW, SH = 13.333, 7.5
LAYOUT_TITLE_ONLY = prs.slide_layouts[5]
LAYOUT_BLANK = prs.slide_layouts[6]
slide_no = 0


# ============================================================================
# Utilidades de dibujo
# ============================================================================
def add_runs(paragraph, text, size, color, bold=False, italic=False, font=BODY):
    """Texto con subíndices _{..} y superíndices ^{..}."""
    for part in re.split(r"(_\{[^}]*\}|\^\{[^}]*\})", text):
        if not part:
            continue
        baseline = None
        if part.startswith("_{"):
            part, baseline = part[2:-1], "-25000"
        elif part.startswith("^{"):
            part, baseline = part[2:-1], "30000"
        r = paragraph.add_run()
        r.text = part
        f = r.font
        f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
        f.color.rgb = color
        if baseline:
            r.font._element.set("baseline", baseline)


def set_bullet(p, level=0):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(Inches(0.28 + 0.28 * level))))
    pPr.set("indent", str(int(-Inches(0.22))))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    bu = pPr.makeelement(qn("a:buChar"), {"char": "•"})
    pPr.append(bu)


def text(slide, x, y, w, h, paras, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, font=BODY, space_after=6, name=None, line_spacing=None):
    """paras: str o lista de str / dict(text, size, color, bold, bullet, italic, font, align)."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    if isinstance(paras, str):
        paras = [paras]
    for i, item in enumerate(paras):
        d = {"text": item} if isinstance(item, str) else dict(item)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = d.get("align", align)
        p.space_after = Pt(d.get("space_after", space_after))
        if line_spacing:
            p.line_spacing = line_spacing
        if d.get("bullet"):
            set_bullet(p, d.get("level", 0))
        add_runs(p, d["text"], d.get("size", size), d.get("color", color), d.get("bold", bold),
                 d.get("italic", False), d.get("font", font))
    return tb


def rect(slide, x, y, w, h, fill=CARD, line=None, rounded=True, name=None, shadow=False):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
                                 Inches(x), Inches(y), Inches(w), Inches(h))
    if rounded:
        shp.adjustments[0] = 0.08
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(1)
    if not shadow:
        shp.shadow.inherit = False
    if name:
        shp.name = name
    shp.text_frame.text = ""
    return shp


def box_text(shp, paras, size=14, color=INK, bold=False, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
             font=BODY, margin=0.08):
    tf = shp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(margin)
    tf.margin_top = tf.margin_bottom = Inches(0.04)
    if isinstance(paras, str):
        paras = [paras]
    for i, item in enumerate(paras):
        d = {"text": item} if isinstance(item, str) else dict(item)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = d.get("align", align)
        p.space_after = Pt(d.get("space_after", 2))
        add_runs(p, d["text"], d.get("size", size), d.get("color", color), d.get("bold", bold),
                 d.get("italic", False), d.get("font", font))


def circle(slide, x, y, d, fill, label, size=16, color=WHITE):
    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.shadow.inherit = False
    box_text(shp, label, size=size, color=color, bold=True, margin=0)
    return shp


def arrow(slide, x1, y1, x2, y2, color=SLATE, width=1.75, dash=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    if dash:
        c.line.dash_style = MSO_LINE.DASH
    ln = c.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def line(slide, x1, y1, x2, y2, color=LINE, width=1.0, dash=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    if dash:
        c.line.dash_style = MSO_LINE.DASH
    return c


def code(slide, x, y, w, h, src, size=12, title=None):
    bg = rect(slide, x, y, w, h, fill=CODE_BG, rounded=True, name="Código")
    top = y + 0.2
    if title:
        text(slide, x + 0.25, y + 0.15, w - 0.5, 0.3, title, size=11, color=MUTED, font=MONO)
        top = y + 0.5
    tb = slide.shapes.add_textbox(Inches(x + 0.25), Inches(top), Inches(w - 0.5), Inches(h - (top - y) - 0.15))
    tf = tb.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, raw in enumerate(src.strip("\n").split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(0)
        if "#" in raw and not raw.strip().startswith('"'):
            body, comment = raw.split("#", 1)
            add_runs_plain(p, body, size, CODE_FG)
            add_runs_plain(p, "#" + comment, size, CODE_COMMENT)
        else:
            add_runs_plain(p, raw, size, CODE_FG)
    return bg


def add_runs_plain(p, s, size, color):
    r = p.add_run()
    r.text = s
    r.font.size, r.font.name = Pt(size), MONO
    r.font.color.rgb = color


def table(slide, x, y, w, col_w, rows, size=13, header_fill=DARK, row_h=0.42, first_col_bold=False,
          cell_colors=None):
    n_rows, n_cols = len(rows), len(rows[0])
    shp = slide.shapes.add_table(n_rows, n_cols, Inches(x), Inches(y), Inches(w), Inches(row_h * n_rows))
    tbl = shp.table
    tblPr = shp._element.graphic.graphicData.tbl.tblPr
    for attr in ("bandRow", "firstRow"):
        tblPr.set(attr, "0")
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if i == 0:
                cell.fill.fore_color.rgb = header_fill
            else:
                cell.fill.fore_color.rgb = WHITE if i % 2 else CARD
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            color = WHITE if i == 0 else INK
            bold = i == 0 or (first_col_bold and j == 0)
            if cell_colors and i > 0 and (i, j) in cell_colors:
                color, bold = cell_colors[(i, j)], True
            add_runs(p, str(val), size, color, bold)
    return shp


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s


def footer(slide, dark=False):
    global slide_no
    col = MUTED
    text(slide, 0.6, 7.05, 8, 0.25, "AEB El Fantástico · Simulación en CARLA", size=10, color=col, name="Pie")
    text(slide, 11.73, 7.05, 1.0, 0.25, str(slide_no), size=10, color=col, align=PP_ALIGN.RIGHT, name="Número")


def content_slide(title, subtitle=None):
    global slide_no
    slide_no += 1
    s = prs.slides.add_slide(LAYOUT_TITLE_ONLY)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = WHITE
    t = s.shapes.title
    t.left, t.top, t.width, t.height = Inches(0.6), Inches(0.38), Inches(12.1), Inches(0.75)
    tf = t.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.word_wrap = True
    tf.text = ""
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    add_runs(p, title, 34, INK, bold=True)
    if subtitle:
        text(s, 0.6, 1.08, 12.1, 0.4, subtitle, size=16, color=SLATE, name="Subtítulo")
    footer(s)
    return s


def divider(number, title, desc):
    global slide_no
    slide_no += 1
    s = prs.slides.add_slide(LAYOUT_TITLE_ONLY)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = DARK
    text(s, 0.9, 2.2, 3, 1.2, number, size=72, color=RED, bold=True, name="Número de sección")
    t = s.shapes.title
    t.left, t.top, t.width, t.height = Inches(0.9), Inches(3.45), Inches(11), Inches(0.9)
    tf = t.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.text = ""
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    add_runs(p, title, 40, WHITE, bold=True)
    text(s, 0.9, 4.45, 10.5, 1.0, desc, size=18, color=MUTED, name="Descripción")
    footer(s, dark=True)
    return s


def picture(slide, path, x, y, w=None, h=None, crop=None, border=True, name=None):
    pic = slide.shapes.add_picture(path, Inches(x), Inches(y),
                                   Inches(w) if w else None, Inches(h) if h else None)
    if crop:
        l, t, r, b = crop
        pic.crop_left, pic.crop_top, pic.crop_right, pic.crop_bottom = crop
        iw, ih = pic.image.size
        aspect = (iw * (1 - l - r)) / (ih * (1 - t - b))
        if w:
            pic.height = int(pic.width / aspect)
        else:
            pic.width = int(pic.height * aspect)
    if border:
        pic.line.color.rgb = LINE
        pic.line.width = Pt(0.75)
    if name:
        pic.name = name
    return pic


def style_chart_axes(ch, size=12):
    for ax in (ch.category_axis, ch.value_axis):
        ax.tick_labels.font.size = Pt(size)
        ax.tick_labels.font.color.rgb = SLATE
        ax.format.line.color.rgb = LINE
    ch.value_axis.has_major_gridlines = True
    ch.value_axis.major_gridlines.format.line.color.rgb = LINE
    ch.font.name = BODY


def axis_title(ax, s, size=12):
    ax.has_title = True
    ax.axis_title.text_frame.text = s
    r = ax.axis_title.text_frame.paragraphs[0].runs[0]
    r.font.size, r.font.bold = Pt(size), False
    r.font.color.rgb = SLATE


# ============================================================================
# Datos
# ============================================================================
with open(os.path.join(RESULTS, "resumen.csv"), encoding="utf-8") as f:
    SUMMARY = list(csv.DictReader(f))
with open(os.path.join(RESULTS, "calibracion_freno", "curva_demanda_desaceleracion.csv")) as f:
    CALIB = list(csv.DictReader(f))


def runs(aeb):
    return [r for r in SUMMARY if r["aeb"] == aeb]


with_aeb, without_aeb = runs("Sí"), runs("No")
avoided = sum(r["colision"] == "No" for r in with_aeb)
limit_case = next(r for r in with_aeb if r["colision"] == "Sí")
limit_base = next(r for r in without_aeb if r["escenario"] == limit_case["escenario"]
                  and r["v_ego_kmh"] == limit_case["v_ego_kmh"])
reduction = 100 * (1 - float(limit_case["v_impacto_rel_kmh"]) / float(limit_base["v_impacto_rel_kmh"]))
radar_err = max(abs(float(r["error_radar_medio_m"])) for r in SUMMARY)


def state_times(run):
    """Primer instante de cada estado AEB en una corrida."""
    times = {}
    with open(os.path.join(RESULTS, run, "log.csv")) as f:
        for r in csv.DictReader(f):
            times.setdefault(r["aeb_state"], float(r["t"]))
    return times


def summary_row(esc, v_kmh, aeb):
    return next(r for r in SUMMARY if r["escenario"] == esc and r["v_ego_kmh"] == str(v_kmh) and r["aeb"] == aeb)

# ============================================================================
# 1. Portada
# ============================================================================
slide_no += 1
s = prs.slides.add_slide(LAYOUT_TITLE_ONLY)
s.background.fill.solid()
s.background.fill.fore_color.rgb = DARK
picture(s, os.path.join(IMG, "frenado.jpg"), 7.0, 0, h=SH, crop=(0.375, 0.0, 0.15, 0.0), border=False, name="Imagen portada")
text(s, 0.7, 1.35, 6.0, 0.4, "PROYECTO EL FANTÁSTICO · SIMULACIÓN AEB", size=14, color=RED, bold=True)
t = s.shapes.title
t.left, t.top, t.width, t.height = Inches(0.7), Inches(1.9), Inches(6.0), Inches(2.4)
tf = t.text_frame
tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
tf.word_wrap = True
tf.vertical_anchor = MSO_ANCHOR.TOP
tf.text = ""
p = tf.paragraphs[0]
p.alignment = PP_ALIGN.LEFT
add_runs(p, "Frenado autónomo de emergencia en simulación", 42, WHITE, bold=True)
text(s, 0.7, 4.45, 5.9, 1.2,
     "Modelos, algoritmos, código y resultados en CARLA 0.9.16 + Python, y ruta de implementación en el Porsche real",
     size=18, color=MUTED)
text(s, 0.7, 6.4, 5, 0.35, "Presentación técnica · Octubre 2026", size=14, color=MUTED)
notes(s, "Presentación técnica de la simulación del sistema de frenado autónomo de emergencia (AEB) para El Fantástico. "
         "Cubre arquitectura, modelos, ecuaciones, código, resultados, limitaciones y la ruta para llevarlo al vehículo real.")

# ============================================================================
# 2. Resumen ejecutivo
# ============================================================================
s = content_slide("Resumen ejecutivo",
                  "Un AEB por TTC alimentado por un radar simulado evita la colisión en casi todos los ensayos Euro NCAP")
stats = [
    (f"{avoided} / {len(with_aeb)}", "colisiones evitadas con AEB", GREEN),
    (f"{len(without_aeb)} / {len(without_aeb)}", "colisiones sin AEB (mismos ensayos)", RED),
    (f"−{reduction:.0f} %", f"velocidad de impacto en el caso límite ({limit_base['v_impacto_rel_kmh']} → {limit_case['v_impacto_rel_kmh']} km/h)", ORANGE),
    (f"< {radar_err:.2f} m", "error medio del radar simulado frente a la distancia real", STEEL),
]
cw, gap, x0 = 2.85, 0.233, 0.6
for i, (big, small, col) in enumerate(stats):
    x = x0 + i * (cw + gap)
    rect(s, x, 1.85, cw, 2.35, fill=CARD, name=f"Indicador {i + 1}")
    text(s, x + 0.25, 2.1, cw - 0.5, 1.0, big, size=46, color=col, bold=True)
    text(s, x + 0.25, 3.15, cw - 0.5, 0.95, small, size=14, color=SLATE)
text(s, 0.6, 4.65, 12.1, 0.4, "Lo que esto significa", size=20, bold=True)
text(s, 0.6, 5.15, 12.1, 1.7, [
    {"text": "La lógica de decisión es simple, explicable y separada del actuador: entrega una demanda de 0–100 %, igual que la interfaz del Porsche.", "bullet": True},
    {"text": "Los 18 ensayos son reproducibles (paso fijo de 50 ms) y generan CSV, gráficas y video para análisis.", "bullet": True},
    {"text": "La dinámica, el actuador y los umbrales son supuestos: los resultados validan la lógica, no el vehículo real.", "bullet": True},
], size=16)
notes(s, "Mensaje principal: con AEB se evitan 8 de 9 colisiones; el caso no evitado (CCRb a 79 km/h) reduce el impacto casi a la mitad. "
         "La simulación valida la lógica; los parámetros físicos deben medirse en el Porsche.")

# ============================================================================
# 3. Contexto y principios
# ============================================================================
s = content_slide("Contexto y alcance")
text(s, 0.6, 1.4, 5.6, 0.4, "Qué se busca", size=20, bold=True)
text(s, 0.6, 1.95, 5.6, 4.6, [
    {"text": "Desarrollar y evaluar la lógica AEB de El Fantástico en un entorno virtual antes de integrarla en el vehículo.", "bullet": True},
    {"text": "Escenarios reproducibles de aproximación a un vehículo detenido, lento o que frena.", "bullet": True},
    {"text": "Relación razonable con el Porsche: usar señales que el vehículo realmente puede medir.", "bullet": True},
    {"text": "Complejidad baja o moderada, reutilizando CARLA y su API de Python.", "bullet": True},
    {"text": "Fuera de alcance por ahora: integración física, fusión de sensores y V2V.", "bullet": True, "color": SLATE},
], size=16, space_after=10)
principles = [
    ("1", "Simple y explicable", "Cada decisión se reduce a una ecuación (TTC) y a umbrales visibles."),
    ("2", "Sensores del Porsche", "La entrada es un radar análogo al AUMOVIO ARS 548 documentado."),
    ("3", "Demanda ≠ actuador", "El AEB entrega 0–100 %; la conversión a pasos del motor queda fuera."),
    ("4", "Trazabilidad", "Cada parámetro está marcado como DOCUMENTADO, SUPUESTO o SIMULACIÓN."),
]
text(s, 6.9, 1.4, 5.8, 0.4, "Principios de diseño", size=20, bold=True)
for i, (n, head, body) in enumerate(principles):
    y = 1.95 + i * 1.18
    circle(s, 6.9, y, 0.55, RED, n, size=18)
    text(s, 7.65, y - 0.02, 5.1, 0.35, head, size=17, bold=True)
    text(s, 7.65, y + 0.36, 5.1, 0.7, body, size=14, color=SLATE)
notes(s, "El proyecto tiene dos áreas: simulación (esta etapa) e implementación física. "
         "Los principios guiaron cada decisión: simplicidad, señales reales, separación demanda-actuador y trazabilidad de supuestos.")

# ============================================================================
# 4. Sección: arquitectura
# ============================================================================
divider("01", "Arquitectura y entorno", "Cómo se organiza el sistema, en qué se ejecuta y por qué se eligió este enfoque")

# ============================================================================
# 5. Arquitectura
# ============================================================================
s = content_slide("Arquitectura del sistema",
                  "Cadena de cinco bloques; la verdad del simulador solo se usa para evaluar")
blocks = [
    ("Radar simulado", "Análogo ARS 548", "sensor.other.radar", STEEL),
    ("Percepción", "Objetivo en el carril", "perception.py", INK),
    ("Lógica AEB", "TTC por etapas", "aeb.py", RED),
    ("Actuador", "Retardo + rampa", "actuator.py", INK),
    ("Vehículo", "Física de CARLA", "VehicleControl", STEEL),
]
bw, bh, by = 2.05, 1.35, 2.05
xs = [0.6 + i * 2.5 for i in range(5)]
for (head, sub, mod, col), x in zip(blocks, xs):
    b = rect(s, x, by, bw, bh, fill=col, name=f"Bloque {head}")
    box_text(b, [{"text": head, "size": 18, "bold": True, "color": WHITE},
                 {"text": sub, "size": 14, "color": WHITE}])
    text(s, x, by + bh + 0.12, bw, 0.3, mod, size=12, color=SLATE, font=MONO, align=PP_ALIGN.CENTER)
signals = ["d, θ, φ, v_{r}", "d_{obj}, v_{c}", "demanda %", "brake 0–1"]
for i, sig in enumerate(signals):
    x1, x2 = xs[i] + bw, xs[i + 1]
    arrow(s, x1 + 0.03, by + bh / 2, x2 - 0.03, by + bh / 2, color=SLATE, width=2)
    mid = (x1 + x2) / 2
    text(s, mid - 0.8, by - 0.42, 1.6, 0.3, sig, size=13, color=INK, align=PP_ALIGN.CENTER)
# frontera con el sistema real
fx = xs[3] - 0.22
line(s, fx, by - 0.05, fx, 4.65, color=RED, width=1.5, dash=True)
text(s, fx + 0.12, 3.95, 3.2, 0.7, "Frontera con el Porsche: aquí entra la conversión % → pasos del motor",
     size=12, color=RED)
# velocidad propia
vy = 5.15
b = rect(s, xs[2] - 0.25, vy, bw + 0.5, 0.62, fill=CARD, name="Velocidad propia")
box_text(b, [{"text": "v_{ego} (equivale a /v2x/kinematics/speed)", "size": 13}])
arrow(s, xs[2] + bw / 2, vy, xs[2] + bw / 2, by + bh + 0.5, color=SLATE)
# evaluación
b = rect(s, 0.6, 6.05, 12.1, 0.75, fill=CARD, name="Evaluación")
box_text(b, [{"text": "Verdad del simulador (posiciones y velocidades reales) → métricas, gráficas y video.  El AEB nunca la usa.",
              "size": 14, "color": SLATE}])
notes(s, "El radar produce detecciones crudas (distancia, azimut, elevación, Doppler). La percepción extrae un objetivo; la lógica calcula TTC y una demanda; "
         "el actuador modela retardo y rampa. La línea roja marca dónde el sistema real sustituye el modelo por la conversión a pasos del motor.")

# ============================================================================
# 6. Entorno de simulación
# ============================================================================
s = content_slide("Entorno de simulación")
picture(s, os.path.join(IMG, "aproximacion.jpg"), 0.6, 1.4, w=6.3, name="Vista del ensayo")
text(s, 0.6, 5.08, 6.3, 0.5, "Cámara de persecución de un ensayo CCRs a 79 km/h, con la telemetría superpuesta",
     size=12, color=SLATE)
env = [
    ["Elemento", "Configuración"],
    ["Simulador", "CARLA 0.9.16 (Unreal Engine 4), Windows 11"],
    ["Lenguaje", "Python 3.12 en entorno virtual (.venv)"],
    ["Mapa", "Town04, tramo recto de autopista de 440 m"],
    ["Paso de tiempo", "Fijo de 50 ms (20 Hz), modo síncrono"],
    ["Ego (El Fantástico)", "vehicle.mercedes.coupe_2020, 1630 kg"],
    ["Objetivo", "vehicle.lincoln.mkz_2020, velocidad impuesta"],
    ["Salidas", "CSV, JSON, MP4 y PNG por corrida"],
]
table(s, 7.3, 1.4, 5.4, [1.9, 3.5], env, size=13, row_h=0.5, first_col_bold=True)
text(s, 7.3, 5.6, 5.4, 1.2, [
    {"text": "CARLA no incluye un Porsche: el Mercedes es solo la representación visual.", "bullet": True},
    {"text": "Town04 es el mapa que el equipo ya usaba en sus pruebas de planificación.", "bullet": True},
], size=14, color=SLATE)
notes(s, "El modo síncrono con paso fijo hace que cada corrida sea determinista y repetible. "
         "El vehículo visual no implica la misma dinámica que el Porsche; eso se trata como supuesto.")

# ============================================================================
# 7. carla_aebs vs. enfoque adoptado
# ============================================================================
s = content_slide("Repositorio candidato frente al enfoque adoptado",
                  "Se revisó el código de carla_aebs antes de decidir; se tomaron ideas, no el algoritmo")
cols = [
    ("carla_aebs (candidato)", RED, [
        "Dueling DQN + CNN de seguimiento de carril",
        "Distancia estimada con cámara semántica y el ancho conocido del objetivo",
        "CARLA 0.9.11, Linux y conda",
        "Requiere entrenar y validar una red neuronal",
        "Decisiones difíciles de explicar y certificar",
    ]),
    ("Enfoque adoptado", GREEN, [
        "TTC por etapas con umbrales explícitos",
        "Radar con distancia y Doppler, como el ARS 548",
        "CARLA 0.9.16 en Windows, con dependencias mínimas",
        "Sin entrenamiento: funciona desde la primera corrida",
        "Cada decisión se traza a una ecuación y un umbral",
    ]),
]
for i, (head, col, items) in enumerate(cols):
    x = 0.6 + i * 6.25
    rect(s, x, 1.7, 5.85, 4.25, fill=CARD, name=head)
    circle(s, x + 0.3, 1.95, 0.5, col, "✕" if i == 0 else "✓", size=18)
    text(s, x + 1.0, 1.98, 4.6, 0.45, head, size=20, bold=True)
    text(s, x + 0.3, 2.75, 5.3, 3.1, [{"text": it, "bullet": True} for it in items], size=16, space_after=10)
b = rect(s, 0.6, 6.15, 12.1, 0.7, fill=WHITE, line=LINE, name="Ideas reutilizadas")
box_text(b, [{"text": "Ideas reutilizadas de carla_aebs: modo síncrono de CARLA y el escenario «vehículo líder como obstáculo».",
              "size": 14, "color": SLATE}])
notes(s, "carla_aebs es un AEB por aprendizaje por refuerzo. Para un primer sistema que debe llevarse a un vehículo real, "
         "un algoritmo basado en reglas es más fácil de verificar, ajustar y justificar.")

# ============================================================================
# 8. Sección: modelos
# ============================================================================
divider("02", "Modelos y algoritmos", "Sensor, percepción, lógica de decisión, actuador y escenarios, con sus ecuaciones")

# ============================================================================
# 9. Modelo del radar
# ============================================================================
s = content_slide("Modelo del sensor: radar AUMOVIO ARS 548",
                  "El radar es el único sensor del Porsche cuyo análogo en CARLA entrega las mismas magnitudes")
radar = [
    ["Parámetro", "ARS 548 (presentación del equipo)", "Modelo en CARLA", "Estado"],
    ["Alcance", "0.2–300 m", "300 m; se descartan detecciones < 0.2 m", "DOCUMENTADO"],
    ["Azimut", "±60°", "FOV horizontal de 120°", "DOCUMENTADO"],
    ["Velocidad", "Doppler", "Velocidad radial por detección", "DOCUMENTADO"],
    ["Elevación", "Radar 4D, mide elevación", "FOV vertical de 10°", "SUPUESTO"],
    ["Frecuencia", "No documentada", "20 Hz (igual al paso de simulación)", "SUPUESTO"],
    ["Montaje", "No documentado", "Paragolpes delantero, 0.6 m de altura", "SUPUESTO"],
    ["Salida", "Lista de objetos + escaneo", "Nube de detecciones sin ruido", "DIFERENCIA"],
]
status_color = {"DOCUMENTADO": GREEN, "SUPUESTO": ORANGE, "DIFERENCIA": RED}
cc = {(i, 3): status_color[r[3]] for i, r in enumerate(radar) if i > 0}
table(s, 0.6, 1.65, 12.1, [1.8, 3.6, 4.4, 2.3], radar, size=14, row_h=0.52, first_col_bold=True, cell_colors=cc)
text(s, 0.6, 6.05, 12.1, 0.8,
     "El ARS 548 real entrega una lista de objetos ya procesada; en la simulación, el módulo de percepción cumple ese papel a partir de las detecciones crudas.",
     size=14, color=SLATE)
notes(s, "Los valores documentados vienen de la presentación «El Fantástico — 2026». Los supuestos están en config.py y deben confirmarse con la instalación real.")

# ============================================================================
# 10. Percepción
# ============================================================================
s = content_slide("Percepción: del escaneo del radar a un objetivo",
                  "Cada detección i entrega distancia d_{i}, azimut θ_{i}, elevación φ_{i} y velocidad radial v_{r,i}")
eq = rect(s, 0.6, 1.7, 6.2, 5.1, fill=CARD, name="Ecuaciones de percepción")
text(s, 0.95, 1.95, 5.6, 4.7, [
    {"text": "Coordenadas del sensor", "size": 15, "bold": True, "color": SLATE},
    {"text": "x_{i} = d_{i} · cos φ_{i} · cos θ_{i}", "size": 18},
    {"text": "y_{i} = d_{i} · cos φ_{i} · sin θ_{i}", "size": 18},
    {"text": "h_{i} = z_{m} + d_{i} · sin φ_{i}", "size": 18, "space_after": 14},
    {"text": "Filtro de carril y altura", "size": 15, "bold": True, "color": SLATE},
    {"text": "d_{i} > 0.2 m,   |y_{i}| < 1.6 m,   0.25 m < h_{i} < 2.5 m", "size": 16, "space_after": 14},
    {"text": "Objetivo y velocidad de cierre", "size": 15, "bold": True, "color": SLATE},
    {"text": "d_{obj} = min x_{i}", "size": 18},
    {"text": "v_{c} = −mediana(v_{r,i})  para  x_{i} < d_{obj} + 1 m", "size": 18, "space_after": 14},
    {"text": "Suavizado exponencial (α = 0.6)", "size": 15, "bold": True, "color": SLATE},
    {"text": "ŝ_{k} = α · s_{k} + (1 − α) · ŝ_{k−1}", "size": 18},
], size=16, space_after=4)
steps = [
    ("Polares a cartesianas", "Cada detección se proyecta al marco del sensor (x adelante, y lateral)."),
    ("Filtro de carril y altura", "Descarta suelo, puentes, barreras y carriles vecinos."),
    ("Agrupación del objetivo", "La detección más cercana fija la distancia; el Doppler del grupo da v_{c}."),
    ("Suavizado y retención", "Filtro exponencial; el objetivo se conserva 3 ciclos si se pierde."),
]
for i, (head, body) in enumerate(steps):
    y = 1.75 + i * 1.27
    circle(s, 7.25, y, 0.55, RED, str(i + 1), size=18)
    text(s, 8.0, y - 0.02, 4.7, 0.35, head, size=17, bold=True)
    text(s, 8.0, y + 0.36, 4.7, 0.8, body, size=14, color=SLATE)
notes(s, "z_m es la altura de montaje (0.6 m). La velocidad radial de CARLA es negativa cuando el objetivo se acerca, por eso v_c lleva signo menos. "
         "La mediana hace robusta la estimación frente a detecciones atípicas.")

# ============================================================================
# 11. Lógica AEB
# ============================================================================
s = content_slide("Lógica AEB: máquina de estados por TTC")
b = rect(s, 0.6, 1.4, 12.1, 0.95, fill=CARD, name="Ecuación TTC")
box_text(b, [{"text": "TTC = d_{obj} / v_{c}   si v_{c} > 0.1 m/s;   en otro caso TTC = ∞", "size": 22, "bold": True}])
states = [
    ("INACTIVO", "0 %", MUTED), ("ALERTA", "FCW · 0 %", AMBER), ("FRENADO PARCIAL", "50 %", ORANGE),
    ("FRENADO TOTAL", "100 %", RED), ("DETENIDO", "100 % (retención)", GREEN),
]
conds = ["TTC < 2.6 s", "TTC < 1.8 s", "TTC < 1.2 s", "v_{ego} < 0.3 m/s"]
sw_, sx0, sy = 2.0, 0.6, 2.95
sxs = [sx0 + i * 2.525 for i in range(5)]
for (name, dem, col), x in zip(states, sxs):
    b = rect(s, x, sy, sw_, 1.15, fill=col, name=f"Estado {name}")
    box_text(b, [{"text": name, "size": 15, "bold": True, "color": WHITE},
                 {"text": dem, "size": 13, "color": WHITE}])
for i, cnd in enumerate(conds):
    x1, x2 = sxs[i] + sw_, sxs[i + 1]
    arrow(s, x1 + 0.03, sy + 0.575, x2 - 0.03, sy + 0.575, color=SLATE, width=2)
    text(s, x1 - 0.3, sy - 0.4, x2 - x1 + 0.6, 0.3, cnd, size=13, align=PP_ALIGN.CENTER)
rules = [
    ("Enclavamiento", "Una vez que frena, sigue frenando hasta detenerse o hasta que v_{c} < 0.2 m/s."),
    ("Escalada directa", "Si el TTC ya es bajo, salta de INACTIVO al estado que corresponda."),
    ("Anulación del conductor", "Mientras el AEB interviene, el acelerador se fuerza a 0."),
    ("Operación mínima", "No actúa con v_{ego} < 1 m/s."),
]
for i, (head, body) in enumerate(rules):
    x = 0.6 + (i % 2) * 6.25
    y = 4.6 + (i // 2) * 1.1
    text(s, x, y, 5.85, 0.35, head, size=16, bold=True)
    text(s, x, y + 0.36, 5.85, 0.7, body, size=14, color=SLATE)
notes(s, "Los umbrales 2.6 / 1.8 / 1.2 s son valores iniciales habituales en AEB comerciales y protocolos Euro NCAP; están marcados como SUPUESTO. "
         "El enclavamiento evita que el freno oscile cuando el TTC sube al frenar.")

# ============================================================================
# 12. Dimensionamiento de umbrales
# ============================================================================
s = content_slide("¿Alcanzan los umbrales? Análisis de distancia de frenado",
                  "Comparación entre el TTC necesario para detenerse y el TTC al que el AEB empieza a frenar")
text(s, 0.6, 1.7, 6.0, 0.4, "Modelo cinemático (objetivo detenido)", size=20, bold=True)
b = rect(s, 0.6, 2.25, 6.0, 2.35, fill=CARD, name="Ecuaciones de frenado")
text(s, 0.9, 2.45, 5.5, 2.1, [
    {"text": "d_{req} = v · t_{eq} + v^{2} / (2 · a)", "size": 20},
    {"text": "TTC_{req} = d_{req} / v = t_{eq} + v / (2 · a)", "size": 20},
    {"text": "t_{eq} ≈ τ + T_{r}/2 = 0.10 + 0.15 = 0.25 s", "size": 18, "color": SLATE},
    {"text": "a ≈ 9 m/s² (MFDD medida en el vehículo virtual)", "size": 18, "color": SLATE},
], size=18, space_after=8)
text(s, 0.6, 4.85, 6.0, 1.9, [
    {"text": "Si TTC_{req} < 1.8 s (inicio del frenado parcial), el AEB tiene margen para detenerse.", "bullet": True},
    {"text": "Con un objetivo que frena (CCRb), el TTC a velocidad constante subestima el riesgo: es el caso límite.", "bullet": True},
], size=15, color=INK)
tt = [["v ego", "v / (2a)", "TTC_{req}", "Margen vs. 1.8 s"]]
for v in (8.0, 16.0, 22.0):
    req = 0.25 + v / (2 * 9.0)
    tt.append([f"{v * 3.6:.0f} km/h", f"{v / 18:.2f} s", f"{req:.2f} s", f"{1.8 - req:+.2f} s"])
table(s, 7.1, 2.25, 5.6, [1.4, 1.3, 1.3, 1.6], tt, size=15, row_h=0.6)
text(s, 7.1, 4.85, 5.6, 1.5, [
    {"text": "Los resultados coinciden con el análisis: a 79 km/h contra un objetivo detenido se detiene a 1.6 m, el menor margen de CCRs.", "size": 15},
], color=SLATE)
notes(s, "t_eq aproxima el retardo del actuador más la mitad de la rampa. a es la desaceleración media del vehículo virtual a demanda alta. "
         "Con los parámetros reales del Porsche (a más baja), los umbrales tendrán que subir; esta misma tabla permite recalcularlos.")

# ============================================================================
# 13. Modelo del actuador
# ============================================================================
s = content_slide("Modelo del actuador: motor a pasos + tornillo sin fin",
                  "Bloque separado del AEB; representa un actuador no ideal con dos parámetros")
b = rect(s, 0.6, 1.7, 6.0, 3.35, fill=CARD, name="Ecuaciones del actuador")
text(s, 0.9, 1.9, 5.5, 3.1, [
    {"text": "Retardo puro (τ = 0.10 s)", "size": 15, "bold": True, "color": SLATE},
    {"text": "N = τ / Δt = 2 ciclos,     u_{d}[k] = u[k − N]", "size": 18, "space_after": 12},
    {"text": "Límite de rampa (T_{r} = 0.30 s para 0 → 100 %)", "size": 15, "bold": True, "color": SLATE},
    {"text": "Δp_{max} = 100 % · Δt / T_{r} = 16.7 % por ciclo", "size": 18},
    {"text": "p[k] = p[k−1] + sat(u_{d}[k] − p[k−1], ±Δp_{max})", "size": 18, "space_after": 12},
    {"text": "Mapeo a CARLA (lineal, SUPUESTO)", "size": 15, "bold": True, "color": SLATE},
    {"text": "brake[k] = p[k] / 100", "size": 18},
], size=16, space_after=4)
text(s, 0.6, 5.3, 6.0, 1.5, [
    {"text": "En el Porsche, este bloque se reemplaza por la interfaz que convierte % → posición del motor.", "bullet": True},
    {"text": "τ y T_{r} son marcadores: deben medirse con una prueba de escalón en banco.", "bullet": True},
], size=15)
# respuesta a un escalón calculada con el propio modelo
act = BrakeActuator(CFG.ACTUATOR, CFG.FIXED_DT)
cd = XyChartData()
s_dem = cd.add_series("Demanda AEB")
for tx, ux in ((-0.1, 0), (0.0, 0), (0.0001, 100), (0.6, 100)):
    s_dem.add_data_point(tx, ux)
s_act = cd.add_series("Posición del actuador")
s_act.add_data_point(-0.1, 0)
for k in range(12):  # salida mantenida durante cada ciclo (retenedor de orden cero)
    pk = act.step(100.0)
    s_act.add_data_point(round(k * CFG.FIXED_DT, 3), pk)
    s_act.add_data_point(round((k + 1) * CFG.FIXED_DT, 3), pk)
gf = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER_LINES_NO_MARKERS, Inches(7.0), Inches(1.6), Inches(5.7), Inches(4.4), cd)
gf.name = "Respuesta al escalón"
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Respuesta a un escalón de demanda 0 → 100 %"
ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
ch.chart_title.text_frame.paragraphs[0].runs[0].font.bold = True
style_chart_axes(ch)
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False
ch.legend.font.size = Pt(12)
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 110
ch.category_axis.minimum_scale, ch.category_axis.maximum_scale = -0.1, 0.6
ch.category_axis.has_major_gridlines = False
axis_title(ch.value_axis, "Freno [%]")
axis_title(ch.category_axis, "Tiempo [s]")
for ser, col, dash in ((ch.series[0], STEEL, False), (ch.series[1], RED, False)):
    ser.format.line.color.rgb = col
    ser.format.line.width = Pt(2.5)
    ser.smooth = False
text(s, 7.0, 6.1, 5.7, 0.6, "Calculada con actuator.py a 20 Hz: 2 ciclos (0.10 s) sin movimiento y luego 16.7 % por ciclo hasta 100 %.",
     size=12, color=SLATE)
notes(s, "El retardo y la rampa son los dos efectos dominantes de un actuador electromecánico. Con mediciones reales se ajustan τ y T_r, "
         "y el mapeo lineal se sustituye por la curva medida demanda → desaceleración.")

# ============================================================================
# 14. Conductor virtual y escenarios
# ============================================================================
s = content_slide("Conductor virtual y escenarios de prueba",
                  "Escenarios inspirados en Euro NCAP AEB Car-to-Car Rear (CCR)")
text(s, 0.6, 1.65, 4.6, 0.4, "Conductor virtual", size=20, bold=True)
text(s, 0.6, 2.15, 4.6, 4.6, [
    {"text": "Control lateral PID reutilizado de PythonAPI/carla/agents (K_{P} 1.95, K_{I} 0.05, K_{D} 0.2).", "bullet": True},
    {"text": "Crucero PID longitudinal (K_{P} 1.0, K_{I} 0.05): mantiene la velocidad de ensayo.", "bullet": True},
    {"text": "Aproximación previa: acelera de forma natural hasta mantener ±0.5 m/s durante 1 s; recién ahí empieza t = 0.", "bullet": True},
    {"text": "El objetivo se mueve con velocidad impuesta para que su perfil sea exacto y repetible.", "bullet": True},
], size=15, space_after=10)
sc_rows = [
    ["Ensayo", "Objetivo", "Distancia inicial", "v ego"],
    ["CCRs", "Detenido", "máx(40 m, 5 s · v)", "29 / 58 / 79 km/h"],
    ["CCRm", "20 km/h constante", "20 m + 5 s · Δv", "29 / 58 / 79 km/h"],
    ["CCRb", "Misma velocidad; frena a 6 m/s² a los 2 s", "25 m", "29 / 58 / 79 km/h"],
]
table(s, 5.6, 1.7, 7.1, [1.0, 2.6, 1.85, 1.65], sc_rows, size=14, row_h=0.7, first_col_bold=True)
b = rect(s, 5.6, 4.6, 7.1, 2.2, fill=CARD, name="Matriz de ensayos")
text(s, 5.9, 4.78, 6.5, 1.9, [
    {"text": "Matriz completa: 3 ensayos × 3 velocidades × con/sin AEB = 18 corridas", "size": 16, "bold": True},
    {"text": "8 y 16 m/s (29 y 58 km/h) son las velocidades de las pruebas previas del equipo en CARLA; 22 m/s amplía el rango.", "size": 14, "color": SLATE},
    {"text": "Sin AEB, la lógica corre en modo sombra: calcula cuándo habría frenado, pero no actúa.", "size": 14, "color": SLATE},
], space_after=6)
notes(s, "Hallazgo de implementación: imponer la velocidad inicial con set_target_velocity deja la caja de cambios en neutro y, al engranar, "
         "aparece un freno motor irreal (~15 m/s²). Por eso el ego acelera de forma natural antes de cada ensayo.")

# ============================================================================
# 15. Sección: código
# ============================================================================
divider("03", "Código", "Estructura de módulos, fragmentos clave y cómo se ejecuta")

# ============================================================================
# 16. Estructura de módulos
# ============================================================================
s = content_slide("Estructura del código (aeb_sim/)",
                  "Nueve módulos de Python; la lógica AEB no depende de CARLA")
mods = [
    ("config.py", "Todos los parámetros, cada uno etiquetado por procedencia", RED),
    ("aeb.py", "Máquina de estados por TTC; módulo puro con autoprueba", RED),
    ("perception.py", "Detecciones del radar → objetivo en el carril", INK),
    ("actuator.py", "Retardo + rampa + mapeo % → brake", INK),
    ("scenarios.py", "Definición de CCRs, CCRm y CCRb", INK),
    ("run_scenario.py", "Bucle síncrono, sensores, registro CSV y video", STEEL),
    ("sim_utils.py", "Conexión, spawn, aproximación previa y verdad del simulador", STEEL),
    ("calibrate_brake.py", "Curva demanda → desaceleración del vehículo virtual", STEEL),
    ("analyze.py", "Gráficas por corrida y tabla resumen", STEEL),
]
for i, (fn, desc, col) in enumerate(mods):
    x = 0.6 + (i % 3) * 4.1
    y = 1.7 + (i // 3) * 1.6
    rect(s, x, y, 3.85, 1.35, fill=CARD, name=fn)
    circle(s, x + 0.2, y + 0.22, 0.32, col, "", size=8)
    text(s, x + 0.65, y + 0.2, 3.1, 0.35, fn, size=16, bold=True, font=MONO)
    text(s, x + 0.2, y + 0.65, 3.5, 0.65, desc, size=14, color=SLATE)
legend = [("Lógica y parámetros", RED), ("Modelos", INK), ("Integración con CARLA", STEEL)]
for i, (lbl, col) in enumerate(legend):
    x = 0.6 + i * 3.2
    circle(s, x, 6.55, 0.22, col, "", size=6)
    text(s, x + 0.32, 6.52, 2.8, 0.3, lbl, size=12, color=SLATE)
notes(s, "La separación permite portar aeb.py y actuator.py a un nodo ROS 2 sin cambios. Solo run_scenario.py y sim_utils.py dependen de CARLA.")

# ============================================================================
# 17. Código: lógica AEB
# ============================================================================
s = content_slide("Fragmento clave: decisión AEB (aeb.py)")
code(s, 0.6, 1.45, 8.3, 5.35, '''
def step(self, target_valid, distance, closing_speed, ego_speed):
    p = self.p
    ttc = time_to_collision(distance, closing_speed) if target_valid else math.inf

    if self.state in BRAKING_STATES:              # freno enclavado
        if ego_speed < p["standstill_speed"]:
            self.state = DETENIDO
        elif self.state != DETENIDO and (not target_valid
                or closing_speed < p["release_closing_speed"]):
            self.state = INACTIVO
        elif self.state == FRENADO_PARCIAL and ttc < p["ttc_full"]:
            self.state = FRENADO_TOTAL
    elif ego_speed < p["min_ego_speed"]: self.state = INACTIVO
    elif ttc < p["ttc_full"]:            self.state = FRENADO_TOTAL
    elif ttc < p["ttc_partial"]:         self.state = FRENADO_PARCIAL
    elif ttc < p["ttc_warning"]:         self.state = ALERTA
    else:                                self.state = INACTIVO

    demand = {FRENADO_PARCIAL: p["partial_demand_pct"],
              FRENADO_TOTAL: p["full_demand_pct"],
              DETENIDO: p["full_demand_pct"]}.get(self.state, 0.0)
    return self.state, demand, ttc
''', size=12, title="aeb.py · AEBController.step (formato condensado)")
text(s, 9.3, 1.5, 3.4, 0.4, "Por qué así", size=20, bold=True)
text(s, 9.3, 2.05, 3.4, 4.8, [
    {"text": "Entrada: objetivo, distancia, velocidad de cierre y velocidad propia. Salida: estado, demanda y TTC.", "bullet": True},
    {"text": "Sin dependencias de CARLA: la misma clase sirve para simulación, datos grabados o un nodo ROS 2.", "bullet": True},
    {"text": "Autoprueba con 7 casos sintéticos:", "bullet": True},
    {"text": "python aeb.py", "font": MONO, "size": 14, "color": RED},
], size=15, space_after=10)
notes(s, "La lógica completa cabe en una función de ~20 líneas. Todos los umbrales vienen de config.AEB, así que se ajustan sin tocar el código.")

# ============================================================================
# 18. Código: bucle de simulación
# ============================================================================
s = content_slide("Fragmento clave: bucle de simulación (run_scenario.py)")
code(s, 0.6, 1.45, 8.3, 5.35, '''
while t < C.MAX_SIM_TIME:
    frame = world.tick()                         # paso fijo de 50 ms
    t += C.FIXED_DT

    perception.update(radar_q.get(frame))        # 1. observación
    v_ego = U.forward_speed(ego)

    state, demand, ttc = aeb.step(perception.valid, perception.distance,
                                  perception.closing_speed, v_ego)
    position = actuator.step(demand if use_aeb else 0.0)
    aeb_braked |= use_aeb and state in BRAKING_STATES

    ctrl = driver.run_step(sc.ego_speed * 3.6,
                           U.lane_keep_waypoint(carla_map, ego))
    if aeb_braked:
        ctrl.throttle = 0.0                      # el AEB anula al conductor
    ctrl.brake = BrakeActuator.to_carla_brake(position)
    ego.apply_control(ctrl)                      # 4. actuación

    gap = U.bumper_gap(ego, target)              # 5. verdad, solo evaluación
''', size=12, title="run_scenario.py · por cada ciclo de 50 ms (formato condensado)")
loop = [("Observación", "Radar del mismo frame"), ("Decisión", "aeb.step()"), ("Actuador", "Retardo y rampa"),
        ("Actuación", "VehicleControl"), ("Evaluación", "Verdad y CSV")]
text(s, 9.3, 1.5, 3.4, 0.4, "Un ciclo, cinco pasos", size=20, bold=True)
for i, (head, body) in enumerate(loop):
    y = 2.1 + i * 0.92
    circle(s, 9.3, y, 0.5, RED if i < 4 else SLATE, str(i + 1), size=16)
    text(s, 9.95, y - 0.02, 2.8, 0.3, head, size=16, bold=True)
    text(s, 9.95, y + 0.3, 2.8, 0.4, body, size=13, color=SLATE)
notes(s, "El modo síncrono garantiza que el dato del radar corresponde exactamente al frame simulado. "
         "La verdad del simulador se calcula después de actuar y solo se registra.")

# ============================================================================
# 19. Ejecución
# ============================================================================
s = content_slide("Cómo se ejecuta", "Con CarlaUE4.exe abierto y el entorno .venv activado")
code(s, 0.6, 1.65, 6.6, 2.75, '''
cd aeb_sim
python aeb.py              # autoprueba de la lógica
python calibrate_brake.py  # curva demanda -> desaceleración
python run_scenario.py --escenario CCRs --vel 16
python run_scenario.py --escenario CCRs --vel 16 --sin-aeb
python run_scenario.py --todos       # 18 corridas
python analyze.py          # gráficas + tabla resumen
''', size=13, title="PowerShell")
text(s, 0.6, 4.7, 6.6, 1.3, [
    {"text": "Opciones: --actuador ideal (sin retardo ni rampa) y --sin-video.", "bullet": True},
    {"text": "La matriz completa tarda unos minutos en una RTX 4050 con video activado.", "bullet": True},
], size=14, color=SLATE)
outs = [
    ["Archivo", "Contenido"],
    ["log.csv", "Señales por ciclo: v, distancias, TTC, estado, demanda"],
    ["meta.json", "Parámetros, física del ego y resultado"],
    ["video.mp4", "Cámara de persecución con telemetría"],
    ["graficas.png", "Velocidad, distancia, TTC y freno"],
    ["resumen.md / .png", "Comparación con y sin AEB"],
    ["calibracion_freno/", "Curva demanda → MFDD"],
]
table(s, 7.6, 1.65, 5.1, [1.9, 3.2], outs, size=13, row_h=0.6, first_col_bold=True)
notes(s, "Todo se reproduce con dos comandos: run_scenario.py --todos y analyze.py. Cada corrida queda en results/<escenario>_<velocidad>_<aeb|sinaeb>/.")

# ============================================================================
# 20. Sección: resultados
# ============================================================================
divider("04", "Resultados", "18 corridas, calibración del freno virtual y el caso límite")

# ============================================================================
# 21. Resultados globales
# ============================================================================
s = content_slide("Velocidad de impacto con y sin AEB",
                  f"Con AEB se evitan {avoided} de {len(with_aeb)} colisiones; en el caso restante el impacto baja {reduction:.0f} %")
order = [(r["escenario"], r["v_ego_kmh"]) for r in with_aeb]
cd = CategoryChartData()
cd.categories = [f"{e} {v}" for e, v in order]
get = {(r["escenario"], r["v_ego_kmh"], r["aeb"]): float(r["v_impacto_rel_kmh"]) for r in SUMMARY}
cd.add_series("Sin AEB", [get[(e, v, "No")] for e, v in order])
cd.add_series("Con AEB", [get[(e, v, "Sí")] for e, v in order])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(1.6), Inches(8.6), Inches(5.2), cd)
gf.name = "Velocidad de impacto"
ch = gf.chart
style_chart_axes(ch, size=11)
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.TOP
ch.legend.include_in_layout = False
ch.legend.font.size = Pt(12)
plot = ch.plots[0]
plot.gap_width, plot.overlap = 60, -5
plot.has_data_labels = True
dl = plot.data_labels
dl.number_format, dl.number_format_is_linked = '0;-0;"0"', False
dl.position = XL_LABEL_POSITION.OUTSIDE_END
dl.font.size = Pt(11)
dl.font.color.rgb = INK
for ser, col in zip(plot.series, (RED, GREEN)):
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = col
axis_title(ch.value_axis, "Velocidad relativa de impacto [km/h]")
axis_title(ch.category_axis, "Ensayo y velocidad del ego [km/h]")
ch.value_axis.minimum_scale = 0
text(s, 9.6, 1.7, 3.1, 0.4, "Lectura", size=20, bold=True)
text(s, 9.6, 2.25, 3.1, 4.6, [
    {"text": "Sin AEB, todos los ensayos terminan en colisión, de 10 a 79 km/h.", "bullet": True},
    {"text": "Con AEB, el ego se detiene entre 1.6 y 9.9 m antes del objetivo.", "bullet": True},
    {"text": f"Único caso no evitado: {limit_case['escenario']} a {limit_case['v_ego_kmh']} km/h, con el líder frenando a 6 m/s² a solo 25 m.", "bullet": True},
    {"text": "0 = colisión evitada.", "color": SLATE, "size": 13},
], size=15, space_after=10)
notes(s, "Los valores salen de results/resumen.csv. La velocidad de impacto es la relativa entre ego y objetivo en el ciclo anterior al contacto.")

# ============================================================================
# 22. Antes / después
# ============================================================================
s = content_slide("Mismo ensayo, con y sin AEB", "CCRs a 79 km/h contra un vehículo detenido")
crop = (0.2, 0.42, 0.2, 0.0)
r_no, r_si = summary_row("CCRs", 79, "No"), summary_row("CCRs", 79, "Sí")
picture(s, os.path.join(IMG, "colision.jpg"), 0.6, 1.65, w=5.9, crop=crop, name="Sin AEB")
picture(s, os.path.join(IMG, "detenido.jpg"), 6.8, 1.65, w=5.9, crop=crop, name="Con AEB")
for x, col, head, body in ((0.6, RED, "Sin AEB", f"Impacto a {r_no['v_impacto_rel_kmh']} km/h"),
                           (6.8, GREEN, "Con AEB", f"Detenido a {float(r_si['gap_minimo_m']):.1f} m del objetivo")):
    circle(s, x, 5.12, 0.42, col, "", size=8)
    text(s, x + 0.6, 5.07, 5.2, 0.4, head, size=20, bold=True)
    text(s, x + 0.6, 5.5, 5.2, 0.4, body, size=16, color=SLATE)
text(s, 0.6, 6.25, 12.1, 0.6,
     f"Frenado parcial a TTC {float(r_si['ttc_al_frenar_s']):.2f} s, con {float(r_si['gap_al_frenar_m']):.0f} m de separación; "
     f"desaceleración media durante la intervención: {float(r_si['decel_media_mps2']):.1f} m/s².",
     size=14, color=SLATE)
notes(s, "Cuadros extraídos de los videos de results/CCRs_22mps_sinaeb y results/CCRs_22mps_aeb. Los videos completos son buen material para la exposición.")

# ============================================================================
# 23. Caso límite
# ============================================================================
s = content_slide("Caso límite: CCRb a 79 km/h", "El líder frena a 6 m/s² con 25 m de separación")
picture(s, os.path.join(RESULTS, "CCRb_22mps_aeb", "graficas.png"), 0.6, 1.55, h=5.3, name="Gráficas CCRb 79 km/h")
text(s, 6.3, 1.65, 6.4, 0.4, "Qué ocurre", size=20, bold=True)
st = state_times("CCRb_22mps_aeb")
text(s, 6.3, 2.15, 6.4, 2.4, [
    {"text": "t = 2.0 s: el líder empieza a frenar; la distancia se reduce rápido.", "bullet": True},
    {"text": f"t = {st['ALERTA']:.2f} s: alerta; t = {st['FRENADO_PARCIAL']:.2f} s: frenado parcial; "
             f"t = {st['FRENADO_TOTAL']:.2f} s: frenado total.", "bullet": True},
    {"text": f"Impacto a {limit_case['v_impacto_rel_kmh']} km/h, frente a {limit_base['v_impacto_rel_kmh']} km/h sin AEB.", "bullet": True},
], size=15, space_after=8)
text(s, 6.3, 4.55, 6.4, 0.4, "Por qué", size=20, bold=True)
text(s, 6.3, 5.05, 6.4, 1.8, [
    {"text": "El TTC supone velocidades constantes y no ve la desaceleración del líder.", "bullet": True},
    {"text": "Mejora posible: TTC con aceleración relativa (ETTC), estimando a_{rel} de la derivada del Doppler.", "bullet": True},
], size=15, space_after=8)
notes(s, "ETTC resuelve d = v_rel·t + ½·a_rel·t² para t. Es una extensión simple que mantiene la arquitectura y mejora los escenarios con objetivo que frena.")

# ============================================================================
# 24. Métricas
# ============================================================================
s = content_slide("Métricas de los ensayos con AEB")
rows = [["Ensayo", "v ego", "Resultado", "Dist. mínima", "TTC al frenar", "Dist. al frenar", "Decel. media", "Error radar"]]
cc = {}
for i, r in enumerate(with_aeb, start=1):
    ok = r["colision"] == "No"
    rows.append([r["escenario"], f"{r['v_ego_kmh']} km/h",
                 "Evitada" if ok else f"Impacto {r['v_impacto_rel_kmh']} km/h",
                 f"{float(r['gap_minimo_m']):.2f} m", f"{float(r['ttc_al_frenar_s']):.2f} s",
                 f"{float(r['gap_al_frenar_m']):.1f} m", f"{float(r['decel_media_mps2']):.1f} m/s²",
                 f"{float(r['error_radar_medio_m']):+.2f} m"])
    cc[(i, 2)] = GREEN if ok else RED
table(s, 0.6, 1.45, 12.1, [1.15, 1.25, 2.2, 1.45, 1.55, 1.6, 1.5, 1.4], rows, size=14, row_h=0.47,
      first_col_bold=True, cell_colors=cc)
text(s, 0.6, 6.3, 12.1, 0.6,
     "Error radar = media de (distancia del radar − distancia real) antes del impacto. Dist. al frenar = separación real al iniciar el frenado parcial.",
     size=12, color=SLATE)
notes(s, "El TTC al frenar es ~1.75 s en todos los casos por la discretización de 50 ms. La desaceleración media supera 9 m/s² en varios casos "
         "porque el vehículo virtual frena más fuerte de lo esperable (ver calibración).")

# ============================================================================
# 25. Calibración
# ============================================================================
s = content_slide("Calibración del freno del vehículo virtual",
                  "En CARLA, la demanda de freno no es lineal con la desaceleración")
cd = XyChartData()
ser = cd.add_series("Vehículo virtual (CARLA)")
for r in CALIB:
    ser.add_data_point(float(r["demand_pct"]), float(r["mfdd_mps2"]))
lin = cd.add_series("Supuesto lineal")
amax = float(CALIB[-1]["mfdd_mps2"])
for d in (0, 100):
    lin.add_data_point(d, amax * d / 100)
gf = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER_LINES, Inches(0.6), Inches(1.6), Inches(7.2), Inches(5.2), cd)
gf.name = "Curva demanda-desaceleración"
ch = gf.chart
style_chart_axes(ch)
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.TOP
ch.legend.include_in_layout = False
ch.legend.font.size = Pt(12)
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 12
ch.category_axis.minimum_scale, ch.category_axis.maximum_scale = 0, 100
ch.category_axis.has_major_gridlines = False
axis_title(ch.value_axis, "MFDD [m/s²]")
axis_title(ch.category_axis, "Demanda de freno [%]")
s0, s1 = ch.series
s0.format.line.color.rgb = RED
s0.format.line.width = Pt(2.5)
s0.marker.format.fill.solid()
s0.marker.format.fill.fore_color.rgb = RED
s0.marker.format.line.color.rgb = RED
s0.smooth = False
s1.format.line.color.rgb = MUTED
s1.format.line.width = Pt(1.5)
s1.format.line.dash_style = MSO_LINE.DASH
s1.smooth = False
s1.marker.style = XL_MARKER_STYLE.NONE
text(s, 8.2, 1.65, 4.5, 0.4, "Método", size=20, bold=True)
b = rect(s, 8.2, 2.15, 4.5, 1.45, fill=CARD, name="Ecuación MFDD")
text(s, 8.4, 2.3, 4.1, 1.2, [
    {"text": "MFDD = (v_{b}^{2} − v_{e}^{2}) / (2 · (s_{e} − s_{b}))", "size": 17},
    {"text": "v_{b} = 0.8 · v_{0},   v_{e} = 0.1 · v_{0},   v_{0} = 58 km/h", "size": 14, "color": SLATE},
], space_after=6)
text(s, 8.2, 3.85, 4.5, 0.4, "Hallazgos", size=20, bold=True)
c20, c100 = float(CALIB[0]["mfdd_mps2"]), float(CALIB[-1]["mfdd_mps2"])
text(s, 8.2, 4.35, 4.5, 2.5, [
    {"text": f"20 % ya produce {c20:.1f} m/s²; 100 % llega a {c100:.1f} m/s² (más de 1 g).", "bullet": True},
    {"text": "Se explica por la física por defecto: fricción de neumáticos de 3.5 y 800 N·m de freno por rueda.", "bullet": True},
    {"text": "Es la misma prueba que hay que repetir en el Porsche para calibrar el mapeo.", "bullet": True},
], size=15, space_after=8)
notes(s, "MFDD: desaceleración media totalmente desarrollada (ECE R13-H). La línea punteada muestra lo que supondría un mapeo lineal. "
         "Esta no linealidad confirma la advertencia del documento de contexto: VehicleControl.brake no equivale a un porcentaje físico.")

# ============================================================================
# 26. Sección: limitaciones
# ============================================================================
divider("05", "Limitaciones", "Qué validan y qué no validan estos resultados")

# ============================================================================
# 27. Limitaciones
# ============================================================================
s = content_slide("Limitaciones de la simulación")
lims = [
    ("Dinámica", "La física es la del Mercedes de CARLA (1630 kg, frenado de más de 1 g), no la del Porsche."),
    ("Radar ideal", "Sin ruido, sin falsos positivos ni clutter y sin la lista de objetos real del ARS 548."),
    ("Actuador supuesto", "El retardo, la rampa y el mapeo lineal no están medidos en el mecanismo real."),
    ("TTC constante", "No considera la aceleración del objetivo; limita el desempeño en CCRb."),
    ("Escenarios acotados", "Recta, un solo objetivo, clima despejado; sin curvas, peatones ni ciclistas."),
    ("Un solo sensor", "Sin fusión con cámaras, LiDAR ni V2V; el filtro de carril asume una recta."),
]
for i, (head, body) in enumerate(lims):
    x = 0.6 + (i % 3) * 4.1
    y = 1.5 + (i // 3) * 2.6
    rect(s, x, y, 3.85, 2.35, fill=CARD, name=head)
    circle(s, x + 0.25, y + 0.25, 0.5, RED if i < 3 else ORANGE, "!", size=18)
    text(s, x + 0.9, y + 0.3, 2.8, 0.4, head, size=18, bold=True)
    text(s, x + 0.25, y + 0.95, 3.4, 1.3, body, size=15, color=SLATE)
text(s, 0.6, 6.7, 12.1, 0.3, "Rojo: afecta directamente a la transferencia al vehículo real. Naranja: limita la cobertura de escenarios.",
     size=12, color=SLATE)
notes(s, "Mensaje clave: un prototipo que funciona en CARLA no es una validación del sistema físico. "
         "Cada limitación tiene una acción concreta en la ruta de implementación.")

# ============================================================================
# 28. Trazabilidad de parámetros
# ============================================================================
s = content_slide("Trazabilidad de parámetros", "Todos están en config.py con su etiqueta de procedencia")
tr = [
    ["Parámetro", "Valor en la simulación", "Procedencia", "Cómo se obtiene el valor real"],
    ["Alcance y FOV del radar", "300 m, ±60°", "DOCUMENTADO", "Ya disponible (ficha ARS 548)"],
    ["Posición y frecuencia del radar", "Paragolpes, 0.6 m, 20 Hz", "SUPUESTO", "Medir la instalación; leer la configuración"],
    ["Umbrales TTC", "2.6 / 1.8 / 1.2 s", "SUPUESTO", "Recalcular con la desaceleración real"],
    ["Demandas por etapa", "50 % / 100 %", "SUPUESTO", "Ajustar con la curva demanda → desaceleración"],
    ["Retardo del actuador τ", "0.10 s", "SUPUESTO", "Prueba de escalón en banco"],
    ["Rampa del actuador T_{r}", "0.30 s", "SUPUESTO", "Prueba de escalón en banco"],
    ["Mapeo % → freno", "Lineal", "SUPUESTO", "Frenadas a demanda fija en pista"],
    ["Dinámica del vehículo", "Física de CARLA", "SIMULACIÓN", "Masa, frenado y neumáticos del Porsche"],
]
cc = {(i, 2): {"DOCUMENTADO": GREEN, "SUPUESTO": ORANGE, "SIMULACIÓN": STEEL}[r[2]] for i, r in enumerate(tr) if i > 0}
table(s, 0.6, 1.6, 12.1, [3.3, 2.7, 2.0, 4.1], tr, size=14, row_h=0.56, first_col_bold=True, cell_colors=cc)
notes(s, "Esta tabla convierte las limitaciones en tareas de medición concretas. Cuando un SUPUESTO pase a medido, basta con actualizar config.py y repetir los ensayos.")

# ============================================================================
# 29. Sección: implementación
# ============================================================================
divider("06", "Implementación en el Porsche", "De la simulación al vehículo real, por fases y con criterios de salida")

# ============================================================================
# 30. Hoja de ruta
# ============================================================================
s = content_slide("Hoja de ruta de implementación", "Cada fase reduce un supuesto antes de pasar a la siguiente")
phases = [
    ("Caracterizar", "Freno y actuador del Porsche", "Curva demanda → desaceleración; τ y T_{r} medidos"),
    ("Integrar radar", "ARS 548 en ROS 2", "Lista de objetos con unidades, marcos y latencia"),
    ("SIL", "Datos grabados → aeb.py", "Sin falsas alarmas en conducción normal"),
    ("HIL", "Actuador en banco + CARLA", "Retardo de lazo cerrado medido"),
    ("Modo sombra", "AEB calcula, no frena", "Alertas coherentes durante horas de conducción"),
    ("Pista", "Frenado real progresivo", "CCRs/CCRm a baja velocidad con objetivo blando"),
]
pw = 1.85
for i, (head, what, exit_) in enumerate(phases):
    x = 0.6 + i * 2.05
    if i < len(phases) - 1:
        line(s, x + 0.55, 1.95, x + 2.05 + 0.2, 1.95, color=LINE, width=2)
    circle(s, x + 0.1, 1.7, 0.5, RED, str(i + 1), size=16)
    text(s, x, 2.45, pw, 0.4, head, size=18, bold=True)
    text(s, x, 2.9, pw, 0.9, what, size=14, color=INK)
    rect(s, x, 3.95, pw, 1.55, fill=CARD, name=f"Criterio fase {i + 1}")
    text(s, x + 0.12, 4.05, pw - 0.24, 0.3, "Criterio de salida", size=11, color=SLATE, bold=True)
    text(s, x + 0.12, 4.38, pw - 0.24, 1.6, exit_, size=13, color=INK)
text(s, 0.6, 5.85, 12.1, 0.5,
     "SIL: software-in-the-loop. HIL: hardware-in-the-loop. Las fases 1 y 2 pueden avanzar en paralelo.",
     size=12, color=SLATE)
notes(s, "El orden prioriza lo que más afecta la fidelidad: primero el frenado y el actuador, luego la interfaz del sensor. "
         "Las pruebas con frenado real solo llegan después del modo sombra.")

# ============================================================================
# 31. Fase 1 detallada
# ============================================================================
s = content_slide("Fase 1: caracterizar el frenado y el actuador",
                  "Repetir en el Porsche las mismas pruebas que se hicieron al vehículo virtual")
text(s, 0.6, 1.65, 5.9, 0.4, "Prueba A: respuesta del actuador (banco)", size=18, bold=True)
text(s, 0.6, 2.1, 5.9, 2.0, [
    {"text": "Escalones de demanda 0 → 25/50/100 % y retorno.", "bullet": True},
    {"text": "Medir: retardo τ, tiempo de recorrido T_{r}, posición final y repetibilidad.", "bullet": True},
    {"text": "Resultado: valores de ACTUATOR en config.py y tabla % ↔ pasos.", "bullet": True},
], size=15, space_after=6)
text(s, 0.6, 4.15, 5.9, 0.4, "Prueba B: frenadas a demanda fija (pista)", size=18, bold=True)
text(s, 0.6, 4.6, 5.9, 2.2, [
    {"text": "Desde 30 y 50 km/h, demandas de 20 a 100 %, con piloto de seguridad.", "bullet": True},
    {"text": "Registrar /v2x/kinematics/speed y /v2x/imu/accel_set (10 Hz, documentados).", "bullet": True},
    {"text": "Calcular MFDD y distancia de frenado con el mismo método de calibrate_brake.py.", "bullet": True},
], size=15, space_after=6)
b = rect(s, 6.9, 1.65, 5.8, 5.15, fill=CARD, name="Uso de los datos")
text(s, 7.2, 1.85, 5.3, 0.4, "Cómo se usan los datos", size=18, bold=True)
use = [
    ("Mapeo", "Reemplazar brake = p/100 por la curva medida a(p)."),
    ("Umbrales", "Recalcular TTC_{req} = t_{eq} + v/(2a) con la a real."),
    ("Simulación", "Ajustar la física del ego en CARLA (masa, freno, fricción) hasta reproducir la curva."),
    ("Validación", "Comparar distancias de frenado reales y simuladas con la misma demanda."),
]
for i, (head, body) in enumerate(use):
    y = 2.45 + i * 1.07
    circle(s, 7.2, y, 0.42, RED, str(i + 1), size=14)
    text(s, 7.8, y - 0.03, 4.7, 0.3, head, size=16, bold=True)
    text(s, 7.8, y + 0.3, 4.7, 0.7, body, size=14, color=SLATE)
notes(s, "Es la fase de mayor prioridad: sin la curva demanda → desaceleración y la respuesta del actuador, los umbrales del AEB no pueden justificarse para el vehículo real. "
         "La física del ego en CARLA se ajusta con get_physics_control / apply_physics_control.")

# ============================================================================
# 32. Arquitectura ROS 2 propuesta
# ============================================================================
s = content_slide("Arquitectura propuesta en el vehículo (ROS 2)",
                  "Los mismos módulos, con las entradas reales en lugar de CARLA")
nodes = [
    (0.6, 2.0, "Driver ARS 548", "Lista de objetos / detecciones", STEEL),
    (3.75, 2.0, "aeb_perception", "perception.py adaptado", INK),
    (6.9, 2.0, "aeb_logic", "aeb.py sin cambios", RED),
    (10.05, 2.0, "Interfaz actuador", "% → pasos (existente)", INK),
]
nw, nh = 2.65, 1.3
for x, y, head, sub, col in nodes:
    b = rect(s, x, y, nw, nh, fill=col, name=head)
    box_text(b, [{"text": head, "size": 16, "bold": True, "color": WHITE, "font": MONO if "_" in head else BODY},
                 {"text": sub, "size": 13, "color": WHITE}])
for i in range(3):
    x1 = nodes[i][0] + nw
    x2 = nodes[i + 1][0]
    arrow(s, x1 + 0.03, 2.65, x2 - 0.03, 2.65, width=2)
text(s, 7.9, 1.55, 3.8, 0.35, "/aeb/brake_demand_pct (propuesto)", size=12, font=MONO, color=RED,
     align=PP_ALIGN.CENTER)
b = rect(s, 6.9, 4.0, nw, 0.75, fill=CARD, name="Velocidad propia real")
box_text(b, [{"text": "/v2x/kinematics/speed", "size": 13, "font": MONO}, {"text": "documentado · 10 Hz", "size": 11, "color": SLATE}])
arrow(s, 6.9 + nw / 2, 4.0, 6.9 + nw / 2, 3.33, width=2)
b = rect(s, 10.05, 4.0, nw, 0.75, fill=CARD, name="Motor a pasos")
box_text(b, [{"text": "Motor a pasos + tornillo sin fin", "size": 13}])
arrow(s, 10.05 + nw / 2, 3.33, 10.05 + nw / 2, 4.0, width=2)
b = rect(s, 0.6, 4.0, 5.8, 0.75, fill=CARD, name="Registro")
box_text(b, [{"text": "rosbag de todos los topics → reproducible en SIL", "size": 13}])
text(s, 0.6, 5.15, 12.1, 0.4, "Cambios necesarios en el código", size=18, bold=True)
text(s, 0.6, 5.6, 12.1, 1.3, [
    {"text": "aeb.py y actuator.py se envuelven en nodos rclpy sin modificar la lógica.", "bullet": True},
    {"text": "perception.py cambia su entrada: del RadarMeasurement de CARLA al mensaje real del ARS 548 (o usa directamente su lista de objetos).", "bullet": True},
    {"text": "Los nombres /aeb/* son propuestas: deben acordarse con el equipo y con la interfaz del actuador existente.", "bullet": True, "color": SLATE},
], size=14, space_after=4)
notes(s, "La arquitectura conserva la frontera: el AEB publica una demanda en %, y la interfaz existente del actuador la convierte en pasos. "
         "La frecuencia de 10 Hz de la velocidad propia es documentada; la del radar debe confirmarse.")

# ============================================================================
# 33. Seguridad
# ============================================================================
s = content_slide("Requisitos de seguridad para las pruebas reales",
                  "Recomendaciones mínimas antes de permitir que el AEB accione el freno")
safety = [
    ("Prioridad del conductor", "El piloto de seguridad puede frenar y anular el actuador en todo momento."),
    ("Parada de emergencia", "Un E-stop físico corta la alimentación del actuador."),
    ("Watchdog", "Si la demanda deja de llegar en el plazo definido, el actuador pasa a un estado seguro."),
    ("Límites progresivos", "Demanda máxima reducida y velocidad creciente: 10 → 30 → 50 km/h."),
    ("Entorno controlado", "Pista cerrada y objetivo blando (soft target), sin tráfico real."),
    ("Registro y revisión", "rosbag completo de cada prueba y revisión antes de subir de nivel."),
]
for i, (head, body) in enumerate(safety):
    x = 0.6 + (i % 2) * 6.25
    y = 1.65 + (i // 2) * 1.7
    rect(s, x, y, 5.85, 1.45, fill=CARD, name=head)
    circle(s, x + 0.25, y + 0.3, 0.5, RED, str(i + 1), size=16)
    text(s, x + 0.95, y + 0.25, 4.7, 0.35, head, size=17, bold=True)
    text(s, x + 0.95, y + 0.65, 4.7, 0.75, body, size=14, color=SLATE)
notes(s, "Son recomendaciones generales de prueba de sistemas de frenado automatizado; los valores concretos (plazo del watchdog, límites de demanda) "
         "deben definirlos el equipo y el responsable de seguridad del vehículo.")

# ============================================================================
# 34. Datos pendientes
# ============================================================================
s = content_slide("Información que falta obtener del Porsche", "Priorizada según su impacto en la fidelidad de la simulación")
pend = [
    ["Prioridad", "Dato", "Se usa en"],
    ["Alta", "Curva demanda → desaceleración y distancia de frenado", "actuator.py, umbrales TTC"],
    ["Alta", "Retardo, velocidad y límites del actuador", "ACTUATOR en config.py"],
    ["Alta", "Posición, orientación y frecuencia de los radares", "RADAR en config.py"],
    ["Alta", "Formato y campos de la lista de objetos del ARS 548", "perception.py"],
    ["Alta", "Interfaz real para enviar la demanda de freno", "Nodo aeb_logic"],
    ["Media", "Masa actual, neumáticos y adherencia", "Física del ego en CARLA"],
    ["Media", "Latencia real de /v2x/kinematics/speed", "Modelo de retardo de la entrada"],
    ["Media", "Velocidades de prueba y criterios de aceptación", "scenarios.py"],
]
cc = {(i, 0): (RED if r[0] == "Alta" else ORANGE) for i, r in enumerate(pend) if i > 0}
table(s, 0.6, 1.6, 12.1, [1.6, 6.3, 4.2], pend, size=14, row_h=0.54, cell_colors=cc)
notes(s, "Lista derivada de los documentos de contexto del proyecto. Ninguno de estos datos se inventó en la simulación: se reemplazaron por supuestos etiquetados.")

# ============================================================================
# 35. Conclusiones
# ============================================================================
slide_no += 1
s = prs.slides.add_slide(LAYOUT_TITLE_ONLY)
s.background.fill.solid()
s.background.fill.fore_color.rgb = DARK
t = s.shapes.title
t.left, t.top, t.width, t.height = Inches(0.9), Inches(0.8), Inches(11.5), Inches(0.9)
tf = t.text_frame
tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
tf.text = ""
p = tf.paragraphs[0]
p.alignment = PP_ALIGN.LEFT
add_runs(p, "Conclusiones", 40, WHITE, bold=True)
concl = [
    ("Funciona en simulación", f"Un AEB por TTC con radar evita {avoided} de {len(with_aeb)} colisiones y reduce el impacto en el caso límite."),
    ("Listo para portar", "La lógica es pura, trazable y separada del actuador, igual que la arquitectura del Porsche."),
    ("No es una validación", "La dinámica, el actuador y los umbrales son supuestos hasta que se midan en el vehículo."),
    ("Siguiente paso", "Fase 1: medir la curva demanda → desaceleración y la respuesta del actuador del Porsche."),
]
for i, (head, body) in enumerate(concl):
    y = 2.0 + i * 1.18
    circle(s, 0.9, y, 0.55, RED if i < 3 else GREEN, str(i + 1), size=18)
    text(s, 1.7, y - 0.02, 10.5, 0.4, head, size=20, bold=True, color=WHITE)
    text(s, 1.7, y + 0.42, 10.5, 0.6, body, size=16, color=MUTED)
footer(s, dark=True)
notes(s, "Cierre: la simulación cumplió su objetivo de validar la lógica de forma sencilla y reproducible; "
         "el valor siguiente está en medir el vehículo real para reemplazar los supuestos.")

prs.save(OUT)
print(f"Presentación: {OUT} ({slide_no} diapositivas)")
