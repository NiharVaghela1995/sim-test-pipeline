"""Surrogates. Margin models return (mu, sd) of the latent mean margin, noise excluded;
classifiers return P(fail).

  GPR      constant x Matern 5/2 with one length scale per input + white noise; marginal likelihood with seeded restarts
  HetGP    two-stage heteroskedastic GP in the stochastic-kriging style (Ankenman et al. 2010; Binois et al. 2018 without
           the joint likelihood): a GP on bias-corrected log sample variances of replicated sites, then a GP on the site
           means with r(x_i) / a_i on the diagonal. Same construction as the repo's src/stp/noise/surrogates.py.
  GPC      GP classification, Laplace approximation (Rasmussen & Williams 2006, ch. 3); latent mean and sd from Alg. 3.2
  Forest   random forest (Breiman 2001); vote share and the spread across trees
  SVM      RBF SVM, Platt scaling for probabilities (Bishop 2006, ch. 7)
"""
import warnings
import numpy as np
from scipy.special import digamma, polygamma
from scipy.stats import norm
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessClassifier, GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, RBF, WhiteKernel
from sklearn.neighbors import KNeighborsRegressor
from sklearn.svm import SVC

RESTARTS = 2


def matern(d, nu=2.5):
    k = Matern(length_scale=np.full(d, 0.3), length_scale_bounds=(1e-2, 1e1), nu=nu) if nu else RBF(np.full(d, 0.3), (1e-2, 1e1))
    return ConstantKernel(1.0, (1e-2, 1e2)) * k


def _quiet_fit(model, X, y):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        warnings.simplefilter("ignore", UserWarning)
        return model.fit(X, y)


