"""Mapas de calor, scanpaths y "fog" a partir de puntos de mirada o fijaciones."""

from __future__ import annotations

from typing import Iterable, Sequence

import cv2
import numpy as np

CV_COLORMAPS = {
    "turbo": cv2.COLORMAP_TURBO,
    "inferno": cv2.COLORMAP_INFERNO,
    "magma": cv2.COLORMAP_MAGMA,
    "jet": cv2.COLORMAP_JET,
    "viridis": cv2.COLORMAP_VIRIDIS,
}


class HeatmapAccumulator:
    """Acumula impulsos en una grilla reducida y la difumina al renderizar.

    Trabajar a 1/`scale` de la resolución hace que el mapa en vivo cueste muy
    poco aunque la pantalla sea grande.
    """

    def __init__(self, width: int, height: int, sigma_px: float = 40.0, scale: int = 4):
        self.width, self.height, self.scale = width, height, scale
        self.sigma_px = sigma_px
        self.grid = np.zeros((max(1, height // scale), max(1, width // scale)), np.float32)

    def clear(self) -> None:
        self.grid.fill(0.0)

    def add(self, x: float, y: float, weight: float = 1.0) -> None:
        gx, gy = int(x / self.scale), int(y / self.scale)
        if 0 <= gx < self.grid.shape[1] and 0 <= gy < self.grid.shape[0]:
            self.grid[gy, gx] += weight

    def density(self, full_size: bool = False) -> np.ndarray:
        """Densidad normalizada 0..1."""
        sigma = max(self.sigma_px / self.scale, 1.0)
        d = cv2.GaussianBlur(self.grid, (0, 0), sigma)
        peak = float(d.max())
        if peak > 0:
            d /= peak
        if full_size:
            d = cv2.resize(d, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        return d


def density_map(
    points: Iterable[Sequence[float]],
    width: int,
    height: int,
    sigma_px: float = 40.0,
    weights: Iterable[float] | None = None,
    scale: int = 4,
) -> np.ndarray:
    acc = HeatmapAccumulator(width, height, sigma_px, scale)
    points = list(points)
    weights = [1.0] * len(points) if weights is None else list(weights)
    for (x, y), w in zip(points, weights):
        acc.add(x, y, w)
    return acc.density(full_size=True)


def colorize(density: np.ndarray, colormap: str = "turbo", max_alpha: float = 0.75,
             floor: float = 0.04) -> np.ndarray:
    """Devuelve BGRA uint8: las zonas frías quedan transparentes."""
    d = np.clip(density, 0.0, 1.0)
    # Se salta el extremo más oscuro del colormap: sobre una captura se ve sucio.
    idx = (40 + d * 215).astype(np.uint8)
    color = cv2.applyColorMap(idx, CV_COLORMAPS.get(colormap, cv2.COLORMAP_TURBO))
    alpha = np.where(d < floor, 0.0, np.power(d, 0.55) * max_alpha)
    return np.dstack([color, (alpha * 255).astype(np.uint8)])


def blend(background_bgr: np.ndarray, overlay_bgra: np.ndarray) -> np.ndarray:
    if overlay_bgra.shape[:2] != background_bgr.shape[:2]:
        overlay_bgra = cv2.resize(overlay_bgra, (background_bgr.shape[1], background_bgr.shape[0]))
    a = overlay_bgra[..., 3:4].astype(np.float32) / 255.0
    out = background_bgr.astype(np.float32) * (1 - a) + overlay_bgra[..., :3].astype(np.float32) * a
    return out.astype(np.uint8)


def heatmap_image(background_bgr: np.ndarray, density: np.ndarray, colormap: str = "turbo",
                  dim: float = 0.25) -> np.ndarray:
    """Captura (ligeramente oscurecida) + mapa de calor encima."""
    bg = background_bgr
    if dim > 0:
        bg = (bg.astype(np.float32) * (1.0 - dim)).astype(np.uint8)
    return blend(bg, colorize(density, colormap))


def fog_image(background_bgr: np.ndarray, density: np.ndarray, gain: float = 2.5,
              floor: float = 0.08) -> np.ndarray:
    """Oscurece todo lo que no fue mirado: revela solo las zonas con atención."""
    if density.shape[:2] != background_bgr.shape[:2]:
        density = cv2.resize(density, (background_bgr.shape[1], background_bgr.shape[0]))
    reveal = np.clip(density * gain, 0.0, 1.0)
    reveal = floor + (1.0 - floor) * reveal
    return (background_bgr.astype(np.float32) * reveal[..., None]).astype(np.uint8)


def scanpath_image(background_bgr: np.ndarray, fixations: Sequence, color=(255, 200, 40),
                   dim: float = 0.45, max_points: int = 120) -> np.ndarray:
    """Fijaciones numeradas unidas por sacadas; el radio crece con la duración."""
    img = (background_bgr.astype(np.float32) * (1.0 - dim)).astype(np.uint8)
    fx = list(fixations)[:max_points]
    if not fx:
        return img
    h = img.shape[0]
    unit = max(h / 1080.0, 0.5)
    pts = [(int(f.x), int(f.y)) for f in fx]
    for a, b in zip(pts, pts[1:]):
        cv2.line(img, a, b, (245, 245, 245), max(1, int(3 * unit)), cv2.LINE_AA)
    layer = img.copy()
    radii = []
    for f, p in zip(fx, pts):
        r = int((24 + min(f.duration, 2.0) * 40) * unit)
        radii.append(r)
        cv2.circle(layer, p, r, color, -1, cv2.LINE_AA)
    img = cv2.addWeighted(layer, 0.55, img, 0.45, 0)
    for i, (p, r) in enumerate(zip(pts, radii), start=1):
        cv2.circle(img, p, r, (255, 255, 255), max(1, int(3 * unit)), cv2.LINE_AA)
        label = str(i)
        fs = 1.0 * unit
        thick = max(1, int(2 * unit))
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, fs, thick)
        cv2.putText(img, label, (p[0] - tw // 2, p[1] + th // 2), cv2.FONT_HERSHEY_DUPLEX, fs,
                    (25, 20, 15), thick, cv2.LINE_AA)
    return img
