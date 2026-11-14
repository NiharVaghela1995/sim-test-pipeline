"""Cut-in scenario, KPI and realisation check (docs/GP_BOUNDARY_PLAN.md, step 1)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import math
import pytest
from stp.cutin import runner as R, scenario as S, gates as G

P = S.Params(30.0, 15.0, -5.0)


def failed_gates(r):
    return {k for k, v in r["gates"].items() if not v}


@pytest.mark.parametrize("p", [P, S.Params(20, 5, 0), S.Params(35, 5, -10), S.Params(20, 40, 0), S.Params(35, 40, -10), S.Params(27.5, 22.5, -5)])
def test_clean_runs_are_realised(p):
    r = R.run(p)
    assert r["realised"], failed_gates(r)


def test_gap_at_cut_in_moment_matches_spec():
    r = R.run(S.Params(25.0, 20.0, -10.0))
    assert abs(r["gap_at_cut"] - 20.0) < 0.01


def test_same_run_twice_is_bitwise_identical():
    assert R.run(P, 1)["margin"] == R.run(P, 1)["margin"]


def test_esmini_seed_has_no_effect():
    assert R.run(P, 1)["margin"] == R.run(P, 12345)["margin"]


# known answers
def test_known_answer_no_closing_passes_at_cap():
    r = R.run(S.Params(20.0, 40.0, 0.0))
    assert r["realised"] and r["min_ttc"] == R.TTC_CAP and not r["failed"]


def test_known_answer_close_fast_cut_in_fails():
    r = R.run(S.Params(35.0, 5.0, -10.0))
    assert r["realised"] and r["failed"] and r["min_ttc"] < 0.5


def test_ego_reacts():
    """The SUT actually brakes: without the ACC the same cut-in ends in a collision."""
    acc = R.run(S.Params(25.0, 15.0, -8.0))
    passive = R.run(S.Params(25.0, 15.0, -8.0), defects=S.Defects(ego_controller="DefaultController"))
    assert acc["min_ego_speed"] < 25.0 - 5 and not acc["collided"]
    assert passive["collided"] and passive["min_ttc"] == 0.0


def test_kpi_on_constructed_traces():
    w = S.CAR_WIDTH
    # side by side lanes, closing: no TTC
    assert R.kpi(dict(gap=[10.0], dy=[-3.5], closing=[5.0]))[0] == R.TTC_CAP
    # in lane, 10 m at 5 m/s closing: 2 s, at step 1
    assert R.kpi(dict(gap=[20.0, 10.0, 12.0], dy=[0, 0, 0], closing=[5.0, 5.0, 5.0]))[0::2] == (2.0, 1)
    # opening: no TTC
    assert R.kpi(dict(gap=[5.0], dy=[0.0], closing=[-1.0]))[0] == R.TTC_CAP
    # just inside the lateral overlap counts, just outside does not
    assert R.kpi(dict(gap=[6.0], dy=[w - 1e-6], closing=[2.0]))[0] == 3.0
    assert R.kpi(dict(gap=[6.0], dy=[w], closing=[2.0]))[0] == R.TTC_CAP
    # contact
    ttc, col, _ = R.kpi(dict(gap=[1.0, -0.5], dy=[0, 0], closing=[10, 10]))
    assert ttc == 0.0 and col
    # far behind (cut in behind the ego) is not contact
    assert R.kpi(dict(gap=[-20.0], dy=[0.0], closing=[1.0]))[:2] == (R.TTC_CAP, False)


def test_x_loss_is_small_and_positive():
    assert 0.01 < S.x_loss(20.0, S.TAU_X) < 0.03 and S.x_loss(30.0, S.TAU_X) < S.x_loss(20.0, S.TAU_X)


def test_tau_x_matches_lane_line():
    shift = S.LANE_WIDTH * (1 - math.cos(math.pi * S.TAU_X / S.LC_TIME)) / 2
    assert abs(shift - S.LINE_SHIFT) < 1e-12


# deliberately broken scenarios: each must be caught by the named gate(s)
BROKEN = [
    ("ego without ACC", S.Defects(ego_controller="DefaultController"), {"controllers"}),
    ("cutting car starts in the ego lane", S.Defects(cut_lane=-1), {"start_pose"}),
    ("no lane change", S.Defects(lane_change=False), {"lane_change_start", "gap_at_cut", "lane_change_end"}),
    ("lane change away from the ego", S.Defects(target_lane=-3), {"lane_change_start", "gap_at_cut", "lane_change_end"}),
    ("lane change triggered late", S.Defects(t_lc=2.5), {"lane_change_start", "gap_at_cut"}),
    ("cutting car placed 2 m off", S.Defects(cut_s_shift=2.0), {"start_pose", "gap_at_cut"}),
    ("cutting car 1 m/s off", S.Defects(cut_speed_shift=1.0), {"start_speed", "cut_speed_held", "gap_at_cut"}),
    ("ego 1 m/s off", S.Defects(ego_speed_shift=1.0), {"start_speed", "ego_cruise_before_cut"}),
    ("simulation too short", S.Defects(t_end=4.0), {"outcome_settled", "lane_change_end"}),
]


@pytest.mark.parametrize("name,defect,expected", BROKEN, ids=[b[0] for b in BROKEN])
def test_broken_scenario_is_caught(name, defect, expected):
    r = R.run(P, defects=defect)
    assert not r["realised"] and not r["failed"]
    assert expected <= failed_gates(r), (name, failed_gates(r))


def test_unloadable_file_is_not_realised():
    tr = dict(init_ok=False)
    g, _ = G.check(tr, P, R.DT)
    assert not any(g.values())


def test_overbraking_before_minimum_is_rejected():
    """A constructed trace where the speed drops beyond the limit before the TTC minimum."""
    tr = R.simulate(P, 0)
    ttc, _, k = R.kpi(tr)
    tr["ev"] = list(tr["ev"]); tr["ev"][k - 5] = tr["ev"][k - 6] - 1.0   # 50 m/s^2 in one step
    g, _ = G.check(tr, P, R.DT, k)
    assert not g["dynamics_valid_to_kpi"]
