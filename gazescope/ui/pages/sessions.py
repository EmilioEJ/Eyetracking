"""Galería de sesiones grabadas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ...core.session import list_sessions
from .. import theme
from ..widgets.common import Card, label, pixmap_rounded

CARD_W = 300


def _when(meta: dict, path: Path) -> str:
    try:
        d = datetime.fromisoformat(meta.get("started", ""))
        return d.strftime("%d %b %Y · %H:%M")
    except ValueError:
        return path.name


class SessionCard(Card):
    clicked = Signal(str)

    def __init__(self, path: Path, meta: dict):
        super().__init__(hover=True, padding=10, spacing=6)
        self.path = path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(CARD_W)
        thumb = QLabel()
        thumb.setFixedSize(CARD_W - 20, int((CARD_W - 20) * 9 / 16))
        pm = QPixmap(str(path / "thumb.jpg"))
        if not pm.isNull():
            pm = pm.scaled(thumb.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
            thumb.setPixmap(pixmap_rounded(pm, 10))
        else:
            thumb.setText("Sin vista previa")
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setStyleSheet(f"background:{theme.SURFACE_2};border-radius:10px;color:{theme.FAINT};")
        self.lay.addWidget(thumb)
        title = label(_when(meta, path), "h2")
        self.lay.addWidget(title)
        dur = float(meta.get("duration", 0))
        m, s = divmod(int(dur), 60)
        acc = meta.get("accuracy_deg")
        parts = [f"{m}:{s:02d} min", f"{meta.get('fixations', 0)} fijaciones", f"{meta.get('scenes', 0)} escenas"]
        self.lay.addWidget(label(" · ".join(parts), "muted"))
        src = {"mouse": "Ratón (simulación)", "demo": "Ejemplo generado"}.get(meta.get("source"), "Webcam")
        extra = f"{src}" + (f" · precisión {acc:.1f}°" if acc else "")
        self.lay.addWidget(label(extra, "faint"))

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(str(self.path))
        super().mouseReleaseEvent(e)


class SessionsPage(QWidget):
    open_session = Signal(str)

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(18)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label("Sesiones", "h1"))
        self.subtitle = label("", "muted")
        col.addWidget(self.subtitle)
        head.addLayout(col)
        head.addStretch()
        demo = QPushButton(theme.icon("flame"), "Crear sesión de ejemplo")
        demo.setToolTip("Genera una página web simulada con una mirada en patrón F para explorar el visor")
        demo.clicked.connect(self._demo)
        head.addWidget(demo)
        root.addLayout(head)

        self.host = QWidget()
        self.grid = QGridLayout(self.host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.host)
        root.addWidget(scroll, 1)

        self.cards: list[SessionCard] = []
        self._cols = 0
        ctrl.sessions_changed.connect(self.refresh)

    def showEvent(self, e) -> None:
        self.refresh()
        super().showEvent(e)

    def resizeEvent(self, e) -> None:
        cols = max(1, (self.width() - 64 + 16) // (CARD_W + 16))
        if cols != self._cols:
            self._layout_cards()
        super().resizeEvent(e)

    def _demo(self) -> None:
        from ...core.demo import create_demo_session

        path = create_demo_session()
        self.refresh()
        self.open_session.emit(str(path))

    def refresh(self) -> None:
        for c in self.cards:
            c.deleteLater()
        self.cards = []
        sessions = list_sessions()
        n = len(sessions)
        self.subtitle.setText(
            f"{n} sesión grabada" if n == 1 else f"{n} sesiones grabadas" if n else
            "Aún no hay sesiones. Pulsa «Iniciar grabación» en Inicio o Ctrl+Alt+R desde cualquier app.")
        for path, meta in sessions:
            card = SessionCard(path, meta)
            card.clicked.connect(self.open_session.emit)
            self.cards.append(card)
        self._layout_cards()

    def _layout_cards(self) -> None:
        cols = max(1, (self.width() - 64 + 16) // (CARD_W + 16))
        self._cols = cols
        for i, c in enumerate(self.cards):
            self.grid.addWidget(c, i // cols, i % cols)
