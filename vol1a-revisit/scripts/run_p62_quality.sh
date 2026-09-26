#!/usr/bin/env bash
# Vol.1-A revisit, P62 Q1 · answer quality of N-BF16, N-FP8, O-Q4, O-FP16 on GSM8K, IFEval and a 2,850-item MMLU sample.
# Results: vol1a-revisit/results/p62_quality/ (items/ · events_public.jsonl · analysis.json · recompute_check.txt; raw/ and
# events.jsonl stay local). The Windows-native Ollama (if running) is stopped before the run and started again after it.
# env: NGC_ENV_FILE (--env-file of the NIM arms, never read) · NIM_CACHE_DIR · OLLAMA_APP · TOKENIZER · OLLAMA_STORE ·
#      LMPY (python of the lm-eval venv) · TEST=<n items> -> harness_test/<tag>/ (ARMS to choose)
set -u
cd "$(dirname "$0")/../.."
RES=vol1a-revisit/results/p62_quality
TAG="p62q_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" != 0 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--test $TEST --arms ${ARMS:-N-BF16,O-Q4}"; mkdir -p "$OUT"; cp "$RES/g1_scorer_controls.json" "$RES/mmlu_sample_ids.json" "$OUT/"; else OUT="$RES"; EXTRA=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }
echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" = 0 ]; then
  (cd $RES && tr -d '\r' < prediction_p62_quality.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -d "$OUT/items" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
native_before=$(tasklist 2>/dev/null | grep -i -c "^ollama" || true)
echo "$(date +%FT%T%z) | windows-native ollama processes before: $native_before" | tee -a "$OUT/ctx.txt"
if [ "$native_before" -gt 0 ]; then taskkill //IM "ollama app.exe" //F >/dev/null 2>&1 || true; taskkill //IM "ollama.exe" //F >/dev/null 2>&1 || true; sleep 3; fi
echo "$(date +%FT%T%z) | windows-native ollama processes after stop: $(tasklist 2>/dev/null | grep -i -c "^ollama" || true)" | tee -a "$OUT/ctx.txt"
echo "lm_eval: $("${LMPY:?}" -c 'import lm_eval; print(lm_eval.__version__)' 2>&1 | tr -d '\r')" | tee "$OUT/versions.txt"
echo "ollama image: $(docker image inspect ollama/ollama:latest --format '{{.Id}} {{json .RepoDigests}}')" | tee -a "$OUT/versions.txt"
echo "nim image: $(docker image inspect nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12 --format '{{.Id}} {{json .RepoDigests}}')" | tee -a "$OUT/versions.txt"
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done
MSYS_NO_PATHCONV=1 PYTHONUTF8=1 HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 "$LMPY" vol1a-revisit/scripts/p62_quality.py --out "$OUT" --tokenizer "${TOKENIZER:?}" --store "${OLLAMA_STORE:?}" $EXTRA > "$LOG/harness.stdout.txt" 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
"$LMPY" vol1a-revisit/scripts/p62_quality_postrun.py "$OUT" > "$LOG/postrun.stdout.txt" 2>"$LOG/postrun.stderr.txt"; echo "postrun rc=$?"
if [ "$native_before" -gt 0 ] && [ -n "${OLLAMA_APP:-}" ]; then (cmd //c start "" "$OLLAMA_APP" >/dev/null 2>&1 &) ; sleep 5; fi
echo "$(date +%FT%T%z) | windows-native ollama processes after the run: $(tasklist 2>/dev/null | grep -i -c '^ollama' || true)" | tee -a "$OUT/ctx.txt"
exit $rc
