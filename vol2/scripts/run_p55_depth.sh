#!/usr/bin/env bash
# Vol.2 · depth probes after P53 · one run per experiment.
# EXP=a1_capture   -> results/p55_a1_capture/    conditions a1_4k_default, a1_4k_eager, a1_16k_default, a1_16k_eager (NIM_DISABLE_CUDA_GRAPH, the reverse test), a1_16k_capture (the forward test)
# EXP=longctx_120k -> results/p55_longctx_120k/  conditions a2_120k, a1_120k (~120k prompt tokens at NIM_MAX_MODEL_LEN 131072)
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · PYTHON (optional) · TEST=1 -> harness_test/ (2 warm-up + 2 requests)
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
case "${EXP:?EXP must be a1_capture or longctx_120k}" in
  a1_capture) CONDS="a1_4k_default,a1_4k_eager,a1_16k_default,a1_16k_eager,a1_16k_capture"; REF="";;
  longctx_120k) CONDS="a2_120k,a1_120k"; REF="--ref vol2/results/p53_longctx/analysis.json --ref vol2/results/p53_longctx_addendum/analysis.json";;
  *) echo "EXP must be a1_capture or longctx_120k"; exit 2;;
esac
RES=vol2/results/p55_$EXP
TAG="p55_${EXP}_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--test"; CONDS="${TEST_CONDS:-$CONDS}"; else OUT="$RES"; EXTRA=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }
echo "run $TAG · conditions $CONDS · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p55_$EXP.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/requests.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done
MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p55_depth.py --out "$OUT" --conditions "$CONDS" $EXTRA 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
"$PY" vol2/scripts/p55_depth_analyze.py "$OUT" $REF > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
