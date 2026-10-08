"""Modelo de mapeo características → pantalla, validación y perfiles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from ..config import PROFILES_DIR
from .features import N_FEATURES

N_EYE = 3  # ix, iy, open → expansión polinómica de grado 2
# Escalas fijas para la pose de cabeza (yaw, pitch, roll en grados; cx, cy, scale
# en fracción de imagen). No se estandarizan con la varianza de la calibración
# porque suele ser diminuta y amplificaría ruido.
HEAD_SCALE = np.array([10.0, 10.0, 10.0, 0.1, 0.1, 0.03])
ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0)


def calibration_targets(n: int = 13, margin: float = 0.08) -> list[tuple[float, float]]:
    """Puntos de calibración en coordenadas normalizadas (0..1)."""
    lo, hi = margin, 1.0 - margin
    grid = [(x, y) for y in (lo, 0.5, hi) for x in (lo, 0.5, hi)]
    if n <= 9:
        return grid
    inner = [(0.29, 0.29), (0.71, 0.29), (0.29, 0.71), (0.71, 0.71)]
    extra = [(0.5, 0.29), (0.29, 0.5), (0.71, 0.5), (0.5, 0.71)]
    return grid + (inner + extra)[: n - 9]


VALIDATION_TARGETS = [(0.5, 0.5), (0.2, 0.2), (0.8, 0.2), (0.2, 0.8), (0.8, 0.8)]


def reject_outliers(samples: np.ndarray, k: float = 3.0) -> np.ndarray:
    """Máscara de muestras cuyo iris no se aleja más de k·MAD de la mediana."""
    if len(samples) < 5:
        return np.ones(len(samples), dtype=bool)
    eye = samples[:, :2]
    med = np.median(eye, axis=0)
    mad = np.median(np.abs(eye - med), axis=0) * 1.4826 + 1e-9
    return np.all(np.abs(eye - med) <= k * mad, axis=1)


@dataclass
class GazeModel:
    mean: np.ndarray
    std: np.ndarray
    coef: np.ndarray  # (n_terms, 2)
    intercept: np.ndarray  # (2,)
    alpha: float
    offset: np.ndarray = field(default_factory=lambda: np.zeros(2))
    cv_error: float = 0.0  # error medio de validación cruzada (normalizado)

    # ---------------------------------------------------------------- diseño
    @staticmethod
    def design(X: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
        X = np.atleast_2d(X)
        eye = (X[:, :N_EYE] - mean[:N_EYE]) / std[:N_EYE]
        quad = [eye[:, i] * eye[:, j] for i in range(N_EYE) for j in range(i, N_EYE)]
        head = (X[:, N_EYE:] - mean[N_EYE:]) / HEAD_SCALE
        return np.column_stack([eye, *quad, head])

    @staticmethod
    def _ridge(D: np.ndarray, Y: np.ndarray, alpha: float) -> tuple[np.ndarray, np.ndarray]:
        dm, ym = D.mean(axis=0), Y.mean(axis=0)
        Dc, Yc = D - dm, Y - ym
        A = Dc.T @ Dc + alpha * len(D) * 1e-2 * np.eye(D.shape[1])
        coef = np.linalg.solve(A, Dc.T @ Yc)
        return coef, ym - dm @ coef

    # ------------------------------------------------------------ ajuste
    @classmethod
    def fit(cls, X: np.ndarray, Y: np.ndarray, groups: np.ndarray) -> "GazeModel":
        """X: (n, N_FEATURES) · Y: (n, 2) normalizado · groups: id de punto por muestra."""
        X, Y, groups = np.asarray(X, float), np.asarray(Y, float), np.asarray(groups)
        if X.shape[1] != N_FEATURES:
            raise ValueError(f"Se esperaban {N_FEATURES} características, llegaron {X.shape[1]}")
        mean = X.mean(axis=0)
        std = X.std(axis=0) + 1e-9
        D = cls.design(X, mean, std)

        best_alpha, best_err = ALPHAS[-1], np.inf
        unique = np.unique(groups)
        if len(unique) >= 5:
            for alpha in ALPHAS:
                errs = []
                for g in unique:
                    train, test = groups != g, groups == g
                    coef, icpt = cls._ridge(D[train], Y[train], alpha)
                    pred = (D[test] @ coef + icpt).mean(axis=0)
                    errs.append(np.linalg.norm(pred - Y[test].mean(axis=0)))
                err = float(np.mean(errs))
                if err < best_err:
                    best_alpha, best_err = alpha, err
        coef, icpt = cls._ridge(D, Y, best_alpha)
        return cls(mean, std, coef, icpt, best_alpha, cv_error=0.0 if np.isinf(best_err) else best_err)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Devuelve coordenadas normalizadas (n, 2) o (2,) para un único vector."""
        single = np.ndim(X) == 1
        out = self.design(X, self.mean, self.std) @ self.coef + self.intercept + self.offset
        return out[0] if single else out

    # ------------------------------------------------------- serialización
    def to_dict(self) -> dict:
        return {
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "coef": self.coef.tolist(),
            "intercept": self.intercept.tolist(),
            "alpha": self.alpha,
            "offset": self.offset.tolist(),
            "cv_error": self.cv_error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GazeModel":
        return cls(
            mean=np.array(d["mean"]),
            std=np.array(d["std"]),
            coef=np.array(d["coef"]),
            intercept=np.array(d["intercept"]),
            alpha=float(d["alpha"]),
            offset=np.array(d.get("offset", [0.0, 0.0])),
            cv_error=float(d.get("cv_error", 0.0)),
        )


# ---------------------------------------------------------------- validación
@dataclass
class ValidationResult:
    targets_px: list[tuple[float, float]]
    predicted_px: list[tuple[float, float]]
    errors_px: list[float]
    mean_error_px: float
    mean_error_deg: float
    precision_px: float  # RMS muestra a muestra

    @property
    def grade(self) -> str:
        d = self.mean_error_deg
        if d <= 2.0:
            return "Excelente"
        if d <= 3.5:
            return "Buena"
        if d <= 5.0:
            return "Regular"
        return "Repetir"

    def to_dict(self) -> dict:
        return {
            "targets_px": self.targets_px,
            "predicted_px": self.predicted_px,
            "errors_px": self.errors_px,
            "mean_error_px": self.mean_error_px,
            "mean_error_deg": self.mean_error_deg,
            "precision_px": self.precision_px,
            "grade": self.grade,
        }


def evaluate(
    model: GazeModel,
    samples: list[np.ndarray],
    targets: list[tuple[float, float]],
    width: int,
    height: int,
    px_per_deg: float,
) -> ValidationResult:
    scale = np.array([width, height], dtype=float)
    tgt_px, pred_px, errors, precisions = [], [], [], []
    for feats, target in zip(samples, targets):
        t = np.array(target) * scale
        tgt_px.append((float(t[0]), float(t[1])))
        if len(feats) == 0:
            pred_px.append((float("nan"), float("nan")))
            continue
        pred = model.predict(np.asarray(feats)) * scale
        center = pred.mean(axis=0)
        pred_px.append((float(center[0]), float(center[1])))
        errors.append(float(np.linalg.norm(center - t)))
        if len(pred) > 1:
            steps = np.diff(pred, axis=0)
            precisions.append(float(np.sqrt(np.mean(np.sum(steps**2, axis=1)))))
    mean_px = float(np.mean(errors)) if errors else float("inf")
    return ValidationResult(
        targets_px=tgt_px,
        predicted_px=pred_px,
        errors_px=errors,
        mean_error_px=mean_px,
        mean_error_deg=mean_px / px_per_deg,
        precision_px=float(np.mean(precisions)) if precisions else 0.0,
    )


# ------------------------------------------------------------------ perfiles
@dataclass
class Profile:
    name: str
    model: GazeModel
    validation: dict
    created: str
    monitor: dict

    @property
    def path(self) -> Path:
        return profile_path(self.name)

    def save(self) -> Path:
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "name": self.name,
            "created": self.created,
            "monitor": self.monitor,
            "validation": self.validation,
            "model": self.model.to_dict(),
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return self.path

    @classmethod
    def load(cls, name: str) -> "Profile":
        data = json.loads(profile_path(name).read_text(encoding="utf-8"))
        return cls(
            name=data["name"],
            model=GazeModel.from_dict(data["model"]),
            validation=data.get("validation", {}),
            created=data.get("created", ""),
            monitor=data.get("monitor", {}),
        )

    @classmethod
    def new(cls, name: str, model: GazeModel, validation: ValidationResult, monitor: dict) -> "Profile":
        return cls(name, model, validation.to_dict(), datetime.now().isoformat(timespec="seconds"), monitor)


def _slug(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", name.strip()) or "perfil"


def profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{_slug(name)}.json"


def list_profiles() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    names = []
    for p in sorted(PROFILES_DIR.glob("*.json")):
        try:
            names.append(json.loads(p.read_text(encoding="utf-8"))["name"])
        except (OSError, ValueError, KeyError):
            continue
    return names
