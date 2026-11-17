"""Noisy R157 cut-in: does a heteroskedastic GP find the failure region {x : p(x) >= ALPHA} better than a homoscedastic one,
Sobol or random, at equal budget? Plan: docs/NOISE_PLAN.md (committed before any step below except `portcheck` ran).

  PYTHONPATH=src .venv/bin/python -m stp.noise.experiment portcheck|broken|reference|campaigns|score|replicate|reruns|all [workers]

Steps
  portcheck   the ported ACC with noise off against esmini's ACC on stored R157 reference runs (must agree)
  broken      the 10 broken scenarios of the R157 study through the noisy runner (level mid)
  reference   per level: grid, 10 replicates everywhere, topped up to 40 near failures (stage-2 rule below); truth p(x)
  campaigns   per level: hom_al, het_al, sobol, random x seeds 0-9, 300 runs each
  score       misclassification, boundary error, recall, band calibration, no-verdict share; planned tests
  replicate   5 predicted-boundary points per campaign, 20 reruns each: empirical p there against ALPHA
  reruns      reruns a verdict needs at each level (binary SPRT; Gaussian quantile rule on the margins)
"""
import hashlib
import json
import multiprocessing as mp
import sys
import time
import warnings
from functools import lru_cache
from pathlib import Path
import numpy as np
from scipy.stats import beta as Beta, nct, norm, wilcoxon
from sklearn.isotonic import IsotonicRegression
from ..cutin import gp as GP
from ..cutin.campaign import environment
from ..r157 import design as D
from . import sut as N, runner as NR, surrogates as M

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/noise"
RAW = ROOT / "results/raw/noise"

LEVELS = {l.name: l for l in (N.Level("low", 0.2, 0.1, 0.1, 0.1), N.Level("mid", 0.5, 0.2, 0.3, 0.2), N.Level("high", 1.0, 0.3, 0.6, 0.3))}
ARMS = ("hom_al", "het_al", "sobol", "random")
MODEL_OF = dict(hom_al="hom", het_al="het", sobol="hom", random="hom")
SECONDARY = (("het_al", "hom"),)            # secondary: the homoscedastic GP refitted on het_al's (replicated) runs
SEEDS = tuple(range(10))
BUDGET = 300
CHECKPOINTS = tuple(range(40, 301, 20))
TEST_N = (100, 200, 300)
BAND = (0.5, 0.8, 0.9, 0.95, 0.99)
HET_INIT, HET_BATCH, HET_REPS = 15, 5, 2    # het_al: 15 points x 2 runs, then 5 points x 2 runs per batch of 10

# reference grid (coarser in ego speed, where the deterministic boundary barely moves; finer in v_rel at the low end)
V = np.round(np.linspace(10.0, 50.0 / 3.0, 5), 10)
VR = np.round(np.r_[np.arange(0.5, 3.0 + 1e-9, 0.25), np.arange(3.5, 8.0 + 1e-9, 0.5)], 10)
T = np.round(np.arange(0.2, 3.0 + 1e-9, 0.05), 10)
REF_STAGE1, REF_STAGE2 = 10, 40
NEIGH_T = 3                                 # stage-2 neighbourhood: +-3 TTC steps on the line, +-1 on the v_rel and ego axes
MIN_REAL_TRUTH = 5                          # a grid point needs >= 5 realised runs to carry a truth label
N_REP_BOUNDARY, REP_BOUNDARY = 5, 20
SPRT = dict(p0=M.ALPHA / 2, p1=2 * M.ALPHA, err=0.05, n_max=200)
QRULE = dict(conf=0.95, n_min=2, n_max=100, boot=200)


def seed_of(*p):
    return int.from_bytes(hashlib.sha256(("noise:" + ":".join(map(str, p))).encode()).digest()[:8], "little")


# ----------------------------------------------------------------------------------------------- runs
def _one(a):
    key, x, lv, seed = a
    r = NR.run(x, LEVELS[lv], seed)
    return dict(key=key, x=[float(v) for v in x], seed=seed, realised=r["realised"], margin=r["margin"], min_gap=r["min_gap"],
                collided=r["collided"], overbrake=r["overbrake"], bad=[k for k, v in r["gates"].items() if not v])


