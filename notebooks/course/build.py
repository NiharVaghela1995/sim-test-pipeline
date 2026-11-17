"""Writes the course notebooks. Usage: python notebooks/course/build.py [NAME ...] [--execute]

The cell sources live in sources/nb_XX.py (one per notebook, a list CELLS of ("md" | "code", text)).
With --execute the notebook is run from a clean kernel and saved with its outputs.
"""
import importlib.util
import sys
import time
from pathlib import Path
import nbformat as nbf

HERE = Path(__file__).resolve().parent
NAMES = {"32": "32_evaluation_harness", "13": "13_initial_designs", "14": "14_surrogates", "15": "15_acquisition", "17": "17_replication"}

SETUP = '''import sys, time, warnings
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
HERE = Path.cwd().resolve()
HERE = HERE if (HERE / "failreg").exists() else HERE / "notebooks/course"
sys.path.insert(0, str(HERE))
from failreg import problems as P, metrics as M, designs as D, models as MD, acquisition as A, replication as R, loop as L, plots as PL
warnings.filterwarnings("ignore")
PL.style(); T0 = time.time()'''

END = 'print(f"notebook ran in {time.time() - T0:.0f} s")'


def load(key):
    spec = importlib.util.spec_from_file_location(f"nb_{key}", HERE / "sources" / f"nb_{key}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.CELLS


def build(key, execute=False):
    nb = nbf.v4.new_notebook()
    cells = load(key)
    out = []
    for i, (kind, src) in enumerate(cells):
        src = src.strip("\n")
        out.append(nbf.v4.new_markdown_cell(src) if kind == "md" else nbf.v4.new_code_cell(src))
        if i == 0:
            out.append(nbf.v4.new_code_cell(SETUP))
    out.append(nbf.v4.new_code_cell(END))
    nb.cells = out
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    path = HERE / f"{NAMES[key]}.ipynb"
    if execute:
        from nbclient import NotebookClient
        t = time.time()
        NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(HERE)}}).execute()
        print(f"{path.name}: executed in {time.time() - t:.0f} s")
    nbf.write(nb, path)
    return path


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for k in args or NAMES:
        print(build(k, "--execute" in sys.argv))
