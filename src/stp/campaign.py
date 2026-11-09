"""Resumable campaign: search and random baseline, replication of every reported failure, and reference runs, at three noise levels.
Checkpoints every 100 runs. Re-running the command continues from the last checkpoint.
Usage: python -m stp.campaign [--levels low medium high] [--seeds 10] [--budget 400] [--reps 20] [--ref 200] [--ref-per-stratum 100]"""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
import platform
import random
import subprocess
import time
from pathlib import Path
import numpy as np
from . import runner, scenario as S
from .sut import LEVELS

ROOT = Path(__file__).resolve().parents[2]
EVERY = 100


def log(out, *a):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(out / "campaign.log", "a") as f: f.write(line + "\n")


def manifest():
    g = lambda *c: subprocess.run(["git", "-C", str(ROOT), *c], capture_output=True, text=True).stdout.strip()
    z = ROOT / "third_party/esmini_dl/esmini-bin_Linux.zip"
    return dict(code_commit=g("rev-parse", "HEAD"), code_dirty=bool(g("status", "--porcelain", "src")), python=platform.python_version(), platform=platform.platform(), cpus=mp.cpu_count(), esmini_lock=(ROOT / "env/esmini.lock").read_text(), opensbt_lock=(ROOT / "env/opensbt.lock").read_text(),
                requirements_sha256=hashlib.sha256((ROOT / "env/requirements.lock").read_bytes()).hexdigest(), esmini_zip_sha256=hashlib.sha256(z.read_bytes()).hexdigest() if z.exists() else None, dt=runner.DT, ranges=dict(xl=S.XL, xu=S.XU))


def read_jsonl(f):
    out = []
    if f.exists():
        for l in open(f):
            try: out.append(json.loads(l))
            except json.JSONDecodeError: break  # a partly written last line after a crash
    return out


def rewrite_clean(f, rows):
    tmp = f.with_suffix(".tmp")
    with open(tmp, "w") as o:
        for r in rows: o.write(json.dumps(r) + "\n")
    os.replace(tmp, f)


def search(level, arm, seed, budget, d):
    """Runs in its own process. Importing both algorithms changes pymoo's patched classes and breaks NSGA-II, so only the one in use is imported."""
    from opensbt.experiment.search_configuration import DefaultSearchConfiguration
    if arm == "nsga2":
        from opensbt.algorithm.nsga2_optimizer import NsgaIIOptimizer
    else:
        from opensbt.algorithm.ps_rand import PureSamplingRand
    from . import opensbt_bridge as B
    f = Path(d) / f"eval_{arm}_{seed}.jsonl"
    cached = read_jsonl(f); cached = cached[: len(cached) - len(cached) % EVERY] if len(cached) < budget else cached
    rewrite_clean(f, cached)
    B.Log.records = []; B.Log.tag = f"{level}-{arm}-{seed}"; B.Log.counter = 0; B.Log.cfg = LEVELS[level]; B.Log.cached = cached; B.Log.sink = open(f, "a"); B.Log.every = EVERY
    cfg = DefaultSearchConfiguration(); cfg.seed = seed
    np.random.seed(seed); random.seed(seed)
    if arm == "nsga2":
        cfg.population_size = 40; cfg.num_offsprings = 40; cfg.n_generations = (budget - 40) // 40 + 1; cfg.prob_mutation = 1 / len(S.VARS)
        NsgaIIOptimizer(B.problem(), cfg).run()
    else:
        cfg.population_size = budget
        PureSamplingRand(B.problem(), cfg).run()
    B.Log.sink.flush(); os.fsync(B.Log.sink.fileno()); B.Log.sink.close()
    return len(B.Log.records)


def one(a):
    level, params, fid, k, stream = a
    seed = int.from_bytes(hashlib.sha256(f"{level}:{stream}:{fid}:{k}".encode()).digest()[:4], "little")
    r = runner.run(S.Params(**params), seed, LEVELS[level])
    return [fid, k, bool(r["realised"]), bool(r["failed"]), r["margin"]]


