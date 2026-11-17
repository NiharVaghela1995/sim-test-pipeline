"""One noisy R157 cut-in run: the R157 KPI, margin and all 16 realisation gates of r157/runner.py, with the ego driven by the
ported ACC through sut.simulate. Only change to the gates: `controllers` expects esmini's ExternalController on the ego
(type 1) instead of its ACCController (type 8), because the ACC now runs outside esmini.
"""
import numpy as np
from ..cutin import scenario as S, gates as G
from ..r157 import design as D, runner as RR
from . import sut as N


def run(x, level: N.Level, seed=0, with_trace=False, defects=S.Defects()):
    x = np.asarray(x, float); p = D.to_params(x)
    tr = N.simulate(p, level, seed, defects)
    if tr["init_ok"]:
        min_gap, coll, k_min = RR.kpi(tr, D.t_ref(x[0] - x[1]))
    else:
        min_gap, coll, k_min = float("nan"), False, None
    g, info = G.check(tr, p, N.DT, k_min)
    g["controllers"] = tr["ctrl"] == [N.EXTERNAL_TYPE, G.DEFAULT_TYPE]
    over = info.get("overbrake_step") is not None
    g2, info2 = RR.r157_gates(tr, x) if tr["init_ok"] else ({}, {})
    g.update(g2); info.update(info2)
    realised = all(g.values())
    margin = min(min_gap, D.GAP_CAP) - D.D_SAFE
    rec = dict(x=[float(v) for v in x], level=level.name, seed=int(seed), realised=bool(realised), gates=g, min_gap=float(min_gap),
               margin=float(margin), failed=bool(realised and margin < 0), collided=bool(coll), overbrake=bool(over),
               **{k: info.get(k) for k in ("ttc_li_meas", "ttc_li_actual", "ego_speed_at_ref")})
    if with_trace:
        rec["trace"] = tr
    return rec
