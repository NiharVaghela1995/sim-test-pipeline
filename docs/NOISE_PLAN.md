# Noisy SUT on the R157 cut-in: plan (2026-11-17)

Written and committed **before** the reference grid, the campaigns, the boundary replication and the rerun analysis were run. Anything decided after this commit is labelled **post hoc** in the report. Code: `src/stp/noise/`, tests `tests/test_noise.py`. Builds on the R157 study (`docs/R157_TEST_DESIGN.md`, `docs/R157_PLAN.md`, `docs/R157_REPORT.md`), whose system was deterministic (250 of 250 reruns bitwise identical).

**Question.** Put perception noise on the cut-in vehicle's position and speed and a small actuation delay between the world and esmini's ACC, at three levels. Then the verdict at a point is random. The target becomes the failure region {x : p(x) ≥ α}, with p(x) the probability that a realised run at x violates the R157 rule plus the 1.0 m margin. At equal budget and over 10 seeds, does a **heteroskedastic GP** find that region better than a **homoscedastic GP** with active learning, and better than Sobol and random designs? Is its band honest? How large is the no-verdict share? How many reruns does a verdict need at each level?

## Why a port of the ACC, and the check that it is exact

esmini's `ACCController` reads ground truth inside C++, so it cannot be given perception noise or a delay. `src/stp/noise/acc.py` ports it line by line from the v3.11.0 source (`EnvironmentSimulator/Modules/Controllers/ControllerACC.cpp`, and the free-space distance from `Entities.cpp`, both read at tag v3.11.0). esmini still runs the road, the scripted cutter and the realisation trace. The ego is moved through esmini's `ExternalController`, and the step order matches esmini's own ACC (the controller sees the cutter after the cutter has moved in the step). Two findings during porting, now handled: (1) the step order (first attempt: braking one step late); (2) on the lane line itself esmini still reports the outer lane, so the port uses a 1e-9 m tie tolerance.

**Known answer, before this plan (declared):** with noise and delay off, the port reproduced esmini's ACC on 300 random stored R157 reference runs: largest speed difference 8e-9 m/s, minimum gaps equal to 1e-6 m. **Step 0 of the run (`portcheck`)** repeats this on 500 seeded stored reference runs. It must give identical realisation and |Δ margin| ≤ 1e-3 m on all 500, or the study stops.

## Noise model and levels (fixed now)

- **Perception (cutter only):** errors on the cutter's longitudinal position x, lateral position y and path speed, as the controller sees them. Each error is a stationary AR(1) process with correlation time τ = 0.5 s (ρ = exp(−0.02/0.5) per step): a tracker-like slowly varying error, not white noise that the controller would average away. The ego's own speed and both headings are exact. Lateral error changes which lane the controller places the cutter in and its free-space "really close" check, so it shifts the reaction time.
- **Actuation delay:** the commanded speed reaches the vehicle after a pure transport delay (FIFO of steps). The controller's internal state is its command, as in esmini.
- **Seeds:** each run's noise comes from numpy PCG64 seeded with a SHA-256 of (level, step, design index, run order). A run is fixed by (x, level, seed). esmini itself stays deterministic.

| Level | σ_x (m) | σ_y (m) | σ_v (m/s) | delay (s) |
|---|---|---|---|---|
| low | 0.2 | 0.1 | 0.1 | 0.1 |
| mid | 0.5 | 0.2 | 0.3 | 0.2 |
| high | 1.0 | 0.3 | 0.6 | 0.3 |

These values are **design choices** of radar/camera-tracker order of magnitude, not taken from a sensor datasheet. Noise and delay rise together, so a level's effect cannot be attributed to either one alone.

**Realisation.** All 16 gates of the R157 runner, unchanged except `controllers`, which now expects `ExternalController` on the ego. A run failing any gate gets no verdict. Under noise, two ego-side gates can fire because of the SUT's own noisy behaviour rather than a broken scenario: `dynamics_valid_to_kpi` (the ACC's instant stop when the perceived gap is below 1 m, before the KPI minimum) and `ego_cruise_before_cut` (braking before the lane change on a perceived cutter). They are kept as they are. Their share is the **no-verdict share**, reported per gate.

