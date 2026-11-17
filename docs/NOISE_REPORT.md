# Noisy SUT on the R157 cut-in: report (2026-11-17)

**Result.** With perception noise on the cutter and an actuation delay on esmini's ACC (ported to Python, exact without noise), the target becomes the failure region {x : p(x) ≥ 0.10}. That region covers 7.7 % / 13.1 % / 19.8 % of the applicable R157 region at the low / mid / high level, against 1.5 % failing without noise (`docs/R157_REPORT.md`). By the rule fixed in the plan, the **heteroskedastic GP helps at mid and high noise from 200 runs on**: 10 of 10 paired seeds, Holm-corrected p = 0.0088, misclassification 0.64–0.67 times the homoscedastic GP's at mid and 0.40–0.45 times at high. It **shows no difference at 100 runs at any level, and none at low noise** at any budget. It helps for a specific reason. A homoscedastic GP fits one noise level for the whole box, too large where the boundary is (slow cut-ins, where runs vary little). So it pushes the predicted region outwards, and its errors concentrate in the low-noise part of the region. No model's band is calibrated: all are overconfident at a stated 95 %. The heteroskedastic GP covers 66–72 %, the best of the two active-learning arms at every level, but Sobol and random cover more at low and mid. A verdict at one point needs 18 runs with a pass/fail SPRT even where nothing ever fails, about 37 near α, and 2–3 with a rule that uses the size of the margin where the margin is clear. The deterministic system needed 1.

Plan: `docs/NOISE_PLAN.md`, committed and pushed in `51bba8f` before the reference, campaigns, boundary replication and rerun analysis ran. Anything decided after that commit is marked **post hoc**. Every number below comes from a file in `results/noise/`, named in each section. Code: `src/stp/noise/`.

## Setup (as planned)

- **SUT.** esmini 3.11.0 runs the road, the scripted cutter and the trace. The ego is driven by a line-by-line Python port of esmini's `ACCController` (v3.11.0 source) through esmini's `ExternalController`. Noise sits between world and controller: AR(1) errors (τ = 0.5 s) on the cutter's longitudinal position, lateral position and speed, plus a pure transport delay on the commanded speed.
- **Levels** (σ_x m / σ_y m / σ_v m/s / delay s): low 0.2/0.1/0.1/0.1, mid 0.5/0.2/0.3/0.2, high 1.0/0.3/0.6/0.3. Noise and delay rise together.
- **Rule and KPI as in R157:** margin = min(min_gap, 10 m) − 1.0 m; p(x) = P(margin < 0 | realised run). α = 0.10. Runs only where R157 para. 5.2.5.2 applies.
- **Arms**, 10 seeds, 300 runs: `hom_al` (homoscedastic GP, 10 new points per batch), `het_al` (heteroskedastic GP, 5 new points × 2 runs per batch), `sobol` and `random` (homoscedastic GP). Straddle on g = μ − 1.28·√r.

## 0. The port and the realisation check (`portcheck.json`, `broken.json`)

- **Port check (step 0):** with noise off, 500 seeded stored R157 reference runs rerun through the port. All 500 had the same realisation outcome, the largest margin difference was 1.6e-8 m, and all 486 verdicts were identical. Passed.
- **Broken scenarios:** all 10 (the R157 set) caught at level mid; 5 of 5 clean runs realised.

## 1. Reference: what the noise does (`reference_summary.json`, `reference_{level}.npz`, `fig_reference_maps.png`)

4,327 applicable grid points per level, 10 runs each, topped up to 40 at 579 / 895 / 1,390 points near failures: 60,640 / 70,120 / 84,970 runs.