def run_jobs(out, level, name, jobs, f, workers):
    done = {(r[0], r[1]) for r in read_jsonl(f)}
    rewrite_clean(f, read_jsonl(f))
    todo = [j for j in jobs if (j[2], j[3]) not in done]
    log(out, level, name, "total", len(jobs), "already done", len(done), "to run", len(todo))
    if not todo: return
    t = time.time(); n = 0
    with mp.Pool(workers, maxtasksperchild=2000) as p, open(f, "a") as o:
        for r in p.imap_unordered(one, todo, chunksize=25):
            o.write(json.dumps(r) + "\n"); n += 1
            if n % EVERY == 0:
                o.flush(); os.fsync(o.fileno())
            if n % 5000 == 0: log(out, level, name, n, "of", len(todo), f"{n / (time.time() - t):.1f} runs/s")
        o.flush(); os.fsync(o.fileno())
    log(out, level, name, "finished", n, f"{time.time() - t:.0f} s")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--levels", nargs="+", default=["low", "medium", "high"]); ap.add_argument("--seeds", type=int, default=10); ap.add_argument("--budget", type=int, default=400); ap.add_argument("--reps", type=int, default=20); ap.add_argument("--ref", type=int, default=200); ap.add_argument("--ref-per-stratum", type=int, default=100); ap.add_argument("--workers", type=int, default=2); ap.add_argument("--out", default="results/raw/campaign_v1")
    a = ap.parse_args(); out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True); log(out, "start", vars(a))
    if not (out / "manifest.json").exists(): json.dump(dict(manifest(), args=vars(a)), open(out / "manifest.json", "w"), indent=1)
    ctx = mp.get_context("spawn")
    for level in a.levels:
        d = out / level; d.mkdir(exist_ok=True)
        for s in range(a.seeds):
            for arm in ("nsga2", "random"):
                if len(read_jsonl(d / f"eval_{arm}_{s}.jsonl")) >= a.budget: continue
                t = time.time()
                with ctx.Pool(1) as p: n = p.apply(search, (level, arm, s, a.budget, str(d)))
                log(out, level, arm, s, "evaluations", n, f"{time.time() - t:.0f} s")
        fails = []
        for s in range(a.seeds):
            for arm in ("nsga2", "random"):
                for r in read_jsonl(d / f"eval_{arm}_{s}.jsonl")[:a.budget]:
                    if r["failed"]: fails.append(dict(failure=len(fails), arm=arm, search_seed=s, params=r["params"], report_margin=r["margin"]))
        rewrite_clean(d / "failures.jsonl", fails); log(out, level, "reported failures", len(fails))
        run_jobs(out, level, "replication", [(level, x["params"], x["failure"], k, "rep") for x in fails for k in range(a.reps)], d / "reps.jsonl", a.workers)
        per = {}
        for fid, k, realised, failed, m in read_jsonl(d / "reps.jsonl"):
            c = per.setdefault(fid, [0, 0]); c[0] += realised; c[1] += failed
        strata = {"never": [], "flaky": [], "always": []}
        for x in fails:
            n, f = per.get(x["failure"], (0, 0)); strata["never" if f == 0 else "always" if f == n else "flaky"].append(x["failure"])
        rng = np.random.default_rng(20261110); pick = {k: sorted(int(i) for i in rng.choice(v, min(len(v), a.ref_per_stratum), replace=False)) if v else [] for k, v in strata.items()}
        json.dump(dict(sizes={k: len(v) for k, v in strata.items()}, picked=pick), open(d / "strata.json", "w"))
        by = {x["failure"]: x for x in fails}
        run_jobs(out, level, "reference", [(level, by[i]["params"], i, k, "ref") for v in pick.values() for i in v for k in range(a.ref)], d / "reference.jsonl", a.workers)
        log(out, level, "complete", {k: len(v) for k, v in strata.items()})
    log(out, "ALL_DONE")


if __name__ == "__main__":
    main()
