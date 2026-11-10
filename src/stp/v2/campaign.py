"""Campaign v2, after the frozen gates: ground-truth set at all levels, then the search campaign at all levels. Resumable; see docs/v2/PLAN.md.
Usage: python -m stp.v2.campaign [--stages truth search] [--levels low medium high]
Exit code 3: more than 5% of a stage's runs were not realised, the plan requires a pause."""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
from .. import runner, scenario as S
from .config import CANDIDATES, LEVELS
from .gate import RAW, params, rng_for
from .jobs import EVERY, log, read_jsonl, rewrite_clean, run_jobs

ROOT = Path(__file__).resolve().parents[3]
BUDGET, SEEDS, CAP_PER_SEARCH, REPS, EXT_TO, REF, PER_STRATUM = 400, 10, 100, 20, 40, 200, 30
POOL, PAIRS, STEPS, PILOT, PER_TRUTH_STRATUM, TRUTH, RULE = 600, 200, 3, 10, 40, 200, 40


def frozen():
    g = json.load(open(ROOT / "results/v2/gate.json"))
    if not g["frozen"]: raise SystemExit("no frozen space in results/v2/gate.json")
    return g["frozen"], CANDIDATES[g["frozen"]]


def check_realised(out, name, f, accept):
    r = read_jsonl(f)
    if not r: return
    bad = 1 - sum(x[2] for x in r) / len(r)
    log(out, name, "not realised", f"{100 * bad:.2f}%")
    if bad > 0.05 and not accept:
        log(out, "PAUSE", name, "more than 5% not realised"); sys.exit(3)


def per(f):
    """rid -> {k: failed} for realised runs, in rerun order."""
    t = {}
    for rid, k, real, failed, m in read_jsonl(f):
        if real: t.setdefault(rid, {})[k] = failed
    return t


def rates(t):
    return {i: sum(v.values()) / len(v) for i, v in t.items() if len(v) >= PILOT}


# ---- ground-truth set ----
def truth_level(level, c, workers, accept):
    d = RAW / "truth" / level; d.mkdir(parents=True, exist_ok=True); X = rng_for("truth", level, "pool").uniform(c["xl"], c["xu"], (POOL, 4)); f = d / "pilot.jsonl"
    pts = {i: X[i] for i in range(POOL)}
    jobs = lambda ids: [(level, params(pts[i]), i, k, "pilot") for i in ids for k in range(PILOT)]
    run_jobs(RAW, f"truth {level} pilot", jobs(range(POOL)), f, workers)
    r = rates(per(f)); fail = [i for i in range(POOL) if r.get(i, 0) >= .5 and i in r]; ok = [i for i in range(POOL) if r.get(i, 1) < .5 and i in r]
    g = rng_for("truth", level, "pairs")
    pairs = [(int(g.choice(ok)), int(g.choice(fail))) for _ in range(PAIRS)] if fail and ok else []
    state = [(pts[a].copy(), pts[b].copy()) for a, b in pairs]
    for step in range(STEPS):
        ids = []
        for p, (a, b) in enumerate(state):
            i = POOL + p * STEPS + step; pts[i] = (a + b) / 2; ids.append(i)
        run_jobs(RAW, f"truth {level} bisect {step}", jobs(ids), f, workers)
        r = rates(per(f))
        for p, i in enumerate(ids):
            a, b = state[p]
            if r.get(i, 0) >= .5: state[p] = (a, pts[i])
            else: state[p] = (pts[i], b)
    check_realised(RAW, f"truth {level} pilot", f, accept)
    r = rates(per(f)); B = {"0": [], "low": [], "mid": [], "high": [], "1": []}
    for i, v in r.items():
        q = round(v * PILOT); B["0" if q == 0 else "low" if q <= 3 else "mid" if q <= 6 else "high" if q <= 9 else "1"].append(i)
    g = rng_for("truth", level, "strata")
    pick = {k: sorted(int(i) for i in g.choice(sorted(v), min(len(v), PER_TRUTH_STRATUM), replace=False)) if v else [] for k, v in B.items()}
    json.dump(dict(pool_sizes={k: len(v) for k, v in B.items()}, picked=pick, points={str(i): params(pts[i]) for v in pick.values() for i in v}, source={str(i): ("random" if i < POOL else "bisect") for v in pick.values() for i in v}), open(d / "set.json", "w"))
    log(RAW, "truth", level, "pool", {k: len(v) for k, v in B.items()}, "picked", {k: len(v) for k, v in pick.items()})
    ids = [i for v in pick.values() for i in v]
    for name, n, stream in (("truth", TRUTH, "truth"), ("rule", RULE, "rule")):
        run_jobs(RAW, f"truth {level} {name}", [(level, params(pts[i]), i, k, stream) for i in ids for k in range(n)], d / f"{name}.jsonl", workers)
        check_realised(RAW, f"truth {level} {name}", d / f"{name}.jsonl", accept)


