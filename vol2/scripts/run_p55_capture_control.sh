#!/usr/bin/env bash
# Vol.2 · A2 capture-size control · two containers in one run (s256_default, then s256_cg064) · profile C · levels 1, 16, 32.
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · AIPERF · TOKENIZER_ROOT · PYTHON (optional)
#      TEST=1 -> harness_test/: one condition (TEST_CONDITIONS, default s256_cg064), level 1, short durations
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol2/results/p55_capture_control
TAG="p55cgctl_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--test --levels 1 --conditions ${TEST_CONDITIONS:-s256_cg064}"; else OUT="$RES"; EXTRA=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }
echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p55_capture_control.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/levels.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
echo "aiperf: $("${AIPERF:?}" --version 2>&1 | tr -d '\r' | head -1)" | tee "$OUT/versions.txt"
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done
MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p55_capture_control.py --out "$OUT" --aiperf "${AIPERF:?}" --tokenizer-root "${TOKENIZER_ROOT:?}" $EXTRA 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
"$PY" vol2/scripts/p55_capture_control_analyze.py "$OUT" > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt" || true
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
