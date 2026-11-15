"""POST HOC sensitivity check (added after the plan, at the user's request): the over-braking runs.

In 1.5% of reference runs the ACC drops its speed by more than the 6 m/s^2 limit in one step, always after the
minimum TTC (else the run would not be realised). This module asks
  1. where those runs sit relative to the pass/fail boundary, and
  2. whether leaving them out changes the reference boundary or the GP-AL vs Sobol/random comparison.
For 2, over-braking runs are dropped from each campaign's training data (the designs are kept as run) and over-braking
grid points are dropped from the scoring, then the planned tests are repeated at 100/200/300 runs.

  python -m stp.cutin.overbrake [workers]   -> results/gp_boundary/overbrake.json
"""
import json
import multiprocessing as mp
import sys
import numpy as np
from . import analysis as A, campaign as C, gp as GP, metrics as M, reference as REF


def reference_part():
    z = np.load(REF.OUT / "reference_grid.npz")
    m, ob, G = z["margin"], z["overbrake"], z["G"]
    g_full = REF.boundary_gap(m, G)
    g_excl = np.empty_like(g_full)
    for iv in range(m.shape[0]):
        for idv in range(m.shape[1]):
            keep = ~ob[iv, idv]
            g_excl[iv, idv] = REF.boundary_gap(m[iv, idv][keep][None], G[keep])[0]
    iv, idv, ig = np.nonzero(ob)
    dist = g_full[iv, idv] - G[ig]          # how far below the boundary gap each over-braking run is
    return dict(
        runs=int(ob.size), overbrake=int(ob.sum()), overbrake_share=float(ob.mean()),
        overbrake_failing_share=float((m[ob] < 0).mean()),
        overbrake_margin_min=float(m[ob].min()), overbrake_margin_max=float(m[ob].max()),
        overbrake_gap_min=float(G[ig].min()), overbrake_gap_max=float(G[ig].max()),
        overbrake_ego_speed=[float(z["V"][iv].min()), float(z["V"][iv].max())],
        overbrake_rel_speed=[float(z["DV"][idv].min()), float(z["DV"][idv].max())],
        overbrake_near_boundary_share=float((np.abs(m[ob]) < 0.5).mean()),
        all_near_boundary_share=float((np.abs(m) < 0.5).mean()),
        distance_below_boundary_min=float(dist.min()), distance_below_boundary_median=float(np.median(dist)),
        boundary_change_max=float(np.abs(g_excl - g_full).max()),
    ), g_excl, ob


def _score(args):
    arm, i, n, g_excl, ob = args
    R = dict(M.ref())
    R["ok"] = R["ok"] & ~ob.ravel()
    R["g_star"] = g_excl
    rows = [r for r in C.run_campaign(arm, i)[:n] if not r["overbrake"]]
    U, y = C.fit_data(rows)
    g = GP.fit(U, y, GP.seed_of("gp", i, n))
    mu, _ = GP.predict(g, R["Ug"])
    return dict(arm=arm, seed=i, n=n, model="gp", n_dropped=n - len(rows), **M.score_field(mu, R))


def main(workers=3):
    ref_part, g_excl, ob = reference_part()
    jobs = [(arm, i, n, g_excl, ob) for arm in C.ARMS for i in C.SEEDS for n in A.BUDGETS]
    with mp.Pool(workers) as p:
        rows = p.map(_score, jobs)
    t = A.tests(rows); v, overall = A.verdicts(t)
    tb = A.tests(rows, "berr_mean")
    dropped = {arm: {n: int(sum(r["n_dropped"] for r in rows if r["arm"] == arm and r["n"] == n)) for n in A.BUDGETS} for arm in C.ARMS}
    out = dict(post_hoc=True, reference=ref_part, dropped_from_training=dropped, verdict_per_budget=v, verdict=overall,
               tests_misclass=t, tests_boundary_error=tb)
    (C.OUT / "overbrake.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(ref_part)); print("dropped", dropped); print("verdict excluding over-braking:", overall, v)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
