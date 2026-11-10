import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
import pytest
from stp.v2 import config as C, jobs as J, rules as R


def seqs(p, n=40, m=40000, seed=1):
    return np.random.default_rng(seed).random((m, n)) < p


@pytest.mark.parametrize("p", [0.0, 0.1, 0.3, 0.5, 0.7, 0.95, 1.0])
@pytest.mark.parametrize("tau", [0.2, 0.5, 0.8])
def test_exact_matches_simulation(p, tau):
    for rule in R.shortlist(tau):
        d = [rule.apply(s) for s in seqs(p, m=4000)]; real = np.mean([x[0] for x in d]); used = np.mean([x[1] for x in d])
        pr, u = rule.exact(p)
        assert abs(pr - real) < 0.04, rule.name
        assert abs(u - used) < max(0.8, 0.1 * u), rule.name


def test_majority_is_k_of_n():
    r = R.k_of_n(2, 3, "m")
    assert r.apply(np.array([1, 1, 0, 0], bool)) == (True, 3) and r.apply(np.array([1, 0, 0, 1], bool)) == (False, 3)


def test_any_and_all():
    a, b = R.k_of_n(1, 3), R.k_of_n(3, 3)
    assert a.exact(0.5)[0] == pytest.approx(0.875) and b.exact(0.5)[0] == pytest.approx(0.125)


def test_sprt_stops_early_and_decides():
    r = R.sprt(.3, .7, .05, .05, .5)
    assert r.apply(np.ones(40, bool)) == (True, 4)
    assert r.apply(np.zeros(40, bool)) == (False, 4)


def test_sprt_uses_cap_on_undecided_sequences():
    r = R.sprt(.45, .55, .01, .01, .5, cap=6)
    assert r.apply(np.array([1, 0, 1, 0, 1, 0, 1], bool)) == (True, 6)


def test_sprt_stated_errors_are_roughly_met():
    r = R.sprt(.3, .7, .05, .05, .5)
    assert r.exact(.3)[0] <= .06 and 1 - r.exact(.7)[0] <= .06


def test_wilson_needs_strong_evidence():
    r = R.wilson(20, .5)
    assert not r.apply(np.array([1] * 12 + [0] * 8, bool))[0] and r.apply(np.array([1] * 16 + [0] * 4, bool))[0]


def test_latency_is_fixed_in_every_level():
    assert all(c.delay_steps == (10, 10) for c in C.LEVELS.values()) and C.cfg_for("high@20").delay_steps == (20, 20) and C.cfg_for("high@20").noise_sd == .30


def test_v2_levels_match_v1_noise():
    from stp.sut import LEVELS as V1
    for k in V1:
        a, b = V1[k], C.LEVELS[k]
        assert (a.noise_sd, a.gust_period, a.gust_phase_span) == (b.noise_sd, b.gust_period, b.gust_phase_span)


def test_streams_are_independent():
    assert J.seed_of("low", "truth", 1, 0) != J.seed_of("low", "rule", 1, 0) and J.seed_of("low", "truth", 1, 0) == J.seed_of("low", "truth", 1, 0)