**Pilot, before this plan (declared):** 48 points (30 uniform applicable plus 18 in and near the deterministic failing pocket), 12 runs each per level, noise seeds 1,000,000+, never reused. The levels above were the candidates going in and were kept. Per-point margin SD (10th/50th/90th percentile): low 0.05/0.11/0.29 m, mid 0.10/0.25/0.59 m, high 0.12/0.43/0.83 m, so the noise is clearly input-dependent. No-verdict share 11.5 / 7.3 / 7.8 %, mostly over-braking; at high, 3 % also came from `ego_cruise_before_cut`. No collisions. **Smoke test (declared):** the whole pipeline at toy scale (level mid, 227 grid points, budget 60, 3 seeds), output to a scratch directory, not reused.

## Target and reference

- **α = 0.10.** p(x) = P(margin < 0 | x, run realised), where margin = min(min_gap, 10 m) − 1.0 m as in R157. Target region T = {x : p(x) ≥ 0.10}. Runs are drawn only where R157 para. 5.2.5.2 applies (`r157/design.applicable`).
- **Grid:** ego speed 10, 11.67, 13.33, 15, 16.67 m/s (5; the deterministic boundary barely moves with ego speed); v_rel 0.5–3.0 step 0.25, then 3.5–8.0 step 0.5 (21); TTC_LaneIntrusion 0.2–3.0 step 0.05 (57). 4,327 applicable points.
- **Two stages per level:** 10 runs at every applicable point. Then the point is topped up to 40 runs if, in stage 1, it or a neighbour had a failing realised run (neighbours: ±3 TTC steps on its line, ±1 step on the v_rel and ego axes), or if it had fewer than 5 realised runs. A point with 0 of 10 failing and no failing neighbour gets p̂ = 0. That is a stated approximation.
- **Truth:** p̂ = fails / realised. Smoothed by isotonic regression (non-increasing in TTC along each (ego, v_rel) line, weighted by realised runs), because at zero noise all 204 R157 lines had a single crossing. The raw multi-crossing count is reported as a check. A grid point carries a truth label if it has ≥ 5 realised runs; label "in T" if p_iso ≥ 0.10.
- **Reference boundary points:** crossings of p_iso = 0.10 between neighbouring labelled points along TTC lines, interpolated linearly.

## Arms and models (10 seeds, budget 300, scored at 40, 60, …, 300 runs)

| Arm | Design | Model |
|---|---|---|
| `hom_al` | first 30 applicable points of scrambled Sobol (seed i), then batches of 10 new points by straddle | homoscedastic GP |
| `het_al` | first 15 applicable Sobol points (same stream) × 2 runs, then batches of 5 new points × 2 runs by straddle | heteroskedastic GP |
| `sobol` | first 300 applicable Sobol points, one run each | homoscedastic GP |
| `random` | first 300 applicable uniform points | homoscedastic GP |

- **Homoscedastic GP:** the demo's (constant × Matérn 5/2 ARD + white noise, 5 seeded restarts, y standardised), with the white-noise upper bound raised from 1e-1 to 1.0 (standardised units), so one noise variance r is fitted for the whole box.
- **Heteroskedastic GP (two-stage, stochastic-kriging style; Ankenman et al. 2010, Binois et al. 2018 without the joint likelihood):** replicates pooled per input (mean, sample variance); a GP on the bias-corrected log sample variance, with its known sampling variance ψ′((n−1)/2) on the diagonal, gives r(x); a GP on the means with r(x_i)/n_i on the diagonal gives m(x). Falls back to the homoscedastic GP with fewer than 5 replicated inputs.
- **Classification:** with latent mean μ(x), its sd s(x) and noise variance r(x): g(x) = μ − z_{0.90}·√r, predicted in T if g ≤ 0 (equivalently Φ(−μ/√r) ≥ α). **Straddle** = 1.96·s − |g|. Pool: 4,096 fresh Sobol points per batch, restricted to the applicable region, minimum distance 0.05 (the R157 rule). Only realised runs are fitted.
- **Secondary model swap:** the homoscedastic GP refitted on `het_al`'s runs, which separates the replicated design from the model.

## Metrics (on labelled grid points)

