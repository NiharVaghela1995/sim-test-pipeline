"""Acquisition criteria for a failure boundary (course Module 15). The surrogate gives latent mean mu and sd at pool
points, the threshold is h (a scalar or one value per point). Every score is "run where largest".

  mee         misclassification probability Phi(-|mu - h| / sd); Lyu et al. 2021 eq. 3.2 (MEE)
  straddle    1.96 sd - |mu - h|; Bryan et al. 2005
  mcu         gamma sd - |mu - h| with gamma = IQR(mu) / (3 mean(sd)); Lyu et al. 2021 eq. 3.1 and their recipe
  contour_ei  E[max(0, eps^delta - |h - G|^delta)], eps = kappa sd; delta = 1 Bichon's EFF, delta = 2 Ranjan's
              (written in one family by Bect et al. 2012)
  timse       targeted IMSE: integrated variance reduction weighted near the threshold (Picheny et al. 2010, via Bect et al.)
  sur         one-step lookahead SUR (Bect et al. 2012, Table 1): J3 = E[mean tau_{n+1}] (eq. 24) or
              J1 = E[(mean sqrt(tau_{n+1}))^2], the one they found best; tau = misclassification probability
  ei_fail     expected improvement below the lowest margin so far: failure-seeking, finds the worst point (Jones et al. 1998)
  LSE         level set estimation with intersected confidence intervals (Gotovos et al. 2013)
  GPHedge     portfolio over criteria (Hoffman et al. 2011)
  batch       naive top-B or sequential batch with the variance updated for pending points (Gotovos et al. 2013)
"""
import numpy as np
from scipy.stats import norm


def _t(mu, sd, h):
    return np.abs(mu - h) / np.maximum(sd, 1e-12)


def mee(mu, sd, h):
    return norm.cdf(-_t(mu, sd, h))


def straddle(mu, sd, h, beta_sqrt=1.96):
    return beta_sqrt * sd - np.abs(mu - h)


def mcu_gamma(mu, sd):
    q75, q25 = np.quantile(mu, [0.75, 0.25])
    return (q75 - q25) / (3 * max(np.mean(sd), 1e-12))


def mcu(mu, sd, h, gamma=None):
    g = mcu_gamma(mu, sd) if gamma is None else gamma
    return g * sd - np.abs(mu - h)


def contour_ei(mu, sd, h, kappa=0.5, delta=1, n_grid=801):
    """Bect et al.'s family E[max(0, eps^delta - |h - G|^delta)], G ~ N(mu, sd^2), eps = kappa sd, by quadrature
    (the integrand has kinks at |h - G| = eps)."""
    mu, sd = np.broadcast_arrays(np.atleast_1d(mu).astype(float), np.atleast_1d(sd).astype(float))
    h = np.broadcast_to(h, mu.shape)
    z = np.linspace(-6, 6, n_grid); w = norm.pdf(z) * (z[1] - z[0])
    out = np.empty(len(mu))
    for a in range(0, len(mu), 512):
        G = mu[a:a + 512, None] + sd[a:a + 512, None] * z[None, :]
        eps = kappa * sd[a:a + 512, None]
        out[a:a + 512] = (np.maximum(0, eps ** delta - np.abs(h[a:a + 512, None] - G) ** delta) * w).sum(1)
    return out


def ei_fail(mu, sd, best):
    s = np.maximum(sd, 1e-12); z = (best - mu) / s
    return (best - mu) * norm.cdf(z) + s * norm.pdf(z)


# ------------------------------------------------------------------ lookahead criteria (need the joint covariance)
def _lookahead_parts(model, cand, ref):
    """Latent mean/sd at ref, and for each candidate c the vector b_c(u) = k_n(u, c) / sqrt(s_n^2(c) + noise) that
    gives the one-step update: mu' = mu + b Z, s'^2 = s^2 - b^2, Z ~ N(0, 1)."""
    U = np.vstack([ref, cand])
    mu, sd = model.predict(U)
    C = model.cov(U)
    nr = len(ref)
    noise = model.noise_var if hasattr(model, "noise_var") else 0.0
    kc = C[:nr, nr:]                                         # (n_ref, n_cand)
    vc = np.maximum(np.diag(C)[nr:], 1e-12) + noise
    return mu[:nr], sd[:nr], kc / np.sqrt(vc)[None, :]


def timse(model, cand, ref, h):
    """Variance reduction on ref weighted by the density of the threshold under the prediction,
    W(u) = phi((mu - h) / s) / s (the window weight with no extra noise term)."""
    mu, sd, B = _lookahead_parts(model, cand, ref)
    W = norm.pdf((mu - h) / np.maximum(sd, 1e-12)) / np.maximum(sd, 1e-12)
    return (W[:, None] * B ** 2).mean(0)


