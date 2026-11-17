"""Initial designs and non-adaptive baselines on [0, 1]^d (course Module 13, section 2)."""
import itertools
import warnings
import numpy as np
from scipy.spatial.distance import cdist, pdist
from scipy.stats import qmc


def random(n, d, seed=0):
    return np.random.default_rng(seed).random((n, d))


def lhs(n, d, seed=0):
    """Latin hypercube: each of the n intervals of every axis holds exactly one point (Santner et al. 2018)."""
    return qmc.LatinHypercube(d=d, seed=seed).random(n)


def maximin_lhs(n, d, seed=0, tries=50):
    """Best of `tries` random LHS by the largest minimum pairwise distance."""
    best, best_d = None, -1.0
    for k in range(tries):
        X = lhs(n, d, seed=seed * 1000 + k)
        dm = pdist(X).min()
        if dm > best_d:
            best, best_d = X, dm
    return best


def sobol(n, d, seed=0):
    """First n points of a scrambled Sobol' sequence. Balanced at powers of two; any prefix is a valid design."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return qmc.Sobol(d=d, scramble=True, seed=seed).random(n)


def fssf(n, d, seed=0, n_cand=None, X_init=None):
    """Fully-sequential space-filling design, forward version (Shang & Apley 2020): from a large Sobol' candidate set,
    add the candidate furthest from the current design, one at a time (their Algorithm 1, FSSF-f). Every prefix is
    space-filling. Candidate set size N = 1000 d + 2 n and a random first candidate, as in the paper."""
    n_cand = n_cand or 1000 * d + 2 * n
    C = sobol(n_cand, d, seed)
    rng = np.random.default_rng(seed)
    X = [C[rng.integers(n_cand)]] if X_init is None or len(X_init) == 0 else list(np.atleast_2d(X_init))
    dmin = cdist(C, np.array(X)).min(1)
    while len(X) < n:
        k = int(np.argmax(dmin)); X.append(C[k])
        dmin = np.minimum(dmin, cdist(C, C[k:k + 1]).ravel())
    return np.array(X[:n])


def min_distance(X):
    return float(pdist(X).min())


def discrepancy(X):
    """Centred L2 discrepancy (smaller = more uniform)."""
    return float(qmc.discrepancy(X, method="CD"))


def projection_gaps(X, bins=None):
    """Share of the n equal 1-D bins left empty, worst axis. 0 for an LHS by construction."""
    n, d = X.shape
    bins = bins or n
    return max(1 - len(np.unique(np.minimum((X[:, j] * bins).astype(int), bins - 1))) / bins for j in range(d))


# ------------------------------------------------------------ two-level fractional factorials
def fractional_factorial(k, generators):
    """2^(k-p) design in {-1, +1}. The first k-p factors form a full factorial; each generator is a string of base
    factor letters, e.g. 'ABC' sets the next factor to A*B*C. Returns (F, names)."""
    base = k - len(generators)
    names = [chr(ord("A") + i) for i in range(k)]
    F = np.array(list(itertools.product([-1, 1], repeat=base)), float)[:, ::-1]
    cols = [F[:, i] for i in range(base)]
    for g in generators:
        cols.append(np.prod([cols[names.index(c)] for c in g], axis=0))
    return np.column_stack(cols), names


def defining_relation(k, generators):
    """All words of the defining relation I = ... and the resolution (length of the shortest word; Wu & Hamada 2021)."""
    base = k - len(generators)
    names = [chr(ord("A") + i) for i in range(k)]
    gens = [frozenset(g + names[base + i]) for i, g in enumerate(generators)]
    words = set()
    for r in range(1, len(gens) + 1):
        for combo in itertools.combinations(gens, r):
            w = frozenset()
            for g in combo:
                w = w ^ g
            words.add("".join(sorted(w)))
    return sorted(words, key=lambda w: (len(w), w)), min(len(w) for w in words)


# ------------------------------------------------------------ Morris elementary effects
def morris(d, r=10, p=4, seed=0):
    """r Morris trajectories of d + 1 points on a p-level grid, one input changed per step by delta = p / (2 (p - 1))
    (Saltelli et al. 2008, ch. 3). Returns X of shape (r (d + 1), d) and the changed input per step."""
    rng = np.random.default_rng(seed)
    delta = p / (2 * (p - 1))
    levels = np.arange(p) / (p - 1)
    base_levels = levels[levels + delta <= 1 + 1e-12]
    X, which = [], []
    for _ in range(r):
        x = rng.choice(base_levels, d)
        order = rng.permutation(d)
        sign = rng.choice([-1, 1], d)
        start = np.where(sign > 0, x, x + delta)          # make every step stay on the grid
        cur = start.copy(); X.append(cur.copy()); which.append(-1)
        for j in order:
            cur[j] = cur[j] + delta * sign[j]
            X.append(cur.copy()); which.append(j)
    return np.array(X), np.array(which), delta


def morris_effects(X, y, which, d):
    """mu* (mean |EE|) and sigma (sd of EE) per input. EE_i = [y(x + delta e_i) - y(x)] / delta, sign-adjusted."""
    EE = [[] for _ in range(d)]
    for k in range(1, len(X)):
        j = which[k]
        if j < 0:
            continue
        step = X[k, j] - X[k - 1, j]
        EE[j].append((y[k] - y[k - 1]) / step)
    EE = [np.array(e) for e in EE]
    return np.array([np.abs(e).mean() for e in EE]), np.array([e.std(ddof=1) for e in EE])