| | low | mid | high |
|---|---|---|---|
| Target share {p ≥ 0.10} | **7.7 %** | **13.1 %** | **19.8 %** |
| Share with p ≥ 0.5 | 6.2 % | 9.1 % | 11.2 % |
| Largest v_rel in the target | 2.75 m/s | 5.0 m/s | 8.0 m/s |
| Margin SD per point, 10/50/90 % | 0.05 / 0.13 / 0.26 m | 0.10 / 0.27 / 0.54 m | 0.15 / 0.42 / 0.80 m |
| Collisions (runs / grid points) | 0 / 0 | 79 / 53 | 592 / 284 |
| **No-verdict share** of runs | **11.6 %** | **5.5 %** | **4.1 %** |
| Grid points without truth (< 5 realised) | 56 | 0 | 0 |
| Lines with > 1 raw crossing of α (before isotonic smoothing) | 0 | 0 | 15 |
| Reference boundary points | 42 | 65 | 90 |

- The noise is **heteroskedastic in a structured way**: the margin varies little at slow cut-ins (v_rel ≤ 1 m/s, where the deterministic boundary lies) and much more at fast ones (lower panels of the map figure). As noise grows, the region grows from the slow-cut-in pocket towards faster cut-ins at nominal TTC_LaneIntrusion 0.7–1.0 s.
- **Collisions appear** at mid and high, so with perception noise the system no longer meets R157's own no-collision criterion everywhere in the applicable region; without noise it never collided (R157 report).
- **No-verdict runs** are almost all `dynamics_valid_to_kpi`: the ACC's instant stop when the perceived gap drops below 1 m, before the KPI minimum (7,054 / 3,841 / 3,170 runs). At high, 363 runs (0.4 %) were also lost to `ego_cruise_before_cut`: phantom braking on a mis-perceived cutter before the lane change. The share *falls* with noise. Why was not investigated (post hoc observation).

## 2. Comparison at equal budget (`metrics.csv`, `summary.json`, `fig_misclass_vs_budget.png`, `fig_boundary_err.png`)

**H0, the control.** Every arm is below the constant predictor ("nothing in the region": 7.7 / 13.1 / 19.8 %) at every budget and level.

**Misclassified share of the applicable region** (median over 10 seeds):

| Level | Runs | het-GP AL | hom-GP AL | Sobol + hom-GP | random + hom-GP |
|---|---|---|---|---|---|
| low | 100 | 0.84 % | 0.71 % | 2.27 % | 2.56 % |
| | 300 | **0.52 %** | 0.62 % | 2.69 % | 2.63 % |
| mid | 100 | 1.96 % | 2.57 % | 5.25 % | 4.47 % |
| | 200 | **1.47 %** | 2.42 % | 5.66 % | 5.23 % |
| | 300 | **1.43 %** | 2.33 % | 5.49 % | 5.40 % |
| high | 100 | 5.17 % | 7.34 % | 7.78 % | 8.78 % |
| | 200 | **3.50 %** | 8.23 % | 8.63 % | 8.71 % |
| | 300 | **3.07 %** | 7.71 % | 8.64 % | 9.83 % |

**H1 (primary): heteroskedastic against homoscedastic GP-AL** (one-sided Wilcoxon on 10 paired seeds, Holm over 9 tests):

| Level | 100 runs | 200 runs | 300 runs |
|---|---|---|---|
| low | no difference (4 wins, ratio 1.23, p_holm 0.81) | no difference (6, 0.89, 0.56) | no difference (7, 0.85, 0.093) |
| mid | no difference (7, 0.79, 0.26) | **helps** (10, 0.67, 0.0088) | **helps** (10, 0.64, 0.0088) |
| high | no difference (6, 0.74, 0.56) | **helps** (10, 0.45, 0.0088) | **helps** (10, 0.40, 0.0088) |

No test found the heteroskedastic GP worse. **Boundary error** (secondary, same rule): the same pattern, helps at mid and high at 200 and 300 runs (10 of 10, p_holm 0.0088). At 300 runs: 0.046 against 0.078 s of TTC at mid, 0.074 against 0.185 s at high; at low, 0.026 against 0.032 s, not significant.

