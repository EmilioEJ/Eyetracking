"""Overlay transparente sobre el escritorio: burbuja de mirada y mapa de calor en vivo.

La ventana ignora el ratón y el teclado (click-through), así que se puede seguir
usando cualquier aplicación por debajo, como con un Tobii.
"""

from __future__ import annotations

from collections import deque

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..core.heatmap import HeatmapAccumulator, colorize
from ..core.sources import GazePoint
from . import theme

BUBBLE_R = 34


class GazeOverlay(QWidget):
    def __init__(self, monitor: QRect, colormap: str = "turbo"):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.colormap = colormap
        self.bubble = True
        self.heatmap = False
        self.suppressed = False  # p. ej. durante la grabación o la calibración
        self._valid = False
        self._trail: deque[QPointF] = deque(maxlen=12)
        self._heat: QImage | None = None
        self._heat_dirty = False
        self._hidden_for_capture = False
        self.set_monitor(monitor)

        self._heat_timer = QTimer(self)
        self._heat_timer.setInterval(120)
        self._heat_timer.timeout.connect(self._refresh_heat)
        self._heat_timer.start()

    # ------------------------------------------------------------ estado
    def set_monitor(self, monitor: QRect) -> None:
        self.monitor = QRect(monitor)
        self.setGeometry(self.monitor)
        self.acc = HeatmapAccumulator(monitor.width(), monitor.height(), sigma_px=45, scale=6)
        self._heat = None

    def set_modes(self, bubble: bool | None = None, heatmap: bool | None = None,
                  suppressed: bool | None = None) -> None:
        if bubble is not None:
            self.bubble = bubble
        if heatmap is not None:
            self.heatmap = heatmap
        if suppressed is not None:
            self.suppressed = suppressed
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        want = (self.bubble or self.heatmap) and not self.suppressed and not self._hidden_for_capture
        if want and not self.isVisible():
            self.setGeometry(self.monitor)
            self.show()
            self.raise_()
        elif not want and self.isVisible():
            self.hide()
        self.update()

    def clear_heatmap(self) -> None:
        self.acc.clear()
        self._heat = None
        self.update()

    # Ganchos para que las capturas de pantalla no incluyan el overlay
    def hide_for_capture(self) -> bool:
        if not self.isVisible():
            return False
        self._hidden_for_capture = True
        self.hide()
        return True

    def restore_after_capture(self) -> None:
        self._hidden_for_capture = False
        self._apply_visibility()

    # ------------------------------------------------------------ datos
    def on_gaze(self, p: GazePoint) -> None:
        self._valid = p.valid
        if p.valid:
            self._trail.append(QPointF(p.x, p.y))
            self.acc.add(p.x, p.y)
            self._heat_dirty = True
        if self.isVisible() and self.bubble:
            self.update(self._trail_rect())

    def _trail_rect(self) -> QRect:
        if not self._trail:
            return self.rect()
        xs = [pt.x() for pt in self._trail]
        ys = [pt.y() for pt in self._trail]
        pad = BUBBLE_R + 40
        return QRect(int(min(xs) - pad), int(min(ys) - pad), int(max(xs) - min(xs) + 2 * pad),
                     int(max(ys) - min(ys) + 2 * pad))

    def _refresh_heat(self) -> None:
        if not (self.heatmap and self.isVisible() and self._heat_dirty):
            return
        self._heat_dirty = False
        rgba = colorize(self.acc.density(), self.colormap, max_alpha=0.55)
        rgba = cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)
        h, w = rgba.shape[:2]
        self._heat = QImage(np.ascontiguousarray(rgba).data, w, h, 4 * w,
                            QImage.Format.Format_RGBA8888).copy()
        self.update()

    # ------------------------------------------------------------ pintura
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(event.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        if self.heatmap and self._heat is not None:
            p.drawImage(QRectF(self.rect()), self._heat)

        if self.bubble and self._trail:
            accent = QColor(theme.ACCENT)
            n = len(self._trail)
            for i, pt in enumerate(list(self._trail)[:-1]):
                k = (i + 1) / n
                c = QColor(accent)
                c.setAlphaF(0.35 * k)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawEllipse(pt, 3 + 5 * k, 3 + 5 * k)

            center = self._trail[-1]
            alpha = 1.0 if self._valid else 0.35
            glow = QRadialGradient(center, BUBBLE_R * 1.6)
            g0 = QColor(accent)
            g0.setAlphaF(0.32 * alpha)
            g1 = QColor(accent)
            g1.setAlphaF(0.0)
            glow.setColorAt(0.0, g0)
            glow.setColorAt(1.0, g1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(center, BUBBLE_R * 1.6, BUBBLE_R * 1.6)

            ring = QColor(255, 255, 255)
            ring.setAlphaF(0.9 * alpha)
            p.setPen(QPen(ring, 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(center, BUBBLE_R, BUBBLE_R)
            violet = QColor(theme.ACCENT_2)
            violet.setAlphaF(0.9 * alpha)
            p.setPen(QPen(violet, 1.4))
            p.drawEllipse(center, BUBBLE_R - 5, BUBBLE_R - 5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ring)
            p.drawEllipse(center, 3.2, 3.2)
        p.end()
