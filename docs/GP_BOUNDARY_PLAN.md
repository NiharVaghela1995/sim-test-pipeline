# GP boundary demo: plan (2026-11-15)

Written and committed before the reference grid, the campaigns and the replication were run. Anything decided after this commit is labelled **post hoc** in the report. The only cut-in data seen so far is the pilot in the last section, used to fix the scenario and the realisation check.

**Question.** For one rule on one logical scenario, does a Gaussian-process (GP) search with active learning find the pass/fail boundary with fewer esmini runs than a plain Sobol design or a random design? Is its uncertainty band honest?

## Setup

| Item | Value |
|---|---|
| Simulator | esmini 3.11.0, pinned by `env/esmini.lock` (zip sha256), fixed step 0.02 s, 15 s per run |
| Road | straight, two driving lanes of 3.5 m, written by `src/stp/cutin/scenario.py` |
| System under test | esmini's built-in `ACCController` on the ego: set speed = ego speed, `timeGap` 1.5 s, `mode` override, longitudinal only. Ego `maxDeceleration` 6 m/s², `maxAcceleration` 3 m/s². Lateral: esmini's default lane following |
| Cutting car | scripted, non-reactive. Starts in the right lane at constant speed, sinusoidal lane change into the ego lane of 3.0 s, starting at t = 2.0 s |
| Parameters | ego speed 20–35 m/s; gap 5–40 m; relative speed of the cutting car −10 to 0 m/s |
| Gap definition | bumper-to-bumper longitudinal gap at the **cut-in moment**, when the cutting car's body first crosses the lane line (0.92 s into its lane change), for an ego still at its set speed |
| Rule | minimum TTC ≥ 1.5 s. The threshold is a placeholder, not a quoted regulation value |
| KPI | TTC = gap / closing speed, only while the cars overlap laterally and the ego is closing. Collision gives 0. TTC is capped at 6 s, also when there is no closing at all. **Margin** = min TTC − 1.5 s, in [−1.5, 4.5]. Pass if margin ≥ 0 |

Why the gap is taken at the lane-line crossing rather than at the start of the lane change: in the pilot, with the gap taken at the start of the lane change, the ego at 35 m/s and −10 m/s passed a car only 5 m ahead before it entered the lane. That corner of the box was not a cut-in in front. At the line crossing, the cutting car is always at least 5 m ahead, and still ahead when the cars first overlap.

Known properties of this SUT, found in the pilot:

- The ACC reacts to the cutting car earlier at small gaps: at 5 m it brakes while the car is 2.66 m to the side, at 7 m or more only at about 1.75 m. The margin is therefore not monotone in gap at small gaps, and it has kinks and plateaus. A smooth GP may handle this badly. That is part of what is tested.
- When the bumper gap falls below about 0.7 m, the ACC drops its speed in one step, far beyond its deceleration limit. This happened in 5 of 300 pilot runs, all with min TTC ≤ 0.37 s and always after the minimum was reached. A gate rejects a run if it happens before the minimum.

## Realisation check (step 1)

Each run is checked against the intended parameters (`src/stp/cutin/gates.py`). A run that fails any gate is logged as not realised and gets no pass or fail. It still counts against the run budget.

| Gate | Passes if |
|---|---|
| loaded | esmini loaded the file |
| controllers | ego runs `ACCController` (type 8), cutting car the default controller (type 0) |
| start_pose | both cars at the intended s, lane and lateral position at t = 0, within 0.05 m |
| start_speed | both speeds as intended after the first step, within 0.05 m/s |
| cut_speed_held | the cutting car keeps its speed until the lane change |
| ego_cruise_before_cut | the ego is at its set speed until the lane change starts |
| lane_change_start | the lateral move starts at 2.0 s, within one step |
| gap_at_cut | gap at the line crossing within 0.05 m of the intended gap, and crossing time within one step |
| lane_change_end | the cutting car ends centred in the ego lane within 3.1 s and stays there |
| ego_lane_kept | the ego stays in its lane |
| outcome_settled | at the end the ego is not closing in, or its TTC is above the cap, so the minimum is reached inside the run |
| dynamics_valid_to_kpi | no deceleration above the limit before the minimum TTC |
| clock | simulated time = steps × 0.02 s |

Deliberately broken scenarios, each a test that the check must catch: ego without ACC, cutting car starting in the ego lane, no lane change, lane change to the wrong lane, late trigger, cutting car placed 2 m off, cutting car 1 m/s off, ego 1 m/s off, simulation too short. Known-answer tests: a large gap with zero relative speed passes at the cap; a 5 m gap at 35 m/s and −10 m/s fails; the TTC function on constructed traces.