def run_points(lv, name, items, workers=4):
    """items: (key, x, seed); stored per level in results/raw/noise/<level>/<name>.jsonl; resumable."""
    f = RAW / lv / f"{name}.jsonl"; f.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    if f.exists():
        for l in f.read_text().splitlines():
            if l.strip():
                r = json.loads(l); rows[r["key"]] = r
    todo = [(k, x, lv, s) for k, x, s in items if k not in rows]
    if todo:
        t0 = time.time()
        with open(f, "a") as o:
            if workers == 1:                       # inside a campaign-level worker: no nested pool
                for a in todo:
                    r = _one(a); o.write(json.dumps(r) + "\n"); rows[r["key"]] = r
            else:
                with mp.Pool(workers) as p:
                    for r in p.imap_unordered(_one, todo, chunksize=16):
                        o.write(json.dumps(r) + "\n"); rows[r["key"]] = r
        if workers > 1 or len(todo) > 50:
            print(f"{lv}/{name}: {len(todo)} runs in {time.time() - t0:.0f} s", flush=True)
    for k, x, s in items:
        if not np.allclose(rows[k]["x"], x, rtol=0, atol=1e-12) or rows[k]["seed"] != s:
            raise RuntimeError(f"{lv}/{name}: stored run {k} has other parameters or seed; refusing to resume")
    return rows


# ----------------------------------------------------------------------------------------------- step 0: port check
def portcheck(workers=4, n=500):
    """With noise off, the ported ACC must reproduce esmini's ACC: margins of n stored R157 reference runs (seeded sample)."""
    rows = [json.loads(l) for l in (ROOT / "results/raw/r157/reference.jsonl").read_text().splitlines() if l.strip()]
    idx = np.random.default_rng(seed_of("portcheck") % 2 ** 32).choice(len(rows), n, replace=False)
    zero = N.Level("zero")
    with mp.Pool(workers) as p:
        new = p.starmap(NR.run, [(rows[i]["x"], zero, 0) for i in idx])
    d = [abs(a["margin"] - rows[i]["margin"]) for a, i in zip(new, idx) if a["realised"] and rows[i]["realised"]]
    same_real = sum(a["realised"] == rows[i]["realised"] for a, i in zip(new, idx))
    out = dict(runs=n, realised_agree=int(same_real), both_realised=len(d), max_abs_margin_diff=float(max(d)),
               verdicts_agree=int(sum((a["margin"] >= 0) == (rows[i]["margin"] >= 0) for a, i in zip(new, idx) if a["realised"] and rows[i]["realised"])),
               passed=bool(same_real == n and max(d) <= 1e-3))
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "portcheck.json").write_text(json.dumps(out, indent=1)); print(out)
    if not out["passed"]:
        raise RuntimeError("port check failed: the ported ACC does not reproduce esmini's ACC; stop (NOISE_PLAN.md step 0)")
    return out


def broken(workers=4):
    sys.path.insert(0, str(ROOT / "tests"))
    from test_cutin import BROKEN
    from ..cutin import scenario as S
    x = np.array([14.0, 3.0, 1.5]); lv = LEVELS["mid"]; out = []
    for name, d, _ in BROKEN + [("cutter 1 m/s slower than designed", S.Defects(cut_speed_shift=-1.0), None)]:
        r = NR.run(x, lv, seed_of("broken", name), defects=d)
        out.append(dict(defect=name, realised=r["realised"], failed_gates=sorted(k for k, v in r["gates"].items() if not v)))
    clean = [NR.run(x, lv, seed_of("broken", "clean", j))["realised"] for j in range(5)]
    res = dict(level="mid", clean_realised=clean, broken=out, all_caught=all(not o["realised"] for o in out))
    (OUT / "broken.json").write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1))
    return res


# ----------------------------------------------------------------------------------------------- reference
def grid():
    vv, rr, tt = np.meshgrid(V, VR, T, indexing="ij")
    X = np.stack([vv.ravel(), rr.ravel(), tt.ravel()], 1)
    return X, D.applicable(X)


def _stage2(fails, app):
    """Grid points to top up: any failing realised run at the point or a neighbour (stage 1), or < MIN_REAL_TRUTH realised."""
    f = fails > 0; sel = np.zeros_like(f)
    for dt in range(-NEIGH_T, NEIGH_T + 1):
        sel |= f if dt == 0 else _shift(f, dt, 2)
    for ax in (0, 1):
        for dd in (-1, 1):
            sel |= _shift(f, dd, ax)
    return sel & app


def _shift(a, d, ax):
    out = np.zeros_like(a); src = [slice(None)] * 3; dst = [slice(None)] * 3
    if d > 0: src[ax], dst[ax] = slice(0, -d), slice(d, None)
    else: src[ax], dst[ax] = slice(-d, None), slice(0, d)
    out[tuple(dst)] = a[tuple(src)]; return out


