"""Known-answer tests for the course notebooks' shared harness (notebooks/course/failreg)."""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks/course"))
from failreg import acquisition as A, designs as D, loop as L, metrics as M, models as MD, problems as P, replication as R  # noqa: E402


# ------------------------------------------------------------------ problems
def test_branin_minima_and_regions():
    xs = np.array([[-np.pi, 12.275], [np.pi, 2.275], [9.42478, 2.475]])
    U = np.column_stack([(xs[:, 0] + 5) / 15, xs[:, 1] / 15])
    assert np.allclose(P.branin(U), 0.397887, atol=1e-4)
    p = P.get("branin"); G, t, sh, _ = p.test
    assert M.regions(t, sh)[1] == 3


def test_four_branch_has_four_regions():
    p = P.get("four_branch"); G, t, sh, _ = p.test
    assert M.regions(t, sh)[1] == 4


def test_car_zero_contour_is_exact():
    c = P.car_zero_contour()
    assert np.allclose(P.car_following(c), 0.0, atol=1e-9)
    p = P.get("car"); G, t, sh, _ = p.test
    d = M.boundary_distance(c, M.boundary_points(t, sh))
    assert d["max"] < 2.0 / (sh[0] - 1)          # grid boundary within two cells of the exact contour


def test_noisy_threshold_moves_to_safe_side():
    p = P.get("noisy_car"); U = np.array([[0.5, 0.5]])
    h = p.h(U)[0]
    assert h > p.tau                               # alpha < 0.5: the boundary is on the safe side of tau
    f_at = lambda u0: P.car_following([[u0, 0.5]])[0] - h
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f_at(mid) < 0 else (lo, mid)
    assert abs(p.p_fail([[lo, 0.5]])[0] - p.alpha) < 1e-6


# ------------------------------------------------------------------ metrics
def test_region_scores_known_counts():
    t = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], bool)
    p = np.array([1, 1, 1, 0, 1, 0, 0, 0, 0, 0], bool)
    s = M.region_scores(t, p)
    assert s["false_safe"] == pytest.approx(0.25) and s["false_unsafe"] == pytest.approx(1 / 6)
    assert s["misclassified"] == pytest.approx(0.2)


def test_constant_pass_is_all_false_safe():
    t = np.random.default_rng(0).random(1000) < 0.3
    s = M.region_scores(t, np.zeros(1000, bool))
    assert s["false_safe"] == 1.0 and s["false_unsafe"] == 0.0 and s["misclassified"] == pytest.approx(t.mean())


def test_runs_to_target_needs_to_stay_below():
    assert M.runs_to_target([10, 20, 30, 40], [0.2, 0.05, 0.2, 0.04], 0.1) == 40
    assert M.runs_to_target([10, 20], [0.2, 0.3], 0.1) == np.inf


def test_iqm_and_holm():
    assert M.iqm([0, 1, 2, 3, 100, 4, 5, 6]) == pytest.approx(3.5)
    assert np.allclose(M.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])


def test_calibration_of_exact_gaussian_band():
    rng = np.random.default_rng(1); v = rng.standard_normal(200000)
    c = M.calibration(np.zeros_like(v), np.ones_like(v), v)
    assert all(abs(c[q] - q) < 0.005 for q in c)


# ------------------------------------------------------------------ designs
def test_lhs_one_point_per_stratum_and_sobol_balance():
    X = D.lhs(32, 3, seed=2)
    assert D.projection_gaps(X) == 0
    S = D.sobol(32, 3, seed=2)
    assert D.projection_gaps(S) == 0 and D.projection_gaps(S[:16]) == 0      # prefixes at powers of two stay balanced


def test_fractional_factorial_resolution_iv():
    F, _ = D.fractional_factorial(8, ["BCD", "ACD", "ABC", "ABD"])
    assert F.shape == (16, 8)
    assert np.allclose(F.T @ F, 16 * np.eye(8))
    words, res = D.defining_relation(8, ["BCD", "ACD", "ABC", "ABD"])
    assert res == 4 and len(words) == 15


def test_morris_effects_of_a_linear_function():
    X, which, delta = D.morris(5, r=10, p=4, seed=0)
    assert X.shape == (60, 5) and delta == pytest.approx(2 / 3)
    assert X.min() >= -1e-12 and X.max() <= 1 + 1e-12
    coef = np.array([3.0, -2.0, 0.0, 1.0, 0.0])
    mu_star, sigma = D.morris_effects(X, X @ coef, which, 5)
    assert np.allclose(mu_star, np.abs(coef)) and np.allclose(sigma, 0, atol=1e-12)


def test_fssf_prefix_is_space_filling():
    X = D.fssf(32, 2, seed=0)
    assert D.min_distance(X[:8]) > D.min_distance(D.random(8, 2, seed=0))


