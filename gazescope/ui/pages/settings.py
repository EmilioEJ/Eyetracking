"""Ajustes de hardware, seguimiento, grabación y visualización."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...config import COLORMAPS, Settings
from .. import screens
from ..widgets.common import Card, label


def _dspin(lo: float, hi: float, step: float, decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setSuffix(suffix)
    return s


def _ispin(lo: int, hi: int, suffix: str = "") -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setSuffix(suffix)
    return s


class SettingsPage(QWidget):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(18)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label("Ajustes", "h1"))
        col.addWidget(label("Los cambios de cámara o monitor reinician el seguimiento.", "muted"))
        head.addLayout(col, 1)
        self.btn_reset = QPushButton("Restablecer")
        self.btn_save = QPushButton("Guardar cambios")
        self.btn_save.setObjectName("primary")
        self.btn_save.setMinimumHeight(40)
        head.addWidget(self.btn_reset)
        head.addWidget(self.btn_save)
        outer.addLayout(head)

        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(18)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        # Hardware
        self.monitor = QComboBox()
        self.camera = _ispin(0, 9)
        self.resolution = QComboBox()
        for w, h in ((640, 480), (960, 540), (1280, 720)):
            self.resolution.addItem(f"{w}×{h}", (w, h))
        self.distance = _ispin(350, 1200, " mm")
        self.source_lbl = label("", "faint", wrap=True)
        grid.addWidget(self._card("Hardware", [
            ("Monitor a rastrear", self.monitor),
            ("Cámara (índice)", self.camera),
            ("Resolución de cámara", self.resolution),
            ("Distancia ojos-pantalla", self.distance),
        ], self.source_lbl), 0, 0)

        # Seguimiento
        self.min_cutoff = _dspin(0.05, 5.0, 0.05)
        self.beta = _dspin(0.0, 0.05, 0.0005, 4)
        self.velocity = _dspin(10, 200, 5, 0, " °/s")
        self.min_fix = _ispin(40, 500, " ms")
        self.merge = _dspin(0.2, 5.0, 0.1, 1, " °")
        grid.addWidget(self._card("Seguimiento y fijaciones", [
            ("Suavizado (min cutoff)", self.min_cutoff),
            ("Reactividad (beta)", self.beta),
            ("Umbral de sacada I-VT", self.velocity),
            ("Duración mínima de fijación", self.min_fix),
            ("Fusionar fijaciones a menos de", self.merge),
        ], label("Menos «min cutoff» = burbuja más estable pero más lenta. Más «beta» = sigue mejor los "
                 "saltos rápidos.", "faint", wrap=True)), 0, 1)

        # Grabación
        self.interval = _dspin(0.3, 10.0, 0.1, 1, " s")
        self.scene_thr = _dspin(1.0, 60.0, 1.0, 1)
        self.jpeg = _ispin(50, 100)
        self.hide_rec = QCheckBox("Ocultar overlay mientras se graba")
        grid.addWidget(self._card("Grabación", [
            ("Intervalo de capturas", self.interval),
            ("Sensibilidad de cambio de escena", self.scene_thr),
            ("Calidad JPEG", self.jpeg),
            ("", self.hide_rec),
        ], label("Una escena nueva se crea al hacer scroll, cambiar de página o de ventana. Ocultar la "
                 "burbuja evita que el participante persiga su propia mirada.", "faint", wrap=True)), 1, 0)

        # Visualización
        self.cmap = QComboBox()
        for c in COLORMAPS:
            self.cmap.addItem(c.capitalize(), c)
        grid.addWidget(self._card("Visualización", [("Paleta del mapa de calor", self.cmap)]), 1, 1)
        grid.setRowStretch(2, 1)

        self.btn_save.clicked.connect(self._save)
        self.btn_reset.clicked.connect(lambda: self._load(Settings(active_profile=ctrl.settings.active_profile)))

    def _card(self, title: str, rows: list, footer=None) -> Card:
        card = Card(padding=20, spacing=12)
        card.lay.addWidget(label(title, "h2"))
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for text, w in rows:
            if text:
                form.addRow(label(text, "muted"), w)
            else:
                form.addRow(w)
        card.lay.addLayout(form)
        if footer is not None:
            card.lay.addWidget(footer)
        card.lay.addStretch()
        return card

    def showEvent(self, e) -> None:
        self._load(self.ctrl.settings)
        super().showEvent(e)

    def _load(self, s: Settings) -> None:
        self.monitor.clear()
        for i, sc in enumerate(screens.screens()):
            self.monitor.addItem(screens.describe(sc), i)
        self.monitor.setCurrentIndex(min(s.monitor_index, self.monitor.count() - 1))
        self.camera.setValue(s.camera_index)
        idx = self.resolution.findData((s.camera_width, s.camera_height))
        self.resolution.setCurrentIndex(max(idx, 0))
        self.distance.setValue(int(s.viewing_distance_mm))
        self.min_cutoff.setValue(s.filter_min_cutoff)
        self.beta.setValue(s.filter_beta)
        self.velocity.setValue(s.ivt_velocity_deg_s)
        self.min_fix.setValue(int(s.min_fixation_ms))
        self.merge.setValue(s.merge_distance_deg)
        self.interval.setValue(s.screenshot_interval_s)
        self.scene_thr.setValue(s.scene_change_threshold)
        self.jpeg.setValue(s.jpeg_quality)
        self.hide_rec.setChecked(s.hide_overlay_while_recording)
        self.cmap.setCurrentIndex(max(0, self.cmap.findData(s.colormap)))
        mode = "simulación con ratón (--source mouse)" if self.ctrl.source.is_direct else "webcam"
        self.source_lbl.setText(f"Fuente actual: {mode}.")

    def _save(self) -> None:
        w, h = self.resolution.currentData()
        new = replace(
            self.ctrl.settings,
            monitor_index=int(self.monitor.currentData() or 0),
            camera_index=self.camera.value(),
            camera_width=w,
            camera_height=h,
            viewing_distance_mm=float(self.distance.value()),
            filter_min_cutoff=self.min_cutoff.value(),
            filter_beta=self.beta.value(),
            ivt_velocity_deg_s=self.velocity.value(),
            min_fixation_ms=float(self.min_fix.value()),
            merge_distance_deg=self.merge.value(),
            screenshot_interval_s=self.interval.value(),
            scene_change_threshold=self.scene_thr.value(),
            jpeg_quality=self.jpeg.value(),
            hide_overlay_while_recording=self.hide_rec.isChecked(),
            colormap=self.cmap.currentData(),
        )
        self.ctrl.apply_settings(new)