1. **Misclassification share** of T (primary). Also by tercile of the reference margin SD (low / mid / high noise), to say *where* a model helps.
2. **Boundary error:** per (ego, v_rel) line, the end of the failure region in TTC (midpoint after the last failing grid point; the line's first TTC minus 0.025 s if none fails). Mean |model − reference| in seconds over lines where either side has a failing point.
3. Recall and precision of T.
4. **Calibration of the band at 300 runs:** share of reference boundary points with |g| ≤ z·s at stated 50/80/90/95/99 %. The noise variance is plugged in, so the band covers the latent mean only.
5. **No-verdict share:** share of an arm's runs not realised, at every scored budget (monitored).
6. **Control:** the constant predictor "nothing is in T", whose misclassification is the share of T.

## Hypotheses and decision rules, fixed now

- **H0 (reported first).** An arm beats the control at a budget only if its median misclassification is below the share of T.
- **H1 (primary).** `het_al` has lower misclassification than `hom_al` at 100, 200 and 300 runs, at each level: 9 one-sided Wilcoxon signed-rank tests on the 10 paired seeds, Holm over the 9, α = 0.05. **Helps** only if p_holm < 0.05, ≥ 8 of 10 wins and median ratio ≤ 0.8. **Worse** if the reverse test passes with ≥ 8 losses and median ratio ≥ 1.25. Otherwise **no difference shown**. Expectation, not a rule: help grows with the noise level.
- **H2 (secondary).** `het_al` and `hom_al` against `sobol` and `random`: 36 tests (2 × 2 × 3 budgets × 3 levels), same rule, Holm over the 36.
- **Secondary, same rule and own Holm families:** boundary error of `het_al` against `hom_al` (9 tests); the model swap (`het_al` with its own model against `het_al` refitted with the homoscedastic GP, 9 tests).
- **H3.** At 300 runs, `het_al`'s band contains the reference boundary at its stated 95 %: mean containment < 0.90 overconfident, > 0.99 conservative, else calibrated. Expectation: `hom_al` is miscalibrated, because one r cannot fit both the low-noise boundary and the noisier rest.
- **H4 (replicate boundary points to estimate p(x)).** For every campaign at 300 runs: 5 points on its predicted boundary (smallest |g| in a fresh 8,192-point applicable Sobol pool, ≥ 0.1 apart in the unit cube), 20 runs each. Pooled over the 10 seeds, the empirical p at an arm's predicted boundary should be in [0.05, 0.20] ("on target"); reported with a Wilson 95 % interval.
- **Monitored.** No-verdict share per arm, level and budget. A comparison is **flagged** if the two arms' median no-verdict shares differ by more than 10 percentage points. The budget counts unrealised runs, as in R157.

## Reruns a verdict needs (descriptive, per level)

For every labelled reference point, with its own p̂ and no-verdict probability q̂:
- **Binary rule:** Wald SPRT on pass/fail, H0: p ≤ 0.05 against H1: p ≥ 0.20 (indifference zone around α), both error rates 0.05, at most 200 realised runs, simulated 100 times per point. Even at p = 0 a "below α" verdict needs ⌈log(19)/−log(0.8/0.95)⌉ = 18 realised runs.
- **Margin rule (uses the size of the margin, assumes it is Gaussian at a point):** after n ≥ 2 realised runs, one-sided 95 % confidence bounds on the 10 % quantile of the margin, ȳ − k·s, with k from the noncentral t. Below α (pass) when the lower bound is > 0, at or above α (fail) when the upper bound is < 0, at most 100 runs. Runs are bootstrap draws from the point's stored realised margins, 200 sequences per point.
- Reported by band of the reference p (0; (0, 0.05); [0.05, 0.2); [0.2, 0.5); ≥ 0.5): median and 90th percentile of attempts (realised plus unrealised runs), the share undecided at the cap, and the share deciding "fail". The deterministic R157 case needs one run per verdict.

## Steps

0. `portcheck` (above; stop if it fails). 1. `broken`: the 10 broken scenarios of R157 through the noisy runner at level mid; all must be not realised, and 5 clean runs realised. 2. `reference`. 3. `campaigns`. 4. `score`. 5. `replicate`. 6. `reruns`. 7. Manifests per campaign (level, settings, environment, code commit, every run with its seed).

## Stated limits, in advance

One controller (a port of esmini's ACC, exact without noise), one scenario family, a synthetic noise model with no sensor physics, noise only on the cutter, noise and delay varied together. The heteroskedastic GP is a two-stage approximation, not Binois et al.'s joint maximum likelihood (the R hetGP package is not run). The target uses p conditional on a realised run, so no-verdict runs are left out of p and reported separately. The reference is itself an estimate (10–40 runs per point, isotonic smoothing). α = 0.10 is a choice.

```bash
PYTHONPATH=src .venv/bin/python -m stp.noise.experiment all 4
.venv/bin/python -m pytest tests/test_noise.py
```
