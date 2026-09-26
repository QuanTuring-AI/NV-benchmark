#!/usr/bin/env bash
# Vol.1-A revisit, P62 Q2 + Q4 · profile C at 1, 2, 4, 8 on the five P59 configurations; O-Q4 also 9, 12, 16.
# Results: vol1a-revisit/results/p62_levels/ (levels.jsonl · events.jsonl · concurrency.jsonl · ollama_ps_O-Q4.jsonl · analysis.json).
# The Windows-native Ollama (if running) is stopped before the run and started again after it.
# env: NGC_ENV_FILE (passed to --env-file of the NIM arms, never read) · NIM_CACHE_DIR · AIPERF · OLLAMA_APP · TOKENIZER ·
#      OLLAMA_STORE · PY · TEST=1 -> harness_test/<tag>/ (two levels, 20 s; ARMS to choose)
set -u
cd "$(dirname "$0")/../.."
RES=vol1a-revisit/results/p62_levels
TAG="p62l_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--test --arms ${ARMS:-O-Q4,N-BF16}"; else OUT="$RES"; EXTRA=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }
echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p62_levels.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/levels.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
native_before=$(tasklist 2>/dev/null | grep -i -c "^ollama" || true)
echo "$(date +%FT%T%z) | windows-native ollama processes before: $native_before" | tee -a "$OUT/ctx.txt"
if [ "$native_before" -gt 0 ]; then taskkill //IM "ollama app.exe" //F >/dev/null 2>&1 || true; taskkill //IM "ollama.exe" //F >/dev/null 2>&1 || true; sleep 3; fi
echo "$(date +%FT%T%z) | windows-native ollama processes after stop: $(tasklist 2>/dev/null | grep -i -c '^ollama' || true)" | tee -a "$OUT/ctx.txt"
echo "aiperf: $("${AIPERF:?}" --version 2>&1 | tr -d '\r' | head -1)" | tee "$OUT/versions.txt"
echo "ollama image: $(docker image inspect ollama/ollama:latest --format '{{.Id}} {{json .RepoDigests}}')" | tee -a "$OUT/versions.txt"
echo "nim image: $(docker image inspect nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12 --format '{{.Id}} {{json .RepoDigests}}')" | tee -a "$OUT/versions.txt"
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done
MSYS_NO_PATHCONV=1 "${PY:?}" vol1a-revisit/scripts/p62_levels.py --out "$OUT" --aiperf "$AIPERF" --tokenizer "${TOKENIZER:?}" --store "${OLLAMA_STORE:?}" $EXTRA 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
"${PY}" vol1a-revisit/scripts/p62_levels_analyze.py "$OUT" vol1a-revisit/results/p59_nim_value/analysis.json > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt" || true
if [ "$native_before" -gt 0 ] && [ -n "${OLLAMA_APP:-}" ]; then (cmd //c start "" "$OLLAMA_APP" >/dev/null 2>&1 &) ; sleep 5; fi
echo "$(date +%FT%T%z) | windows-native ollama processes after the run: $(tasklist 2>/dev/null | grep -i -c '^ollama' || true)" | tee -a "$OUT/ctx.txt"
exit $rc
