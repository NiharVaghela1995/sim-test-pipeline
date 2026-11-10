"""Figures for docs/v2/REPORT.md, from results/v2/summary.json. Usage: python -m stp.v2.plots"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/v2/figures"
BLUE, ORANGE, AQUA, VIOLET, MAGENTA, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e87ba4", "#0b0b0b", "#52514e", "#e6e5e0"
LEVELS = ("low", "medium", "high")
plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": GRID, "xtick.color": MUTED, "ytick.color": MUTED, "axes.labelcolor": MUTED, "text.color": INK, "axes.titlesize": 13, "svg.fonttype": "none", "figure.facecolor": "white", "axes.facecolor": "white"})
SHOW = ["report as-is", "any-of-1", "any-of-3", "any-of-5", "2-of-5", "3-of-10", "4-of-5", "majority-of-3", "majority-of-5", "majority-of-9", "majority-of-19", "majority-of-39", "all-of-3", "all-of-5", "all-of-10", "Wilson bound, n=20", "SPRT 0.2/0.8, a=b=0.05", "SPRT 0.3/0.7, a=b=0.05", "SPRT 0.3/0.7, a=b=0.01", "SPRT 0.4/0.6, a=b=0.05"]


def style(ax, axis="y"):
    ax.grid(axis=axis, color=GRID, lw=.8); ax.set_axisbelow(True); ax.tick_params(length=0)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True); fig.savefig(OUT / f"{name}.svg", bbox_inches="tight"); fig.savefig(OUT / f"{name}.png", dpi=110, bbox_inches="tight"); plt.close(fig)


def truth_cover(S):
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.7), sharey=True); e = np.linspace(0, 1, 21)
    for ax, l in zip(axs, LEVELS):
        h = S[l]["truth"]["truth_hist"]; ax.bar(e[:-1] + .025, h, width=.042, color=BLUE); ax.set_title(f"{l} noise, {S[l]['truth']['scenarios']} scenarios", loc="left"); ax.set_xlabel("True failure probability p(s), 200 reruns"); ax.set_xlim(0, 1); style(ax)
    axs[0].set_ylabel("Scenarios"); fig.tight_layout(); save(fig, "truth_coverage")


def oc(S):
    C = S["oc"]; p = np.array(C["p"]); fig, ax = plt.subplots(figsize=(8.5, 5))
    L = [("any-of-3", AQUA, "-"), ("majority-of-9", BLUE, "-"), ("all-of-3", MAGENTA, "-"), ("SPRT 0.3/0.7, a=b=0.05", ORANGE, "-"), ("SPRT 0.4/0.6, a=b=0.05", VIOLET, "--")]
    for n, c, ls in L: ax.plot(p, np.array(C[n]["real"]) * 100, color=c, lw=2, ls=ls, label=n.replace(", a=b=", ", α=β="))
    ax.axvline(.5, color=MUTED, lw=1, ls=":"); ax.text(.51, 3, "real at p ≥ 0.5", color=MUTED, fontsize=11)
    ax.set_xlabel("True failure probability p(s)"); ax.set_ylabel("Chance the rule says real, %"); ax.set_xlim(0, 1); ax.set_ylim(-2, 102); style(ax); ax.legend(frameon=False, loc="upper left", fontsize=11); fig.tight_layout(); save(fig, "operating_curves")


def rule_panels(S, key, name, sub, group="decidable"):
    fig, axs = plt.subplots(1, 3, figsize=(15, 7.6)); y = np.arange(len(SHOW))[::-1]
    for ax, l in zip(axs, LEVELS):
        R = S[l][key]["scores"]["0.5"]["rules"]
        for off, m, c, lab, mk in ((.17, "false_real", BLUE, 'False "real" calls', "o"), (-.17, "missed", ORANGE, "Missed real failures", "s")):
            xs, ys, lo, hi = [], [], [], []
            for yy, n in zip(y, SHOW):
                g = R[n].get(group)
                if not g or g[m]["est"] is None: continue
                xs.append(g[m]["est"] * 100); ys.append(yy + off); lo.append(max(0, g[m]["est"] - g[m]["lo"]) * 100); hi.append(max(0, g[m]["hi"] - g[m]["est"]) * 100)
            ax.errorbar(xs, ys, xerr=[lo, hi], fmt=mk, color=c, ms=7, lw=1.8, label=lab)
        ax.axvline(5, color=MUTED, lw=1, ls=":")
        ax.set_yticks(y); ax.set_yticklabels([f"{n.replace(', a=b=', ', α=β=')}  ({R[n]['all']['reruns']['est']:.1f})" for n in SHOW], fontsize=10.5); ax.set_title(f"{l} noise", loc="left"); ax.set_xlabel("% of scenarios, |p − 0.5| ≥ 0.1"); style(ax, "x"); ax.set_xlim(-2, 102)
    h, lab = axs[0].get_legend_handles_labels(); fig.tight_layout(rect=(0, .07, 1, 1)); fig.legend(h, lab, frameon=False, loc="lower right", ncol=2, fontsize=11, bbox_to_anchor=(.99, .0)); fig.text(.01, .02, f"{sub} In brackets: mean reruns. Dotted line: 5%. Bars: bootstrap 95% interval.", fontsize=11, color=MUTED); save(fig, name)


def repro(S):
    fig, axs = plt.subplots(1, 3, figsize=(11, 4), sharey=True)
    for ax, l in zip(axs, LEVELS):
        s = S[l]["search"]; h = np.array(s["hist"], float); h = 100 * h / h.sum(); ax.bar(np.arange(10) / 10 + .05, h, width=.085, color=BLUE)
        b, m = s["base_rate"]["est"], s["rate_all"]["est"]; ax.axvline(b, color=ORANGE, lw=2); ax.axvline(m, color=INK, lw=2, ls="--")
        ax.set_title(f"{l} noise", loc="left"); ax.set_xlabel("Share of 20 reruns that failed"); ax.set_xlim(0, 1); style(ax)
    axs[0].set_ylabel("% of reported failures")
    from matplotlib.lines import Line2D
    axs[1].legend(handles=[Line2D([], [], color=ORANGE, lw=2, label="Base rate (random arm)"), Line2D([], [], color=INK, lw=2, ls="--", label="Mean reproduction rate")], frameon=False, loc="upper center", fontsize=11)
    fig.tight_layout(); save(fig, "reproduction_vs_base")


def search(S):
    M = [("reported", "Reported failures"), ("confirmed", "Reproducing in at\nleast half of reruns"), ("cells", "Distinct input cells\nwith such a failure")]
    fig, axs = plt.subplots(3, 3, figsize=(10, 8)); rng = np.random.default_rng(1)
    for i, (k, lab) in enumerate(M):
        for j, l in enumerate(LEVELS):
            ax = axs[i][j]; style(ax)
            for x, arm, c in ((0, "nsga2", BLUE), (1, "random", ORANGE)):
                v = [r[k] for r in S[l]["search"]["per_seed"][arm]]; ax.scatter(x + rng.uniform(-.09, .09, len(v)), v, s=42, color=c, alpha=.8, edgecolors="white", linewidths=.8, zorder=3); ax.hlines(np.median(v), x - .25, x + .25, color=INK, lw=2, zorder=4)
            ax.set_xticks([0, 1]); ax.set_xticklabels(["NSGA-II", "Random"]); ax.set_xlim(-.6, 1.6); ax.set_ylim(bottom=0); ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            if i == 0: ax.set_title(f"{l} noise", loc="left")
        axs[i][0].set_ylabel(lab)
    fig.tight_layout(); save(fig, "search_vs_random")


def main():
    S = json.load(open(ROOT / "results/v2/summary.json"))
    truth_cover(S); oc(S); rule_panels(S, "truth", "rules_truth_set", "Ground-truth set, equal weight per stratum."); repro(S); search(S); rule_panels(S, "search", "rules_reported_failures", "Search-reported failures, weighted by stratum and cap.")


if __name__ == "__main__":
    main()
