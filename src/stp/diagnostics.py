"""Post-hoc diagnostic, not in docs/PREREG.md: does a run's outcome depend on the scenario x, or only on the injected W?
Uses logged runs only (no new simulation). Writes results/diagnostics.json. Usage: python -m stp.diagnostics"""
import json
from pathlib import Path
import numpy as np
from scipy import stats
from sklearn.ensemble import HistGradientBoostingClassifier as GB
from sklearn.model_selection import cross_val_predict
from sklearn.metrics import roc_auc_score
from . import scenario as S
from .sut import LEVELS, LaneKeeper
from .analysis import jsonl

ROOT = Path(__file__).resolve().parents[2]


def drawn_w(seed, level):
    """Gust period, gust phase and latency of a run, redrawn in the order stp.runner.run draws them."""
    cfg = LEVELS[level]; rng = np.random.default_rng(seed)
    period = rng.uniform(*cfg.gust_period); phase = rng.uniform(0, cfg.gust_phase_span)
    return period, phase, LaneKeeper(cfg, rng).delay


def auc(X, y):
    p = cross_val_predict(GB(max_depth=3, max_iter=100, random_state=0), X, y, cv=5, method="predict_proba")[:, 1]
    return float(roc_auc_score(y, p))


def main():
    raw = ROOT / "results/raw/campaign_v1"; out = {}
    for level in LEVELS:
        rows = [x for s in range(10) for x in jsonl(raw / level / f"eval_random_{s}.jsonl")[:400] if x["realised"]]
        y = np.array([x["failed"] for x in rows], int); W = np.array([drawn_w(x["seed"], level) for x in rows]); d = W[:, 2].astype(int); X = np.array([[x["params"][v] for v in S.VARS] for x in rows])
        L = dict(runs=len(rows), fail_rate=float(y.mean()), by_latency={int(v): dict(n=int((d == v).sum()), fail_rate=float(y[d == v].mean())) for v in np.unique(d)})
        if y.sum() >= 20:
            L["auc_cv"] = dict(scenario_only=auc(X, y), latency_only=auc(d[:, None], y), gust_timing_only=auc(W[:, :2], y), all_w=auc(W, y), scenario_and_w=auc(np.c_[X, W], y))
        fails = jsonl(raw / level / "failures.jsonl")
        if fails:
            reps = {}
            for fid, k, realised, failed, m in jsonl(raw / level / "reps.jsonl"):
                if realised: reps.setdefault(fid, []).append(failed)
            n = np.array([len(v) for v in reps.values()]); k = np.array([sum(v) for v in reps.values()]); p = k.sum() / n.sum()
            D = float(((k - n * p) ** 2 / (n * p * (1 - p))).sum()); df = len(k) - 1
            L["heterogeneity"] = dict(failures=len(k), pooled_rate=float(p), chi2=D, df=df, dispersion=D / df, p=float(stats.chi2.sf(D, df)))
            ref = {}
            for fid, kk, realised, failed, m in jsonl(raw / level / "reference.jsonl"):
                if realised: ref.setdefault(fid, []).append(failed)
            ph = np.array([np.mean(v) for v in ref.values() if len(v) >= 150])
            L["reference"] = dict(failures=len(ph), mean=float(ph.mean()), sd=float(ph.std(ddof=1)), sd_if_identical=float(np.sqrt(ph.mean() * (1 - ph.mean()) / 200)), min=float(ph.min()), max=float(ph.max()))
        out[level] = L; print(level, {k: v for k, v in L.items() if k != "by_latency"}, flush=True)
        print({k: (v["n"], round(v["fail_rate"], 3)) for k, v in L["by_latency"].items()}, flush=True)
    json.dump(out, open(ROOT / "results/diagnostics.json", "w"), indent=1)


if __name__ == "__main__":
    main()
