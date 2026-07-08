"""Geometric morphometrics on approved gravestone outlines.

Method: each closed outline is resampled to N equally spaced points by arc
length (start point = topmost, clockwise direction — orientation is
meaningful for gravestones, so no rotation normalization), centered on its
centroid and scaled to unit centroid size. PCA over the flattened
coordinates gives a shape space; decade means and PC-axis extreme shapes are
reconstructed for visualization; nearest neighbors in PC space give
"similar shapes". Pure numpy — runs automatically at Export time."""
import re

import numpy as np

N_PTS = 64
MIN_SHAPES = 3
N_NEIGHBORS = 5
PC_KEEP = 5


def parse_path(d):
    pts = np.array(re.findall(r"(-?\d+\.?\d*),(-?\d+\.?\d*)", d),
                   dtype=float)
    return pts if len(pts) >= 3 else None


def resample(pts, n=N_PTS):
    # ensure clockwise (positive signed area in y-down coords)
    area = np.sum(pts[:, 0] * np.roll(pts[:, 1], -1)
                  - np.roll(pts[:, 0], -1) * pts[:, 1])
    if area < 0:
        pts = pts[::-1]
    # start at topmost point (smallest y)
    pts = np.roll(pts, -int(np.argmin(pts[:, 1])), axis=0)
    closed = np.vstack([pts, pts[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    if total <= 0:
        return None
    targets = np.linspace(0, total, n, endpoint=False)
    out = np.empty((n, 2))
    for i, t in enumerate(targets):
        j = np.searchsorted(cum, t, side="right") - 1
        j = min(j, len(seg) - 1)
        f = (t - cum[j]) / max(seg[j], 1e-9)
        out[i] = closed[j] * (1 - f) + closed[j + 1] * f
    return out


def normalize(pts):
    pts = pts - pts.mean(axis=0)
    size = np.sqrt((pts ** 2).sum(axis=1).mean())
    return pts / max(size, 1e-9)


def to_display(pts):
    """Rescale a normalized shape to a width-100 box for SVG rendering."""
    p = pts - pts.min(axis=0)
    w = max(p[:, 0].max(), 1e-9)
    p = p * (100.0 / w)
    return [[round(float(x), 1), round(float(y), 1)] for x, y in p]


def analyze(outlines, years):
    """outlines: {stone_id: svg_path_d}; years: {stone_id: year_or_None}.
    Returns the morpho dict for morpho.json, or None if too few shapes."""
    ids, rows = [], []
    for sid, d in outlines.items():
        pts = parse_path(d)
        if pts is None:
            continue
        r = resample(pts)
        if r is None:
            continue
        ids.append(sid)
        rows.append(normalize(r).flatten())
    if len(ids) < MIN_SHAPES:
        return None
    X = np.array(rows)
    mean = X.mean(axis=0)
    Xc = X - mean
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    k = min(PC_KEEP, len(S))
    scores = Xc @ Vt[:k].T
    var = S ** 2
    expl = (var / var.sum())[:k]

    # decade mean shapes
    decades = {}
    for i, sid in enumerate(ids):
        y = years.get(sid)
        if y:
            decades.setdefault(int(y) // 10 * 10, []).append(i)
    decade_means = {
        str(dec): to_display(X[idx].mean(axis=0).reshape(-1, 2))
        for dec, idx in sorted(decades.items()) if len(idx) >= 1}

    # PC axis extremes (mean ± 2 sd) for interpreting the scatter
    axes = []
    for i in range(min(2, k)):
        sd = scores[:, i].std()
        axes.append({
            "explained": round(float(expl[i]) * 100, 1),
            "minus": to_display((mean - 2 * sd * Vt[i]).reshape(-1, 2)),
            "plus": to_display((mean + 2 * sd * Vt[i]).reshape(-1, 2)),
        })

    # per-stone: full PC scores (for client-side similarity ranking) and the
    # resampled 64-point outline (for morphing between any two stones)
    stones = {}
    for i, sid in enumerate(ids):
        stones[str(sid)] = {
            "s": [round(float(v), 3) for v in scores[i]],
            "p": to_display(X[i].reshape(-1, 2)),
        }

    return {
        "n": len(ids),
        "stones": stones,
        "axes": axes,
        "decadeMeans": decade_means,
        "meanShape": to_display(mean.reshape(-1, 2)),
    }
