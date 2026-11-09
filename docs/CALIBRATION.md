# Calibration of the input ranges

Done once, before the main campaign, on 2026-11-10, using **uniform random samples only**: no search results and no replication data informed this choice. The system under test was at the medium noise level.

Criterion, chosen in advance: a random-sample failure rate of roughly 5% to 20%. Above that, a search has little to find and almost every failure is trivial.

| Set | speed m/s | k1 1/m | k2 1/m | gust m/s | n | Random failure rate | Not realised |
|---|---|---|---|---|---|---|---|
| Original pilot | 12–32 | 0.002–0.040 | ±0.040 | 0–1.0 | 120 | 0.91 | 0 |
| A | 10–24 | 0.002–0.025 | ±0.025 | 0–1.0 | 250 | 0.520 | 0 |
| B | 10–22 | 0.002–0.020 | ±0.020 | 0–1.0 | 250 | 0.428 | 0 |
| C | 10–20 | 0.002–0.018 | ±0.018 | 0–1.0 | 250 | 0.304 | 0 |
| D | 10–20 | 0.002–0.016 | ±0.016 | 0–1.5 | 250 | 0.460 | 0 |
| E | 8–20 | 0.002–0.014 | ±0.014 | 0–1.0 | 250 | 0.308 | 0 |
| F | 8–18 | 0.002–0.016 | ±0.016 | 0–1.0 | 250 | 0.308 | 0 |
| G | 8–20 | 0.002–0.012 | ±0.012 | 0–1.0 | 250 | 0.256 | 0 |
| H | 8–17 | 0.002–0.015 | ±0.015 | 0–1.0 | 250 | 0.296 | 0 |
| **I (frozen)** | **8–20** | **0.002–0.012** | **±0.012** | **0–0.5** | **400** | **0.182** | **0** |
| J | 8–20 | 0.002–0.014 | ±0.014 | 0–0.4 | 400 | 0.172 | 0 |
| K | 8–20 | 0.002–0.016 | ±0.016 | 0–0.3 | 400 | 0.177 | 0 |

Set I was chosen among I, J and K, all inside the target, because it keeps the widest gust range, the source of disturbance the controller cannot see. The ranges are frozen in `src/stp/scenario.py` and are the same at all three noise levels. The original pilot's 120 random failures are the only outputs other than failure rate that were seen before freezing, and they were used only to reject that range.
