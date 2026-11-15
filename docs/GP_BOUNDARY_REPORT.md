# GP boundary demo: report (2026-11-15)

**Result.** By the rule fixed in the plan, **GP with active learning (GP-AL) helps at every budget.** At 100, 200 and 300 esmini runs it misclassified fewer points than the same GP on a Sobol design or on a random design. On misclassification it won in 10 of 10 paired seeds at every budget and against both baselines, with Holm-corrected p = 0.0059. Its median misclassification was 0.10–0.19 of the baseline's. Boundary error gives the same verdict (ratios 0.06–0.38). Its 95% band contains the reference boundary at 90.1% on average, which just meets the planned "calibrated at 95%" rule. All the misses are on the stretch at small gaps where the margin is not monotone. esmini with this controller is deterministic: 1,500 replicate runs were bitwise identical, and a campaign rebuilt in a clean clone from its manifest was identical.

Plan: `docs/GP_BOUNDARY_PLAN.md`, committed in `dfc5f44` before any reference, campaign or replication run. Anything decided after it is marked **post hoc**. Every result below comes from a file in `results/gp_boundary/`, named in each section. Setup values come from the code and `env/` locks, and the controller properties come from the plan's pilot section.

## Setup (unchanged from the plan)

- **Simulator:** esmini 3.11.0, pinned by zip sha256, step 0.02 s, 15 s per run.
- **Scenario:** the cut-in from `src/stp/cutin/scenario.py`.
- **Parameters:**
  - ego speed 20–35 m/s
  - gap at the cut-in moment 5–40 m; the cut-in moment is when the cutting car's body crosses the lane line
  - relative speed of the cutting car −10 to 0 m/s
- **System under test:** esmini's `ACCController` on the ego, with time gap 1.5 s, set speed equal to the ego speed, and longitudinal control only. The cutting car is scripted.
- **Rule:** min TTC ≥ 1.5 s (a placeholder). Margin = min TTC − 1.5 s, with TTC capped at 6 s.

Two properties of this controller, found in the pilot (plan, "Known properties"), matter for the results:

- **It reacts earlier at small gaps.** At 5 m it brakes while the cutting car is still 2.66 m to the side; from 7 m up, only at about 1.75 m. So at small gaps the margin is not monotone in gap: it rises, dips and rises again. In the reference, 109 of the 332 gap lines that have a boundary cross zero more than once (computed with `reference.crossings` on `reference_grid.npz`).
- **It sometimes brakes harder than its limit.** Below about 0.7 m bumper gap it drops speed in one step, well beyond its 6 m/s² limit. A gate rejects a run if this happens before the minimum TTC. The over-braking section below covers what it does to the results.

## 1. Realisation check

Every run is checked against its intended parameters by 13 gates (`src/stp/cutin/gates.py`). A run that is not realised gets no pass or fail verdict.

- **Clean runs:** all are realised. That covers the 91,791 reference runs, the 9,000 campaign runs, the 150 bisection runs and the 1,500 replicate runs.
- **Broken scenarios:** all 9 deliberately broken files are caught, are not realised and get no verdict (`broken_scenarios.csv`, `broken/*.xosc`, `tests/test_cutin.py`).

| Broken scenario | Gates that caught it |
|---|---|
| ego without ACC | controllers, outcome_settled |
| cutting car starts in the ego lane | start_pose, start_speed, lane_change_start, gap_at_cut, lane_change_end, ego_cruise_before_cut |
| no lane change | lane_change_start, gap_at_cut, lane_change_end, outcome_settled |
| lane change away from the ego | lane_change_start, gap_at_cut, lane_change_end, outcome_settled |
| lane change triggered late | lane_change_start, gap_at_cut |
| cutting car placed 2 m off | start_pose, gap_at_cut |
| cutting car 1 m/s off | start_speed, cut_speed_held, gap_at_cut |
| ego 1 m/s off | start_speed, ego_cruise_before_cut |
| simulation too short | lane_change_end, outcome_settled |

**Post hoc fix.** The "lane change away from the ego" test exposed a bug after the plan was committed. The cut-in moment was found from the *absolute* lateral shift, so a lane change away from the ego counted as a crossing. It now uses the shift towards the ego lane (commit `b150416`). This fix was made before any reference or campaign run.

