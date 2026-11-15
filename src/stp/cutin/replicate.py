"""Replication of boundary points (docs/GP_BOUNDARY_PLAN.md, step 4).

Points: per GP-AL seed at 300 runs, the 10 realised runs with the smallest |margin| (100), plus 50 reference grid points
next to a sign change (seeded draw). Each is rerun 10 times: reps 0-4 in this process in order, reps 5-9 in a pool of
4 workers in shuffled order; reps 3 and 8 use esmini seed 987 instead of 0.

  python -m stp.cutin.replicate   -> results/gp_boundary/replication.csv, replication.json
"""
import csv
import json
import multiprocessing as mp
import numpy as np
from . import gp as GP, reference as REF, campaign as C, runner as R, scenario as S

REPS, OTHER_SEED, OTHER_SEED_REPS = 10, 987, (3, 8)


def points():
    pts = []
    for i in C.SEEDS:
        rows = [r for r in C.run_campaign("gp_al", i) if r["realised"]]
        for r in sorted(rows, key=lambda r: abs(r["margin"]))[:10]:
            pts.append(dict(source=f"gp_al_{i}", x=r["x"], margin=r["margin"]))
    ref = REF.load(); m = ref["margin"]
    iv, idv, ig = np.nonzero((m[..., :-1] < 0) != (m[..., 1:] < 0))
    pick = np.random.default_rng(GP.seed_of("replicate")).choice(len(iv), 50, replace=False)
    for k in pick:
        a, b = (iv[k], idv[k], ig[k]), (iv[k], idv[k], ig[k] + 1)
        c = a if abs(m[a]) <= abs(m[b]) else b
        pts.append(dict(source="reference", x=[float(ref["V"][c[0]]), float(ref["G"][c[2]]), float(ref["DV"][c[1]])], margin=float(m[c])))
    return pts


def seed_for(rep):
    return OTHER_SEED if rep in OTHER_SEED_REPS else 0


def _one(a):
    j, rep, x = a
    return j, rep, R.run(S.Params(*x), seed_for(rep))["margin"]


def main():
    pts = points()
    res = {}
    for j, p in enumerate(pts):                                  # reps 0-4, sequential, this process
        for rep in range(5):
            res[(j, rep)] = R.run(S.Params(*p["x"]), seed_for(rep))["margin"]
    tasks = [(j, rep, p["x"]) for j, p in enumerate(pts) for rep in range(5, REPS)]
    np.random.default_rng(1).shuffle(tasks)
    with mp.Pool(4) as pool:
        for j, rep, m in pool.imap_unordered(_one, tasks, chunksize=7):
            res[(j, rep)] = m
    out = []
    for j, p in enumerate(pts):
        ms = np.array([res[(j, r)] for r in range(REPS)])
        out.append(dict(point=j, source=p["source"], ego_speed=p["x"][0], gap=p["x"][1], rel_speed=p["x"][2], original_margin=p["margin"],
                        max_abs_diff=float(np.max(np.abs(ms - p["margin"]))), bitwise_identical=bool(np.all(ms == p["margin"])),
                        verdicts_match=bool(np.all((ms < 0) == (p["margin"] < 0)))))
    with open(C.OUT / "replication.csv", "w", newline="") as f:
        w = csv.DictWriter(f, list(out[0])); w.writeheader(); w.writerows(out)
    summ = dict(points=len(out), runs=len(out) * REPS, bitwise_identical=sum(o["bitwise_identical"] for o in out),
                verdicts_match=sum(o["verdicts_match"] for o in out), max_abs_diff=max(o["max_abs_diff"] for o in out),
                smallest_abs_margin=min(abs(o["original_margin"]) for o in out))
    (C.OUT / "replication.json").write_text(json.dumps(summ, indent=1)); print(summ)


if __name__ == "__main__":
    main()
