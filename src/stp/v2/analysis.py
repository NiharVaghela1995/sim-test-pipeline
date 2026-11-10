"""Analysis fixed in docs/v2/PLAN.md. Writes results/v2/summary.json and CSVs. Usage: python -m stp.v2.analysis [--levels low medium high]"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from scipy import stats
from .. import scenario as S
from . import rules as RL
from .campaign import REF, SEEDS, TRUTH
from .config import CANDIDATES
from .jobs import read_jsonl

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "results/raw/campaign_v2"
OUT = ROOT / "results/v2"
TAUS = (0.5, 0.2, 0.8)
BANDS = [(0, .1), (.1, .35), (.35, .65), (.65, .9), (.9, 1.0001)]
B = 1000


def table(f):
    t = {}
    for rid, k, real, failed, m in read_jsonl(f):
        t.setdefault(rid, {})[k] = (real, failed)
    return t


def seq(rows):
    return np.array([rows[k][1] for k in sorted(rows) if rows[k][0]], dtype=bool)


def wilson_hi_lo(k, n):
    z = RL.Z; p = k / n; d = 1 + z ** 2 / n; c = p + z ** 2 / (2 * n); h = z * np.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2))
    return (c - h) / d, (c + h) / d


def resample(strata, rng):
    """Bootstrap indices, resampled within strata."""
    idx = np.arange(len(strata)); out = []
    for s in np.unique(strata):
        v = idx[strata == s]; out.append(rng.choice(v, (B, len(v)), replace=True))
    return np.concatenate(out, axis=1)


def rates(real, truth, w, used):
    nt, nr = (w * ~truth).sum(-1), (w * truth).sum(-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return dict(false_real=(w * (~truth & real)).sum(-1) / nt, missed=(w * (truth & ~real)).sum(-1) / nr, wrong=(w * (real != truth)).sum(-1) / w.sum(-1), reruns=(w * used).sum(-1) / w.sum(-1))


def score(real, used, p, w, strata, tau, rng, mask=None):
    """Point estimates with bootstrap 95% intervals (within strata). real may be fractional (exact verdict probability)."""
    m = np.ones(len(p), bool) if mask is None else mask
    if m.sum() < 2: return None
    real, used, p, w, strata = real[m], used[m], p[m], w[m], strata[m]; truth = p >= tau
    frac = real.dtype != bool
    def of(ix):
        R, T, W, U = real[ix], truth[ix], w[ix], used[ix]
        if frac:
            nt, nr = (W * ~T).sum(-1), (W * T).sum(-1)
            with np.errstate(invalid="ignore", divide="ignore"):
                return dict(false_real=(W * ~T * R).sum(-1) / nt, missed=(W * T * (1 - R)).sum(-1) / nr, wrong=(W * (T * (1 - R) + ~T * R)).sum(-1) / W.sum(-1), reruns=(W * U).sum(-1) / W.sum(-1))
        return rates(R, T, W, U)
    base = of(np.arange(len(p))); boot = of(resample(strata, rng)); o = {"n": int(m.sum()), "n_real": int(truth.sum()), "n_not_real": int((~truth).sum())}
    for k in base:
        v = boot[k]; ok = np.any(~np.isnan(v))
        o[k] = dict(est=None if np.isnan(base[k]) else float(base[k]), lo=float(np.nanpercentile(v, 2.5)) if ok else None, hi=float(np.nanpercentile(v, 97.5)) if ok else None)
    return o


def apply_rule(rule, seqs):
    d = [rule.apply(s) for s in seqs]
    return np.array([x[0] for x in d], bool), np.array([x[1] for x in d], float)


def exact_rule(rule, p):
    cache = {}
    def f(q):
        q = round(float(q), 6)
        if q not in cache: cache[q] = rule.exact(q)
        return cache[q]
    v = np.array([f(q) for q in p], float)
    return v[:, 0], v[:, 1]


def recommend(res):
    """Fewest mean reruns among rules with at most 5% false 'real' and 5% missed on scenarios at least 0.1 from tau."""
    q = []
    for name, m in res.items():
        d = m.get("decidable")
        if not d or d["false_real"]["est"] is None or d["missed"]["est"] is None: continue
        if d["false_real"]["est"] <= .05 and d["missed"]["est"] <= .05: q.append((m["all"]["reruns"]["est"], name))
    if q:
        c = min(q); return dict(rule=c[1], reruns=c[0], qualifying=sorted(n for _, n in q))
    close = sorted((max(m["decidable"]["false_real"]["est"], m["decidable"]["missed"]["est"]), n) for n, m in res.items() if m.get("decidable") and m["decidable"]["false_real"]["est"] is not None and m["decidable"]["missed"]["est"] is not None)
    return dict(rule=None, closest=close[:3])


def score_rules(seqs, p, w, strata, rng, n_truth, csvrows, ctx):
    p = np.asarray(p, float); w = np.asarray(w, float); strata = np.asarray(strata); ns = n_truth; out = {}
    for tau in TAUS:
        R = {}
        rl = RL.shortlist(tau)
        k = np.round(p * ns); lo, hi = wilson_hi_lo(k, ns); clear = (lo >= tau) | (hi < tau)
        masks = dict(all=None, decidable=np.abs(p - tau) >= .1, near_tau=np.abs(p - tau) < .1, truth_clear=clear)
        for r in rl:
            real, used = apply_rule(r, seqs); ex, exu = exact_rule(r, p); M = {g: score(real, used, p, w, strata, tau, rng, m) for g, m in masks.items()}
            M["exact_all"] = score(ex, exu, p, w, strata, tau, rng); M["exact_decidable"] = score(ex, exu, p, w, strata, tau, rng, masks["decidable"])
            M["by_band"] = [dict(band=b, n=int(((p >= b[0]) & (p < b[1])).sum()), share_real=float(np.average(real[(p >= b[0]) & (p < b[1])], weights=w[(p >= b[0]) & (p < b[1])])) if ((p >= b[0]) & (p < b[1])).any() else None) for b in BANDS]
            R[r.name] = M
            for g in ("all", "decidable", "truth_clear"):
                if M[g]: csvrows.append(dict(ctx, tau=tau, rule=r.name, group=g, n=M[g]["n"], **{f"{a}_{b}": (None if M[g][a][b] is None else round(M[g][a][b], 4)) for a in ("false_real", "missed", "wrong", "reruns") for b in ("est", "lo", "hi")}))
        out[str(tau)] = dict(rules=R, n_real=int((p >= tau).sum()), n_not_real=int((p < tau).sum()), n_decidable=int(masks["decidable"].sum()), n_near_tau=int(masks["near_tau"].sum()), recommended=recommend(R), recommended_exact=recommend({n: dict(all=m["exact_all"], decidable=m["exact_decidable"]) for n, m in R.items()}))
    return out


def sprt_errors():
    """Achieved error rates of the capped sequential tests, exact, against the stated ones."""
    out = []
    for p0, p1, a, tau in [(.3, .7, .05, .5), (.2, .8, .05, .5), (.4, .6, .05, .5), (.3, .7, .01, .5), (.05, .35, .05, .2), (.65, .95, .05, .8)]:
        r = RL.sprt(p0, p1, a, a, tau)
        out.append(dict(rule=r.name, tau=tau, stated=a, false_real_at_p0=r.exact(p0)[0], missed_at_p1=1 - r.exact(p1)[0], reruns_at_p0=r.exact(p0)[1], reruns_at_p1=r.exact(p1)[1], reruns_at_tau=r.exact(tau)[1], worst_reruns=max(r.exact(q)[1] for q in np.linspace(.01, .99, 99))))
    return out


def oc_curves():
    g = np.round(np.linspace(0, 1, 101), 3); out = dict(p=g.tolist())
    for r in RL.shortlist(.5):
        v = [r.exact(float(q)) for q in g]; out[r.name] = dict(real=[x[0] for x in v], reruns=[x[1] for x in v])
    return out


def truth_level(level, rng, csvrows, gridrows):
    d = RAW / "truth" / level
    if not (d / "rule.jsonl").exists(): return None
    S_ = json.load(open(d / "set.json")); tr, ru, pil = table(d / "truth.jsonl"), table(d / "rule.jsonl"), table(d / "pilot.jsonl")
    seqs, p, w, strata, ids, dropped, pilot = [], [], [], [], [], 0, []
    used = {k: v for k, v in S_["picked"].items() if v}
    for g, v in used.items():
        for i in v:
            s, t = seq(ru.get(i, {})), seq(tr.get(i, {}))
            if len(s) < 39 or len(t) < 150: dropped += 1; continue
            seqs.append(s); p.append(float(t.mean())); w.append((1 / len(used)) / len(v)); strata.append(g); ids.append(i); pilot.append(float(seq(pil[i]).mean()))
    p = np.array(p); L = dict(pool_sizes=S_["pool_sizes"], picked={k: len(v) for k, v in S_["picked"].items()}, source_counts={k: sum(S_["source"][str(i)] == "random" for i in v) for k, v in S_["picked"].items()}, dropped_unrealised=dropped, scenarios=len(p))
    L["truth_hist"] = np.histogram(p, bins=np.linspace(0, 1, 21))[0].tolist(); L["truth_by_stratum"] = {g: dict(n=sum(1 for s in strata if s == g), mean=float(p[[s == g for s in strata]].mean()), min=float(p[[s == g for s in strata]].min()), max=float(p[[s == g for s in strata]].max())) for g in used}
    L["truth_band_counts"] = [dict(band=b, n=int(((p >= b[0]) & (p < b[1])).sum())) for b in BANDS]
    L["not_realised"] = {n: 1 - sum(r[0] for v in t.values() for r in v.values()) / max(sum(len(v) for v in t.values()), 1) for n, t in (("pilot", pil), ("truth", tr), ("rule", ru))}
    L["pilot_truth_corr"] = float(np.corrcoef(pilot, p)[0, 1])
    L["scores"] = score_rules(seqs, p, w, strata, rng, TRUTH, csvrows, dict(population="truth_set", level=level))
    for rl in RL.grid():
        real, u = apply_rule(rl, seqs)
        M = score(real, u, p, np.array(w), np.array(strata), .5, rng, np.abs(p - .5) >= .1)
        if M: gridrows.append(dict(population="truth_set", level=level, tau=.5, rule=rl.name, group="decidable", n=M["n"], false_real=M["false_real"]["est"], missed=M["missed"]["est"], wrong=M["wrong"]["est"], reruns=M["reruns"]["est"]))
    return L


def a12(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return float(sum((a > b) + .5 * (a == b) for a in x for b in y) / (len(x) * len(y)))


def boot_mean(v, w, rng):
    v, w = np.asarray(v, float), np.asarray(w, float); n = len(v); ix = rng.integers(0, n, (B, n)); m = (v[ix] * w[ix]).sum(1) / w[ix].sum(1)
    return dict(est=float((v * w).sum() / w.sum()), lo=float(np.percentile(m, 2.5)), hi=float(np.percentile(m, 97.5)))


def search_level(level, c, rng, csvrows):
    d = RAW / "search" / level
    if not (d / "strata.json").exists(): return None
    fails = read_jsonl(d / "failures.jsonl"); rep, ref, ext = table(d / "reps.jsonl"), table(d / "reference.jsonl"), table(d / "reps_ext.jsonl"); st = json.load(open(d / "strata.json"))
    evals = {(a, s): read_jsonl(d / f"eval_{a}_{s}.jsonl")[:400] for a in ("nsga2", "random") for s in range(SEEDS)}
    L = {}
    rnd = [r for (a, _), v in evals.items() if a == "random" for r in v]; real_rnd = [r for r in rnd if r["realised"]]
    base = np.array([r["failed"] for r in real_rnd], float); L["base_rate"] = boot_mean(base, np.ones(len(base)), rng); L["evaluations"] = sum(len(v) for v in evals.values())
    L["not_realised_search"] = sum(not r["realised"] for v in evals.values() for r in v) / L["evaluations"]; L["reported"] = {a: int(sum(r["failed"] for (b, _), v in evals.items() if b == a for r in v)) for a in ("nsga2", "random")}
    if not fails: return L
    r = {x["failure"]: float(seq(rep[x["failure"]]).mean()) for x in fails if len(seq(rep.get(x["failure"], {})))}
    F = [x for x in fails if x["failure"] in r]; v = np.array([r[x["failure"]] for x in F]); w = np.array([x["reported_in_seed"] / x["sampled_in_seed"] for x in F]); arm = np.array([x["arm"] for x in F])
    L["sampled_for_replication"] = len(F); L["not_realised_replication"] = 1 - sum(q[0] for t in rep.values() for q in t.values()) / sum(len(t) for t in rep.values())
    L["rate_all"] = boot_mean(v, w, rng); L["rate_by_arm"] = {a: boot_mean(v[arm == a], w[arm == a], rng) for a in ("nsga2", "random") if (arm == a).any()}; L["hist"] = np.histogram(v, bins=np.linspace(0, 1, 11), weights=w)[0].tolist()
    L["hist_by_arm"] = {a: np.histogram(v[arm == a], bins=np.linspace(0, 1, 11), weights=w[arm == a])[0].tolist() for a in ("nsga2", "random") if (arm == a).any()}
    L["shares"] = dict(never=float(w[v == 0].sum() / w.sum()), partly=float(w[(v > 0) & (v < 1)].sum() / w.sum()), always=float(w[v == 1].sum() / w.sum()), ge_half=float(w[v >= .5].sum() / w.sum()))
    L["excess_over_base"] = L["rate_all"]["est"] - L["base_rate"]["est"]
    # H2, dispersion above binomial
    n = np.array([len(seq(rep[x["failure"]])) for x in F]); k = np.round(v * n); pooled = k.sum() / n.sum()
    if 0 < pooled < 1:
        D = float(((k - n * pooled) ** 2 / (n * pooled * (1 - pooled))).sum()); df = len(k) - 1; L["heterogeneity"] = dict(failures=len(k), pooled=float(pooled), chi2=D, df=df, dispersion=D / df, p=float(stats.chi2.sf(D, df)))
    # search against random
    per = {a: [] for a in ("nsga2", "random")}
    for a in per:
        for s in range(SEEDS):
            f = [x for x in F if x["arm"] == a and x["search_seed"] == s]; rep_n = sum(q["failed"] for q in evals[(a, s)]); sc = rep_n / len(f) if f else 0
            conf = [x for x in f if r[x["failure"]] >= .5]
            cells = {tuple(min(4, int(5 * (x["params"][q] - lo) / (hi - lo))) for q, lo, hi in zip(S.VARS, c["xl"], c["xu"])) for x in conf}
            per[a].append(dict(reported=rep_n, confirmed=len(conf) * sc, cells=len(cells), sampled=len(f)))
    L["per_seed"] = per; cmp = {}
    for q in ("reported", "confirmed", "cells"):
        x, y = [z[q] for z in per["nsga2"]], [z[q] for z in per["random"]]; u = stats.mannwhitneyu(x, y, alternative="two-sided")
        cmp[q] = dict(nsga2_median=float(np.median(x)), random_median=float(np.median(y)), A12=a12(x, y), p=float(u.pvalue))
    L["search_vs_random"] = cmp
    # rules on reported failures
    picked = [(g, i) for g, q in st["picked"].items() for i in q]; by = {x["failure"]: x for x in F}; seqs, p, W, strat, dropped = [], [], [], [], 0
    for g, i in picked:
        if i not in by: dropped += 1; continue
        a = {**rep.get(i, {}), **ext.get(i, {})}; s, t = seq(a), seq(ref.get(i, {}))
        if len(s) < 39 or len(t) < 150: dropped += 1; continue
        seqs.append(s); p.append(float(t.mean())); W.append(st["sizes"][g] / len(st["picked"][g]) * by[i]["reported_in_seed"] / by[i]["sampled_in_seed"]); strat.append(g)
    L["strata"] = st["sizes"]; L["rule_sample"] = len(p); L["rule_sample_dropped"] = dropped
    p = np.array(p); L["reference_by_stratum"] = {g: dict(n=sum(1 for s in strat if s == g), mean=float(p[[s == g for s in strat]].mean()), min=float(p[[s == g for s in strat]].min()), max=float(p[[s == g for s in strat]].max())) for g in set(strat)}
    L["share_real"] = {str(t): float(np.array(W)[p >= t].sum() / np.sum(W)) for t in TAUS}; L["reference_hist"] = np.histogram(p, bins=np.linspace(0, 1, 11))[0].tolist()
    L["not_realised_reference"] = 1 - sum(q[0] for t in ref.values() for q in t.values()) / max(sum(len(t) for t in ref.values()), 1)
    L["scores"] = score_rules(seqs, p, W, strat, rng, REF, csvrows, dict(population="reported_failures", level=level))
    return L


def holm(S):
    tests = [(lv, q, S[lv]["search"]["search_vs_random"][q]["p"]) for lv in S if isinstance(S[lv], dict) and S[lv].get("search") and "search_vs_random" in S[lv]["search"] for q in ("reported", "confirmed", "cells")]
    tests = sorted([t for t in tests if not np.isnan(t[2])], key=lambda t: t[2]); adj, m = {}, len(tests); running = 0.0
    for i, (lv, q, p) in enumerate(tests):
        running = max(running, min(1.0, (m - i) * p)); S[lv]["search"]["search_vs_random"][q]["p_holm"] = running


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--levels", nargs="+", default=["low", "medium", "high"]); a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True); g = json.load(open(OUT / "gate.json")); c = CANDIDATES[g["frozen"]]; rng = np.random.default_rng(20261110); S_ = {}; rows, grid = [], []
    for lv in a.levels:
        S_[lv] = dict(truth=truth_level(lv, rng, rows, grid), search=search_level(lv, c, rng, rows)); print(lv, "done", flush=True)
    holm(S_)
    S_["sprt_errors"] = sprt_errors(); S_["oc"] = oc_curves(); S_["gate"] = g; S_["provenance"] = json.load(open(RAW / "manifest.json"))
    S_["runs"] = {n: sum(1 for _ in open(f)) for n, f in ((str(f.relative_to(RAW)), f) for f in RAW.rglob("*.jsonl"))}
    json.dump(S_, open(OUT / "summary.json", "w"), indent=1, default=lambda x: float(x))
    for name, data in (("verdict_rules.csv", rows), ("k_of_n_grid.csv", grid)):
        if data:
            with open(OUT / name, "w", newline="") as f:
                wr = csv.DictWriter(f, fieldnames=list(data[0])); wr.writeheader(); wr.writerows(data)


if __name__ == "__main__":
    main()
