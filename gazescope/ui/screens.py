"""Utilidades de monitores: geometría y conversión píxeles ↔ grados visuales."""

from __future__ import annotations

import math

from PySide6.QtGui import QGuiApplication, QScreen


def screens() -> list[QScreen]:
    return list(QGuiApplication.screens())


def screen_at(index: int) -> QScreen:
    all_ = screens()
    return all_[index] if 0 <= index < len(all_) else QGuiApplication.primaryScreen()


def describe(screen: QScreen) -> str:
    g = screen.geometry()
    mm = screen.physicalSize()
    inches = math.hypot(mm.width(), mm.height()) / 25.4 if mm.width() > 0 else 0
    size = f' · {inches:.0f}"' if inches else ""
    return f"{screen.name()} · {g.width()}×{g.height()}{size}"


def px_per_degree(screen: QScreen, distance_mm: float) -> float:
    """Píxeles que ocupa 1° de ángulo visual a la distancia indicada."""
    mm = screen.physicalSize()
    g = screen.geometry()
    px_per_mm = g.width() / mm.width() if mm.width() > 0 else 96 / 25.4
    return float(distance_mm * math.tan(math.radians(1.0)) * px_per_mm)


def monitor_info(screen: QScreen, distance_mm: float) -> dict:
    g = screen.geometry()
    mm = screen.physicalSize()
    return {
        "name": screen.name(),
        "x": g.x(), "y": g.y(), "width": g.width(), "height": g.height(),
        "width_mm": mm.width(), "height_mm": mm.height(),
        "px_per_deg": px_per_degree(screen, distance_mm),
    }
