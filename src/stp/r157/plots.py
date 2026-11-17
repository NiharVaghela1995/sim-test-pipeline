"""Figures for docs/R157_REPORT.md from results/r157 only (no simulation)."""
import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import norm
from ..cutin import gp as GP
from . import design as D, experiment as E

COL = {"gp_al": "#2a6fdb", "sobol": "#e08a00", "random": "#7a7a7a"}


def misclass_curves():
    rows = list(csv.DictReader(open(E.OUT / "metrics.csv")))
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for arm in E.ARMS:
        ns = sorted({int(r["n"]) for r in rows})
        v = np.array([[float(r["misclass"]) for r in rows if r["arm"] == arm and int(r["n"]) == n] for n in ns]) * 100
        ax.plot(ns, np.median(v, 1), color=COL[arm], label=arm.replace("_", "-"))
        ax.fill_between(ns, v.min(1), v.max(1), color=COL[arm], alpha=0.15)
    ax.axhline(float(rows[0]["const"]) * 100, color="k", ls="--", lw=1, label="constant (all pass)")
    ax.set_xlabel("esmini runs"); ax.set_ylabel("misclassified share of applicable region, %"); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(E.OUT / "fig_misclass_vs_budget.png", dpi=150)


def region_map(v_target=15.0):
    R = E.load_ref(); iv = int(np.argmin(np.abs(R["V"] - v_target))); v0 = R["V"][iv]
    rows = E.load_campaign("gp_al", 0); gpm = E.fit(rows, 0, E.BUDGET)
    vr = np.linspace(D.XL[1], D.XU[1], 151); tt = np.linspace(D.XL[2], D.XU[2], 141)
    VV, TT = np.meshgrid(vr, tt, indexing="ij")
    X = np.stack([np.full(VV.size, v0), VV.ravel(), TT.ravel()], 1)
    mu, sd = GP.predict(gpm, D.to_unit(X)); p = norm.cdf(mu / np.maximum(sd, 1e-12))
    reg = np.where(p >= E.HI, 1.0, np.where(p <= E.LO, -1.0, 0.0)); reg[~D.applicable(X)] = np.nan
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.pcolormesh(vr, tt, reg.reshape(VV.shape).T, cmap=matplotlib.colors.ListedColormap(["#c0392b", "#f1c40f", "#27ae60"]), vmin=-1, vmax=1, shading="nearest")
    B = E.boundary_points(R); B = B[np.isclose(B[:, 0], v0)]
    ax.plot(B[:, 1], B[:, 2], "ko", ms=4, label="true boundary (reference grid)")
    line = D.ttc_li_min(D.v_rel_at_ref(np.stack([np.full(len(vr), v0), vr, np.ones(len(vr))], 1)))
    ax.plot(vr, line, "k--", lw=1, label="applicability line (c)")
    ax.set_xlabel("v_rel (m/s)"); ax.set_ylabel("nominal TTC_LaneIntrusion (s)"); ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.set_title(f"ego {v0 * 3.6:.0f} km/h, GP-AL seed 0 at 300 runs: green compliant, red violating, yellow undecided", fontsize=8)
    fig.tight_layout(); fig.savefig(E.OUT / "fig_region_map.png", dpi=150)


if __name__ == "__main__":
    import sys
    (region_map if 'map' in sys.argv else (lambda: (misclass_curves(), region_map())))()
