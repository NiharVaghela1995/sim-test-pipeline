"""R157 rule on the esmini ACC cut-in: reference grid, GP-AL / Sobol / random campaigns, scoring, compliance report, hold-out
check runs, replication. Plan: docs/R157_PLAN.md (committed before any of this ran). Settings are the GP demo's (cutin/gp.py)
except that every design point, pool point and grid point lies in the region where R157 para. 5.2.5.2 applies.

  PYTHONPATH=src .venv/bin/python -m stp.r157.experiment reference|campaigns|score|compliance|replicate|broken|all [workers]
"""
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path
import numpy as np
from scipy.stats import beta as Beta, norm, wilcoxon
from ..cutin import gp as GP, scenario as S, runner as CR
from ..cutin.campaign import environment
from . import design as D, runner as RR

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/r157"
RAW = ROOT / "results/raw/r157"
ARMS = ("gp_al", "sobol", "random")
SEEDS = tuple(range(10))
BUDGET = 300
CHECKPOINTS = tuple(range(40, 301, 20))
LEVELS = (0.5, 0.8, 0.9, 0.95, 0.99)
ESMINI_SEED = 0
HI, LO = 0.95, 0.05
N_HOLDOUT = 200

V = np.round(np.r_[np.arange(10.0, 16.5 + 1e-9, 0.5), 50.0 / 3.0], 10)
VR = np.round(np.arange(0.5, 8.0 + 1e-9, 0.5), 10)
T = np.round(np.arange(0.2, 3.0 + 1e-9, 0.025), 10)


def seed_of(*p):
    return int.from_bytes(hashlib.sha256(("r157:" + ":".join(map(str, p))).encode()).digest()[:4], "little")


# ----------------------------------------------------------------------------------------------- runs
def _one(a):
    key, x, seed = a
    r = RR.run(x, seed)
    return dict(key=key, x=[float(v) for v in x], seed=seed, realised=r["realised"], margin=r["margin"], min_gap=r["min_gap"],
                collided=r["collided"], overbrake=r["overbrake"], applicable=r["applicable"], ttc_li_meas=r["ttc_li_meas"],
                ttc_li_actual=r["ttc_li_actual"], ego_speed_at_ref=r["ego_speed_at_ref"],
                bad=[k for k, v in r["gates"].items() if not v])


def run_points(name, items, workers=4):
    f = RAW / f"{name}.jsonl"; f.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    if f.exists():
        for l in f.read_text().splitlines():
            if l.strip():
                r = json.loads(l); rows[r["key"]] = r
    todo = [it for it in items if it[0] not in rows]
    if todo:
        t0 = time.time()
        with mp.Pool(workers) as p, open(f, "a") as o:
            for r in p.imap_unordered(_one, todo, chunksize=20):
                o.write(json.dumps(r) + "\n"); rows[r["key"]] = r
        print(f"{name}: {len(todo)} runs in {time.time() - t0:.0f} s", flush=True)
    for k, x, _ in items:
        if not np.allclose(rows[k]["x"], x, rtol=0, atol=1e-12):
            raise RuntimeError(f"{name}: stored run {k} has other parameters; refusing to resume")
    return rows


# ----------------------------------------------------------------------------------------------- reference grid
def grid():
    vv, rr, tt = np.meshgrid(V, VR, T, indexing="ij")
    X = np.stack([vv.ravel(), rr.ravel(), tt.ravel()], 1)
    return X, D.applicable(X)


def reference(workers=4):
    X, app = grid()
    idx = np.nonzero(app)[0]
    rows = run_points("reference", [(int(i), tuple(X[i]), ESMINI_SEED) for i in idx], workers)
    shape = (len(V), len(VR), len(T))
    margin = np.full(len(X), np.nan); real = np.zeros(len(X), bool); coll = np.zeros(len(X), bool); ob = np.zeros(len(X), bool)
    for i in idx:
        r = rows[int(i)]; real[i] = r["realised"]; margin[i] = r["margin"]; coll[i] = r["collided"]; ob[i] = r["overbrake"]
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / "reference_grid.npz", V=V, VR=VR, T=T, applicable=app.reshape(shape), realised=real.reshape(shape),
                        margin=margin.reshape(shape), collided=coll.reshape(shape), overbrake=ob.reshape(shape))
    s = dict(points=int(len(X)), applicable=int(app.sum()), realised=int(real.sum()),
             fail_share=float(np.mean(margin[real] < 0)), collided=int(coll[real].sum()),
             not_realised_by_gate=_count([rows[int(i)]["bad"] for i in idx]))
    (OUT / "reference_summary.json").write_text(json.dumps(s, indent=1)); print(s)
    return s


