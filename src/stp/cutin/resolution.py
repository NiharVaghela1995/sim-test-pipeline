"""Resolution check of the reference boundary (docs/GP_BOUNDARY_PLAN.md, Reference).

  python -m stp.cutin.resolution   -> results/gp_boundary/reference_resolution.json, reference_bisection.csv

1. g* from every second gap (0.5 m spacing) against g* from the full 0.25 m grid, over all 651 lines.
2. On 30 random lines with a sign change (seed fixed below), the last sign change refined by bisection to 0.01 m
   with fresh simulations, against the interpolated g* of the full grid."""
import csv
import json
import numpy as np
from . import gp as GP, reference as REF, runner as RUN, scenario as S

N_LINES = 30
TOL = 0.01


def margin_at(v, g, dv):
    r = RUN.run(S.Params(float(v), float(g), float(dv)), REF.REF_SEED)
    assert r["realised"], (v, g, dv, r["gates"])
    return r["margin"]


def bisect(v, dv, lo, hi):
    """lo fails, hi passes; returns the gap where the sign changes, to TOL, and the number of runs used."""
    n = 0
    while hi - lo > TOL:
        mid = 0.5 * (lo + hi); n += 1
        if margin_at(v, mid, dv) < 0: lo = mid
        else: hi = mid
    return 0.5 * (lo + hi), n


def main():
    r = REF.load(); m = r["margin"]; G = r["G"]
    full = REF.boundary_gap(m, G)
    coarse = REF.boundary_gap(m[..., ::2], G[::2])
    e = np.abs(coarse - full)
    out = dict(lines=int(full.size), coarse_vs_full_mean=float(e.mean()), coarse_vs_full_p90=float(np.quantile(e, 0.9)),
               coarse_vs_full_max=float(e.max()))
    # lines with an interior last sign change (not 5 or 40)
    fail = m < 0
    has = fail.any(-1) & ~fail[..., -1]
    cand = np.argwhere(has)
    rng = np.random.default_rng(GP.seed_of("resolution"))
    pick = cand[rng.choice(len(cand), N_LINES, replace=False)]
    rows = []
    for iv, idv in pick:
        line = m[iv, idv]
        i = len(G) - 1 - int(np.argmax((line < 0)[::-1]))
        g_b, n = bisect(r["V"][iv], r["DV"][idv], G[i], G[i + 1])
        rows.append(dict(ego_speed=float(r["V"][iv]), rel_speed=float(r["DV"][idv]), g_star_grid=float(full[iv, idv]),
                         g_star_bisect=float(g_b), abs_diff=float(abs(g_b - full[iv, idv])), runs=n))
    d = np.array([x["abs_diff"] for x in rows])
    out.update(bisect_lines=N_LINES, bisect_tol=TOL, bisect_mean=float(d.mean()), bisect_max=float(d.max()),
               bisect_runs=int(sum(x["runs"] for x in rows)))
    with open(REF.OUT / "reference_bisection.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (REF.OUT / "reference_resolution.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
