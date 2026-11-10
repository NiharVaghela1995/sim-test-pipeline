# Campaign v2: calibration record

Random samples only. See `docs/v2/PLAN.md`. Raw results: `results/v2/gate.json`.

## Status (2026-11-10): G0 failed on candidate A, the plan's stop rule applies

G0 required 0 failures in 100 runs at 200 ms and at 300 ms at every level, on scenarios with lateral demand at most 3 m/s². Result, failures out of 100:

| Latency | Low | Medium | High |
|---|---|---|---|
| 100 ms | 0 | 0 | 8 |
| 200 ms | 0 | 2 | 7 |
| 300 ms | 3 | 4 | 12 |
| 360 ms | 24 | 13 | 26 |
| 400 ms | 39 | 30 | 56 |
| 460 ms | 99 | 99 | 98 |

The plan's fallback, 100 ms, also has failures at high noise, so the plan says to stop without a campaign. No later gate and no campaign has been run.

The author approved Amendment 1 in `docs/v2/PLAN.md` (post hoc): G0 is rerun with gust 0 to isolate latency.
