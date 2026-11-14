"""Cut-in boundary demo: esmini ACC controller against a scripted cut-in, GP boundary search, baselines.

BLAS threads are pinned to 1 before numpy is imported, so GP fits do not depend on the machine's core count.
The manifest records the values in effect."""
import os

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_k, "1")
