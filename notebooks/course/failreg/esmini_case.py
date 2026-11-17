"""The small esmini cut-in case at the end of each notebook, reusing the repo's pipeline (src/stp).

  cutin()        deterministic: esmini's ACC ego against a scripted cut-in (stp.cutin.runner), a 2-D slice at
                 ego speed 30 m/s over (gap at cut-in 5-40 m, relative speed -10-0 m/s). Fail: min TTC < 1.5 s.
                 Answer key: the committed dense reference grid results/gp_boundary/reference_grid.npz (141 x 21 at 30 m/s).
  noisy_cutin()  noisy: the R157 cut-in with perception noise and actuation delay, level 'mid' (stp.noise.runner), a 2-D
                 slice at ego speed 13.3 m/s over (v_rel 0.5-8 m/s, TTC at lane intrusion 0.2-3 s). Fail: min gap < 1 m.
                 Target {p(x) >= 0.10}; answer key p_iso from results/noise/reference_mid.npz on the applicable points.

Each run takes about 0.03 s (deterministic) or 0.05 s (noisy) on one CPU core. A run whose realisation check fails
returns NaN and is not used as data.
"""
import sys
from pathlib import Path
import numpy as np
from .problems import Problem

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


class EsminiProblem(Problem):
    def __init__(self, name, run_one, lo, hi, test, labels, alpha=0.5, noisy=False):
        super().__init__(name, 2, f=None, tau=0.0, alpha=alpha, labels=labels)
        self.run_one, self.lo, self.hi = run_one, np.asarray(lo, float), np.asarray(hi, float)
        self._test = test
        self._noisy = noisy
        self.records = []

    @property
    def noisy(self):
        return self._noisy

    def to_phys(self, U):
        return self.lo + np.atleast_2d(U) * (self.hi - self.lo)

    def run(self, U, rng):
        out = []
        for x in self.to_phys(U):
            r = self.run_one(x, int(rng.integers(2 ** 31)))
            self.records.append(r); self.calls += 1
            out.append(r["margin"] if r["realised"] else np.nan)
        return np.array(out)

    def noise_sd(self, U):
        """Not known for the simulator; the loop uses the model's own noise estimate instead."""
        raise NotImplementedError


def cutin(ego_speed=30.0):
    from stp.cutin import runner, scenario as S
    R = np.load(ROOT / "results/gp_boundary/reference_grid.npz")
    iv = int(np.argmin(np.abs(R["V"] - ego_speed)))
    G_, DV = R["G"], R["DV"]
    gg, dd = np.meshgrid((G_ - G_[0]) / np.ptp(G_), (DV - DV[0]) / np.ptp(DV), indexing="ij")
    U = np.column_stack([gg.ravel(), dd.ravel()])
    margin = R["margin"][iv].T.ravel()                     # (DV, G) -> (G, DV)
    ok = R["realised"][iv].T.ravel()
    truth = (margin < 0) & ok

    def run_one(x, seed):
        return runner.run(S.Params(float(R["V"][iv]), float(x[0]), float(x[1])), seed)

    p = EsminiProblem("esmini_cutin", run_one, [G_[0], DV[0]], [G_[-1], DV[-1]], (U, truth, (len(G_), len(DV)), ok),
                      ("gap at cut-in [m]", "relative speed [m/s]"))
    p.true_margin = margin
    p.ego_speed = float(R["V"][iv])
    return p


def noisy_cutin(level="mid", ego_index=2):
    from stp.noise import runner as NR
    from stp.noise.experiment import LEVELS, MIN_REAL_TRUTH
    R = np.load(ROOT / f"results/noise/reference_{level}.npz")
    VR, T = R["VR"], R["T"]
    v = float(R["V"][ego_index])
    rr, tt = np.meshgrid((VR - VR[0]) / np.ptp(VR), (T - T[0]) / np.ptp(T), indexing="ij")
    U = np.column_stack([rr.ravel(), tt.ravel()])
    ok = (R["applicable"][ego_index] & (R["realised"][ego_index] >= MIN_REAL_TRUTH)).ravel()
    p_true = R["p_iso"][ego_index].ravel()
    truth = (p_true >= 0.10) & ok

    def run_one(x, seed):
        return NR.run([v, x[0], x[1]], LEVELS[level], seed)

    p = EsminiProblem(f"esmini_noisy_{level}", run_one, [VR[0], T[0]], [VR[-1], T[-1]], (U, truth, (len(VR), len(T)), ok),
                      ("v_rel [m/s]", "TTC at lane intrusion [s]"), alpha=0.10, noisy=True)
    p.p_true, p.ego_speed = p_true, v
    return p
