#!/usr/bin/env bash
# Vol.2 answer-completion run · one run · four alternating blocks (A1, A2, A1, A2) at max_tokens 4096.
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · PYTHON (optional) · TEST=1 -> harness_test/
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol2/results/p53_answer
SAMPLE_DIR=vol1b/results/p20_coresidence
TAG="p53ans_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; FLAG="--test"; N="--n 3"; else OUT="$RES"; FLAG=""; N=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }

echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p53_answer.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/requests.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
(cd $SAMPLE_DIR && tr -d '\r' < sample.sha256 | sha256sum -c -) || { echo "SAMPLE-MISSING-OR-CHANGED"; exit 2; }
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; timeout 30s docker ps; exit 3; }
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done

MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p53_answer.py --out "$OUT" $FLAG 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
"$PY" vol2/scripts/p53_answer_analyze.py "$OUT" --bytes A1=17776454656,A2=3590938272 $N > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
