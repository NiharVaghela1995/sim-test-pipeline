# sim-test-pipeline

CPU-only experiments on scenario-based testing of automated driving functions in simulation, built around two
questions:

1. When a search reports a failure, how many reruns and which verdict rule are needed before calling it real?
2. How few simulator runs are enough to map the failure region of a parameter space, and how do you show that a method
   for this works?

Everything runs on a laptop CPU with [esmini](https://github.com/esmini/esmini) 3.11.0 and
[OpenSBT](https://github.com/opensbt/opensbt-core) 0.1.7, in a pinned environment. Every study was planned in writing
before its main run: its hypotheses, metrics and decision rule are in a plan file committed before any result. Every run
passes a realisation check (did the simulator execute the intended scenario?). Every method is compared with a random or
Sobol' baseline at equal budget and on paired seeds. Analyses added after the fact are labelled as such.

All results come from injected noise and simple controllers in one simulator. None of them says anything about a real
vehicle.

## The studies

| Study | Question | Plan | Report | Code |
|---|---|---|---|---|
| **v1: verdict rules, lane keeping** | Which rerun rule separates real from spurious failures of an OpenSBT/NSGA-II search on a seeded lane-keeping controller? | `docs/PREREG.md`, `docs/CALIBRATION.md` | `docs/REPORT.md` | `src/stp/` (top level) |
| **v2: verdict rules against ground truth** | The same, after fixing the v1 design flaw, with each scenario's true failure probability estimated from 200 runs | `docs/v2/PLAN.md` | `docs/v2/REPORT.md` | `src/stp/v2/` |
| **GP boundary demo** | Does a GP with active learning (straddle criterion) find the boundary of a cut-in failure region, for esmini's ACC, better than Sobol' or random designs? | `docs/GP_BOUNDARY_PLAN.md` | `docs/GP_BOUNDARY_REPORT.md` | `src/stp/cutin/` |
| **R157 cut-in rule** | The same demo with the pass criterion taken from UN R157 para. 5.2.5.2 (no collision) plus a stated 1.0 m margin | `docs/R157_TEST_DESIGN.md`, `docs/R157_PLAN.md` | `docs/R157_REPORT.md` | `src/stp/r157/` |
| **Noisy SUT, heteroskedastic GP** | With perception noise and actuation delay on a Python port of esmini's ACC, does a heteroskedastic GP map {x : p(x) ≥ 0.10} better than a homoskedastic one, Sobol' or random? | `docs/NOISE_PLAN.md` | `docs/NOISE_REPORT.md` | `src/stp/noise/` |
| **Stage notebooks** | Five short notebooks, one per pipeline stage (search, execution and realisation, oracle, failure validation, cost), reading the v2 results | | `notebooks/*.ipynb` | `notebooks/build.py` |
| **Method notebooks** | Runnable notebooks on initial designs, surrogate models, acquisition functions, replication and evaluation, with a shared harness of test problems with known failure regions; each ends with an esmini cut-in case | | `notebooks/course/` | `notebooks/course/failreg/` |

Supporting documents: `docs/CODE_MAP.md` (where each part of the code sits) and `docs/COVERAGE_MATRIX.md` (which open
problems the pipeline can test).

**The `v1-noise-dominated` tag** marks the end of v1. v1 drew the control latency per run, and the latency decided
almost every outcome. All reported failures at one noise level therefore had about the same reproduction rate, and no
verdict rule could be ranked. The tag keeps that state of the code and results visible as a cautionary result. v2 fixed
the latency and answers the question; `docs/v2/REPORT.md` explains the difference.

**Problem IDs.** IDs such as `S02-P05` or `X2-P06` in `docs/COVERAGE_MATRIX.md` and some plans refer to problems in the
author's own research map, which is not public. Each ID is shown with a short name of the problem, so the documents
can be read without the map.

## Setup

Linux x86-64, Python 3.10, [uv](https://github.com/astral-sh/uv), no sudo. About 80 MB is downloaded (esmini binary,
OpenSBT source); both are checked against the pins in `env/`.

```bash
scripts/setup_env.sh                                                           # pinned .venv, esmini, OpenSBT
uv pip install --python .venv/bin/python -r env/requirements-notebooks.txt     # notebook runner
.venv/bin/python -m pytest -q tests                                            # unit tests, about 40 s
.venv/bin/python -m pytest -q -o addopts="" -m notebook tests/test_notebooks.py   # executes all 10 notebooks
```

CI (`.github/workflows/ci.yml`) builds the environment and runs both test commands on every push.

## Reproduce

Committed results are in `results/`. Raw per-run logs go to `results/raw/` (not committed). Times are wall-clock on a
4-core laptop CPU unless noted.

| Study | Command | Time |
|---|---|---|
| v1 | `scripts/run_campaign.sh` (resumable, checkpoints every 100 runs) | 2 h 2 min, 196,840 runs |
| v2 | `scripts/run_campaign_v2.sh` | 3 h 7 min on 2 workers, 373,452 runs |
| GP boundary demo | the module sequence in `docs/GP_BOUNDARY_REPORT.md`, "Reproduce" | about 2 h (reference grid about 30 min, scoring about 75 min) |
| R157 rule | `PYTHONPATH=src .venv/bin/python -m stp.r157.experiment all 4`, then `-m stp.r157.plots` | reference grid 343 s (19,056 runs); total not recorded |
| Noisy SUT | `PYTHONPATH=src .venv/bin/python -m stp.noise.experiment all 4`, then `-m stp.noise.plots` | about 4 h 15 min, about 264,000 runs |
| Stage notebooks | `.venv/bin/python notebooks/build.py --execute` | a few minutes |
| Method notebooks | `.venv/bin/python notebooks/course/build.py --execute` | under 5 min per notebook |
| One campaign, clean clone | `scripts/rerun_clean.sh results/gp_boundary/manifests/gp_al_0.json` | about 2 min |

Each campaign writes a manifest (`results/*/manifests/`) with its settings, seeds, every run and the environment, so a
single campaign can be rerun and compared.

## Notes

- The stage notebooks link to the matching assessment pages on the author's website
  (<https://niharvaghela1995.github.io/masters-thesis/>).
- The method notebooks cite the papers they implement. Their background comes from the author's own study notes, which
  are not public.

## Licence

Code: MIT (`LICENSE`), except `src/stp/noise/acc.py`, a port of esmini code, which stays under MPL-2.0. Documentation in
`docs/` and data in `results/`: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Third-party software and its
licences: `THIRD_PARTY.md`.
