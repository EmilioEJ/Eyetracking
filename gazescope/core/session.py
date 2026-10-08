"""Carga de sesiones grabadas, métricas y áreas de interés (AOI)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from ..config import SESSIONS_DIR
from .fixations import Fixation, detect_fixations
from .heatmap import density_map, heatmap_image


@dataclass
class Scene:
    id: int
    file: str
    t_start: float
    t_end: float
    title: str = ""

    @property
    def duration(self) -> float:
        return max(self.t_end - self.t_start, 0.0)


@dataclass
class AOI:
    name: str
    x: float
    y: float
    w: float
    h: float

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


class Session:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.meta: dict = _read_json(self.path / "meta.json", {})
        self.width = int(self.meta.get("width", 1920))
        self.height = int(self.meta.get("height", 1080))
        self.px_per_deg = float(self.meta.get("px_per_deg", 40.0))
        self.scenes = [Scene(**s) for s in _read_json(self.path / "scenes.json", [])]
        gaze_file = self.path / "gaze.csv"
        self.gaze = pd.read_csv(gaze_file) if gaze_file.exists() else pd.DataFrame(
            columns=["t", "x", "y", "valid", "scene_id"])
        self.fixations = self._load_fixations()
        raw_aois = _read_json(self.path / "aois.json", {})
        self.aois: dict[int, list[AOI]] = {int(k): [AOI(**a) for a in v] for k, v in raw_aois.items()}
        self._images: dict[int, np.ndarray] = {}

    # ------------------------------------------------------------ datos
    @property
    def id(self) -> str:
        return self.path.name

    @property
    def duration(self) -> float:
        return float(self.meta.get("duration", self.gaze["t"].max() if len(self.gaze) else 0.0))

    def _load_fixations(self) -> list[Fixation]:
        f = self.path / "fixations.csv"
        if not f.exists():
            return []
        df = pd.read_csv(f)
        return [Fixation(r.start, r.end, r.x, r.y, int(r.n), int(r.scene_id)) for r in df.itertuples()]

    def recompute_fixations(self, velocity_deg_s: float, min_ms: float, merge_deg: float, gap_ms: float) -> None:
        g = self.gaze
        self.fixations = detect_fixations(
            g["t"].to_numpy(), g["x"].to_numpy(), g["y"].to_numpy(), g["valid"].astype(bool).to_numpy(),
            g["scene_id"].to_numpy(), self.px_per_deg, velocity_deg_s, min_ms, merge_deg, gap_ms,
        )

    def scene(self, scene_id: int) -> Scene | None:
        return next((s for s in self.scenes if s.id == scene_id), None)

    def image(self, scene_id: int) -> np.ndarray:
        if scene_id not in self._images:
            sc = self.scene(scene_id)
            img = cv2.imread(str(self.path / sc.file)) if sc else None
            if img is None:
                img = np.full((self.height, self.width, 3), 24, np.uint8)
            self._images[scene_id] = img
        return self._images[scene_id]

    def fixations_for(self, scene_id: int | None) -> list[Fixation]:
        if scene_id is None:
            return list(self.fixations)
        return [f for f in self.fixations if f.scene_id == scene_id]

    def gaze_for(self, scene_id: int | None) -> pd.DataFrame:
        g = self.gaze[self.gaze["valid"] == 1]
        return g if scene_id is None else g[g["scene_id"] == scene_id]

    @property
    def sigma_px(self) -> float:
        """El kernel del heatmap se ajusta al error de calibración medido."""
        err = float(self.meta.get("accuracy_px", 0.0) or 0.0)
        return float(np.clip(err * 0.6, 28.0, 90.0)) if err else 40.0

    def density(self, scene_id: int | None, use_fixations: bool = True) -> np.ndarray:
        if use_fixations and self.fixations_for(scene_id):
            fx = self.fixations_for(scene_id)
            return density_map([(f.x, f.y) for f in fx], self.width, self.height, self.sigma_px,
                               weights=[f.duration for f in fx])
        g = self.gaze_for(scene_id)
        return density_map(g[["x", "y"]].to_numpy(), self.width, self.height, self.sigma_px)

    # -------------------------------------------------------- métricas
    def metrics(self, scene_id: int | None = None) -> dict:
        fx = self.fixations_for(scene_id)
        g_all = self.gaze if scene_id is None else self.gaze[self.gaze["scene_id"] == scene_id]
        sc = self.scene(scene_id) if scene_id is not None else None
        duration = sc.duration if sc else self.duration
        durations = np.array([f.duration for f in fx]) if fx else np.zeros(0)
        amplitudes = [np.hypot(b.x - a.x, b.y - a.y) / self.px_per_deg for a, b in zip(fx, fx[1:])]
        coverage = 0.0
        if fx:
            d = self.density(scene_id)
            coverage = float(np.mean(d > 0.15))
        return {
            "duration_s": float(duration),
            "samples": int(len(g_all)),
            "valid_ratio": float(g_all["valid"].mean()) if len(g_all) else 0.0,
            "fixations": len(fx),
            "fixation_time_s": float(durations.sum()),
            "mean_fixation_ms": float(durations.mean() * 1000) if len(durations) else 0.0,
            "mean_saccade_deg": float(np.mean(amplitudes)) if amplitudes else 0.0,
            "coverage": coverage,
        }

    # ------------------------------------------------------------ AOIs
    def aoi_stats(self, scene_id: int) -> list[dict]:
        fx = self.fixations_for(scene_id)
        sc = self.scene(scene_id)
        t0 = sc.t_start if sc else 0.0
        total = sum(f.duration for f in fx) or 1.0
        out = []
        for aoi in self.aois.get(scene_id, []):
            inside = [aoi.contains(f.x, f.y) for f in fx]
            hits = [f for f, k in zip(fx, inside) if k]
            entries = sum(1 for i, k in enumerate(inside) if k and (i == 0 or not inside[i - 1]))
            dwell = sum(f.duration for f in hits)
            out.append({
                "name": aoi.name,
                "ttff_s": (hits[0].start - t0) if hits else None,
                "dwell_s": dwell,
                "fixations": len(hits),
                "revisits": max(entries - 1, 0),
                "share": dwell / total,
            })
        return out

    def save_aois(self) -> None:
        data = {str(k): [a.__dict__ for a in v] for k, v in self.aois.items() if v}
        (self.path / "aois.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")

    # --------------------------------------------------------- miniatura
    def main_scene(self) -> int | None:
        if not self.scenes:
            return None
        weight = {s.id: 0.0 for s in self.scenes}
        for f in self.fixations:
            weight[f.scene_id] = weight.get(f.scene_id, 0.0) + f.duration
        return max(weight, key=weight.get)

    def write_thumbnail(self, colormap: str = "turbo") -> Path | None:
        sid = self.main_scene()
        if sid is None:
            return None
        img = heatmap_image(self.image(sid), self.density(sid), colormap)
        h, w = img.shape[:2]
        thumb = cv2.resize(img, (480, int(480 * h / w)), interpolation=cv2.INTER_AREA)
        out = self.path / "thumb.jpg"
        cv2.imwrite(str(out), thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return out

    def delete(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def list_sessions(root: Path = SESSIONS_DIR) -> list[tuple[Path, dict]]:
    if not root.exists():
        return []
    out = []
    for p in sorted(root.iterdir(), reverse=True):
        if p.is_dir() and (p / "meta.json").exists():
            out.append((p, _read_json(p / "meta.json", {})))
    return out
