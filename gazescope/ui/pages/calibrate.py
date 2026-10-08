"""Calibración: lanzar una nueva calibración y gestionar perfiles guardados."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.calibration import Profile, list_profiles
from .. import screens, theme
from ..widgets.common import Card, StatusDot, label

STEPS = [
    ("Posición", "Centra tu cara frente a la cámara con luz frontal, a ~60 cm de la pantalla."),
    ("Calibración", "Sigue con la mirada un punto que recorre la pantalla. La cabeza, quieta."),
    ("Validación", "5 puntos nuevos miden la precisión real en grados y píxeles."),
]


class CalibratePage(QWidget):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(18)
        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(label("Calibración", "h1"))
        head.addWidget(label("Enseña al sistema cómo se ven tus ojos al mirar cada zona de la pantalla.", "muted"))
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(18)
        root.addLayout(body, 1)

        # --------------------------------------------------- nueva calibración
        new = Card(padding=24, spacing=14)
        new.lay.addWidget(label("Nueva calibración", "h2"))
        for i, (title, text) in enumerate(STEPS, start=1):
            row = QHBoxLayout()
            row.setSpacing(14)
            num = label(str(i))
            num.setFixedSize(30, 30)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(f"background:{theme.SURFACE_3};border-radius:15px;font-weight:700;color:{theme.ACCENT};")
            row.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(title, "h2"))
            col.addWidget(label(text, "muted", wrap=True))
            row.addLayout(col, 1)
            new.lay.addLayout(row)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.name = QLineEdit(ctrl.settings.active_profile or "Mi perfil")
        self.points = QComboBox()
        self.points.addItem("9 puntos · rápida", 9)
        self.points.addItem("13 puntos · recomendada", 13)
        self.points.setCurrentIndex(1 if ctrl.settings.calibration_points >= 13 else 0)
        self.monitor = label("", "muted")
        form.addRow(label("Nombre del perfil", "muted"), self.name)
        form.addRow(label("Puntos", "muted"), self.points)
        form.addRow(label("Monitor", "muted"), self.monitor)
        new.lay.addLayout(form)
        new.lay.addStretch()
        self.btn_start = QPushButton(theme.icon("target", "#06121a"), "  Iniciar calibración")
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumHeight(48)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        new.lay.addWidget(self.btn_start)
        body.addWidget(new, 1)

        # --------------------------------------------------- perfiles
        prof = Card(padding=24, spacing=12)
        prof.lay.addWidget(label("Perfiles guardados", "h2"))
        prof.lay.addWidget(label("Un perfil por persona o puesto. El activo se usa al grabar.", "muted"))
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.list_host)
        prof.lay.addWidget(scroll, 1)
        body.addWidget(prof, 1)

        self.btn_start.clicked.connect(self._start)
        ctrl.profile_changed.connect(lambda _p: self.refresh())

    def showEvent(self, e) -> None:
        self.refresh()
        super().showEvent(e)

    def _start(self) -> None:
        name = self.name.text().strip() or "Mi perfil"
        self.ctrl.settings.calibration_points = int(self.points.currentData())
        self.ctrl.settings.save()
        self.ctrl.calibrate(name)

    def refresh(self) -> None:
        self.monitor.setText(screens.describe(self.ctrl.screen()))
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        names = list_profiles()
        if not names:
            self.list_lay.addWidget(label("Todavía no hay perfiles. Haz tu primera calibración.", "faint"))
        active = self.ctrl.profile.name if self.ctrl.profile else None
        for name in names:
            try:
                p = Profile.load(name)
            except (OSError, ValueError, KeyError):
                continue
            self.list_lay.addWidget(self._row(p, p.name == active))
        self.list_lay.addStretch()

    def _row(self, p: Profile, active: bool) -> QWidget:
        card = Card(padding=12, spacing=4)
        top = QHBoxLayout()
        v = p.validation or {}
        grade = v.get("grade", "")
        color = {"Excelente": theme.OK, "Buena": theme.ACCENT, "Regular": theme.WARN}.get(grade, theme.DANGER)
        top.addWidget(StatusDot(color))
        top.addWidget(label(p.name + ("  · activo" if active else ""), "h2"), 1)
        if not active:
            use = QPushButton("Usar")
            use.clicked.connect(lambda: self.ctrl.set_profile(p.name))
            top.addWidget(use)
        rm = QPushButton(theme.icon("trash", theme.MUTED, 16), "")
        rm.setObjectName("ghost")
        rm.setToolTip("Eliminar perfil")
        rm.clicked.connect(lambda: self._delete(p.name))
        top.addWidget(rm)
        card.lay.addLayout(top)
        info = f"{grade} · {v.get('mean_error_deg', 0):.1f}° · {v.get('mean_error_px', 0):.0f} px" if v else ""
        card.lay.addWidget(label(f"{info} · {p.created.replace('T', ' ')[:16]} · {p.monitor.get('name', '')}",
                                 "faint"))
        return card

    def _delete(self, name: str) -> None:
        if QMessageBox.question(self, "Eliminar perfil", f"¿Eliminar el perfil «{name}»?") \
                == QMessageBox.StandardButton.Yes:
            self.ctrl.delete_profile(name)
            self.refresh()
