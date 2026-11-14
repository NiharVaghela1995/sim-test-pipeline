"""One cut-in run on the pinned esmini: the ego is driven by esmini's ACCController (the system under test), the cutting
car by the scripted storyboard. Returns the run record: params, seed, realised, gates, min_ttc, margin, failed.

KPI (docs/GP_BOUNDARY_PLAN.md):
  TTC(t) = gap(t) / closing(t), only while the cars overlap laterally (|dy| < CAR_WIDTH), the cutting car is ahead and
  closing(t) = v_ego,x - v_cut,x > 0. gap <= 0 with lateral overlap is a collision and gives TTC = 0.
  min_ttc = min over the run of TTC(t), capped at TTC_CAP (no closing at all gives TTC_CAP).
  margin  = min_ttc - TTC_RULE. Pass if margin >= 0.
"""
import math
import tempfile
from pathlib import Path
import numpy as np
from .. import esmini_lib as E
from . import scenario as S, gates

DT = 0.02
TTC_RULE = 1.5      # s, placeholder threshold, not a quoted regulation value
TTC_CAP = 6.0       # s
ctypes = E.C


def kpi(trace):
    """(min TTC, collided, step of the minimum) from a trace with per-step lists gap, dy, closing.
    Pure function, tested on constructed traces. The step is None if TTC never fell below the cap."""
    ttc, k_min, collided = TTC_CAP, None, False
    for k, (g, dy, c) in enumerate(zip(trace["gap"], trace["dy"], trace["closing"])):
        if abs(dy) >= S.CAR_WIDTH:
            continue
        if g <= 0.0:
            if g > -S.CAR_LENGTH * 2:   # overlap in x as well: contact
                if not collided: k_min = k if ttc > 0.0 else k_min
                collided = True; ttc = 0.0
            continue
        if c > 0.0 and g / c < ttc:
            ttc, k_min = g / c, k
    return ttc, collided, k_min


def simulate(p: S.Params, seed: int, defects: S.Defects = S.Defects(), keep_file: Path = None):
    """Run esmini and return the raw per-step trace."""
    n_steps = int(round(defects.t_end / DT))
    tr = dict(init_ok=False, ctrl=[-1, -1], t=[], ex=[], ey=[], ev=[], elane=[], cx=[], cy=[], cv=[], clane=[], gap=[], dy=[], closing=[], sim_time=0.0, steps=0, quit=False)
    with tempfile.TemporaryDirectory(prefix="stp_cut_") as tmp:
        f = S.write(p, Path(tmp), defects)
        if keep_file is not None:
            keep_file.parent.mkdir(parents=True, exist_ok=True); keep_file.write_text(f.read_text())
        E.L.SE_SetLogFilePath(b""); E.L.SE_LogToConsole(False); E.L.SE_SetSeed(seed & 0xFFFFFFFF)
        rc = E.L.SE_Init(str(f).encode(), 0, 0, 0, 0)
        tr["init_ok"] = rc == 0
        if rc == 0:
            ids = [E.L.SE_GetId(0), E.L.SE_GetId(1)]
            a, b = E.ObjectState(), E.ObjectState()

            def sample():
                E.L.SE_GetObjectState(ids[0], ctypes.byref(a)); E.L.SE_GetObjectState(ids[1], ctypes.byref(b))
                tr["t"].append(E.L.SE_GetSimulationTime())
                tr["ex"].append(a.x); tr["ey"].append(a.y); tr["ev"].append(a.speed * math.cos(a.h)); tr["elane"].append(a.laneId)
                tr["cx"].append(b.x); tr["cy"].append(b.y); tr["cv"].append(b.speed * math.cos(b.h)); tr["clane"].append(b.laneId)
                # straight road along +x: bumper-to-bumper gap from the reference points
                tr["gap"].append((b.x - S.REAR) - (a.x + S.FRONT)); tr["dy"].append(b.y - a.y); tr["closing"].append(tr["ev"][-1] - tr["cv"][-1])
                return a.ctrl_type, b.ctrl_type

            tr["ctrl"] = list(sample())
            for _ in range(n_steps):
                E.L.SE_StepDT(DT); tr["steps"] += 1; sample()
            tr["sim_time"] = E.L.SE_GetSimulationTime()
        E.L.SE_Close()
    return tr


def run(p: S.Params, seed: int = 0, defects: S.Defects = S.Defects(), spec: S.Params = None, keep_file: Path = None, with_trace=False):
    """Execute p (with optional defects). Gates compare the execution with spec (default p)."""
    tr = simulate(p, seed, defects, keep_file)
    ttc, collided, k_min = kpi(tr) if tr["init_ok"] else (float("nan"), False, None)
    g, info = gates.check(tr, spec or p, DT, k_min)
    realised = all(g.values())
    margin = ttc - TTC_RULE
    rec = dict(params=(spec or p).dict(), seed=int(seed), realised=bool(realised), gates=g, min_ttc=float(ttc), margin=float(margin),
               failed=bool(realised and margin < 0.0), collided=bool(collided), gap_at_cut=info.get("gap_at_cut"), overbrake=info.get("overbrake_step") is not None, min_ego_speed=float(min(tr["ev"])) if tr["ev"] else None)
    if with_trace:
        rec["trace"] = tr
    return rec
