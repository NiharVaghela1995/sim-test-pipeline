# R157 rule on the GP boundary demo: report (2026-11-17)

**Result.** With the placeholder replaced by UN R157's cut-in requirement (para. 5.2.5.2: no collision under conditions (a)–(c)) plus a stated 1.0 m minimum-gap margin, esmini's ACC **never collides** anywhere in the region where the paragraph applies, so it meets R157's own criterion on the whole tested range. It **violates the 1.0 m margin in 1.5 %** of that region: slow-closing cut-ins (v_rel 0.5–1.5 m/s) at nominal TTC_LaneIntrusion 0.5–1.6 s, at every ego speed, by up to 0.21 m. By the rule fixed in the plan, **GP with active learning helps at 100, 200 and 300 runs** against Sobol and random designs (10 of 10 paired seeds, Holm-corrected p = 0.0059, median ratios 0.13–0.31), and every arm beats the "everything passes" control. GP-AL's band is calibrated at 95 % (96.9 % containment). Its cost: **26.6 % of GP-AL's runs were not realised**, against 2.6 % for the baselines, because the ACC's over-braking artefact clusters near the boundary.

Plan: `docs/R157_PLAN.md` and test design `docs/R157_TEST_DESIGN.md`, committed in `3d13470` before any reference, campaign, hold-out or replication run. Anything decided after that commit is marked **post hoc**. Every number below comes from a file in `results/r157/`, named in each section.

## Setup (unchanged from the plan)

- esmini 3.11.0 pinned by sha256, step 0.02 s, 15 s per run; ego: esmini `ACCController` (time gap 1.5 s, maximum deceleration 6 m/s², set speed = ego speed); scripted cutter, 3 s sinusoidal lane change from 2.0 s.
- Parameters: ego speed 10–16.667 m/s (36–60 km/h, R157 para. 5.2.3.1), v_rel 0.5–8 m/s, nominal TTC_LaneIntrusion 0.2–3.0 s at the yaw-aware reference point; cutter speed ≥ 6 m/s. Runs only where para. 5.2.5.2 applies.
- KPI: minimum bumper gap from the reference point on; margin = min(min_gap, 10 m) − 1.0 m; pass if ≥ 0.

## 1. Realisation (`broken.json`, `reference_summary.json`)

