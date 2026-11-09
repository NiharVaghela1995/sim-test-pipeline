#!/usr/bin/env bash
# Rebuild the pinned environment. No sudo. Downloads about 80 MB.
set -euo pipefail
cd "$(dirname "$0")/.."
. env/esmini.lock 2>/dev/null || true
url=$(grep '^url=' env/esmini.lock | cut -d= -f2-); sha=$(grep '^sha256=' env/esmini.lock | cut -d= -f2); tag=$(grep '^tag=' env/opensbt.lock | cut -d= -f2); commit=$(grep '^commit=' env/opensbt.lock | cut -d= -f2)
mkdir -p third_party/esmini_dl
[ -f third_party/esmini_dl/esmini-bin_Linux.zip ] || curl -sSL -o third_party/esmini_dl/esmini-bin_Linux.zip "$url"
echo "$sha  third_party/esmini_dl/esmini-bin_Linux.zip" | sha256sum -c -
[ -d third_party/esmini_v3.11.0 ] || unzip -q third_party/esmini_dl/esmini-bin_Linux.zip -d third_party/esmini_v3.11.0
[ -d third_party/opensbt-core ] || git clone -q --depth 1 --branch "$tag" https://github.com/opensbt/opensbt-core.git third_party/opensbt-core
[ "$(git -C third_party/opensbt-core rev-parse HEAD)" = "$commit" ]
uv venv --python 3.10 .venv -q --allow-existing
uv pip install -q --python .venv/bin/python -r env/requirements.lock
uv pip install -q --python .venv/bin/python --no-deps -e third_party/opensbt-core
echo "environment ready"
