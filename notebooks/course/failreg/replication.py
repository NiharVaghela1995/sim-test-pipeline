"""Explore or replicate (course Module 17). Sites are candidate points already picked; the rules decide how many runs
each gets.

  fixed            equal replicates per site
  ocba             Chen & Lee 2011, Theorem 3.2: asymptotically optimal for selecting the BEST site (wrong target here)
  threshold_alloc  N_i proportional to s_i^2 / (|m_i - tau| + eps)^2, or 1 / KL(alpha || p_i) for pass/fail sites.
                   The review's own derivation, valid only for large budgets (course Module 17 says so)
  apt              Locatelli et al. 2016: pull argmin sqrt(T_k) (|mu_k - tau| + eps); pull each arm n_init times first
  imspe_choice     replicate-or-explore by one-step IMSPE: compare the integrated predictive variance after one new site
                   with that after one more replicate at an existing site (a one-step version of Binois et al. 2019)
"""
import numpy as np


def fixed(K, total):
    n = np.full(K, total // K)
    n[: total - n.sum()] += 1
    return n


def ocba(means, sds, total, minimise=True):
    """Fractions of `total`: N_i / N_j = ((s_i / d_i) / (s_j / d_j))^2 for non-best i, j;
    N_b = s_b sqrt(sum_{i != b} N_i^2 / s_i^2); d_i = gap to the best mean."""
    m = np.asarray(means, float) * (1 if minimise else -1)
    s = np.maximum(np.asarray(sds, float), 1e-12)
    b = int(np.argmin(m))
    d = np.maximum(np.abs(m - m[b]), 1e-12)
    r = (s / d) ** 2
    r[b] = 0.0
    r[b] = s[b] * np.sqrt(np.sum(np.delete(r, b) ** 2 / np.delete(s, b) ** 2))
    return total * r / r.sum()


def threshold_alloc(means, sds, tau, total, eps=0.0, rate="gaussian"):
    m = np.asarray(means, float)
    if rate == "gaussian":
        r = np.maximum(np.asarray(sds, float), 1e-12) ** 2 / np.maximum(np.abs(m - tau) + eps, 1e-6) ** 2
    else:
        a = float(tau); sign = np.where(m >= a, 1.0, -1.0)
        q = np.clip(a + sign * (np.abs(m - a) + eps), 1e-9, 1 - 1e-9)
        r = 1 / np.maximum(a * np.log(a / q) + (1 - a) * np.log((1 - a) / (1 - q)), 1e-12)
    return total * r / r.sum()


def integerise(frac, total):
    """Largest-remainder rounding of fractional allocations to integers summing to total."""
    n = np.floor(frac).astype(int); rem = total - n.sum()
    n[np.argsort(-(frac - n))[:rem]] += 1
    return n


def apt(pull, K, tau, budget, eps=0.0, n_init=1):
    """APT for `budget` pulls; pull(k) returns one reward. Returns (estimated means, pulls per arm)."""
    s, c = np.zeros(K), np.zeros(K)
    for k in range(K):
        for _ in range(n_init):
            s[k] += pull(k); c[k] += 1
    for _ in range(budget - K * n_init):
        k = int(np.argmin(np.sqrt(c) * (np.abs(s / c - tau) + eps)))
        s[k] += pull(k); c[k] += 1
    return s / c, c


def imspe_choice(model, X, new, ref):
    """For a homoskedastic GP: the IMSPE on ref after one run at the best new candidate versus after one replicate at
    the best existing site. Returns ('explore' or 'replicate', point, (imspe_new, imspe_rep))."""
    xs = np.unique(np.round(np.asarray(X, float), 10), axis=0)
    cand = np.vstack([new, xs])
    U = np.vstack([ref, cand])
    C = model.cov(U)
    nr = len(ref)
    k = C[:nr, nr:]
    v = np.maximum(np.diag(C)[nr:], 1e-12) + model.noise_var
    base = np.diag(C)[:nr].mean()
    after = base - (k ** 2 / v[None, :]).mean(0)
    i_new = int(np.argmin(after[:len(new)])); i_rep = len(new) + int(np.argmin(after[len(new):]))
    if after[i_rep] < after[i_new]:
        return "replicate", cand[i_rep], (after[i_new], after[i_rep])
    return "explore", cand[i_new], (after[i_new], after[i_rep])
