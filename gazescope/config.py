"""Rutas del proyecto y ajustes persistentes."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(os.environ.get("GAZESCOPE_HOME", Path(__file__).resolve().parent.parent))
DATA_DIR = ROOT / "data"
SESSIONS_DIR = ROOT / "sessions"
PROFILES_DIR = ROOT / "profiles"
SETTINGS_FILE = DATA_DIR / "settings.json"

COLORMAPS = ("turbo", "inferno", "magma", "jet", "viridis")


@dataclass
class Settings:
    # Hardware
    monitor_index: int = 0
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    viewing_distance_mm: float = 600.0

    # Calibración
    active_profile: str = ""
    calibration_points: int = 13

    # Filtro One Euro (unidades en píxeles de pantalla)
    filter_min_cutoff: float = 0.5
    filter_beta: float = 0.0015

    # Detección de fijaciones (I-VT)
    ivt_velocity_deg_s: float = 45.0
    min_fixation_ms: float = 100.0
    merge_distance_deg: float = 1.5
    merge_gap_ms: float = 75.0

    # Grabación
    screenshot_interval_s: float = 1.0
    scene_change_threshold: float = 10.0
    jpeg_quality: int = 88

    # Visualización
    colormap: str = "turbo"
    overlay_bubble: bool = True
    overlay_heatmap: bool = False
    hide_overlay_while_recording: bool = True

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
