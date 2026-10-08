"""Ventana principal del dashboard con barra lateral de navegación."""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from . import theme
from .pages.calibrate import CalibratePage
from .pages.home import HomePage
from .pages.sessions import SessionsPage
from .pages.settings import SettingsPage
from .pages.viewer import ViewerPage
from .widgets.common import StatusDot, label

NAV = [("home", "Inicio", "home"), ("calibrate", "Calibración", "target"),
       ("sessions", "Sesiones", "sessions"), ("settings", "Ajustes", "settings")]


class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet(
            f"background:{theme.SURFACE_3};border:1px solid {theme.LINE};border-radius:10px;"
            f"padding:10px 16px;color:{theme.FG};")
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade)
        self.hide()

    def show_message(self, text: str, ms: int = 3200) -> None:
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move(p.width() - self.width() - 24, p.height() - self.height() - 24)
        self.anim.stop()
        self.effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self.timer.start(ms)

    def _fade(self) -> None:
        self.anim.setDuration(400)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.hide)
        self.anim.start()


class MainWindow(QMainWindow):
    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(theme.app_icon())
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --------------------------------------------------- sidebar
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 20, 16, 16)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(theme.app_icon().pixmap(QSize(36, 36)))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label(APP_NAME, "brand"))
        names.addWidget(label("Eye-tracking studio", "brandSub"))
        brand.addLayout(names, 1)
        sl.addLayout(brand)
        sl.addSpacing(24)

        self.nav_group = QButtonGroup(self)
        self.nav: dict[str, QPushButton] = {}
        for key, text, ic in NAV:
            b = QPushButton(theme.nav_icon(ic), "  " + text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.nav_group.addButton(b)
            self.nav[key] = b
            sl.addWidget(b)
        sl.addStretch()

        status = QFrame()
        status.setObjectName("chip")
        st = QVBoxLayout(status)
        st.setContentsMargins(12, 10, 12, 10)
        st.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.status_dot = StatusDot(theme.OK)
        self.status_text = label("Seguimiento activo")
        row.addWidget(self.status_dot)
        row.addWidget(self.status_text, 1)
        st.addLayout(row)
        self.status_sub = label("", "faint")
        st.addWidget(self.status_sub)
        sl.addWidget(status)
        sl.addSpacing(6)
        sl.addWidget(label(f"v{__version__}", "faint"))
        lay.addWidget(side)

        # --------------------------------------------------- páginas
        self.stack = QStackedWidget()
        self.home = HomePage(ctrl)
        self.calibrate = CalibratePage(ctrl)
        self.sessions = SessionsPage(ctrl)
        self.settings = SettingsPage(ctrl)
        self.viewer = ViewerPage(ctrl)
        self.pages = {"home": self.home, "calibrate": self.calibrate, "sessions": self.sessions,
                      "settings": self.settings, "viewer": self.viewer}
        for p in self.pages.values():
            self.stack.addWidget(p)
        lay.addWidget(self.stack, 1)

        self.toast = Toast(root)
        self.sessions.open_session.connect(self.open_session)
        self.viewer.back.connect(lambda: self.go("sessions"))
        ctrl.recording_changed.connect(self._on_status)
        ctrl.profile_changed.connect(lambda _p: self._on_status())
        ctrl.source_changed.connect(self._on_status)
        self.go("home")
        self._on_status()

    def go(self, key: str) -> None:
        self.stack.setCurrentWidget(self.pages[key])
        nav_key = "sessions" if key == "viewer" else key
        self.nav[nav_key].setChecked(True)

    def open_session(self, path: str) -> None:
        self.viewer.load(path)
        self.go("viewer")

    def _on_status(self, *_a) -> None:
        c = self.ctrl
        src = "Ratón (simulación)" if c.source.is_direct else "Webcam"
        if c.recorder.recording:
            self.status_dot.set_color(theme.DANGER)
            self.status_text.setText("Grabando")
        elif c.engine.ready or c.source.is_direct:
            self.status_dot.set_color(theme.OK)
            self.status_text.setText("Seguimiento activo")
        else:
            self.status_dot.set_color(theme.WARN)
            self.status_text.setText("Sin calibrar")
        prof = c.profile.name if c.profile else "sin perfil"
        self.status_sub.setText(f"{src} · {prof}")

    def closeEvent(self, e) -> None:
        # Cerrar la ventana no detiene el seguimiento: la app sigue en la bandeja.
        if self.ctrl.tray_available and not self.ctrl.quitting:
            e.ignore()
            self.hide()
            self.ctrl.notify_background()
        else:
            e.accept()
            self.ctrl.quit()