def reference(workers=4):
    X, app = grid(); shape = (len(V), len(VR), len(T)); A = app.reshape(shape)
    idx = np.nonzero(app)[0]
    summ = {}
    for lv in LEVELS:
        items = [((int(i), j), tuple(X[i]), seed_of(lv, "ref", int(i), j)) for i in idx for j in range(REF_STAGE1)]
        rows = run_points(lv, "reference", [(f"{k[0]}:{k[1]}", x, s) for k, x, s in items], workers)
        fails = np.zeros(len(X), int); nreal = np.zeros(len(X), int)
        for i in idx:
            for j in range(REF_STAGE1):
                r = rows[f"{i}:{j}"]; nreal[i] += r["realised"]; fails[i] += r["realised"] and r["margin"] < 0
        top = _stage2(fails.reshape(shape), A).ravel() | (app & (nreal < MIN_REAL_TRUTH))
        items2 = [(f"{i}:{j}", tuple(X[i]), seed_of(lv, "ref", int(i), j)) for i in np.nonzero(top)[0] for j in range(REF_STAGE1, REF_STAGE2)]
        rows = run_points(lv, "reference", items2, workers)
        n_tot = np.zeros(len(X), int); nreal[:] = 0; fails[:] = 0
        msum = np.zeros(len(X)); msq = np.zeros(len(X)); coll = np.zeros(len(X), int); gates = {}
        for r in rows.values():
            i = int(r["key"].split(":")[0]); n_tot[i] += 1
            if r["realised"]:
                nreal[i] += 1; fails[i] += r["margin"] < 0; msum[i] += r["margin"]; msq[i] += r["margin"] ** 2; coll[i] += r["collided"]
            for b in r["bad"]: gates[b] = gates.get(b, 0) + 1
        p_raw = np.where(nreal > 0, fails / np.maximum(nreal, 1), np.nan)
        p_iso = isotonic(p_raw.reshape(shape), nreal.reshape(shape), A).ravel()
        mean = np.where(nreal > 0, msum / np.maximum(nreal, 1), np.nan)
        sd = np.sqrt(np.maximum(msq / np.maximum(nreal, 1) - mean ** 2, 0) * nreal / np.maximum(nreal - 1, 1))
        np.savez_compressed(OUT / f"reference_{lv}.npz", V=V, VR=VR, T=T, applicable=A, n=n_tot.reshape(shape), realised=nreal.reshape(shape),
                            fails=fails.reshape(shape), p_raw=p_raw.reshape(shape), p_iso=p_iso.reshape(shape), mean=mean.reshape(shape),
                            sd=sd.reshape(shape), collided=coll.reshape(shape), stage2=top.reshape(shape))
        tr = app & (nreal >= MIN_REAL_TRUTH)
        summ[lv] = dict(level=LEVELS[lv].dict(), applicable=int(app.sum()), runs=int(n_tot.sum()), stage2_points=int(top.sum()),
                        no_verdict_share=float(1 - nreal[app].sum() / n_tot[app].sum()), not_realised_by_gate=gates,
                        truth_points=int(tr.sum()), target_share=float(np.mean(p_iso[tr] >= M.ALPHA)),
                        p_half_share=float(np.mean(p_iso[tr] >= 0.5)), any_fail_share=float(np.mean(fails[tr] > 0)),
                        collisions=int(coll.sum()), iso_change_mean_abs=float(np.nanmean(np.abs(p_iso[tr] - p_raw[tr]))),
                        lines_with_multiple_raw_crossings=_multi_cross(p_raw.reshape(shape), (tr).reshape(shape)),
                        boundary_points=int(len(boundary_points(p_iso.reshape(shape), tr.reshape(shape)))),
                        margin_sd_quantiles_10_50_90=_q(sd[tr & (nreal >= REF_STAGE1)], (0.1, 0.5, 0.9)))
        print(lv, summ[lv], flush=True)
    (OUT / "reference_summary.json").write_text(json.dumps(summ, indent=1))
    return summ


def _q(a, qs):
    a = a[np.isfinite(a)]
    return [float(np.quantile(a, q)) for q in qs] if len(a) else None


def isotonic(p, w, ok):
    """p(x) non-increasing in TTC_LaneIntrusion along each (ego speed, v_rel) line, weighted by realised runs."""
    out = np.full(p.shape, np.nan)
    for a in range(p.shape[0]):
        for b in range(p.shape[1]):
            m = ok[a, b] & (w[a, b] > 0)
            if m.sum() >= 1:
                ir = IsotonicRegression(increasing=False, y_min=0.0, y_max=1.0)
                out[a, b, m] = ir.fit_transform(T[m], p[a, b, m], sample_weight=w[a, b, m])
    return out


def _multi_cross(p, ok):
    c = 0
    for a in range(p.shape[0]):
        for b in range(p.shape[1]):
            s = (p[a, b][ok[a, b]] >= M.ALPHA).astype(int)
            c += int(np.sum(np.abs(np.diff(s))) > 1)
    return c


