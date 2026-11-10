# sim-test-pipeline

CPU-only closed-loop simulation testing, built around one question: when a search reports a failure, how many replications and which verdict rule are needed before calling it real?

Stage 1 uses OpenSBT 0.1.7 with esmini 3.11.0 and a seeded lane-keeping controller. Stage 2, Autoware Mini in planner simulation, is not started.

Built in from the start: a realisation check on every run, a pinned environment, a random baseline at equal budget, and replication of every reported failure.

```bash
scripts/setup_env.sh                  # about 80 MB, no sudo
.venv/bin/python -m pytest -q tests
scripts/run_campaign.sh               # resumable, checkpoints every 100 runs
```

Plan and input ranges were fixed before the main run: `docs/PREREG.md`, `docs/CALIBRATION.md`. First result, including why it needs a corrected design: `docs/REPORT.md`.
