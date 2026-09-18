#!/usr/bin/env bash
# P28 start gate (P30 section 3-2). A wrapper, not an edit: run_p28.sh is bound by SHA-256 in the frozen
# prediction_p28.json, so the free-memory check lives here and run_p28.sh is called unchanged.
# Always writes start_gate.txt (pass or fail). Below the threshold: exit 3, no container, no judgements.jsonl.
# env: same as run_p28.sh (NGC_ENV_FILE is passed through as a path and never read here)
set -u
cd "$(dirname "$0")/../.."
OUT=vol1b/results/p28_judge_isolation; GATE="$OUT/start_gate.txt"
THRESHOLD_MIB=30500
PROVENANCE="threshold: NIM classifies this GPU as busy and filters profiles against free memory at its own sampling instant; desktop occupancy fluctuates ±300 MiB (overlay respawn); 30,500 keeps launches ≥ 1 noise band above every observed failure (max 30,102). Inference, not a measured boundary."
samples=""; min=999999
for i in 1 2 3; do
  f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | tr -d ' \r\n')
  samples="$samples $f"; [ "$f" -lt "$min" ] && min=$f
  sleep 2
done
{
  echo "$(date +%FT%T%z) | P28 start gate"
  echo "free MiB samples:$samples · min $min"
  echo "gate: free >= $THRESHOLD_MIB MiB (P30 section 3-2, raised to 30,500 by P32 section 3-4)"
  echo "$PROVENANCE"
  echo "context: $(nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,driver_version --format=csv,noheader | tr -d '\r\n')"
} >> "$GATE"
if [ "$min" -lt "$THRESHOLD_MIB" ]; then
  echo "decision: NOT STARTED (min $min < $THRESHOLD_MIB)" >> "$GATE"; echo "" >> "$GATE"
  echo "GATE: free $min MiB < $THRESHOLD_MIB -- not starting"; exit 3
fi
echo "decision: PASS -> run_p28.sh (unchanged)" >> "$GATE"; echo "" >> "$GATE"
echo "GATE: free $min MiB >= $THRESHOLD_MIB -- starting run_p28.sh"
exec bash vol1b/scripts/run_p28.sh
