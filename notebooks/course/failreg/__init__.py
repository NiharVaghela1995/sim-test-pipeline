"""Shared harness for the course notebooks: test problems with known failure regions, metrics, designs, surrogates,
acquisition and replication rules, and the search loop."""
import os

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_k, "1")

from . import problems, metrics, designs, models, acquisition, replication, loop  # noqa: E402,F401
