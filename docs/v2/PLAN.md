# Campaign v2: analysis plan (2026-11-10)

Written and committed before any v2 simulation. Anything decided after seeing v2 results is labelled **post hoc** in the report. The only data seen before this plan are the v1 results (tag `v1-noise-dominated`, "v1: noise-dominated, cautionary result"), which stay unchanged.

**Question.** When a search reports a failure, which verdict rule should decide whether it is real, at which noise level, and how many reruns does that cost?

**Why v1 could not answer.** Drawn control latency decided almost every outcome (AUC at least 0.99, against 0.50 to 0.53 for the scenario inputs). The v1 road never demanded more than 4.8 m/s² of lateral acceleration, below the controller's 6 m/s² limit, so the scenario could not cause a failure. All failures at one noise level therefore had the same reproduction probability, and rules could only be seen at two base rates.

## System and randomness

Same simulator (esmini 3.11.0), S-curve road, pure-pursuit controller, failure definition and realisation checks as v1. Reproduction measures injected randomness W only.

| Level | Perception noise sd | Gust period s | Gust phase | Latency |
|---|---|---|---|---|
| low | 0.05 m | 2.5–3.0 | 0–π/4 | fixed 200 ms |
| medium | 0.15 m | 1.5–4.0 | 0–2π | fixed 200 ms |
| high | 0.30 m | 1.0–6.0 | 0–2π | fixed 200 ms |

Noise and gust timing are the v1 levels. Latency is fixed at 200 ms (10 steps of 20 ms) for every run. In v1 no run failed below 380 ms, so this leaves a factor of 1.9, and gate G0 checks it.

## Calibration gates, on random samples only

Candidate scenario spaces are tried **in this order**, and the first that passes every gate is frozen. No space outside the list is tried. Latency is never changed to pass G1, G2 or G3.

| Candidate | speed m/s | k1 1/m | k2 1/m | gust m/s |
|---|---|---|---|---|
| A | 8–24 | 0.002–0.020 | ±0.020 | 0–1.0 |
| B | 8–24 | 0.002–0.020 | ±0.020 | 0–1.5 |
| C | 8–24 | 0.002–0.016 | ±0.016 | 0–1.0 |
| D | 8–22 | 0.002–0.020 | ±0.020 | 0–1.0 |
| E | 8–26 | 0.002–0.020 | ±0.020 | 0–1.0 |

Chosen by arithmetic only: each puts the controller's limit inside the space, with 10% to 27% of scenarios demanding more than 6 m/s².

| Gate | Sample | Pass condition |
|---|---|---|
| G0 latency alone | 100 random scenarios per level with demand v²·max(k1, abs k2) ≤ 3 m/s²; latency 100, 200, 300, 360, 400, 460 ms | 0 failures at 200 ms and at 300 ms, at every level |
| G1 scenario predicts failure | 1,000 random scenarios per level, one run each; AUC of a gradient-boosted classifier on the four scenario inputs, 5-fold cross-validated (same model as the v1 diagnostic) | AUC ≥ 0.75 and bootstrap 95% lower bound ≥ 0.70, at every level |
| G2 failure rate | same runs | medium 10–40%, low at least 3%, high at most 60% |
| Realisation | same runs | at least 99% of runs realised, at every level |
| G3 noise matters | 300 random scenarios at medium and high, 20 reruns each | at least 5% of scenarios with a rerun failure rate from 0.1 to 0.9, at each of the two levels |
| Confirmation | a fresh 1,000 random scenarios per level | G1, G2 and realisation pass again on data not used to choose the space |

The AUC is also reported for gust timing alone (a diagnostic, not a gate). If G0 fails at 200 ms, latency drops once to 100 ms and G0 is repeated. If it fails again, or no candidate passes, the work stops and is reported without a campaign. Every candidate tried is listed in `docs/v2/CALIBRATION.md`, which is committed before the campaign starts.

## Hypotheses, stated in advance

- **H1.** Scenario inputs predict failure at each level (G1).
- **H2.** Reported failures at one level differ from one another: dispersion of rerun counts above binomial (chi-square test as in v1).
- **H3.** The mean reproduction rate of reported failures exceeds that level's random-sample base rate.
- **H4.** Mean reproduction of reported failures falls, and the share of partly reproducing failures rises, from low to high noise.
- **H5.** Any-of-n rules make many false "real" calls and all-of-n rules miss many real failures. Majority-of-n and the sequential tests balance the two.
- **H6.** The sequential test with p0 = 0.3, p1 = 0.7, α = β = 0.05 uses fewer mean reruns than a fixed-n majority rule of equal or lower error.
- **H7.** NSGA-II finds more confirmed failures than random sampling at equal budget.

## Metrics and verdict rules

A scenario's true failure probability is p(s). A failure is **real** if p(s) ≥ τ. Primary τ = 0.5, with sensitivity at τ = 0.2 and 0.8. τ is a policy choice and not a fact about the system.

