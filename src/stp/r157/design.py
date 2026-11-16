"""Test design for UN R157 para. 5.2.5.2 (cut-in) on the esmini ACC cut-in. Every constant cites its source.

Source: UN Regulation No. 157, E/ECE/TRANS/505/Rev.3/Add.156 (4 March 2021), the version read; later amendments not used.

Logical scenario parameters (unit cube order):
  ego_speed  [m/s]  10.0 - 16.667   R157 para. 5.2.3.1, p. 9: ALKS up to 60 km/h (16.667 m/s). Lower bound 36 km/h: ODD assumption.
  v_rel      [m/s]   0.5 - 8.0      para. 5.2.5.2(a), p. 10: cutter slower than the ALKS vehicle (v_rel > 0). Bounds: ODD assumption.
  ttc_li     [s]     0.2 - 3.0      TTC_LaneIntrusion, para. 5.2.5.2(c), p. 10; Annex 5 para. 4.4.3(a), p. 61 asks for avoidable and
                                    unavoidable cut-ins, so the box extends below the applicability line. Bounds: design.

Applicability (where 5.2.5.2 requires collision avoidance):
  (a) cutter keeps a constant longitudinal speed lower than the ego's. esmini's lane change keeps the cutter's PATH speed, so its
      longitudinal speed sags while it turns (first pilot: up to 0.56 m/s at the lowest cutter speeds drawn; about 1 m/s for a 2 m/s cutter). Read here as: constant path speed, sag up
      to the reference point <= VLONG_SAG_MAX, and cutter speed >= V_CUT_MIN (ODD constraint). Checked per run (gate).
  (b) lateral movement visible >= 0.72 s before the TTC_LaneIntrusion reference point: tau_ref(v_cut) >= 0.72 s (about 0.8-1.0 s
      for the fixed 3 s lane change); checked per run (gate).
  (c) TTC_LaneIntrusion > v_rel / (2 * 6 m/s^2) + 0.35 s, with TTC as defined in Annex 5 para. 2.1, p. 59 (longitudinal distance /
      longitudinal relative speed at that instant) and v_rel the longitudinal relative speed at the reference point.
The parameter v_rel is the set speed difference (ego minus cutter) before the lane change.
Reference point (para. 5.2.5.2, p. 10): the outside of the tyre of the intruding front wheel closest to the lane marking crosses a line
0.3 m beyond the outside edge of the visible lane marking. Geometry: marking 0.12 m wide (scenario.xodr), front axle 2.7 m ahead
of the reference point, tyre outside edge TYRE_HALF = 0.9 m from the centre line (half track 0.8 m + assumed half tyre width 0.1 m),
rotated by the cutter's heading. TTC_LaneIntrusion is NOMINAL: gap and speeds at the reference point with the ego still at its set
speed, i.e. the criticality of the cutter's manoeuvre as set up by the test. The ego may legitimately react earlier; the actual
TTC at the reference point is recorded per run (runner: ttc_li_actual).

Pass criterion: no collision (para. 5.2.5.2). Stated safety margin (own choice, not from R157): minimum bumper gap >= D_SAFE = 1.0 m
while the cars overlap laterally. KPI: min_gap from the reference point on (all samples; collision needs lateral overlap); margin = min(min_gap, GAP_CAP) - D_SAFE. Pass if margin >= 0.
"""
import math
from functools import lru_cache
import numpy as np
from ..cutin import scenario as S

D_SAFE = 1.0          # m, stated safety margin (own choice)
GAP_CAP = 10.0        # m, cap on the KPI so that far-away runs do not dominate the GP's scale
DECEL_R157 = 6.0      # m/s^2, para. 5.2.5.2(c)
OFFSET_R157 = 0.35    # s, para. 5.2.5.2(c)
T_VIS_MIN = 0.72      # s, para. 5.2.5.2(b)
REF_BEYOND_LINE = 0.3 # m, para. 5.2.5.2 (reference point)
TYRE_HALF = 0.9       # m, assumption: half track (0.8) + half tyre width (0.1)
FRONT_AXLE_X = 2.7    # m, front axle ahead of the reference point (vehicle file, FrontAxle positionX)
MARK_HALF = 0.06      # m, half of the 0.12 m road-mark width written by cutin/scenario.xodr()
V_CUT_MIN = 6.0       # m/s, ODD constraint on the cutter's speed (keeps the longitudinal sag small)
VLONG_SAG_MAX = 0.30  # m/s, reading of "maintains its longitudinal speed" for esmini's path-speed lane change

