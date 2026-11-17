"""Noisy SUT for the R157 cut-in: esmini runs the world (road, scripted cutter, ego kinematics); the ego is driven by the Python
port of esmini's ACC (acc.py) through esmini's ExternalController. Between world and controller sit

  perception noise   on the cutter's position (longitudinal x, lateral y) and path speed, each a stationary AR(1) process
                     e[k+1] = rho e[k] + sqrt(1 - rho^2) sigma w[k], rho = exp(-dt / TAU_NOISE), w ~ N(0, 1)
  actuation delay    the commanded speed reaches the vehicle DELAY seconds later (pure transport delay, a FIFO of steps)

Timing as in esmini's own ACC: at step k the controller sees the state at t_k and moves the ego to x_k + v dt before esmini
advances the cutter. The noise stream is drawn from numpy's PCG64 seeded with the run's replicate seed, so a run is fixed by
(x, level, seed). Noise levels: docs/NOISE_PLAN.md.
"""
import math
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
from scipy.signal import lfilter
from .. import esmini_lib as E
from ..cutin import scenario as S
from . import acc as A

DT = 0.02
TAU_NOISE = 0.5          # s, correlation time of the perception error (design choice, NOISE_PLAN.md)
EXTERNAL_TYPE = 1        # esmini Controller::Type CONTROLLER_TYPE_EXTERNAL
ctypes = E.C


@dataclass(frozen=True)
class Level:
    name: str
    sigma_x: float = 0.0     # m, longitudinal position error of the cutter
    sigma_y: float = 0.0     # m, lateral position error
    sigma_v: float = 0.0     # m/s, path-speed error
    delay: float = 0.0       # s, actuation delay

    def dict(self):
        return asdict(self)

    @property
    def noisy(self):
        return self.sigma_x > 0 or self.sigma_y > 0 or self.sigma_v > 0 or self.delay > 0


def noise_stream(level: Level, n, seed):
    """(n, 3) array of AR(1) errors (x, y, v), stationary from the first sample."""
    rng = np.random.default_rng(seed)
    w = rng.standard_normal((n, 3)); sig = np.array([level.sigma_x, level.sigma_y, level.sigma_v])
    rho = math.exp(-DT / TAU_NOISE); q = math.sqrt(1 - rho ** 2)
    w[1:] *= q                                   # e[0] = w[0] (stationary start), e[k] = rho e[k-1] + q w[k]
    e = lfilter([1.0], [1.0, -rho], w, axis=0)
    return (e * sig).tolist()


def simulate(p: S.Params, level: Level, seed: int, defects: S.Defects = S.Defects()):
    """Closed-loop run; returns the same trace dict as cutin.runner.simulate plus the controller's commanded speed."""
    d = S.Defects(**{**asdict(defects), "ego_controller": "ExternalController"}) if defects.ego_controller == "ACCController" else defects
    n_steps = int(round(d.t_end / DT))
    tr = dict(init_ok=False, ctrl=[-1, -1], t=[], ex=[], ey=[], ev=[], elane=[], cx=[], cy=[], cv=[], clane=[], gap=[], dy=[], closing=[],
              v_cmd=[], sim_time=0.0, steps=0, quit=False)
    err = noise_stream(level, n_steps + 1, seed)
    lag = int(round(level.delay / DT))
    with tempfile.TemporaryDirectory(prefix="stp_noise_") as tmp:
        f = S.write(p, Path(tmp), d)
        E.L.SE_SetLogFilePath(b""); E.L.SE_LogToConsole(False); E.L.SE_SetSeed(0)
        rc = E.L.SE_Init(str(f).encode(), 0, 0, 0, 0)
        tr["init_ok"] = rc == 0
        if rc == 0:
            ids = [E.L.SE_GetId(0), E.L.SE_GetId(1)]
            a, b = E.ObjectState(), E.ObjectState()

            def sample(xe=None, ve=None):
                E.L.SE_GetObjectState(ids[0], ctypes.byref(a)); E.L.SE_GetObjectState(ids[1], ctypes.byref(b))
                ex_ = a.x if xe is None else xe; ev_ = a.speed * math.cos(a.h) if ve is None else ve
                tr["t"].append(E.L.SE_GetSimulationTime())
                tr["ex"].append(ex_); tr["ey"].append(a.y); tr["ev"].append(ev_); tr["elane"].append(a.laneId)
                tr["cx"].append(b.x); tr["cy"].append(b.y); tr["cv"].append(b.speed * math.cos(b.h)); tr["clane"].append(b.laneId)
                tr["gap"].append((b.x - S.REAR) - (ex_ + S.FRONT)); tr["dy"].append(b.y - a.y); tr["closing"].append(ev_ - tr["cv"][-1])
                return a.ctrl_type, b.ctrl_type

            tr["ctrl"] = list(sample())
            v_set = p.ego_speed + d.ego_speed_shift
            ctl = A.ACC(v_set)
            fifo = [v_set] * lag
            x_ego, y_ego, v_act = a.x, a.y, v_set
            active = d.ego_controller == "ExternalController"
            for k in range(n_steps):
                # esmini's own ACC steps after the scripted cutter has moved: it sees the cutter at t_k+1 and the ego at t_k.
                # Here: esmini advances the world with the ego held at x_k (ExternalController does not move it), then the
                # controller sees the cutter at t_k+1 (with perception error), commands a speed, and the ego is reported at
                # x_k + v dt. The ego's trace comes from these reported values.
                E.L.SE_StepDT(DT); tr["steps"] += 1
                if active:
                    E.L.SE_GetObjectState(ids[1], ctypes.byref(b)); e = err[k]
                    v_cmd = ctl.step((x_ego, y_ego, 0.0), (b.x + e[0], b.y + e[1], b.h), b.speed + e[2], DT)
                    fifo.append(v_cmd); v_act = fifo.pop(0)
                    x_ego += v_act * DT
                    E.L.SE_ReportObjectPosXYH(ids[0], x_ego, y_ego, 0.0); E.L.SE_ReportObjectSpeed(ids[0], v_act)
                    tr["v_cmd"].append(v_cmd)
                    sample(x_ego, v_act)
                else:
                    sample()
            tr["sim_time"] = E.L.SE_GetSimulationTime()
        E.L.SE_Close()
    return tr
