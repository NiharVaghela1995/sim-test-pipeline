"""Noisy R157 cut-in (docs/NOISE_PLAN.md): the ACC port against esmini's ACC, the noise and delay, the surrogates, the
reference helpers and the rerun rules."""
import math
import numpy as np
import pytest
from stp.cutin import runner as CR, scenario as S
from stp.r157 import design as D, runner as RR
from stp.noise import acc as A, sut as N, runner as NR, surrogates as M, experiment as X

ZERO = N.Level("zero")


@pytest.mark.parametrize("x", [(14.0, 1.0, 1.0), (16.0, 0.8, 0.9), (10.5, 4.0, 2.5), (12.0, 3.0, 1.5)])
def test_port_reproduces_esmini_acc(x):
    """Known answer: with noise and delay off, the Python ACC gives esmini's ACC trace (10.5/4/2.5 crosses the lane line
    exactly on a sample, which needs the lane tie rule)."""
    p = D.to_params(np.array(x))
    a, b = CR.simulate(p, 0), N.simulate(p, ZERO, 0)
    assert np.max(np.abs(np.array(a["ev"]) - np.array(b["ev"]))) < 1e-6
    assert abs(RR.run(x)["margin"] - NR.run(x, ZERO)["margin"]) < 1e-6


def test_noisy_run_realised_and_seeded():
    lv = X.LEVELS["mid"]
    r1, r2, r3 = NR.run([14.0, 3.0, 1.5], lv, 7), NR.run([14.0, 3.0, 1.5], lv, 7), NR.run([14.0, 3.0, 1.5], lv, 8)
    assert r1["realised"] and r1["gates"]["controllers"]
    assert r1["margin"] == r2["margin"] and r1["margin"] != r3["margin"]


def test_noise_stream_ar1():
    lv = N.Level("t", 1.0, 0.5, 0.2, 0.0)
    e = np.array(N.noise_stream(lv, 200000, 3))
    assert np.allclose(e.std(0), [1.0, 0.5, 0.2], rtol=0.05)
    rho = np.corrcoef(e[:-1, 0], e[1:, 0])[0, 1]
    assert abs(rho - math.exp(-N.DT / N.TAU_NOISE)) < 0.005
    assert np.array_equal(e[:10], np.array(N.noise_stream(lv, 200000, 3))[:10])


def test_actuation_delay_shifts_speed():
    """With a pure delay the ego's speed is the command delay/dt steps earlier."""
    lv = N.Level("d", delay=0.2); p = D.to_params(np.array([14.0, 1.0, 1.0]))
    tr = N.simulate(p, lv, 0); lag = 10
    v_cmd, ev = np.array(tr["v_cmd"]), np.array(tr["ev"][1:])
    assert np.allclose(ev[lag:], v_cmd[:-lag]) and np.allclose(ev[:lag], 14.0)


def test_free_space_matches_geometry():
    # ego at y = -1.75, lead in the next lane at y = -5.25, 10 m ahead: lateral free space 1.5 m to the right, longitudinal 10 - 4.5
    coll, lat, lon = A.free_space_lat_long((0.0, -1.75, 0.0), (10.0, -5.25, 0.0))
    assert not coll and lat == pytest.approx(-1.5) and lon == pytest.approx(5.5)
    assert A.free_space_lat_long((0.0, -1.75, 0.0), (2.0, -1.75, 0.0))[0]


def test_hetgp_recovers_input_dependent_noise():
    rng = np.random.default_rng(0)
    U = rng.random((80, 3)); U = np.repeat(U, 4, axis=0)
    sd = 0.05 + 0.6 * U[:, 0]
    y = 2 * U[:, 1] - 1 + sd * rng.standard_normal(len(U))
    het, hom = M.Het(U, y, 1), M.Hom(U, y, 1)
    Q = np.array([[0.05, 0.5, 0.5], [0.95, 0.5, 0.5]])
    r_het = het.predict(Q)[2]; r_hom = hom.predict(Q)[2]
    assert r_het[1] / r_het[0] > 10                        # true ratio (0.62/0.08)^2 = 60
    assert r_hom[0] == r_hom[1]


def test_pool_replicates():
    U = np.array([[0.1, 0.2, 0.3]] * 3 + [[0.5, 0.5, 0.5]])
    Uu, n, yb, s2 = M.pool_replicates(U, np.array([1.0, 2.0, 3.0, 5.0]))
    k = int(np.argmax(n == 3))
    assert sorted(n) == [1, 3] and yb[k] == 2.0 and s2[k] == 1.0 and np.isnan(s2[1 - k])


def test_target_region_algebra():
    mu, r = np.array([M.Z_A * 0.5]), np.array([0.25])        # exactly on the boundary: p = ALPHA
    assert abs(M.g_of(mu, r)[0]) < 1e-12 and M.p_of(mu, r)[0] == pytest.approx(M.ALPHA)


def test_isotonic_and_line_boundary():
    p = np.zeros((1, 1, len(X.T))); p[0, 0, :5] = [0.9, 0.5, 0.3, 0.12, 0.08]; p[0, 0, 6] = 0.2    # one bump above ALPHA
    ok = np.ones_like(p, bool); w = np.full(p.shape, 10)
    iso = X.isotonic(p, w, ok)
    assert np.all(np.diff(iso[0, 0]) <= 1e-12)
    b, has = X.line_boundary(iso >= M.ALPHA, ok)
    assert has[0, 0] and X.T[0] < b[0, 0] < X.T[8]
    assert len(X.boundary_points(iso, ok)) == 1


def test_sprt_needs_reruns_even_at_p0():
    rng = np.random.default_rng(0)
    att, real, says_fail, und = X.sprt_runs(0.0, 0.0, rng, reps=20)
    lp = math.log((1 - X.SPRT["p1"]) / (1 - X.SPRT["p0"])); B = math.log(X.SPRT["err"] / (1 - X.SPRT["err"]))
    assert real == math.ceil(B / lp) and says_fail == 0 and und == 0
    att, real, says_fail, und = X.sprt_runs(0.0, 0.5, rng, reps=200)        # half the attempts give no verdict
    assert att == pytest.approx(2 * real, rel=0.15)


def test_quantile_rule_factors():
    k1, k0 = X._qfactors()
    assert k1[10] == pytest.approx(2.355, abs=2e-3)            # one-sided tolerance factor, n = 10, 90 % content, 95 % conf.
    assert all(k0[n] < M.Z_A < k1[n] for n in k1)


def test_qrule_far_and_near():
    rng = np.random.default_rng(0)
    far = X.qrule_runs(np.full(40, 3.0) + 0.01 * rng.standard_normal(40), 0.0, rng)
    assert far[1] == 2 and far[2] == 0                       # a clear margin with small spread: two runs decide
    near = X.qrule_runs(0.1 + 0.3 * rng.standard_normal(40), 0.0, rng)
    assert near[1] > 5


def test_stage2_neighbourhood():
    f = np.zeros((3, 3, 10), int); f[1, 1, 5] = 1; app = np.ones_like(f, bool)
    sel = X._stage2(f, app)
    assert sel[1, 1, 2:9].all() and not sel[1, 1, 1] and sel[0, 1, 5] and sel[1, 2, 5] and not sel[0, 0, 5]
