"""Search (NSGA-II) and random baseline at equal budget, then replicate every reported failure. Usage: python -m stp.campaign [--seeds N] [--budget B] [--reps R]"""
import argparse
import hashlib
import json
import multiprocessing as mp
import platform
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
from . import runner, scenario as S

ROOT = Path(__file__).resolve().parents[2]


def manifest():
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "uncommitted"
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "src"], capture_output=True, text=True).stdout.strip())
    lib = (ROOT / "third_party/esmini_dl/esmini-bin_Linux.zip")
    return dict(code_commit=git, code_dirty=dirty, python=platform.python_version(), platform=platform.platform(), cpus=mp.cpu_count(), esmini_lock=(ROOT / "env/esmini.lock").read_text(), opensbt_lock=(ROOT / "env/opensbt.lock").read_text(),
                requirements_sha256=hashlib.sha256((ROOT / "env/requirements.lock").read_bytes()).hexdigest(), esmini_zip_sha256=hashlib.sha256(lib.read_bytes()).hexdigest() if lib.exists() else None, dt=runner.DT)


def search(arm, seed, budget):
    import pymoo
    from opensbt.experiment.search_configuration import DefaultSearchConfiguration
    # Import only the algorithm in use: importing both changes pymoo's patched classes and breaks NSGA-II (each search runs in its own process).
    if arm == "nsga2":
        from opensbt.algorithm.nsga2_optimizer import NsgaIIOptimizer
    else:
        from opensbt.algorithm.ps_rand import PureSamplingRand
    from . import opensbt_bridge as B
    B.Log.records = []; B.Log.tag = f"{arm}-{seed}"; B.Log.counter = 0
    cfg = DefaultSearchConfiguration(); cfg.seed = seed
    np.random.seed(seed); import random; random.seed(seed)
    if arm == "nsga2":
        cfg.population_size = 40; cfg.num_offsprings = 40; cfg.n_generations = (budget - 40) // 40 + 1
        cfg.prob_mutation = 1 / len(S.VARS)
        NsgaIIOptimizer(B.problem(), cfg).run()
    else:
        cfg.population_size = budget
        PureSamplingRand(B.problem(), cfg).run()
    return B.Log.records[:budget]


def _replicate(a):
    params, fid, k, tag = a
    seed = int.from_bytes(hashlib.sha256(f"{tag}:{fid}:{k}".encode()).digest()[:4], "little")
    r = runner.run(S.Params(**params), seed)
    return fid, k, r["realised"], r["failed"], r["margin"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--seeds", type=int, default=5); ap.add_argument("--budget", type=int, default=400); ap.add_argument("--reps", type=int, default=20); ap.add_argument("--workers", type=int, default=2); ap.add_argument("--out", default="results/raw/campaign")
    a = ap.parse_args()
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True); t0 = time.time()
    json.dump(dict(manifest(), args=vars(a)), open(out / "manifest.json", "w"), indent=1)
    rec = []
    for s in range(a.seeds):
        for arm in ("nsga2", "random"):
            with mp.get_context("spawn").Pool(1) as p1:
                r = p1.apply(search, (arm, s, a.budget))
            for x in r: x.update(arm=arm, search_seed=s)
            rec += r; print(arm, s, len(r), sum(x["failed"] for x in r), sum(not x["realised"] for x in r), round(time.time() - t0), flush=True)
    with open(out / "evaluations.jsonl", "w") as f:
        for r in rec: f.write(json.dumps(r) + "\n")
    fails = [r for r in rec if r["failed"]]
    jobs = [(r["params"], i, k, "rep") for i, r in enumerate(fails) for k in range(a.reps)]
    print("reported failures", len(fails), "replication runs", len(jobs), flush=True)
    res = [[None] * a.reps for _ in fails]; invalid = 0
    with mp.Pool(a.workers) as p:
        for fid, k, realised, failed, margin in p.imap_unordered(_replicate, jobs, chunksize=50):
            res[fid][k] = (bool(realised), bool(failed), margin); invalid += not realised
    with open(out / "replications.jsonl", "w") as f:
        for i, r in enumerate(fails): f.write(json.dumps(dict(failure=i, arm=r["arm"], search_seed=r["search_seed"], params=r["params"], report_margin=r["margin"], reps=res[i])) + "\n")
    print("done", len(fails), "not realised in replication", invalid, round(time.time() - t0), "s", flush=True)


if __name__ == "__main__":
    main()
