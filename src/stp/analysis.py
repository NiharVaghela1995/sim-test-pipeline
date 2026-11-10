"""Analysis fixed in docs/PREREG.md. Usage: python -m stp.analysis [--raw results/raw/campaign_v1] [--levels low medium high]"""
import argparse
import csv
import json
import math
from pathlib import Path
import numpy as np
from scipy import stats
from . import scenario as S

ROOT = Path(__file__).resolve().parents[2]
TAUS = (0.5, 0.2, 0.8)
Z = 1.959964


def wilson_low(k, n):
    if n == 0: return 0.0
    p = k / n; d = 1 + Z ** 2 / n
    return (p + Z ** 2 / (2 * n) - Z * math.sqrt(p * (1 - p) / n + Z ** 2 / (4 * n ** 2))) / d


def sprt(seq, p0=0.3, p1=0.7, a=0.05, b=0.05, cap=20):
    """Wald sequential test of p <= p0 against p >= p1. Returns (real, reruns used)."""
    upper, lower = math.log((1 - b) / a), math.log(b / (1 - a)); llr = 0.0; n = 0; k = 0
    for x in seq[:cap]:
        n += 1; k += int(x)
        llr += math.log(p1 / p0) if x else math.log((1 - p1) / (1 - p0))
        if llr >= upper: return True, n
        if llr <= lower: return False, n
    return (k / max(n, 1) >= 0.5), n


def rules(tau):
    R = {"report as-is": lambda s: (True, 0)}
    for n in (1, 3, 5): R[f"any-of-{n}"] = (lambda n: lambda s: (bool(np.any(s[:n])), n))(n)
    for n in (3, 5, 9, 19): R[f"majority-of-{n}"] = (lambda n: lambda s: (int(np.sum(s[:n])) > n / 2, n))(n)
    for n in (3, 5, 10): R[f"all-of-{n}"] = (lambda n: lambda s: (bool(np.all(s[:n])), n))(n)
    R["Wilson bound, n=20"] = lambda s: (wilson_low(int(np.sum(s[:20])), min(20, len(s))) >= tau, 20)
    R["SPRT 0.3 vs 0.7"] = lambda s: sprt(s)
    return R


def jsonl(f): return [json.loads(l) for l in open(f) if l.strip()]


def load(raw, level):
    d = raw / level; fails = jsonl(d / "failures.jsonl"); n = len(fails)
    def table(name):
        t = {}
        for fid, k, realised, failed, m in jsonl(d / name):
            t.setdefault(fid, {})[k] = (realised, failed)
        return t
    rep, ref = table("reps.jsonl"), table("reference.jsonl")
    evals = {(a, s): jsonl(d / f"eval_{a}_{s}.jsonl")[:400] for a in ("nsga2", "random") for s in range(10) if (d / f"eval_{a}_{s}.jsonl").exists()}
    return fails, rep, ref, evals, json.load(open(d / "strata.json"))


def seq_of(t, fid):
    rows = t.get(fid, {})
    return np.array([rows[k][1] for k in sorted(rows) if rows[k][0]], dtype=bool)


def weighted_metrics(items, weights, tau, rule, rng, B=1000):
    """items: (seq, p_hat). Inverse-probability weighted over strata, bootstrap interval over failures."""
    dec = np.array([rule(s) for s, _ in items], dtype=float)
    real = dec[:, 0].astype(bool); used = dec[:, 1]; p = np.array([x[1] for x in items]); w = np.asarray(weights, float); truth = p >= tau
    def m(ix):
        W, R, T, U = w[ix], real[ix], truth[ix], used[ix]; nt = W[~T].sum(); nr = W[T].sum()
        return dict(false_confirm=(W[~T & R].sum() / nt) if nt else float("nan"), false_reject=(W[T & ~R].sum() / nr) if nr else float("nan"), error=W[R != T].sum() / W.sum(), reruns=(W * U).sum() / W.sum())
    base = m(np.arange(len(items)))
    boot = [m(rng.integers(0, len(items), len(items))) for _ in range(B)]
    return {k: dict(est=float(base[k]), lo=float(np.nanpercentile([b[k] for b in boot], 2.5)), hi=float(np.nanpercentile([b[k] for b in boot], 97.5))) for k in base}


def describe(rows):
    realised = [x for x in rows if x["realised"]]; m = np.array([x["margin"] for x in realised], float); n = len(rows); f = sum(x["failed"] for x in realised)
    gates = {}
    for x in rows:
        for g, ok in x["gates"].items():
            if not ok: gates[g] = gates.get(g, 0) + 1
    return dict(runs=n, realised=len(realised), failed=f, fail_rate=f / max(len(realised), 1), margin_min=float(m.min()), margin_p05=float(np.percentile(m, 5)), margin_median=float(np.median(m)), gate_failures=gates, upper95_if_zero=1 - 0.05 ** (1 / len(realised)) if f == 0 else None)


