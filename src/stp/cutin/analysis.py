"""Planned analysis of docs/GP_BOUNDARY_PLAN.md on results/gp_boundary/metrics.csv and permutation.csv.
Writes results/gp_boundary/summary.json; every number in docs/GP_BOUNDARY_REPORT.md comes from it or from the CSVs.

  python -m stp.cutin.analysis
"""
import csv
import json
import math
import numpy as np
from scipy.stats import wilcoxon
from . import campaign as C, metrics as M

BUDGETS = (100, 200, 300)
BASELINES = ("sobol", "random")
ALPHA = 0.05
MIN_WINS, MAX_RATIO = 8, 0.8
TARGETS = dict(misclass=(0.02, 0.01), berr_mean=(1.0,))


def load(path=C.OUT / "metrics.csv"):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        for k, v in r.items():
            if k not in ("arm", "model"):
                r[k] = float(v) if v not in ("", None) else math.nan
        r["seed"], r["n"] = int(r["seed"]), int(r["n"])
    return rows


def series(rows, arm, model, n, key):
    d = {r["seed"]: r[key] for r in rows if r["arm"] == arm and r["model"] == model and r["n"] == n}
    return np.array([d[i] for i in C.SEEDS])


def holm(ps):
    order = np.argsort(ps); m = len(ps); adj = np.empty(m); run = 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (m - k) * ps[i])); adj[i] = run
    return adj


def compare(a, b):
    """a better than b? a, b: per-seed errors (lower is better)."""
    d = a - b
    p = 1.0 if np.all(d == 0) else float(wilcoxon(a, b, alternative="less", zero_method="wilcox").pvalue)
    wins = int(np.sum(a < b)) + int(np.sum((a == 0) & (b == 0)))
    keep = b > 0
    ratio = float(np.median(a[keep] / b[keep])) if keep.any() else math.nan
    return dict(p=p, wins=wins, median_ratio=ratio, median_a=float(np.median(a)), median_b=float(np.median(b)),
                min_a=float(a.min()), max_a=float(a.max()), min_b=float(b.min()), max_b=float(b.max()))


def tests(rows, key="misclass"):
    out = []
    for direction in ("gp_al_better", "baseline_better"):
        block = []
        for n in BUDGETS:
            for base in BASELINES:
                x = series(rows, "gp_al", "gp", n, key); y = series(rows, base, "gp", n, key)
                r = compare(x, y) if direction == "gp_al_better" else compare(y, x)
                block.append(dict(direction=direction, budget=n, baseline=base, **r))
        adj = holm([b["p"] for b in block])
        for b, pa in zip(block, adj):
            b["p_holm"] = float(pa)
            b["passes"] = bool(pa < ALPHA and b["wins"] >= MIN_WINS and b["median_ratio"] <= MAX_RATIO)
        out += block
    return out


def verdicts(t):
    v = {}
    for n in BUDGETS:
        helps = next(x for x in t if x["direction"] == "gp_al_better" and x["budget"] == n and x["baseline"] == "sobol")["passes"]
        worse = next(x for x in t if x["direction"] == "baseline_better" and x["budget"] == n and x["baseline"] == "sobol")["passes"]
        v[n] = "GP-AL is worse" if worse else "helps" if helps else "does not help"
    if all(x == "does not help" for x in v.values()): overall = "GP does not help"
    elif all(x == "helps" for x in v.values()): overall = "GP-AL helps at every budget"
    else: overall = "mixed: " + ", ".join(f"{n} runs {x}" for n, x in v.items())
    return v, overall


def runs_needed(rows, arm, model, key, target):
    out = []
    for i in C.SEEDS:
        hit = [r["n"] for r in rows if r["arm"] == arm and r["model"] == model and r["seed"] == i and r[key] <= target]
        out.append(min(hit) if hit else None)
    vals = [x if x is not None else math.inf for x in out]
    med = float(np.median(vals))
    return dict(per_seed=out, median=None if math.isinf(med) else med, reached=sum(x is not None for x in out))


def calibration(rows, n=300):
    out = {}
    for arm in C.ARMS:
        d = {}
        for q in M.LEVELS:
            s = series(rows, arm, "gp", n, f"contain_{int(q * 100)}")
            d[str(q)] = dict(mean=float(s.mean()), min=float(s.min()), max=float(s.max()))
        s = series(rows, arm, "gp", n, "cov95_near"); d["cov95_near"] = dict(mean=float(s.mean()), min=float(s.min()), max=float(s.max()))
        s = series(rows, arm, "gp", n, "band_width_mean"); d["band_width_mean"] = float(s.mean())
        m95 = d["0.95"]["mean"]
        d["verdict_95"] = "overconfident" if m95 < 0.90 else "conservative" if m95 > 0.99 else "calibrated at 95%"
        out[arm] = d
    return out


def curves(rows, key):
    out = {}
    for arm in C.ARMS:
        for model in ("gp", "1nn", "constant"):
            out[f"{arm}/{model}"] = {n: dict(median=float(np.median(series(rows, arm, model, n, key))), min=float(series(rows, arm, model, n, key).min()),
                                              max=float(series(rows, arm, model, n, key).max())) for n in M.CHECKPOINTS}
    return out


def main():
    rows = load()
    t = tests(rows); v, overall = verdicts(t)
    tb = tests(rows, "berr_mean")
    perm = list(csv.DictReader(open(C.OUT / "permutation.csv")))
    S = dict(
        verdict_per_budget=v, verdict=overall, tests_misclass=t, tests_boundary_error=tb,
        runs_needed={f"{arm}/{model}/{key}<={tg}": runs_needed(rows, arm, model, key, tg)
                     for key, tgs in TARGETS.items() for tg in tgs for arm in C.ARMS for model in ("gp", "1nn")},
        calibration=calibration(rows), misclass_curves=curves(rows, "misclass"), berr_curves=curves(rows, "berr_mean"),
        berr_p90_curves=curves(rows, "berr_p90"),
        permutation=[dict(arm=r["arm"], seed=int(r["seed"]), p=float(r["p"]), lml_real=float(r["lml_real"]), lml_null_max=float(r["lml_null_max"])) for r in perm],
        not_realised_in_campaigns=int(sum(300 - r["n_realised"] for r in rows if r["n"] == 300 and r["model"] == "gp")))
    (C.OUT / "summary.json").write_text(json.dumps(S, indent=1))
    print("verdict:", overall, v)
    for x in t:
        print(f"{x['direction']:16s} n={x['budget']} vs {x['baseline']:6s} p_holm={x['p_holm']:.4f} wins={x['wins']} ratio={x['median_ratio']:.3f} "
              f"median {x['median_a']:.4f} vs {x['median_b']:.4f} passes={x['passes']}")
    return S


if __name__ == "__main__":
    main()
