"""Figures for docs/REPORT.md, from results/summary.json. Usage: python -m stp.plots"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

ROOT = Path(__file__).resolve().parents[2]
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e5e0"
LEVELS = ("low", "medium", "high")
plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": GRID, "xtick.color": MUTED, "ytick.color": MUTED, "axes.labelcolor": MUTED, "text.color": INK, "axes.titlesize": 13, "svg.fonttype": "none", "figure.facecolor": "none", "axes.facecolor": "none"})


def active(S): return [l for l in LEVELS if S[l]["reported_failures"] > 0]


def note(fig, S):
    skip = [l for l in LEVELS if S[l]["reported_failures"] == 0]
    if skip: fig.text(0.99, 0.015, f"Not shown: {', '.join(skip)} noise, no reported failures in {S[skip[0]]['evaluations']:,} runs.", fontsize=10, color=MUTED, ha="right")


def style(ax, axis="y"):
    ax.grid(axis=axis, color=GRID, lw=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)


def repro(S, out):
    A = active(S); fig, axs = plt.subplots(1, len(A), figsize=(9, 3.9), sharey=True)
    for ax, l in zip(axs, A):
        h = np.array(S[l]["reproduction"]["hist"], float); h = 100 * h / max(h.sum(), 1)
        ax.bar(np.arange(10) / 10 + 0.05, h, width=0.085, color=BLUE); ax.set_title(f"{l} noise, {S[l]['reported_failures']} failures"); ax.set_xlabel("Share of 20 reruns that failed"); ax.set_xlim(0, 1); style(ax)
    axs[0].set_ylabel("% of reported failures"); fig.tight_layout(rect=(0, .05, 1, 1)); note(fig, S); fig.savefig(out / "reproduction_rates.svg"); plt.close(fig)


def search(S, out):
    M = [("reported", "Reported failures"), ("confirmed", "Failures reproducing\nin at least half of reruns"), ("cells", "Distinct input cells\nwith such a failure")]
    A = active(S); fig, axs = plt.subplots(3, len(A), figsize=(8.5, 8))
    rng = np.random.default_rng(1)
    for i, (k, lab) in enumerate(M):
        for j, l in enumerate(A):
            ax = axs[i][j]; style(ax)
            for x, arm, c, nm in ((0, "nsga2", BLUE, "NSGA-II"), (1, "random", ORANGE, "Random")):
                v = [r[k] for r in S[l]["per_seed"][arm]]; ax.scatter(x + rng.uniform(-.09, .09, len(v)), v, s=40, color=c, alpha=.75, edgecolors="white", linewidths=.8, zorder=3)
                ax.hlines(np.median(v), x - .25, x + .25, color=INK, lw=2, zorder=4)
            ax.set_xticks([0, 1]); ax.set_xticklabels(["NSGA-II", "Random"]); ax.set_xlim(-.6, 1.6); ax.set_ylim(bottom=0); ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            if i == 0: ax.set_title(f"{l} noise")
        axs[i][0].set_ylabel(lab)
    fig.tight_layout(rect=(0, .03, 1, 1)); note(fig, S); fig.savefig(out / "search_vs_random.svg"); plt.close(fig)


def rules(S, out):
    show = ["report as-is", "any-of-1", "any-of-3", "any-of-5", "majority-of-3", "majority-of-5", "majority-of-9", "majority-of-19", "all-of-3", "all-of-10", "Wilson bound, n=20", "SPRT 0.3 vs 0.7"]
    A = active(S); fig, axs = plt.subplots(1, len(A), figsize=(10.5, 5.6), sharex=True)
    titles = {"medium": "Medium noise (none real)", "high": "High noise (all real)"}
    for ax, l in zip(axs, A):
        y = np.arange(len(show))[::-1]; R = S[l]["rules"]["0.5"]; e = [R[n]["error"] for n in show]
        ax.errorbar([v["est"] * 100 for v in e], y, xerr=[[max(0, (v["est"] - v["lo"]) * 100) for v in e], [max(0, (v["hi"] - v["est"]) * 100) for v in e]], fmt="o", color=BLUE, ms=8, lw=2, capsize=0)
        ax.set_yticks(y); ax.set_yticklabels([f"{n}  ({R[n]['reruns']['est']:.1f})" for n in show]); ax.set_title(titles[l], loc="left"); ax.set_xlabel("Wrong verdicts, %"); style(ax, "x"); ax.set_xlim(-2, 102)
    fig.tight_layout(rect=(0, .1, 1, 1)); fig.text(0.01, 0.05, "In brackets: mean reruns used. Real means reproduction probability at least 0.5. Bars: 95% bootstrap interval.", fontsize=10, color=MUTED); fig.text(0.01, 0.015, "Low noise is not shown: no reported failures in 8,000 runs.", fontsize=10, color=MUTED); fig.savefig(out / "verdict_rules.svg"); plt.close(fig)


def latency(out):
    D = json.load(open(ROOT / "results/diagnostics.json")); fig, axs = plt.subplots(1, 2, figsize=(9.5, 3.8), sharey=True)
    for ax, l in zip(axs, ("medium", "high")):
        b = D[l]["by_latency"]; x = np.array([int(k) for k in b]) * 20; y = [100 * b[k]["fail_rate"] for k in b]
        ax.plot(x, y, color=BLUE, lw=2, marker="o", ms=8, markeredgecolor="white", markeredgewidth=1.5); ax.set_title(f"{l} noise", loc="left"); ax.set_xlabel("Control latency drawn for the run, ms"); ax.set_ylim(-3, 103); style(ax)
    axs[0].set_ylabel("Runs that failed, %"); fig.tight_layout(); fig.savefig(out / "failure_by_latency.svg"); plt.close(fig)


def main():
    S = json.load(open(ROOT / "results/summary.json")); out = ROOT / "results/figures"; out.mkdir(parents=True, exist_ok=True)
    repro(S, out); search(S, out); rules(S, out); latency(out)


if __name__ == "__main__":
    main()
