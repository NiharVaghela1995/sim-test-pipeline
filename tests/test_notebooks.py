"""Every stage notebook must run from a clean kernel in under five minutes."""
import time
from pathlib import Path
import nbformat
import pytest
from nbclient import NotebookClient

DIR = Path(__file__).resolve().parents[1] / "notebooks"
LIMIT_S = 300


@pytest.mark.notebook
@pytest.mark.parametrize("path", sorted(DIR.glob("*.ipynb")), ids=lambda p: p.name)
def test_notebook_runs(path):
    nb = nbformat.read(path, as_version=4)
    t = time.time()
    NotebookClient(nb, timeout=LIMIT_S, kernel_name="python3", resources={"metadata": {"path": str(DIR)}}).execute()
    assert time.time() - t < LIMIT_S, f"{path.name} took more than {LIMIT_S} s"
