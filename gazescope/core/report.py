"""Exportación: imágenes compuestas, datos y un reporte HTML autocontenido."""

from __future__ import annotations

import base64
import html
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .. import APP_NAME, __version__
from .heatmap import heatmap_image, scanpath_image
from .session import Session


def _b64_jpeg(img: np.ndarray, width: int = 1280) -> str:
    h, w = img.shape[:2]
    if w > width:
        img = cv2.resize(img, (width, int(width * h / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 84])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode() if ok else ""


def _fmt_s(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f} s"


def export_png(session: Session, scene_id: int, out: Path, mode: str = "heatmap", colormap: str = "turbo") -> Path:
    img = session.image(scene_id)
    if mode == "scanpath":
        result = scanpath_image(img, session.fixations_for(scene_id))
    else:
        result = heatmap_image(img, session.density(scene_id), colormap)
    cv2.imwrite(str(out), result)
    return out


CSS = """
:root{--bg:#0b0d12;--card:#141821;--line:#232a36;--fg:#e8ecf3;--muted:#8a94a6;--accent:#22d3ee;--accent2:#a78bfa}
@media (prefers-color-scheme: light){:root{--bg:#f5f7fb;--card:#fff;--line:#e3e7ef;--fg:#141821;--muted:#5d6678}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 Inter,system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:40px 16px 80px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:28px}
h1{font-size:28px;margin:0;letter-spacing:-.02em}h1 span{background:linear-gradient(90deg,var(--accent),var(--accent2));
-webkit-background-clip:text;background-clip:text;color:transparent}
h2{font-size:18px;margin:0 0 4px}.muted{color:var(--muted)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:0 0 32px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.kpi small{color:var(--muted)}
.scene{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px;margin-bottom:24px}
.imgs{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}
.imgs figure{margin:0}.imgs img{width:100%;border-radius:10px;display:block;border:1px solid var(--line)}
figcaption{font-size:12px;color:var(--muted);margin-top:6px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:500}
@media (max-width:720px){.imgs{grid-template-columns:1fr}}
footer{color:var(--muted);font-size:12px;margin-top:40px}
"""


def export_html(session: Session, out: Path, colormap: str = "turbo") -> Path:
    m = session.metrics()
    meta = session.meta
    kpis = [
        ("Duración", f"{m['duration_s']:.0f} s"),
        ("Fijaciones", f"{m['fixations']}"),
        ("Fijación media", f"{m['mean_fixation_ms']:.0f} ms"),
        ("Datos válidos", f"{m['valid_ratio'] * 100:.0f} %"),
        ("Escenas", f"{len(session.scenes)}"),
        ("Precisión calib.", f"{meta.get('accuracy_deg', 0):.1f}°" if meta.get("accuracy_deg") else "—"),
    ]
    parts = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Reporte {html.escape(session.id)}</title><style>{CSS}</style></head><body><main>",
        "<header><div><h1><span>GazeScope</span> · reporte de atención</h1>",
        f"<div class='muted'>Sesión {html.escape(session.id)} · fuente {html.escape(str(meta.get('source', '')))}"
        f" · monitor {session.width}×{session.height}</div></div></header>",
        "<section class='kpis'>",
        *[f"<div class='kpi'><small>{k}</small><b>{v}</b></div>" for k, v in kpis],
        "</section>",
    ]
    for sc in session.scenes:
        fx = session.fixations_for(sc.id)
        if not fx:
            continue
        sm = session.metrics(sc.id)
        img = session.image(sc.id)
        heat = _b64_jpeg(heatmap_image(img, session.density(sc.id), colormap))
        path = _b64_jpeg(scanpath_image(img, fx))
        title = html.escape(sc.title or f"Escena {sc.id + 1}")
        parts += [
            f"<section class='scene'><h2>{title}</h2>",
            f"<div class='muted'>{sc.t_start:.1f}–{sc.t_end:.1f} s · {sm['fixations']} fijaciones · "
            f"{sm['fixation_time_s']:.1f} s de atención · cobertura {sm['coverage'] * 100:.0f} %</div>",
            "<div class='imgs'>",
            f"<figure><img src='{heat}' alt='Mapa de calor de {title}'><figcaption>Mapa de calor</figcaption></figure>",
            f"<figure><img src='{path}' alt='Scanpath de {title}'><figcaption>Recorrido visual (scanpath)</figcaption></figure>",
            "</div>",
        ]
        stats = session.aoi_stats(sc.id)
        if stats:
            parts.append("<table><tr><th>AOI</th><th>1ª fijación</th><th>Permanencia</th>"
                         "<th>Fijaciones</th><th>Revisitas</th><th>% atención</th></tr>")
            for s in stats:
                parts.append(
                    f"<tr><td>{html.escape(s['name'])}</td><td>{_fmt_s(s['ttff_s'])}</td>"
                    f"<td>{_fmt_s(s['dwell_s'])}</td><td>{s['fixations']}</td><td>{s['revisits']}</td>"
                    f"<td>{s['share'] * 100:.0f} %</td></tr>"
                )
            parts.append("</table>")
        parts.append("</section>")
    parts.append(
        f"<footer>Generado por {APP_NAME} {__version__} · {datetime.now():%Y-%m-%d %H:%M}. "
        "La precisión del seguimiento con webcam es aproximada (≈2–4°).</footer></main></body></html>"
    )
    out.write_text("".join(parts), encoding="utf-8")
    return out