def boundary_points(p, ok):
    """Crossings of p_iso = ALPHA along TTC lines between neighbouring truth points (linear interpolation)."""
    pts = []
    for a in range(p.shape[0]):
        for b in range(p.shape[1]):
            for c in range(p.shape[2] - 1):
                if ok[a, b, c] and ok[a, b, c + 1] and (p[a, b, c] >= M.ALPHA) != (p[a, b, c + 1] >= M.ALPHA):
                    w = (p[a, b, c] - M.ALPHA) / (p[a, b, c] - p[a, b, c + 1])
                    pts.append([V[a], VR[b], T[c] + w * (T[c + 1] - T[c])])
    return np.array(pts).reshape(-1, 3)


def load_ref(lv):
    z = np.load(OUT / f"reference_{lv}.npz")
    return {k: z[k] for k in z.files}


# ----------------------------------------------------------------------------------------------- campaigns
def applicable_stream(arm, i, n):
    s = seed_of("design", i) % 2 ** 32 if arm != "random" else seed_of("random", i) % 2 ** 32
    U = GP.sobol_unit(8192, s) if arm != "random" else np.random.default_rng(s).random((8192, 3))
    U = U[D.applicable(D.from_unit(U))]
    assert len(U) >= n
    return U[:n]


def fit(rows, kind, lv, i, n):
    ok = [r for r in rows[:n] if r["realised"]]
    return M.MODELS[kind](D.to_unit([r["x"] for r in ok]), np.array([r["margin"] for r in ok]), seed_of("gp", lv, i, n) % 2 ** 31)


def _pool(lv, i, n):
    pool = GP.sobol_unit(GP.CFG["pool"] * 2, seed_of("pool", lv, i, n) % 2 ** 32)
    return pool[D.applicable(D.from_unit(pool))]


def campaign(lv, arm, i, workers=4):
    name = f"{arm}_{i}"
    sd = lambda k: seed_of(lv, arm, i, k)
    if arm in ("sobol", "random"):
        U = applicable_stream(arm, i, BUDGET)
        rows = run_points(lv, name, [(k, tuple(D.from_unit(u)), sd(k)) for k, u in enumerate(U)], workers)
        return [rows[k] for k in range(BUDGET)]
    if arm == "hom_al":
        U0, reps, batch, kind = applicable_stream(arm, i, GP.CFG["init"]), 1, GP.CFG["batch"], "hom"
    else:
        U0, reps, batch, kind = applicable_stream(arm, i, HET_INIT), HET_REPS, HET_BATCH, "het"
    U0 = np.repeat(U0, reps, axis=0)
    rows = run_points(lv, name, [(k, tuple(D.from_unit(u)), sd(k)) for k, u in enumerate(U0)], workers)
    ordered = [rows[k] for k in range(len(U0))]
    while len(ordered) < BUDGET:
        n = len(ordered)
        m = fit(ordered, kind, lv, i, n)
        pool = _pool(lv, i, n); mu, s, r = m.predict(pool)
        done = np.unique(D.to_unit([o["x"] for o in ordered]), axis=0)
        B = np.repeat(GP.select_batch(pool, M.straddle(mu, s, r), done, batch), reps, axis=0)[: BUDGET - n]
        rows = run_points(lv, name, [(n + k, tuple(D.from_unit(u)), sd(n + k)) for k, u in enumerate(B)], workers)
        ordered += [rows[n + k] for k in range(len(B))]
    return ordered


def manifest(lv, arm, i, rows):
    return dict(level=LEVELS[lv].dict(), arm=arm, model=MODEL_OF[arm], seed_index=i, budget=BUDGET, alpha=M.ALPHA,
                settings=dict(gp=GP.CFG, hom_noise_bounds=M.HOM_NOISE_BOUNDS, het=dict(init=HET_INIT, batch=HET_BATCH, reps=HET_REPS),
                              tau_noise=N.TAU_NOISE, dt=N.DT, d_safe=D.D_SAFE, gap_cap=D.GAP_CAP, xl=D.XL.tolist(), xu=D.XU.tolist()),
                environment=environment(), runs=[dict(order=k, x=r["x"], seed=r["seed"], realised=r["realised"], margin=r["margin"]) for k, r in enumerate(rows)])


def _campaign_job(a):
    lv, arm, i = a
    rows = campaign(lv, arm, i, workers=1)
    (OUT / "manifests" / lv / f"{arm}_{i}.json").write_text(json.dumps(manifest(lv, arm, i, rows)))
    return a


