"""Writes docs/COVERAGE_MATRIX.md and, with --site PATH, a reader-facing page without file names.
Classes: 1 covered by v1/v2; 2 doable on the current CPU pipeline; 3 needs Autoware Mini; 4 needs GPU/CARLA; 5 literature only.
Efforts are estimates, in working days for one person, not measurements."""
import argparse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLS = {1: "Covered by v1/v2", 2: "Doable on the CPU pipeline", 3: "Needs Autoware Mini", 4: "Needs GPU/CARLA", 5: "Literature only"}

# id, problem, class, plain text (covered by what, or what to add / why not), code (class 1), effort days (class 2), feeds
ROWS = [
("S01-P01", "Hand-chosen parameter ranges", 1, "v2 tried candidate spaces in a fixed order and required a gate on random samples. Ranges are still chosen, not derived from data.", "v2/gate.py, docs/v2/CALIBRATION.md", None, ""),
("S01-P02", "Invalid or unrealistic parameter combinations", 2, "Add constraints on speed against curvature, report the rejected share and how failures change.", "", "1–2", ""),
("S01-P03", "Exposure model fit and ignored dependence", 2, "Sample from a synthetic test-bed generator as the nominal. Tests the method only, because no real exposure data is linked.", "", "3", "G2"),
("S01-P04", "Support gaps and data sufficiency of the exposure model", 5, "Needs real traffic data at scale.", "", None, ""),
("S01-P05", "Dimensionality of the space", 2, "Add inputs such as lane width, arc length and start offset, and repeat search against random as dimension grows.", "", "2–3", ""),
("S01-P06", "Representation biases what search can find", 2, "Encode the same scenarios as radius or as lateral demand and compare what search finds.", "", "2", ""),
("S02-P01", "Directed search does not reliably beat random sampling", 1, "v2: NSGA-II found about four times the failures of random at equal budget, in half the input cells, 10 seeds, three noise levels.", "v2/campaign.py, results/v2/summary.json", None, ""),
("S02-P02", "Surrogates guide or skip simulations without a measure of how far to trust them", 2, "Fit a Gaussian-process surrogate on logged evaluations, check calibration and a no-signal control.", "", "3–4", ""),
("S02-P03", "Repeated simulations of the same scenario give different objective values", 2, "v2 measured the spread. Search still sees one noisy value: add re-evaluation in the search and compare at equal budget.", "", "3", "G1/G4"),
("S02-P04", "Low-fidelity evidence can mislead or hide failures", 4, "Needs a higher-fidelity simulator to compare with.", "", None, ""),
("S02-P05", "Rare-event sampling depends on its base distribution and proposal", 2, "Use importance sampling with v2's ground truth as the reference.", "", "3", "G2"),
("S02-P06", "Search degrades with dimension and mixed variables", 2, "Add a categorical road type on top of the extra inputs above.", "", "2–3", ""),
("S02-P07", "Search optimises a worst case when the task needs the failure region's shape", 2, "Estimate the failure boundary from v2's bisection code and score it against dense sampling.", "", "3", "G2"),
("S03-P01", "Cross-simulator disagreement", 3, "Needs a second simulator running the same SUT.", "", None, ""),
("S03-P02", "Fidelity selection and low/high agreement", 4, "Needs a high-fidelity simulator.", "", None, ""),
("S03-P03", "Sensor realism gap", 4, "Needs rendered sensors.", "", None, ""),
("S03-P04", "Vehicle dynamics model validity", 5, "A second internal model would show sensitivity, but validity needs vehicle data.", "", None, ""),
("S03-P05", "Traffic-agent realism, scripted vs reactive", 3, "The pipeline has no other actors.", "", None, ""),
("S03-P06", "Simulator credibility not demonstrated", 5, "Needs standards-based evidence and real data.", "", None, ""),
("S03-P07", "Simulator bugs", 5, "Gates catch mismatches in esmini, but a bug study is literature work.", "", None, ""),
("S03-P08", "Simulator nondeterminism", 1, "esmini is deterministic given the seed, by test. Says nothing about other simulators.", "tests/test_pipeline.py", None, ""),
("S04-P01", "SUT choice limits what results mean", 3, "One simple controller today.", "", None, ""),
("S04-P02", "Failure attribution: black-box vs module level", 3, "Needs a modular stack.", "", None, ""),
("S04-P03", "Perception mode and perception error models", 4, "v1/v2 inject noise on a lateral target only. Real perception needs a GPU.", "", None, ""),
("S04-P04", "Open-loop vs closed-loop mismatch", 3, "Needs a planner that can run both ways.", "", None, ""),
("S04-P05", "SUT non-determinism and latency", 1, "v1 showed a latency cliff deciding outcomes, and v2's gate measured it. Injected latency only.", "diagnostics.py, v2/gate.py, results/diagnostics.json", None, ""),
("S04-P06", "Integration effort and maintenance", 3, "Measured when Autoware Mini is integrated.", "", None, ""),
("S04-P07", "Fault injection into stacks", 2, "Inject dropouts and bias in the controller's input and measure propagation to the margin. Limited to this controller.", "", "3", ""),
("S05-P01", "A run may not realise the intended scenario", 1, "Eight checks on every run, seven seeded defects caught, all v2 runs realised.", "gates.py, tests/test_pipeline.py", None, ""),
("S05-P02", "Identical inputs do not give identical runs", 1, "Per-run seeds, determinism tests and measured rerun spread. Injected randomness only.", "v2/jobs.py, tests/test_pipeline.py", None, ""),
("S05-P03", "Invalid or ill-formed tests reach the simulator", 1, "Load and specification checks reject them at run time. No static pre-check yet.", "gates.py", None, ""),
("S05-P04", "The same scenario is executed differently by different engines", 4, "Needs a second OpenSCENARIO engine, such as CARLA's.", "", None, ""),
("S05-P05", "Simulator and harness faults silently corrupt runs", 1, "Checkpointing, resume and the realisation pause. Tested on a simulated crash.", "v2/jobs.py, scripts/run_campaign_v2.sh", None, ""),
("S05-P06", "Results are hard to reproduce: environment not recorded", 1, "Pinned environment and a manifest per campaign. A rerun of one search seed matched exactly.", "env/*.lock, notebooks/01_search.ipynb", None, ""),
("S06-P01", "Tail-risk objective for closed-loop failure search", 2, "Run mean, worst and tail objectives on repeated runs, then a tail-guided search. A small notebook demo exists.", "", "5–6", "G2"),
("S06-P02", "Criticality metrics and thresholds rest on unchecked assumptions", 2, "Vary the margin threshold across the campaign and report how the failure set changes.", "", "2", "G2"),
("S06-P03", "A collision verdict does not say who was responsible", 3, "Needs other actors.", "", None, ""),
("S06-P04", "Traffic rules are ambiguous, so rule oracles embed interpretations", 3, "Needs traffic and a rule set.", "", None, ""),
("S06-P05", "The objective is hard to search: masked signals, binary outcomes, noise", 2, "Compare margin-guided with binary-guided search at equal budget.", "", "3", "G2"),
("S06-P06", "Composite objectives can hide which failure type was found", 2, "Add a second failure type, then a weighted objective, and check which type is found.", "", "3", ""),
("S06-P07", "Comfort and derived-signal oracles inherit sampling artefacts", 2, "Log trajectories and compute jerk at several rates against a known signal.", "", "2", ""),
("S06-P08", "Misbehaviour indicators trade false alarms against misses", 2, "Predict failure from the early part of a run and report the alarm trade-off.", "", "3", ""),
("S07-P01", "Flakiness-aware validation of reported failures", 1, "v2: reported failures reproduce at 0.95 to 0.99 against a 22% to 29% base rate. v1 is the cautionary contrast.", "v2/campaign.py, docs/v2/REPORT.md", None, ""),
("S07-P02", "Replication budgets and noise-aware verdicts", 1, "v2 scored 20 rules against ground truth at three noise levels, with stated against achieved error.", "v2/rules.py, v2/analysis.py", None, ""),
("S07-P03", "Failure transfer across fidelity levels and simulators", 4, "Needs both fidelity levels.", "", None, ""),
("S07-P04", "Simulation-to-real failure transfer", 5, "Needs a vehicle.", "", None, ""),
("S07-P05", "Realism and plausibility of reported failures", 5, "Needs a reference for what is plausible.", "", None, ""),
("S07-P06", "Failure attribution and root-cause explanation", 3, "Needs a modular stack.", "", None, ""),
("S07-P07", "Linking simulator credibility to individual failures", 5, "Depends on credibility evidence not available here.", "", None, ""),
("S08-P01", "Coverage of the failure region cannot be measured at realistic cost", 2, "Build a dense reference sample of the v2 space and test coverage estimators against it.", "", "4", ""),
("S08-P02", "Optimisation-driven search covers failure regions poorly", 1, "v2 counted distinct input cells: NSGA-II about half of random's.", "v2/analysis.py, results/v2/summary.json", None, ""),
("S08-P03", "Failure counts do not equal distinct failure modes", 2, "Cluster failures from logged trajectories and compare counts with modes.", "", "3", "G1/G4"),
("S08-P04", "Diversity scores depend on descriptors and settings", 2, "Recompute diversity under several descriptors on logged runs.", "", "2", ""),
("S08-P05", "Input and structural coverage is weakly tied to fault finding", 2, "Seed faults in the controller and compare coverage with faults found.", "", "3", ""),
("S08-P06", "No accepted rule says when closed-loop search can stop", 2, "Test stop rules against the dense reference above.", "", "4", ""),
("S08-P07", "Stop statistics assume sampling that closed-loop search violates", 2, "Compare estimators under random and adaptive sampling.", "", "3", ""),
("S08-P08", "Summaries of failure regions are hard to validate", 2, "Fit rule or tree summaries and score them against the dense reference.", "", "2", ""),
("X1-P01", "Simulation cost is not reported in a plannable form", 1, "Runs per stage, wall-clock and time per run are recorded for this setup.", "campaign logs, notebooks/05_cost.ipynb", None, ""),
("X1-P02", "Splitting a budget between exploration, replication and validation", 2, "Run the allocation experiment. A saved-results calculation exists, not a test.", "", "3–4", "G1/G4"),
("X1-P03", "Selecting and ordering tests before execution", 2, "Use a classifier on inputs, already near AUC 0.98 here, to order runs.", "", "3", ""),
("X1-P04", "Ending a run early when its outcome is settled", 2, "The runner stops 3 m past the lane edge. Test earlier stopping and its error.", "", "2", "G1/G4"),
("X1-P05", "Parallel execution and hardware cost", 1, "One and two workers measured for this setup.", "notebooks/05_cost.ipynb, v2/jobs.py", None, ""),
("X1-P06", "Time budgets versus evaluation budgets", 2, "Rerun search with a time limit and compare with an evaluation limit.", "", "1–2", ""),
("X1-P07", "Cost of setting up the simulator and integrating the SUT", 3, "Measured when integrating.", "", None, ""),
("X1-P08", "Cost ratios used by multi-fidelity methods", 4, "Needs two fidelity levels.", "", None, ""),
("X2-P01", "Baselines: random can match the proposed search", 1, "Random baseline at equal budget in both campaigns. No quasi-random arm.", "v2/campaign.py", None, ""),
("X2-P02", "Comparing search methods fairly when the simulator is noisy", 1, "Equal budget, 10 seeds, confirmed failures and a planned correction for multiple tests.", "v2/analysis.py", None, ""),
("X2-P03", "Shared benchmarks and competitions", 5, "A community effort.", "", None, ""),
("X2-P04", "Reproducibility of replication packages", 2, "Tidy the repository and test a clean-clone rerun on another machine.", "", "2", ""),
("X2-P05", "Benchmark functions with known answers versus real driving systems", 2, "Compare method rankings on a synthetic known boundary and on this pipeline.", "", "3", ""),
("X2-P06", "Metric choice: hypervolume, IGD and failures per budget", 2, "Recompute these on logged evaluations and see whether the ranking changes.", "", "2", ""),
("X2-P07", "Replications that changed a published conclusion", 5, "A literature question. v1 against v2 is only a personal example.", "", None, ""),
]

