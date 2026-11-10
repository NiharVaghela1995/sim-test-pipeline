import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
import pytest
from stp import gates, runner, scenario as S
from stp.sut import SutConfig

CLEAN = S.Params(15.0, 0.01, -0.01, 0.0)
QUIET = SutConfig(noise_sd=0.0, delay_steps=(1, 1))


def test_clean_run_is_realised():
    r = runner.run(CLEAN, 1); assert r["realised"], r["gates"]


def test_same_seed_is_deterministic():
    a = runner.run(CLEAN, 3); b = runner.run(CLEAN, 3); assert a["margin"] == b["margin"]


def test_different_seed_differs():
    assert runner.run(S.Params(15, 0.01, -0.01, 0.5), 1)["margin"] != runner.run(S.Params(15, 0.01, -0.01, 0.5), 2)["margin"]


def test_known_answer_straight_road():
    """Straight road, no noise, no gust: the car stays centred, so margin equals the geometric clearance of 0.75 m."""
    r = runner.run(S.Params(15.0, 1e-9, 1e-9, 0.0), 1, QUIET)
    assert r["realised"], r["gates"]
    assert abs(r["margin"] - 0.75) < 0.01


def test_known_answer_impossible_curve_fails():
    """Lateral demand far above the controller limit must depart the lane."""
    r = runner.run(S.Params(30.0, 0.04, 0.04, 0.0), 1, QUIET)
    assert r["failed"]


# seeded defects: each must be caught by the realisation check
def test_defect_controller_not_external():
    assert not runner.run(CLEAN, 1, external=False)["gates"]["external_control"]


def test_defect_mirrored_road():
    executed = S.Params(15.0, -0.01, -0.01, 0.0)
    assert not runner.run(executed, 1, spec=CLEAN)["gates"]["road_arc1"]


def test_defect_wrong_second_arc():
    executed = S.Params(15.0, 0.01, 0.03, 0.0)
    assert not runner.run(executed, 1, spec=CLEAN)["gates"]["road_arc2"]


def test_defect_speed_not_applied():
    executed = S.Params(20.0, 0.01, -0.01, 0.0)
    assert not runner.run(executed, 1, spec=CLEAN)["gates"]["speed_applied"]


def test_defect_wrong_start_position():
    tr = dict(init_ok=True, ctrl_type=1, s0=40.0, t0=-1.75, lane0=-1, speed_mean=15.0, curv=[(70, 0.01), (150, -0.01)], ended_early=False, sim_time=1.0, steps=50, s_max=300)
    assert not gates.check(tr, CLEAN, 0.02)["start_pose"]


def test_defect_wrong_lane():
    tr = dict(init_ok=True, ctrl_type=1, s0=5.0, t0=-1.75, lane0=-2, speed_mean=15.0, curv=[], ended_early=False, sim_time=1.0, steps=50, s_max=300)
    assert not gates.check(tr, CLEAN, 0.02)["start_pose"]


def test_defect_clock_mismatch():
    tr = dict(init_ok=True, ctrl_type=1, s0=5.0, t0=-1.75, lane0=-1, speed_mean=15.0, curv=[], ended_early=False, sim_time=5.0, steps=50, s_max=300)
    assert not gates.check(tr, CLEAN, 0.02)["clock"]


def test_failed_needs_realised():
    r = runner.run(S.Params(30.0, 0.04, 0.04, 0.0), 1, QUIET, spec=S.Params(30.0, 0.01, 0.04, 0.0))
    assert not r["realised"] and not r["failed"]


@pytest.mark.parametrize("name,low,high", [("speed", 15.0, 18.0), ("k1", 0.01, 0.02), ("k2", -0.01, -0.02), ("gust", 0.0, 1.0)])
def test_every_input_reaches_the_simulator(name, low, high):
    """No inert parameters: changing one input must change the executed outcome, with W held fixed."""
    a = dict(CLEAN.dict()); b = dict(a); a[name] = low; b[name] = high
    ra, rb = runner.run(S.Params(**a), 11), runner.run(S.Params(**b), 11)
    assert ra["realised"] and rb["realised"] and ra["peak_offset"] != rb["peak_offset"]


def test_wilson_known_value():
    from stp.analysis import wilson_low
    assert abs(wilson_low(10, 20) - 0.2993) < 0.001


def test_sprt_stops_early_and_decides():
    from stp.analysis import sprt
    assert sprt(np.ones(20, bool)) == (True, 4)
    assert sprt(np.zeros(20, bool)) == (False, 4)


def test_rules_known_answers():
    from stp.analysis import rules
    R = rules(0.5); s = np.array([1, 0, 1, 1, 0] + [0] * 15, bool)
    assert R["report as-is"](s) == (True, 0)
    assert R["any-of-1"](s) == (True, 1)
    assert R["majority-of-3"](s) == (True, 3)
    assert R["all-of-3"](s) == (False, 3)