def campaigns(workers=4):
    """Campaigns run in parallel (one per worker, runs serial inside), because the GP fits between batches are serial."""
    for lv in LEVELS:
        (OUT / "manifests" / lv).mkdir(parents=True, exist_ok=True)
    jobs = [(lv, arm, i) for lv in LEVELS for arm in ("het_al", "hom_al", "sobol", "random") for i in SEEDS]
    t0 = time.time()
    with mp.Pool(workers) as p:
        for k, a in enumerate(p.imap_unordered(_campaign_job, jobs)):
            print(f"campaign {a} done ({k + 1}/{len(jobs)}, {time.time() - t0:.0f} s)", flush=True)
    for lv in LEVELS:
        with open(OUT / f"campaign_runs_{lv}.csv", "w") as f:
            f.write("arm,seed_index,order,ego_speed,v_rel,ttc_li,realised,margin,collided\n")
            for arm in ARMS:
                for i in SEEDS:
                    for k, r in enumerate(load_campaign(lv, arm, i)):
                        f.write(f"{arm},{i},{k},{r['x'][0]},{r['x'][1]},{r['x'][2]},{r['realised']},{r['margin']},{r['collided']}\n")


def load_campaign(lv, arm, i):
    """The stored runs in campaign order (keys are the order); campaign() checked parameters and seeds when it ran them."""
    f = RAW / lv / f"{arm}_{i}.jsonl"
    rows = {}
    for l in f.read_text().splitlines():
        if l.strip():
            r = json.loads(l); rows[r["key"]] = r
    assert all(k in rows for k in range(BUDGET)), f"{lv}/{arm}_{i}: campaign incomplete"
    return [rows[k] for k in range(BUDGET)]


# ----------------------------------------------------------------------------------------------- scoring
def truth(lv):
    R = load_ref(lv); ok = R["applicable"] & (R["realised"] >= MIN_REAL_TRUTH)
    vv, rr, tt = np.meshgrid(R["V"], R["VR"], R["T"], indexing="ij")
    return R, ok, np.stack([vv[ok], rr[ok], tt[ok]], 1), R["p_iso"][ok] >= M.ALPHA


def line_boundary(fail, ok):
    """Per (ego speed, v_rel) line: end of the failure region in TTC: midpoint between the last failing grid point and the
    next one (the line's last TTC if it fails there), or the line's first TTC if nothing fails. fail, ok: (V, VR, T) arrays."""
    b = np.full(fail.shape[:2], np.nan); has = np.zeros(fail.shape[:2], bool)
    for a in range(fail.shape[0]):
        for c in range(fail.shape[1]):
            j = np.nonzero(ok[a, c])[0]
            if not len(j): continue
            f = fail[a, c, j]; t = T[j]
            if f.any():
                k = int(np.nonzero(f)[0][-1]); has[a, c] = True
                b[a, c] = t[k] if k == len(j) - 1 else (t[k] + t[k + 1]) / 2
            else:
                b[a, c] = t[0] - 0.025
    return b, has


def _score(args):
    lv, arm, kind = args
    R, ok, X, tru = truth(lv); Ug = D.to_unit(X)
    B = boundary_points(R["p_iso"], ok); Ub = D.to_unit(B)
    b_ref, h_ref = line_boundary(np.where(ok, R["p_iso"] >= M.ALPHA, False), ok)
    sd_ref = R["sd"][ok]; edges = np.nanquantile(sd_ref, [1 / 3, 2 / 3])          # where: terciles of the reference margin sd
    terc = {"sd_lo": sd_ref <= edges[0], "sd_mid": (sd_ref > edges[0]) & (sd_ref <= edges[1]), "sd_hi": sd_ref > edges[1]}
    out = []
    for i in SEEDS:
        rows = load_campaign(lv, arm, i)
        for n in CHECKPOINTS:
            m = fit(rows, kind, lv, i, n)
            mu, s, r = m.predict(Ug); g = M.g_of(mu, r); pred = g <= 0
            pf = np.zeros(ok.shape, bool); pf[ok] = pred
            b_m, h_m = line_boundary(pf, ok); lines = h_ref | h_m
            row = dict(level=lv, arm=arm, model=kind, seed_index=i, n=n, misclass=float(np.mean(pred != tru)),
                       recall=float(np.mean(pred[tru])) if tru.any() else float("nan"),
                       precision=float(np.mean(tru[pred])) if pred.any() else float("nan"),
                       boundary_err=float(np.mean(np.abs(b_m - b_ref)[lines])) if lines.any() else 0.0,
                       const=float(np.mean(tru)), no_verdict=float(np.mean([not o["realised"] for o in rows[:n]])),
                       **{f"misclass_{k}": float(np.mean((pred != tru)[w])) for k, w in terc.items()},
                       r_median=float(np.median(r)), unique_inputs=int(len(np.unique(np.round([o["x"] for o in rows[:n]], 12), axis=0))))
            if n == BUDGET and len(B):
                mb, sb, rb = m.predict(Ub); gb = M.g_of(mb, rb)
                for lvl in BAND:
                    z = norm.ppf(0.5 + lvl / 2); row[f"contain_{int(lvl * 100)}"] = float(np.mean(np.abs(gb) <= z * sb))
            out.append(row)
    return out