- All 10 broken scenarios (the demo's 9 plus "cutter 1 m/s slower than designed") were caught; the clean run was realised. The R157 gates `ttc_li_realised`, `visibility` and `cut_speed_lc` fired on 7 of them.
- Reference: 19,056 applicable grid points run, **18,318 realised**. All 738 not realised (3.9 %) failed one gate, `dynamics_valid_to_kpi`: the ACC dropped its speed in one step beyond its 6 m/s² limit before its closest approach (the demo's known over-braking artefact).

## 2. Reference: where the rule is met (`reference_grid.npz`, `reference_summary.json`)

| Criterion | Share of realised applicable region failing | Collisions |
|---|---|---|
| R157 as written: no collision | **0 %** | 0 of 18,318 |
| With the stated 1.0 m margin | **1.50 %** (275 points) | — |
| Secondary: the 738 over-braking runs counted as failures | 5.32 % | — |

Failing points lie at v_rel 0.5–1.5 m/s and nominal TTC_LaneIntrusion 0.50–1.60 s, across all ego speeds; the smallest margin is −0.212 m (min gap 0.79 m). Faster cut-ins are handled with room to spare. Figure: `fig_region_map.png` (54 km/h slice).

## 3. Comparison at equal budgets (`metrics.csv`, `summary.json`)

**H0, the control (reported first).** The constant predictor "everything passes" misclassifies 1.50 % of the region. All three arms are below it at every scored budget (`fig_misclass_vs_budget.png`).

**Misclassified share of the applicable region** (median over 10 seeds):

| Runs | GP-AL | Sobol + GP | Random + GP | Constant |
|---|---|---|---|---|
| 100 | 0.060 % | 0.431 % | 0.401 % | 1.50 % |
| 200 | 0.049 % | 0.227 % | 0.281 % | 1.50 % |
| 300 | 0.049 % | 0.147 % | 0.186 % | 1.50 % |

**Planned tests (H1, H2).** One-sided Wilcoxon signed-rank on 10 paired seeds, Holm over 6 tests: every test p_holm = 0.0059, 10 of 10 wins, median ratio GP-AL/baseline 0.13, 0.20, 0.31 against Sobol and 0.13, 0.19, 0.22 against random. All six pass: **GP-AL helps at every budget against both baselines.**

**Recall of the violating region (H3)** (median): GP-AL 0.98 / 0.99 / 0.99 at 100 / 200 / 300 runs; Sobol 0.72 / 0.86 / 0.91; random 0.77 / 0.84 / 0.90. H3 (≥ 0.9 at 300) holds for GP-AL, and also, narrowly, for the baselines at 300.

**Runs needed** (median over seeds of the first scored budget): misclassification ≤ 0.5 %: GP-AL 60, Sobol 80, random 80. ≤ 0.2 %: GP-AL 70, Sobol 180, random 240 (2 of 10 random seeds never reached it by 300).

## 4. Calibration of the band (H4) (`summary.json`, `calibration`)

Share of the 45 reference boundary points inside the band at 300 runs (mean over seeds, range):

| Stated | GP-AL | Sobol + GP | Random + GP |
|---|---|---|---|
| 50 % | 61.3 % (55.6–66.7) | 100 % | 99.8 % |
| 80 % | 85.8 % | 100 % | 100 % |
| 90 % | 92.2 % | 100 % | 100 % |
| 95 % | **96.9 %** (93.3–100) | 100 % | 100 % |
| 99 % | 99.3 % | 100 % | 100 % |

By the plan's rule GP-AL is **calibrated at 95 %**; Sobol and random are **conservative** (> 0.99): their bands near this small pocket are wide. Only 45 boundary points exist on the grid (the pocket is small), so containment moves in steps of 2.2 points.

## 5. Compliance report and hold-out (H5) (`compliance.json`)

GP-AL seed 0, 300 runs, thresholds 0.95 / 0.05, shares of the realised applicable region:

| Criterion | Compliant | Violating | Undecided | Check against the grid |
|---|---|---|---|---|
| 1.0 m margin | **98.3 %** | **1.4 %** | **0.3 %** | compliant truly pass 100 %; violating truly fail 99.6 %; undecided 50 % fail |
| No collision (R157 as written; secondary) | 100 % | 0 % | 0 % | 0 collisions on the grid |

**Hold-out check runs:** 200 fresh uniform applicable runs (never used for fitting), 197 realised. 196 fell in the compliant region and **none failed** (one-sided 95 % upper bound on the wrong-call rate 1.5 %); 1 fell in the violating region and failed. H5 holds. Coverage sentence: *"Within the applicable conditions of R157 para. 5.2.5.2 and the stated ranges, esmini's ACC avoided collision in every run, and kept at least 1.0 m in 98.3 % of the region with ≥ 95 % confidence; it violated the 1.0 m margin in 1.4 %, undecided in 0.3 %."* Manifest `manifests/gp_al_0.json`, sha256 `bcc54d07…`.

## 6. Replication (H6) (`replication.json`)

The 50 runs closest to the threshold (5 per GP-AL campaign) were rerun 5 times each, the last with esmini seed 987: **all 250 bitwise identical** (largest margin difference 0.0), all verdicts identical.

## 7. Nominal vs actual TTC_LaneIntrusion (secondary, from the run records)

The ACC was already braking at the reference point in 58.6 % of realised runs (it reacts while the cutter is still beside it). The actual TTC there exceeded the nominal one by a median of 0.36 s (90th percentile 3.15 s). So a compliant verdict "at nominal TTC_LaneIntrusion 1.0 s" includes the system's early reaction, which the rule allows. The scenario's criticality is set by the cutter's manoeuvre.

## Post hoc (after the plan)

- **Not-realised share by arm** (from `campaign_runs.csv`): GP-AL 26.6 %, Sobol 2.6 %, random 2.5 %. Straddle sends runs to the boundary, and that is where the ACC over-brakes. The budget comparison counts those runs, so GP-AL won despite losing about a quarter of its runs. A search on this system should handle unrealised runs, for example by excluding their neighbourhood from the pool.
- The region-map figure was redrawn at a finer grid before publication; no number changed.

## Limits

- **System and simulator.** esmini's ACC, not an ALKS; no sensors, so "visible" is geometric. The boundary is a property of this controller in esmini; the over-braking artefact removes 3.9 % of the region from any verdict, exactly near the boundary.
- **Rule coverage.** Only para. 5.2.5.2 of the 2021 text (Add.156), read as stated in the test design: nominal TTC_LaneIntrusion, longitudinal v_rel, the 0.30 m/s sag reading of condition (a), assumed tyre width. Not covered: different lateral velocities and accelerations, accelerating or decelerating cutters, two-wheelers, the competent-driver level outside (a)–(c), no-deactivation (5.2.5.4), harsh braking (5.2.3.3) and Emergency Manoeuvre (5.3.1.1).
- **The 1.0 m margin is our choice.** By R157 as written the system complies everywhere tested.
- **Scale.** One seed for the compliance report; 45 boundary points for calibration; a deterministic system, so the band contains no run-to-run spread. No clean-clone rerun from a manifest was done this time (the demo did one).

## Reproduce

```bash
PYTHONPATH=src .venv/bin/python -m stp.r157.experiment all 4     # broken, reference (~6 min), campaigns, score, compliance, replicate
PYTHONPATH=src .venv/bin/python -m stp.r157.plots
.venv/bin/python -m pytest tests/test_r157.py
```
