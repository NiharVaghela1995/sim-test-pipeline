"""POST HOC (decided after the plan): where does the GP-AL 95% band miss the reference boundary?

Reference boundary points are split by their gap line: lines with one sign change (monotone in gap) and lines with
more than one (the non-monotone stretch at small gaps, where the ACC detects the cutting car earlier).

  python -m stp.cutin.band_misses [workers]   -> results/gp_boundary/band_misses.json
"""
import collections
import json
import multiprocessing as mp
import sys
import numpy as np
from scipy.stats import norm
from . import campaign as C, gp as GP, metrics as M, reference as REF


def _one(i):
    R = M.ref(); r = REF.load()
    iv, idv, gc = REF.crossings(r["margin"])
    cnt = collections.Counter(zip(iv, idv)); multi = np.array([cnt[k] > 1 for k in zip(iv, idv)])
    g = C.model_at(C.run_campaign("gp_al", i), i, 300)
    mu, sd = GP.predict(g, R["Ub"]); miss = np.abs(mu) > norm.ppf(0.975) * sd
    return dict(seed=i, miss_share=float(miss.mean()), miss_multi=float(miss[multi].mean()), miss_single=float(miss[~multi].mean()),
                miss_gap_max=float(gc[miss].max()) if miss.any() else None, multi_share=float(multi.mean()), points=int(len(gc)))


def main(workers=3):
    with mp.Pool(workers) as p:
        rows = p.map(_one, C.SEEDS)
    out = dict(post_hoc=True, arm="gp_al", n=300, level=0.95, per_seed=rows,
               mean_miss_single=float(np.mean([r["miss_single"] for r in rows])), mean_miss_multi=float(np.mean([r["miss_multi"] for r in rows])),
               max_miss_gap=max(r["miss_gap_max"] or 0 for r in rows))
    (C.OUT / "band_misses.json").write_text(json.dumps(out, indent=1)); print(json.dumps({k: v for k, v in out.items() if k != "per_seed"}))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