def holm(p):
    p = np.asarray(p, float); o = np.argsort(p); adj = np.empty_like(p); run = 0.0
    for r, k in enumerate(o):
        run = max(run, (len(p) - r) * p[k]); adj[k] = min(1.0, run)
    return adj


def _tests(rows, pairs, metric="misclass"):
    get = lambda lv, arm, model, n: np.array([next(r[metric] for r in rows if r["level"] == lv and r["arm"] == arm and r["model"] == model
                                                  and r["seed_index"] == i and r["n"] == n) for i in SEEDS])
    tests, pv, rev = [], [], []
    for lv in LEVELS:
        for (a, ma), (b, mb) in pairs:
            for n in TEST_N:
                x, y = get(lv, a, ma, n), get(lv, b, mb, n); d = y - x
                p = wilcoxon(x, y, alternative="less").pvalue if np.any(d != 0) else 1.0
                q = wilcoxon(y, x, alternative="less").pvalue if np.any(d != 0) else 1.0
                ratio = [u / v for u, v in zip(x, y) if v > 0]
                tests.append(dict(level=lv, arm=a, vs=b, n=n, metric=metric, wins=int(np.sum(x < y)), losses=int(np.sum(x > y)),
                                  median=float(np.median(x)), vs_median=float(np.median(y)),
                                  median_ratio=float(np.median(ratio)) if ratio else float("nan")))
                pv.append(p); rev.append(q)
    for t, p, q, pr, qr in zip(tests, pv, holm(pv), rev, holm(rev)):
        t.update(p=float(p), p_holm=float(q), helps=bool(q < 0.05 and t["wins"] >= 8 and t["median_ratio"] <= 0.8),
                 p_rev_holm=float(qr), worse=bool(qr < 0.05 and t["losses"] >= 8 and t["median_ratio"] >= 1.25))
    return tests


def score(workers=4):
    jobs = [(lv, arm, MODEL_OF[arm]) for lv in LEVELS for arm in ARMS] + [(lv, a, k) for lv in LEVELS for a, k in SECONDARY]
    with mp.Pool(workers) as p:
        rows = [r for rr in p.map(_score, jobs) for r in rr]
    keys = list(rows[0].keys()) + sorted({k for r in rows for k in r} - set(rows[0].keys()))
    with open(OUT / "metrics.csv", "w") as f:
        f.write(",".join(keys) + "\n")
        for r in rows: f.write(",".join(str(r.get(k, "")) for k in keys) + "\n")
    A = lambda arm: (arm, MODEL_OF[arm])
    primary = _tests(rows, [(A("het_al"), A("hom_al"))])
    secondary = _tests(rows, [(A(a), A(b)) for a in ("het_al", "hom_al") for b in ("sobol", "random")])
    model_only = _tests(rows, [(A("het_al"), ("het_al", "hom"))])
    boundary = _tests(rows, [(A("het_al"), A("hom_al"))], "boundary_err")
    med = lambda lv, arm, model, n, k: float(np.nanmedian([r[k] for r in rows if r["level"] == lv and r["arm"] == arm and r["model"] == model and r["n"] == n]))
    mods = [(a, MODEL_OF[a]) for a in ARMS] + list(SECONDARY)
    summ = dict(primary=primary, secondary=secondary, model_only=model_only, boundary_err_tests=boundary,
                medians={lv: {f"{a}/{m}": {n: {k: med(lv, a, m, n, k) for k in ("misclass", "boundary_err", "recall", "precision", "no_verdict",
                                                                                   "misclass_sd_lo", "misclass_sd_mid", "misclass_sd_hi")}
                                            for n in TEST_N} for a, m in mods} for lv in LEVELS},
                const={lv: float(next(r["const"] for r in rows if r["level"] == lv)) for lv in LEVELS},
                calibration={lv: {f"{a}/{m}": {int(b * 100): [float(f([r[f"contain_{int(b * 100)}"] for r in rows if r["level"] == lv and r["arm"] == a
                                                                     and r["model"] == m and r["n"] == BUDGET])) for f in (np.mean, np.min, np.max)]
                                                for b in BAND} for a, m in mods} for lv in LEVELS},
                calibration_verdict={lv: {f"{a}/{m}": _calib(np.mean([r["contain_95"] for r in rows if r["level"] == lv and r["arm"] == a and r["model"] == m
                                                                     and r["n"] == BUDGET])) for a, m in mods} for lv in LEVELS},
                no_verdict_flags=[dict(level=t["level"], arm=t["arm"], vs=t["vs"], n=t["n"], diff_pp=100 * (med(t["level"], t["arm"], MODEL_OF[t["arm"]], t["n"], "no_verdict")
                                                                                                     - med(t["level"], t["vs"], MODEL_OF[t["vs"]], t["n"], "no_verdict")))
                                  for t in primary + secondary if abs(med(t["level"], t["arm"], MODEL_OF[t["arm"]], t["n"], "no_verdict")
                                                                       - med(t["level"], t["vs"], MODEL_OF[t["vs"]], t["n"], "no_verdict")) > 0.10])
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1))
    for t in primary: print(t)
    return summ


