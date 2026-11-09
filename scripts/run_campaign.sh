#!/usr/bin/env bash
# Run the campaign until it finishes, restarting after a crash. Progress is checkpointed, so a restart only repeats the last batch.
cd "$(dirname "$0")/.."
export PYTHONPATH=src OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
O=results/raw/campaign_v1; mkdir -p "$O"
for i in $(seq 1 30); do
  .venv/bin/python -m stp.campaign --out "$O" "$@" >> "$O/stdout.log" 2>&1 && exit 0
  echo "$(date '+%F %T') restart $i after exit $?" >> "$O/campaign.log"; sleep 20
done
exit 1
