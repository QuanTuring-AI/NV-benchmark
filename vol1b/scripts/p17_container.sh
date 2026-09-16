#!/usr/bin/env bash
# P17 · NIM container lifecycle on the Vol.1-B cell ④ NIM stack (no Guardrails).
# usage: p17_container.sh start <name> <logdir>   → waits for READY, discards the first request, records engine settings
#        p17_container.sh stop  <name> <logdir>
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
set -u
cd "$(dirname "$0")/../.."
ACT=$1; NAME=$2; LOG=$3; mkdir -p "$LOG"
IMG="nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12"
IDX="sha256:d2c94c1d654c3e80b8bc08cc83298d2ba4e219dff41d1092555795edb93c6545"
PROF="092ed4213624e774d24cdaf84e3b6222839bab2008a21d3c214ab46626366f90"
MODEL="meta/llama-3.1-8b-instruct"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\n'; }

if [ "$ACT" = stop ]; then
  timeout 60s docker logs "$NAME" > "$LOG/nim_full.log.txt" 2>&1
  echo "$(date +%FT%T%z) | stop | $(ctx)" | tee -a "$LOG/ctx.txt"
  timeout 60s docker rm -f "$NAME" >/dev/null; sleep 5
  echo "$(date +%FT%T%z) | after stop | $(ctx)" | tee -a "$LOG/ctx.txt"
  exit 0
fi

[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; timeout 30s docker ps; exit 3; }
timeout 30s docker image inspect "$IMG" --format '{{join .RepoDigests " "}}' | grep -qF "${IDX#sha256:}" || { echo "INDEX-DIGEST-MISMATCH"; exit 4; }
for i in 1 2 3 4 5; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$LOG/ctx.txt"; sleep 2; done
echo "$(date +%FT%T%z) | prelaunch | $(ctx)" | tee -a "$LOG/ctx.txt"
MSYS_NO_PATHCONV=1 timeout 90s docker run -d --name "$NAME" --gpus all -p 8000:8000 --env-file "${NGC_ENV_FILE:?}" \
  -e NIM_MODEL_PROFILE="$PROF" -e NIM_MAX_MODEL_LEN=8192 -e VLLM_USE_V2_MODEL_RUNNER=0 -v "${NIM_CACHE_DIR:?}:/opt/nim/.cache" "$IMG" \
  2>"$LOG/docker_run.stderr.txt" || { echo "RUN-FAILED"; cat "$LOG/docker_run.stderr.txt"; exit 1; }
ok=0
for i in $(seq 1 120); do
  L=$(timeout 25s docker logs "$NAME" 2>&1)
  if echo "$L" | grep -qaE "Uvicorn running|Application startup complete"; then ok=1; break; fi
  if echo "$L" | grep -qaE "Traceback|OutOfMemory|No available memory"; then break; fi
  [ -z "$(timeout 25s docker ps -q --filter name=$NAME)" ] && break
  sleep 10
done
timeout 30s docker logs "$NAME" > "$LOG/nim_startup.log.txt" 2>&1
[ $ok = 1 ] || { echo "NOT-READY $(date +%FT%T%z)"; exit 1; }
echo "READY $(date +%FT%T%z)"
echo "$(date +%FT%T%z) | ready | $(ctx)" | tee -a "$LOG/ctx.txt"
# engine settings: the process command line inside the container, and the server's own metrics page
timeout 30s docker exec "$NAME" sh -c 'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline 2>/dev/null; echo; done' | grep -a . > "$LOG/container_cmdlines.txt"
curl -s --max-time 20 http://localhost:8000/metrics > "$LOG/metrics_at_ready.txt"
grep -aF "clamping gpu_memory_utilization" "$LOG/nim_startup.log.txt" > "$LOG/memory_clamp_line.txt"
# first request after READY: sent, recorded, never counted
curl -s --max-time 120 -o "$LOG/first_request_discarded.json" -w "first request discarded · http %{http_code} · %{time_total}s\n" \
  http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}],\"max_tokens\":16,\"temperature\":0}" | tee "$LOG/first_request_discarded.txt"
exit 0
