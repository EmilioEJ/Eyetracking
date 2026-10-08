"""Extracción de características de la mirada a partir de la malla facial.

La versión anterior usaba la posición absoluta del iris en la imagen, que cambia
igual si mueves los ojos o la cabeza. Aquí medimos el iris *dentro* de cada ojo
(respecto a sus esquinas y párpados) y añadimos la pose de la cabeza, de modo que
el modelo puede separar ambos movimientos.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .head_pose import HeadPoseEstimator

# Ojo derecho del sujeto (a la izquierda en la imagen) e izquierdo.
# outer/inner = esquinas, top/bottom = párpados, iris = anillo refinado.
RIGHT_EYE = dict(a=33, b=133, top=159, bottom=145, iris=(469, 470, 471, 472),
                 ear=(33, 160, 158, 133, 153, 144))
LEFT_EYE = dict(a=362, b=263, top=386, bottom=374, iris=(474, 475, 476, 477),
                ear=(362, 385, 387, 263, 373, 380))

# Contornos para dibujar en la vista previa
RIGHT_EYE_CONTOUR = (33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7)
LEFT_EYE_CONTOUR = (362, 398, 384, 385, 386, 387, 388, 466, 263, 249, 390, 373, 374, 380, 381, 382)

FEATURE_NAMES = ("ix", "iy", "open", "yaw", "pitch", "roll", "cx", "cy", "scale")
N_FEATURES = len(FEATURE_NAMES)


@dataclass
class EyeMeasure:
    ix: float  # desplazamiento horizontal del iris / ancho del ojo
    iy: float  # desplazamiento vertical del iris / ancho del ojo
    open: float  # apertura de párpados / ancho del ojo
    ear: float  # eye aspect ratio (parpadeo)
    iris_center: np.ndarray  # píxeles
    iris_radius: float


@dataclass
class FaceFeatures:
    vector: np.ndarray  # (N_FEATURES,)
    ear: float
    right: EyeMeasure
    left: EyeMeasure
    landmarks_px: np.ndarray  # (478, 2)
    face_box: tuple[float, float, float, float]  # x, y, w, h en píxeles


def _measure_eye(pts: np.ndarray, eye: dict) -> EyeMeasure:
    a, b = pts[eye["a"]], pts[eye["b"]]
    origin = (a + b) / 2.0
    axis = b - a
    width = float(np.linalg.norm(axis)) or 1e-6
    ux = axis / width
    uy = np.array([-ux[1], ux[0]])  # perpendicular, apunta hacia abajo en la imagen

    ring = pts[list(eye["iris"])]
    iris = ring.mean(axis=0)
    radius = float(np.linalg.norm(ring - iris, axis=1).mean())
    rel = iris - origin

    lid = float(np.dot(pts[eye["bottom"]] - pts[eye["top"]], uy))
    p1, p2, p3, p4, p5, p6 = (pts[i] for i in eye["ear"])
    ear = (np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2.0 * np.linalg.norm(p1 - p4) + 1e-6)

    return EyeMeasure(
        ix=float(np.dot(rel, ux)) / width,
        iy=float(np.dot(rel, uy)) / width,
        open=lid / width,
        ear=float(ear),
        iris_center=iris,
        iris_radius=radius,
    )


def extract_features(
    landmarks: np.ndarray, width: int, height: int, pose: HeadPoseEstimator
) -> FaceFeatures:
    """`landmarks` es (478, 3) normalizado como lo entrega MediaPipe."""
    pts = landmarks[:, :2] * np.array([width, height], dtype=np.float64)
    right = _measure_eye(pts, RIGHT_EYE)
    left = _measure_eye(pts, LEFT_EYE)
    yaw, pitch, roll = pose.estimate(pts, width, height)

    lo, hi = pts.min(axis=0), pts.max(axis=0)
    inter_ocular = float(np.linalg.norm(pts[RIGHT_EYE["a"]] - pts[LEFT_EYE["b"]]))
    cx = (lo[0] + hi[0]) / 2.0 / width
    cy = (lo[1] + hi[1]) / 2.0 / height

    vector = np.array(
        [
            (right.ix + left.ix) / 2.0,
            (right.iy + left.iy) / 2.0,
            (right.open + left.open) / 2.0,
            yaw,
            pitch,
            roll,
            cx,
            cy,
            inter_ocular / width,
        ],
        dtype=np.float64,
    )
    return FaceFeatures(
        vector=vector,
        ear=(right.ear + left.ear) / 2.0,
        right=right,
        left=left,
        landmarks_px=pts,
        face_box=(float(lo[0]), float(lo[1]), float(hi[0] - lo[0]), float(hi[1] - lo[1])),
    )


class BlinkDetector:
    """Detecta parpadeos comparando el EAR con una línea base adaptativa."""

    def __init__(self, ratio: float = 0.62, history: int = 90):
        self.ratio = ratio
        self._history: list[float] = []
        self._size = history

    def update(self, ear: float) -> bool:
        baseline = float(np.median(self._history)) if len(self._history) >= 10 else None
        blinking = baseline is not None and ear < baseline * self.ratio
        if not blinking:
            self._history.append(ear)
            if len(self._history) > self._size:
                self._history.pop(0)
        return blinking
