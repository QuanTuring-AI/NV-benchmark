#!/usr/bin/env bash
# Vol.2 long context · addendum · one run · A2 at 1k/4k/16k/64k and A1 at 16k, timed warm-up before the measured requests.
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · PYTHON (optional) · TEST=1 -> harness_test/ (A2, 1k, 2 warm-up + 2 requests)
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol2/results/p53_longctx_addendum
TAG="p53ctxadd_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--test --arms A2 --depths 1024"; else OUT="$RES"; EXTRA=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }

echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p53_longctx_addendum.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/requests.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done

if [ "${TEST:-0}" = 1 ]; then
  MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p53_longctx_addendum.py --out "$OUT" $EXTRA 2>"$LOG/harness.stderr.txt"; rc=$?
else
  MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p53_longctx_addendum.py --out "$OUT" --arms A2 --depths 1024,4096,16384,65536 2>"$LOG/harness.stderr.txt"; rc=$?
  MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p53_longctx_addendum.py --out "$OUT" --arms A1 --depths 16384 2>>"$LOG/harness.stderr.txt"; rc2=$?; [ $rc -eq 0 ] && rc=$rc2
fi
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
"$PY" vol2/scripts/p53_longctx_addendum_analyze.py "$OUT" > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
