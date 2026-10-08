"""Inicio: vista de cámara, calidad del seguimiento, perfil activo y grabación."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ...core.sources import FeatureSample
from .. import theme
from ..widgets.common import Card, Chip, Gauge, ImageView, StatCard, label


class HomePage(QWidget):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(18)

        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(label("Inicio", "h1"))
        head.addWidget(label("Seguimiento ocular en tiempo real sobre todo tu escritorio.", "muted"))
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(18)
        root.addLayout(body, 1)

        # ---------------------------------------------------- cámara
        cam_card = Card()
        top = QHBoxLayout()
        top.addWidget(label("Cámara", "h2"))
        top.addStretch()
        self.fps = label("", "faint")
        top.addWidget(self.fps)
        cam_card.lay.addLayout(top)
        self.camera = ImageView("Cámara inactiva")
        cam_card.lay.addWidget(self.camera, 1)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chip_face = Chip("Cara")
        self.chip_dist = Chip("Distancia")
        self.chip_center = Chip("Centrado")
        self.chip_light = Chip("Iluminación")
        for c in (self.chip_face, self.chip_dist, self.chip_center, self.chip_light):
            chips.addWidget(c)
        chips.addStretch()
        cam_card.lay.addLayout(chips)
        body.addWidget(cam_card, 3)

        # ---------------------------------------------------- columna derecha
        side = QVBoxLayout()
        side.setSpacing(18)
        body.addLayout(side, 2)

        # Calidad + perfil
        quality = Card()
        row = QHBoxLayout()
        row.setSpacing(16)
        self.gauge = Gauge()
        row.addWidget(self.gauge)
        qtext = QVBoxLayout()
        qtext.setSpacing(2)
        qtext.addWidget(label("CALIDAD DE SEGUIMIENTO", "kpiLabel"))
        self.quality_title = label("Esperando cámara…", "h2")
        self.quality_hint = label("", "muted", wrap=True)
        qtext.addWidget(self.quality_title)
        qtext.addWidget(self.quality_hint)
        qtext.addStretch()
        row.addLayout(qtext, 1)
        quality.lay.addLayout(row)
        side.addWidget(quality)

        profile = Card()
        profile.lay.addWidget(label("PERFIL DE CALIBRACIÓN", "kpiLabel"))
        self.profile_name = label("Sin calibrar", "h2")
        self.profile_info = label("Calibra para que el sistema aprenda cómo se mueven tus ojos.", "muted",
                                  wrap=True)
        profile.lay.addWidget(self.profile_name)
        profile.lay.addWidget(self.profile_info)
        prow = QHBoxLayout()
        self.btn_cal = QPushButton(theme.icon("target"), "Calibrar")
        self.btn_drift = QPushButton(theme.icon("drift"), "Corregir deriva")
        self.btn_drift.setToolTip("Mira un punto central 1 s para reajustar sin recalibrar (Ctrl+Alt+D)")
        for b in (self.btn_cal, self.btn_drift):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            prow.addWidget(b)
        profile.lay.addLayout(prow)
        side.addWidget(profile)

        # Grabación
        rec = Card()
        rec.lay.addWidget(label("GRABACIÓN", "kpiLabel"))
        self.btn_record = QPushButton(theme.icon("record", "#06121a"), "  Iniciar grabación")
        self.btn_record.setObjectName("primary")
        self.btn_record.setMinimumHeight(48)
        self.btn_record.setCursor(Qt.CursorShape.PointingHandCursor)
        rec.lay.addWidget(self.btn_record)
        stats = QGridLayout()
        stats.setSpacing(10)
        self.st_time = StatCard("Tiempo", "00:00")
        self.st_samples = StatCard("Muestras", "0")
        self.st_scenes = StatCard("Escenas", "0")
        stats.addWidget(self.st_time, 0, 0)
        stats.addWidget(self.st_samples, 0, 1)
        stats.addWidget(self.st_scenes, 0, 2)
        rec.lay.addLayout(stats)
        toggles = QHBoxLayout()
        self.cb_bubble = QCheckBox("Burbuja de mirada")
        self.cb_heat = QCheckBox("Mapa de calor en vivo")
        toggles.addWidget(self.cb_bubble)
        toggles.addWidget(self.cb_heat)
        toggles.addStretch()
        rec.lay.addLayout(toggles)
        rec.lay.addWidget(label("Ctrl+Alt+R grabar · Ctrl+Alt+B burbuja · Ctrl+Alt+H calor · Ctrl+Alt+D deriva",
                                "faint", wrap=True))
        side.addWidget(rec)
        side.addStretch()

        # ---------------------------------------------------- señales
        self.btn_cal.clicked.connect(lambda: ctrl.calibrate())
        self.btn_drift.clicked.connect(ctrl.drift_correct)
        self.btn_record.clicked.connect(ctrl.toggle_recording)
        self.cb_bubble.toggled.connect(ctrl.set_bubble)
        self.cb_heat.toggled.connect(ctrl.set_live_heatmap)
        ctrl.profile_changed.connect(self._on_profile)
        ctrl.recording_changed.connect(self._on_recording)
        ctrl.overlay_changed.connect(self._sync_toggles)
        ctrl.source_changed.connect(self._connect_source)
        ctrl.recorder.tick.connect(self._on_tick)
        self._connect_source()
        self._on_profile(ctrl.profile)
        self._sync_toggles()

    # ------------------------------------------------------------ fuente
    def _connect_source(self) -> None:
        src = self.ctrl.source
        src.sample.connect(self._on_sample)
        src.preview.connect(self._on_preview)
        if src.is_direct:
            self.camera.placeholder = "Modo ratón: el cursor actúa como mirada"
            self.camera.set_image(None)
        self._update_preview()

    def showEvent(self, e) -> None:
        self._update_preview()
        super().showEvent(e)

    def hideEvent(self, e) -> None:
        self._update_preview(False)
        super().hideEvent(e)

    def _update_preview(self, visible: bool | None = None) -> None:
        on = self.isVisible() if visible is None else visible
        self.ctrl.source.set_preview(on)

    def _on_preview(self, img: QImage) -> None:
        if self.isVisible():
            self.camera.set_image(img)

    def _on_sample(self, s: FeatureSample) -> None:
        if not self.isVisible():
            return
        q = s.quality
        self.fps.setText(f"{q.fps:.0f} fps" if q.fps else "")
        self.chip_face.set(q.face, "Cara detectada" if q.face else "Sin cara")
        self.chip_dist.set(q.distance == "ok" if q.face else None,
                           {"ok": "Distancia ok", "near": "Muy cerca", "far": "Muy lejos"}.get(q.distance, "Distancia"))
        self.chip_center.set(q.centered if q.face else None, "Centrado" if q.centered else "Descentrado")
        self.chip_light.set(q.light_ok if q.face else None,
                            "Luz ok" if q.light_ok else "Poca luz" if q.brightness < 50 else "Mucha luz")
        self.gauge.set(q.score, f"{q.score * 100:.0f}")
        if not q.face:
            title, hint = "Sin cara", "Mira hacia la cámara y asegúrate de tener luz frontal."
        elif q.score >= 0.99:
            title, hint = "Óptima", "Todo listo para seguir tu mirada."
        else:
            title, hint = "Mejorable", "Ajusta distancia, centrado o luz según los indicadores."
        if s.direct is not None:
            title, hint = "Modo ratón", "Simulación sin cámara para probar la app."
        self.quality_title.setText(title)
        self.quality_hint.setText(hint)

    # ------------------------------------------------------------ estado
    def _on_profile(self, profile) -> None:
        if profile is None:
            self.profile_name.setText("Sin calibrar")
            self.profile_info.setText("Calibra para que el sistema aprenda cómo se mueven tus ojos.")
            self.btn_drift.setEnabled(False)
            return
        v = profile.validation
        self.profile_name.setText(profile.name)
        if v:
            self.profile_info.setText(
                f"{v.get('grade', '')} · {v.get('mean_error_deg', 0):.1f}° ({v.get('mean_error_px', 0):.0f} px) · "
                f"{profile.created.replace('T', ' ')[:16]}")
        self.btn_drift.setEnabled(not self.ctrl.source.is_direct)

    def _on_recording(self, on: bool) -> None:
        if on:
            self.btn_record.setText("  Detener grabación")
            self.btn_record.setIcon(theme.icon("stop", "#ffd3d3"))
            self.btn_record.setObjectName("danger")
            self.st_time.set("00:00")
            self.st_samples.set("0")
            self.st_scenes.set("1")
        else:
            self.btn_record.setText("  Iniciar grabación")
            self.btn_record.setIcon(theme.icon("record", "#06121a"))
            self.btn_record.setObjectName("primary")
        self.btn_record.style().unpolish(self.btn_record)
        self.btn_record.style().polish(self.btn_record)

    def _on_tick(self, seconds: float, samples: int, scenes: int) -> None:
        m, s = divmod(int(seconds), 60)
        self.st_time.set(f"{m:02d}:{s:02d}")
        self.st_samples.set(f"{samples:,}".replace(",", "."))
        self.st_scenes.set(str(scenes))

    def _sync_toggles(self) -> None:
        for cb, val in ((self.cb_bubble, self.ctrl.overlay.bubble), (self.cb_heat, self.ctrl.overlay.heatmap)):
            cb.blockSignals(True)
            cb.setChecked(val)
            cb.blockSignals(False)