def a12(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return float(sum((a > b) + 0.5 * (a == b) for a in x for b in y) / (len(x) * len(y)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--raw", default="results/raw/campaign_v1"); ap.add_argument("--levels", nargs="+", default=["low", "medium", "high"]); ap.add_argument("--out", default="results")
    a = ap.parse_args(); raw = ROOT / a.raw; out = ROOT / a.out; out.mkdir(exist_ok=True); rng = np.random.default_rng(20261110); summary = {}; csvrows = []
    for level in a.levels:
        fails, rep, ref, evals, strata = load(raw, level)
        L = dict(reported_failures=len(fails), strata=strata["sizes"])
        ev = [x for v in evals.values() for x in v]
        L["evaluations"] = len(ev); L["not_realised_in_search"] = sum(not x["realised"] for x in ev)
        # descriptive additions, not in docs/PREREG.md: run failure rates, safety margins, which gates failed
        L["descriptive"] = {arm: describe([x for (a, _), v in evals.items() if a == arm for x in v]) for arm in ("nsga2", "random")}
        L["not_realised_in_replication"] = sum(1 for v in rep.values() for r in v.values() if not r[0]); L["replication_runs"] = sum(len(v) for v in rep.values()); L["reference_runs"] = sum(len(v) for v in ref.values())
        if not fails:
            print(level, "failures 0, no replication or rule analysis possible", flush=True)
            L["per_seed"] = {arm: [dict(reported=0, confirmed=0, cells=0)] * 10 for arm in ("nsga2", "random")}
            summary[level] = L; continue
        rates = {x["failure"]: float(seq_of(rep, x["failure"]).mean()) if len(seq_of(rep, x["failure"])) else float("nan") for x in fails}
        R = np.array(list(rates.values()))
        L["reproduction"] = dict(mean=float(np.nanmean(R)), median=float(np.nanmedian(R)), share_never=float(np.nanmean(R == 0)), share_flaky=float(np.nanmean((R > 0) & (R < 1))), share_always=float(np.nanmean(R == 1)), share_ge_half=float(np.nanmean(R >= 0.5)), hist=np.histogram(R[~np.isnan(R)], bins=np.linspace(0, 1, 11))[0].tolist())
        # search against random
        sv = {}
        for arm in ("nsga2", "random"):
            rows = []
            for s in range(10):
                fs = [x for x in fails if x["arm"] == arm and x["search_seed"] == s]; conf = [x for x in fs if rates[x["failure"]] >= 0.5]
                bins = {tuple(min(4, int(5 * (x["params"][v] - lo) / (hi - lo))) for v, lo, hi in zip(S.VARS, S.XL, S.XU)) for x in conf}
                rows.append(dict(reported=len(fs), confirmed=len(conf), cells=len(bins), first_reported_rate=np.mean([rates[x["failure"]] for x in fs]) if fs else float("nan")))
            sv[arm] = rows
        cmp = {}
        for k in ("reported", "confirmed", "cells"):
            x, y = [r[k] for r in sv["nsga2"]], [r[k] for r in sv["random"]]
            u = stats.mannwhitneyu(x, y, alternative="two-sided")
            cmp[k] = dict(nsga2_median=float(np.median(x)), random_median=float(np.median(y)), A12=a12(x, y), p=float(u.pvalue))
        L["search_vs_random"] = cmp; L["per_seed"] = sv
        L["reproduction_by_arm"] = {arm: float(np.nanmean([rates[x["failure"]] for x in fails if x["arm"] == arm])) for arm in ("nsga2", "random")}
        # rules on the reference-sampled failures
        picked = [(g, i) for g, v in strata["picked"].items() for i in v]; items, w = [], []
        for g, i in picked:
            s, r = seq_of(rep, i), seq_of(ref, i)
            if len(s) < 19 or len(r) < 150: continue
            items.append((s, float(r.mean()))); w.append(strata["sizes"][g] / len(strata["picked"][g]))
        L["rule_sample"] = len(items); P = np.array([x[1] for x in items]); L["share_real_at_tau"] = {str(t): float((np.asarray(w) * (P >= t)).sum() / np.sum(w)) for t in TAUS}
        L["reference_p_by_stratum"] = {g: float(np.mean([seq_of(ref, j).mean() for j in v if len(seq_of(ref, j))])) if v else None for g, v in strata["picked"].items()}
        L["rules"] = {}
        for tau in TAUS:
            L["rules"][str(tau)] = {}
            for name, rule in rules(tau).items():
                L["rules"][str(tau)][name] = weighted_metrics(items, w, tau, rule, rng)
                M = L["rules"][str(tau)][name]; csvrows.append(dict(level=level, tau=tau, rule=name, **{f"{k}_{q}": round(M[k][q], 4) for k in M for q in M[k]}))
        need = {}
        for t in TAUS:
            need[str(t)] = None
            for n in (1, 3, 5, 7, 9, 11, 13, 15, 17, 19):
                e = weighted_metrics(items, w, t, (lambda n: lambda s: (int(np.sum(s[:n])) > n / 2, n))(n), rng, B=2)["error"]["est"]
                if e <= 0.05: need[str(t)] = n; break
        L["majority_n_for_5pct_error"] = need
        summary[level] = L; print(level, "failures", len(fails), "rule sample", len(items), flush=True)
    summary["provenance"] = json.load(open(raw / "manifest.json"))
    json.dump(summary, open(out / "summary.json", "w"), indent=1)
    with open(out / "verdict_rules.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(csvrows[0])); w.writeheader(); w.writerows(csvrows)


if __name__ == "__main__":
    main()