## 2. Reference

The reference is a grid of 31 ego speeds × 21 relative speeds × 141 gaps (0.25 m apart), 91,791 runs (`reference_grid.npz`).

- **Realisation and outcomes:** all runs were realised. 14.7% fail the rule; none collided.
- **Boundary:** the reference boundary gap g* is computed on each of the 651 (speed, relative speed) lines. 319 lines pass at every gap.
- **Resolution check** (`reference_resolution.json`, `reference_bisection.csv`):
  - **Every second gap (0.5 m) against the full grid:** mean |Δg*| 0.025 m, 90th percentile 0.0004 m.
  - **Three exceptions:** at 24.5–25.5 m/s and −5 m/s, the dip near 10 m only just touches zero (margin −0.003), so the coarse grid misses it (max 5.36 m).
  - **Bisection to 0.01 m:** on 30 random lines it moves g* by 0.002 m on average and by 0.004 m at most.
  - **Conclusion:** the reference is far more precise than the 1.0 m target.

## 3. Comparison at equal budgets

Each arm has 10 seeds × 300 runs, scored every 20 runs against the reference. Sources: `metrics.csv`, `summary.json`, `campaign_runs.csv`, `manifests/`. Sobol and GP-AL share their first 30 points per seed. All 9,000 runs were realised.

**Misclassified share of the box** (median, with min–max over 10 seeds):

| Runs | GP-AL | Sobol + GP | Random + GP |
|---|---|---|---|
| 100 | 0.26% (0.17–0.63) | 1.58% (1.14–2.09) | 1.74% (1.33–2.78) |
| 200 | 0.10% (0.08–0.14) | 0.78% (0.41–1.28) | 0.99% (0.44–1.69) |
| 300 | 0.09% (0.06–0.11) | 0.45% (0.37–0.92) | 0.68% (0.41–1.44) |

**Mean boundary error |ĝ* − g*|, in metres** (median, with min–max):

| Runs | GP-AL | Sobol + GP | Random + GP |
|---|---|---|---|
| 100 | 0.19 (0.06–0.46) | 0.55 (0.28–0.88) | 0.59 (0.13–1.36) |
| 200 | 0.027 (0.006–0.075) | 0.33 (0.06–0.67) | 0.39 (0.16–1.03) |
| 300 | 0.029 (0.012–0.054) | 0.22 (0.11–0.33) | 0.27 (0.09–0.77) |

**Planned tests on misclassification** (H1, H2):

- **Setup:** one-sided Wilcoxon signed-rank tests with Holm correction over the 6 tests (3 budgets × 2 baselines).
- **Result:** every test gives p_holm = 0.0059 and 10/10 wins, with median ratios from 0.10 to 0.19. All 6 pass, so the verdict at each budget is "helps".
- **Reverse direction** (baseline better than GP-AL): none of the 6 tests passes; the baseline won 0 of 10 seeds in every case.
- **Boundary error:** the same tests pass at every budget against both baselines (`tests_boundary_error`).

**Runs needed for a target** (H3; median over seeds of the first scored budget that reaches it; source: `runs_needed`):

| Target | GP-AL | Sobol + GP | Random + GP |
|---|---|---|---|
| misclassification ≤ 2% | 50 | 60 | 90 |
| misclassification ≤ 1% | 80 | 200 | 200 (reached by 8/10 seeds) |
| boundary error ≤ 1.0 m | 50 | 40 | 60 |

H3 holds for the misclassification targets and not for the 1.0 m boundary target. That target is loose enough that Sobol reaches it at 40 runs, before active learning has had much effect: GP-AL spends its first 30 runs on the same Sobol points.

Figures:
- `fig_misclass_vs_budget.png`
- `fig_boundary_error_vs_budget.png`
- `fig_boundary_map.png`: reference and GP-AL seed 0 at 300 runs, at 20, 27.5 and 35 m/s.

**Read-off at 30 m/s** (GP-AL seed 0, 300 runs; `readoff_30.csv`). With the cutting car 5, 7.5 and 10 m/s slower:

