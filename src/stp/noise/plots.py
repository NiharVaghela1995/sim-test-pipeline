"""Figures for docs/NOISE_REPORT.md from results/noise only (no simulation).

  PYTHONPATH=src .venv/bin/python -m stp.noise.plots
"""
import csv
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import experiment as E, surrogates as M

# fixed categorical order (one hue per arm, never re-assigned), line style as a second cue
COL = {"het_al": "#2a78d6", "hom_al": "#eb6834", "sobol": "#1baf7a", "random": "#eda100"}
LS = {"het_al": "-", "hom_al": "--", "sobol": "-.", "random": ":"}
NAME = {"het_al": "het-GP AL", "hom_al": "hom-GP AL", "sobol": "Sobol + hom-GP", "random": "random + hom-GP"}
INK, MUTED = "#222222", "#777777"


def _style(ax):
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelcolor=INK, labelsize=8); ax.grid(axis="y", color="#e6e6e6", lw=0.6); ax.set_axisbelow(True)


def curves(metric="misclass", fname="fig_misclass_vs_budget.png", ylabel="misclassified share of the region, %", scale=100):
    rows = list(csv.DictReader(open(E.OUT / "metrics.csv")))
    fig, axs = plt.subplots(1, len(E.LEVELS), figsize=(10, 3.4), squeeze=False); axs = axs[0]
    for ax, lv in zip(axs, E.LEVELS):
        for arm in E.ARMS:
            rr = [r for r in rows if r["level"] == lv and r["arm"] == arm and r["model"] == E.MODEL_OF[arm]]
            ns = sorted({int(r["n"]) for r in rr})
            v = np.array([[float(r[metric]) for r in rr if int(r["n"]) == n] for n in ns]) * scale
            ax.plot(ns, np.median(v, 1), color=COL[arm], ls=LS[arm], lw=2, label=NAME[arm])
            ax.fill_between(ns, np.quantile(v, 0.25, 1), np.quantile(v, 0.75, 1), color=COL[arm], alpha=0.12, lw=0)
        if metric == "misclass":
            c = float(next(r["const"] for r in rows if r["level"] == lv)) * scale
            ax.axhline(c, color=MUTED, ls=(0, (4, 3)), lw=1); ax.text(max(ns), c, "constant (nothing in region) ", ha="right", va="bottom", fontsize=7, color=MUTED)
        lvl = E.LEVELS[lv]
        ax.set_title(f"{lv}: σx {lvl.sigma_x} m, σv {lvl.sigma_v} m/s, delay {lvl.delay} s", fontsize=9, color=INK)
        ax.set_xlabel("runs (budget)", fontsize=8, color=INK); _style(ax); ax.set_ylim(bottom=0)
    axs[0].set_ylabel(ylabel, fontsize=8, color=INK)
    axs[-1].legend(frameon=False, fontsize=7, loc="center right")
    fig.text(0.01, 0.01, "median over 10 seeds; band: interquartile range", fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(E.OUT / fname, dpi=150); plt.close(fig)


def reference_maps(v_index=2):
    """Per level, at one ego speed: reference p_iso (sequential, one hue) with the p = ALPHA contour, and the margin SD."""
    fig, axs = plt.subplots(2, len(E.LEVELS), figsize=(10, 5.6), sharex=True, sharey=True, squeeze=False)
    for k, lv in enumerate(E.LEVELS):
        R = E.load_ref(lv); ok = R["applicable"][v_index] & (R["realised"][v_index] >= E.MIN_REAL_TRUTH)
        p = np.where(ok, R["p_iso"][v_index], np.nan); sd = np.where(ok & (R["realised"][v_index] >= 2), R["sd"][v_index], np.nan)
        a = axs[0, k].pcolormesh(R["VR"], R["T"], p.T, cmap="Blues", vmin=0, vmax=1, shading="nearest")
        okall = R["applicable"] & (R["realised"] >= E.MIN_REAL_TRUTH)
        bl, has = E.line_boundary(np.where(okall, R["p_iso"] >= M.ALPHA, False), okall)
        axs[0, k].plot(R["VR"][has[v_index]], bl[v_index][has[v_index]], "o-", color=INK, ms=3, lw=1, label=f"end of p ≥ {M.ALPHA} region")
        b = axs[1, k].pcolormesh(R["VR"], R["T"], sd.T, cmap="Oranges", vmin=0, vmax=1.0, shading="nearest")
        axs[0, k].set_title(f"{lv}: p(x); dots: end of p ≥ {M.ALPHA}", fontsize=9, color=INK); axs[1, k].set_title(f"{lv}: margin SD (m)", fontsize=9, color=INK)
        for ax in axs[:, k]: _style(ax); ax.grid(False); ax.set_ylim(0.2, 2.0); ax.set_xlim(0.4, 4.0)
        axs[1, k].set_xlabel("v_rel (m/s)", fontsize=8)
    for ax in axs[:, 0]: ax.set_ylabel("nominal TTC_LaneIntrusion (s)", fontsize=8)
    fig.colorbar(a, ax=axs[0].tolist(), shrink=0.8, label="p(x)"); fig.colorbar(b, ax=axs[1].tolist(), shrink=0.8, label="SD (m)")
    fig.suptitle(f"reference, ego {E.V[v_index] * 3.6:.0f} km/h (zoom: v_rel ≤ 4 m/s, TTC ≤ 2 s; white: not applicable or no truth)", fontsize=9, color=INK)
    fig.savefig(E.OUT / "fig_reference_maps.png", dpi=150); plt.close(fig)


def reruns_fig():
    s = json.load(open(E.OUT / "reruns.json"))
    bands = [b[0] for b in E.BANDS]
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.4), sharey=True)
    w = 0.25
    for j, (key, title) in enumerate((("sprt_attempts_median_p90", "binary SPRT (pass/fail only)"), ("qrule_attempts_median_p90", "margin quantile rule"))):
        ax = axs[j]
        for k, lv in enumerate(E.LEVELS):
            bb = s[lv]["bands"]; x = np.arange(len(bands)) + (k - 1) * w
            med = [bb[b][key][0] if b in bb else np.nan for b in bands]; p90 = [bb[b][key][1] if b in bb else np.nan for b in bands]
            ax.bar(x, med, w * 0.9, color=["#9ec5f4", "#3987e5", "#184f95"][k % 3], label=lv)
            ax.errorbar(x, med, yerr=[np.zeros(len(med)), np.array(p90) - np.array(med)], fmt="none", ecolor=MUTED, lw=1, capsize=2)
        ax.set_xticks(np.arange(len(bands))); ax.set_xticklabels([b.split(" (")[0] for b in bands], fontsize=7, rotation=15)
        ax.set_title(title, fontsize=9, color=INK); _style(ax); ax.set_xlabel("reference p(x)", fontsize=8)
    axs[0].set_ylabel("runs per verdict (median; whisker to 90th pct.)", fontsize=8); axs[1].legend(frameon=False, fontsize=7, title="level", title_fontsize=7)
    fig.tight_layout(); fig.savefig(E.OUT / "fig_reruns.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    curves(); curves("boundary_err", "fig_boundary_err.png", "boundary error, s of TTC", 1)
    curves("no_verdict", "fig_no_verdict.png", "no-verdict share of runs, %", 100)
    reference_maps(); reruns_fig()