def sur(model, cand, ref, h, n_gh=10, kind="J1"):
    """Negative SUR criterion after one more run at each candidate (larger = better). The integral over x is a mean
    over the reference sample; the future run is integrated out by Gauss-Hermite quadrature, as in Bect et al."""
    mu, sd, B = _lookahead_parts(model, cand, ref)
    z, w = np.polynomial.hermite_e.hermegauss(n_gh); w = w / w.sum()
    hh = np.broadcast_to(h, mu.shape)[:, None]
    s_new = np.sqrt(np.maximum(sd[:, None] ** 2 - B ** 2, 1e-12))
    J = np.zeros(B.shape[1])
    for zi, wi in zip(z, w):
        tau = norm.cdf(-np.abs(mu[:, None] + B * zi - hh) / s_new)
        J += wi * (np.sqrt(tau).mean(0) ** 2 if kind == "J1" else tau.mean(0))
    return -J


# ------------------------------------------------------------------ LSE
class LSE:
    """Gotovos et al. 2013 on a fixed candidate set. Confidence intervals Q_t = mu +- beta_sqrt sd are intersected over
    time; a point is classified failing (mean below h) once its interval's top is below h + eps, safe once its bottom is
    above h - eps. The next run goes to the unclassified point with the largest ambiguity
    min(max C - h, h - min C). Here failing = below h."""

    def __init__(self, n_cand, h, beta_sqrt=3.0, eps=0.0):
        self.h, self.b, self.eps = h, beta_sqrt, eps
        self.lo = np.full(n_cand, -np.inf); self.hi = np.full(n_cand, np.inf)
        self.fail = np.zeros(n_cand, bool); self.safe = np.zeros(n_cand, bool)

    @property
    def unclassified(self):
        return ~(self.fail | self.safe)

    def update(self, mu, sd):
        u = self.unclassified
        self.lo[u] = np.maximum(self.lo[u], mu[u] - self.b * sd[u])
        self.hi[u] = np.minimum(self.hi[u], mu[u] + self.b * sd[u])
        self.fail |= u & (self.hi - self.eps < self.h)
        self.safe |= u & ~self.fail & (self.lo + self.eps >= self.h)

    def ambiguity(self):
        a = np.minimum(self.hi - self.h, self.h - self.lo)
        return np.where(self.unclassified, a, -np.inf)


# ------------------------------------------------------------------ portfolio
class GPHedge:
    """Hoffman et al. 2011: each criterion nominates a point; one nominee is run with probability proportional to
    exp(eta * gain); then every nominee gets a reward and the gains are updated. The paper's reward is the updated GP
    mean at the nominee (for maximisation); the paper gives eta only in theory, so eta here is a free choice."""

    def __init__(self, names, eta=1.0, seed=0):
        self.names, self.eta = list(names), eta
        self.gain = np.zeros(len(self.names))
        self.rng = np.random.default_rng(seed)
        self.picks = []

    def probs(self):
        p = np.exp(self.eta * (self.gain - self.gain.max()))
        return p / p.sum()

    def choose(self):
        i = int(self.rng.choice(len(self.names), p=self.probs()))
        self.picks.append(self.names[i])
        return i

    def update(self, rewards):
        self.gain += np.asarray(rewards, float)


# ------------------------------------------------------------------ batches
def top_b(scores, k):
    return np.argsort(-scores, kind="stable")[:k]


def pending_batch(model, pool, h, k, score=straddle):
    """Sequential batch: pick the best point, then shrink the variance as if it had been run (the GP variance does not
    depend on the outcome) and pick again. Mean unchanged."""
    mu, sd = model.predict(pool)
    C = model.cov(pool)
    noise = model.noise_var if hasattr(model, "noise_var") else 0.0
    var = np.maximum(np.diag(C).copy(), 1e-12)
    chosen = []
    for _ in range(k):
        s = score(mu, np.sqrt(np.maximum(var, 1e-12)), h)
        s[chosen] = -np.inf
        i = int(np.argmax(s)); chosen.append(i)
        ci = C[:, i].copy()
        C = C - np.outer(ci, ci) / (C[i, i] + noise + 1e-12)
        var = np.diag(C).copy()
    return np.array(chosen)


def weight_valid(scores, p_valid, floor=0.0):
    """Unknown constraints: multiply a non-negative score by the predicted probability that the run is valid
    (Gardner et al. 2014; Gelbart et al. 2014). Shifts the score to be >= floor first."""
    s = scores - min(scores.min(), floor)
    return s * p_valid