## Reference (step 2)

A dense grid, run once: ego speed every 0.5 m/s (31 values), relative speed every 0.5 m/s (21), gap every 0.25 m (141), 91,791 runs. Every point must be realised. Otherwise its share is reported and the point is left out of all metrics.

- **True class** at a grid point: the sign of its margin.
- **Reference boundary gap** g*(v, Δv) on each of the 651 (ego speed, relative speed) lines: the smallest gap above which every grid gap passes, with linear interpolation of the margin at the last sign change. If the largest gap still fails, g* = 40; if every gap passes, g* = 5. This handles non-monotone lines conservatively.
- **Reference boundary points**: every sign change along a gap line, located by linear interpolation. There can be more than one per line.
- **Resolution check**: g* recomputed from every second gap (0.5 m) against the full grid, and refined by bisection to 0.01 m on 30 random lines with a sign change (seed fixed in code). The reference is usable only if its own error is well below the 1.0 m target below.

## Compared arms (step 3)

Budgets of 100, 200 and 300 runs, 10 seeds (index 0–9). Every arm is scored at 40, 60, …, 300 runs.

| Arm | Design | Model scored |
|---|---|---|
| **GP-AL** | first 30 points of the scrambled Sobol sequence of seed i, then batches of 10 chosen by active learning | GP refit after every batch |
| **Sobol** | the first n points of the same scrambled Sobol sequence of seed i | the same GP, fit to those n points |
| **Random** | n uniform points from seed i | the same GP |

Sobol and GP-AL share the first 30 points for each seed, so they are compared in pairs.

The GP, ported from an earlier project (private) and simplified: scikit-learn `GaussianProcessRegressor`, inputs scaled to [0, 1], `normalize_y`, kernel constant × Matérn 5/2 with one length scale per input (bounds 0.01–10) plus a white-noise term (bounds 1e-8 to 1e-1, on the normalised scale), fitted by maximum marginal likelihood with 5 seeded restarts. The target is the margin. The band is the full predictive standard deviation, white-noise term included.

Active learning, as in an earlier project (private): the straddle score 1.96·σ − |μ| (Bryan et al., NIPS 2005) on a fresh pool of 2,048 scrambled Sobol points per batch. Pick the 10 highest-scoring points that are at least 0.05 apart (unit cube) from each other and from every earlier run; relax the distance if the batch cannot be filled. All seeds derive from the seed index by hashing, so a campaign is a pure function of its manifest.

Not kept from an earlier project (private): the heteroscedastic noise surface, OCBA replicate allocation, GP-Hedge and the stopping rule. esmini and this SUT are expected to be deterministic, so replicate noise is measured (step 4), not modelled. Budgets are fixed in advance, so there is no stopping rule.

Controls, which answer "does the GP model matter at all":

- **Constant**: predict the majority class of the n runs everywhere.
- **1-NN**: class of the nearest run (unit cube), on the Sobol and on the random designs.
- **Permutation null**: at 300 runs, for GP-AL and Sobol, marginal likelihood of the fit against 19 fits to shuffled margins (smallest attainable p = 0.05).

## Metrics

All are scored against the reference grid, with the model's prediction at every grid point.

1. **Misclassification rate (primary)**: share of grid points where sign(μ) differs from the true class. Equal grid spacing, so this is the share of the box's volume.
2. **Boundary error**: mean over the 651 lines of |ĝ* − g*| in metres, where ĝ* is computed from μ on the same gap points by the same rule. The 90th percentile is reported too.
3. **Runs needed for a target error**: the first scored budget at which misclassification ≤ 2% (secondary 1%), and boundary error ≤ 1.0 m, per seed. "> 300" if never. Median over seeds.
4. **Calibration of the band**: at stated levels 50, 80, 90, 95 and 99%, the share of reference boundary points with |μ| ≤ z·σ, where z is the two-sided normal quantile. A band that is honest contains the reference boundary at about its stated rate. Secondary: coverage of the reference margin by μ ± z·σ at grid points within 0.5 s of the threshold.

## Hypotheses and decision rules, fixed now

- **H1 (primary).** GP-AL has a lower misclassification rate than Sobol at 100, 200 and 300 runs.
- **H2.** The same against random.
- **H3.** GP-AL reaches the targets with fewer runs than Sobol and random.
- **H4.** The GP-AL band at 300 runs contains the reference boundary at its stated 95% rate. Expected to fail: the pilot shows kinks, and the proposal names sharp boundaries as a risk.
- **H5.** On the same Sobol design, the GP beats 1-NN and the constant predictor, and its fit beats the permutation null.
- **H6.** esmini with this ACC is deterministic: replicated runs give bitwise-identical margins.
- **H7.** A campaign rerun from its manifest gives an identical result.

