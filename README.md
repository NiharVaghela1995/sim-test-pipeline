# sim-test-pipeline

CPU-only closed-loop simulation testing, built around one question: when a search reports a failure, how many replications and which verdict rule are needed before calling it real?

Stage 1 uses OpenSBT 0.1.7 with esmini 3.11.0 and a seeded lane-keeping controller. Stage 2, Autoware Mini in planner simulation, is not started.

Built in from the start: a realisation check on every run, a pinned environment, a random baseline at equal budget, and replication of every reported failure.

```bash
scripts/setup_env.sh                  # about 80 MB, no sudo
.venv/bin/python -m pytest -q tests
scripts/run_campaign.sh               # resumable, checkpoints every 100 runs
```

Plan and input ranges were fixed before the main run: `docs/PREREG.md`, `docs/CALIBRATION.md`. v1, a noise-dominated cautionary result: `docs/REPORT.md`. The corrected campaign, with verdict rules scored against ground truth: `docs/v2/REPORT.md`, with its plan in `docs/v2/PLAN.md`. A GP boundary demo on a cut-in with esmini's ACC (GP with active learning against Sobol and random designs): `docs/GP_BOUNDARY_REPORT.md`, plan in `docs/GP_BOUNDARY_PLAN.md`. The same demo with the rule taken from UN R157 para. 5.2.5.2 (no collision under the cut-in conditions, plus a stated 1.0 m margin): test design `docs/R157_TEST_DESIGN.md`, plan `docs/R157_PLAN.md`, report `docs/R157_REPORT.md` (branch `r157-rule`). The same cut-in with injected noise (perception noise on the cutter, actuation delay, three levels) and a heteroskedastic GP against a homoscedastic one, Sobol and random, targeting {x : p(x) ≥ 0.10}: plan `docs/NOISE_PLAN.md`, report `docs/NOISE_REPORT.md` (branch `noise-gp`).

Course notebooks (branch `course-notebooks`): runnable companions to course Modules 13, 14, 15, 17 and 32 on initial designs, surrogates, acquisition functions, replication and evaluation, with a shared harness of test problems with known failure regions. Each ends with an esmini cut-in case from this pipeline. See `notebooks/course/README.md`.
