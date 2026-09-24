#!/usr/bin/env bash
# Vol.2 Guardrails 0.23.0 × Nemotron · one run · both arms, 45 questions × 3 rounds, N/G rotated per question.
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · GR023_PY (python of the Guardrails 0.23.0 venv) · PYTHON (optional)
#      TEST=1 -> harness_test/ (A1 only, 2 questions, 1 round)
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol2/results/p53_guardrails
TAG="p53gr_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--arms A1 --question-limit 2 --rounds 1"; NQ="--n-questions 2 --rounds 1"; else OUT="$RES"; EXTRA=""; NQ=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }

echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p53_guardrails.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/rows.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
"${GR023_PY:?}" -c "import nemoguardrails,sys;print('nemoguardrails',nemoguardrails.__version__,'python',sys.version.split()[0])" | tr -d '\r' | tee "$OUT/versions.txt"
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done

MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p53_guardrails.py --out "$OUT" --gr023-py "${GR023_PY:?}" $EXTRA 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
"$PY" vol2/scripts/p53_guardrails_analyze.py "$OUT" $NQ > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
