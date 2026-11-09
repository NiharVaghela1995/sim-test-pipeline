"""Connect the runner to OpenSBT 0.1.7: simulator, fitness, oracle, problem."""
import hashlib
import json
import numpy as np
from opensbt.evaluation.critical import Critical
from opensbt.evaluation.fitness import Fitness
from opensbt.problem.adas_problem import ADASProblem
from opensbt.simulation.simulator import Simulator, SimulationOutput
from . import runner, scenario as S

WORST = 10.0  # fitness for a run that was not realised, so search does not exploit broken runs


class Log:
    records = []; tag = ""; counter = 0


def _seed(tag, i):
    return int.from_bytes(hashlib.sha256(f"{tag}:{i}".encode()).digest()[:4], "little")


class EsminiLaneKeep(Simulator):
    @staticmethod
    def simulate(list_individuals, variable_names, scenario_path, sim_time, time_step, do_visualize=False):
        out = []
        for ind in list_individuals:
            x = [float(v) for v in ind]
            Log.counter += 1; seed = _seed(Log.tag, Log.counter)
            r = runner.run(S.Params(**dict(zip(variable_names, x))), seed)
            r.update(eval=Log.counter, tag=Log.tag); Log.records.append(r)
            out.append(SimulationOutput(simTime=sim_time, times=[0.0], location={"ego": [(0, 0)]}, velocity={"ego": [(0, 0, 0)]}, speed={"ego": [x[0]]}, acceleration={"ego": [0.0]}, yaw={"ego": [0.0]}, collisions=[], actors={"ego": "ego"},
                                        otherParams={"margin": r["margin"] if r["realised"] else WORST, "peak_offset": r["peak_offset"] if r["realised"] else 0.0, "failed": r["failed"], "realised": r["realised"]}))
        return out


class FitnessLaneMargin(Fitness):
    @property
    def min_or_max(self): return "min", "max"
    @property
    def name(self): return "margin", "peak_offset"
    def eval(self, simout, **kw): return simout.otherParams["margin"], simout.otherParams["peak_offset"]


class CriticalLaneDeparture(Critical):
    def eval(self, vector_fitness, simout=None): return bool(simout.otherParams["failed"])


def problem():
    return ADASProblem(problem_name="LaneKeepSCurve", scenario_path="generated", xl=S.XL, xu=S.XU, simulation_variables=list(S.VARS), fitness_function=FitnessLaneMargin(), critical_function=CriticalLaneDeparture(),
                       simulate_function=EsminiLaneKeep.simulate, simulation_time=30, sampling_time=50, approx_eval_time=0.05, do_visualize=False)
