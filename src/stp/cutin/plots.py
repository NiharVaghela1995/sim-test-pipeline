"""Figures for docs/GP_BOUNDARY_REPORT.md. Reads summary.json, metrics.csv, the reference grid and the campaign runs.

  python -m stp.cutin.plots
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from . import gp as GP, reference as REF, campaign as C, metrics as M

SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COL = {"gp_al": "#2a78d6", "sobol": "#eb6834", "random": "#1baf7a"}      # categorical slots 1-3, fixed order
NAME = {"gp_al": "GP-AL", "sobol": "Sobol + GP", "random": "Random + GP"}
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": INK2, "axes.labelcolor": INK, "text.color": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "lines.linewidth": 2})


def boundary_map(seed=0, n=300, speeds=(20.0, 27.5, 35.0)):
    r = REF.load(); rows = C.run_campaign("gp_al", seed)[:n]; g = C.model_at(rows, seed, n)
    X = np.array([q["x"] for q in rows]); m = np.array([q["margin"] for q in rows])
    fig, axs = plt.subplots(1, len(speeds), figsize=(12, 4.8), sharey=True)
    for ax, v in zip(axs, speeds):
        iv = int(np.argmin(np.abs(r["V"] - v)))
        ref = r["margin"][iv]                                   # [idv, ig]
        gg, dd = np.meshgrid(r["G"], r["DV"])
        U = GP.to_unit(np.stack([np.full(gg.size, v), gg.ravel(), dd.ravel()], 1)); mu, sd = GP.predict(g, U)
        mu, sd = mu.reshape(gg.shape), sd.reshape(gg.shape)
        ax.contourf(gg, dd, (ref < 0).astype(float), levels=[0.5, 1.5], colors=["#e8e7e3"])
        ax.contourf(gg, dd, (np.abs(mu) <= 1.96 * sd).astype(float), levels=[0.5, 1.5], colors=[COL["gp_al"]], alpha=0.22)
        ax.contour(gg, dd, ref, levels=[0], colors=[INK], linewidths=1.6)
        ax.contour(gg, dd, mu, levels=[0], colors=[COL["gp_al"]], linewidths=2, linestyles="--")
        near = np.abs(X[:, 0] - v) <= 1.25
        ax.scatter(X[near & (m >= 0), 1], X[near & (m >= 0), 2], s=22, facecolors="none", edgecolors=INK2, linewidths=1, zorder=3)
        ax.scatter(X[near & (m < 0), 1], X[near & (m < 0), 2], s=22, c=INK2, edgecolors=SURF, linewidths=1, zorder=3)
        ax.set_title(f"ego speed {v:g} m/s", fontsize=10, color=INK); ax.set_xlabel("gap at cut-in (m)")
        ax.set_xlim(5, 40); ax.set_ylim(-10, 0)
    axs[0].set_ylabel("relative speed of cutting car (m/s)")
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    h = [Patch(color="#e8e7e3", label="fails rule (reference)"), Line2D([], [], color=INK, lw=1.6, label="reference boundary"),
         Line2D([], [], color=COL["gp_al"], lw=2, ls="--", label=f"GP-AL boundary, seed {seed}, {n} runs"),
         Patch(color=COL["gp_al"], alpha=0.22, label="GP 95% band"),
         Line2D([], [], ls="", marker="o", mfc="none", mec=INK2, label="run within ±1.25 m/s: pass"),
         Line2D([], [], ls="", marker="o", mfc=INK2, mec=SURF, label="run: fail")]
    fig.legend(handles=h, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle("Where the ACC holds min TTC ≥ 1.5 s: reference and GP-AL estimate", x=0.01, ha="left", fontsize=12)
    fig.tight_layout(rect=(0, 0.14, 1, 0.95)); fig.savefig(C.OUT / "fig_boundary_map.png", dpi=150); plt.close(fig)


def vs_budget(S, key, fname, ylabel, title, log=True, target=None):
    cur = S[key]; fig, ax = plt.subplots(figsize=(7.5, 5.2))
    ns = np.array(M.CHECKPOINTS)
    for arm in C.ARMS:
        c = cur[f"{arm}/gp"]; med = np.array([c[str(n)]["median"] for n in ns])
        lo = np.array([c[str(n)]["min"] for n in ns]); hi = np.array([c[str(n)]["max"] for n in ns])
        ax.fill_between(ns, lo, hi, color=COL[arm], alpha=0.13, linewidth=0)
        ax.plot(ns, med, color=COL[arm], label=f"{NAME[arm]} (median, range over 10 seeds)")
        ax.annotate(NAME[arm], (ns[-1], med[-1]), xytext=(6, 0), textcoords="offset points", va="center", color=INK, fontsize=9)
    c = cur["sobol/1nn"]; ax.plot(ns, [c[str(n)]["median"] for n in ns], color=INK2, lw=1.2, ls=":", label="Sobol + 1-NN (no GP), median")
    if target is not None:
        ax.axhline(target, color=INK2, lw=0.8, ls="--"); ax.annotate(f"target {target:g}", (ns[0], target), xytext=(2, 3), textcoords="offset points", fontsize=8, color=INK2)
    for b in (100, 200, 300): ax.axvline(b, color=GRID, lw=1, zorder=0)
    if log: ax.set_yscale("log")
    ax.set_xlabel("esmini runs"); ax.set_ylabel(ylabel); ax.set_xlim(40, 330); ax.set_title(title, loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2); fig.tight_layout(); fig.savefig(C.OUT / fname, dpi=150); plt.close(fig)


def calibration_plot(S):
    fig, ax = plt.subplots(figsize=(5.2, 4.6)); q = np.array(M.LEVELS)
    ax.plot([0.45, 1], [0.45, 1], color=INK2, lw=1, ls="--"); ax.annotate("honest band", (0.62, 0.64), rotation=38, fontsize=8, color=INK2)
    for k, arm in enumerate(C.ARMS):
        d = S["calibration"][arm]; mean = np.array([d[str(x)]["mean"] for x in q])
        lo = mean - np.array([d[str(x)]["min"] for x in q]); hi = np.array([d[str(x)]["max"] for x in q]) - mean
        off = (k - 1) * 0.006
        ax.errorbar(q + off, mean, yerr=[lo, hi], color=COL[arm], marker="o", ms=6, lw=2, capsize=0, label=NAME[arm])
    ax.set_xlabel("stated band level"); ax.set_ylabel("share of reference boundary points inside the band")
    ax.set_xlim(0.45, 1.02); ax.set_ylim(0, 1.02); ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.set_title("Band calibration at 300 runs (mean, range over 10 seeds)", loc="left", fontsize=10)
    fig.tight_layout(); fig.savefig(C.OUT / "fig_calibration.png", dpi=150); plt.close(fig)


def main():
    S = json.loads((C.OUT / "summary.json").read_text())
    boundary_map()
    vs_budget(S, "misclass_curves", "fig_misclass_vs_budget.png", "misclassified share of the box", "Misclassification against budget", target=0.02)
    vs_budget(S, "berr_curves", "fig_boundary_error_vs_budget.png", "mean |critical gap error| (m)", "Boundary error against budget", target=1.0)
    calibration_plot(S)


if __name__ == "__main__":
    main()
