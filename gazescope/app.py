"""Controlador de la aplicación: conecta fuente, motor, overlay, grabación, bandeja y atajos."""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME
from .config import Settings
from .core.calibration import Profile, list_profiles, profile_path
from .core.recorder import SessionRecorder
from .core.sources import CameraSource, GazeEngine, MouseSource
from .ui import screens, theme
from .ui.calibration_window import CalibrationWindow
from .ui.overlay import GazeOverlay

HOTKEYS = {
    "<ctrl>+<alt>+r": "record",
    "<ctrl>+<alt>+b": "bubble",
    "<ctrl>+<alt>+h": "heatmap",
    "<ctrl>+<alt>+d": "drift",
}


class HotkeyBridge(QObject):
    """pynput escucha en su propio hilo; la señal lleva el evento al hilo de Qt."""

    triggered = Signal(str)

    def __init__(self):
        super().__init__()
        self._listener = None

    def start(self) -> bool:
        try:
            from pynput import keyboard

            self._listener = keyboard.GlobalHotKeys(
                {combo: (lambda a=action: self.triggered.emit(a)) for combo, action in HOTKEYS.items()})
            self._listener.daemon = True
            self._listener.start()
            return True
        except Exception:
            return False

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()


class Controller(QObject):
    profile_changed = Signal(object)
    recording_changed = Signal(bool)
    overlay_changed = Signal()
    source_changed = Signal()
    sessions_changed = Signal()

    def __init__(self, app: QApplication, source_kind: str = "webcam", monitor: int | None = None,
                 start_hidden: bool = False):
        super().__init__()
        self.app = app
        self.quitting = False
        self.source_kind = source_kind
        self.settings = Settings.load()
        if monitor is not None:
            self.settings.monitor_index = monitor
        self.profile: Profile | None = None
        self._cal_window: CalibrationWindow | None = None
        self._bg_notified = False

        rect = self.screen().geometry()
        self.engine = GazeEngine(rect)
        self.engine.filter.configure(self.settings.filter_min_cutoff, self.settings.filter_beta)
        self.overlay = GazeOverlay(rect, self.settings.colormap)
        self.overlay.bubble = self.settings.overlay_bubble
        self.overlay.heatmap = self.settings.overlay_heatmap
        self.recorder = SessionRecorder(self.settings)
        self.recorder.set_capture_hooks(self.overlay.hide_for_capture, self.overlay.restore_after_capture)
        self.engine.gaze.connect(self.overlay.on_gaze)
        self.engine.gaze.connect(self.recorder.on_gaze)
        self.recorder.stopped.connect(self._on_recording_stopped)

        self.source = self._make_source()
        self._start_source()

        if self.settings.active_profile and profile_path(self.settings.active_profile).exists():
            self.set_profile(self.settings.active_profile, announce=False)
        elif list_profiles():
            self.set_profile(list_profiles()[0], announce=False)

        from .ui.main_window import MainWindow

        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.window = MainWindow(self)
        self._build_tray()
        self.hotkeys = HotkeyBridge()
        self.hotkeys.triggered.connect(self._on_hotkey, Qt.ConnectionType.QueuedConnection)
        self.hotkeys_ok = self.hotkeys.start()

        self._refresh_overlay()
        if not (start_hidden and self.tray_available):
            self.window.show()

    # ------------------------------------------------------------ monitor
    def screen(self):
        return screens.screen_at(self.settings.monitor_index)

    def px_per_deg(self) -> float:
        return screens.px_per_degree(self.screen(), self.settings.viewing_distance_mm)

    # ------------------------------------------------------------ fuente
    def _make_source(self):
        if self.source_kind == "mouse":
            return MouseSource(self.screen().geometry())
        s = self.settings
        return CameraSource(s.camera_index, s.camera_width, s.camera_height)

    def _start_source(self) -> None:
        self.source.sample.connect(self.engine.on_sample)
        self.source.error.connect(self._on_source_error)
        self.source.start()

    def _restart_source(self) -> None:
        self.source.stop()
        self.source.deleteLater()
        self.source = self._make_source()
        self._start_source()
        self.source_changed.emit()

    def _on_source_error(self, msg: str) -> None:
        self.toast(msg)
        if self.tray_available:
            self.tray.showMessage(APP_NAME, msg, QSystemTrayIcon.MessageIcon.Warning, 5000)

    # ------------------------------------------------------------ perfiles
    def set_profile(self, name: str, announce: bool = True) -> None:
        try:
            self.profile = Profile.load(name)
        except (OSError, ValueError, KeyError):
            self.profile = None
            if announce:
                self.toast(f"No se pudo cargar el perfil «{name}»")
            return
        self.engine.set_model(self.profile.model)
        self.settings.active_profile = self.profile.name
        self.settings.save()
        self.profile_changed.emit(self.profile)
        if announce:
            self.toast(f"Perfil activo: {self.profile.name}")

    def delete_profile(self, name: str) -> None:
        try:
            profile_path(name).unlink()
        except OSError:
            return
        if self.profile and self.profile.name == name:
            self.profile = None
            self.engine.set_model(None)
            self.settings.active_profile = ""
            self.settings.save()
            self.profile_changed.emit(None)

    # ------------------------------------------------------------ calibración
    def calibrate(self, name: str | None = None) -> None:
        if self._cal_window is not None:
            return
        if self.recorder.recording:
            self.stop_recording()
        name = name or (self.profile.name if self.profile else "Mi perfil")
        screen = self.screen()
        self._open_calibration(CalibrationWindow(
            self.source, screen, name, self.settings.calibration_points, self.px_per_deg(),
            screens.monitor_info(screen, self.settings.viewing_distance_mm), mode="full"))

    def drift_correct(self) -> None:
        if self._cal_window is not None or self.profile is None or self.source.is_direct:
            if self.profile is None:
                self.toast("Primero necesitas un perfil de calibración")
            return
        screen = self.screen()
        self._open_calibration(CalibrationWindow(
            self.source, screen, self.profile.name, 1, self.px_per_deg(),
            screens.monitor_info(screen, self.settings.viewing_distance_mm), mode="drift",
            base_profile=self.profile))

    def _open_calibration(self, win: CalibrationWindow) -> None:
        self._cal_window = win
        self.overlay.set_modes(suppressed=True)
        win.finished.connect(self._on_calibration_done)
        win.open()

    def _on_calibration_done(self, profile: Profile | None) -> None:
        mode = self._cal_window.mode if self._cal_window else "full"
        self._cal_window = None
        if profile is not None:
            if mode == "drift":
                profile.save()
                self.toast("Deriva corregida")
            self.profile = None
            self.set_profile(profile.name, announce=mode != "drift")
        self.engine.filter.reset()
        self._refresh_overlay()
        self.window.home._update_preview()

    # ------------------------------------------------------------ overlay
    def set_bubble(self, on: bool) -> None:
        self.settings.overlay_bubble = on
        self.settings.save()
        self._refresh_overlay()

    def set_live_heatmap(self, on: bool) -> None:
        self.settings.overlay_heatmap = on
        self.settings.save()
        if on:
            self.overlay.clear_heatmap()
        self._refresh_overlay()

    def _refresh_overlay(self) -> None:
        suppressed = self._cal_window is not None or (
            self.recorder.recording and self.settings.hide_overlay_while_recording)
        if not (self.engine.ready or self.source.is_direct):
            suppressed = True
        self.overlay.set_modes(self.settings.overlay_bubble, self.settings.overlay_heatmap, suppressed)
        if hasattr(self, "act_bubble"):
            self.act_bubble.setChecked(self.settings.overlay_bubble)
            self.act_heat.setChecked(self.settings.overlay_heatmap)
        self.overlay_changed.emit()

    # ------------------------------------------------------------ grabación
    def toggle_recording(self) -> None:
        if self.recorder.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        if self.recorder.recording or self._cal_window is not None:
            return
        if not (self.engine.ready or self.source.is_direct):
            self.toast("Calibra antes de grabar")
            self.window.show()
            self.window.go("calibrate")
            return
        import time

        screen = self.screen()
        v = self.profile.validation if self.profile else {}
        meta = {
            "source": self.source_kind,
            "monitor": screens.monitor_info(screen, self.settings.viewing_distance_mm),
            "px_per_deg": self.px_per_deg(),
            "profile": self.profile.name if self.profile else None,
            "accuracy_px": v.get("mean_error_px"),
            "accuracy_deg": v.get("mean_error_deg"),
        }
        self.recorder.start(screen.geometry(), meta, time.monotonic())
        self.overlay.clear_heatmap()
        self._refresh_overlay()
        self.tray.setIcon(theme.app_icon(recording=True))
        self.act_record.setText("Detener grabación")
        self.recording_changed.emit(True)
        self.toast("Grabando · Ctrl+Alt+R para detener")

    def stop_recording(self) -> None:
        self.recorder.stop()

    def _on_recording_stopped(self, path: str) -> None:
        self.tray.setIcon(theme.app_icon())
        self.act_record.setText("Iniciar grabación")
        self._refresh_overlay()
        self.recording_changed.emit(False)
        self.sessions_changed.emit()
        self.toast("Sesión guardada")
        if self.tray_available and not self.window.isVisible():
            self.tray.showMessage(APP_NAME, "Sesión guardada. Ábrela desde el panel.",
                                  QSystemTrayIcon.MessageIcon.Information, 4000)

    # ------------------------------------------------------------ ajustes
    def apply_settings(self, new: Settings) -> None:
        old = self.settings
        restart = (new.camera_index, new.camera_width, new.camera_height) != (
            old.camera_index, old.camera_width, old.camera_height)
        monitor_changed = new.monitor_index != old.monitor_index
        if self.recorder.recording and (restart or monitor_changed):
            self.stop_recording()
        self.settings = new
        self.recorder.settings = new
        new.save()
        self.engine.filter.configure(new.filter_min_cutoff, new.filter_beta)
        self.overlay.colormap = new.colormap
        if monitor_changed:
            rect = self.screen().geometry()
            self.engine.set_monitor(rect)
            self.overlay.set_monitor(rect)
            if isinstance(self.source, MouseSource):
                self.source.monitor = rect
        if restart and not self.source.is_direct:
            self._restart_source()
        self._refresh_overlay()
        self.toast("Ajustes guardados" + (" · recalibra para el nuevo monitor" if monitor_changed else ""))

    # ------------------------------------------------------------ bandeja
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(theme.app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        self.act_record = QAction("Iniciar grabación", self)
        self.act_record.triggered.connect(self.toggle_recording)
        self.act_bubble = QAction("Burbuja de mirada", self, checkable=True)
        self.act_bubble.triggered.connect(self.set_bubble)
        self.act_heat = QAction("Mapa de calor en vivo", self, checkable=True)
        self.act_heat.triggered.connect(self.set_live_heatmap)
        act_drift = QAction("Corregir deriva", self)
        act_drift.triggered.connect(self.drift_correct)
        act_cal = QAction("Calibrar…", self)
        act_cal.triggered.connect(lambda: self.calibrate())
        act_open = QAction("Abrir panel", self)
        act_open.triggered.connect(self.show_window)
        act_quit = QAction("Salir", self)
        act_quit.triggered.connect(self.quit)
        for a in (self.act_record, None, self.act_bubble, self.act_heat, None, act_cal, act_drift, None,
                  act_open, act_quit):
            menu.addSeparator() if a is None else menu.addAction(a)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.show_window() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        if self.tray_available:
            self.tray.show()

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def notify_background(self) -> None:
        if not self._bg_notified:
            self._bg_notified = True
            self.tray.showMessage(APP_NAME, "Sigue funcionando en segundo plano. Ctrl+Alt+R para grabar.",
                                  QSystemTrayIcon.MessageIcon.Information, 4000)

    def toast(self, text: str) -> None:
        if hasattr(self, "window"):
            self.window.toast.show_message(text)

    # ------------------------------------------------------------ atajos
    def _on_hotkey(self, action: str) -> None:
        if action == "record":
            self.toggle_recording()
        elif action == "bubble":
            self.set_bubble(not self.settings.overlay_bubble)
        elif action == "heatmap":
            self.set_live_heatmap(not self.settings.overlay_heatmap)
        elif action == "drift":
            self.drift_correct()

    # ------------------------------------------------------------ salida
    def quit(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        if self.recorder.recording:
            self.recorder.stop()
        self.hotkeys.stop()
        self.source.stop()
        self.overlay.close()
        self.tray.hide()
        self.window.close()
        self.app.quit()


def run(source: str = "webcam", monitor: int | None = None, hidden: bool = False) -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(theme.app_icon())
    try:
        ctrl = Controller(app, source, monitor, hidden)
    except Exception as exc:  # pragma: no cover - errores de arranque visibles
        QMessageBox.critical(None, APP_NAME, f"No se pudo iniciar: {exc}")
        raise
    app.aboutToQuit.connect(lambda: None if ctrl.quitting else ctrl.quit())
    return app.exec()
