#!/usr/bin/env bash
# Campaign v2 under the plan's 8-hour wall-clock cap, restarting after a crash. Exit 3 means the plan's realisation pause.
cd "$(dirname "$0")/.."
export PYTHONPATH=src OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
O=results/raw/campaign_v2; mkdir -p "$O"
END=$(( $(date +%s) + 8 * 3600 ))
for i in $(seq 1 30); do
  LEFT=$(( END - $(date +%s) )); [ "$LEFT" -le 0 ] && { echo "$(date '+%F %T') WALL_CLOCK_CAP" >> "$O/campaign.log"; exit 4; }
  timeout "$LEFT" .venv/bin/python -m stp.v2.campaign "$@" >> "$O/stdout.log" 2>&1; rc=$?
  [ "$rc" -eq 0 ] && exit 0; [ "$rc" -eq 3 ] && exit 3
  echo "$(date '+%F %T') restart $i after exit $rc" >> "$O/campaign.log"; sleep 20
done
exit 1
