import json

import numpy as np
import pytest

from gazescope.core.calibration import (
    GazeModel,
    calibration_targets,
    evaluate,
    reject_outliers,
)
from gazescope.core.features import N_FEATURES
from gazescope.core.filters import OneEuroFilter2D
from gazescope.core.fixations import detect_fixations
from gazescope.core.heatmap import colorize, density_map, fog_image, heatmap_image, scanpath_image


# ------------------------------------------------------------------ filtros
def test_one_euro_reduces_jitter_but_follows_jumps():
    rng = np.random.default_rng(0)
    f = OneEuroFilter2D(min_cutoff=0.5, beta=0.0015)
    t = np.arange(0, 2, 1 / 30)
    raw = 500 + rng.normal(0, 15, len(t))
    out = np.array([f(x, 300, ti)[0] for x, ti in zip(raw, t)])
    assert np.std(out[15:]) < np.std(raw[15:]) / 2

    # Salto grande (sacada): debe alcanzarlo en pocos frames.
    vals = [f(1400, 300, 2 + i / 30)[0] for i in range(8)]
    assert vals[-1] > 1250


# --------------------------------------------------------------- fijaciones
def _trace(points, per_point=15, hz=30, noise=4.0, seed=1):
    rng = np.random.default_rng(seed)
    t, x, y = [], [], []
    for i, (px, py) in enumerate(points):
        for k in range(per_point):
            t.append((i * per_point + k) / hz)
            x.append(px + rng.normal(0, noise))
            y.append(py + rng.normal(0, noise))
    return np.array(t), np.array(x), np.array(y)


def test_ivt_finds_known_fixations():
    pts = [(200, 200), (900, 300), (1500, 800)]
    t, x, y = _trace(pts)
    fx = detect_fixations(t, x, y, px_per_deg=40)
    assert len(fx) == 3
    for f, (px, py) in zip(fx, pts):
        assert abs(f.x - px) < 10 and abs(f.y - py) < 10
        assert 0.4 < f.duration < 0.55


def test_ivt_drops_short_and_merges_gaps():
    t, x, y = _trace([(300, 300)], per_point=30)
    valid = np.ones(len(t), bool)
    valid[14] = False  # parpadeo de un frame
    fx = detect_fixations(t, x, y, valid=valid, px_per_deg=40)
    assert len(fx) == 1

    t2, x2, y2 = _trace([(300, 300), (1200, 300)], per_point=2)
    assert detect_fixations(t2, x2, y2, px_per_deg=40) == []


def test_ivt_splits_on_scene_change():
    t, x, y = _trace([(300, 300)], per_point=30)
    scene = np.array([0] * 15 + [1] * 15)
    fx = detect_fixations(t, x, y, scene=scene, px_per_deg=40)
    assert [f.scene_id for f in fx] == [0, 1]


# ---------------------------------------------------------------- heatmap
def test_density_peaks_at_points():
    d = density_map([(400, 300)] * 5 + [(1500, 900)], 1920, 1080, sigma_px=40)
    assert d.shape == (1080, 1920)
    assert d.max() == pytest.approx(1.0, abs=0.01)
    peak_y, peak_x = np.unravel_index(np.argmax(d), d.shape)
    assert abs(peak_x - 400) < 8 and abs(peak_y - 300) < 8
    assert d[900, 1500] < d[300, 400]


def test_visualizations_shapes():
    bg = np.full((360, 640, 3), 128, np.uint8)
    d = density_map([(320, 180)], 640, 360, sigma_px=20)
    rgba = colorize(d)
    assert rgba.shape == (360, 640, 4)
    assert rgba[0, 0, 3] == 0  # zonas frías transparentes
    assert heatmap_image(bg, d).shape == bg.shape
    fog = fog_image(bg, d)
    assert fog[180, 320].mean() > fog[0, 0].mean()

    class F:
        def __init__(self, x, y):
            self.x, self.y, self.duration = x, y, 0.3

    assert scanpath_image(bg, [F(100, 100), F(400, 200)]).shape == bg.shape


# ------------------------------------------------------------ calibración
def _synthetic_features(targets, n=30, seed=2, head_noise=True):
    """Modelo directo sintético: el iris se desplaza según el punto mirado."""
    rng = np.random.default_rng(seed)
    X, Y, G = [], [], []
    for g, (tx, ty) in enumerate(targets):
        for _ in range(n):
            yaw = rng.normal(0, 2.0) if head_noise else 0.0
            ix = -0.12 + 0.24 * tx - 0.004 * yaw + rng.normal(0, 0.004)
            iy = 0.02 + 0.06 * ty + 0.02 * ty**2 + rng.normal(0, 0.003)
            open_ = 0.30 + 0.05 * ty + rng.normal(0, 0.004)
            X.append([ix, iy, open_, yaw, 0.0, 0.0, 0.5, 0.5, 0.17])
            Y.append([tx, ty])
            G.append(g)
    return np.array(X), np.array(Y), np.array(G)


def test_gaze_model_recovers_mapping_and_roundtrips():
    targets = calibration_targets(13)
    assert len(targets) == 13
    X, Y, G = _synthetic_features(targets)
    assert X.shape[1] == N_FEATURES
    model = GazeModel.fit(X, Y, G)

    vt = [(0.5, 0.5), (0.2, 0.2), (0.8, 0.8)]
    Xv, _, Gv = _synthetic_features(vt, seed=9)
    samples = [Xv[Gv == g] for g in range(len(vt))]
    res = evaluate(model, samples, vt, 1920, 1080, px_per_deg=40)
    assert res.mean_error_px < 40, res.mean_error_px

    clone = GazeModel.from_dict(json.loads(json.dumps(model.to_dict())))
    np.testing.assert_allclose(clone.predict(X[:5]), model.predict(X[:5]))


def test_reject_outliers():
    rng = np.random.default_rng(3)
    s = np.column_stack([rng.normal(0, 0.01, (40, 2)), np.zeros((40, N_FEATURES - 2))])
    s[5, :2] = [0.5, 0.5]
    mask = reject_outliers(s)
    assert not mask[5] and mask.sum() >= 36