RANK = [
("X1-P02", "G1/G4", "Direct. It decides how many reruns a campaign can afford."),
("S02-P03", "G1/G4", "Direct. Search that handles noise changes which failures need confirming."),
("X1-P04", "G1/G4", "Lowers the cost of every rerun."),
("S08-P03", "G1/G4", "Confirmed failures only count once they are separated into modes."),
("S06-P01", "G2", "Direct. It is the G2 experiment."),
("S06-P05", "G2", "Decides how a tail objective can guide search."),
("S06-P02", "G2", "A tail is only meaningful once the threshold is shown stable."),
("S02-P07", "G2", "Shape of the failure region, where tail objectives act."),
("S02-P05", "G2", "Rare-event estimates against a known truth."),
("S01-P03", "G2", "The nominal distribution a tail claim rests on."),
]

EXPERIMENTS = [
("E1. Budget split for confirmation", "S07-P02, X1-P02", "At fixed total budgets, vary the share spent on replication and the rule used, at three noise levels.", "3–4", "Confirmed failures against budget, per rule. Completes G4."),
("E2. Tail objective on repeated runs", "S06-P01, S06-P02", "30 scenarios, 20 reruns each, mean, worst and tail objectives. Then one tail-guided search.", "5–6", "Rank-sensitivity report and first G2 result."),
("E3. Noise-aware search", "S02-P03, X2-P02", "NSGA-II with no re-evaluation, fixed re-evaluation and sequential re-evaluation at equal budget.", "3", "Confirmed failures per budget for each variant."),
("E4. A less sharp failure boundary", "S01-P05, S07-P02", "Add inputs and stronger timing effects so more scenarios have intermediate probability, then repeat the rule scoring.", "3–4", "Whether v2's rule choice survives when the choice matters more."),
("E5. Failure-region reference and stop rules", "S08-P01, S08-P06", "A dense reference of the frozen space, with coverage estimators and stop rules scored against it.", "4–5", "Coverage and stop-rule accuracy with a known answer. Feeds G5."),
]