| Cutting car slower by | Reference g* | GP-AL estimate | 95% band |
|---|---|---|---|
| 5 m/s | 10.54 m | 10.50 m | 10.27–10.66 m |
| 7.5 m/s | 15.76 m | 15.75 m | 15.58–15.94 m |
| 10 m/s | 21.06 m | 21.06 m | 20.83–21.31 m |

At 0 and −2.5 m/s every gap passes.

## 4. Does the GP model matter? (H5)

On the Sobol design at 300 runs (`summary.json`, `misclass_curves`, `permutation`):

| Model on the Sobol design | Misclassified share | Boundary error |
|---|---|---|
| GP | 0.45% | 0.22 m |
| 1-NN | 3.47% | 1.12 m |
| Constant | 14.68% | 5.58 m |

In all 20 permutation tests (GP-AL and Sobol, 10 seeds each), the real fit's marginal likelihood beats all 19 fits to shuffled margins, so p = 0.05, the smallest attainable. H5 holds.

A 1-NN classifier on the GP-AL design does *worse* than on Sobol: 4.61% against 3.47% at 300 runs. GP-AL's points bunch up near the boundary and leave the rest of the box thin. That design only pays off with a model that interpolates smoothly.

## 5. Calibration of the band (H4)

The table gives the share of the 551 reference boundary points inside the GP band at 300 runs: the mean over seeds, with the range (`summary.json`, `calibration`).

| Stated level | GP-AL | Sobol + GP | Random + GP |
|---|---|---|---|
| 50% | 72.4% (68.1–77.7) | 77.2% (64.8–90.4) | 73.8% (48.1–91.8) |
| 80% | 82.7% (78.0–87.3) | 90.1% (76.4–99.3) | 85.7% (67.2–96.9) |
| 90% | 87.0% (82.0–92.0) | 94.4% (82.2–100) | 89.0% (71.0–98.9) |
| 95% | 90.1% (85.5–94.2) | 96.2% (87.3–100) | 91.0% (73.9–99.3) |
| 99% | 94.3% (89.8–97.6) | 98.1% (95.6–100) | 94.0% (78.9–99.8) |

- **Planned verdict at 95%:** all three arms are "calibrated at 95%", since their means fall between 0.90 and 0.99. GP-AL passes narrowly, and 4 of its 10 seeds are below 0.90 (`metrics.csv`, `contain_95`). The plan expected H4 to fail; by its own rule it passes.
- **Shape of the error:** the band is too wide at the 50% level and too narrow at the 99% level. The model's errors are heavier-tailed than a normal distribution.
- **GP-AL's band is narrow:** its mean width at the boundary is 0.053 s of margin, against 0.39 s for Sobol and 0.42 s for random (`band_width_mean`).

**Post hoc** (`band_misses.json`, `src/stp/cutin/band_misses.py`): where does the GP-AL 95% band miss?

- On lines with a single crossing, it never misses: 0% in all 10 seeds.
- On lines with more than one crossing, it misses 16.7% of points on average.
- No miss is above a gap of 9.95 m.

So the band is honest where the boundary is smooth and too confident in the non-monotone zone at small gaps. That zone is the "sharp boundary" risk the plan names.

## 6. Replication and determinism (H6, H7)

**esmini with this ACC is deterministic**, and all replicates of a point give the same margin to the last bit:

- **Points:** 150 points closest to the boundary (`replication.csv`, `replication.json`): the 10 runs with the smallest |margin| from each of the 10 GP-AL campaigns (100 runs), the closest being 5.1 × 10⁻⁵ s from the threshold, and 50 reference points next to a sign change.
- **Runs:** each point was rerun 10 times, giving 1,500 runs. They ran in sequence and in a 4-worker pool in shuffled order. Two of the 10 used esmini seed 987 instead of 0.
- **Result:** 150 of 150 points were bitwise identical in every repeat. The largest difference was 0.0 and all verdicts matched.

This is the expected result and it is a good one. The pass/fail verdict at a point is a property of the scenario, so no noise model or replicate allocation is needed. That differs from Project 2, where noise was estimated from 2–5 replicates (CLAIM_CORRECTIONS.md §1, as listed in the plan).