**Test for H1 and H2.** For each budget (100, 200, 300) and baseline (Sobol, random): a one-sided Wilcoxon signed-rank test on the 10 per-seed differences, with Holm correction over these 6 tests at α = 0.05. GP-AL **helps** against a baseline at a budget only if all three hold: the Holm-corrected test is significant, GP-AL is better in at least 8 of 10 seeds, and the median per-seed ratio GP-AL / baseline is at most 0.8 (at least 20% fewer misclassified points). A ratio is not used for a seed whose baseline error is zero: that seed counts as a GP-AL win only if GP-AL is also zero, and the median is taken over the rest.

**What counts as "GP does not help".** Against Sobol, the stronger and simpler baseline, GP-AL fails the "helps" test at all three budgets. If it helps at some budgets and not others, the report says which. If Sobol passes the same test against GP-AL at any budget, the report says **GP-AL is worse** there. The report states this outcome in its first lines whichever way it falls.

**Calibration verdict.** At 300 runs: mean containment over seeds at the stated 95% below 0.90 is **overconfident**, above 0.99 is **conservative**, otherwise **calibrated at 95%**. The same for Sobol and random.

## Replication (step 4)

Boundary points: for each GP-AL seed at 300 runs, the 10 runs with the smallest |margin| (100 points), plus 50 reference grid points next to a sign change (seeded draw). Each is rerun 10 times: 5 in one process in sequence, 5 in a pool of 4 workers in shuffled order, 2 of all 10 with a different esmini seed. Reported: the largest absolute margin difference from the original run, and whether every verdict matched. If any difference is non-zero, the spread is the result and the verdict rules of `src/stp/v2/rules.py` are applied to those points. Bitwise identity is what H6 claims.

## Determinism (step 5)

Each campaign writes a manifest: arm, seed index, derived seeds, budget, GP and design settings, scenario constants, esmini version, zip and library hashes, Python and package versions, thread settings, the code commit, every run's parameters, its .xosc hash and its margin, and a hash of the final model's prediction on the reference grid. `python -m stp.cutin.campaign rerun <manifest>` rebuilds the campaign from the manifest alone and compares everything. Tests rerun a short campaign in a fresh process. Once, a full campaign (GP-AL, seed 0, 300 runs) is rerun from a fresh clone of the commit with an environment rebuilt by `scripts/setup_env.sh`.

## Outputs

`docs/GP_BOUNDARY_REPORT.md`; figures in `results/gp_boundary/`: boundary map with band at three ego speeds, misclassification against budget, boundary error against budget, calibration. Critical .xosc files near the boundary in `results/gp_boundary/critical/`. Run records and the reference grid as committed CSV/NPZ, so every number in the report can be recomputed without simulating.

## Pilot, before this plan

300 uniform points from a separate seed (987654), not reused anywhere. Used to fix the gap definition, the lane-change trigger timing (esmini starts a triggered action one step after its condition first holds, so the trigger is set half a step early), the correction for the cutting car's small longitudinal slowdown while it turns, and the gates `ego_cruise_before_cut`, `outcome_settled` and `dynamics_valid_to_kpi` as described above. After these fixes, 300 of 300 pilot runs were realised. 13.7% failed the rule, none collided, and 35% were at the 6 s cap. Six gap sweeps at 1 m steps showed the non-monotone stretches described above.

## Weaknesses of an earlier project (private) that this design answers

From the author's own correction notes on an earlier project (private).

| Weakness in the earlier project | Answer here |
|---|---|
| No search-versus-Sobol comparison on the real simulator; only a synthetic one | All arms run on esmini, against a reference from 91,791 esmini runs |
| 3 seeds; the mean ordering came from one seed | 10 paired seeds, a per-seed win count in the decision rule, Holm correction |
| RMSE barely beat a constant predictor | Constant and 1-NN controls; error scored against truth, not against held-out noisy runs |
| GP fit no better than on permuted targets | Permutation null on the final fits |
| 95% intervals covered 85–89% | Band calibration against the reference boundary, at five stated levels |
| Noise estimated from 2–5 replicates and used as known | No noise model; determinism measured by replication |
| Stopping rule fired the same on no-signal data | Fixed budgets, no stopping rule |
| Many scenarios not executed as specified | Realisation check on every run, with broken scenarios it must catch |
| Kernel and restart flips | One kernel fixed here, seeded restarts, results reproduced from the manifest |