def _count(lists):
    c = {}
    for l in lists:
        for k in l: c[k] = c.get(k, 0) + 1
    return c


def load_ref():
    z = np.load(OUT / "reference_grid.npz")
    return {k: z[k] for k in z.files}


# ----------------------------------------------------------------------------------------------- designs and campaigns
def applicable_stream(arm, i, n):
    """First n applicable points of the arm's seeded stream (Sobol for sobol and gp_al, uniform for random), in unit space."""
    s = seed_of("design", i) if arm in ("sobol", "gp_al") else seed_of("random", i)
    U = GP.sobol_unit(8192, s) if arm in ("sobol", "gp_al") else np.random.default_rng(s).random((8192, 3))
    U = U[D.applicable(D.from_unit(U))]
    assert len(U) >= n
    return U[:n]


def fit(rows, i, n):
    ok = [r for r in rows[:n] if r["realised"]]
    return GP.fit(D.to_unit([r["x"] for r in ok]), np.array([r["margin"] for r in ok]), seed_of("gp", i, n))


def next_batch(rows, i):
    n = len(rows); gp = fit(rows, i, n)
    pool = GP.sobol_unit(GP.CFG["pool"] * 2, seed_of("pool", i, n))
    pool = pool[D.applicable(D.from_unit(pool))]
    mu, sd = GP.predict(gp, pool)
    done = D.to_unit([r["x"] for r in rows])
    return GP.select_batch(pool, GP.straddle(mu, sd), done, GP.CFG["batch"])


def campaign(arm, i, workers=4):
    name = f"{arm}_{i}"
    if arm != "gp_al":
        U = applicable_stream(arm, i, BUDGET)
        rows = run_points(name, [(k, tuple(D.from_unit(u)), ESMINI_SEED) for k, u in enumerate(U)], workers)
        return [rows[k] for k in range(BUDGET)]
    U = applicable_stream(arm, i, GP.CFG["init"])
    rows = run_points(name, [(k, tuple(D.from_unit(u)), ESMINI_SEED) for k, u in enumerate(U)], workers)
    ordered = [rows[k] for k in range(len(U))]
    while len(ordered) < BUDGET:
        n = len(ordered)
        B = next_batch(ordered, i)[: BUDGET - n]
        rows = run_points(name, [(n + k, tuple(D.from_unit(u)), ESMINI_SEED) for k, u in enumerate(B)], workers)
        ordered += [rows[n + k] for k in range(len(B))]
    return ordered


def manifest(arm, i, rows):
    gpm = fit(rows, i, len(rows))
    Xg, app = grid(); mu, sd = GP.predict(gpm, D.to_unit(Xg[app]))
    return dict(arm=arm, seed_index=i, budget=BUDGET, settings=dict(gp=GP.CFG, d_safe=D.D_SAFE, gap_cap=D.GAP_CAP, xl=D.XL.tolist(),
                xu=D.XU.tolist(), v_cut_min=D.V_CUT_MIN, sag_max=D.VLONG_SAG_MAX, tyre_half=D.TYRE_HALF, dt=CR.DT, esmini_seed=ESMINI_SEED),
                environment=environment(), runs=[dict(order=k, x=r["x"], realised=r["realised"], margin=r["margin"]) for k, r in enumerate(rows)],
                final_prediction_sha256=hashlib.sha256(mu.tobytes() + sd.tobytes()).hexdigest())


def campaigns(workers=4):
    (OUT / "manifests").mkdir(parents=True, exist_ok=True)
    allrows = {}
    for arm in ARMS:
        for i in SEEDS:
            rows = campaign(arm, i, workers); allrows[(arm, i)] = rows
            (OUT / "manifests" / f"{arm}_{i}.json").write_text(json.dumps(manifest(arm, i, rows)))
    with open(OUT / "campaign_runs.csv", "w") as f:
        f.write("arm,seed_index,order,ego_speed,v_rel,ttc_li,realised,margin,collided\n")
        for (arm, i), rows in allrows.items():
            for k, r in enumerate(rows):
                f.write(f"{arm},{i},{k},{r['x'][0]},{r['x'][1]},{r['x'][2]},{r['realised']},{r['margin']},{r['collided']}\n")
    return allrows


def load_campaign(arm, i):
    return campaign(arm, i, workers=1)    # every run is stored: this only reads


# ----------------------------------------------------------------------------------------------- scoring
def ref_points():
    R = load_ref(); mask = R["applicable"] & R["realised"]
    vv, rr, tt = np.meshgrid(R["V"], R["VR"], R["T"], indexing="ij")
    X = np.stack([vv[mask], rr[mask], tt[mask]], 1)
    return X, R["margin"][mask], R