**H2 (secondary, Holm over 36):** both active-learning arms help against Sobol and random at low and mid at every budget (median ratios 0.18–0.58). At high, the **heteroskedastic arm helps at 200 and 300 runs** (ratios 0.31–0.42) but not at 100. The **homoscedastic arm does not meet the rule for helps at any budget** at high (no difference shown; median ratios 0.83–0.96). At 300 runs it wins 10 of 10 seeds against Sobol (p_holm 0.035) but fails the ratio criterion (0.88). Sobol and random do not improve between 100 and 300 runs at any level (curves flat). Interpretation, post hoc: their error is bias of the homoscedastic model, not lack of data.

**Where the heteroskedastic GP helps and where it doesn't** (misclassification at 300 runs by tercile of the reference margin SD; `misclass_sd_*` in `metrics.csv`):

| Level | Arm | low-noise third | middle third | high-noise third | precision | recall |
|---|---|---|---|---|---|---|
| low | het / hom AL | 1.05 / 1.47 % | 0.56 / 0.35 % | 0.07 / 0.07 % | 0.97 / 0.94 | 0.97 / 0.98 |
| mid | het / hom AL | 1.87 / 4.44 % | 1.60 / 2.01 % | 0.76 / 0.83 % | 0.93 / 0.89 | 0.96 / 0.93 |
| high | het / hom AL | **3.47 / 14.97 %** | 2.25 / 2.77 % | 2.95 / 5.41 % | **0.92 / 0.75** | 0.95 / 0.90 |

- **Helps:** in the low-noise part of the region, where the boundary is, and increasingly with the noise level. The mechanism: the region's edge is μ = 1.28·√r. A homoscedastic GP fits one √r for the whole box, 0.49 m for hom-GP AL and 0.60 m for Sobol at high (median over seeds, `r_median`). The true SD near the slow-cut-in boundary is 0.1–0.2 m. Too large an r moves the edge outwards: the region is over-drawn (precision 0.75) and the errors pile up where the system is quiet. Post hoc interpretation: this is the opposite of the failure mode Module 14 predicted (a band "too narrow where the system is noisiest"). Here a constant noise level made the region too *wide* where the system is least noisy.
- **Doesn't help:** at low noise, where one r is nearly right (0.08 m against a median per-point SD of 0.13 m), and at 100 runs at every level, when 50 replicated pairs are too few to learn the noise surface. Its own price is its design: 2 runs per point give 150 distinct points instead of 300.
- **Model, not design (secondary model swap, `model_only`):** refitting `het_al`'s own runs with the homoscedastic GP is worse than the heteroskedastic model in all 9 tests (helps, 9 or 10 wins, ratios 0.29–0.68). Even at low noise the heteroskedastic model is the better reader of replicated data. Descriptive, no planned test: paired runs fitted with a homoscedastic GP are *worse* than hom-GP AL's single runs at mid and high (median 4.17 % against 2.33 %, 10.42 % against 7.71 % at 300). Replication alone did not help here; it helped together with a noise model.

## 3. Calibration of the band (H3) (`summary.json`, `calibration`)

Share of reference boundary points with |g| ≤ 1.96·s at 300 runs (mean over seeds, range):

| Level | het-GP AL | hom-GP AL | Sobol | random |
|---|---|---|---|---|
| low (42 points) | 67.1 % (50.0–78.6) | 64.8 % (52.4–90.5) | 89.5 % | 89.0 % |
| mid (65) | 65.8 % (44.6–86.2) | 48.2 % (33.8–60.0) | 70.3 % | 69.4 % |
| high (90) | **72.4 %** (54.4–82.2) | 42.0 % (30.0–53.3) | 52.3 % | 55.0 % |

