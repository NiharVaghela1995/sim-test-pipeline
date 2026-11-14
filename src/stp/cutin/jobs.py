"""Resumable parallel batches of cut-in runs. Results are appended as JSON lines keyed by an index and fsynced every
100 runs (the v2 checkpoint helpers), so an interrupted batch resumes where it stopped without changing any result."""
import json
import multiprocessing as mp
import os
import time
from ..v2.jobs import read_jsonl, rewrite_clean, log, EVERY
from . import runner as R, scenario as S


def record(r):
    """Compact run record kept on disk."""
    return dict(realised=r["realised"], margin=r["margin"], min_ttc=r["min_ttc"], collided=r["collided"], overbrake=r["overbrake"],
                gap_at_cut=r["gap_at_cut"], bad=[k for k, v in r["gates"].items() if not v])


def _one(a):
    key, x, seed = a
    return dict(key=key, x=list(x), seed=seed, **record(R.run(S.Params(*map(float, x)), seed)))


def run_points(out, name, items, f, workers=4):
    """items: list of (key, (ego_speed, gap, rel_speed), esmini seed). Returns {key: row} for all items."""
    f.parent.mkdir(parents=True, exist_ok=True)
    rows = read_jsonl(f); rewrite_clean(f, rows)
    done = {r["key"] for r in rows}
    todo = [it for it in items if it[0] not in done]
    if todo:
        log(out, name, "total", len(items), "done", len(done), "to run", len(todo))
        t = time.time(); n = 0
        with mp.Pool(workers, maxtasksperchild=5000) as p, open(f, "a") as o:
            for r in p.imap_unordered(_one, todo, chunksize=50):
                o.write(json.dumps(r) + "\n"); n += 1; rows.append(r)
                if n % EVERY == 0:
                    o.flush(); os.fsync(o.fileno())
                if n % 10000 == 0: log(out, name, n, "of", len(todo), f"{n / (time.time() - t):.1f} runs/s")
            o.flush(); os.fsync(o.fileno())
        log(out, name, "finished", n, f"{time.time() - t:.0f} s")
    want = {it[0] for it in items}
    return {r["key"]: r for r in rows if r["key"] in want}
