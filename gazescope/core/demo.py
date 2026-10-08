"""Genera una sesión de ejemplo: una landing page simulada y una mirada en patrón F.

Sirve para explorar el visor (heatmap, scanpath, AOIs, reporte) sin cámara.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from ..config import SESSIONS_DIR
from .fixations import detect_fixations

W, H = 1920, 1080


def _page(variant: int) -> np.ndarray:
    img = np.full((H, W, 3), (250, 248, 246), np.uint8)
    ink, soft, accent = (40, 32, 28), (150, 140, 135), (220, 120, 60)
    font = cv2.FONT_HERSHEY_DUPLEX
    # barra de navegador
    cv2.rectangle(img, (0, 0), (W, 70), (232, 230, 228), -1)
    cv2.rectangle(img, (220, 18), (1300, 52), (255, 255, 255), -1)
    cv2.putText(img, "https://ejemplo-tienda.com" + ("/producto" if variant else ""), (240, 44), font, 0.7, soft, 1,
                cv2.LINE_AA)
    # cabecera
    cv2.rectangle(img, (0, 70), (W, 150), (255, 255, 255), -1)
    cv2.circle(img, (130, 110), 22, accent, -1, cv2.LINE_AA)
    cv2.putText(img, "Nebula", (165, 122), font, 1.1, ink, 2, cv2.LINE_AA)
    for i, t in enumerate(("Productos", "Precios", "Blog", "Contacto")):
        cv2.putText(img, t, (980 + i * 170, 120), font, 0.75, soft, 1, cv2.LINE_AA)
    cv2.rectangle(img, (1660, 88), (1820, 132), accent, -1)
    cv2.putText(img, "Entrar", (1700, 118), font, 0.75, (255, 255, 255), 1, cv2.LINE_AA)
    if variant == 0:
        cv2.putText(img, "Organiza tu trabajo", (130, 330), font, 2.4, ink, 4, cv2.LINE_AA)
        cv2.putText(img, "sin esfuerzo.", (130, 430), font, 2.4, accent, 4, cv2.LINE_AA)
        for i, t in enumerate(("Planifica, colabora y entrega a tiempo con un panel",
                               "que se adapta a como trabaja tu equipo.")):
            cv2.putText(img, t, (132, 520 + i * 44), font, 0.95, soft, 1, cv2.LINE_AA)
        cv2.rectangle(img, (130, 640), (470, 720), accent, -1)
        cv2.putText(img, "Prueba gratis", (185, 692), font, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.rectangle(img, (500, 640), (780, 720), ink, 2)
        cv2.putText(img, "Ver demo", (565, 692), font, 1.0, ink, 1, cv2.LINE_AA)
        cv2.rectangle(img, (1060, 230), (1800, 760), (236, 226, 252), -1)
        cv2.rectangle(img, (1110, 290), (1750, 700), (255, 255, 255), -1)
        for i in range(5):
            cv2.rectangle(img, (1150, 330 + i * 70), (1150 + 380 - i * 50, 360 + i * 70), (220, 205, 248), -1)
        for i, t in enumerate(("Tareas", "Calendario", "Informes")):
            x = 130 + i * 580
            cv2.rectangle(img, (x, 850), (x + 520, 1030), (255, 255, 255), -1)
            cv2.putText(img, t, (x + 30, 910), font, 1.0, ink, 2, cv2.LINE_AA)
            cv2.putText(img, "Todo en un mismo lugar.", (x + 30, 960), font, 0.7, soft, 1, cv2.LINE_AA)
    else:
        cv2.rectangle(img, (130, 210), (900, 900), (240, 232, 226), -1)
        cv2.circle(img, (515, 555), 200, (200, 170, 150), -1, cv2.LINE_AA)
        cv2.putText(img, "Nebula Pro", (1000, 300), font, 2.0, ink, 3, cv2.LINE_AA)
        cv2.putText(img, "$29 / mes", (1000, 400), font, 1.6, accent, 3, cv2.LINE_AA)
        for i, t in enumerate(("Proyectos ilimitados", "Informes avanzados", "Soporte prioritario")):
            cv2.circle(img, (1015, 490 + i * 60), 8, accent, -1, cv2.LINE_AA)
            cv2.putText(img, t, (1040, 500 + i * 60), font, 0.9, soft, 1, cv2.LINE_AA)
        cv2.rectangle(img, (1000, 720), (1400, 800), accent, -1)
        cv2.putText(img, "Comprar ahora", (1070, 772), font, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def _gaze_path(points, rng, hz=30):
    t, x, y, cur = [], [], [], 0.0
    for px, py, dur in points:
        for _ in range(int(dur * hz)):
            t.append(cur)
            x.append(px + rng.normal(0, 14))
            y.append(py + rng.normal(0, 14))
            cur += 1 / hz
        cur += 0.05  # sacada
    return t, x, y


def create_demo_session(root: Path = SESSIONS_DIR) -> Path:
    rng = np.random.default_rng(7)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = root / stamp
    (path / "screens").mkdir(parents=True, exist_ok=True)
    scenes_spec = [
        ("Nebula · Organiza tu trabajo — Navegador", [
            (300, 330, 0.6), (700, 330, 0.5), (420, 430, 0.5), (350, 525, 0.35), (800, 525, 0.3),
            (300, 680, 0.9), (630, 680, 0.4), (1400, 450, 0.8), (1250, 380, 0.4), (210, 110, 0.3),
            (1740, 110, 0.5), (380, 930, 0.5), (960, 930, 0.3), (300, 330, 0.4), (300, 680, 0.7),
        ]),
        ("Nebula Pro — Navegador", [
            (515, 555, 0.9), (1200, 290, 0.6), (1150, 390, 0.9), (1150, 500, 0.4), (1150, 560, 0.3),
            (1200, 760, 1.0), (515, 555, 0.4), (1150, 390, 0.5), (1200, 760, 0.6),
        ]),
    ]
    rows, scenes, t_offset = [], [], 0.0
    for sid, (title, pts) in enumerate(scenes_spec):
        cv2.imwrite(str(path / "screens" / f"scene_{sid:03d}.jpg"), _page(sid), [cv2.IMWRITE_JPEG_QUALITY, 90])
        t, x, y = _gaze_path(pts, rng)
        t = [ti + t_offset for ti in t]
        rows += [(ti, xi, yi, 1, sid) for ti, xi, yi in zip(t, x, y)]
        scenes.append({"id": sid, "file": f"screens/scene_{sid:03d}.jpg", "t_start": t_offset,
                       "t_end": t[-1], "title": title})
        t_offset = t[-1] + 0.2

    with open(path / "gaze.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "x", "y", "valid", "scene_id"])
        for r in rows:
            w.writerow([f"{r[0]:.4f}", f"{r[1]:.1f}", f"{r[2]:.1f}", r[3], r[4]])
    arr = np.array(rows)
    fx = detect_fixations(arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3].astype(bool), arr[:, 4].astype(int), 40.0)
    with open(path / "fixations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["start", "end", "duration", "x", "y", "n", "scene_id"])
        w.writeheader()
        for fi in fx:
            w.writerow(fi.to_row())
    (path / "scenes.json").write_text(json.dumps(scenes, indent=2, ensure_ascii=False), "utf-8")
    (path / "aois.json").write_text(json.dumps({"0": [
        {"name": "Botón CTA", "x": 120, "y": 630, "w": 360, "h": 100},
        {"name": "Titular", "x": 120, "y": 250, "w": 880, "h": 210},
        {"name": "Imagen", "x": 1050, "y": 220, "w": 760, "h": 550},
    ]}, indent=2, ensure_ascii=False), "utf-8")
    meta = {
        "id": stamp, "source": "demo", "started": datetime.now().isoformat(timespec="seconds"),
        "width": W, "height": H, "px_per_deg": 40.0, "profile": "Demo", "accuracy_px": 70.0, "accuracy_deg": 1.8,
        "duration": t_offset, "samples": len(rows), "valid_ratio": 1.0, "fixations": len(fx), "scenes": len(scenes),
    }
    (path / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), "utf-8")
    from .session import Session

    Session(path).write_thumbnail()
    return path
