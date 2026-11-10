"""Writes the five stage notebooks. Usage: python notebooks/build.py [--execute]"""
import sys
from pathlib import Path
import nbformat as nbf

HERE = Path(__file__).resolve().parent
SITE = "https://niharvaghela1995.github.io/masters-thesis/assessments"
SETUP = '''import json, sys, tempfile, time
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
ROOT = Path.cwd().resolve()
ROOT = ROOT if (ROOT / "src").exists() else ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
from stp import runner, scenario as S
from stp.v2.config import CANDIDATES, LEVELS, cfg_for
from stp.v2 import rules as RL
SPACE = CANDIDATES["A"]
SUMMARY = json.load(open(ROOT / "results/v2/summary.json"))
plt.rcParams.update({"figure.dpi": 90, "axes.spines.top": False, "axes.spines.right": False, "font.size": 11})
BLUE, ORANGE = "#2a78d6", "#eb6834"
def along(speeds, k1=0.012, k2=-0.004, gust=0.8):
    return [S.Params(float(v), k1, k2, gust) for v in speeds]
def reruns(p, n, level="medium", base=0):
    return [runner.run(p, base + i, LEVELS[level]) for i in range(n)]
'''

def head(title, intro, links):
    li = "\n".join(f"- [{t}]({SITE}/{a}.html)" for t, a in links)
    return ("md", f"# {title}\n\n{intro}\n\nThe live cells are small and take a few minutes on a laptop CPU. Campaign-scale numbers are read from `results/v2/summary.json`. Everything here measures injected noise in one simple simulator setup, so none of it says anything about a real vehicle.\n\n**Matching assessment**\n\n{li}")

NB = {}

NB["01_search"] = [
head("Search", "Directed search against random sampling on the frozen v2 scenario space.", [("Search and sampling strategy", "s02_search_strategy"), ("Coverage, diversity and stopping", "s08_coverage_stopping")]),
("code", SETUP),
("md", "## S02-P01: does directed search beat random sampling?\n\nThis reruns one real seed of each arm with the campaign's own code: 400 evaluations, medium noise, seed 0."),
("code", '''import multiprocessing as mp
from stp.v2.campaign import search
tmp = Path(tempfile.mkdtemp())
t = time.time()
ctx = mp.get_context("spawn")
with ctx.Pool(1) as p:
    n_nsga = p.apply(search, ("medium", "nsga2", 0, SPACE, str(tmp)))
with ctx.Pool(1) as p:
    n_rand = p.apply(search, ("medium", "random", 0, SPACE, str(tmp)))
print(f"{time.time() - t:.0f} s")
rows = {a: [json.loads(l) for l in open(tmp / f"eval_{a}_0.jsonl")] for a in ("nsga2", "random")}
saved = SUMMARY["medium"]["search"]["per_seed"]
for a in rows:
    print(a, "failures in this rerun:", sum(r["failed"] for r in rows[a]), "| saved campaign value for seed 0:", saved[a][0]["reported"])'''),
("md", "The saved campaign, over 10 seeds per noise level:"),
("code", '''fig, axs = plt.subplots(1, 3, figsize=(10, 3.2), sharey=True)
for ax, l in zip(axs, ("low", "medium", "high")):
    P = SUMMARY[l]["search"]["per_seed"]
    ax.boxplot([[r["confirmed"] for r in P["nsga2"]], [r["confirmed"] for r in P["random"]]], labels=["NSGA-II", "Random"])
    ax.set_title(f"{l} noise", loc="left")
axs[0].set_ylabel("Failures reproducing in at least half of reruns")
plt.tight_layout(); plt.show()
for l in ("low", "medium", "high"):
    print(l, {k: (round(v["nsga2_median"], 1), round(v["random_median"], 1), "A12", v["A12"]) for k, v in SUMMARY[l]["search"]["search_vs_random"].items()})'''),
("md", "## S02-P03: the same scenario gives different objective values\n\nSpeed is swept along a line through the controller's limit, with 20 fresh-seed reruns at each point. Search sees one of these noisy values."),
("code", '''speeds = np.linspace(18, 25, 8)
data = [reruns(p, 20) for p in along(speeds)]
m = np.array([[r["margin"] for r in d] for d in data])
plt.figure(figsize=(6, 3.2))
for s, v in zip(speeds, m): plt.scatter([s] * len(v), v, s=12, color=BLUE, alpha=.5)
plt.axhline(0, color="k", lw=1); plt.xlabel("Speed, m/s"); plt.ylabel("Safety margin, m"); plt.show()
print("sd of margin at each speed:", np.round(m.std(axis=1), 3))'''),
("md", "## S08-P02: many failures, narrow coverage\n\nThe failed evaluations from the two live runs above are binned into input cells, 5 bins per input."),
("code", '''def cells(rs):
    out = set()
    for r in rs:
        if r["failed"]:
            out.add(tuple(min(4, int(5 * (r["params"][v] - lo) / (hi - lo))) for v, lo, hi in zip(S.VARS, SPACE["xl"], SPACE["xu"])))
    return len(out)
print({a: (sum(r["failed"] for r in rows[a]), cells(rows[a])) for a in rows}, "(failures, distinct cells) in this rerun")
print({l: {a: int(np.median([r["cells"] for r in SUMMARY[l]["search"]["per_seed"][a]])) for a in ("nsga2", "random")} for l in ("low", "medium", "high")}, "median cells with a confirmed failure, saved campaign")'''),
]