def _calib(c):
    return "overconfident" if c < 0.90 else ("conservative" if c > 0.99 else "calibrated")


# ----------------------------------------------------------------------------------------------- replicate predicted boundary points
def _boundary_pick(m, lv, arm, i):
    """N_REP_BOUNDARY applicable points on the arm's predicted boundary: smallest |g| in a fresh Sobol pool, >= 0.1 apart."""
    pool = GP.sobol_unit(8192, seed_of("bpool", lv, arm, i) % 2 ** 32); pool = pool[D.applicable(D.from_unit(pool))]
    mu, s, r = m.predict(pool); g = M.g_of(mu, r)
    chosen = []
    for k in np.argsort(np.abs(g)):
        if all(np.linalg.norm(pool[k] - pool[c]) >= 0.1 for c in chosen):
            chosen.append(int(k))
        if len(chosen) == N_REP_BOUNDARY: break
    return pool[chosen], M.p_of(mu, r)[chosen]


def _replicate_job(a):
    lv, arm, i = a
    rows = load_campaign(lv, arm, i); m = fit(rows, MODEL_OF[arm], lv, i, BUDGET)
    P, p_pred = _boundary_pick(m, lv, arm, i)
    items = [(f"{k}_{j}", tuple(D.from_unit(u)), seed_of(lv, "bnd", arm, i, k, j)) for k, u in enumerate(P) for j in range(REP_BOUNDARY)]
    rr = run_points(lv, f"boundary_reps_{arm}_{i}", items, 1)
    out = []
    for k, u in enumerate(P):
        real = [rr[f"{k}_{j}"] for j in range(REP_BOUNDARY) if rr[f"{k}_{j}"]["realised"]]
        out.append(dict(level=lv, arm=arm, seed_index=i, x=D.from_unit(u).tolist(), p_pred=float(p_pred[k]), realised=len(real),
                        fails=int(sum(r["margin"] < 0 for r in real))))
    return out


def replicate(workers=4):
    with mp.Pool(workers) as p:
        out = [r for rr in p.map(_replicate_job, [(lv, arm, i) for lv in LEVELS for arm in ARMS for i in SEEDS]) for r in rr]
    summ = {}
    for lv in LEVELS:
        for arm in ARMS:
            o = [r for r in out if r["level"] == lv and r["arm"] == arm]
            k, n = sum(r["fails"] for r in o), sum(r["realised"] for r in o)
            lo, hi = wilson(k, n)
            summ[f"{lv}/{arm}"] = dict(points=len(o), runs=n, fails=k, p_emp=k / n if n else float("nan"), ci95=[lo, hi],
                                       on_target=bool(SPRT["p0"] <= k / max(n, 1) <= SPRT["p1"]),
                                       no_verdict=1 - n / (len(o) * REP_BOUNDARY))
    (OUT / "boundary_reps.json").write_text(json.dumps(dict(points=out, summary=summ), indent=1)); print(json.dumps(summ, indent=1))
    return summ


def wilson(k, n, z=1.96):
    if n == 0: return float("nan"), float("nan")
    p = k / n; c = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n); m = (p + z * z / (2 * n)) / (1 + z * z / n)
    return float(m - c), float(m + c)


# ----------------------------------------------------------------------------------------------- reruns a verdict needs
def sprt_runs(p, q, rng, reps=400):
    """Wald SPRT on pass/fail, H0: p <= p0 against H1: p >= p1, both errors SPRT['err']; each attempt is realised with
    probability 1 - q. Returns (mean attempts, mean realised runs, share deciding 'p >= ALPHA', share undecided at n_max)."""
    p0, p1, e, nmax = SPRT["p0"], SPRT["p1"], SPRT["err"], SPRT["n_max"]
    A, B = np.log((1 - e) / e), np.log(e / (1 - e)); lf, lp = np.log(p1 / p0), np.log((1 - p1) / (1 - p0))
    att, real, fail_dec, und = [], [], 0, 0
    for _ in range(reps):
        s, n, a = 0.0, 0, 0
        while n < nmax and a < 20 * nmax:
            a += 1
            if rng.random() < q: continue
            n += 1; s += lf if rng.random() < p else lp
            if s >= A: fail_dec += 1; break
            if s <= B: break
        else:
            und += 1
        att.append(a); real.append(n)
    return float(np.mean(att)), float(np.mean(real)), fail_dec / reps, und / reps


