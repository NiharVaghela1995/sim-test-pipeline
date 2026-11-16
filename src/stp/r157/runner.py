"""One R157 cut-in run: reuse the demo's esmini runner and its 13 realisation gates, add the R157 KPI and gates.

KPI (docs/R157_TEST_DESIGN.md): min_gap = smallest bumper gap from the TTC_LaneIntrusion reference point (D.t_ref, when R157
treats the cutter as intruding into the lane) to the end of the run. Collision (gap <= 0 while the cars overlap laterally) gives
min_gap = 0. margin = min(min_gap, GAP_CAP) - D_SAFE; pass if margin >= 0. Secondary (no safety margin): collided.
esmini's ACC can drop its speed in one step beyond its deceleration limit at small gaps (GP_BOUNDARY_REPORT.md section 7); as in
the demo, a run in which that happens before the KPI minimum is not realised (gate dynamics_valid_to_kpi).

Extra gates (R157):
  ttc_li_realised   nominal TTC_LaneIntrusion (ego at its set speed, as designed) at the yaw-aware reference point found in the
                    trace, within TOL_TTC of the design; the actual TTC there (the ego may already brake) is recorded, not gated
  visibility        lateral movement started at least 0.72 s before the reference point
  cut_speed_lc      the cutter's longitudinal speed stays within TOL_VLONG of its set speed until the reference point
"""
import numpy as np
from ..cutin import runner as R, scenario as S, gates as G
from . import design as D

TOL_TTC = 0.02     # s
TOL_VLONG = D.VLONG_SAG_MAX   # m/s (design: reading of condition a)


def kpi(tr, t_ref):
    """(min_gap, collided, step of the minimum) from the reference time t_ref on."""
    t_ = np.asarray(tr["t"]); gap, dy = np.asarray(tr["gap"]), np.asarray(tr["dy"])
    k0 = int(np.searchsorted(t_, t_ref - 1e-9))
    g = gap[k0:]
    coll_mask = (g <= 0) & (np.abs(dy[k0:]) < S.CAR_WIDTH)
    if coll_mask.any():
        return 0.0, True, k0 + int(np.argmax(coll_mask))
    i = int(np.argmin(g))
    return float(max(g[i], 0.0)), False, k0 + i


def r157_gates(tr, x):
    """Reference point from the trace: the front tyre's outside edge (2.7 m ahead, 0.9 m to the side, rotated by the heading taken
    from the cutter's motion) reaches D.REF_LINE from its lane centre. TTC there: nominal (ego at set speed, as designed) and actual."""
    t = np.asarray(tr["t"]); cy = np.asarray(tr["cy"]); cx = np.asarray(tr["cx"]); cv = np.asarray(tr["cv"])
    ex = np.asarray(tr["ex"]); ev = np.asarray(tr["ev"]); gap = np.asarray(tr["gap"])
    y_cut, y_ego = G.lane_y(S.CUT_LANE), G.lane_y(S.EGO_LANE)
    sgn = np.sign(y_ego - y_cut)
    shift = (cy - y_cut) * sgn
    h = np.arctan2(np.gradient(cy) * sgn, np.gradient(cx))
    tyre = shift + D.FRONT_AXLE_X * np.sin(h) + D.TYRE_HALF * np.cos(h)
    out, info = {}, {}
    j = np.nonzero(tyre >= D.REF_LINE)[0]
    moved = np.nonzero(np.abs(cy - y_cut) > 1e-6)[0]
    if len(j) and j[0] > 0 and len(moved):
        j = int(j[0]); w = (D.REF_LINE - tyre[j - 1]) / (tyre[j] - tyre[j - 1])
        lerp = lambda a: a[j - 1] + w * (a[j] - a[j - 1])
        tr_ = lerp(t); cxr = lerp(cx); cvr = lerp(cv)
        nominal_gap = (cxr - S.REAR) - (S.EGO_S0 + x[0] * tr_ + S.FRONT)
        v_rel_long = x[0] - cvr
        ttc_nom = nominal_gap / v_rel_long
        closing = lerp(ev) - cvr
        ttc_act = lerp(gap) / closing if closing > 0 else float("inf")
        t_start = t[max(int(moved[0]) - 1, 0)]
        info.update(t_ref=float(tr_), ttc_li_meas=float(ttc_nom), ttc_li_actual=float(ttc_act), t_vis=float(tr_ - t_start),
                    v_rel_long_at_ref=float(v_rel_long), ego_speed_at_ref=float(lerp(ev)))
        out["ttc_li_realised"] = abs(ttc_nom - x[2]) <= TOL_TTC
        out["visibility"] = (tr_ - t_start) >= D.T_VIS_MIN
        out["cut_speed_lc"] = bool(np.all(np.abs(cv[1:j + 1] - (x[0] - x[1])) <= TOL_VLONG))
    else:
        out = dict(ttc_li_realised=False, visibility=False, cut_speed_lc=False)
    return out, info


def run(x, seed=0, with_trace=False, defects=S.Defects()):
    x = np.asarray(x, float); p = D.to_params(x)
    tr = R.simulate(p, seed, defects)
    if tr["init_ok"]:
        min_gap, coll, k_min = kpi(tr, D.t_ref(x[0] - x[1]))
    else:
        min_gap, coll, k_min = float("nan"), False, None
    g, info = G.check(tr, p, R.DT, k_min)      # includes dynamics_valid_to_kpi: no over-braking before the KPI minimum
    over = info.get("overbrake_step") is not None
    g2, info2 = r157_gates(tr, x) if tr["init_ok"] else ({}, {})
    g.update(g2); info.update(info2)
    realised = all(g.values())
    margin = min(min_gap, D.GAP_CAP) - D.D_SAFE
    rec = dict(x=[float(v) for v in x], applicable=bool(D.applicable(x)[0]), in_odd=bool(D.in_odd(x)[0]), seed=int(seed), realised=bool(realised), gates=g,
               min_gap=float(min_gap), margin=float(margin), failed=bool(realised and margin < 0), collided=bool(coll),
               overbrake=bool(over), **{k: info.get(k) for k in ("ttc_li_meas", "ttc_li_actual", "ego_speed_at_ref", "t_ref", "t_vis", "v_rel_long_at_ref", "gap_at_cut")})
    if with_trace:
        rec["trace"] = tr
    return rec
