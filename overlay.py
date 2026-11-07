"""Superposiciones del video: panel de telemetría y vista superior esquemática."""

import math
import unicodedata

import cv2
import numpy as np

import config as C
import sim_utils as U

STATE_COLORS = {  # BGR
    "INACTIVO": (170, 170, 170),
    "ALERTA": (0, 220, 255),
    "FRENADO_PARCIAL": (0, 140, 255),
    "FRENADO_TOTAL": (40, 40, 230),
    "FRENANDO": (40, 40, 230),
    "DETENIDO": (90, 200, 90),
}

VARIANT_TEXT = {  # (texto, color BGR)
    "btn": ("AEB: CONTINUO (desac. requerida / BTN)", (120, 230, 120)),
    "ttc": ("AEB: ESCALONADO (TTC 0/50/100 %)", (120, 200, 255)),
    "sinaeb": ("AEB: DESACTIVADO (sombra)", (120, 120, 255)),
}


def draw_hud(img, inset, sc, variant, row, n_actors, collided, verdict=None):
    h, w = img.shape[:2]
    overlay = img.copy()
    cv2.rectangle(overlay, (10, 10), (480, 296), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.65, img, 0.35, 0, img)

    def text(s, y, color=(255, 255, 255), scale=0.6, thick=1):
        cv2.putText(img, s, (22, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)

    def num(x, fmt):
        return "  --" if x is None or math.isnan(x) else fmt.format(x)

    label, color = VARIANT_TEXT[variant]
    text(f"AEB El Fantastico  |  {sc.name} @ {sc.ego_speed * 3.6:.0f} km/h", 38, scale=0.62, thick=2)
    text(label, 64, color, 0.55)
    text(f"t = {row['t']:5.2f} s     actores: {n_actors}", 92)
    text(f"Velocidad ego:      {row['v_ego'] * 3.6:6.1f} km/h", 118)
    text(f"Objetivo en carril: {num(row['v_target_gt'] * 3.6, '{:6.1f}')} km/h", 142)
    d_radar = "  --" if row["radar_valid"] == 0 else f"{row['radar_distance']:5.1f}"
    text(f"Distancia radar / real: {d_radar} / {num(row['gap_gt'], '{:5.1f}')} m", 166)
    if math.isnan(row["btn"]):
        text(f"TTC radar: {U.fmt_inf(row['ttc_radar'], '{:5.2f}')} s", 190)
    else:
        text(f"TTC {U.fmt_inf(row['ttc_radar'], '{:4.1f}')} s  D_req {row['d_req']:4.1f} m/s2  BTN {row['btn']:.2f}",
             190, scale=0.55)
    text(f"Estado: {row['aeb_state']}", 218, STATE_COLORS[row["aeb_state"]], 0.65, 2)
    y, val = 240, row["demand_pct"]
    text("Freno", y + 15, scale=0.55)
    cv2.rectangle(img, (120, y), (460, y + 18), (90, 90, 90), 1)
    cv2.rectangle(img, (120, y), (120 + int(3.4 * val), y + 18), (40, 40, 230), -1)
    cv2.putText(img, f"{val:3.0f}%", (410, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    text(f"Esperado: {'frenar' if sc.expect_brake else 'NO frenar'}", 284, (200, 200, 200), 0.5)

    if inset is not None:
        ih, iw = inset.shape[:2]
        x0, y0 = w - iw - 12, 12
        img[y0:y0 + ih, x0:x0 + iw] = inset
        cv2.rectangle(img, (x0 - 1, y0 - 1), (x0 + iw, y0 + ih), (255, 255, 255), 1)

    if sc.norma:
        draw_norm_banner(img, sc, verdict)

    if collided:
        cv2.putText(img, "COLISION", (w // 2 - 200, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 255), 4, cv2.LINE_AA)


def ascii_text(s):
    """OpenCV solo dibuja ASCII: quita tildes y reemplaza símbolos."""
    for a, b in (("§", "sec. "), ("≤", "<="), ("–", "-"), ("±", "+/-"), ("²", "2"), ("·", "-")):
        s = s.replace(a, b)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def draw_norm_banner(img, sc, verdict):
    """Franja inferior: fuente, ensayo, criterio y resultado."""
    h, w = img.shape[:2]
    y0 = h - (112 if verdict else 84)
    overlay = img.copy()
    cv2.rectangle(overlay, (0, y0), (w, h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)
    put = lambda s, y, color=(255, 255, 255), scale=0.55, thick=1: cv2.putText(
        img, ascii_text(s), (16, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)
    label = "ENSAYO" if sc.norma.startswith("Ensayo propio") else "ENSAYO DE NORMA"
    put(f"{label}: {sc.norma}", y0 + 24, (0, 220, 255), 0.6, 2)
    put(f"{sc.name} @ {sc.ego_speed * 3.6:.0f} km/h: {sc.description}", y0 + 50)
    put(f"Criterio: {sc.criterio}", y0 + 74, (200, 200, 200))
    if verdict:
        ok, txt = verdict
        color = (90, 220, 90) if ok else ((60, 60, 240) if ok is False else (200, 200, 200))
        put(f"RESULTADO: {txt}", y0 + 102, color, 0.7, 2)


def draw_schematic(frame, ego, scripted, radar, perception, threat_name):
    """Vista superior centrada en el ego: carriles, vehículos, corredor del radar y detecciones."""
    S = C.SCHEMATIC
    W, H = S["width"], S["height"]
    lat_min, lat_max = S["lat_min"], S["lat_max"]
    kx, ky = W / (lat_max - lat_min), H / (S["ahead"] + S["behind"])
    img = np.full((H, W, 3), (48, 48, 48), np.uint8)
    o, fwd, right = frame.origin, frame.fwd, frame.right
    ego_s = frame.s_of(ego.get_location()) + ego.bounding_box.extent.x   # distancias desde el paragolpes delantero

    def road_xy(wx, wy):
        dx, dy = wx - o.x, wy - o.y
        return dx * fwd.x + dy * fwd.y, dx * right.x + dy * right.y   # (s, lat)

    def px(s, lat):
        return (lat - lat_min) * kx, (S["ahead"] - (s - ego_s)) * ky

    # Marcas de carril
    lw = frame.lane_width
    for k in range(-1, 4):
        lat = (k - 0.5) * lw
        u = int((lat - lat_min) * kx)
        if k in (-1, 3):
            cv2.line(img, (u, 0), (u, H), (230, 230, 230), 2)
        else:
            s0 = math.floor((ego_s - S["behind"]) / 9.0) * 9.0
            for s in np.arange(s0, ego_s + S["ahead"], 9.0):
                _, v1 = px(s, lat)
                _, v2 = px(s + 3.0, lat)
                cv2.line(img, (u, int(v1)), (u, int(v2)), (230, 230, 230), 2)

    # Corredor del radar
    r_tf = radar.get_transform()
    rf, rr, rl = r_tf.get_forward_vector(), r_tf.get_right_vector(), r_tf.location
    hw = C.PERCEPTION["lane_half_width"]
    poly = []
    for x, y in ((0, -hw), (S["ahead"], -hw), (S["ahead"], hw), (0, hw)):
        s, lat = road_xy(rl.x + x * rf.x + y * rr.x, rl.y + x * rf.y + y * rr.y)
        poly.append(px(s, lat))
    layer = img.copy()
    cv2.fillPoly(layer, [np.array(poly, np.int32)], (90, 140, 60))
    cv2.addWeighted(layer, 0.35, img, 0.65, 0, img)

    # Actores
    def footprint(actor, color, label=None):
        verts = actor.bounding_box.get_world_vertices(actor.get_transform())
        pts = np.array([px(*road_xy(p.x, p.y)) for p in verts], np.float32)
        hull = cv2.convexHull(pts).astype(np.int32)
        cv2.fillPoly(img, [hull], color)
        cv2.polylines(img, [hull], True, (20, 20, 20), 1)
        if label:
            u, v = hull[:, 0, 0].max() + 4, hull[:, 0, 1].min() + 10
            cv2.putText(img, label, (int(u), int(v)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)

    kind_colors = {"vehiculo": (185, 185, 185), "peaton": (230, 140, 255), "objeto": (60, 200, 230)}
    for sa in scripted:
        is_threat = sa.spec.name == threat_name
        footprint(sa.actor, (0, 140, 255) if is_threat else kind_colors[sa.spec.kind],
                  sa.spec.name if is_threat or sa.spec.kind != "vehiculo" else None)
    footprint(ego, (40, 40, 220), "ego")

    # Detecciones del radar
    if len(perception.points_xy):
        x, y = perception.points_xy[:, 0], perception.points_xy[:, 1]
        wx, wy = rl.x + x * rf.x + y * rr.x, rl.y + x * rf.y + y * rr.y
        dx, dy = wx - o.x, wy - o.y
        s, lat = dx * fwd.x + dy * fwd.y, dx * right.x + dy * right.y
        us, vs = (lat - lat_min) * kx, (S["ahead"] - (s - ego_s)) * ky
        for u, v, inl in zip(us, vs, perception.points_in_lane):
            cv2.circle(img, (int(u), int(v)), 3 if inl else 2, (0, 230, 255) if inl else (230, 170, 100), -1)

    # Escala y título
    for d in range(0, S["ahead"] + 1, 10):
        v = int((S["ahead"] - d) * ky)
        cv2.line(img, (0, v), (6, v), (255, 255, 255), 1)
        if d:
            cv2.putText(img, f"{d}", (8, v + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.rectangle(img, (0, H - 24), (W, H), (25, 25, 25), -1)
    cv2.putText(img, "Vista superior (m)  - radar en carril", (8, H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                (255, 255, 255), 1, cv2.LINE_AA)
    cv2.circle(img, (W - 22, H - 12), 3, (0, 230, 255), -1)
    return img
