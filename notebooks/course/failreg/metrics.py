"""Scoring an estimated failure region against the answer key (course Module 32, section 2).

A test point is positive when it fails. False-safe = a failing point predicted safe; false-unsafe = a safe point
predicted failing.
"""
import numpy as np
from scipy.ndimage import label
from scipy.spatial import cKDTree
from scipy.stats import norm, wilcoxon, mannwhitneyu


def region_scores(truth, pred):
    t, p = np.asarray(truth, bool), np.asarray(pred, bool)
    tp, fn, fp, tn = np.sum(t & p), np.sum(t & ~p), np.sum(~t & p), np.sum(~t & ~p)
    fsr = fn / max(tp + fn, 1)                 # false-safe rate
    fur = fp / max(fp + tn, 1)                 # false-unsafe rate
    return dict(false_safe=fsr, false_unsafe=fur, misclassified=(fn + fp) / t.size,
                error_recall=1 - fsr, balanced_accuracy=1 - 0.5 * (fsr + fur))   # mean of the two class accuracies


def boundary_points(mask, shape, ok=None):
    """Grid points with a 4-neighbour (2-D) or 6-neighbour (3-D) of the other class; ok masks out points without a label.
    Returned in unit coordinates."""
    m = np.asarray(mask, bool).reshape(shape)
    okm = np.ones(shape, bool) if ok is None else np.asarray(ok, bool).reshape(shape)
    edge = np.zeros(shape, bool)
    for ax in range(len(shape)):
        a = [slice(None)] * len(shape); b = [slice(None)] * len(shape)
        a[ax], b[ax] = slice(None, -1), slice(1, None)
        diff = (m[tuple(a)] != m[tuple(b)]) & okm[tuple(a)] & okm[tuple(b)]
        edge[tuple(a)] |= diff; edge[tuple(b)] |= diff
    idx = np.nonzero(edge)
    return np.column_stack([i / (n - 1) for i, n in zip(idx, shape)])


def boundary_distance(b_true, b_pred):
    """Mean and maximum distance between two boundaries (symmetric nearest-neighbour; the maximum is the Hausdorff
    distance, the quantity Batsch et al. 2019 compare between estimates)."""
    if len(b_true) == 0 or len(b_pred) == 0:
        return dict(mean=np.inf, max=np.inf)
    d1, _ = cKDTree(b_pred).query(b_true)
    d2, _ = cKDTree(b_true).query(b_pred)
    return dict(mean=0.5 * (d1.mean() + d2.mean()), max=max(d1.max(), d2.max()))


def coverage(lo, hi, values):
    """Share of values inside [lo, hi]."""
    v = np.asarray(values)
    return float(np.mean((v >= lo) & (v <= hi)))


def calibration(mu, sd, values, levels=(0.5, 0.8, 0.95)):
    """Coverage of central bands mu +- z sd at stated levels; honest when coverage is close to the level."""
    out = {}
    for q in levels:
        z = norm.ppf(0.5 + q / 2)
        out[q] = coverage(mu - z * sd, mu + z * sd, values)
    return out


def undecided(p, lo=0.05, hi=0.95):
    """Share of points where the model is not sure which side they are on (0.05 < P(fail) < 0.95)."""
    p = np.asarray(p)
    return float(np.mean((p > lo) & (p < hi)))


def runs_to_target(ns, values, target):
    """First budget from which the metric stays <= target for every later checkpoint; inf if never."""
    ns, v = np.asarray(ns), np.asarray(values)
    for i in range(len(ns)):
        if np.all(v[i:] <= target):
            return ns[i]
    return np.inf


def regions(mask, shape):
    """Label the connected failure regions of a grid mask (4-connectivity)."""
    lab, n = label(np.asarray(mask, bool).reshape(shape))
    return lab.ravel(), n


def mechanisms_found(truth, pred, shape, min_share=0.2):
    """How many of the built-in failure regions the estimate recovers: a region counts as found when at least
    min_share of its cells are predicted failing."""
    lab, n = regions(truth, shape)
    p = np.asarray(pred, bool)
    found = sum(p[lab == k].mean() >= min_share for k in range(1, n + 1))
    return int(found), int(n)


# ------------------------------------------------------------------ across seeds
def iqm(x):
    """Interquartile mean: mean of the middle 50 % (Agarwal et al. 2021)."""
    x = np.sort(np.asarray(x, float))
    n = len(x); a = int(np.floor(0.25 * n)); b = int(np.ceil(0.75 * n))
    return float(x[a:b].mean()) if b > a else float(x.mean())


def bootstrap_ci(x, stat=iqm, reps=2000, level=0.95, seed=0):
    """Percentile bootstrap interval of a statistic over seeds (one task, so the stratified bootstrap of
    Agarwal et al. reduces to the plain one)."""
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    b = np.array([stat(rng.choice(x, len(x))) for _ in range(reps)])
    return float(np.quantile(b, (1 - level) / 2)), float(np.quantile(b, (1 + level) / 2))


def paired_test(a, b):
    """Two-sided Wilcoxon signed-rank test on paired seeds (arms share the seed and initial design)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if np.allclose(a, b):
        return 1.0
    return float(wilcoxon(a, b, zero_method="zsplit").pvalue)


def unpaired_test(a, b):
    """Mann-Whitney U, two-sided, as Klees et al. 2018 recommend for independent trials."""
    return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)


def holm(p):
    """Holm step-down adjusted p-values."""
    p = np.asarray(p, float); o = np.argsort(p); m = len(p)
    adj = np.empty(m); run = 0.0
    for r, i in enumerate(o):
        run = max(run, (m - r) * p[i]); adj[i] = min(1.0, run)
    return adj


def summary(x):
    x = np.asarray(x, float)
    return dict(median=float(np.median(x)), q25=float(np.quantile(x, 0.25)), q75=float(np.quantile(x, 0.75)), iqm=iqm(x))
