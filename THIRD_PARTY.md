# Third-party software

Neither package below is included in this repository. `scripts/setup_env.sh` downloads both into `third_party/`
(ignored by git), checks them against the pins in `env/esmini.lock` and `env/opensbt.lock`, and installs OpenSBT into the
local virtual environment.

| Software | Version used | Licence | Source |
|---|---|---|---|
| esmini (environment simulator, OpenSCENARIO player) | v3.11.0, Linux binary release `esmini-bin_Linux.zip`, sha256 in `env/esmini.lock` | Mozilla Public License 2.0 (MPL-2.0) | https://github.com/esmini/esmini |
| OpenSBT (search-based testing framework) | 0.1.7, commit `3ace1864802f49e524d9612642bc6feb9d1f0caf` | Apache License 2.0 | https://github.com/opensbt/opensbt-core |

Notes:

- The esmini binary release ships without a licence file; the MPL-2.0 notice is in its source headers and in the
  project's repository. The binaries bundle further libraries under their own licences (see the esmini repository).
- `src/stp/esmini_lib.py` loads esmini's shared library through ctypes and copies none of its code. The ACC controller in
  `src/stp/noise/acc.py` is a Python port of esmini's ACC controller logic. Files derived from MPL-2.0 code stay under
  MPL-2.0, so that file carries an MPL-2.0 notice.
- Python packages (numpy, scipy, scikit-learn, matplotlib, pandas, nbclient and their dependencies) are installed from
  PyPI at the versions pinned in `env/requirements.lock` and `env/requirements-notebooks.txt`, each under its own licence.