# ---- search campaign ----
def search(level, arm, seed, c, d):
    """Runs in its own process: importing both algorithms breaks NSGA-II (see v1)."""
    from opensbt.experiment.search_configuration import DefaultSearchConfiguration
    from opensbt.problem.adas_problem import ADASProblem
    if arm == "nsga2":
        from opensbt.algorithm.nsga2_optimizer import NsgaIIOptimizer as Opt
    else:
        from opensbt.algorithm.ps_rand import PureSamplingRand as Opt
    from .. import opensbt_bridge as B
    f = Path(d) / f"eval_{arm}_{seed}.jsonl"
    cached = read_jsonl(f); cached = cached[: len(cached) - len(cached) % EVERY] if len(cached) < BUDGET else cached
    rewrite_clean(f, cached)
    B.Log.records = []; B.Log.tag = f"v2-{level}-{arm}-{seed}"; B.Log.counter = 0; B.Log.cfg = LEVELS[level]; B.Log.cached = cached; B.Log.sink = open(f, "a"); B.Log.every = EVERY
    cfg = DefaultSearchConfiguration(); cfg.seed = seed
    np.random.seed(seed); random.seed(seed)
    prob = ADASProblem(problem_name="LaneKeepSCurveV2", scenario_path="generated", xl=c["xl"], xu=c["xu"], simulation_variables=list(S.VARS), fitness_function=B.FitnessLaneMargin(), critical_function=B.CriticalLaneDeparture(), simulate_function=B.EsminiLaneKeep.simulate, simulation_time=30, sampling_time=50, approx_eval_time=0.05, do_visualize=False)
    if arm == "nsga2":
        cfg.population_size = 40; cfg.num_offsprings = 40; cfg.n_generations = (BUDGET - 40) // 40 + 1; cfg.prob_mutation = 1 / len(S.VARS)
    else:
        cfg.population_size = BUDGET
    Opt(prob, cfg).run()
    B.Log.sink.flush(); os.fsync(B.Log.sink.fileno()); B.Log.sink.close()
    return len(B.Log.records)


def search_level(level, c, workers, accept):
    d = RAW / "search" / level; d.mkdir(parents=True, exist_ok=True); ctx = mp.get_context("spawn")
    for s in range(SEEDS):
        for arm in ("nsga2", "random"):
            if len(read_jsonl(d / f"eval_{arm}_{s}.jsonl")) >= BUDGET: continue
            t = time.time()
            with ctx.Pool(1) as p: n = p.apply(search, (level, arm, s, c, str(d)))
            log(RAW, "search", level, arm, s, "evaluations", n, f"{time.time() - t:.0f} s")
    fails = []
    for s in range(SEEDS):
        for arm in ("nsga2", "random"):
            rows = read_jsonl(d / f"eval_{arm}_{s}.jsonl")[:BUDGET]; ix = [i for i, r in enumerate(rows) if r["failed"]]
            pick = set(int(i) for i in rng_for("cap", level, arm, s).choice(ix, min(len(ix), CAP_PER_SEARCH), replace=False)) if ix else set()
            for i in ix:
                if i in pick: fails.append(dict(failure=len(fails), arm=arm, search_seed=s, eval=i, params=rows[i]["params"], report_margin=rows[i]["margin"], reported_in_seed=len(ix), sampled_in_seed=len(pick)))
    rewrite_clean(d / "failures.jsonl", fails); log(RAW, "search", level, "failures sampled for replication", len(fails))
    run_jobs(RAW, f"search {level} replication", [(level, x["params"], x["failure"], k, "rep") for x in fails for k in range(REPS)], d / "reps.jsonl", workers)
    check_realised(RAW, f"search {level} replication", d / "reps.jsonl", accept)
    t = per(d / "reps.jsonl"); strata = {"never": [], "partly": [], "always": []}
    for x in fails:
        v = t.get(x["failure"], {}); k = sum(v.values()); strata["never" if k == 0 else "always" if k == len(v) else "partly"].append(x["failure"])
    g = rng_for("reference", level)
    pick = {k: sorted(int(i) for i in g.choice(v, min(len(v), PER_STRATUM), replace=False)) if v else [] for k, v in strata.items()}
    json.dump(dict(sizes={k: len(v) for k, v in strata.items()}, picked=pick), open(d / "strata.json", "w"))
    by = {x["failure"]: x for x in fails}; ids = [i for v in pick.values() for i in v]
    run_jobs(RAW, f"search {level} reference", [(level, by[i]["params"], i, k, "ref") for i in ids for k in range(REF)], d / "reference.jsonl", workers)
    run_jobs(RAW, f"search {level} extension", [(level, by[i]["params"], i, k, "rep") for i in ids for k in range(REPS, EXT_TO)], d / "reps_ext.jsonl", workers)
    check_realised(RAW, f"search {level} reference", d / "reference.jsonl", accept)
    log(RAW, "search", level, "complete", {k: len(v) for k, v in strata.items()})


def manifest(name, c):
    g = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()
    return dict(code_commit=g("rev-parse", "HEAD"), code_dirty=bool(g("status", "--porcelain", "src")), python=platform.python_version(), platform=platform.platform(), cpus=mp.cpu_count(), dt=runner.DT, frozen=name, space=c, esmini_lock=(ROOT / "env/esmini.lock").read_text(), opensbt_lock=(ROOT / "env/opensbt.lock").read_text(), requirements_sha256=hashlib.sha256((ROOT / "env/requirements.lock").read_bytes()).hexdigest())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stages", nargs="+", default=["truth", "search"]); ap.add_argument("--levels", nargs="+", default=["low", "medium", "high"]); ap.add_argument("--workers", type=int, default=2); ap.add_argument("--accept-realisation", action="store_true")
    a = ap.parse_args(); name, c = frozen(); m = RAW / "manifest.json"
    if not m.exists(): json.dump(manifest(name, c), open(m, "w"), indent=1)
    log(RAW, "start", vars(a), name)
    if "truth" in a.stages:
        for l in a.levels: truth_level(l, c, a.workers, a.accept_realisation)
    if "search" in a.stages:
        for l in a.levels: search_level(l, c, a.workers, a.accept_realisation)
    log(RAW, "ALL_DONE")


if __name__ == "__main__":
    main()