def boundary_points(R):
    """Sign changes of the reference margin along TTC_LaneIntrusion lines, between realised applicable neighbours."""
    m, ok = R["margin"], R["applicable"] & R["realised"]
    pts = []
    for a in range(m.shape[0]):
        for b in range(m.shape[1]):
            for c in range(m.shape[2] - 1):
                if ok[a, b, c] and ok[a, b, c + 1] and (m[a, b, c] < 0) != (m[a, b, c + 1] < 0):
                    w = -m[a, b, c] / (m[a, b, c + 1] - m[a, b, c])
                    pts.append([R["V"][a], R["VR"][b], R["T"][c] + w * (R["T"][c + 1] - R["T"][c])])
    return np.array(pts).reshape(-1, 3)


def _score(args):
    arm, i = args
    X, truth_m, R = ref_points(); truth = truth_m >= 0
    B = boundary_points(R); Ug, Ub = D.to_unit(X), D.to_unit(B)
    rows = load_campaign(arm, i); out = []
    for n in CHECKPOINTS:
        gpm = fit(rows, i, n)
        mu, sd = GP.predict(gpm, Ug); pred = mu >= 0
        vio = ~truth
        row = dict(arm=arm, seed_index=i, n=n, misclass=float(np.mean(pred != truth)),
                   viol_recall=float(np.mean(~pred[vio])) if vio.any() else float("nan"),
                   viol_precision=float(np.mean(vio[~pred])) if (~pred).any() else float("nan"),
                   const=float(min(np.mean(truth), np.mean(~truth))))
        if n == BUDGET and len(B):
            mb, sb = GP.predict(gpm, Ub)
            for lv in LEVELS:
                z = norm.ppf(0.5 + lv / 2); row[f"contain_{int(lv * 100)}"] = float(np.mean(np.abs(mb) <= z * sb))
        out.append(row)
    return out


def holm(p):
    p = np.asarray(p); o = np.argsort(p); adj = np.empty_like(p); run = 0
    for r, k in enumerate(o):
        run = max(run, (len(p) - r) * p[k]); adj[k] = min(1.0, run)
    return adj


def score(workers=4):
    with mp.Pool(workers) as p:
        rows = [r for rr in p.map(_score, [(a, i) for a in ARMS for i in SEEDS]) for r in rr]
    keys = list(rows[0].keys()) + [k for k in rows[-1].keys() if k not in rows[0]]
    with open(OUT / "metrics.csv", "w") as f:
        f.write(",".join(keys) + "\n")
        for r in rows: f.write(",".join(str(r.get(k, "")) for k in keys) + "\n")
    get = lambda arm, n, k: np.array([next(r[k] for r in rows if r["arm"] == arm and r["seed_index"] == i and r["n"] == n) for i in SEEDS])
    tests, pv = [], []
    for base in ("sobol", "random"):
        for n in (100, 200, 300):
            a, b = get("gp_al", n, "misclass"), get(base, n, "misclass")
            d = b - a
            p = wilcoxon(a, b, alternative="less").pvalue if np.any(d != 0) else 1.0
            ratio = [x / y for x, y in zip(a, b) if y > 0]
            tests.append(dict(baseline=base, n=n, wins=int(np.sum(a < b)), ties=int(np.sum(a == b)), median_ratio=float(np.median(ratio)) if ratio else float("nan"),
                              gp_al_median=float(np.median(a)), base_median=float(np.median(b))))
            pv.append(p)
    for t, p, q in zip(tests, pv, holm(pv)):
        t.update(p=float(p), p_holm=float(q), helps=bool(q < 0.05 and t["wins"] >= 8 and t["median_ratio"] <= 0.8))
    summ = dict(tests=tests, medians={f"{arm}_{n}_{k}": float(np.nanmedian(get(arm, n, k))) for arm in ARMS for n in (100, 200, 300)
                                       for k in ("misclass", "viol_recall")},
                const_misclass=float(rows[0]["const"]),
                calibration={arm: {lv: [float(np.mean(get(arm, BUDGET, f"contain_{lv}"))), float(np.min(get(arm, BUDGET, f"contain_{lv}"))),
                                        float(np.max(get(arm, BUDGET, f"contain_{lv}")))] for lv in (50, 80, 90, 95, 99)} for arm in ARMS},
                runs_needed={arm: {tgt: [next((n for n in CHECKPOINTS if get(arm, n, "misclass")[j] <= tgt), None) for j in range(len(SEEDS))]
                                   for tgt in (0.005, 0.002)} for arm in ARMS})
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1)); print(json.dumps(summ["tests"], indent=1))
    return summ


# ----------------------------------------------------------------------------------------------- compliance + hold-out
def cp_upper(k, n, conf=0.95):
    return 1.0 if n == 0 or k == n else float(Beta.ppf(conf, k + 1, n - k))