# ------------------------------------------------------------------ acquisition
def test_lse_ambiguity_equals_straddle_before_intersection():
    mu, sd, h = np.array([-1.0, 0.2, 2.0]), np.array([1.0, 0.5, 0.3]), 0.0
    lse = A.LSE(3, h, beta_sqrt=1.96); lse.update(mu, sd)
    amb = np.minimum(mu + 1.96 * sd - h, h - (mu - 1.96 * sd))
    assert np.allclose(np.where(lse.unclassified, amb, -np.inf), lse.ambiguity())
    assert np.allclose(amb, A.straddle(mu, sd, h))


def test_mee_and_straddle_pick_boundary_point():
    mu, sd = np.array([-3.0, 0.05, 2.0]), np.array([1.0, 1.0, 1.0])
    assert np.argmax(A.mee(mu, sd, 0.0)) == 1 and np.argmax(A.straddle(mu, sd, 0.0)) == 1


def test_contour_ei_closed_form_delta1():
    """At mu = h the EFF integrand is eps - |G - h|: E = eps (2 Phi(k) - 1) - 2 sd (phi(0) - phi(k))."""
    from scipy.stats import norm
    k, sd = 0.5, 2.0
    exact = k * sd * (2 * norm.cdf(k) - 1) - 2 * sd * (norm.pdf(0) - norm.pdf(k))
    assert A.contour_ei(np.array([1.0]), np.array([sd]), 1.0, kappa=k, delta=1, n_grid=20001)[0] == pytest.approx(exact, rel=1e-4)


def test_sur_prefers_runs_near_the_boundary():
    p = P.get("branin")
    X = D.sobol(12, 2, seed=0); y = p.run(X, np.random.default_rng(0))
    m = MD.GPR(seed=0).fit(X, y)
    pool, ref = D.sobol(512, 2, seed=2), D.sobol(256, 2, seed=1)
    mu, sd = m.predict(pool); e = A.mee(mu, sd, p.tau)
    cand = pool[[np.argmax(e), np.argmin(e)]]
    s = A.sur(m, cand, ref, p.tau)
    assert s[0] > s[1]


# ------------------------------------------------------------------ replication
def test_ocba_targets_the_best_threshold_rule_the_boundary():
    """Sites 0, 0.48, 0.9, threshold 0.5. OCBA does not put most runs on 0.48; the threshold rule does."""
    m, s = [0.0, 0.48, 0.9], [1.0, 1.0, 1.0]
    o = R.ocba(m, s, 300); t = R.threshold_alloc(m, s, 0.5, 300, eps=0.01)
    assert np.argmax(o) != 1 and np.argmax(t) == 1


def test_apt_classifies_well_separated_arms():
    rng = np.random.default_rng(0); p = np.array([0.02, 0.05, 0.3, 0.5])
    est, cnt = R.apt(lambda k: float(rng.random() < p[k]), 4, 0.1, 400, eps=0.01, n_init=10)
    assert np.array_equal(est >= 0.1, p >= 0.1)


def test_integerise_sums():
    n = R.integerise(np.array([1.4, 2.4, 3.2]), 7)
    assert n.sum() == 7 and np.all(n >= 1)


# ------------------------------------------------------------------ models and loop
def test_gpr_interpolates_and_beats_constant():
    p = P.get("branin")
    h, _, _ = L.static(p, D.sobol, 40, 0, lambda: MD.GPR(seed=0))
    c, _, _ = L.static(p, D.sobol, 40, 0, lambda: MD.Constant(100.0))
    assert h[-1]["misclassified"] < 0.05 < c[-1]["misclassified"]
    assert c[-1]["false_safe"] == 1.0


def test_hetgp_learns_increasing_noise():
    p = P.get("noisy_car"); rng = np.random.default_rng(0)
    X = np.repeat(D.sobol(32, 2, seed=0), 6, axis=0); y = p.run(X, rng)
    m = MD.HetGP(seed=0).fit(X, y)
    lo, hi = m.noise_sd(np.array([[0.5, 0.1]]))[0], m.noise_sd(np.array([[0.5, 0.9]]))[0]
    assert not m.fallback and hi > 2 * lo


def test_active_and_sobol_share_initial_design():
    p = P.get("car")
    _, Xa, ya, _ = L.active(p, lambda: MD.GPR(seed=0), L.by_score(A.straddle), 20, 3, n0=10, batch=5)
    _, Xs, ys = L.static(p, D.sobol, 20, 3, lambda: MD.GPR(seed=0))
    assert np.allclose(Xa[:10], Xs[:10]) and np.allclose(ya[:10], ys[:10])
