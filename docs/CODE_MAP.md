# Code map

Which code does what, which master's stage and problem each piece serves, and how much of it survives a change of system under test (SUT). Problem IDs (S05-P01 and so on) are those of the master's problem map.

"SUT-independent" means the module would work unchanged with a different driving system: **yes**, **no**, or **partly** with the part that would change. Tests refer to `tests/test_pipeline.py` (TP) and `tests/test_v2_rules.py` (TR). "None" means no direct test exists. The module may still be exercised by a campaign.

## Core

| Module | What it does | Stage and problem slice | SUT-independent | Tests |
|---|---|---|---|---|
| `src/stp/scenario.py` | Four-input logical scenario. Writes the S-curve OpenDRIVE road and the OpenSCENARIO file with an externally controlled ego | S01-P01, S01-P06; S05-P03 | Partly. The parameter interface is general; the road and file templates are specific to this scenario family | TP: known answers, inputs reach the simulator |
| `src/stp/sut.py` | Pure-pursuit lane keeper with a curvature limit, and the seeded randomness W (perception noise, latency, gust timing) at three v1 levels | S04-P05; S05-P02 | No. This is the SUT | TP: inputs, determinism |
| `src/stp/runner.py` | One closed-loop run: steps esmini, calls the controller, computes the safety margin, applies the gates, returns the run record | S05-P01, S05-P02; S06-P05 (continuous margin); X1-P04 (stops early past 3 m departure) | No. Couples esmini, the controller and the oracle. Its return dictionary is the interface to keep | TP: realised, determinism, known answers, `failed` needs `realised` |
| `src/stp/gates.py` | Eight realisation checks of the executed run against the specification | S05-P01, S05-P03, S05-P05 | Partly. The principle and the record are general; each check reads esmini's trace and this road | TP: seven seeded defects |
| `src/stp/esmini_lib.py` | ctypes binding to the pinned esmini library | S03 (simulator), S05-P06 | No. Simulator-specific | Through TP |
| `src/stp/opensbt_bridge.py` | OpenSBT simulator, fitness and critical-function wrappers; replays cached evaluations for resume | S02-P01; S06-P05; X2-P01 | Partly. The OpenSBT contract is general; it calls `runner.run` | None |

## v1 campaign (kept as committed)

| Module | What it does | Stage and problem slice | SUT-independent | Tests |
|---|---|---|---|---|
| `src/stp/campaign.py` | Resumable v1 campaign: search, random, replication, reference runs | S07-P01, S07-P02; X2-P02 | Partly | None |
| `src/stp/analysis.py` | v1 analysis: rules, weighted scores, search against random | S07-P02; X2-P01, X2-P02 | Yes | TP: Wilson, SPRT, rule answers |
| `src/stp/diagnostics.py` | Post hoc: what decided failures in v1 (latency against scenario) | S04-P05; S07-P01 | Partly. Reads v1 seeds and W | None |
| `src/stp/plots.py` | v1 figures | Reporting | Yes | None |
| `scripts/run_campaign.sh` | Restart loop for v1 | S05-P05 | Yes | None |

## v2 campaign

| Module | What it does | Stage and problem slice | SUT-independent | Tests |
|---|---|---|---|---|
| `src/stp/v2/config.py` | Fixed-latency noise levels, candidate spaces | S01-P01; S04-P05 | No. SUT settings and scenario ranges | TR: latency fixed, levels match v1 |
| `src/stp/v2/jobs.py` | Per-run seeds, resumable batches, fsync every 100 runs | S05-P02, S05-P06; X1-P05 | Yes, apart from calling `runner.run` | TR: seed streams |
| `src/stp/v2/gate.py` | Calibration gates on random samples: latency alone, scenario predicts failure, failure rate, noise matters, confirmation | S01-P01; S02-P01; S05-P02; S07-P01 | Partly. The AUC, rate and confirmation gates are general; the latency sweep is not | None |
| `src/stp/v2/rules.py` | Verdict rules with exact operating characteristics | S07-P01, S07-P02; X1-P02 | Yes | TR: exact against simulation, stated errors, boundaries |
| `src/stp/v2/campaign.py` | Ground-truth set with pilot and bisection, then search, capped replication and reference runs | S07-P01, S07-P02; S08-P02; X2-P01, X2-P02 | Partly. The search stage imports the OpenSBT bridge; the rest is general | None |
| `src/stp/v2/analysis.py` | Planned scores, bootstrap, recommendation rule, Holm correction | S07-P02; X2-P02, X2-P06 | Yes | None directly; rules are tested in TR |
| `src/stp/v2/plots.py` | v2 figures | Reporting | Yes | None |
| `scripts/run_campaign_v2.sh` | Restart loop under the 8-hour cap, with the realisation pause | S05-P05 | Yes | None |