NB["02_execution_realisation"] = [
head("Execution and realisation", "Did the simulator run what was specified, is a run repeatable, and is the environment recorded?", [("Execution and realisation", "s05_execution_realisation")]),
("code", SETUP),
("md", "## S05-P01: a run may not realise the intended scenario\n\nEach seeded defect executes something other than the specification. The realisation check must say so, and the run then gets no verdict."),
("code", '''CLEAN = S.Params(15.0, 0.01, -0.01, 0.0)
print("clean run gates:", runner.run(CLEAN, 1)["gates"])
defects = {"mirrored road": S.Params(15.0, -0.01, -0.01, 0.0), "wrong second arc": S.Params(15.0, 0.01, 0.03, 0.0), "speed not applied": S.Params(20.0, 0.01, -0.01, 0.0)}
for name, executed in defects.items():
    r = runner.run(executed, 1, spec=CLEAN)
    print(f"{name:20s} realised={r['realised']} failed gates={[g for g, ok in r['gates'].items() if not ok]}")
r = runner.run(CLEAN, 1, external=False)
print(f"{'controller not in loop':20s} realised={r['realised']} failed gates={[g for g, ok in r['gates'].items() if not ok]}")'''),
("md", "## S05-P02: identical inputs, identical runs?\n\nHere the simulator is deterministic given the seed, so all run-to-run variation is the injected randomness. On a real stack this separation is not available."),
("code", '''p = S.Params(20.0, 0.014, -0.004, 0.8)
same = [runner.run(p, 7, LEVELS["medium"])["margin"] for _ in range(5)]
other = [r["margin"] for r in reruns(p, 30, "medium", 100)]
print("same seed, five runs:", set(np.round(same, 9)))
print(f"fresh seeds: mean margin {np.mean(other):.3f}, sd {np.std(other):.3f}, failed {np.mean([m < 0 for m in other]):.2f}")'''),
("md", "## S04-P05: latency as a hidden cause of failure\n\nThe first campaign's failures were decided by the latency drawn for each run. The live sweep repeats the check with gust 0, so latency acts alone, on low-demand scenarios."),
("code", '''g = np.random.default_rng(5); X = g.uniform(SPACE["xl"], SPACE["xu"], (4000, 4)); X = X[X[:, 0] ** 2 * np.maximum(X[:, 1], np.abs(X[:, 2])) <= 3][:20]; X[:, 3] = 0
sw = {}
for steps in (5, 10, 15, 20, 23):
    c = cfg_for(f"high@{steps}"); sw[steps * 20] = np.mean([runner.run(S.Params(*map(float, x)), i, c)["failed"] for i, x in enumerate(X)])
print("failed share by latency, ms (live, 20 scenarios):", sw)
A = SUMMARY["gate"]["candidates"]["A"]["G0_amended"]
print("saved gate, failures of 100:", {l: {ms: x["failed"] for ms, x in v.items()} for l, v in A.items()})
D = json.load(open(ROOT / "results/diagnostics.json"))["high"]["by_latency"]
x = sorted(map(int, D)); plt.figure(figsize=(6, 3)); plt.plot([k * 20 for k in x], [100 * D[str(k)]["fail_rate"] for k in x], "o-", color=BLUE); plt.xlabel("Latency drawn, ms (first campaign, high noise)"); plt.ylabel("Runs that failed, %"); plt.show()'''),
("md", "## S05-P05: harness faults must not corrupt a campaign\n\nBatches checkpoint their results and a restart runs only what is missing. This simulates a crash with a half-written last line."),
("code", '''from stp.v2.jobs import read_jsonl, run_jobs
d = Path(tempfile.mkdtemp()); f = d / "demo.jsonl"
jobs = [("medium", S.Params(15.0, 0.01, -0.01, 0.2).dict(), i, 0, "demo") for i in range(40)]
run_jobs(d, "first", jobs[:25], f, workers=2)
with open(f, "a") as o: o.write('[99, 0, tr')
run_jobs(d, "resume", jobs, f, workers=2)
rows = read_jsonl(f); print("rows:", len(rows), "unique ids:", len({r[0] for r in rows}))'''),
("md", "## S05-P06: is the environment recorded?\n\nEach campaign saves its code commit, versions and hashes."),
("code", '''P = SUMMARY["provenance"]; print({k: P[k] for k in ("code_commit", "code_dirty", "python", "dt", "frozen")})
print((ROOT / "env/esmini.lock").read_text()); print((ROOT / "env/opensbt.lock").read_text())'''),
]