VARS = ("ego_speed", "v_rel", "ttc_li")
XL = np.array([10.0, 0.5, 0.2])
XU = np.array([50.0 / 3.0, 8.0, 3.0])

# Reference point, yaw-aware: the outside of the intruding front tyre (2.7 m ahead of the reference point, 0.9 m to the side,
# rotated by the heading h) crosses a line 0.3 m beyond the outside edge of the 0.12 m lane marking. With the cutter's centre
# shift s(tau) from its lane centre and sin h = s'(tau) / v_cut (esmini keeps path speed v_cut), the tyre's lateral position is
# s + 2.7 sin h + 0.9 cos h, and the reference point is reached when it equals LANE/2 + MARK_HALF + 0.3 (2.11 m).
REF_LINE = S.LANE_WIDTH / 2 + MARK_HALF + REF_BEYOND_LINE


def _shift(tau):
    return S.LANE_WIDTH * (1 - np.cos(np.pi * tau / S.LC_TIME)) / 2


def _lat_speed(tau):
    return S.LANE_WIDTH * np.pi / (2 * S.LC_TIME) * np.sin(np.pi * tau / S.LC_TIME)


def tau_ref(v_cut):
    return _tau_ref(round(float(v_cut), 9))


@lru_cache(maxsize=None)
def _tau_ref(v_cut):
    """Time from lane-change start to the reference point, for a cutter at path speed v_cut (bisection on a monotone function)."""
    def y(tau):
        sh = np.clip(_lat_speed(tau) / v_cut, -1, 1); h = np.arcsin(sh)
        return _shift(tau) + FRONT_AXLE_X * np.sin(h) + TYRE_HALF * np.cos(h) - REF_LINE
    a, b = 0.0, S.LC_TIME
    for _ in range(60):
        m = (a + b) / 2
        a, b = (m, b) if y(m) < 0 else (a, m)
    return (a + b) / 2


def t_ref(v_cut):
    return S.T_LC + tau_ref(v_cut)


def cut_long_at_ref(v_cut):
    v_cut = np.atleast_1d(np.asarray(v_cut, float))
    lat = np.array([_lat_speed(tau_ref(v)) if v > 0 else 0.0 for v in v_cut])
    return np.sqrt(np.maximum(v_cut ** 2 - lat ** 2, 0.0))


def v_rel_at_ref(X):
    X = np.atleast_2d(X)
    return X[:, 0] - cut_long_at_ref(X[:, 0] - X[:, 1])


def ttc_li_min(v_rel_ref):
    """Lower bound of TTC_LaneIntrusion for which 5.2.5.2 requires avoidance (condition c, strict inequality)."""
    return np.asarray(v_rel_ref) / (2 * DECEL_R157) + OFFSET_R157


def in_odd(X):
    X = np.atleast_2d(X)
    return (X[:, 0] - X[:, 1] >= V_CUT_MIN) & (X[:, 0] - X[:, 1] - cut_long_at_ref(X[:, 0] - X[:, 1]) <= VLONG_SAG_MAX)


def applicable(X):
    """In the ODD and inside conditions (a)-(c) of para. 5.2.5.2."""
    X = np.atleast_2d(X)
    vis = np.array([tau_ref(v) for v in X[:, 0] - X[:, 1]]) >= T_VIS_MIN
    return in_odd(X) & (X[:, 2] > ttc_li_min(v_rel_at_ref(X))) & (X[:, 1] > 0) & (X[:, 0] <= XU[0] + 1e-9) & vis


def to_unit(X):
    return (np.asarray(X, float) - XL) / (XU - XL)


def from_unit(U):
    return XL + np.asarray(U, float) * (XU - XL)


def to_params(x):
    """(ego_speed, v_rel, ttc_li) -> the cut-in Params of the demo (gap at the body-crossing moment T_CUT), so that at the
    reference point the gap is ttc_li * (longitudinal v_rel there), with the ego at its set speed. Between T_CUT and T_REF the
    gap shrinks by v_rel * dt plus the cutter's extra longitudinal loss from turning (S.x_loss)."""
    v, vr, ttc = (float(a) for a in x)
    vc = v - vr; tr_ = tau_ref(vc)
    gap_ref = ttc * float(v_rel_at_ref([[v, vr, ttc]])[0])
    dloss = S.x_loss(vc, tr_) - S.x_loss(vc, S.TAU_X)
    gap_cut = gap_ref + vr * (S.T_LC + tr_ - S.T_CUT) + dloss
    return S.Params(ego_speed=v, gap=gap_cut, rel_speed=-vr)
