#!/usr/bin/env bash
# Vol.1-A revisit (P54) · NIM 2.0.12 against upstream vLLM v0.27.1 on the same Llama 3.1 8B bf16 weight files.
# STAGE=all (default) runs stack -> attempts -> single -> conc; STAGE=<one of them> runs one stage.
# Results: vol2/results/p54_engine/ (stack.json · attempts.jsonl · v_args.json · attempts_summary.json · single/ · conc/).
# env: NGC_ENV_FILE (passed to --env-file of arm N, never read) · NIM_CACHE_DIR · V_CACHE_DIR (arm V's persistent cache) · AIPERF · TOKENIZER_ROOT (dirs n/ and v/,
#      each holding the snapshot's tokenizer files) · PYTHON (optional) · SEQS (the sequence cap P3 checks; 256)
#      TEST=1 -> harness_test/<tag>/ (single: the sample's 3 harness-test questions; conc: LEVELS, default 1,2, profile C, no fresh)
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol2/results/p54_engine
TAG="p54_$(date +%Y%m%dT%H%M%S)"
SEQS="${SEQS:-256}"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--test"; else OUT="$RES"; EXTRA=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }
echo "run $TAG · stage ${STAGE:-all} · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p54_engine.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
VARGS="$RES/v_args.json"; [ "${TEST:-0}" = 1 ] && VARGS="${TEST_VARGS:-$OUT/v_args.json}"
once(){ [ "${TEST:-0}" = 1 ] || [ ! -e "$1" ] || { echo "RESULT EXISTS ($1) — one run only"; exit 2; }; }
stage(){  # $1 name
  echo "## $1 start $(date +%FT%T%z) | $(ctx)" | tee -a "$OUT/ctx.txt"
  case "$1" in
    stack)    once "$OUT/stack.json"
              MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p54_engine.py stack --out "$OUT" 2>"$LOG/stack.stderr.txt"; rc=$? ;;
    attempts) once "$OUT/attempts.jsonl"
              MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p54_engine.py attempts --out "$OUT" 2>"$LOG/attempts.stderr.txt"; rc=$?
              "$PY" vol2/scripts/p54_attempts_analyze.py "$OUT" > "$LOG/attempts_analyze.stdout.txt" 2>&1 || true ;;
    single)   once "$OUT/single/requests.jsonl"; mkdir -p "$OUT/single"
              MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p54_engine.py single --out "$OUT/single" --vargs "$VARGS" $EXTRA 2>"$LOG/single.stderr.txt"; rc=$?
              "$PY" vol2/scripts/p54_single_analyze.py "$OUT/single" $([ "${TEST:-0}" = 1 ] && echo --any-n) > "$LOG/single_analyze.stdout.txt" 2>&1 || true ;;
    conc)     once "$OUT/conc/levels.jsonl"; mkdir -p "$OUT/conc"
              if [ "${TEST:-0}" = 1 ]; then CX="--test --levels ${LEVELS:-1,2} --profiles C"; else CX=""; fi
              MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p54_engine.py conc --out "$OUT/conc" --vargs "$VARGS" --aiperf "$AIPERF" --tokenizer-root "$TOKENIZER_ROOT" $CX 2>"$LOG/conc.stderr.txt"; rc=$?
              "$PY" vol2/scripts/p54_conc_analyze.py "$OUT/conc" --seqs "$SEQS" > "$LOG/conc_analyze.stdout.txt" 2>&1 || true ;;
  esac
  echo "## $1 exit $rc $(date +%FT%T%z) | $(ctx)" | tee -a "$OUT/ctx.txt"
  return $rc
}
rc=0
for s in $( [ "${STAGE:-all}" = all ] && echo "stack attempts single conc" || echo "${STAGE}" ); do
  stage "$s" || { rc=$?; echo "stage $s failed rc=$rc; later stages not run"; break; }
  sleep 20
done
echo "P54 done rc=$rc $(date +%FT%T%z)"
exit $rc
