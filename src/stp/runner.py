"""Run one scenario instance closed loop. Returns verdict, safety margin, realisation gates."""
import math
import tempfile
from pathlib import Path
import numpy as np
from . import esmini_lib as E, gates, scenario as S
from .sut import LaneKeeper, SutConfig

DT = 0.02
ctypes = E.C


def run(p: S.Params, seed: int, cfg: SutConfig = SutConfig(), spec: S.Params = None, **scenario_kw):
    """Execute p. Gates compare the execution with spec (default p), so a mismatch between intent and execution is caught."""
    rng = np.random.default_rng(seed)
    gust_period = rng.uniform(*cfg.gust_period); gust_phase = rng.uniform(0, cfg.gust_phase_span)
    tr = dict(curv=[], ended_early=False, init_ok=False, ctrl_type=-1, s0=-1, t0=99, lane0=0, steps=0, s_max=0.0, sim_time=0.0, speed_mean=0.0)
    with tempfile.TemporaryDirectory(prefix="stp_") as tmp:
        f = S.write(p, Path(tmp), **scenario_kw)
        E.L.SE_SetLogFilePath(b""); E.L.SE_LogToConsole(False)
        rc = E.L.SE_Init(str(f).encode(), 0, 0, 0, 0)
        tr["init_ok"] = rc == 0
        margin, offs = 99.0, []
        if rc == 0:
            oid = E.L.SE_GetId(0); st = E.ObjectState(); ri = E.RoadInfo()
            E.L.SE_GetObjectState(oid, ctypes.byref(st))
            tr.update(ctrl_type=st.ctrl_type, s0=st.s, t0=st.t, lane0=st.laneId)
            x, y, h, v = st.x, st.y, st.h, p.speed
            lk = LaneKeeper(cfg, rng); speeds = []
            t_max = (S.ROAD_LENGTH - 5) / max(p.speed, 1e-3) + 2
            half = S.LANE_WIDTH / 2
            for i in range(int(t_max / DT)):
                E.L.SE_GetRoadInfoAtDistance(oid, lk.lookahead(v), ctypes.byref(ri), 0, True)
                kappa = lk.step(ri.local_pos_x, ri.local_pos_y, v, DT)
                g = p.gust * math.sin(2 * math.pi * i * DT / gust_period + gust_phase)
                h += v * kappa * DT
                x += DT * (v * math.cos(h) - g * math.sin(h)); y += DT * (v * math.sin(h) + g * math.cos(h))
                E.L.SE_ReportObjectPosXYH(oid, x, y, h); E.L.SE_ReportObjectSpeed(oid, v)
                E.L.SE_StepDT(DT)
                E.L.SE_GetObjectState(oid, ctypes.byref(st))
                tr["steps"] += 1; speeds.append(st.speed)
                off = st.t + half; offs.append(off); margin = min(margin, half - (abs(off) + st.width / 2))
                tr["s_max"] = max(tr["s_max"], st.s)
                if i % 25 == 0:
                    E.L.SE_GetRoadInfoAtDistance(oid, 0.0, ctypes.byref(ri), 0, True); tr["curv"].append((ri.s, ri.curvature))
                if st.s >= S.ROAD_LENGTH - 8: break
                if margin < -3.0:
                    tr["ended_early"] = True; break
            tr["sim_time"] = E.L.SE_GetSimulationTime(); tr["speed_mean"] = float(np.mean(speeds[5:])) if len(speeds) > 5 else 0.0
        E.L.SE_Close()
    g = gates.check(tr, spec or p, DT, **{k: v for k, v in scenario_kw.items() if k in ("start_s", "lane")})
    realised = all(g.values())
    return dict(params=p.dict(), seed=int(seed), realised=realised, gates=g, margin=float(margin), failed=bool(realised and margin < 0.0), peak_offset=float(np.max(np.abs(offs))) if offs else 0.0, steps=tr["steps"])
