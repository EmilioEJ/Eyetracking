"""Detección de fijaciones con I-VT (umbral de velocidad).

Una fijación es un periodo en que la mirada se mantiene casi quieta. Agrupa las
muestras con velocidad baja, fusiona fijaciones separadas por huecos muy cortos
(parpadeos, ruido) y descarta las demasiado breves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class Fixation:
    start: float  # s
    end: float  # s
    x: float  # px
    y: float  # px
    n: int
    scene_id: int = -1

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_row(self) -> dict:
        d = asdict(self)
        d["duration"] = self.duration
        return d


def _close(groups: list[list[int]], t, x, y, scene) -> list[Fixation]:
    out = []
    for g in groups:
        idx = np.asarray(g)
        sc = scene[idx]
        values, counts = np.unique(sc, return_counts=True)
        out.append(
            Fixation(
                start=float(t[idx[0]]),
                end=float(t[idx[-1]]),
                x=float(np.mean(x[idx])),
                y=float(np.mean(y[idx])),
                n=len(idx),
                scene_id=int(values[np.argmax(counts)]),
            )
        )
    return out


def detect_fixations(
    t: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    valid: np.ndarray | None = None,
    scene: np.ndarray | None = None,
    px_per_deg: float = 40.0,
    velocity_deg_s: float = 45.0,
    min_duration_ms: float = 100.0,
    merge_distance_deg: float = 1.5,
    merge_gap_ms: float = 75.0,
) -> list[Fixation]:
    t, x, y = (np.asarray(a, dtype=float) for a in (t, x, y))
    n = len(t)
    if n == 0:
        return []
    valid = np.ones(n, bool) if valid is None else np.asarray(valid, bool)
    scene = np.full(n, -1) if scene is None else np.asarray(scene, int)

    # 1. Agrupar muestras válidas consecutivas con velocidad bajo el umbral.
    groups: list[list[int]] = []
    current: list[int] = []
    prev = None
    threshold = velocity_deg_s * px_per_deg
    for i in range(n):
        if not valid[i]:
            if current:
                groups.append(current)
            current, prev = [], None
            continue
        if prev is None:
            current = [i]
        else:
            dt = max(t[i] - t[prev], 1e-3)
            speed = np.hypot(x[i] - x[prev], y[i] - y[prev]) / dt
            same_scene = scene[i] == scene[prev]
            if speed <= threshold and same_scene:
                current.append(i)
            else:
                if current:
                    groups.append(current)
                current = [i]
        prev = i
    if current:
        groups.append(current)

    fixations = _close([g for g in groups if len(g) >= 2], t, x, y, scene)

    # 2. Fusionar fijaciones contiguas en el tiempo y el espacio.
    merged: list[Fixation] = []
    max_dist = merge_distance_deg * px_per_deg
    for f in fixations:
        if merged:
            last = merged[-1]
            gap_ok = (f.start - last.end) * 1000.0 <= merge_gap_ms
            near = np.hypot(f.x - last.x, f.y - last.y) <= max_dist
            if gap_ok and near and f.scene_id == last.scene_id:
                total = last.n + f.n
                last.x = (last.x * last.n + f.x * f.n) / total
                last.y = (last.y * last.n + f.y * f.n) / total
                last.end, last.n = f.end, total
                continue
        merged.append(f)

    # 3. Descartar fijaciones demasiado cortas.
    return [f for f in merged if f.duration * 1000.0 >= min_duration_ms]