NB["03_oracle"] = [
head("Oracle and objective", "What a verdict and a safety margin do and do not tell a search.", [("Oracle and objective", "s06_oracle_objective"), ("Tail-risk gap", "s06b_tail_risk_gap")]),
("code", SETUP),
("md", "## S06-P05: binary outcomes are hard to search\n\nThe pass or fail verdict is flat almost everywhere. The margin it is derived from has a slope a search can follow."),
("code", '''speeds = np.linspace(10, 26, 17)
rs = [runner.run(p, 1, LEVELS["low"]) for p in along(speeds)]
fig, ax = plt.subplots(1, 2, figsize=(9, 3))
ax[0].plot(speeds, [r["margin"] for r in rs], "o-", color=BLUE); ax[0].axhline(0, color="k", lw=1); ax[0].set_xlabel("Speed, m/s"); ax[0].set_ylabel("Safety margin, m")
ax[1].step(speeds, [int(r["failed"]) for r in rs], color=ORANGE, where="mid"); ax[1].set_xlabel("Speed, m/s"); ax[1].set_ylabel("Failed"); plt.tight_layout(); plt.show()'''),
("md", "## S06-P02: a threshold decides which scenarios count\n\nA failure is a margin below 0. Moving that threshold changes the failure set, and the overlap below measures how much."),
("code", '''g = np.random.default_rng(3); X = g.uniform(SPACE["xl"], SPACE["xu"], (400, 4))
t = time.time(); m = np.array([runner.run(S.Params(*map(float, x)), i, LEVELS["medium"])["margin"] for i, x in enumerate(X)]); print(f"{time.time() - t:.0f} s")
base = m < 0
for th in (-0.2, -0.1, 0.0, 0.1, 0.2):
    s = m < th; print(f"margin < {th:+.1f}: {s.mean():.3f} of runs, overlap with margin < 0: {(s & base).sum() / max((s | base).sum(), 1):.2f}")'''),
("md", "## S06-P01: does the objective change which scenarios look worst?\n\nA first look at G2: 15 scenarios near the limit, 20 reruns each, ranked by the mean margin, the worst run, and the mean of the worst 4 runs (a tail measure at α = 0.8). This is a small demonstration, not a G2 result."),
("code", '''from scipy.stats import spearmanr
g = np.random.default_rng(11); Y = g.uniform([14, .008, -.02, .3], [24, .018, .02, 1.0], (15, 4))
M = np.array([[r["margin"] for r in reruns(S.Params(*map(float, y)), 20, "high", 500)] for y in Y])
mean, worst, cvar = M.mean(1), M.min(1), np.sort(M, axis=1)[:, :4].mean(1)
print("rank correlation with the mean: worst run %.2f, tail mean %.2f" % (spearmanr(mean, worst)[0], spearmanr(mean, cvar)[0]))
print("worst scenario by mean:", int(mean.argmin()), "by worst run:", int(worst.argmin()), "by tail mean:", int(cvar.argmin()))'''),
]