By the plan's rule **every arm is overconfident at every level; H3 fails** for the heteroskedastic GP as well. It covers more than hom-GP AL at every level, and its coverage does not fall as noise rises, while hom-GP AL's falls from 65 % to 42 %. Among all four arms it is closest to 95 % only at high. At low and mid, Sobol and random cover more (89–90 % and 69–70 %), because their boundary sits on the safe side with wider bands (section 4). Possible reasons, **post hoc and untested**: the band covers only the latent mean, with the noise variance plugged in and its uncertainty ignored; and the reference boundary is itself estimated from 10–40 runs per point, so part of the "miss" may be the reference's own error. Until a check separates these, the band must not be read as a 95 % statement under noise.

## 4. Replicating predicted boundary points to estimate p(x) (H4) (`boundary_reps.json`)

5 points on each campaign's predicted boundary (300 runs), 20 runs each; empirical p pooled over the 10 seeds (Wilson 95 %); target α = 0.10, "on target" if within [0.05, 0.20]:

| Level | het-GP AL | hom-GP AL | Sobol | random |
|---|---|---|---|---|
| low | **0.109** (0.091–0.131) | 0.099 (0.082–0.119) | 0.005 ✗ | 0.008 ✗ |
| mid | **0.081** (0.066–0.100) | 0.074 (0.060–0.093) | 0.028 ✗ | 0.018 ✗ |
| high | **0.104** (0.087–0.125) | 0.057 (0.044–0.074) | 0.057 | 0.058 |

Both active-learning arms put their boundary where p is near α. The homoscedastic arm drifts to the safe side as noise grows (0.099 → 0.057), as the mechanism above predicts. Sobol and random draw their boundary far on the safe side at low and mid: where they say "p = 0.10", the system fails 0.5–3 % of the time.

## 5. No-verdict share (monitored) (`fig_no_verdict.png`)

Median share of an arm's runs not realised, at 300 runs: low 8.3 % (het) / 10.7 % (hom AL) / 2.0 % (Sobol) / 2.0 % (random); mid 2.2 / 3.8 / 0.8 / 1.2 %; high 1.5 / 2.5 / 1.3 / 1.7 %. As in R157, active learning sends runs to the boundary, where the ACC's instant stop clusters. **Flagged by the plan's rule (> 10 points apart):** at low, 100 runs, hom-GP AL against Sobol (13.0 points) and random (12.5). Those two comparisons count lost runs against the active-learning arm and it still wins. No H1 comparison was flagged.

## 6. How many reruns a verdict needs (`reruns.json`, `fig_reruns.png`)

