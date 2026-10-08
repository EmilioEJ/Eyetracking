"""Fuentes de mirada (webcam o ratón) y motor que las convierte en puntos en pantalla."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRect, QThread, QTimer, Signal
from PySide6.QtGui import QCursor, QImage

from .calibration import GazeModel
from .features import (
    LEFT_EYE_CONTOUR,
    RIGHT_EYE_CONTOUR,
    BlinkDetector,
    FaceFeatures,
    extract_features,
)
from .filters import OneEuroFilter2D
from .head_pose import HeadPoseEstimator


@dataclass
class TrackingQuality:
    face: bool = False
    distance: str = "none"  # ok | near | far | none
    centered: bool = False
    brightness: float = 0.0
    blink: bool = False
    fps: float = 0.0

    @property
    def light_ok(self) -> bool:
        return 50.0 <= self.brightness <= 215.0

    @property
    def score(self) -> float:
        if not self.face:
            return 0.0
        checks = (self.distance == "ok", self.centered, self.light_ok)
        return 0.4 + 0.2 * sum(checks)


@dataclass
class FeatureSample:
    t: float
    vector: np.ndarray | None
    valid: bool
    quality: TrackingQuality = field(default_factory=TrackingQuality)
    direct: tuple[float, float] | None = None  # coordenadas normalizadas (fuente ratón)


@dataclass
class GazePoint:
    t: float
    x: float  # px relativos al monitor
    y: float
    valid: bool


# ---------------------------------------------------------------- webcam
class CameraSource(QThread):
    sample = Signal(object)  # FeatureSample
    preview = Signal(QImage)
    error = Signal(str)
    is_direct = False

    def __init__(self, index: int = 0, width: int = 640, height: int = 480, parent=None):
        super().__init__(parent)
        self.index, self.width, self.height = index, width, height
        self._running = False
        self.preview_enabled = False

    def set_preview(self, enabled: bool) -> None:
        self.preview_enabled = enabled

    def stop(self) -> None:
        self._running = False
        self.wait(3000)

    def run(self) -> None:  # noqa: C901 - bucle principal de captura
        import mediapipe as mp

        cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            self.error.emit(f"No se pudo abrir la cámara {self.index}")
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, 30)

        mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        pose = HeadPoseEstimator()
        blink = BlinkDetector()
        fps, last, failures, frame_no = 0.0, time.monotonic(), 0, 0
        self._running = True
        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    failures += 1
                    if failures > 60:
                        self.error.emit("La cámara dejó de entregar imágenes")
                        break
                    time.sleep(0.02)
                    continue
                failures = 0
                now = time.monotonic()
                fps = 0.9 * fps + 0.1 * (1.0 / max(now - last, 1e-3))
                last = now
                h, w = frame.shape[:2]

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                result = mesh.process(rgb)

                q = TrackingQuality(fps=fps)
                feats: FaceFeatures | None = None
                if result.multi_face_landmarks:
                    lm = result.multi_face_landmarks[0].landmark
                    arr = np.array([(p.x, p.y, p.z) for p in lm], dtype=np.float64)
                    feats = extract_features(arr, w, h, pose)
                    q.face = True
                    q.blink = blink.update(feats.ear)
                    io = feats.vector[8]
                    q.distance = "far" if io < 0.11 else "near" if io > 0.26 else "ok"
                    cx, cy = feats.vector[6], feats.vector[7]
                    q.centered = abs(cx - 0.5) < 0.17 and abs(cy - 0.5) < 0.2
                    x, y, bw, bh = (int(v) for v in feats.face_box)
                    roi = frame[max(y, 0): y + bh, max(x, 0): x + bw]
                    q.brightness = float(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).mean()) if roi.size else 0.0
                else:
                    pose.reset()
                    q.brightness = float(frame.mean())

                vector = feats.vector if feats is not None else None
                self.sample.emit(FeatureSample(now, vector, feats is not None and not q.blink, q))

                frame_no += 1
                if self.preview_enabled and frame_no % 2 == 0:
                    self.preview.emit(self._render_preview(frame, feats, q))
        finally:
            cap.release()
            mesh.close()

    @staticmethod
    def _render_preview(frame: np.ndarray, feats: FaceFeatures | None, q: TrackingQuality) -> QImage:
        img = frame.copy()
        if feats is not None:
            pts = feats.landmarks_px.astype(np.int32)
            accent = (255, 214, 0) if not q.blink else (90, 90, 255)
            for contour in (RIGHT_EYE_CONTOUR, LEFT_EYE_CONTOUR):
                cv2.polylines(img, [pts[list(contour)]], True, accent, 1, cv2.LINE_AA)
            for eye in (feats.right, feats.left):
                c = tuple(int(v) for v in eye.iris_center)
                cv2.circle(img, c, max(2, int(eye.iris_radius)), (246, 92, 139), 1, cv2.LINE_AA)
                cv2.circle(img, c, 2, (255, 255, 255), -1, cv2.LINE_AA)
            x, y, bw, bh = (int(v) for v in feats.face_box)
            k = max(10, bw // 6)
            for (px, py), (dx, dy) in (
                ((x, y), (1, 1)), ((x + bw, y), (-1, 1)), ((x, y + bh), (1, -1)), ((x + bw, y + bh), (-1, -1))
            ):
                cv2.line(img, (px, py), (px + dx * k, py), (230, 230, 230), 2, cv2.LINE_AA)
                cv2.line(img, (px, py), (px, py + dy * k), (230, 230, 230), 2, cv2.LINE_AA)
        img = cv2.flip(img, 1)  # espejo: más natural para el usuario
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


# ----------------------------------------------------------------- ratón
class MouseSource(QObject):
    """Usa el cursor como "mirada": sirve para probar todo sin cámara."""

    sample = Signal(object)
    preview = Signal(QImage)
    error = Signal(str)
    is_direct = True

    def __init__(self, monitor: QRect, parent=None):
        super().__init__(parent)
        self.monitor = QRect(monitor)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._rng = np.random.default_rng()

    def set_preview(self, enabled: bool) -> None:
        pass

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def isRunning(self) -> bool:  # misma interfaz que QThread
        return self._timer.isActive()

    def _tick(self) -> None:
        pos = QCursor.pos()
        m = self.monitor
        nx = (pos.x() - m.x()) / max(m.width(), 1)
        ny = (pos.y() - m.y()) / max(m.height(), 1)
        noise = self._rng.normal(0, 0.004, 2)
        vector = np.array([nx + noise[0], ny + noise[1], 0.3, 0, 0, 0, 0.5, 0.5, 0.18])
        q = TrackingQuality(face=True, distance="ok", centered=True, brightness=128, fps=30)
        self.sample.emit(FeatureSample(time.monotonic(), vector, True, q, direct=(nx, ny)))


# ----------------------------------------------------------------- motor
class GazeEngine(QObject):
    """Convierte muestras de características en puntos filtrados sobre el monitor."""

    gaze = Signal(object)  # GazePoint

    def __init__(self, monitor: QRect, parent=None):
        super().__init__(parent)
        self.monitor = QRect(monitor)
        self.model: GazeModel | None = None
        self.filter = OneEuroFilter2D(0.5, 0.0015)
        self._last = (monitor.width() / 2, monitor.height() / 2)
        self._invalid_streak = 0

    @property
    def ready(self) -> bool:
        return self.model is not None

    def set_model(self, model: GazeModel | None) -> None:
        self.model = model
        self.filter.reset()

    def set_monitor(self, monitor: QRect) -> None:
        self.monitor = QRect(monitor)
        self.filter.reset()

    def predict_norm(self, s: FeatureSample) -> tuple[float, float] | None:
        if s.direct is not None:
            return s.direct
        if self.model is not None and s.valid and s.vector is not None:
            nx, ny = self.model.predict(s.vector)
            return float(nx), float(ny)
        return None

    def on_sample(self, s: FeatureSample) -> None:
        norm = self.predict_norm(s)
        if norm is None:
            self._invalid_streak += 1
            if self._invalid_streak > 6:  # tras ~200 ms sin datos reiniciamos el filtro
                self.filter.reset()
            self.gaze.emit(GazePoint(s.t, self._last[0], self._last[1], False))
            return
        self._invalid_streak = 0
        nx = min(max(norm[0], -0.05), 1.05)
        ny = min(max(norm[1], -0.05), 1.05)
        x, y = self.filter(nx * self.monitor.width(), ny * self.monitor.height(), s.t)
        self._last = (x, y)
        self.gaze.emit(GazePoint(s.t, x, y, True))
