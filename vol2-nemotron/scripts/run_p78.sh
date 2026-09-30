#!/usr/bin/env bash
# P78 · one stage per call. Stages: fp8 (G1, Vol.1) · quality_n3 (G2) · quality_n2 (G3) · nimvllm (G4 speed and answers) ·
# quality_v3 (G4 quality arms) · rerun (G6) · n2up (G5). Results: <volume>/results/p78_<stage>/ (the result directory is
# the one next to the harness; no volume directory name is written here). Model output text goes to the process bucket
# outside the repository.
# Before every stage: the old-directory gate; in a real run the stage's pre-registration and its .sha256 must be present
# and unchanged, and the results must not exist. The harness's exit code is written into the results directory.
# env: NGC_ENV_FILE (--env-file of NIM containers, never read) · NIM_CACHE_DIR · V_CACHE_DIR · AIPERF · PY (python with
#      psutil and requests) · LMPY (python of the lm-eval venv) · TOK_LLAMA · TOK_ROOT (a1/ a2/) · OLLAMA_STORE ·
#      RAW_ROOT (the process bucket outside the repository) · DEADLINE (HH:MM, default 08:00) · TEST=1 -> harness_test/<tag>/ (short), MOCK=1 (quality stages only, no GPU)
set -u
SD="$(cd "$(dirname "$0")" && pwd -W)"
REPO="$(cd "$SD/../.." && pwd -W)"
STAGE="${1:?stage}"
TAG="p78_${STAGE}_$(date +%Y%m%dT%H%M%S)"
DEADLINE="${DEADLINE:-08:00}"
find_script(){ ls "$REPO"/*/scripts/"$1" 2>/dev/null | head -1; }
case "$STAGE" in
  fp8)        H="$(find_script p78_fp8_clean.py)"; RESNAME=p78_fp8_clean;   PRED=prediction_p78_fp8.json ;;
  quality_n3|quality_n2|quality_v3) H="$SD/p78_quality.py"; RESNAME=p78_quality; PRED=prediction_p78_quality.json ;;
  nimvllm)    H="$SD/p78_nim_vs_vllm.py"; RESNAME=p78_nim_vs_vllm; PRED=prediction_p78_nim_vs_vllm.json ;;
  rerun)      H="$SD/p78_clean_rerun.py"; RESNAME=p78_clean_rerun; PRED=prediction_p78_clean_rerun.json ;;
  n2up)       H="$SD/p78_n2_upstream.py"; RESNAME=p78_n2_upstream; PRED=prediction_p78_n2_upstream.json ;;
  *) echo "unknown stage $STAGE"; exit 2 ;;
esac
RES="$(cd "$(dirname "$H")/../results" && pwd -W)/$RESNAME"
case "$STAGE" in quality_n3) ARMS=N3 ;; quality_n2) ARMS=N2 ;; quality_v3) ARMS=V3B1,V3B2 ;; *) ARMS="" ;; esac
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; else OUT="$RES"; fi
RAW="${RAW_ROOT:?}/$TAG"                       # the process bucket (model output text), outside the repository; one directory per run
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }
echo "run $TAG · stage $STAGE · test=${TEST:-0} · mock=${MOCK:-0} · $(date +%FT%T%z)"
"${PY:?}" "$REPO/tools/renumber_dirs.py" check-old-dirs > "$LOG/old_dir_gate.txt" 2>&1 || { echo "OLD-DIRECTORY GATE FAILED"; cat "$LOG/old_dir_gate.txt"; exit 5; }
if [ "${TEST:-0}" != 1 ]; then
  (cd "$RES" && tr -d '\r' < "${PRED%.json}.sha256" | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  case "$STAGE" in
    quality_*) grep -q "\"arm\": \"${ARMS%%,*}\"" "$OUT/items.jsonl" 2>/dev/null && { echo "RESULT EXISTS for $ARMS — one run only"; exit 2; } ;;
    *) [ ! -f "$OUT/events.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; } ;;
  esac
fi
if [ "${MOCK:-0}" != 1 ]; then
  [ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
  echo "$(date +%FT%T%z) | steam processes: $(tasklist 2>/dev/null | grep -i -c '^steam' || true) | ollama processes: $(tasklist 2>/dev/null | grep -i -c '^ollama' || true)" | tee -a "$OUT/ctx.txt"
  echo "driver: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader | tr -d '\r') · aiperf: $("${AIPERF:?}" --version 2>&1 | tr -d '\r' | head -1)" | tee -a "$OUT/versions.txt"
  for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done
fi
T=""; [ "${TEST:-0}" = 1 ] && T="--test"
case "$STAGE" in
  fp8)       MSYS_NO_PATHCONV=1 "$PY" "$H" --out "$OUT" --aiperf "$AIPERF" --tokenizer "${TOK_LLAMA:?}" --store "${OLLAMA_STORE:?}" $T ;;
  quality_*) Q=""; [ "${TEST:-0}" = 1 ] && Q="--test ${TEST_ITEMS:-8}"; M=""; [ "${MOCK:-0}" = 1 ] && M="--mock --mock-die-after ${MOCK_DIE:-30}"
             MSYS_NO_PATHCONV=1 "$PY" "$H" --arms "$ARMS" --lmpy "${LMPY:?}" --out "$OUT" --raw "$RAW" --deadline "$DEADLINE" $Q $M ;;
  nimvllm)   MSYS_NO_PATHCONV=1 "$PY" "$H" --out "$OUT" --aiperf "$AIPERF" --tokenizer "${TOK_ROOT:?}/a2" $T ;;
  rerun)     MSYS_NO_PATHCONV=1 "$PY" "$H" --out "$OUT" --aiperf "$AIPERF" --tokenizer-root "${TOK_ROOT:?}" --deadline "$DEADLINE" ${SWEEPS:+--sweeps $SWEEPS} $T ;;
  n2up)      MSYS_NO_PATHCONV=1 "$PY" "$H" --out "$OUT" --aiperf "$AIPERF" --tokenizer "${TOK_ROOT:?}/a1" $T ;;
esac > "$LOG/harness.stdout.txt" 2> "$LOG/harness.stderr.txt"
rc=$?
echo "$STAGE rc=$rc $(date +%FT%T%z)" | tee -a "$OUT/exit_code.txt"
[ "${MOCK:-0}" = 1 ] || echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
exit $rc
