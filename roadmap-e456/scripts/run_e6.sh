#!/usr/bin/env bash
# E6 · concurrency on the Vol.1 stack · one container, one run.
# stderr kept · startup log saved · GPU context before launch recorded · timestamps from $(date)
# Machine-specific paths come from env: NGC_ENV_FILE (passed to --env-file, never read), NIM_CACHE_DIR.
set -u
cd "$(dirname "$0")/.."                                    # roadmap-e456/
ENV="${NGC_ENV_FILE:?set NGC_ENV_FILE}"; CACHE="${NIM_CACHE_DIR:?set NIM_CACHE_DIR}:/opt/nim/.cache"
PY="${PYTHON:-python}"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader | tr -d '\n'; }

IMG="nvcr.io/nim/meta/llama-3.1-8b-instruct:1.13.1"
IDX="sha256:bc8a12da7ca78599609a60d30cdcce576de5bbb80ad7a87b9a9a5c6ade634c99"
MAN="sha256:7fd73b514d1afa5b73ecce594a90afbb9a0f81b5de0500412fd8432c79b80086"   # amd64 manifest · value from the Vol.2 arm P record, not re-queried here
PROF="574eb0765118b2087b5fd6c8684a79e682bd03062f80343cfd9e2140ffa962cd"
EXTRA_S="NIM_MAX_MODEL_LEN=8192 · all other NIM settings default"
NAME="nim-e6-llama"
LEVELS="1,4,16,32,50"
mkdir -p logs

[ -f prediction_e6.json ] && [ -f prediction_e6.sha256 ] || { echo "NO-PREDICTION"; exit 2; }
sha256sum -c prediction_e6.sha256 || { echo "PREDICTION-CHANGED"; exit 2; }
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY: containers running"; timeout 30s docker ps; exit 3; }

local_idx=$(timeout 30s docker image inspect "$IMG" --format '{{join .RepoDigests " "}}')
echo "local RepoDigests: $local_idx"
echo "$local_idx" | grep -qF "${IDX#sha256:}" || { echo "INDEX-DIGEST-MISMATCH"; exit 4; }

echo "$(date +%FT%T%z) | prelaunch e6 | $(ctx)" | tee e6_ctx_before.txt
timeout 90s docker run -d --name "$NAME" --gpus all -p 8000:8000 --env-file "$ENV" \
  -e NIM_MODEL_PROFILE="$PROF" -e NIM_MAX_MODEL_LEN=8192 -v "$CACHE" "$IMG" 2>logs/docker_run.stderr.txt \
  || { echo "RUN-FAILED rc=$?"; cat logs/docker_run.stderr.txt; exit 1; }
echo "container started $(date +%FT%T%z)"
ok=0
for i in $(seq 1 90); do
  L=$(timeout 25s docker logs "$NAME" 2>&1)
  if echo "$L" | grep -qaE "Uvicorn running|Application startup complete"; then echo "READY $(date +%FT%T%z)"; ok=1; break; fi
  if echo "$L" | grep -qaE "No available memory|OutOfMemory|Traceback"; then echo "FAILED $(date +%FT%T%z)"; break; fi
  if [ -z "$(timeout 25s docker ps -q --filter name=$NAME)" ]; then echo "EXITED $(date +%FT%T%z)"; break; fi
  sleep 10
done
timeout 30s docker logs "$NAME" > logs/nim-e6-llama_startup.log.txt 2>&1
[ $ok = 1 ] || { timeout 60s docker rm -f "$NAME" >/dev/null; exit 1; }
served=$(curl -s --max-time 20 http://localhost:8000/v1/models)
echo "$served" | grep -qa 'llama-3.1-8b-instruct' || { echo "WRONG-MODEL: $served"; timeout 60s docker rm -f "$NAME" >/dev/null; exit 1; }
echo "$(date +%FT%T%z) | ready | $(ctx)" | tee -a e6_ctx_before.txt
sleep 5

"$PY" scripts/e6_concurrency.py --levels "$LEVELS" --prelaunch-ctx e6_ctx_before.txt \
  --image "$IMG" --index-digest "$IDX" --manifest-digest "$MAN" --profile "$PROF" --extra-env "$EXTRA_S" \
  --prediction prediction_e6.json --out e6_concurrency_llama.json 2>logs/e6_harness.stderr.txt
rc=$?
echo "harness rc=$rc $(date +%FT%T%z)"
timeout 30s docker logs "$NAME" > logs/nim-e6-llama_full.log.txt 2>&1
echo "$(date +%FT%T%z) | stop | $(ctx)" | tee e6_ctx_after.txt
timeout 60s docker rm -f "$NAME" >/dev/null; sleep 5
echo "$(date +%FT%T%z) | after stop | $(ctx)" | tee -a e6_ctx_after.txt
exit $rc
