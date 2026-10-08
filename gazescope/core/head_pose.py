"""Estimación de la pose de la cabeza a partir de landmarks de MediaPipe."""

from __future__ import annotations

import cv2
import numpy as np

# Índices de FaceMesh y su posición en un modelo 3D de cara genérico (mm aprox.)
POSE_LANDMARKS = (1, 152, 33, 263, 61, 291)
MODEL_POINTS = np.array(
    [
        (0.0, 0.0, 0.0),  # punta de la nariz
        (0.0, -330.0, -65.0),  # mentón
        (-225.0, 170.0, -135.0),  # esquina externa del ojo derecho
        (225.0, 170.0, -135.0),  # esquina externa del ojo izquierdo
        (-150.0, -150.0, -125.0),  # comisura derecha
        (150.0, -150.0, -125.0),  # comisura izquierda
    ],
    dtype=np.float64,
)


class HeadPoseEstimator:
    """solvePnP con la solución anterior como semilla para que sea estable."""

    def __init__(self) -> None:
        self._rvec: np.ndarray | None = None
        self._tvec: np.ndarray | None = None

    def reset(self) -> None:
        self._rvec = self._tvec = None

    def estimate(self, landmarks_px: np.ndarray, width: int, height: int) -> tuple[float, float, float]:
        """Devuelve (yaw, pitch, roll) en grados. `landmarks_px` es (N, 2) en píxeles."""
        image_points = landmarks_px[list(POSE_LANDMARKS)].astype(np.float64)
        focal = float(width)
        camera = np.array(
            [[focal, 0, width / 2.0], [0, focal, height / 2.0], [0, 0, 1]], dtype=np.float64
        )
        dist = np.zeros((4, 1))
        use_guess = self._rvec is not None
        ok, rvec, tvec = cv2.solvePnP(
            MODEL_POINTS,
            image_points,
            camera,
            dist,
            rvec=self._rvec.copy() if use_guess else None,
            tvec=self._tvec.copy() if use_guess else None,
            useExtrinsicGuess=use_guess,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            self.reset()
            return 0.0, 0.0, 0.0
        self._rvec, self._tvec = rvec, tvec
        rot, _ = cv2.Rodrigues(rvec)
        angles, *_ = cv2.RQDecomp3x3(rot)
        pitch, yaw, roll = angles
        # RQDecomp devuelve el pitch cerca de ±180 por la orientación del modelo
        if pitch > 90:
            pitch -= 180
        elif pitch < -90:
            pitch += 180
        return float(yaw), float(pitch), float(roll)