def compliance(workers=4):
    rows = load_campaign("gp_al", 0); gpm = fit(rows, 0, BUDGET)
    X, truth_m, R = ref_points(); mu, sd = GP.predict(gpm, D.to_unit(X))
    out = {}
    for label, shift in (("margin_1m", 0.0), ("no_collision", D.D_SAFE)):     # P(min_gap >= d) = Phi((mu + D_SAFE - d)/sd)
        p = norm.cdf((mu + shift) / np.maximum(sd, 1e-12)); truth = (truth_m + shift) >= 0
        reg = np.where(p >= HI, 1, np.where(p <= LO, -1, 0))
        out[label] = dict(share={k: float(np.mean(reg == v)) for k, v in (("compliant", 1), ("violating", -1), ("undecided", 0))},
                          check=dict(compliant_truly_pass=float(np.mean(truth[reg == 1])) if (reg == 1).any() else None,
                                     violating_truly_fail=float(np.mean(~truth[reg == -1])) if (reg == -1).any() else None,
                                     undecided_truly_fail=float(np.mean(~truth[reg == 0])) if (reg == 0).any() else None),
                          truth_fail_share=float(np.mean(~truth)))
    rng = np.random.default_rng(seed_of("holdout"))
    U = rng.random((20000, 3)); U = U[D.applicable(D.from_unit(U))][:N_HOLDOUT]
    hold = run_points("holdout", [(k, tuple(D.from_unit(u)), ESMINI_SEED) for k, u in enumerate(U)], workers)
    hr = [hold[k] for k in range(len(U))]; ok = [r for r in hr if r["realised"]]
    mh, sh = GP.predict(gpm, D.to_unit([r["x"] for r in ok])); ph = norm.cdf(mh / np.maximum(sh, 1e-12))
    passed = np.array([r["margin"] >= 0 for r in ok])
    comp, viol = ph >= HI, ph <= LO
    k1, n1, k2, n2 = int((~passed[comp]).sum()), int(comp.sum()), int(passed[viol].sum()), int(viol.sum())
    out["holdout"] = dict(runs=len(hr), realised=len(ok), compliant_n=n1, compliant_failed=k1, compliant_wrong_upper95=cp_upper(k1, n1),
                          violating_n=n2, violating_passed=k2, violating_wrong_upper95=cp_upper(k2, n2), undecided_n=int((~comp & ~viol).sum()),
                          fails_total=int((~passed).sum()))
    out["manifest_sha256"] = hashlib.sha256((OUT / "manifests/gp_al_0.json").read_bytes()).hexdigest()
    (OUT / "compliance.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
    return out


# ----------------------------------------------------------------------------------------------- replication + broken
def replicate(workers=4):
    pts = []
    for i in SEEDS:
        rows = [r for r in load_campaign("gp_al", i) if r["realised"]]
        pts += [r["x"] for r in sorted(rows, key=lambda r: abs(r["margin"]))[:5]]
    items = [(k * 10 + j, tuple(x), ESMINI_SEED if j < 4 else 987) for k, x in enumerate(pts) for j in range(5)]
    rows = run_points("replicate", items, workers)
    diffs, same = [], 0
    for k, x in enumerate(pts):
        ms = [rows[k * 10 + j]["margin"] for j in range(5)]; vs = [rows[k * 10 + j]["margin"] >= 0 for j in range(5)]
        diffs.append(max(ms) - min(ms)); same += len(set(vs)) == 1
    out = dict(points=len(pts), reruns=len(items), max_margin_spread=float(max(diffs)), verdicts_all_identical=same == len(pts))
    (OUT / "replication.json").write_text(json.dumps(out, indent=1)); print(out)
    return out


def broken():
    sys.path.insert(0, str(ROOT / "tests"))
    from test_cutin import BROKEN
    x = np.array([14.0, 3.0, 1.5]); out = []
    for name, d, _ in BROKEN + [("cutter 1 m/s slower than designed", S.Defects(cut_speed_shift=-1.0), None)]:
        r = RR.run(x, defects=d); out.append(dict(defect=name, realised=r["realised"], failed_gates=sorted(k for k, v in r["gates"].items() if not v)))
    clean = RR.run(x)
    res = dict(clean_realised=clean["realised"], broken=out, all_caught=all(not o["realised"] for o in out))
    (OUT / "broken.json").write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    step = sys.argv[1]; w = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    steps = dict(reference=reference, campaigns=campaigns, score=score, compliance=compliance, replicate=replicate, broken=lambda w: broken())
    for s in (("broken", "reference", "campaigns", "score", "compliance", "replicate") if step == "all" else (step,)):
        print("==", s, flush=True); steps[s](w)
