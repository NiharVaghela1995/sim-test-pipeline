# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
# distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Ported from esmini (https://github.com/esmini/esmini), ControllerACC.cpp, tag v3.11.0, which is under MPL-2.0.
"""Python port of esmini 3.11.0's ACCController (EnvironmentSimulator/Modules/Controllers/ControllerACC.cpp, tag v3.11.0),
so that perception noise and an actuation delay can be put between the world and the controller. esmini's own ACC reads
ground truth inside C++ and cannot be given either.

What is ported, line by line (comments name the C++ step):
  lead selection   a) same lane (dLaneId == 0), ref-point-to-ref-point distance along the road minus the bounding-box offsets,
                      > 0, |lateral offset| < lateralDist (5 m); b) "really close" check with esmini's free-space distance
                      (separating-axis projections on the ego's axes, Object::CollisionAndRelativeDistLatLong):
                      0 < x_local < 1 + L_lead + 0.5 max(0, v - v_lead) and -0.5 < y_local < 0.2
  control law      gap < 1 m: speed set to 0 at once (the over-braking artefact the realisation gate catches); otherwise
                   acc = 2.5 f - f (v - v_set) - (1 - f)(v - min(v_set, v_lead)), f = min(1, (gap - d_follow)/d_follow),
                   d_follow = 3 + timeGap max(v, v_lead); clamped to [-maxDec, maxAcc]; v += acc dt; v in [0, v_set]
                   no lead: acc = 0.7 maxAcc (v_set - v), clamped, no overshoot of v_set
Not ported (cannot occur here): the "new set speed from another action" check (no other action drives the ego), the
virtual mode, lookahead beyond 50 m (every lead in this scenario is closer), lateral control.

Inputs come through a Perception object: the lead's position, heading and path speed as the controller sees them. With
noise off the port is checked against esmini's ACC on the stored R157 reference runs (tests/test_noise.py, docs/NOISE_PLAN.md).
"""
import math
import numpy as np
from ..cutin import scenario as S

MIN_DIST = 3.0          # m, ControllerACC.cpp minDist
ACC_FACTOR = 0.7        # accelerationFactor
LATERAL_DIST = 5.0      # m, lateralDist_ default
LOOKAHEAD_MIN = 50.0    # m
SMALL = 1e-10           # esmini SMALL_NUMBER


_L2, _W2 = S.CAR_LENGTH / 2, S.CAR_WIDTH / 2
_LOC = ((S.BB_X + _L2, _W2), (S.BB_X - _L2, _W2), (S.BB_X - _L2, -_W2), (S.BB_X + _L2, -_W2))


def _corners(x, y, h):
    """Bounding-box corners (esmini order: first quadrant first) of a car at reference point (x, y), heading h."""
    c, s = math.cos(h), math.sin(h)
    return [(x + c * u - s * v, y + s * u + c * v) for u, v in _LOC]


def free_space_lat_long(ego, lead):
    """(collision, lat, long) as Object::CollisionAndRelativeDistLatLong: gaps measured on the ego's own axes (only i == 0
    records them). ego, lead = (x, y, h). lat < 0: lead to the ego's right. Plain Python: numpy is slower on 4 points."""
    P = (_corners(*ego), _corners(*lead))
    lat = lon = 0.0; gap = False
    for i in range(2):
        h = (ego if i == 0 else lead)[2]
        A, B = (P[0], P[1]) if i == 0 else (P[1], P[0])
        c, s = math.cos(h), math.sin(h)
        for j, n in enumerate(((-s, c), (c, s))):          # rotated (0, 1) and (1, 0)
            pa = [p[0] * n[0] + p[1] * n[1] for p in A]; pb = [p[0] * n[0] + p[1] * n[1] for p in B]
            mn0, mx0, mn1, mx1 = min(pa), max(pa), min(pb), max(pb)
            below = mn0 < mn1 - SMALL and mx0 < mn1 - SMALL
            above = mx0 > mx1 + SMALL and mn0 > mx1 + SMALL
            if below or above:
                gap = True
                if i == 0:
                    d = (mn1 - mx0) if below else -(mn0 - mx1)
                    if j == 0: lat = d
                    else: lon = d
    return (not gap), lat, lon


def lane_of(y):
    """Lane id on the straight two-lane road (lane -1: 0 > y > -3.5, lane -2 below). On the line itself esmini still reports
    the outer lane (seen in the trace at y = -3.5 + 2e-15), hence the 1e-9 m tie tolerance."""
    return -1 if y > -S.LANE_WIDTH + 1e-9 else -2


class ACC:
    def __init__(self, set_speed, time_gap=S.ACC_TIME_GAP, max_dec=S.MAX_DECEL, max_acc=3.0):
        self.v_set, self.tg, self.dec, self.acc_max = float(set_speed), time_gap, max_dec, max_acc
        self.v = float(set_speed)        # currentSpeed_ (Activate: object speed, = set speed after the init speed action)

    def step(self, ego, lead, v_lead, dt):
        """ego = (x, y, h) true ego pose; lead = (x, y, h) as perceived, v_lead perceived path speed. Returns the commanded speed."""
        v = self.v
        min_gap, found = math.inf, False
        # a) lane-based lead (Position::Delta, ref point to ref point; straight road, so ds = dx and dt = dy)
        ds, dts = lead[0] - ego[0], lead[1] - ego[1]
        look = max(LOOKAHEAD_MIN, 2 * MIN_DIST - v ** 2 / -self.dec)
        if abs(ds) <= look:
            adj = ds - ((S.CAR_LENGTH / 2 + S.BB_X) + (S.CAR_LENGTH / 2 - S.BB_X))     # same direction
            if lane_of(lead[1]) == lane_of(ego[1]) and 0 < adj < min_gap and abs(dts) < LATERAL_DIST:
                min_gap, found = adj, True
        # b) really close in front (only if a) did not pick this object)
        if not found:
            _, y_loc, x_loc = free_space_lat_long(ego, lead)
            if 0 < x_loc < 1.0 + S.CAR_LENGTH + 0.5 * max(0.0, v - v_lead) and -0.5 < y_loc < 0.2:
                min_gap, found = x_loc, True
        if found:
            if min_gap < 1:
                v = 0.0
            else:
                d_follow = MIN_DIST + self.tg * abs(max(v, v_lead))
                f = min(1.0, (min_gap - d_follow) / d_follow)
                dv_min = v - min(self.v_set, v_lead); dv_set = v - self.v_set
                a = 2.5 * f - f * dv_set - (1 - f) * dv_min
                a = min(max(a, -self.dec), self.acc_max)
                v = min(max(0.0, v + a * dt), self.v_set)
        else:
            a = (self.v_set - v) * ACC_FACTOR * self.acc_max
            a = min(max(a, -self.dec), ACC_FACTOR * self.acc_max)
            tmp = v + a * dt
            v = self.v_set if abs(tmp - self.v_set) > abs(v - self.v_set) else tmp
        self.v = v
        return v
