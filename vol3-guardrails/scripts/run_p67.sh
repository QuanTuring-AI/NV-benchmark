#!/usr/bin/env bash
# Vol.2 (directory vol1b/), P67 · the Guardrails server's worker count W and keep-alive timeout K at 32 / 64 / 128 concurrent
# requests, and detection under load on four workers. Results: vol1b/results/p67_rails_server_config/.
# The Windows-native Ollama (if running) is stopped before the run and started again after it.
# env: NGC_ENV_FILE (--env-file of the NIM container, never read) · NIM_CACHE_DIR · AIPERF · TOKENIZER · PY (AIPerf venv python) ·
#      GRPY (Guardrails 0.23.0 server venv python) · OLLAMA_APP · TEST=1 -> harness_test/<tag>/ (ONLY to choose labels)
set -u
cd "$(dirname "$0")/../.."
RES=vol1b/results/p67_rails_server_config
TAG="p67_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; EXTRA="--test --only ${ONLY:-N,R3_W4K75}"; mkdir -p "$OUT"; cp -r "$RES/configs" "$OUT/"; else OUT="$RES"; EXTRA=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }
echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && tr -d '\r' < prediction_p67.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/levels.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
native_before=$(tasklist 2>/dev/null | grep -i -c "^ollama" || true)
echo "$(date +%FT%T%z) | windows-native ollama processes before: $native_before" | tee -a "$OUT/ctx.txt"
if [ "$native_before" -gt 0 ]; then taskkill //IM "ollama app.exe" //F >/dev/null 2>&1 || true; taskkill //IM "ollama.exe" //F >/dev/null 2>&1 || true; sleep 3; fi
echo "$(date +%FT%T%z) | windows-native ollama processes after stop: $(tasklist 2>/dev/null | grep -i -c '^ollama' || true)" | tee -a "$OUT/ctx.txt"
echo "aiperf: $("${AIPERF:?}" --version 2>&1 | tr -d '\r' | head -1)" | tee "$OUT/versions.txt"
echo "nim image: $(docker image inspect nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12 --format '{{.Id}} {{json .RepoDigests}}')" | tee -a "$OUT/versions.txt"
"${GRPY:?}" -c "import nemoguardrails, httpx, uvicorn, h11, sys; from nemoguardrails.llm.clients.constants import DEFAULT_CONNECTION_LIMITS as L; print('nemoguardrails', nemoguardrails.__version__, '· httpx', httpx.__version__, '· uvicorn', uvicorn.__version__, '· h11', h11.__version__, '· python', sys.version.split()[0], '· client pool max_connections', L.max_connections, 'max_keepalive', L.max_keepalive_connections)" 2>&1 | tr -d '\r' | tail -1 | tee -a "$OUT/versions.txt"
"${PY:?}" -c "import psutil, os; print('host physical cores', psutil.cpu_count(logical=False), '· logical', psutil.cpu_count(), '· os', os.name)" 2>&1 | tr -d '\r' | tee -a "$OUT/versions.txt"
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done
MSYS_NO_PATHCONV=1 "${PY:?}" vol1b/scripts/p67_rails_server_config.py --out "$OUT" --aiperf "$AIPERF" --tokenizer "${TOKENIZER:?}" --grpy "$GRPY" $EXTRA > "$LOG/harness.stdout.txt" 2>"$LOG/harness.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
if [ "$native_before" -gt 0 ] && [ -n "${OLLAMA_APP:-}" ]; then (cmd //c start "" "$OLLAMA_APP" >/dev/null 2>&1 &) ; sleep 5; fi
echo "$(date +%FT%T%z) | windows-native ollama processes after the run: $(tasklist 2>/dev/null | grep -i -c '^ollama' || true)" | tee -a "$OUT/ctx.txt"
exit $rc
