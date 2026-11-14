"""Score a design + model against the reference grid (docs/GP_BOUNDARY_PLAN.md, Metrics).

  python -m stp.cutin.metrics [workers]   -> results/gp_boundary/metrics.csv, permutation.csv
"""
import csv
import multiprocessing as mp
import os
import sys
import numpy as np
from scipy.stats import norm
from sklearn.neighbors import KNeighborsClassifier
from . import gp as GP, reference as REF, campaign as C

CHECKPOINTS = tuple(range(40, 301, 20))
LEVELS = (0.5, 0.8, 0.9, 0.95, 0.99)
N_PERM = 19
_REF = {}


def ref():
    """Reference quantities, computed once per process."""
    if not _REF:
        r = REF.load()
        m = r["margin"]; ok = r["realised"]
        iv, idv, gc = REF.crossings(m)
        Ub = GP.to_unit(np.stack([r["V"][iv], gc, r["DV"][idv]], axis=1))
        _REF.update(margin=m, ok=ok.ravel(), cls=(m.ravel() < 0), g_star=REF.boundary_gap(m), Ug=C.grid_units(), Ub=Ub,
                    near=np.abs(m.ravel()) < 0.5, shape=m.shape)
    return _REF


def score_field(pred, R):
    """pred: values on the grid whose sign gives the class (margin estimate or +-1 labels)."""
    ok = R["ok"]
    mis = float(np.mean((pred < 0)[ok] != R["cls"][ok]))
    gh = REF.boundary_gap(pred.reshape(R["shape"]))
    e = np.abs(gh - R["g_star"])
    return dict(misclass=mis, berr_mean=float(e.mean()), berr_p90=float(np.quantile(e, 0.9)))


def score_gp(gp, R):
    mu, sd = GP.predict(gp, R["Ug"])
    out = score_field(mu, R)
    mub, sdb = GP.predict(gp, R["Ub"])
    for q in LEVELS:
        z = norm.ppf(0.5 + q / 2)
        out[f"contain_{int(q * 100)}"] = float(np.mean(np.abs(mub) <= z * sdb))
    z95 = norm.ppf(0.975); near = R["near"] & R["ok"]
    out["cov95_near"] = float(np.mean(np.abs(R["margin"].ravel()[near] - mu[near]) <= z95 * sd[near]))
    out["band_width_mean"] = float(np.mean(2 * z95 * sdb))
    return out


def evaluate(arm, i):
    R = ref()
    rows = C.run_campaign(arm, i)
    out = []
    for n in CHECKPOINTS:
        U, y = C.fit_data(rows[:n])
        g = GP.fit(U, y, GP.seed_of("gp", i, n))
        out.append(dict(arm=arm, seed=i, n=n, model="gp", n_realised=len(y), **score_gp(g, R)))
        lab = np.where(y < 0, -1.0, 1.0)
        knn = KNeighborsClassifier(1).fit(U, lab)
        out.append(dict(arm=arm, seed=i, n=n, model="1nn", n_realised=len(y), **score_field(knn.predict(R["Ug"]), R)))
        const = -1.0 if np.mean(y < 0) > 0.5 else 1.0
        out.append(dict(arm=arm, seed=i, n=n, model="constant", n_realised=len(y), **score_field(np.full(len(R["Ug"]), const), R)))
    return out


def permutation(arm, i, n=300):
    """Log marginal likelihood of the real fit against N_PERM fits to shuffled margins (same procedure)."""
    rows = C.run_campaign(arm, i)
    U, y = C.fit_data(rows[:n])
    real = GP.fit(U, y, GP.seed_of("gp", i, n)).log_marginal_likelihood_value_
    rng = np.random.default_rng(GP.seed_of("perm", arm, i))
    null = [GP.fit(U, rng.permutation(y), GP.seed_of("gp", i, n)).log_marginal_likelihood_value_ for _ in range(N_PERM)]
    return dict(arm=arm, seed=i, n=n, lml_real=float(real), lml_null_max=float(max(null)), lml_null_median=float(np.median(null)),
                p=(1 + sum(v >= real for v in null)) / (N_PERM + 1))


def _eval(a): return evaluate(*a)
def _perm(a): return permutation(*a)


def write(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(rows)


def main(workers=3):
    jobs_ = [(a, i) for i in C.SEEDS for a in C.ARMS]
    with mp.Pool(workers) as p:
        res = [r for rs in p.imap(_eval, jobs_) for r in rs]
        write(C.OUT / "metrics.csv", res); print("metrics rows", len(res), flush=True)
        perm = list(p.imap(_perm, [(a, i) for i in C.SEEDS for a in ("gp_al", "sobol")]))
        write(C.OUT / "permutation.csv", perm); print("permutation rows", len(perm))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