NB["04_failure_validation"] = [
head("Failure validation", "How often reported failures reproduce, and which rule should call them real.", [("Failure validation", "s07_failure_validation")]),
("code", SETUP),
("md", "## S07-P01: flakiness-aware validation\n\nReported failures against the base rate, from the saved campaign. A reported failure that reproduces no more often than a random run fails carries no information about its scenario."),
("code", '''for l in ("low", "medium", "high"):
    s = SUMMARY[l]["search"]; print(l, "base rate %.3f, mean reproduction %.3f, partly reproducing %.3f, dispersion %.1f" % (s["base_rate"]["est"], s["rate_all"]["est"], s["shares"]["partly"], s["heterogeneity"]["dispersion"]))
V1 = json.load(open(ROOT / "results/diagnostics.json"))
print("first campaign dispersion:", {l: round(V1[l]["heterogeneity"]["dispersion"], 2) for l in ("medium", "high")})'''),
("md", "## S07-P02: replication budgets and noise-aware verdicts\n\nFirst the exact behaviour of each rule, which needs no simulation."),
("code", '''g = np.linspace(0, 1, 101); plt.figure(figsize=(7, 3.6))
for r in RL.shortlist(.5):
    if r.name in ("any-of-3", "all-of-3", "majority-of-9", "SPRT 0.2/0.8, a=b=0.05", "SPRT 0.3/0.7, a=b=0.01"):
        plt.plot(g, [100 * r.exact(float(q))[0] for q in g], label=r.name)
plt.axvline(.5, color="k", lw=.8, ls=":"); plt.xlabel("True failure probability"); plt.ylabel("Chance of 'real', %"); plt.legend(frameon=False, fontsize=9); plt.show()
for r in RL.shortlist(.5):
    if r.name.startswith("SPRT"): print(r.name, "chance of real at p = 0.2, 0.3, 0.4, 0.6, 0.7, 0.8:", [round(r.exact(q)[0], 3) for q in (.2, .3, .4, .6, .7, .8)], "reruns at 0.5:", round(r.exact(.5)[1], 1))'''),
("md", "A miniature of the campaign's scoring: 8 scenarios on a line through the limit, 100 truth reruns and, on separate seeds, 40 rule reruns each."),
("code", '''t = time.time(); rows = []
for p in along(np.linspace(19, 24, 8)):
    truth = np.mean([r["failed"] for r in reruns(p, 100, "high", 10000)])
    seq = np.array([r["failed"] for r in reruns(p, 40, "high", 20000)], bool); rows.append((p.speed, truth, seq))
print(f"{time.time() - t:.0f} s")
names = ("any-of-3", "all-of-3", "majority-of-9", "SPRT 0.2/0.8, a=b=0.05")
R = {r.name: r for r in RL.shortlist(.5)}
print("speed  truth  " + "  ".join(names))
for v, q, s in rows: print(f"{v:5.1f}  {q:.2f}   " + "  ".join(("real" if R[n].apply(s)[0] else "no  ") + f"({R[n].apply(s)[1]})" for n in names))'''),
("md", "The saved scores, on the full ground-truth set: errors on scenarios at least 0.1 from the 0.5 threshold."),
("code", '''show = ("any-of-3", "all-of-3", "majority-of-9", "SPRT 0.2/0.8, a=b=0.05", "SPRT 0.3/0.7, a=b=0.01")
for l in ("low", "medium", "high"):
    Q = SUMMARY[l]["truth"]["scores"]["0.5"]
    print(l, "| planned pick:", Q["recommended"]["rule"], "| exact-score pick:", Q["recommended_exact"]["rule"])
    for n in show:
        d = Q["rules"][n]["decidable"]; print(f"   {n:26s} false real {100 * d['false_real']['est']:5.1f}%  missed {100 * d['missed']['est']:5.1f}%  reruns {Q['rules'][n]['all']['reruns']['est']:.1f}")'''),
]