**Rerun from manifest** (`determinism_rerun.json`). `scripts/rerun_clean.sh` takes a fresh git clone of commit `68450d7`, builds a fresh `.venv` from `env/requirements.lock`, checks the esmini zip sha256, and rebuilds GP-AL seed 0 (300 runs) from `manifests/gp_al_0.json` alone. The result was **identical**:

- `campaign.rerun` compared all 300 run parameters, .xosc hashes and margins with the manifest and found no difference (the record stores the verdict, `problems: []`, and the hash);
- the final prediction hash on the reference grid matches;
- the run took 1 min 33 s.

`tests/test_gp_boundary.py` reruns a short campaign in a fresh process on every test run.

## 7. Over-braking runs (post hoc, requested after the plan)

Source: `overbrake.json`, `src/stp/cutin/overbrake.py`.

**Where the runs sit.** 1,411 of the 91,791 reference runs (1.5%) show the one-step over-braking, always after the minimum TTC. They don't cluster near the boundary:

- All of them fail the rule clearly: margin −1.43 to −1.01 s, so min TTC ≤ 0.49 s.
- They sit at gaps of 5–9 m and relative speeds of −10 to −7.5 m/s.
- Each is at least 10.48 m below its line's boundary gap (median 13.2 m).
- None has |margin| < 0.5 s, against 16.0% of all grid points.

**Leaving them out:**

- **Reference boundary:** g* changes by 0.000 m on every line.
- **Comparison:** over-braking runs are dropped from each campaign's training data, with the designs kept as run, and over-braking grid points are dropped from scoring. All 12 tests on misclassification and boundary error still pass. The verdict is unchanged: GP-AL helps at 100, 200 and 300 runs, with median misclassification within 0.0001 of section 3 for GP-AL and within 0.0017 for Sobol and random.

The over-braking is a defect of the controller model, not of the scenario, and it doesn't touch the boundary.

## What was decided after the plan

All of these are marked post hoc above:

- the signed-shift fix in the cut-in detection;
- the over-braking analysis;
- the analysis of where the band misses.

**Figures.** They use the first three categorical colours of the reference palette of the plotting guidance. These are documented as distinguishable for colour-vision deficiency as a set of three, and the figures label the lines directly. The palette validator could not be run because Node is not installed.

## Limits

- **Scope:** one scenario, one controller and one placeholder threshold. The ACC's early reaction at small gaps is a property of this esmini controller, not a general finding.
- **Reference:** the "true" boundary is a 0.25 m grid. Its own error (section 2) is far below every difference reported here, but on lines that only just touch zero the boundary depends on margins of a few milliseconds.
- **Active learning:** GP-AL used the straddle score with batches of 10, and was not tuned. Other acquisition rules were not tried.

## Reproduce

```bash
PYTHONPATH=src .venv/bin/python -m stp.cutin.broken           # broken scenarios
PYTHONPATH=src .venv/bin/python -m stp.cutin.reference 4      # reference grid (~30 min on 4 CPUs)
PYTHONPATH=src .venv/bin/python -m stp.cutin.resolution
PYTHONPATH=src .venv/bin/python -m stp.cutin.campaign run     # 30 campaigns + manifests
PYTHONPATH=src .venv/bin/python -m stp.cutin.metrics 3        # ~75 min
PYTHONPATH=src .venv/bin/python -m stp.cutin.analysis
PYTHONPATH=src .venv/bin/python -m stp.cutin.plots
PYTHONPATH=src .venv/bin/python -m stp.cutin.overbrake 3
PYTHONPATH=src .venv/bin/python -m stp.cutin.band_misses 3
PYTHONPATH=src .venv/bin/python -m stp.cutin.replicate
PYTHONPATH=src .venv/bin/python -m stp.cutin.critical
scripts/rerun_clean.sh results/gp_boundary/manifests/gp_al_0.json
.venv/bin/python -m pytest tests/test_cutin.py tests/test_gp_boundary.py
```

Critical files are in `results/gp_boundary/critical/`, listed with their parameters and verdicts in `index.csv`. They include:

- the last-fail and first-pass reference pairs at 30 m/s, with min TTC 1.492 / 1.542 s, 1.499 / 1.532 s and 1.493 / 1.521 s;
- the 10 GP-AL seed-0 runs closest to the threshold (|margin| ≤ 0.0044 s).

They load in esmini with `cutin.xodr` beside them.
