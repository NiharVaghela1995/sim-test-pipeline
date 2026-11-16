# R157 rule on the GP boundary demo: plan (2026-11-16)

Written and committed before the reference grid, the campaigns, the hold-out runs and the replication were run. Anything decided after this commit is labelled **post hoc** in the report. Test design: `docs/R157_TEST_DESIGN.md`. Code: `src/stp/r157/`.

**Question.** Replace the demo's placeholder rule (min TTC ≥ 1.5 s) with UN R157's cut-in requirement (para. 5.2.5.2: no collision under conditions (a)–(c)) plus a stated 1.0 m safety margin. Inside the region where the paragraph applies: where does esmini's ACC meet the rule, does GP active learning find the pass/fail boundary with fewer runs than Sobol and random designs, is its band honest, and does a three-region compliance statement survive hold-out check runs?

## Setup

As in the GP demo (`docs/GP_BOUNDARY_PLAN.md`): esmini 3.11.0 pinned by sha256, step 0.02 s, 15 s per run; esmini's `ACCController` on the ego (time gap 1.5 s, maximum deceleration 6 m/s², set speed = ego speed, longitudinal only); scripted cutter, 3 s sinusoidal lane change from 2.0 s. New: parameters (ego speed 10–16.667 m/s, v_rel 0.5–8 m/s, TTC_LaneIntrusion 0.2–3.0 s), cutter speed ≥ 6 m/s, the applicability region of para. 5.2.5.2, the KPI (min bumper gap from the reference point), margin = min(min_gap, 10 m) − 1.0 m.

## Pilot, before this plan (declared)

500 runs from seeds 424242 and 777, not reused anywhere, plus a rerun of the 300 with seed 777 after the independent review. They fixed: (1) the cutter's longitudinal sag in esmini's path-speed lane change, hence the ODD constraint cutter speed ≥ 6 m/s, the 0.30 m/s reading of condition (a) and TTC_LaneIntrusion computed with the longitudinal relative speed; (2) the KPI window: the first pilot measured the gap only while the bodies overlap laterally and missed that esmini's ACC reacts, and sometimes over-brakes, while the cutter is still 2.7–2.95 m to the side; the KPI now starts at the R157 reference point. The 1.0 m margin was chosen before the pilots. (3) After the independent review (end of the test design): the yaw-aware reference point with the 0.12 m marking, and nominal vs actual TTC_LaneIntrusion. Pilot outcome after that, 300 applicable points: 96.7 % realised (10 runs over-braked before the KPI minimum), **1.4 % fail**, smallest margin −0.15 m, no collision, 4 % at the 10 m cap. So the violating region is expected to be small.

## Steps

1. **Broken scenarios.** The demo's 9 broken scenarios plus "cutter 1 m/s slower than designed", run through the R157 runner at one applicable point; all must be not realised, the clean run realised.
2. **Reference.** Grid: ego speed 10, 10.5, …, 16.5, 16.667 m/s (15); v_rel 0.5–8 step 0.5 (16); TTC_LaneIntrusion 0.2–3.0 step 0.025 (113); 27,120 points, of which the 19,056 applicable ones are run once. Truth at a point = sign of its margin. Points not realised are reported and left out of all metrics.
3. **Campaigns.** Arms GP-AL, Sobol, random; seeds 0–9; budget 300; scored at 40, 60, …, 300 runs.
   - Sobol: the first n applicable points of the scrambled Sobol sequence of seed i (rejection from 8,192). GP-AL: the same first 30, then batches of 10 by straddle (1.96·σ − |μ|) from a fresh pool of 4,096 Sobol points restricted to the applicable region, minimum distance 0.05. Random: first n applicable uniform points.
   - The GP is the demo's, unchanged (`cutin/gp.py`: constant × Matérn 5/2 ARD, white noise, normalize_y, 5 seeded restarts), fitted to realised runs in the unit cube of (ego speed, v_rel, TTC_LaneIntrusion).
4. **Scoring** against the reference, on realised applicable grid points: misclassification share (primary); recall of the violating region (share of truly violating grid points predicted violating); calibration at 300 runs at stated levels 50/80/90/95/99 % on reference boundary points (sign changes along TTC_LaneIntrusion lines); runs needed to reach misclassification ≤ 0.5 % and ≤ 0.2 %.
5. **Compliance report** for GP-AL seed 0 at 300 runs: P(rule met) = Φ(μ/σ); compliant P ≥ 0.95, violating P ≤ 0.05, undecided otherwise; shares of the applicable region; check against the grid. **Hold-out:** 200 fresh uniform applicable runs (seed derived from "holdout"), never used for fitting, compared with the regions; one-sided 95 % Clopper–Pearson bound on the wrong-call rate per region.
6. **Replication.** The 5 runs with smallest |margin| from each GP-AL campaign (50 points) rerun 5 times, the last with esmini seed 987.
7. **Manifests** per campaign (settings, environment, code commit, every run, prediction hash).

## Hypotheses and decision rules, fixed now

- **H0 (control, new).** Because the violating region is small, the constant predictor "everything passes" already has a low misclassification (about the fail share). A GP arm **beats the control** at a budget only if its median misclassification over seeds is below the constant predictor's. Reported first.
- **H1/H2.** GP-AL has lower misclassification than Sobol (H1) and random (H2) at 100, 200, 300 runs. Same rule as the demo: one-sided Wilcoxon signed-rank on the 10 paired seeds, Holm over the 6 tests, α = 0.05; **helps** only if significant, ≥ 8 of 10 wins and median ratio ≤ 0.8. If Sobol passes the reverse test at a budget, GP-AL is **worse** there.
- **H3.** GP-AL's violating-region recall at 300 runs is ≥ 0.9 (median over seeds). Expected to be at risk: the region is small.
- **H4.** GP-AL's band at 300 runs contains the reference boundary at its stated 95 %: mean containment < 0.90 overconfident, > 0.99 conservative, else calibrated.
- **H5.** Hold-out: no compliant-region hold-out run fails; report the bound whatever happens.
- **H6.** Replicates are bitwise identical (as in the demo).

**Secondary (reported, no decision):** nominal vs actual TTC_LaneIntrusion at the reference point (how early the ACC reacts); the pure R157 criterion (no collision, d = 0) from the same runs: P(min_gap ≥ 0) = Φ((μ + 1.0)/σ); the share of runs not realised because of over-braking, and the fail share if they were counted as failures.

## Stated limits, in advance

One controller, one scenario family, no sensors; a 3 s lane change only; R157's 2021 text only; the 1.0 m margin is a choice. Results describe esmini's ACC under this test design, not an ALKS.
