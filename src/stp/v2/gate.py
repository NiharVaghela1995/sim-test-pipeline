"""Calibration gates of docs/v2/PLAN.md, on random samples only. Tries candidates in order and stops at the first that passes.
Usage: python -m stp.v2.gate [--candidates A B C D E]"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier as GB
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from .. import scenario as S
from .config import CANDIDATES, G0_LATENCY_STEPS, LATENCY_STEPS, LEVELS, cfg_for
from .jobs import log, read_jsonl, run_jobs, seed_of

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "results/raw/campaign_v2"


def rng_for(*tag):
    return np.random.default_rng(int.from_bytes(hashlib.sha256(":".join(map(str, ("v2-sample", *tag))).encode()).digest()[:8], "little"))


def sample(c, n, *tag):
    return rng_for(*tag).uniform(c["xl"], c["xu"], (n, 4))


def demand(X):
    return X[:, 0] ** 2 * np.maximum(X[:, 1], np.abs(X[:, 2]))


def params(x):
    return dict(zip(S.VARS, map(float, x)))


def auc_cv(X, y, seed=0):
    p = cross_val_predict(GB(max_depth=3, max_iter=100, random_state=0), X, y, cv=StratifiedKFold(5, shuffle=True, random_state=seed), method="predict_proba")[:, 1]
    r = np.random.default_rng(seed); n = len(y); boots = []
    for _ in range(1000):
        i = r.integers(0, n, n)
        if 0 < y[i].sum() < n: boots.append(roc_auc_score(y[i], p[i]))
    return float(roc_auc_score(y, p)), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def g0(name, c, workers):
    """Latency sweep on scenarios demanding at most 3 m/s^2, with gust 0 so that latency is isolated (amendment 1 in docs/v2/PLAN.md)."""
    res = {}
    for level in LEVELS:
        pool = sample(c, 20000, name, "g0_amended", level); X = pool[demand(pool) <= 3.0][:100].copy(); X[:, 3] = 0.0; res[level] = {}  # amendment 1: gust 0, fresh scenarios
        for lat in G0_LATENCY_STEPS:
            key = f"{level}@{lat}"; f = RAW / "gate" / name / f"g0_amended_{key}.jsonl"
            run_jobs(RAW, f"gate {name} G0-amended {key}", [(key, params(x), i, 0, "g0_amended") for i, x in enumerate(X)], f, workers)
            r = read_jsonl(f); res[level][lat * 20] = dict(n=len(r), realised=sum(x[2] for x in r), failed=sum(x[3] for x in r))
    return res, all(res[l][ms]["failed"] == 0 for l in LEVELS for ms in (200, 300))


def g1(name, c, stage, workers):
    """AUC, failure rate and realisation on 1,000 random scenarios per level, one run each."""
    res = {}
    for level in LEVELS:
        X = sample(c, 1000, name, stage, level); f = RAW / "gate" / name / f"{stage}_{level}.jsonl"
        run_jobs(RAW, f"gate {name} {stage} {level}", [(level, params(x), i, 0, stage) for i, x in enumerate(X)], f, workers)
        r = sorted(read_jsonl(f)); ok = np.array([x[2] for x in r], bool); y = np.array([x[3] for x in r], int)[ok]; A = X[[x[0] for x in r]][ok]
        L = dict(n=len(r), realised_share=float(ok.mean()), fail_rate=float(y.mean()), failures=int(y.sum()))
        if 5 <= y.sum() <= len(y) - 5:
            L["auc"], L["auc_lo"], L["auc_hi"] = auc_cv(A, y)
            cfg = cfg_for(level); W = []
            for x in r:
                if x[2]:
                    g = np.random.default_rng(seed_of(level, stage, x[0], 0)); W.append([g.uniform(*cfg.gust_period), g.uniform(0, cfg.gust_phase_span)])
            L["auc_gust_timing"] = auc_cv(np.array(W), y)[0]
        res[level] = L
    pass_auc = all(res[l].get("auc", 0) >= 0.75 and res[l].get("auc_lo", 0) >= 0.70 for l in LEVELS)
    pass_rate = 0.10 <= res["medium"]["fail_rate"] <= 0.40 and res["low"]["fail_rate"] >= 0.03 and res["high"]["fail_rate"] <= 0.60
    pass_real = all(res[l]["realised_share"] >= 0.99 for l in LEVELS)
    return res, dict(auc=pass_auc, rate=pass_rate, realisation=pass_real)


def g3(name, c, workers):
    res = {}
    for level in ("medium", "high"):
        X = sample(c, 300, name, "g3", level); f = RAW / "gate" / name / f"g3_{level}.jsonl"
        run_jobs(RAW, f"gate {name} G3 {level}", [(level, params(x), i, k, "g3") for i, x in enumerate(X) for k in range(20)], f, workers)
        per = {}
        for rid, k, real, failed, m in read_jsonl(f):
            if real: per.setdefault(rid, []).append(failed)
        p = np.array([np.mean(v) for v in per.values()])
        res[level] = dict(scenarios=len(p), share_intermediate=float(np.mean((p >= 0.1) & (p <= 0.9))), share_zero=float(np.mean(p == 0)), share_one=float(np.mean(p == 1)))
    return res, all(res[l]["share_intermediate"] >= 0.05 for l in res)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--candidates", nargs="+", default=list(CANDIDATES)); ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args(); RAW.mkdir(parents=True, exist_ok=True); out = ROOT / "results/v2"; out.mkdir(parents=True, exist_ok=True)
    f = out / "gate.json"; R = json.load(open(f)) if f.exists() else {"latency_ms": LATENCY_STEPS * 20, "candidates": {}, "frozen": None}
    for name in a.candidates:
        c = CANDIDATES[name]; E = R["candidates"].setdefault(name, dict(space=c)); save = lambda: json.dump(R, open(f, "w"), indent=1)
        E["G0_amended"], ok = g0(name, c, a.workers); E["G0_amended_pass"] = ok; save(); log(RAW, name, "G0-amended", ok)
        if not ok:
            log(RAW, name, "G0 failed: stop, see the plan's fallback"); return
        E["G1"], p = g1(name, c, "g1", a.workers); E["G1_pass"] = p; save(); log(RAW, name, "G1/G2", p, {l: (round(E["G1"][l]["fail_rate"], 3), E["G1"][l].get("auc")) for l in LEVELS})
        if not all(p.values()): continue
        E["G3"], ok = g3(name, c, a.workers); E["G3_pass"] = ok; save(); log(RAW, name, "G3", ok, E["G3"])
        if not ok: continue
        E["confirm"], p = g1(name, c, "confirm", a.workers); E["confirm_pass"] = p; save(); log(RAW, name, "confirm", p, {l: (round(E["confirm"][l]["fail_rate"], 3), E["confirm"][l].get("auc")) for l in LEVELS})
        if all(p.values()):
            R["frozen"] = name; save(); log(RAW, "FROZEN", name, c); return
    log(RAW, "NO CANDIDATE PASSED")


if __name__ == "__main__":
    main()
