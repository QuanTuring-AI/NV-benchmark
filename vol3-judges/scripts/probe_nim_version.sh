#!/usr/bin/env bash
# Startup probe for a Llama 3.1 8B NIM version: list profiles, start the BF16 profile with NIM_MAX_MODEL_LEN=8192,
# wait for READY or failure, save logs and /v1/models, stop. Sends NO inference request.
# usage: probe_nim_version.sh <tag>      env: NGC_ENV_FILE, NIM_CACHE_DIR
set -u
cd "$(dirname "$0")/../.."                                   # repo root
V=$1; SUFFIX="${2:-}"; EXTRA=(); [ -n "${PROBE_EXTRA_ENV:-}" ] && EXTRA=(-e "$PROBE_EXTRA_ENV")
D=vol1b/results/version_select; IMG=nvcr.io/nim/meta/llama-3.1-8b-instruct:$V; N=nim-probe-${V//./}
V="${V}${SUFFIX}"
ENV="${NGC_ENV_FILE:?}"; CACHE="${NIM_CACHE_DIR:?}"
[ -z "$(timeout 20s docker ps -q)" ] || { echo BUSY; exit 3; }
if ! timeout 30s docker image inspect "$IMG" >/dev/null 2>&1; then
  echo "pull $V start $(date +%FT%T%z)" > $D/pull_${V}.txt; timeout 3000s docker pull "$IMG" >> $D/pull_${V}.txt 2>&1; echo "rc=$? end $(date +%FT%T%z)" >> $D/pull_${V}.txt
fi
echo "RepoDigests: $(timeout 30s docker image inspect "$IMG" --format '{{join .RepoDigests " "}}')" > $D/probe_${V}_console.txt
MSYS_NO_PATHCONV=1 timeout 600s docker run --rm --gpus all --env-file "$ENV" -v "$CACHE:/opt/nim/.cache" "$IMG" list-model-profiles > $D/probe_${V}_profiles.txt 2>&1
PROF=$(grep -oE "[0-9a-f]{64} \(vllm-bf16-tp1-pp1-[0-9.]+\)" $D/probe_${V}_profiles.txt | head -1 | cut -d' ' -f1)
echo "bf16 profile: ${PROF:-NONE}" >> $D/probe_${V}_console.txt
[ -n "$PROF" ] || { cat $D/probe_${V}_console.txt; exit 4; }
echo "$(date +%FT%T%z) | prelaunch | $(nvidia-smi --query-gpu=memory.used,utilization.gpu,driver_version --format=csv,noheader)" >> $D/probe_${V}_console.txt
MSYS_NO_PATHCONV=1 timeout 90s docker run -d --name $N --gpus all -p 8000:8000 --env-file "$ENV" -e NIM_MODEL_PROFILE=$PROF -e NIM_MAX_MODEL_LEN=8192 \
  "${EXTRA[@]}" -v "$CACHE:/opt/nim/.cache" "$IMG" >/dev/null 2>$D/probe_${V}_docker_run.stderr.txt || { echo RUN-FAILED >> $D/probe_${V}_console.txt; exit 1; }
echo "extra env: ${PROBE_EXTRA_ENV:-none}" >> $D/probe_${V}_console.txt
ok=0
for i in $(seq 1 120); do
  L=$(timeout 25s docker logs $N 2>&1)
  if echo "$L" | grep -qaE "Uvicorn running|Application startup complete"; then echo "READY $(date +%FT%T%z)" >> $D/probe_${V}_console.txt; ok=1; break; fi
  if echo "$L" | grep -qaE "Traceback|OutOfMemory|No available memory"; then echo "FAILED $(date +%FT%T%z)" >> $D/probe_${V}_console.txt; break; fi
  [ -z "$(timeout 20s docker ps -q --filter name=$N)" ] && { echo EXITED >> $D/probe_${V}_console.txt; break; }
  sleep 10
done
timeout 30s docker logs $N > $D/probe_${V}_startup.log.txt 2>&1
echo "$(date +%FT%T%z) | after wait | $(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader)" >> $D/probe_${V}_console.txt
[ $ok = 1 ] && curl -s --max-time 20 http://localhost:8000/v1/models > $D/probe_${V}_v1_models.json
timeout 60s docker rm -f $N >/dev/null; sleep 5
echo "stopped $(date +%FT%T%z) | $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)" >> $D/probe_${V}_console.txt
cat $D/probe_${V}_console.txt
[ $ok = 1 ]
