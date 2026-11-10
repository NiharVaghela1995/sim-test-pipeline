"""Resumable batches of runs. Each run has its own seed, so resuming cannot change results. Checkpoint (fsync) every 100 runs."""
import hashlib
import json
import multiprocessing as mp
import os
import time
from .. import runner, scenario as S
from .config import cfg_for

EVERY = 100


def seed_of(cfg_key, stream, rid, k):
    return int.from_bytes(hashlib.sha256(f"v2:{cfg_key}:{stream}:{rid}:{k}".encode()).digest()[:4], "little")


def one(a):
    cfg_key, params, rid, k, stream = a
    r = runner.run(S.Params(**params), seed_of(cfg_key, stream, rid, k), cfg_for(cfg_key))
    return [rid, k, bool(r["realised"]), bool(r["failed"]), r["margin"]]


def read_jsonl(f):
    out = []
    if f.exists():
        for l in open(f):
            try: out.append(json.loads(l))
            except json.JSONDecodeError: break  # partly written last line after a crash
    return out


def rewrite_clean(f, rows):
    tmp = f.with_suffix(".tmp")
    with open(tmp, "w") as o:
        for r in rows: o.write(json.dumps(r) + "\n")
    os.replace(tmp, f)


def log(out, *a):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(out / "campaign.log", "a") as f: f.write(line + "\n")


def run_jobs(out, name, jobs, f, workers=2):
    """jobs: (cfg_key, params, rid, k, stream). Results appended to f; already finished runs are skipped."""
    f.parent.mkdir(parents=True, exist_ok=True)
    rows = read_jsonl(f); rewrite_clean(f, rows)
    done = {(r[0], r[1]) for r in rows}
    todo = [j for j in jobs if (j[2], j[3]) not in done]
    log(out, name, "total", len(jobs), "done", len(done), "to run", len(todo))
    if not todo: return
    t = time.time(); n = 0
    with mp.Pool(workers, maxtasksperchild=2000) as p, open(f, "a") as o:
        for r in p.imap_unordered(one, todo, chunksize=25):
            o.write(json.dumps(r) + "\n"); n += 1
            if n % EVERY == 0:
                o.flush(); os.fsync(o.fileno())
            if n % 5000 == 0: log(out, name, n, "of", len(todo), f"{n / (time.time() - t):.1f} runs/s")
        o.flush(); os.fsync(o.fileno())
    log(out, name, "finished", n, f"{time.time() - t:.0f} s")
