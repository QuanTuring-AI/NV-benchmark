#!/usr/bin/env bash
# Vol.2 speed table · one run · four alternating blocks (A1, A2, A1, A2).
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · PYTHON (optional)
#      TEST=1 runs the same sequence on the sample's three harness-test questions into harness_test/
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol2/results/p50_speed
SAMPLE_DIR=vol1b/results/p20_coresidence
TAG="p50sp_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; FLAG="--test"; N="--n 3"; else OUT="$RES"; FLAG=""; N=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }

echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && sha256sum -c prediction_p50_speed.sha256) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/requests.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
# the sidecar is read through tr: git's line-ending conversion can give the checked-out .sha256 file CRLF endings, and
# sha256sum then looks for a file named "sample.json\r" (seen 2026-09-21 after a branch checkout)
(cd $SAMPLE_DIR && tr -d '\r' < sample.sha256 | sha256sum -c -) || { echo "SAMPLE-MISSING-OR-CHANGED"; exit 2; }
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; timeout 30s docker ps; exit 3; }
curl -s --max-time 5 http://127.0.0.1:11434/api/ps | grep -q '"models":\[\]' || { echo "OLLAMA-MODEL-LOADED"; exit 3; }
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done

MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p50_speed.py --out "$OUT" $FLAG 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
"$PY" vol2/scripts/p50_speed_analyze.py "$OUT" --bytes A1=17776454656,A2=3590938272 $N > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
