"""Two surrogates for a noisy margin y(x) = m(x) + e, e ~ N(0, r(x)), and the failure region {x : p(x) >= ALPHA} with
p(x) = P(y < 0) = Phi(-m / sqrt(r)). p >= ALPHA  <=>  g(x) = m(x) - Z_A sqrt(r(x)) <= 0, Z_A = Phi^-1(1 - ALPHA).

Both return (mu, sd_mu, r) on query points: the latent mean, its posterior sd (noise excluded), and the noise variance.

  Homoscedastic  the demo's GP (constant x Matern 5/2 ARD + white noise, normalize_y, 5 seeded restarts) with the white-noise
                 upper bound raised from 1e-1 to 1.0 (normalised units), so one noise variance r is fitted for the whole box.
  Heteroskedastic  two-stage, stochastic-kriging style (Ankenman et al. 2010; Binois et al. 2018 without the joint likelihood):
                 1) replicates are pooled per unique input: mean ybar_i, sample variance s2_i (n_i >= 2);
                 2) a GP on log s2_i, bias-corrected (E log s2 = log r + psi((n-1)/2) - log((n-1)/2)) with its known sampling
                    variance psi'((n-1)/2) on the diagonal, gives log r(x) everywhere;
                 3) a GP on ybar_i with r(x_i) / n_i on the diagonal (no white-noise term) gives m(x).
                 Without at least MIN_VAR_POINTS replicated inputs it falls back to the homoscedastic GP.
"""
import warnings
import numpy as np
from scipy.special import digamma, polygamma
from scipy.stats import norm
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from ..cutin import gp as GP

ALPHA = 0.10
Z_A = float(norm.ppf(1 - ALPHA))
HOM_NOISE_BOUNDS = (1e-8, 1.0)
MIN_VAR_POINTS = 5


def _fit(kernel, U, y, alpha, seed):
    gp = GaussianProcessRegressor(kernel, alpha=alpha, normalize_y=False, n_restarts_optimizer=GP.CFG["restarts"], random_state=seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        gp.fit(np.asarray(U, float), np.asarray(y, float))
    return gp


def _matern(c=GP.CFG):
    return ConstantKernel(1.0, c["const_bounds"]) * Matern(length_scale=[c["length_scale_init"]] * 3, length_scale_bounds=c["length_scale_bounds"], nu=c["nu"])


class Hom:
    kind = "hom"

    def __init__(self, U, y, seed):
        U, y = np.asarray(U, float), np.asarray(y, float)
        self.mean, self.scale = float(y.mean()), float(y.std()) or 1.0
        k = _matern() + WhiteKernel(GP.CFG["noise_init"], HOM_NOISE_BOUNDS)
        self.gp = _fit(k, U, (y - self.mean) / self.scale, 1e-10, seed)
        self.r_norm = float(self.gp.kernel_.k2.noise_level)
        self.r = self.r_norm * self.scale ** 2

    def predict(self, U, chunk=8192):
        U = np.asarray(U, float); mu = np.empty(len(U)); sd = np.empty(len(U))
        for a in range(0, len(U), chunk):
            m, s = self.gp.predict(U[a:a + chunk], return_std=True)      # s includes the white noise (WhiteKernel.diag)
            mu[a:a + chunk] = self.mean + self.scale * m
            sd[a:a + chunk] = self.scale * np.sqrt(np.maximum(s ** 2 - self.r_norm, 1e-12))
        return mu, sd, np.full(len(U), self.r)


def pool_replicates(U, y, decimals=12):
    """Unique inputs with (n_i, ybar_i, s2_i); s2_i is nan where n_i = 1."""
    U, y = np.asarray(U, float), np.asarray(y, float)
    keys, inv = np.unique(np.round(U, decimals), axis=0, return_inverse=True)
    inv = inv.ravel(); n = np.bincount(inv); ybar = np.bincount(inv, y) / n
    ss = np.bincount(inv, (y - ybar[inv]) ** 2)
    s2 = np.where(n > 1, ss / np.maximum(n - 1, 1), np.nan)
    Uu = np.array([U[inv == k][0] for k in range(len(keys))])
    return Uu, n, ybar, s2


class Het:
    kind = "het"

    def __init__(self, U, y, seed):
        Uu, n, ybar, s2 = pool_replicates(U, y)
        rep = (n > 1) & (s2 > 0)
        if rep.sum() < MIN_VAR_POINTS:
            self.fallback = Hom(U, y, seed); return
        self.fallback = None
        dof = (n[rep] - 1) / 2.0
        z = np.log(s2[rep]) - (digamma(dof) - np.log(dof))          # unbiased for log r
        zv = polygamma(1, dof)                                         # Var(log s2)
        self.zm, self.zs = float(z.mean()), float(z.std()) or 1.0
        kz = _matern() + WhiteKernel(1e-2, (1e-6, 1.0))
        self.gz = _fit(kz, Uu[rep], (z - self.zm) / self.zs, zv / self.zs ** 2, seed + 1)
        r_i = self._r(Uu)
        self.mean, self.scale = float(ybar.mean()), float(ybar.std()) or 1.0
        self.gm = _fit(_matern(), Uu, (ybar - self.mean) / self.scale, np.maximum(r_i / n, 1e-10) / self.scale ** 2, seed)
        self.n_unique, self.n_rep = int(len(n)), int(rep.sum())

    def _r(self, U):
        return np.exp(self.zm + self.zs * self.gz.predict(np.asarray(U, float)))

    def predict(self, U, chunk=8192):
        if self.fallback is not None:
            return self.fallback.predict(U, chunk)
        U = np.asarray(U, float); mu = np.empty(len(U)); sd = np.empty(len(U)); r = np.empty(len(U))
        for a in range(0, len(U), chunk):
            m, s = self.gm.predict(U[a:a + chunk], return_std=True)     # no white-noise term: s is the latent sd
            mu[a:a + chunk] = self.mean + self.scale * m; sd[a:a + chunk] = self.scale * s; r[a:a + chunk] = self._r(U[a:a + chunk])
        return mu, sd, r


MODELS = dict(hom=Hom, het=Het)


def g_of(mu, r):
    """Signed distance to the target region: g <= 0 where the predicted p(x) >= ALPHA."""
    return mu - Z_A * np.sqrt(r)


def p_of(mu, r):
    return norm.cdf(-mu / np.sqrt(r))


def straddle(mu, sd, r, beta=GP.CFG["beta"]):
    return beta * sd - np.abs(g_of(mu, r))
