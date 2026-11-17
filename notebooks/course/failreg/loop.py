"""Seeds, baselines and the search loop shared by the course notebooks.

Every arm on a seed shares the replicate stream and, for active learning, the initial design with the Sobol arm, so
arms can be compared seed by seed (paired). Seeds come from a hash of their names, so adding an arm does not shift
another arm's seeds.
"""
import hashlib
import time
import numpy as np
from scipy.stats import norm
from . import designs as D, metrics as M, models as MD


def seed_of(*parts):
    return int.from_bytes(hashlib.sha256(":".join(map(str, parts)).encode()).digest()[:4], "little")


def threshold(problem, model, U):
    """Threshold on the mean margin for the target {p(x) >= alpha}: tau - s(x) Phi^-1(alpha) with the MODEL's noise
    estimate (so a constant-noise model puts the boundary in the wrong place where the noise varies)."""
    U = np.atleast_2d(U)
    if not problem.noisy or not hasattr(model, "noise_sd"):
        return np.full(len(U), problem.tau)
    return problem.tau - model.noise_sd(U) * norm.ppf(problem.alpha)


def region(problem, model, U):
    if model.kind == "class":
        return model.p_fail(U) >= (problem.alpha if problem.noisy else 0.5)
    mu, _ = model.predict(U)
    return mu < threshold(problem, model, U)


def p_region(problem, model, U):
    """Model probability that x is in the target region."""
    if model.kind == "class":
        return model.p_fail(U)
    mu, sd = model.predict(U)
    return norm.cdf((threshold(problem, model, U) - mu) / np.maximum(sd, 1e-12))


def evaluate(problem, model, boundary=True):
    G, truth, shape, ok = problem.test
    pred = region(problem, model, G)
    sel = slice(None) if ok is None else ok
    out = M.region_scores(truth[sel], pred[sel])
    out["undecided"] = M.undecided(p_region(problem, model, G[sel]))
    if boundary:
        bd = M.boundary_distance(M.boundary_points(truth, shape, ok), M.boundary_points(pred, shape, ok))
        out["boundary_mean"], out["boundary_max"] = bd["mean"], bd["max"]
    return out


def labels(problem, y):
    return (np.asarray(y) < problem.tau).astype(int)


def fit(problem, make_model, X, y):
    """Fit on the runs that produced data (NaN = the run failed its realisation check)."""
    ok = np.isfinite(y); X, y = np.asarray(X)[ok], np.asarray(y)[ok]
    m = make_model()
    return m.fit(X, labels(problem, y) if m.kind == "class" else y)


def static(problem, design, budget, seed, make_model, checkpoints=None):
    """A non-adaptive arm: the design's first n points, refitted at each checkpoint. design(n, d, seed)."""
    checkpoints = checkpoints or [budget]
    rng = np.random.default_rng(seed_of("rep", problem.name, seed))
    X = design(budget, problem.d, seed_of("design", seed))
    y = problem.run(X, rng)
    hist = []
    for n in checkpoints:
        t = time.time()
        m = fit(problem, make_model, X[:n], y[:n])
        hist.append(dict(n=n, **evaluate(problem, m), fit_s=time.time() - t))
    return hist, X, y


def select(scores, pool, X, k, min_dist=0.0):
    """Highest scores first, at least min_dist from every earlier run and each other; fill up in score order."""
    order = np.argsort(-scores, kind="stable"); chosen = []
    for i in order:
        if len(chosen) == k:
            break
        c = pool[i]
        if min_dist > 0 and len(X) and np.min(np.linalg.norm(X - c, axis=1)) < min_dist:
            continue
        if min_dist > 0 and chosen and np.min(np.linalg.norm(pool[chosen] - c, axis=1)) < min_dist:
            continue
        chosen.append(int(i))
    for i in order:
        if len(chosen) == k:
            break
        if int(i) not in chosen:
            chosen.append(int(i))
    return np.array(chosen)


def by_score(score, min_dist=0.02):
    """Turn a score(mu, sd, h) into a batch picker for `active`."""
    def pick(problem, model, pool, X, y, k, state):
        mu, sd = model.predict(pool)
        return select(score(mu, sd, threshold(problem, model, pool)), pool, X, k, min_dist)
    return pick


def active(problem, make_model, pick, budget, seed, n0=10, batch=5, pool_n=1024, checkpoints=None, replicate=1, state=None):
    """Active learning: n0 Sobol points (the same as the Sobol arm's first n0), then batches chosen by `pick`, each new
    site run `replicate` times. Metrics at each checkpoint use the model fitted on the runs so far."""
    checkpoints = sorted(checkpoints or [budget])
    rng = np.random.default_rng(seed_of("rep", problem.name, seed))
    X = D.sobol(n0, problem.d, seed_of("design", seed))
    X = np.repeat(X, replicate, axis=0)
    y = problem.run(X, rng)
    hist, step, state = [], 0, {} if state is None else state
    t0 = time.time()
    while True:
        m = fit(problem, make_model, X, y)
        while checkpoints and len(X) >= checkpoints[0]:
            hist.append(dict(n=checkpoints.pop(0), **evaluate(problem, m), wall_s=time.time() - t0))
        if len(X) >= budget:
            break
        pool = D.sobol(pool_n, problem.d, seed_of("pool", seed, step))
        k = min(batch, (budget - len(X)) // replicate)
        idx = pick(problem, m, pool, X, y, k, state)
        new = np.repeat(pool[idx], replicate, axis=0)
        X = np.vstack([X, new]); y = np.append(y, problem.run(new, rng)); step += 1
    return hist, X, y, m


def table(hists, key, n):
    """Metric `key` at checkpoint n across seeds."""
    return np.array([next(r[key] for r in h if r["n"] == n) for h in hists])
