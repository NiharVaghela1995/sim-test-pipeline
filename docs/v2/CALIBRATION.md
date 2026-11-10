# Campaign v2: calibration record

Random samples only. See `docs/v2/PLAN.md`. Raw results: `results/v2/gate.json`.

## First G0 (2026-11-10): failed on candidate A, the plan's stop rule applied

G0 required 0 failures in 100 runs at 200 ms and at 300 ms at every level, on scenarios with lateral demand at most 3 m/s². Result, failures out of 100:

| Latency | Low | Medium | High |
|---|---|---|---|
| 100 ms | 0 | 0 | 8 |
| 200 ms | 0 | 2 | 7 |
| 300 ms | 3 | 4 | 12 |
| 360 ms | 24 | 13 | 26 |
| 400 ms | 39 | 30 | 56 |
| 460 ms | 99 | 99 | 98 |

The plan's fallback, 100 ms, also has failures at high noise, so the plan said to stop without a campaign.

The author approved Amendment 1 in `docs/v2/PLAN.md` (post hoc): G0 is rerun with gust 0 to isolate latency.

## Result under Amendment 1: candidate A frozen (2026-11-10)

Candidate A is the first in the plan's order and it passed every gate, so B to E were not tried.

**Frozen space:** speed 8–24 m/s, k1 0.002–0.020 1/m, k2 ±0.020 1/m, gust 0–1.0 m/s. Latency fixed at 200 ms.

Amended G0 (gust 0), failures out of 100:

| Latency | Low | Medium | High |
|---|---|---|---|
| 100, 200, 300, 360 ms | 0 | 0 | 0 |
| 400 ms | 0 | 0 | 28 |
| 460 ms | 87 | 90 | 98 |

G1, G2 and realisation, 1,000 random scenarios per level, one run each. AUC from scenario inputs, 5-fold cross-validated, with bootstrap 95% interval:

| Sample | Level | Failure rate | AUC scenario inputs | Interval | AUC gust timing only (diagnostic) | Realised |
|---|---|---|---|---|---|---|
| Tuning | low | 20.7% | 0.994 | 0.990–0.997 | 0.517 | 100% |
| Tuning | medium | 24.3% | 0.988 | 0.983–0.992 | 0.511 | 100% |
| Tuning | high | 28.0% | 0.972 | 0.962–0.981 | 0.506 | 100% |
| Confirmation | low | 22.3% | 0.993 | 0.989–0.996 | 0.496 | 100% |
| Confirmation | medium | 23.7% | 0.979 | 0.970–0.985 | 0.506 | 100% |
| Confirmation | high | 28.0% | 0.967 | 0.956–0.976 | 0.539 | 100% |

G3, 300 random scenarios, 20 reruns each:

| Level | Rerun failure rate 0.1–0.9 | Rate 0 | Rate 1 |
|---|---|---|---|
| medium | 13.0% | 64.0% | 21.7% |
| high | 18.3% | 59.3% | 19.0% |

Interpretation fixed when writing the campaign code: "200 bisection probes" means 200 pairs with three bisection steps each, so up to 600 probe points per level.
