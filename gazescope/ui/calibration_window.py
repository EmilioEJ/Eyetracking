"""Ventana de calibración a pantalla completa.

Flujo: posicionamiento con la cámara → 13 puntos de calibración → 5 puntos de
validación → resultados (guardar, repetir o cancelar). En modo "drift" muestra un
único punto central y solo corrige el desplazamiento del perfil activo.
"""

from __future__ import annotations

import math
import random

import numpy as np
from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ..core.calibration import (
    VALIDATION_TARGETS,
    GazeModel,
    Profile,
    ValidationResult,
    calibration_targets,
    evaluate,
    reject_outliers,
)
from ..core.sources import FeatureSample, TrackingQuality
from . import theme

TRAVEL_MS = 550
COLLECT_FROM_MS = 1150
COLLECT_TO_MS = 2150
MIN_SAMPLES = 8
MAX_RETRIES = 2


def _ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


class CalibrationWindow(QWidget):
    finished = Signal(object)  # Profile | None

    def __init__(self, source, screen, profile_name: str, n_points: int, px_per_deg: float,
                 monitor: dict, mode: str = "full", base_profile: Profile | None = None):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.BlankCursor if not source.is_direct else Qt.CursorShape.CrossCursor)
        self.source = source
        self.screen_ = screen
        self.profile_name = profile_name
        self.px_per_deg = px_per_deg
        self.monitor = monitor
        self.mode = mode
        self.base_profile = base_profile
        self.n_points = n_points

        self.phase = "position" if mode == "full" else "intro"
        self.preview: QImage | None = None
        self.quality = TrackingQuality()
        self.clock = QElapsedTimer()
        self.clock.start()
        self.phase_t0 = 0

        self.targets: list[tuple[float, float]] = []
        self.idx = 0
        self.retries = 0
        self.prev_pos = (0.5, 0.5)
        self.current: list[np.ndarray] = []
        self.cal_X: list[np.ndarray] = []
        self.cal_Y: list[tuple[float, float]] = []
        self.cal_G: list[int] = []
        self.val_samples: list[np.ndarray] = []
        self.val_targets: list[tuple[float, float]] = []
        self.model: GazeModel | None = None
        self.result: ValidationResult | None = None
        self._emitted = False

        self._build_buttons()
        source.sample.connect(self._on_sample)
        source.preview.connect(self._on_preview)
        source.set_preview(True)

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        if self.phase == "intro":
            self._start_intro()

    # ------------------------------------------------------------ ventana
    def open(self) -> None:
        self.winId()
        self.windowHandle().setScreen(self.screen_)
        self.setGeometry(self.screen_.geometry())
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def _build_buttons(self) -> None:
        self.bar = QWidget(self)
        lay = QHBoxLayout(self.bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.btn_cancel = QPushButton("Cancelar  ·  Esc")
        self.btn_retry = QPushButton("Repetir  ·  R")
        self.btn_main = QPushButton("Comenzar  ·  Espacio")
        self.btn_main.setObjectName("primary")
        for b in (self.btn_cancel, self.btn_retry, self.btn_main):
            b.setMinimumHeight(44)
            b.setMinimumWidth(170)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_retry.clicked.connect(self._restart)
        self.btn_main.clicked.connect(self._primary)
        self._update_buttons()

    def _update_buttons(self) -> None:
        visible = self.phase in ("position", "results")
        self.bar.setVisible(visible)
        if self.phase == "position":
            self.btn_retry.hide()
            self.btn_main.setText("Comenzar  ·  Espacio")
        elif self.phase == "results":
            self.btn_retry.show()
            ok = self.result is not None and math.isfinite(self.result.mean_error_px)
            self.btn_main.setEnabled(ok)
            self.btn_main.setText("Guardar y usar  ·  Enter")
        if visible:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif not self.source.is_direct:
            self.setCursor(Qt.CursorShape.BlankCursor)
        self.bar.adjustSize()
        self._place_bar()

    def _place_bar(self) -> None:
        self.bar.adjustSize()
        x = (self.width() - self.bar.width()) // 2
        y = self.height() - self.bar.height() - int(self.height() * 0.08)
        self.bar.move(x, y)

    def resizeEvent(self, e) -> None:
        self._place_bar()
        super().resizeEvent(e)

    # ------------------------------------------------------------ teclas
    def keyPressEvent(self, e) -> None:
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self._cancel()
        elif k == Qt.Key.Key_Space and self.phase == "position":
            self._start_intro()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.phase == "results":
            self._primary()
        elif k == Qt.Key.Key_R and self.phase == "results":
            self._restart()

    def _primary(self) -> None:
        if self.phase == "position":
            self._start_intro()
        elif self.phase == "results" and self.btn_main.isEnabled():
            self._save()

    def _cancel(self) -> None:
        self._finish(None)

    def _restart(self) -> None:
        self.cal_X, self.cal_Y, self.cal_G = [], [], []
        self.val_samples, self.val_targets = [], []
        self.model, self.result = None, None
        if self.mode == "full":
            self.source.set_preview(True)
            self._set_phase("position")
        else:
            self._start_intro()

    # ------------------------------------------------------------ fases
    def _set_phase(self, phase: str) -> None:
        self.phase = phase
        self.phase_t0 = self.clock.elapsed()
        self._update_buttons()

    def _start_intro(self) -> None:
        self.source.set_preview(False)
        self._set_phase("intro")

    def _begin_points(self, phase: str, targets: list[tuple[float, float]]) -> None:
        self.targets = targets
        self.idx = 0
        self.retries = 0
        self.current = []
        self._set_phase(phase)

    def _elapsed(self) -> int:
        return self.clock.elapsed() - self.phase_t0

    def _tick(self) -> None:
        if self.phase == "intro" and self._elapsed() > 1800:
            self.prev_pos = (0.5, 0.5)
            if self.mode == "drift":
                self._begin_points("drift", [(0.5, 0.5)])
            else:
                pts = calibration_targets(self.n_points)
                center, rest = pts[4], pts[:4] + pts[5:]
                random.shuffle(rest)
                self._begin_points("calibrate", [center] + rest)
        elif self.phase in ("calibrate", "validate", "drift") and self._elapsed() >= COLLECT_TO_MS:
            self._point_done()
        self.update()

    def _point_done(self) -> None:
        samples = np.array(self.current) if self.current else np.zeros((0, 9))
        if len(samples):
            samples = samples[reject_outliers(samples)]
        target = self.targets[self.idx]
        if len(samples) < MIN_SAMPLES and self.retries < MAX_RETRIES:
            self.retries += 1
            self.current = []
            self.phase_t0 = self.clock.elapsed() - TRAVEL_MS  # repetir sin viajar
            return
        if self.phase == "calibrate" and len(samples):
            for s in samples:
                self.cal_X.append(s)
                self.cal_Y.append(target)
                self.cal_G.append(self.idx)
        elif self.phase in ("validate", "drift"):
            self.val_samples.append(samples)
            self.val_targets.append(target)

        self.prev_pos = target
        self.idx += 1
        self.retries = 0
        self.current = []
        if self.idx < len(self.targets):
            self.phase_t0 = self.clock.elapsed()
            return
        if self.phase == "calibrate":
            self._fit()
        elif self.phase == "validate":
            self._evaluate()
        else:
            self._apply_drift()

    def _fit(self) -> None:
        if len(set(self.cal_G)) < 6:
            self.result = None
            self._set_phase("results")
            return
        self.model = GazeModel.fit(np.array(self.cal_X), np.array(self.cal_Y), np.array(self.cal_G))
        targets = list(VALIDATION_TARGETS)
        first, rest = targets[0], targets[1:]
        random.shuffle(rest)
        self._begin_points("validate", [first] + rest)

    def _evaluate(self) -> None:
        assert self.model is not None
        self.result = evaluate(self.model, self.val_samples, self.val_targets,
                               self.width(), self.height(), self.px_per_deg)
        self._set_phase("results")

    def _apply_drift(self) -> None:
        if self.base_profile is None or not len(self.val_samples[0]):
            self._finish(None)
            return
        model = self.base_profile.model
        pred = model.predict(self.val_samples[0]).mean(axis=0)
        model.offset = model.offset + (np.array(self.val_targets[0]) - pred)
        self._finish(self.base_profile)

    def _save(self) -> None:
        assert self.model is not None and self.result is not None
        profile = Profile.new(self.profile_name, self.model, self.result, self.monitor)
        profile.save()
        self._finish(profile)

    def _finish(self, profile: Profile | None) -> None:
        if self._emitted:
            return
        self._emitted = True
        self.timer.stop()
        try:
            self.source.sample.disconnect(self._on_sample)
            self.source.preview.disconnect(self._on_preview)
        except (RuntimeError, TypeError):
            pass
        self.source.set_preview(False)
        self.finished.emit(profile)
        self.close()

    # ------------------------------------------------------------ datos
    def _on_sample(self, s: FeatureSample) -> None:
        self.quality = s.quality
        if self.phase not in ("calibrate", "validate", "drift"):
            return
        if COLLECT_FROM_MS <= self._elapsed() < COLLECT_TO_MS and s.valid and s.vector is not None:
            self.current.append(np.array(s.vector, dtype=float))

    def _on_preview(self, img: QImage) -> None:
        self.preview = img

    # ------------------------------------------------------------ pintura
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        bg = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.7)
        bg.setColorAt(0, QColor("#121722"))
        bg.setColorAt(1, QColor(theme.BG))
        p.fillRect(self.rect(), bg)

        if self.phase == "position":
            self._paint_position(p)
        elif self.phase == "intro":
            self._paint_intro(p)
        elif self.phase in ("calibrate", "validate", "drift"):
            self._paint_points(p)
        elif self.phase == "results":
            self._paint_results(p)
        p.end()

    def _text(self, p: QPainter, rect: QRectF, text: str, size: float, color: str = theme.FG,
              weight: QFont.Weight = QFont.Weight.Normal, flags=Qt.AlignmentFlag.AlignCenter) -> None:
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(int(size))
        f.setWeight(weight)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(rect, int(flags) | int(Qt.TextFlag.TextWordWrap), text)

    def _paint_position(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        self._text(p, QRectF(0, h * 0.07, w, 50), "Prepárate para calibrar", 34, weight=QFont.Weight.Bold)
        self._text(p, QRectF(w * 0.2, h * 0.07 + 52, w * 0.6, 50),
                   "Coloca tu cara dentro del óvalo, a un brazo de distancia de la pantalla. "
                   "Durante la calibración sigue el punto solo con la mirada.", 16, theme.MUTED)

        cam_w = min(w * 0.42, 720)
        cam_h = cam_w * 3 / 4
        cam = QRectF((w - cam_w) / 2 - 140, h * 0.25, cam_w, cam_h)
        path = QPainterPath()
        path.addRoundedRect(cam, 22, 22)
        p.save()
        p.setClipPath(path)
        p.fillRect(cam, QColor(theme.SURFACE))
        if self.preview is not None:
            p.drawImage(cam, self.preview)
        elif self.source.is_direct:
            self._text(p, cam, "Modo ratón\n(sin cámara)", 20, theme.MUTED)
        else:
            self._text(p, cam, "Iniciando cámara…", 18, theme.MUTED)
        p.restore()
        p.setPen(QPen(QColor(theme.LINE), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(cam, 22, 22)

        ok = self.quality.score >= 0.99
        guide = QColor(theme.OK if ok else theme.ACCENT)
        guide.setAlphaF(0.85)
        p.setPen(QPen(guide, 3, Qt.PenStyle.DashLine))
        p.drawEllipse(cam.center(), cam_w * 0.2, cam_h * 0.36)

        q = self.quality
        dist_txt = {"ok": "Distancia correcta", "near": "Aléjate un poco", "far": "Acércate un poco",
                    "none": "Distancia"}[q.distance]
        checks = [
            (q.face, "Cara detectada"),
            (q.distance == "ok", dist_txt),
            (q.centered, "Cara centrada"),
            (q.face and q.light_ok, "Iluminación adecuada" if q.face and q.light_ok or not q.face
             else ("Poca luz" if q.brightness < 50 else "Demasiada luz")),
        ]
        x0 = cam.right() + 40
        y = cam.top() + 10
        for good, label in checks:
            chip = QRectF(x0, y, 280, 52)
            p.setPen(QPen(QColor(theme.LINE), 1))
            p.setBrush(QColor(theme.SURFACE))
            p.drawRoundedRect(chip, 14, 14)
            dot = QColor(theme.OK if good else theme.WARN)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dot)
            p.drawEllipse(QPointF(chip.left() + 24, chip.center().y()), 6, 6)
            self._text(p, chip.adjusted(44, 0, -10, 0), label, 15, theme.FG,
                       flags=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            y += 64
        self._text(p, QRectF(x0, y + 4, 280, 60),
                   f"{q.fps:.0f} fps" if q.fps else "", 13, theme.FAINT,
                   flags=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def _paint_intro(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        t = self._elapsed() / 1800.0
        title = "Mira el punto central" if self.mode == "drift" else "Sigue el punto con la mirada"
        sub = "Corrección de deriva" if self.mode == "drift" else \
            f"{self.n_points} puntos de calibración + 5 de validación · mantén la cabeza quieta"
        self._text(p, QRectF(0, h / 2 - 120, w, 50), title, 34, weight=QFont.Weight.Bold)
        self._text(p, QRectF(0, h / 2 - 66, w, 30), sub, 16, theme.MUTED)
        self._paint_target(p, QPointF(w / 2, h / 2), 1.0 - 0.3 * _ease(t), 0.0)

    def _target_pos(self) -> QPointF:
        w, h = self.width(), self.height()
        tx, ty = self.targets[self.idx]
        k = _ease(self._elapsed() / TRAVEL_MS)
        px, py = self.prev_pos
        return QPointF((px + (tx - px) * k) * w, (py + (ty - py) * k) * h)

    def _paint_target(self, p: QPainter, c: QPointF, scale: float, progress: float) -> None:
        r = 26 * scale
        glow = QRadialGradient(c, r * 2.4)
        g = QColor(theme.ACCENT)
        g.setAlphaF(0.28)
        glow.setColorAt(0, g)
        g2 = QColor(theme.ACCENT)
        g2.setAlphaF(0.0)
        glow.setColorAt(1, g2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, r * 2.4, r * 2.4)
        p.setBrush(QColor(theme.ACCENT))
        p.drawEllipse(c, r, r)
        p.setBrush(QColor(theme.BG))
        p.drawEllipse(c, max(r * 0.22, 2.5), max(r * 0.22, 2.5))
        if progress > 0:
            p.setPen(QPen(QColor(theme.FG), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rr = 40
            p.drawArc(QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr), 90 * 16, int(-progress * 360 * 16))

    def _paint_points(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        el = self._elapsed()
        shrink = _ease((el - TRAVEL_MS) / (COLLECT_TO_MS - TRAVEL_MS))
        scale = 1.0 - 0.62 * shrink
        progress = max(0.0, min(1.0, (el - COLLECT_FROM_MS) / (COLLECT_TO_MS - COLLECT_FROM_MS)))
        self._paint_target(p, self._target_pos(), scale, progress)

        label = {"calibrate": "Calibración", "validate": "Validación", "drift": "Deriva"}[self.phase]
        total = len(self.targets)
        self._text(p, QRectF(0, 26, w, 24), f"{label}  ·  {self.idx + 1} / {total}", 14, theme.FAINT)
        # barra de progreso global
        bar_w = 260
        bar = QRectF((w - bar_w) / 2, 58, bar_w, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.SURFACE_3))
        p.drawRoundedRect(bar, 2, 2)
        frac = (self.idx + min(el / COLLECT_TO_MS, 1.0)) / max(total, 1)
        p.setBrush(QColor(theme.ACCENT if self.phase != "validate" else theme.ACCENT_2))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar_w * frac, 4), 2, 2)
        if not self.quality.face and not self.source.is_direct:
            self._text(p, QRectF(0, h - 70, w, 30), "No se detecta tu cara: vuelve a mirar a la cámara",
                       15, theme.WARN)

    def _paint_results(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        r = self.result
        if r is None or not math.isfinite(r.mean_error_px):
            self._text(p, QRectF(0, h * 0.35, w, 50), "No se pudo calibrar", 34, weight=QFont.Weight.Bold)
            self._text(p, QRectF(w * 0.2, h * 0.35 + 56, w * 0.6, 60),
                       "Hubo muy pocas muestras válidas. Revisa la iluminación y que tu cara esté visible.",
                       16, theme.MUTED)
            return
        colors = {"Excelente": theme.OK, "Buena": theme.ACCENT, "Regular": theme.WARN, "Repetir": theme.DANGER}
        col = colors[r.grade]

        # vectores de error
        for (tx, ty), (px, py) in zip(r.targets_px, r.predicted_px):
            t = QPointF(tx, ty)
            p.setPen(QPen(QColor(theme.LINE), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(t, 22, 22)
            p.drawLine(QPointF(tx - 8, ty), QPointF(tx + 8, ty))
            p.drawLine(QPointF(tx, ty - 8), QPointF(tx, ty + 8))
            if math.isfinite(px):
                c = QPointF(px, py)
                pen = QPen(QColor(col), 2)
                p.setPen(pen)
                p.drawLine(t, c)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(col))
                p.drawEllipse(c, 6, 6)

        card = QRectF((w - 520) / 2, h / 2 + 60, 520, 230)  # bajo el punto central
        p.setPen(QPen(QColor(theme.LINE), 1))
        p.setBrush(QColor(theme.SURFACE))
        p.drawRoundedRect(card, 20, 20)
        self._text(p, QRectF(card.left(), card.top() + 24, card.width(), 24), "PRECISIÓN", 12, theme.MUTED,
                   QFont.Weight.DemiBold)
        self._text(p, QRectF(card.left(), card.top() + 50, card.width(), 70),
                   f"{r.mean_error_deg:.1f}°", 58, col, QFont.Weight.Bold)
        self._text(p, QRectF(card.left(), card.top() + 124, card.width(), 30),
                   f"{r.grade}  ·  error medio {r.mean_error_px:.0f} px  ·  estabilidad {r.precision_px:.0f} px",
                   15, theme.FG)
        self._text(p, QRectF(card.left() + 30, card.top() + 160, card.width() - 60, 50),
                   "Las líneas muestran la diferencia entre cada punto y dónde se estimó tu mirada.",
                   13, theme.FAINT)