Per labelled grid point, runs until a verdict on "p(x) ≥ 0.10?". Attempts include unrealised runs. Points are banded by their raw p̂ (fails / realised runs, not smoothed: **a deviation from the plan's "reference p"**, noticed after the run; the code used p̂ from the start); SPRT runs are simulated from that p̂, margin-rule runs are bootstrap draws from the point's stored margins. Each point's mean over its simulated sequences; then median (90th percentile) over the points in the band:

| Raw p̂ at the point | Rule | low | mid | high |
|---|---|---|---|---|
| 0 (no failure seen) | SPRT on pass/fail | 18 (18) | 18 (18) | 18 (18) |
| | margin quantile rule | 2.3 (2.9) | 2.7 (4.2) | 3.1 (5.6) |
| 0 < p < 0.05 | SPRT | 23.5 (25.7) | 23.3 (26.1) | 23.4 (26.4) |
| | margin rule | 16.4 (28.3) | 15.3 (33.3) | 15.1 (40.3) |
| 0.05 ≤ p < 0.2 (near α) | SPRT | 35.5 (44.6) | 37.3 (47.8) | 37.1 (47.1) |
| | margin rule | 37.6 (53.1), 19 % undecided at 100 | 39.4 (64.9), 24 % | 36.1 (57.8), 19 % |
| 0.2 ≤ p < 0.5 | SPRT | 11.7 (19.0) | 11.3 (18.5) | 11.4 (21.6) |
| | margin rule | 6.4 (14.3) | 5.9 (13.3) | 6.5 (17.9) |
| p ≥ 0.5 | SPRT | 5.6 (18.4) | 4.2 (5.5) | 3.7 (5.4) |
| | margin rule | 3.6 (12.2) | 2.6 (3.3) | 2.4 (2.8) |
| Mean over all points | SPRT / margin rule | 17.6 / 3.2 | 17.4 / 4.7 | 17.8 / 6.8 |

- **Deterministic system: 1 run per verdict** (R157: 250 of 250 reruns identical).
- **A pass/fail SPRT needs 18 realised runs for any "below α" verdict**, whatever the noise level: that is the price of the 0.05/0.20 indifference zone at 5 % error, not of the noise. The noise level decides how many points sit near α: 49 / 135 / 307 grid points in [0.05, 0.2), each needing about 37 runs.
- **Using the size of the margin cuts the mean cost over the whole region 5.5 / 3.7 / 2.6 fold** (3.2 / 4.7 / 6.8 runs against 17.6 / 17.4 / 17.8). It grows with the noise level, as it should. It has a price, though: it assumes a Gaussian margin at a point and was wrong more often. Where the reference p is 0.2–0.5 it said "fail" in 92–93 % of sequences against 99 % for the SPRT, and near α it left 19–24 % undecided at 100 runs.

## Post hoc (after the plan)

- The figures' layout and the observation on the falling no-verdict share. No number changed.
- The interpretations labelled post hoc in section 2, and the descriptive model-swap comparison against hom-GP AL.
- Rerun bands by raw p̂ instead of the smoothed reference p (section 6).
- Wording fixed after an independent traceability check of every number against `results/noise/` (four corrections: calibration ranking, isotonic count, margin-rule saving, H2 wording at high).
- The calibration explanations in section 3 are hypotheses, not results.

## Limits

- **The SUT is a port.** Exact without noise (step 0), but the noisy system is "esmini's ACC as it would behave with this noise", not a real stack. The noise model is synthetic (AR(1), cutter only, no sensor physics), and noise and delay rise together, so their effects are not separated.
- **The heteroskedastic GP is a two-stage approximation** (not Binois et al.'s joint likelihood; the R hetGP package was not run). Its design is fixed at 2 runs per point; no explore-or-replicate rule was tested.
- **The reference is an estimate:** 10–40 runs per point, isotonic smoothing along TTC (it changed p̂ on 5 / 36 / 76 lines at low / mid / high; 15 high-level lines had more than one raw crossing of α), and p̂ = 0 at points with 0 of 10 failing and no failing neighbour. 56 low-level grid points had too few realised runs for a label.
- **p is conditional on a realised run.** Unrealised runs (4–12 %) are left out of p and reported separately; they cluster at the boundary.
- One scenario family, one controller, α = 0.10, one budget (300), 10 seeds.

## Provenance: uncommitted code at run time

All 120 campaign manifests (`results/noise/manifests/*/*.json`) record `code_commit` `51bba8f` with
`code_dirty: true`: when the campaigns ran, `src/` or `env/` had changes that were not committed. Git did not record what
they were. Between `51bba8f` and the commit that added these results (`d8a9d42`), the only change to `src/` and `env/` is
one new file, `src/stp/noise/plots.py`; no file the campaigns use was edited. The likely cause is that this file was
present but not yet committed. That is an inference, not a record.

Spot check (`results/noise/clean_rerun_spotcheck.json`): campaign `mid/het_al_0` (heteroskedastic GP, active learning,
300 runs) was rerun in a fresh clone of the clean commit `91d62b7`, with a freshly built environment. All 300 runs
match the manifest: same inputs, seeds and realisation flags, and identical margins (largest absolute difference 0.0).
The rerun took 187 s on 4 workers. The other 119 campaigns were not rerun.

## Reproduce

```bash
PYTHONPATH=src .venv/bin/python -m stp.noise.experiment all 4    # about 4 h 15 min on 4 cores (10:13–14:26 here): ~264,000 runs + GP fits
PYTHONPATH=src .venv/bin/python -m stp.noise.plots
.venv/bin/python -m pytest tests/test_noise.py
```
