#!/usr/bin/env bash
# P28 v2 · judge isolation · one container run on the cell-4 NIM stack. v2 of run_p28.sh (P33): reads prediction_p28_v2.json,
# and refuses a profile value that is not a bare 64-hex id -- v1's prediction carried the display suffix, which NIM
# reported 30 s later as 'no matching profile in manifest'.
# No generation: the judge reads texts from the corpus.
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · GR023_PY · PYTHON (optional)
# One run: refuses to start if judgements.jsonl exists.
set -u
cd "$(dirname "$0")/../.."
ENV="${NGC_ENV_FILE:?}"; CACHE="${NIM_CACHE_DIR:?}"; G23="${GR023_PY:?}"; PY="${PYTHON:-python}"
OUT=vol1b/results/p28_judge_isolation; PRED=$OUT/prediction_p28_v2.json
IMG="nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12"
IDX=$("$PY" -c "import json;print(json.load(open('$PRED',encoding='utf-8'))['stack']['index_digest'])")
MAN=$("$PY" -c "import json;print(json.load(open('$PRED',encoding='utf-8'))['stack']['manifest_digest_amd64'])")
PROF=$("$PY" -c "import json;print(json.load(open('$PRED',encoding='utf-8'))['stack']['profile'])" | tr -d '\r')
[[ $PROF =~ ^[0-9a-f]{64}$ ]] || { echo "PROFILE-MALFORMED len=${#PROF}: $PROF"; exit 5; }
NAME="nim-p28"; RUN_TAG="p28_$(date +%Y%m%dT%H%M%S)"; LOG="$OUT/logs/$RUN_TAG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\n'; }

echo "run $RUN_TAG · $(date +%FT%T%z)"
(cd $OUT && sha256sum -c prediction_p28_v2.sha256) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
(cd $OUT && sha256sum -c corpus.sha256) || { echo "CORPUS-MISSING-OR-CHANGED"; exit 2; }
[ ! -f "$OUT/judgements.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
mkdir -p "$LOG"
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; timeout 30s docker ps; exit 3; }
timeout 30s docker image inspect "$IMG" --format '{{join .RepoDigests " "}}' | grep -qF "${IDX#sha256:}" || { echo "INDEX-DIGEST-MISMATCH"; exit 4; }

for i in 1 2 3 4 5; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/idle_baseline.txt"; sleep 2; done
echo "$(date +%FT%T%z) | prelaunch | $(ctx)" | tee "$OUT/ctx_before.txt"
MSYS_NO_PATHCONV=1 timeout 90s docker run -d --name "$NAME" --gpus all -p 8000:8000 --env-file "$ENV" \
  -e NIM_MODEL_PROFILE="$PROF" -e NIM_MAX_MODEL_LEN=8192 -e VLLM_USE_V2_MODEL_RUNNER=0 -v "$CACHE:/opt/nim/.cache" "$IMG" 2>"$LOG/docker_run.stderr.txt" \
  || { echo "RUN-FAILED"; cat "$LOG/docker_run.stderr.txt"; exit 1; }
ok=0
for i in $(seq 1 120); do
  L=$(timeout 25s docker logs "$NAME" 2>&1)
  if echo "$L" | grep -qaE "Uvicorn running|Application startup complete"; then echo "READY $(date +%FT%T%z)"; ok=1; break; fi
  if echo "$L" | grep -qaE "Traceback|OutOfMemory|No available memory"; then echo "FAILED $(date +%FT%T%z)"; break; fi
  [ -z "$(timeout 25s docker ps -q --filter name=$NAME)" ] && { echo "EXITED $(date +%FT%T%z)"; break; }
  sleep 10
done
timeout 30s docker logs "$NAME" > "$LOG/nim_startup.log.txt" 2>&1
rc=1
if [ $ok = 1 ]; then
  echo "$(date +%FT%T%z) | ready | $(ctx)" | tee -a "$OUT/ctx_before.txt"
  grep -aF "clamping gpu_memory_utilization" "$LOG/nim_startup.log.txt" > "$OUT/memory_clamp_line.txt"
  curl -s --max-time 20 http://localhost:8000/metrics > "$OUT/metrics_at_ready.txt"
  # first request after READY is sent and discarded (it is systematically slow)
  curl -s --max-time 120 -o /dev/null -w "first request discarded · http %{http_code} · %{time_total}s\n" \
    http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" \
    -d '{"model":"meta/llama-3.1-8b-instruct","messages":[{"role":"user","content":"Hello"}],"max_tokens":16,"temperature":0}' | tee "$OUT/first_request_discarded.txt"
  sleep 5
  "$PY" vol1b/scripts/p28_judge_isolation.py --corpus "$OUT/corpus.json" --out "$OUT" --prediction "$PRED" --gr023-py "$G23" \
    --container "$NAME" --image "$IMG" --index-digest "$IDX" --manifest-digest "$MAN" --profile "$PROF" \
    --extra-env "NIM_MAX_MODEL_LEN=8192 · extra: VLLM_USE_V2_MODEL_RUNNER=0 · all other NIM settings default" 2>"$LOG/harness.stderr.txt"
  rc=$?
fi
echo "harness rc=$rc $(date +%FT%T%z)"
timeout 30s docker logs "$NAME" > "$LOG/nim_full.log.txt" 2>&1
echo "$(date +%FT%T%z) | stop | $(ctx)" | tee "$OUT/ctx_after.txt"
timeout 60s docker rm -f "$NAME" >/dev/null; sleep 5
echo "$(date +%FT%T%z) | after stop | $(ctx)" | tee -a "$OUT/ctx_after.txt"
[ $rc = 0 ] && "$PY" vol1b/scripts/p28_analyze.py "$OUT" --excluded "$OUT/excluded_segments.json" > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