@lru_cache(maxsize=None)
def _qfactors():
    nmin, nmax, c = QRULE["n_min"], QRULE["n_max"], QRULE["conf"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)      # boost's nct quantile warns internally; values checked in tests
        k1 = {n: float(nct.ppf(c, n - 1, M.Z_A * np.sqrt(n)) / np.sqrt(n)) for n in range(nmin, nmax + 1)}
        k0 = {n: float(nct.ppf(1 - c, n - 1, M.Z_A * np.sqrt(n)) / np.sqrt(n)) for n in range(nmin, nmax + 1)}
    return k1, k0


def qrule_runs(margins, q, rng):
    """Gaussian quantile rule on the margins: after n >= 2 realised runs, the ALPHA-quantile of the margin, m - Z_A sd, has a
    one-sided 95 % lower bound ybar - k1 s and upper bound ybar - k0 s (noncentral t). Pass (p < ALPHA) when the lower bound > 0,
    fail when the upper bound < 0. Runs are bootstrap draws from the point's stored realised margins."""
    nmin, nmax, B = QRULE["n_min"], QRULE["n_max"], QRULE["boot"]
    k1, k0 = _qfactors()
    att, real, fail_dec, und = [], [], 0, 0
    for _ in range(B):
        n, a, s1, s2, done = 0, 0, 0.0, 0.0, False
        draws = margins[rng.integers(len(margins), size=nmax)]
        while n < nmax and a < 20 * nmax:
            a += 1
            if rng.random() < q: continue
            y = float(draws[n]); n += 1; s1 += y; s2 += y * y
            if n >= nmin:
                yb = s1 / n; s = np.sqrt(max(s2 - n * yb * yb, 0.0) / (n - 1))
                if yb - k1[n] * s > 0: done = True; break
                if yb - k0[n] * s < 0: fail_dec += 1; done = True; break
        und += not done
        att.append(a); real.append(n)
    return float(np.mean(att)), float(np.mean(real)), fail_dec / B, und / B


BANDS = (("p = 0 (no fail seen)", 0.0, 0.0), ("0 < p < 0.05", 1e-12, 0.05), ("0.05 <= p < 0.2 (near ALPHA)", 0.05, 0.2),
         ("0.2 <= p < 0.5", 0.2, 0.5), ("p >= 0.5", 0.5, 1.0))


def reruns(workers=4):
    out = {}
    for lv in LEVELS:
        R = load_ref(lv); rows = run_points(lv, "reference", [], workers)
        by = {}
        for r in rows.values():
            by.setdefault(int(r["key"].split(":")[0]), []).append(r)
        ok = (R["applicable"] & (R["realised"] >= MIN_REAL_TRUTH)).ravel(); P = R["p_raw"].ravel(); Q = 1 - (R["realised"] / np.maximum(R["n"], 1)).ravel()
        rng = np.random.default_rng(seed_of("reruns", lv) % 2 ** 32)
        res = []
        for i in np.nonzero(ok)[0]:
            m = np.array([r["margin"] for r in by[int(i)] if r["realised"]])
            sp = sprt_runs(P[i], Q[i], rng, reps=100); qr = qrule_runs(m, Q[i], rng)
            res.append(dict(i=int(i), p=float(P[i]), q=float(Q[i]), n_ref=int(len(m)), sprt=sp, qrule=qr))
        bands = {}
        for name, lo, hi in BANDS:
            s = [r for r in res if (r["p"] == 0 if hi == 0 else lo <= r["p"] < hi or (hi == 1.0 and r["p"] == 1.0))]
            if not s: continue
            f = lambda key, j: [float(np.median([r[key][j] for r in s])), float(np.quantile([r[key][j] for r in s], 0.9))]
            bands[name] = dict(points=len(s), sprt_attempts_median_p90=f("sprt", 0), sprt_undecided_mean=float(np.mean([r["sprt"][3] for r in s])),
                               qrule_attempts_median_p90=f("qrule", 0), qrule_undecided_mean=float(np.mean([r["qrule"][3] for r in s])),
                               qrule_says_fail_mean=float(np.mean([r["qrule"][2] for r in s])), sprt_says_fail_mean=float(np.mean([r["sprt"][2] for r in s])))
        out[lv] = dict(points=len(res), bands=bands, all_sprt_attempts_mean=float(np.mean([r["sprt"][0] for r in res])),
                       all_qrule_attempts_mean=float(np.mean([r["qrule"][0] for r in res])))
        print(lv, json.dumps(out[lv], indent=1), flush=True)
    (OUT / "reruns.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    step = sys.argv[1]; w = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    steps = dict(portcheck=portcheck, broken=broken, reference=reference, campaigns=campaigns, score=score, replicate=replicate, reruns=reruns)
    OUT.mkdir(parents=True, exist_ok=True)
    for s in (("portcheck", "broken", "reference", "campaigns", "score", "replicate", "reruns") if step == "all" else (step,)):
        print("==", s, flush=True); steps[s](w)
