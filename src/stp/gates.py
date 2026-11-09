"""Realisation checks: did the simulator execute the scenario that was specified? A run that fails a gate is NOT_REALISED and gets no verdict."""
from .scenario import L_IN, L_ARC1, LANE_WIDTH

TOL_CURV, TOL_SPEED, TOL_START = 2e-4, 0.05, 0.05


def check(trace, p, dt, start_s=5.0, lane=-1):
    g = {}
    g["loaded"] = bool(trace["init_ok"])
    g["external_control"] = trace["ctrl_type"] == 1
    g["start_pose"] = abs(trace["s0"] - start_s) <= TOL_START and trace["lane0"] == lane and abs(trace["t0"] + LANE_WIDTH / 2) <= TOL_START
    g["speed_applied"] = abs(trace["speed_mean"] - p.speed) <= TOL_SPEED
    # esmini reports curvature along the lane centre: k / (1 + k * lane_offset), right lane at half a lane from the reference line
    half = LANE_WIDTH / 2
    lane_k = lambda k: k / (1 + k * half)
    k = lambda a, b: [c for s, c in trace["curv"] if a + 2 <= s <= b - 2]
    a1, a2 = k(L_IN, L_IN + L_ARC1), k(L_IN + L_ARC1, L_IN + 2 * L_ARC1)
    g["road_arc1"] = bool(a1) and max(abs(c - lane_k(p.k1)) for c in a1) <= TOL_CURV
    g["road_arc2"] = max(abs(c - lane_k(p.k2)) for c in a2) <= TOL_CURV if a2 else trace["ended_early"]
    g["clock"] = abs(trace["sim_time"] - trace["steps"] * dt) <= dt
    g["reached_curve"] = trace["s_max"] >= L_IN + 5
    return g
