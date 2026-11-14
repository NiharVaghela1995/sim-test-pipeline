"""GP surrogate and active learning, ported from Project 2 (ls_hz001_deep_dive/wp5/boundary_model.py and
wp6/acquisition.py) and simplified per docs/GP_BOUNDARY_PLAN.md: one fixed kernel, no noise surface, no OCBA."""
import hashlib
import warnings
import numpy as np
from scipy.stats import qmc
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from . import scenario as S

XL, XU = np.array(S.XL), np.array(S.XU)
CFG = dict(nu=2.5, length_scale_init=0.3, length_scale_bounds=(0.01, 10.0), const_bounds=(1e-2, 1e2), noise_init=1e-4,
           noise_bounds=(1e-8, 1e-1), restarts=5, beta=1.96, pool=2048, batch=10, init=30, min_dist=0.05)


def seed_of(*parts):
    return int.from_bytes(hashlib.sha256(("gpb:" + ":".join(str(p) for p in parts)).encode()).digest()[:4], "little")


def to_unit(X):
    return (np.asarray(X, float) - XL) / (XU - XL)


def from_unit(U):
    return XL + np.asarray(U, float) * (XU - XL)


def kernel():
    c = CFG
    return (ConstantKernel(1.0, c["const_bounds"]) * Matern(length_scale=[c["length_scale_init"]] * 3, length_scale_bounds=c["length_scale_bounds"], nu=c["nu"])
            + WhiteKernel(c["noise_init"], c["noise_bounds"]))


def fit(U, y, seed):
    gp = GaussianProcessRegressor(kernel(), normalize_y=True, n_restarts_optimizer=CFG["restarts"], random_state=seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        gp.fit(np.asarray(U, float), np.asarray(y, float))
    return gp


def predict(gp, U, chunk=8192):
    U = np.asarray(U, float); mu = np.empty(len(U)); sd = np.empty(len(U))
    for a in range(0, len(U), chunk):
        mu[a:a + chunk], sd[a:a + chunk] = gp.predict(U[a:a + chunk], return_std=True)
    return mu, sd


def straddle(mu, sd, beta=CFG["beta"]):
    """Bryan et al. (NIPS 2005): large where the model is both near the threshold (margin 0) and unsure."""
    return beta * sd - np.abs(mu)


def sobol_unit(n, seed):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)      # balance warning for n not a power of 2
        return qmc.Sobol(d=3, scramble=True, seed=seed).random(n)


def select_batch(pool, scores, history, k, min_dist=CFG["min_dist"]):
    """Project 2's select_batch_space_filling: highest scores first, at least min_dist from every earlier run and from
    the batch; if the batch cannot be filled, the rest is taken in score order without the distance rule."""
    order = np.argsort(-scores, kind="stable")
    hist = np.asarray(history, float).reshape(-1, pool.shape[1])
    chosen = []
    for i in order:
        if len(chosen) == k: break
        c = pool[i]
        if len(hist) and np.min(np.linalg.norm(hist - c, axis=1)) < min_dist: continue
        if chosen and np.min(np.linalg.norm(pool[chosen] - c, axis=1)) < min_dist: continue
        chosen.append(int(i))
    for i in order:
        if len(chosen) == k: break
        if int(i) not in chosen: chosen.append(int(i))
    return pool[chosen]


def next_batch(U_done, y_done, seed_index, n_done):
    gp = fit(U_done, y_done, seed_of("gp", seed_index, n_done))
    pool = sobol_unit(CFG["pool"], seed_of("pool", seed_index, n_done))
    mu, sd = predict(gp, pool)
    return select_batch(pool, straddle(mu, sd), U_done, CFG["batch"])
