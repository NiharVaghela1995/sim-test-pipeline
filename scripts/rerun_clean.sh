#!/usr/bin/env bash
# Rerun one campaign from its manifest in a fresh clone of the current commit with a freshly built environment.
# Usage: scripts/rerun_clean.sh results/gp_boundary/manifests/gp_al_0.json [work dir]
# The esmini zip and the OpenSBT checkout are copied from this tree to avoid downloads; setup_env.sh still checks the
# zip's sha256 and the OpenSBT commit against env/*.lock.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
manifest="$1"; work="${2:-$(mktemp -d)}"
commit=$(git -C "$here" rev-parse HEAD)
git clone -q "$here" "$work/repo"; git -C "$work/repo" checkout -q "$commit"
mkdir -p "$work/repo/third_party/esmini_dl"
cp "$here/third_party/esmini_dl/esmini-bin_Linux.zip" "$work/repo/third_party/esmini_dl/"
cp -r "$here/third_party/opensbt-core" "$work/repo/third_party/"
cd "$work/repo"
scripts/setup_env.sh
echo "commit $commit, clean clone in $work/repo"
PYTHONPATH=src .venv/bin/python -m stp.cutin.campaign rerun "$manifest"