def group(X, y, decimals=10):
    """Unique sites, replicate counts a, site means, sample variances (nan where a = 1)."""
    Xr = np.round(np.asarray(X, float), decimals)
    xs, inv, a = np.unique(Xr, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    ybar = np.bincount(inv, y) / a
    ss = np.bincount(inv, (y - ybar[inv]) ** 2)
    s2 = np.where(a > 1, ss / np.maximum(a - 1, 1), np.nan)
    return xs, a, ybar, s2


class GPR:
    """Homoskedastic GP on the margin."""
    kind = "margin"

    def __init__(self, nu=2.5, noise=True, restarts=RESTARTS, seed=0):
        self.nu, self.noise, self.restarts, self.seed = nu, noise, restarts, seed

    def fit(self, X, y):
        X, y = np.asarray(X, float), np.asarray(y, float)
        self.m, self.s = float(y.mean()), float(y.std()) or 1.0
        k = matern(X.shape[1], self.nu) + WhiteKernel(1e-3, (1e-8, 1.0)) if self.noise else matern(X.shape[1], self.nu)
        self.gp = GaussianProcessRegressor(k, alpha=1e-8, normalize_y=False,
                                           n_restarts_optimizer=self.restarts, random_state=self.seed)
        _quiet_fit(self.gp, X, (y - self.m) / self.s)
        self.r_norm = float(self.gp.kernel_.k2.noise_level) if self.noise else 0.0
        self.X = X
        return self

    @property
    def noise_var(self):
        return self.r_norm * self.s ** 2

    def predict(self, U):
        mu, sd = self.gp.predict(np.asarray(U, float), return_std=True)
        return self.m + self.s * mu, self.s * np.sqrt(np.maximum(sd ** 2 - self.r_norm, 1e-12))

    def noise_sd(self, U):
        return np.full(len(U), np.sqrt(self.noise_var))

    def cov(self, U):
        """Latent posterior covariance on U (for lookahead criteria and batch updates)."""
        _, C = self.gp.predict(np.asarray(U, float), return_cov=True)
        return self.s ** 2 * (C - self.r_norm * np.eye(len(U)))

    def log_marginal_likelihood(self):
        return float(self.gp.log_marginal_likelihood_value_)


class HetGP:
    """Heteroskedastic two-stage GP. Falls back to GPR when fewer than min_rep sites are replicated."""
    kind = "margin"

    def __init__(self, nu=2.5, restarts=RESTARTS, seed=0, min_rep=5):
        self.nu, self.restarts, self.seed, self.min_rep = nu, restarts, seed, min_rep

    def fit(self, X, y):
        X, y = np.asarray(X, float), np.asarray(y, float)
        xs, a, ybar, s2 = group(X, y)
        rep = a > 1
        self.fallback = rep.sum() < self.min_rep
        if self.fallback:
            self.hom = GPR(self.nu, restarts=self.restarts, seed=self.seed).fit(X, y)
            return self
        h = (a[rep] - 1) / 2
        z = np.log(np.maximum(s2[rep], 1e-12)) - (digamma(h) - np.log(h))       # E log s2 = log r + psi(h) - log h
        self.zm = float(z.mean())
        self.vgp = GaussianProcessRegressor(matern(X.shape[1], self.nu), alpha=polygamma(1, h), normalize_y=False,
                                            n_restarts_optimizer=self.restarts, random_state=self.seed)
        _quiet_fit(self.vgp, xs[rep], z - self.zm)
        r = self._r(xs)
        self.m, self.s = float(ybar.mean()), float(ybar.std()) or 1.0
        self.gp = GaussianProcessRegressor(matern(X.shape[1], self.nu), alpha=r / a / self.s ** 2, normalize_y=False,
                                           n_restarts_optimizer=self.restarts, random_state=self.seed)
        _quiet_fit(self.gp, xs, (ybar - self.m) / self.s)
        return self

    def _r(self, U):
        return np.exp(self.zm + self.vgp.predict(np.asarray(U, float)))

    def predict(self, U):
        if self.fallback:
            return self.hom.predict(U)
        mu, sd = self.gp.predict(np.asarray(U, float), return_std=True)
        return self.m + self.s * mu, self.s * sd

    def noise_sd(self, U):
        return self.hom.noise_sd(U) if self.fallback else np.sqrt(self._r(U))


class GPC:
    """GP classifier on pass/fail labels (1 = fail). Replicated runs enter as separate rows."""
    kind = "class"

    def __init__(self, nu=2.5, restarts=RESTARTS, seed=0):
        self.nu, self.restarts, self.seed = nu, restarts, seed

    def fit(self, X, z):
        z = np.asarray(z, int)
        self.const = None if 0 < z.mean() < 1 else float(z.mean())
        if self.const is None:
            self.gpc = GaussianProcessClassifier(matern(np.shape(X)[1], self.nu), n_restarts_optimizer=self.restarts, random_state=self.seed)
            _quiet_fit(self.gpc, np.asarray(X, float), z)
        return self

    def p_fail(self, U):
        return np.full(len(U), self.const) if self.const is not None else self.gpc.predict_proba(np.asarray(U, float))[:, 1]

    def latent(self, U):
        """Laplace posterior mean and sd of the latent f (Rasmussen & Williams Alg. 3.2, lines 4-6)."""
        if self.const is not None:
            return np.full(len(U), 10.0 if self.const else -10.0), np.full(len(U), 1e-3)
        e = self.gpc.base_estimator_
        Ks = e.kernel_(e.X_train_, np.asarray(U, float))
        f = Ks.T @ (e.y_train_ - e.pi_)
        v = np.linalg.solve(e.L_, e.W_sr_[:, None] * Ks)
        var = e.kernel_.diag(np.asarray(U, float)) - np.einsum("ij,ij->j", v, v)
        return f, np.sqrt(np.maximum(var, 1e-12))


class Forest:
    """Random forest. As a classifier: vote share P(fail) and spread across trees; as a regressor: mean margin."""

    def __init__(self, classify=True, n_trees=200, min_leaf=2, seed=0):
        self.kind = "class" if classify else "margin"
        Cls = RandomForestClassifier if classify else RandomForestRegressor
        self.rf = Cls(n_estimators=n_trees, min_samples_leaf=min_leaf, random_state=seed, n_jobs=1)

    def fit(self, X, y):
        if self.kind == "class":
            y = np.asarray(y, int)
            self.const = None if 0 < y.mean() < 1 else float(y.mean())
        self.rf.fit(np.asarray(X, float), y)
        return self

    def _per_tree(self, U):
        if self.kind == "class":
            return np.stack([t.predict_proba(U)[:, -1] if t.n_classes_ == 2 else np.full(len(U), self.const) for t in self.rf.estimators_])
        return np.stack([t.predict(U) for t in self.rf.estimators_])

    def p_fail(self, U):
        return self._per_tree(np.asarray(U, float)).mean(0)

    def predict(self, U):
        T = self._per_tree(np.asarray(U, float))
        return T.mean(0), T.std(0)


class SVM:
    """RBF support vector classifier with Platt scaling."""
    kind = "class"

    def __init__(self, C=10.0, seed=0):
        self.svc = SVC(C=C, kernel="rbf", gamma="scale", probability=True, random_state=seed)

    def fit(self, X, z):
        self.svc.fit(np.asarray(X, float), np.asarray(z, int))
        return self

    def decision(self, U):
        return self.svc.decision_function(np.asarray(U, float))      # > 0: class 1 (fail)

    def p_fail(self, U):
        return self.svc.predict_proba(np.asarray(U, float))[:, 1]


class NearestNeighbour:
    """1-NN on the margin: the 'no model' control."""
    kind = "margin"

    def fit(self, X, y):
        self.knn = KNeighborsRegressor(1).fit(np.asarray(X, float), y)
        return self

    def predict(self, U):
        return self.knn.predict(np.asarray(U, float)), np.zeros(len(U))


class Constant:
    """Predicts one margin everywhere: 'everything passes' with value > threshold."""
    kind = "margin"

    def __init__(self, value=1.0):
        self.value = value

    def fit(self, X, y):
        return self

    def predict(self, U):
        return np.full(len(U), self.value), np.zeros(len(U))


def p_fail_margin(model, U, h=0.0):
    """P(true mean margin is below h) from a margin model: Phi((h - mu) / sd)."""
    mu, sd = model.predict(U)
    return norm.cdf((h - mu) / np.maximum(sd, 1e-12))


def predicted_region(model, U, h=0.0, alpha=None):
    """Failure region estimate. Margin model: mu < h (h may be an array). Classifier: P(fail) >= alpha (default 0.5)."""
    if model.kind == "margin":
        mu, _ = model.predict(U)
        return mu < h
    return model.p_fail(U) >= (0.5 if alpha is None else alpha)
