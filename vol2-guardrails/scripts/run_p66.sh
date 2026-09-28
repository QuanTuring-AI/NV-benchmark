#!/usr/bin/env bash
# Vol.2 (directory vol1b/), P66 · NeMo Guardrails 0.23.0 under load: four arms (N, P, R3, R1024) at 1-128 concurrent requests,
# and detection under load (Part D). Results: vol1b/results/p66_rails_under_load/.
# The Windows-native Ollama (if running) is stopped before the run and started again after it.
# env: NGC_ENV_FILE (--env-file of the NIM container, never read) · NIM_CACHE_DIR · AIPERF · TOKENIZER · PY (AIPerf venv python) ·
#      GRPY (Guardrails 0.23.0 venv python) · OLLAMA_APP · TEST=1 -> harness_test/<tag>/ (ARMS to choose)
set -u
cd "$(dirname "$0")/../.."
RES=vol1b/results/p66_rails_under_load
TAG="p66_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--test --arms ${ARMS:-N,R3}"; mkdir -p "$OUT"; cp -r "$RES/configs" "$OUT/"; else OUT="$RES"; EXTRA=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }
echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p66.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/levels.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
native_before=$(tasklist 2>/dev/null | grep -i -c "^ollama" || true)
echo "$(date +%FT%T%z) | windows-native ollama processes before: $native_before" | tee -a "$OUT/ctx.txt"
if [ "$native_before" -gt 0 ]; then taskkill //IM "ollama app.exe" //F >/dev/null 2>&1 || true; taskkill //IM "ollama.exe" //F >/dev/null 2>&1 || true; sleep 3; fi
echo "$(date +%FT%T%z) | windows-native ollama processes after stop: $(tasklist 2>/dev/null | grep -i -c '^ollama' || true)" | tee -a "$OUT/ctx.txt"
echo "aiperf: $("${AIPERF:?}" --version 2>&1 | tr -d '\r' | head -1)" | tee "$OUT/versions.txt"
echo "nim image: $(docker image inspect nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12 --format '{{.Id}} {{json .RepoDigests}}')" | tee -a "$OUT/versions.txt"
"${GRPY:?}" -c "import nemoguardrails, httpx, sys; from nemoguardrails.llm.clients.constants import DEFAULT_CONNECTION_LIMITS as L; print('nemoguardrails', nemoguardrails.__version__, '· httpx', httpx.__version__, '· python', sys.version.split()[0], '· client pool max_connections', L.max_connections, 'max_keepalive', L.max_keepalive_connections)" 2>&1 | tr -d '\r' | tail -1 | tee -a "$OUT/versions.txt"
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done
MSYS_NO_PATHCONV=1 "${PY:?}" vol1b/scripts/p66_rails_under_load.py --out "$OUT" --aiperf "$AIPERF" --tokenizer "${TOKENIZER:?}" --grpy "$GRPY" $EXTRA > "$LOG/harness.stdout.txt" 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
if [ "$native_before" -gt 0 ] && [ -n "${OLLAMA_APP:-}" ]; then (cmd //c start "" "$OLLAMA_APP" >/dev/null 2>&1 &) ; sleep 5; fi
echo "$(date +%FT%T%z) | windows-native ollama processes after the run: $(tasklist 2>/dev/null | grep -i -c '^ollama' || true)" | tee -a "$OUT/ctx.txt"
exit $rc
