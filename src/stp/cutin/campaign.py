"""Campaigns of docs/GP_BOUNDARY_PLAN.md, step 3: GP-AL, Sobol and random, 10 seeds, up to 300 runs each.

  python -m stp.cutin.campaign run [arms] [seeds]     run (resumable) and write manifests
  python -m stp.cutin.campaign rerun <manifest>       rebuild a campaign from its manifest alone and compare

A campaign is a pure function of (arm, seed index, budget, settings): the design seeds, GP restarts and candidate
pools are all derived from the seed index by hashing (gp.seed_of)."""
import hashlib
import importlib.metadata as md
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
from . import gp as GP, jobs, scenario as S, runner as R, gates

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/gp_boundary"
RAW = ROOT / "results/raw/gp_boundary/campaigns"
ARMS = ("gp_al", "sobol", "random")
SEEDS = tuple(range(10))
BUDGET = 300
ESMINI_SEED = 0


def design_seed(arm, i):
    return GP.seed_of("random", i) if arm == "random" else GP.seed_of("design", i)   # Sobol and GP-AL share it


def fixed_design(arm, i, n):
    s = design_seed(arm, i)
    return GP.sobol_unit(n, s) if arm in ("sobol", "gp_al") else np.random.default_rng(s).random((n, 3))


def _run_units(U, keys, raw_file, workers, name):
    X = GP.from_unit(U)
    rows = jobs.run_points(raw_file.parent, name, [(int(k), tuple(map(float, x)), ESMINI_SEED) for k, x in zip(keys, X)], raw_file, workers)
    for k, x in zip(keys, X):
        if not np.allclose(rows[int(k)]["x"], x, rtol=0, atol=0):
            raise RuntimeError(f"{raw_file}: stored run {k} has other parameters than the design; refusing to resume")
    return rows


def run_campaign(arm, i, budget=BUDGET, raw_dir=RAW, workers=4):
    """Returns the ordered list of run rows. Resumes from raw_dir/{arm}_{i}.jsonl."""
    f = raw_dir / f"{arm}_{i}.jsonl"
    if arm != "gp_al":
        rows = _run_units(fixed_design(arm, i, budget), range(budget), f, workers, f"{arm}_{i}")
        return [rows[k] for k in range(budget)]
    n0 = GP.CFG["init"]
    rows = _run_units(fixed_design(arm, i, n0), range(n0), f, workers, f"{arm}_{i}")
    ordered = [rows[k] for k in range(n0)]
    while len(ordered) < budget:
        n = len(ordered)
        U, y = fit_data(ordered)
        B = GP.next_batch(U, y, i, n)[: budget - n]
        rows = _run_units(B, range(n, n + len(B)), f, workers, f"{arm}_{i}")
        ordered += [rows[k] for k in range(n, n + len(B))]
    return ordered


def fit_data(rows):
    ok = [r for r in rows if r["realised"]]
    return GP.to_unit([r["x"] for r in ok]), np.array([r["margin"] for r in ok])


def model_at(rows, i, n):
    U, y = fit_data(rows[:n])
    return GP.fit(U, y, GP.seed_of("gp", i, n))


def xosc_sha(x):
    return hashlib.sha256(S.xosc(S.Params(*map(float, x)), "cutin.xodr").encode()).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def environment():
    lock = dict(l.strip().split("=", 1) for l in open(ROOT / "env/esmini.lock") if "=" in l)
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "src", "env"], capture_output=True, text=True).stdout.strip())
    except OSError:
        commit, dirty = None, None
    return dict(esmini_version=lock.get("version"), esmini_zip_sha256=lock.get("sha256"), esmini_lib_sha256=sha_file(R.E.LIB),
                python=platform.python_version(), packages={p: md.version(p) for p in ("numpy", "scipy", "scikit-learn")},
                threads={k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
                code_commit=commit, code_dirty=dirty, platform=platform.platform())


def settings():
    return dict(gp=GP.CFG, dt=R.DT, ttc_rule=R.TTC_RULE, ttc_cap=R.TTC_CAP, xl=S.XL, xu=S.XU, t_lc=S.T_LC, lc_time=S.LC_TIME,
                t_end=S.T_END, acc_time_gap=S.ACC_TIME_GAP, max_decel=S.MAX_DECEL, esmini_seed=ESMINI_SEED,
                gate_tolerances=dict(pos=gates.TOL_POS, speed=gates.TOL_SPEED, gap=gates.TOL_GAP, t=gates.TOL_T, lat=gates.TOL_LAT))


def prediction_hash(rows, i, U_grid):
    mu, sd = GP.predict(model_at(rows, i, len(rows)), U_grid)
    return hashlib.sha256(mu.tobytes() + sd.tobytes()).hexdigest()


def manifest(arm, i, rows, U_grid, budget=BUDGET):
    return dict(arm=arm, seed_index=i, budget=budget, design_seed=design_seed(arm, i), settings=settings(), environment=environment(),
                runs=[dict(order=k, x=r["x"], xosc_sha256=xosc_sha(r["x"]), realised=r["realised"], margin=r["margin"]) for k, r in enumerate(rows)],
                final_prediction_sha256=prediction_hash(rows, i, U_grid))


def grid_units():
    from .reference import grid_points
    return GP.to_unit(grid_points())


def rerun(manifest_path, workers=4):
    """Rebuild the campaign from the manifest in a fresh directory, without reading any cached run, and compare."""
    m = json.loads(Path(manifest_path).read_text())
    problems = []
    if m["settings"] != json.loads(json.dumps(settings())):
        problems.append("settings differ from this code")
    env = environment()
    for k in ("esmini_lib_sha256", "esmini_zip_sha256", "packages"):
        if m["environment"][k] != env[k]: problems.append(f"environment {k}: {m['environment'][k]} != {env[k]}")
    with tempfile.TemporaryDirectory(prefix="stp_rerun_") as tmp:
        rows = run_campaign(m["arm"], m["seed_index"], m["budget"], Path(tmp), workers)
    new = manifest(m["arm"], m["seed_index"], rows, grid_units(), m["budget"])
    for a, b in zip(m["runs"], new["runs"]):
        if a != b: problems.append(f"run {a['order']} differs: {a} != {b}"); break
    if len(m["runs"]) != len(new["runs"]): problems.append("number of runs differs")
    if m["final_prediction_sha256"] != new["final_prediction_sha256"]: problems.append("final prediction differs")
    return dict(identical=not problems, problems=problems, runs=len(new["runs"]), final_prediction_sha256=new["final_prediction_sha256"])


def main(argv):
    cmd = argv[0] if argv else "run"
    if cmd == "rerun":
        res = rerun(argv[1]); print(json.dumps(res)); return 0 if res["identical"] else 1
    arms = argv[1].split(",") if len(argv) > 1 else ARMS
    seeds = [int(s) for s in argv[2].split(",")] if len(argv) > 2 else SEEDS
    Ug = grid_units()
    (OUT / "manifests").mkdir(parents=True, exist_ok=True)
    for i in seeds:
        for arm in arms:
            mf = OUT / "manifests" / f"{arm}_{i}.json"
            rows = run_campaign(arm, i)
            if not mf.exists():
                mf.write_text(json.dumps(manifest(arm, i, rows, Ug), indent=1))
            print(arm, i, "runs", len(rows), "realised", sum(r["realised"] for r in rows), "failed", sum(r["realised"] and r["margin"] < 0 for r in rows), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
