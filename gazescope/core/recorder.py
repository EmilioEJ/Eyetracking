"""Grabación de sesiones en segundo plano: mirada + capturas de pantalla + ventana activa."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRect, QTimer, Signal

from ..config import SESSIONS_DIR, Settings
from .fixations import detect_fixations
from .sources import GazePoint


class ActiveWindow:
    """Título de la ventana activa vía EWMH (X11). Devuelve "" si no está disponible."""

    def __init__(self) -> None:
        self._d = None
        try:
            from Xlib import X, display

            self._X = X
            self._d = display.Display()
            self._root = self._d.screen().root
            self._active = self._d.intern_atom("_NET_ACTIVE_WINDOW")
            self._name = self._d.intern_atom("_NET_WM_NAME")
            self._utf8 = self._d.intern_atom("UTF8_STRING")
        except Exception:
            self._d = None

    def title(self) -> str:
        if self._d is None:
            return ""
        try:
            prop = self._root.get_full_property(self._active, self._X.AnyPropertyType)
            if not prop or not prop.value:
                return ""
            win = self._d.create_resource_object("window", int(prop.value[0]))
            name = win.get_full_property(self._name, self._utf8)
            if name and name.value:
                v = name.value
                return v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)
            wm = win.get_wm_name()
            return wm or ""
        except Exception:
            return ""

    def close(self) -> None:
        if self._d is not None:
            try:
                self._d.close()
            except Exception:
                pass


class SessionRecorder(QObject):
    started = Signal(str)
    stopped = Signal(str)  # ruta de la sesión
    scene_changed = Signal(int, str)  # id, título
    tick = Signal(float, int, int)  # segundos, muestras, escenas

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.path: Path | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._capture)
        self._before_capture: Callable[[], bool] | None = None
        self._after_capture: Callable[[], None] | None = None
        self._reset()

    def _reset(self) -> None:
        self._file = None
        self._writer = None
        self._t0 = 0.0
        self._t: list[float] = []
        self._x: list[float] = []
        self._y: list[float] = []
        self._valid: list[bool] = []
        self._scene: list[int] = []
        self._scenes: list[dict] = []
        self._thumb: np.ndarray | None = None
        self._title = ""
        self._sct = None
        self._window: ActiveWindow | None = None
        self._meta: dict = {}

    @property
    def recording(self) -> bool:
        return self.path is not None

    def set_capture_hooks(self, before: Callable[[], bool], after: Callable[[], None]) -> None:
        """`before` oculta el overlay y devuelve True si había que ocultarlo."""
        self._before_capture, self._after_capture = before, after

    # ------------------------------------------------------------ ciclo
    def start(self, monitor: QRect, meta: dict, t0: float) -> Path:
        import mss

        if self.recording:
            return self.path  # type: ignore[return-value]
        self._reset()
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = SESSIONS_DIR / stamp
        (self.path / "screens").mkdir(parents=True, exist_ok=True)
        self._monitor = QRect(monitor)
        self._t0 = t0
        self._meta = dict(meta, id=stamp, started=datetime.now().isoformat(timespec="seconds"),
                          width=monitor.width(), height=monitor.height())
        self._file = open(self.path / "gaze.csv", "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(["t", "x", "y", "valid", "scene_id"])
        self._sct = mss.mss()
        self._window = ActiveWindow()
        self._capture()
        self._timer.start(int(self.settings.screenshot_interval_s * 1000))
        self.started.emit(str(self.path))
        return self.path

    def stop(self) -> Path | None:
        if not self.recording:
            return None
        self._timer.stop()
        path = self.path
        assert path is not None
        end = self._t[-1] if self._t else 0.0
        if self._scenes:
            self._scenes[-1]["t_end"] = end
        if self._file:
            self._file.close()

        px_per_deg = float(self._meta.get("px_per_deg", 40.0))
        s = self.settings
        fixations = detect_fixations(
            self._t, self._x, self._y, self._valid, self._scene, px_per_deg,
            s.ivt_velocity_deg_s, s.min_fixation_ms, s.merge_distance_deg, s.merge_gap_ms,
        )
        with open(path / "fixations.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["start", "end", "duration", "x", "y", "n", "scene_id"])
            w.writeheader()
            for fx in fixations:
                w.writerow(fx.to_row())

        (path / "scenes.json").write_text(json.dumps(self._scenes, indent=2, ensure_ascii=False), "utf-8")
        valid = int(np.sum(self._valid)) if self._valid else 0
        self._meta.update(
            ended=datetime.now().isoformat(timespec="seconds"),
            duration=end,
            samples=len(self._t),
            valid_ratio=valid / len(self._t) if self._t else 0.0,
            fixations=len(fixations),
            scenes=len(self._scenes),
        )
        (path / "meta.json").write_text(json.dumps(self._meta, indent=2, ensure_ascii=False), "utf-8")

        if self._sct is not None:
            self._sct.close()
        if self._window is not None:
            self._window.close()
        self.path = None
        self._reset()

        from .session import Session

        try:
            Session(path).write_thumbnail(s.colormap)
        except Exception:
            pass
        self.stopped.emit(str(path))
        return path

    # ---------------------------------------------------------- muestras
    def on_gaze(self, p: GazePoint) -> None:
        if not self.recording or self._writer is None:
            return
        t = p.t - self._t0
        scene = self._scenes[-1]["id"] if self._scenes else 0  # la 1ª captura puede ir con retraso
        self._t.append(t)
        self._x.append(p.x)
        self._y.append(p.y)
        self._valid.append(p.valid)
        self._scene.append(scene)
        self._writer.writerow([f"{t:.4f}", f"{p.x:.1f}", f"{p.y:.1f}", int(p.valid), scene])
        if len(self._t) % 30 == 0:
            self.tick.emit(t, len(self._t), len(self._scenes))

    # ---------------------------------------------------------- capturas
    def _capture(self) -> None:
        if not self.recording:
            return
        hidden = self._before_capture() if self._before_capture else False
        if hidden:
            QTimer.singleShot(60, self._grab_and_restore)  # deja que el compositor repinte
        else:
            self._grab()

    def _grab_and_restore(self) -> None:
        try:
            self._grab()
        finally:
            if self._after_capture:
                self._after_capture()

    def _grab(self) -> None:
        if self._sct is None or self.path is None:
            return
        m = self._monitor
        shot = np.asarray(self._sct.grab({"left": m.x(), "top": m.y(), "width": m.width(), "height": m.height()}))
        frame = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
        thumb = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA)
        title = self._window.title() if self._window else ""
        changed = (
            self._thumb is None
            or title != self._title
            or float(np.mean(cv2.absdiff(thumb, self._thumb))) > self.settings.scene_change_threshold
        )
        if not changed:
            return
        self._thumb, self._title = thumb, title
        now = self._t[-1] if self._t else 0.0
        if self._scenes:
            self._scenes[-1]["t_end"] = now
        sid = len(self._scenes)
        name = f"scene_{sid:03d}.jpg"
        cv2.imwrite(str(self.path / "screens" / name), frame,
                    [cv2.IMWRITE_JPEG_QUALITY, int(self.settings.jpeg_quality)])
        self._scenes.append({"id": sid, "file": f"screens/{name}", "t_start": now, "t_end": now, "title": title})
        self.scene_changed.emit(sid, title)
