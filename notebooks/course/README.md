# Course notebooks: finding a failure region with few simulator runs

Runnable companions to course Modules 13, 14, 15, 17 and 32. Each notebook implements the methods its module names, from
the papers it cites, on test problems with a known failure region, and ends with one small esmini cut-in case that reuses
this repo's pipeline (`src/stp`). Theory stays in the course modules; the notebooks keep the text short.

CPU only. Each notebook runs from a clean kernel in under five minutes; CI executes all of them.

| Notebook | Course module | Methods |
|---|---|---|
| [32_evaluation_harness](32_evaluation_harness.ipynb) | 32, evaluation methodology | test problems, metrics, paired seeds, IQM with bootstrap intervals, Holm, runs to target, calibration, ablations |
| [13_initial_designs](13_initial_designs.ipynb) | 13, initial design | random, LHS, maximin LHS, Sobol', FSSF, 2⁸⁻⁴ resolution IV fraction, Morris screening against a noise null, n₀ at fixed budget |
| [14_surrogates](14_surrogates.ipynb) | 14, surrogate model | GP regression (Matérn, squared-exp.), two-stage heteroskedastic GP, GP classification (latent vs averaged rule), random forest, SVM + Platt, permutation null, band calibration |

## Shared harness: `failreg/`

| File | Contents |
|---|---|
| `problems.py` | Branin (three failure regions), four-branch series system (four), car-following stop with a closed-form zero contour, a noisy car-following variant with input-dependent noise and target {p(x) ≥ 0.10} |
| `metrics.py` | false-safe and false-unsafe rates, misclassified share, boundary distance (mean, max), calibration, undecided share, runs to target, mechanisms found, IQM, bootstrap interval, Wilcoxon, Mann-Whitney, Holm |
| `designs.py` | random, LHS, maximin LHS, scrambled Sobol', FSSF, 2ᵏ⁻ᵖ fractions with their defining relation, Morris trajectories and effects |
| `models.py` | GP regression, two-stage heteroskedastic GP, GP classification (Laplace), random forest, SVM with Platt scaling, 1-NN and constant controls |
| `acquisition.py` | MEE, straddle, MCU, the EFF / contour-EI family, tIMSE, SUR, failure-seeking EI, LSE, GP-Hedge, batches, constraint weighting |
| `replication.py` | fixed replicates, OCBA, threshold allocation, APT, one-step IMSPE replicate-or-explore |
| `loop.py` | hashed seeds, static (baseline) arms, the active-learning loop, scoring |
| `esmini_case.py` | the deterministic esmini cut-in (`stp.cutin`) and the noisy R157 cut-in (`stp.noise`) as problems, scored against the committed reference grids in `results/` |

Known-answer tests for the harness: `tests/test_course_harness.py`.

## Run

```bash
scripts/setup_env.sh                                              # pinned environment with esmini
uv pip install --python .venv/bin/python -r env/requirements-notebooks.txt
.venv/bin/python -m pytest -q tests/test_course_harness.py         # harness, seconds
.venv/bin/python -m pytest -q -o addopts="" -m notebook tests/test_notebooks.py   # executes every notebook
.venv/bin/python notebooks/course/build.py 32 --execute            # rebuild one notebook from sources/nb_32.py
```

The notebooks are generated from `sources/nb_XX.py` by `build.py`; edit the source, not the `.ipynb`.