def table(rows, site):
    head = "| ID | Problem | Class | Status or what to add | Days |" if site else "| ID | Problem | Class | Status or what to add | Code and result | Days |"
    out = [head, "|---|---|---|---|---|" if site else "|---|---|---|---|---|---|"]
    for i, p, c, t, code, d, f in rows:
        if site: out.append(f"| {i} | {p} | {c}. {CLS[c]} | {t} | {d or ''} |")
        else: out.append(f"| {i} | {p} | {c} | {t} | {code} | {d or ''} |")
    return "\n".join(out)


def body(site):
    n = Counter(r[2] for r in ROWS); by = {r[0]: r for r in ROWS}
    assert len(ROWS) == 72 and len(by) == 72
    s = ["| Class | Meaning | Problems |", "|---|---|---|"] + [f"| {c} | {CLS[c]} | {n[c]} |" for c in CLS]
    r2 = ["| Rank | ID | Problem | Feeds | Why | Days |", "|---|---|---|---|---|---|"] + [f"| {k} | {i} | {by[i][1]} | {g} | {w} | {by[i][5]} |" for k, (i, g, w) in enumerate(RANK, 1)]
    e = ["| Experiment | Problems | Design | Days | Artifact |", "|---|---|---|---|---|"] + [f"| {a} | {b} | {c} | {d} | {f} |" for a, b, c, d, f in EXPERIMENTS]
    return "\n\n".join([
        "\n".join(s),
        "\"Covered\" means covered on one simple controller in esmini with injected noise. It does not mean the problem is solved. Days are my estimates for one person and have not been measured.",
        "## All problems", table(ROWS, site),
        "## Ranking the CPU-pipeline items", "Ranked by how directly each feeds G1/G4 (confirming reported failures, verdict rules) and G2 (tail objective). The other CPU-pipeline items feed neither directly and are not ranked.", "\n".join(r2),
        "## The next five experiments", "\n".join(e),
        "Autoware Mini follows these: the problems in class 3 all wait on it, and integrating it is itself a measurement (X1-P07, S04-P06).",
    ]) + "\n"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--site"); a = ap.parse_args()
    (ROOT / "docs/COVERAGE_MATRIX.md").write_text("# Coverage matrix\n\nEvery problem of the master's research map, classified by what could test it. Problem names are shortened from the map.\n\n" + body(False))
    if a.site:
        Path(a.site).write_text('---\ntitle: "Coverage matrix"\ndescription: "Which problems in the map the pipeline has covered, could cover, or cannot test, and the next five experiments."\ndate: 2026-11-10\nauthor: Nihar Vaghela\nformat:\n  html:\n    toc: true\n---\n\n::: {.callout-important}\n## Crux\n\nThe map has 72 problems. This page says, for each, whether the two campaigns covered it, whether the current CPU pipeline could, or whether it needs Autoware Mini, a GPU with CARLA, or stays with the literature. It then ranks what the pipeline could do next by how directly it feeds the opening questions. Every effort figure is an estimate.\n:::\n\n' + body(True))
    print(sorted(Counter(r[2] for r in ROWS).items()))


if __name__ == "__main__":
    main()
