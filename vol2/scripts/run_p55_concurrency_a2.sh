#!/usr/bin/env bash
# Vol.2 · A2 concurrency with the sequence cap raised · one run per cap · profiles C and R · levels 1..2N · fresh-container repeat of the top two levels.
# env: SEQS (64, 128 or 256; required) · NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · AIPERF · TOKENIZER_ROOT · PYTHON (optional)
#      TEST=1 -> harness_test/: profile C, levels 1,4, short durations
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
N="${SEQS:?SEQS must be 64, 128 or 256}"
case "$N" in 64|128|256) ;; *) echo "SEQS must be 64, 128 or 256"; exit 2;; esac
NN=$(printf '%03d' "$N")
RES=vol2/results/p55_concurrency_a2_$NN
TAG="p55conc_s${N}_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--test --profiles ${TEST_PROFILES:-C} --levels 1,4"; else OUT="$RES"; EXTRA=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }

echo "run $TAG · seqs=$N · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p55_concurrency_a2_$NN.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/levels.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
echo "aiperf: $("${AIPERF:?}" --version 2>&1 | tr -d '\r' | head -1)" | tee "$OUT/versions.txt"
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done

MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p55_concurrency_a2.py --out "$OUT" --aiperf "${AIPERF:?}" --tokenizer-root "${TOKENIZER_ROOT:?}" --seqs "$N" $EXTRA 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
"$PY" vol2/scripts/p55_concurrency_a2_analyze.py "$OUT" --seqs "$N" > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
