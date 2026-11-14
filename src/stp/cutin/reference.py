"""Reference: dense grid over the box (docs/GP_BOUNDARY_PLAN.md, step 2), the reference boundary and its resolution check.

Grid: ego speed every 0.5 m/s (31), relative speed every 0.5 m/s (21), gap every 0.25 m (141). Stored as
results/gp_boundary/reference_grid.npz with margin[iv, idv, ig] and realised[iv, idv, ig]."""
import sys
from pathlib import Path
import numpy as np
from . import jobs, scenario as S

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/gp_boundary"
RAW = ROOT / "results/raw/gp_boundary"
V = np.round(np.arange(20.0, 35.0 + 1e-9, 0.5), 10)
DV = np.round(np.arange(-10.0, 0.0 + 1e-9, 0.5), 10)
G = np.round(np.arange(5.0, 40.0 + 1e-9, 0.25), 10)
REF_SEED = 0   # esmini seed for reference runs (it has no effect; tested)


def grid_points():
    """Grid points as an (N, 3) array in the order (ego_speed, rel_speed, gap) -> flattened [iv, idv, ig]."""
    vv, dd, gg = np.meshgrid(V, DV, G, indexing="ij")
    return np.stack([vv.ravel(), gg.ravel(), dd.ravel()], axis=1)     # columns in Params order: ego_speed, gap, rel_speed


def boundary_gap(margin_line, gaps=G):
    """Smallest gap above which every gap passes, with linear interpolation at the last sign change.
    40 if the largest gap fails, 5 if every gap passes. Works on any array whose last axis is gap."""
    m = np.asarray(margin_line)
    fail = m < 0
    out = np.full(m.shape[:-1], gaps[0], dtype=float)
    any_fail = fail.any(axis=-1)
    last = m.shape[-1] - 1 - np.argmax(fail[..., ::-1], axis=-1)    # index of the last failing gap
    for idx in zip(*np.nonzero(any_fail)):
        i = last[idx]; line = m[idx]
        if i == len(gaps) - 1:
            out[idx] = gaps[-1]
        else:
            a, b = line[i], line[i + 1]
            out[idx] = gaps[i] + (gaps[i + 1] - gaps[i]) * (-a) / (b - a)
    return out


def crossings(margin, gaps=G):
    """All sign changes along gap: list of (iv, idv, gap at crossing) by linear interpolation."""
    m = margin; s = m < 0
    iv, idv, ig = np.nonzero(s[..., :-1] != s[..., 1:])
    a, b = m[iv, idv, ig], m[iv, idv, ig + 1]
    gc = gaps[ig] + (gaps[ig + 1] - gaps[ig]) * (-a) / (b - a)
    return iv, idv, gc


def load():
    z = np.load(OUT / "reference_grid.npz")
    return dict(margin=z["margin"], realised=z["realised"], V=z["V"], DV=z["DV"], G=z["G"])


def build(workers=4):
    X = grid_points()
    items = [(i, tuple(x), REF_SEED) for i, x in enumerate(X)]
    rows = jobs.run_points(RAW, "reference", items, RAW / "reference.jsonl", workers)
    margin = np.array([rows[i]["margin"] for i in range(len(X))]).reshape(len(V), len(DV), len(G))
    realised = np.array([rows[i]["realised"] for i in range(len(X))]).reshape(margin.shape)
    collided = np.array([rows[i]["collided"] for i in range(len(X))]).reshape(margin.shape)
    overbrake = np.array([rows[i]["overbrake"] for i in range(len(X))]).reshape(margin.shape)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / "reference_grid.npz", margin=margin, realised=realised, collided=collided, overbrake=overbrake, V=V, DV=DV, G=G)
    bad = {}
    for r in rows.values():
        for k in r["bad"]: bad[k] = bad.get(k, 0) + 1
    print("runs", margin.size, "realised", int(realised.sum()), "gate failures", bad)
    print("fail share", float((margin < 0).mean()), "collided", int(collided.sum()), "overbrake", int(overbrake.sum()))


if __name__ == "__main__":
    build(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