NB["05_cost"] = [
head("Cost and budget", "What a run costs here, how replication competes with exploration, and what stopping early saves.", [("Cost and benchmarking", "x_cost_and_benchmarking")]),
("code", SETUP),
("md", "## X1-P01: cost in a form that can be planned with\n\nTime per run, measured live, across the scenario space."),
("code", '''g = np.random.default_rng(1); X = g.uniform(SPACE["xl"], SPACE["xu"], (200, 4)); T, F, St = [], [], []
for i, x in enumerate(X):
    t = time.perf_counter(); r = runner.run(S.Params(*map(float, x)), i, LEVELS["medium"]); T.append(time.perf_counter() - t); F.append(r["failed"]); St.append(r["steps"])
T, F = np.array(T), np.array(F)
print(f"mean {1000 * T.mean():.0f} ms per run, {len(T) / T.sum():.0f} runs/s on one process; passed runs {1000 * T[~F].mean():.0f} ms, failed runs {1000 * T[F].mean():.0f} ms")
print("runs in the v2 campaign:", {k: sum(v for n, v in SUMMARY["runs"].items() if n.startswith(k)) for k in ("gate", "truth", "search")})'''),
("md", "## X1-P02: splitting one budget between exploration and replication\n\nA calculation from saved results. For a total budget of runs, each reported failure costs the rule's mean reruns, so replication reduces what exploration can buy."),
("code", '''B = 2000
for l in ("low", "medium", "high"):
    s = SUMMARY[l]["search"]; Rl = s["scores"]["0.5"]["rules"]
    for arm in ("nsga2", "random"):
        rate = s["reported"][arm] / 4000
        for rule in ("majority-of-19", "SPRT 0.2/0.8, a=b=0.05"):
            c = Rl[rule]["all"]["reruns"]["est"]; e = B / (1 + rate * c)
            print(f"{l:6s} {arm:6s} {rule:24s} of {B} runs: explore {e:6.0f}, replicate {B - e:6.0f}, reported failures {rate * e:6.0f}")'''),
("md", "## X1-P04: ending a run early\n\nThe runner stops once the car is 3 m past the lane edge. The comparison is the steps used against the steps a run to the road's end would take."),
("code", '''X2 = X[F][:60]; used = np.array([St[i] for i in np.flatnonzero(F)[:60]]); full = np.array([int(((S.ROAD_LENGTH - 5) / x[0] + 2) / runner.DT) for x in X2])
print(f"failed runs: mean steps used {used.mean():.0f} of a possible {full.mean():.0f} ({100 * (1 - used.sum() / full.sum()):.0f}% saved)")'''),
("md", "## X1-P05: parallel execution\n\nThe same batch on one and on two workers. The number is machine-dependent."),
("code", '''from stp.v2.jobs import run_jobs
d = Path(tempfile.mkdtemp()); P = S.Params(15.0, 0.01, -0.01, 0.2).dict()
for w in (1, 2):
    t = time.time(); run_jobs(d, f"w{w}", [("medium", P, i, 0, f"w{w}") for i in range(300)], d / f"w{w}.jsonl", workers=w); print(w, "workers:", round(300 / (time.time() - t), 1), "runs/s")'''),
]

def build(execute):
    from nbclient import NotebookClient
    for name, cells in NB.items():
        nb = nbf.v4.new_notebook(); nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        nb.cells = [nbf.v4.new_markdown_cell(t) if k == "md" else nbf.v4.new_code_cell(t) for k, t in cells]
        if execute:
            import time as T
            t = T.time(); NotebookClient(nb, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(HERE)}}).execute(); print(name, round(T.time() - t), "s", flush=True)
        nbf.write(nb, HERE / f"{name}.ipynb")

if __name__ == "__main__":
    build("--execute" in sys.argv)