## Environment and records

| Item | What it does | Stage and problem slice |
|---|---|---|
| `scripts/setup_env.sh`, `env/*.lock` | Rebuild the pinned environment and check esmini's hash and OpenSBT's commit | S05-P06; X2-P04 |
| `docs/PREREG.md`, `docs/CALIBRATION.md`, `docs/v2/PLAN.md`, `docs/v2/CALIBRATION.md` | Plans and frozen ranges, committed before runs | X2-P02, X2-P07 |
| `results/**` (except `results/raw`) | Summaries, CSVs and figures. Raw logs are git-ignored | X2-P04 |

## Swapping in Autoware Mini

The aim is to keep the rules, batches and analysis, and replace what touches the simulator and the SUT.

| Change | What to do | Size |
|---|---|---|
| New runner | Write `runner_autoware.py` returning the same record: `params`, `seed`, `realised`, `gates`, `margin`, `failed`, `peak_offset`, `steps`. `v2/jobs.py`, `opensbt_bridge.py` and the analysis read only that | Main piece |
| Replace `sut.py` | Autoware Mini is the SUT. Its controller and timing live outside this process | Removal |
| Replace `scenario.py` | Generate what its planner simulation needs: a map, a route and scripted actors, in place of the S-curve templates | Moderate |
| Rewrite `gates.py` checks | Keep the principle. New checks: map and route loaded, localisation available, planner publishing, clock and rate within bounds, actors present, ego moved | Moderate |
| Redefine the oracle | Lane departure with a margin may not be enough: collision, route completion and a continuous safety margin, each with a known-answer test | Moderate |
| Redefine W | v1 and v2 inject seeded W. Stack timing is not seedable in the same way, so seeds no longer imply determinism, and `test_same_seed_is_deterministic` has to become a measurement of run-to-run spread. This changes what a "rerun" means, and rerun independence must be checked, not assumed | Design decision |
| Isolate parallel runs | Each ROS run needs its own master and ports, probably a container per worker. `jobs.py`'s process pool would drive containers | Moderate |
| Time budget | Runs will cost seconds to minutes. Time a pilot first and resize strata and reruns; the rules and analysis do not change | Planning |
| Rerun the gates | Scenario inputs must predict failure on random samples before any freeze, and the noise levels must be re-derived | Required |

Rules (`v2/rules.py`), analysis, plotting, batching and the plan structure should carry over unchanged. Autoware Mini has not been installed or timed here, so these sizes are estimates.

## Before making the repository public

1. Add a licence. None exists. OpenSBT is Apache-2.0 per its `LICENSE`; confirm esmini's licence and how the downloaded binaries may be used.
2. Add a CI workflow; none exists yet (the notebook work adds one).
3. Merge `campaign-v2` into `main`, and keep the `v1-noise-dominated` tag.
4. Reformat the code. Modules are dense, with many semicolon-joined statements and 63 lines over 180 characters, and they need a formatter and a linter.
5. Merge the v1 and v2 duplication (`campaign`, `analysis`, `plots`), or move v1 to a clearly archived package.
6. Write direct tests for `opensbt_bridge.py`, `v2/gate.py`, `v2/campaign.py` and `v2/analysis.py`, which have none.
7. Remove the workspace leftovers: an empty, git-ignored `log.txt` and `tests/output`.
8. Decide how to share raw logs. `results/raw` (about 28 MB for v2) is git-ignored, so an archive release would let others re-run the analysis without simulating.
9. Rewrite the README around both campaigns, with how to reproduce them and expected run times. Add a citation file.
10. State the use of AI assistance, consistent with the `Co-Authored-By` lines in the history.
11. No personal paths or email addresses were found in tracked files. Re-run that check before publishing.