| Rule | Declares real if |
|---|---|
| report as-is | always (0 reruns) |
| any-of-n, n = 1, 3, 5 | at least one of n reruns fails |
| 2-of-5, 3-of-10, 4-of-5 | at least k of n reruns fail |
| majority-of-n, n = 3, 5, 9, 19, 39 | more than half of n reruns fail |
| all-of-n, n = 3, 5, 10 | every one of n reruns fails |
| Wilson bound, n = 20 | 95% Wilson lower bound on the rerun rate is at least τ |
| SPRT 0.3/0.7, α = β = 0.05 | Wald sequential test, p ≤ 0.3 against p ≥ 0.7 |
| SPRT 0.2/0.8, α = β = 0.05 | as above, wider indifference band |
| SPRT 0.4/0.6, α = β = 0.05 | as above, narrower band |
| SPRT 0.3/0.7, α = β = 0.01 | as above, stricter errors |

Sequential tests are capped at 40 reruns; at the cap the verdict is real if the rate is at least τ. For τ other than 0.5 the sequential tests are recentred (0.05/0.35 at τ = 0.2, 0.65/0.95 at τ = 0.8). The full k-of-n grid for n = 3, 5, 10, 20, 40 goes in a CSV as exploratory output.

For each rule and level: **false "real" calls** (real verdict when p < τ), **missed real failures** (not-real verdict when p ≥ τ), overall wrong verdicts, and mean reruns. Bootstrap 95% intervals over scenarios within strata.

Rules are applied to rerun sequences that are never used to estimate p(s), so verdicts and truth are independent. Primary scores use those actual sequences. A secondary score computes each rule's exact verdict probability given p̂ (binomial, or dynamic programming for the capped sequential tests), which also gives each sequential test's achieved error rates against its stated ones.

Which rule to recommend, fixed now: per level, among rules with at most 5% false "real" calls and at most 5% missed real failures on scenarios at least 0.1 from τ, the one with the fewest mean reruns. If none qualifies, the report says so and shows the closest. Verdicts within 0.1 of τ are reported separately, because no affordable rule can resolve them.

## Ground-truth set (step 4)

Per level, on the frozen space:

1. Pool: 600 random scenarios, plus 200 bisection probes (three bisection steps between a random pair where one failed and one passed, using pilot rates). Each candidate gets 10 pilot reruns.
2. Strata by pilot rate: 0; 0.1–0.3; 0.4–0.6; 0.7–0.9; 1.0. Draw 40 per stratum at random with a fixed seed, 200 scenarios per level.
3. Each gets 200 truth reruns and, separately, 40 rule reruns, on independent seed streams. Pilot reruns are used only for stratifying.

Scoring groups scenarios by their 200-run truth estimate, not by pilot rate. Summary rates weight the five strata equally. That mix is a design choice and not an estimate of any population. A stratum that cannot be filled is reported as a shortfall and not topped up from elsewhere. Sensitivity for truth error: repeat the scores excluding scenarios whose 95% Wilson interval on p̂ straddles τ.

## Search campaign (step 5)

Per level: NSGA-II (population 40, 10 generations) and uniform random sampling, 400 evaluations each, 10 seeds, the frozen space, the same seed construction as v1 with a `v2` prefix.

- **Reported failures** are failed, realised evaluations.
- **Replication:** every reported failure gets 20 reruns, capped at 100 failures per arm and seed (uniform random, fixed seed). Per-seed counts are scaled by reported/sampled.
- **Reference:** strata never, partly and always reproduced in those 20 reruns; up to 30 per stratum get 200 truth reruns plus 20 more rule reruns, so that rules can use 40. Estimates over all failures are weighted by stratum size and the cap.
- **Reproduction against base rate:** mean rerun failure rate of reported failures against the random arm's failed share, with bootstrap intervals, per level and arm.
- **Search against random:** reported failures, failures reproducing in at least half of 20 reruns, and distinct input cells (5 bins per input) containing one. Mann-Whitney U and Vargha-Delaney A12 over 10 seeds, Holm-corrected over the 9 tests. Cells count sampled failures only, so the cap may understate them for NSGA-II.
- **Rules on reported failures:** the same scores against the reference p̂.

## Stopping rules

- The gates stop as stated above.
- No stage is stopped or extended because of its results.
- More than 5% of runs not realised at a level in any stage is recorded and pauses the work until explained.
- Crashes resume from the last checkpoint (fsync every 100 runs). Seeds are per run, so resumption does not change results.
- Budget: about 300,000 runs, upper bound 400,000. Wall-clock cap 8 hours. If the cap is reached, the finished stages are analysed and the rest is reported as not run.
- Order: gates, then ground-truth set at all levels, then search campaign at all levels.

## Stated limits, in advance

One simulator, one scenario family, one simple controller. Injected noise is not real-vehicle nondeterminism, so no rule recommendation transfers to a real vehicle without re-estimation. Truth is itself an estimate from 200 reruns. The strata mix is a design choice.

## Commits

This plan, then the frozen calibration, then the runs, then the report.
