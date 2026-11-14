"""Realisation checks for the cut-in: did esmini execute the scenario that was specified? A run that fails any gate
is NOT_REALISED, is logged, and gets no pass or fail. Each check compares the executed trace with the intended Params."""
import numpy as np
from . import scenario as S

ACC_TYPE, DEFAULT_TYPE = 8, 0     # esmini 3.11.0 Controller::Type values, read from ObjectState.ctrl_type
TOL_POS = 0.05      # m
TOL_SPEED = 0.05    # m/s
TOL_GAP = 0.05      # m, bumper gap at the cut-in moment
TOL_T = 0.021       # s, about one step
TOL_LAT = 0.05      # m, final lateral position
TOL_LC_DUR = 0.10   # s
TTC_CAP_FOR_SETTLED = 6.0   # s, same as runner.TTC_CAP


def lane_y(lane):
    return -(abs(lane) - 0.5) * S.LANE_WIDTH


def check(tr, p: S.Params, dt, k_min_ttc=None):
    g, info = {}, {"k_min_ttc": k_min_ttc}
    g["loaded"] = bool(tr["init_ok"])
    if not tr["init_ok"]:
        return {k: False for k in ("loaded", "controllers", "start_pose", "start_speed", "cut_speed_held", "ego_cruise_before_cut",
                                     "lane_change_start", "gap_at_cut", "lane_change_end", "ego_lane_kept", "outcome_settled", "dynamics_valid_to_kpi", "clock")}, info
    t = np.asarray(tr["t"]); cy = np.asarray(tr["cy"]); ey = np.asarray(tr["ey"])
    g["controllers"] = tr["ctrl"] == [ACC_TYPE, DEFAULT_TYPE]
    y_ego, y_cut = lane_y(S.EGO_LANE), lane_y(S.CUT_LANE)
    g["start_pose"] = (abs(tr["ex"][0] - S.EGO_S0) <= TOL_POS and abs(ey[0] - y_ego) <= TOL_POS and tr["elane"][0] == S.EGO_LANE
                       and abs(tr["cx"][0] - p.cut_s0) <= TOL_POS and abs(cy[0] - y_cut) <= TOL_POS and tr["clane"][0] == S.CUT_LANE)
    # speeds after the first step (speeds are applied by step actions in Init)
    g["start_speed"] = abs(tr["ev"][1] - p.ego_speed) <= TOL_SPEED and abs(tr["cv"][1] - p.cut_speed) <= TOL_SPEED
    # the cutting car's longitudinal speed: constant before the lane change; its path speed is constant throughout
    pre = t < S.T_LC - 1e-9
    g["cut_speed_held"] = bool(np.all(np.abs(np.asarray(tr["cv"])[1:][pre[1:]] - p.cut_speed) <= TOL_SPEED))
    moved = np.nonzero(np.abs(cy - y_cut) > 1e-6)[0]
    shift = (cy - y_cut) * np.sign(y_ego - y_cut)     # signed: positive towards the ego lane
    crossed = np.nonzero(shift >= S.LINE_SHIFT)[0]
    if len(moved) and len(crossed) and crossed[0] > 0:
        i0 = max(int(moved[0]) - 1, 0)       # last sample before the lateral move: lane change start
        info["t_lc"] = float(t[i0])
        g["lane_change_start"] = abs(t[i0] - S.T_LC) <= TOL_T
        j = int(crossed[0]); w = (S.LINE_SHIFT - shift[j - 1]) / (shift[j] - shift[j - 1])   # interpolate to the crossing
        tx = t[j - 1] + w * (t[j] - t[j - 1]); gx = tr["gap"][j - 1] + w * (tr["gap"][j] - tr["gap"][j - 1])
        info["t_cut"] = float(tx); info["gap_at_cut"] = float(gx)
        # The scenario controls the cutting car, not the ego: the ACC may legitimately brake once the cutting car moves
        # sideways. So the check is on the nominal gap, from the cutting car's executed position and an ego that kept
        # its set speed; the executed gap (larger if the ego braked early) is recorded as info.
        cx = tr["cx"][j - 1] + w * (tr["cx"][j] - tr["cx"][j - 1])
        nominal = (cx - S.REAR) - (S.EGO_S0 + p.ego_speed * tx + S.FRONT)
        info["nominal_gap_at_cut"] = float(nominal)
        g["gap_at_cut"] = abs(nominal - p.gap) <= TOL_GAP and abs(tx - S.T_CUT) <= TOL_T
        # the ego must be cruising at its set speed until the lane change starts (no reaction to the adjacent lane)
        g["ego_cruise_before_cut"] = bool(np.all(np.abs(np.asarray(tr["ev"])[1:i0 + 1] - p.ego_speed) <= TOL_SPEED))
        arrived = np.nonzero(np.abs(cy - y_ego) <= TOL_LAT)[0]
        if len(arrived):
            dur = t[int(arrived[0])] - t[i0]
            info["lc_duration"] = float(dur)
            g["lane_change_end"] = (dur <= S.LC_TIME + TOL_LC_DUR and tr["clane"][-1] == S.EGO_LANE
                                    and bool(np.all(np.abs(cy[arrived[0]:] - y_ego) <= TOL_LAT)))
        else:
            g["lane_change_end"] = False
    else:
        g["lane_change_start"] = g["gap_at_cut"] = g["lane_change_end"] = False
        g["ego_cruise_before_cut"] = bool(np.all(np.abs(np.asarray(tr["ev"])[1:] - p.ego_speed) <= TOL_SPEED))
    g["ego_lane_kept"] = bool(np.all(np.abs(ey - y_ego) <= TOL_POS)) and all(l == S.EGO_LANE for l in tr["elane"])
    # the minimum TTC has been reached: at the end the ego is not closing in, or its TTC is above the cap
    c_end, g_end = tr["closing"][-1], tr["gap"][-1]
    g["outcome_settled"] = bool(c_end <= 0.05 or g_end / c_end > TTC_CAP_FOR_SETTLED) and abs(tr["dy"][-1]) < S.CAR_WIDTH
    # esmini's ACC can drop the speed in one step far beyond maxDeceleration when the gap is below about 0.7 m.
    # The run is only usable if that has not happened before the KPI minimum.
    ev = np.asarray(tr["ev"]); over = np.nonzero(-np.diff(ev) / dt > S.MAX_DECEL + 0.01)[0]
    info["overbrake_step"] = int(over[0]) + 1 if len(over) else None
    k_min = info.get("k_min_ttc")
    g["dynamics_valid_to_kpi"] = (not len(over)) or (k_min is not None and k_min <= int(over[0]))
    g["clock"] = abs(tr["sim_time"] - tr["steps"] * dt) <= dt / 2
    return {k: bool(v) for k, v in g.items()}, info
