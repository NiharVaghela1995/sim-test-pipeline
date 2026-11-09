# Analysis plan, fixed before the main campaign (2026-11-10)

**Question.** When a search reports a failure, how many replications and which verdict rule are needed before calling it real?

**System.** esmini 3.11.0, an S-curve road, a pure-pursuit lane keeper with a curvature limit. A failure is the car's edge crossing the lane edge, in a run that passed every realisation check.

**Nondeterminism.** Reproduction here measures injected randomness W only (perception noise, control latency, gust timing). It is not real-vehicle nondeterminism. esmini itself is deterministic given W (tested).

| Level | Perception noise sd | Latency (20 ms steps) | Gust period s | Gust phase |
|---|---|---|---|---|
| low | 0.05 m | 5–8 | 2.5–3.0 | 0–π/4 |
| medium | 0.15 m | 5–25 | 1.5–4.0 | 0–2π |
| high | 0.30 m | 5–50 | 1.0–6.0 | 0–2π |

**Design, per level.** NSGA-II (population 40, 10 generations) and uniform random sampling, 400 evaluations each, 10 seeds, same frozen ranges. Every reported failure is rerun 20 times with fresh W. From each of three strata (never reproduced, sometimes, always, in those 20 reruns), up to 100 failures get 200 further independent reference runs. Estimates over all failures are weighted by stratum size.

**Definitions.** A failure's reproduction rate p is the probability that a fresh run fails. Reference p̂ comes from the 200 reference runs. A failure is **real** if p ≥ τ. Primary τ = 0.5; sensitivity τ = 0.2 and 0.8. The choice of τ is a policy, and not a fact about the system.

**Verdict rules, applied to the 20 reruns only, in order, never to the reference runs.**

| Rule | Declares the failure real if |
|---|---|
| report as-is | always (0 reruns) |
| any-of-n, n = 1, 3, 5 | at least one rerun fails |
| majority-of-n, n = 3, 5, 9, 19 | more than half of n reruns fail |
| all-of-n, n = 3, 5, 10 | every one of n reruns fails |
| Wilson bound, n = 20 | the 95% Wilson lower bound on the rerun rate is at least τ |
| Sequential probability ratio test | Wald SPRT of p ≤ 0.3 against p ≥ 0.7, α = β = 0.05, stops early, capped at 20 reruns; at the cap, real if the rate is at least 0.5 |

**Outcomes.** Per level and rule: false-confirm rate (declares real when p < τ), false-reject rate (declares not real when p ≥ τ), accuracy, mean reruns used, each with a bootstrap 95% interval over failures. Replication need: the smallest n for which majority-of-n reaches at most 5% misclassification.

**Search against random, per level, over 10 seeds.** Reported failures; failures with reproduction rate at least 0.5 over 20 reruns; distinct grid cells (5 bins per input) containing such a failure. Mann-Whitney U and Vargha-Delaney A12.

**Stated limits, in advance.** One simulator, one scenario family, one simple controller. No claim about real driving stacks. Autoware Mini is the next stage.
