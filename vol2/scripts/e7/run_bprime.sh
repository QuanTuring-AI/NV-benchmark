#!/usr/bin/env bash
# B′ · one run only. Refuses to start if a B′ result already exists.
# stderr kept · startup log saved · idle baseline measured first · timestamps from $(date) · logs named by run tag
# Machine-specific paths come from env: NGC_ENV_FILE (passed to --env-file, never read), NIM_CACHE_DIR, PYTHON (optional).
set -u
cd "$(dirname "$0")/../.."                                    # vol2/
ENV="${NGC_ENV_FILE:?set NGC_ENV_FILE}"; CACHE="${NIM_CACHE_DIR:?set NIM_CACHE_DIR}:/opt/nim/.cache"
PY="${PYTHON:-python}"
OUT=results/e7/b_prime
RUN_TAG="bprime_$(date +%Y%m%dT%H%M%S)"; LOG="$OUT/logs/$RUN_TAG"; mkdir -p "$LOG" "$OUT/counters"
W(){ cygpath -w "$1"; }
PS1=scripts/e7/gpu_counters.ps1
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\n'; }

IMG="nvcr.io/nim/meta/llama-3.1-8b-instruct:1.13.1"
IDX="sha256:bc8a12da7ca78599609a60d30cdcce576de5bbb80ad7a87b9a9a5c6ade634c99"
PROF="574eb0765118b2087b5fd6c8684a79e682bd03062f80343cfd9e2140ffa962cd"
NAME="nim-bprime-llama"

echo "run $RUN_TAG · $(date +%FT%T%z)"
(cd "$OUT" && sha256sum -c prediction_bprime.sha256) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
[ ! -f "$OUT/bprime_cohabit.json" ] || { echo "B′ RESULT ALREADY EXISTS — one run only, refusing"; exit 2; }
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY: containers running"; timeout 30s docker ps; exit 3; }
[ -z "$(timeout 30s ollama ps | tail -n +2)" ] || { echo "OLLAMA-BUSY: a model is loaded"; timeout 30s ollama ps; exit 3; }
timeout 30s docker image inspect "$IMG" --format '{{join .RepoDigests " "}}' | grep -qF "${IDX#sha256:}" || { echo "INDEX-DIGEST-MISMATCH"; exit 4; }
echo "ollama: $(ollama --version)" | tee "$LOG/versions.txt"

# idle desktop baseline (no container, no Ollama model): 5 samples, 2 s apart
for i in 1 2 3 4 5; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/idle_baseline.txt"; sleep 2; done
powershell.exe -NoProfile -File "$(W $PS1)" -Mode snapshot -Out "$(W $OUT/counters/snap_idle.json)"
echo "$(date +%FT%T%z) | prelaunch | $(ctx)" | tee "$OUT/bprime_ctx_before.txt"

timeout 90s docker run -d --name "$NAME" --gpus all -p 8000:8000 --env-file "$ENV" \
  -e NIM_MODEL_PROFILE="$PROF" -e NIM_MAX_MODEL_LEN=8192 -v "$CACHE" "$IMG" 2>"$LOG/docker_run.stderr.txt" \
  || { echo "RUN-FAILED"; cat "$LOG/docker_run.stderr.txt"; exit 1; }
ok=0
for i in $(seq 1 90); do
  L=$(timeout 25s docker logs "$NAME" 2>&1)
  if echo "$L" | grep -qaE "Uvicorn running|Application startup complete"; then echo "READY $(date +%FT%T%z)"; ok=1; break; fi
  if echo "$L" | grep -qaE "No available memory|OutOfMemory|Traceback"; then echo "FAILED $(date +%FT%T%z)"; break; fi
  if [ -z "$(timeout 25s docker ps -q --filter name=$NAME)" ]; then echo "EXITED $(date +%FT%T%z)"; break; fi
  sleep 10
done
timeout 30s docker logs "$NAME" > "$LOG/nim_startup.log.txt" 2>&1
if [ $ok = 1 ] && curl -s --max-time 20 http://localhost:8000/v1/models | grep -qa 'llama-3.1-8b-instruct'; then
  echo "$(date +%FT%T%z) | ready | $(ctx)" | tee -a "$OUT/bprime_ctx_before.txt"
  sleep 5
  powershell.exe -NoProfile -File "$(W $PS1)" -Mode sample -Out "$(W $OUT/counters/sampler.jsonl)" \
    -PidFile "$(W $OUT/counters/pids.txt)" -StopFile "$(W $LOG/sampler.stop)" -IntervalSec 3 &
  SAMPLER=$!
  RUN_TAG="$RUN_TAG" BPRIME_IDLE_SNAPSHOT="$OUT/counters/snap_idle.json" \
    "$PY" scripts/e7/bprime_cohabit.py 2>"$LOG/harness.stderr.txt"
  rc=$?
  touch "$LOG/sampler.stop"; for i in $(seq 1 20); do kill -0 $SAMPLER 2>/dev/null || break; sleep 1; done
else
  echo "NIM not ready ⇒ no measurement"; rc=1
fi
echo "harness rc=$rc $(date +%FT%T%z)"
timeout 30s docker logs "$NAME" > "$LOG/nim_full.log.txt" 2>&1
timeout 60s curl -s http://localhost:11434/api/generate -d '{"model":"llama3.1:8b","keep_alive":0}' >/dev/null 2>&1
echo "$(date +%FT%T%z) | stop | $(ctx)" | tee "$OUT/bprime_ctx_after.txt"
timeout 60s docker rm -f "$NAME" >/dev/null; sleep 5
echo "$(date +%FT%T%z) | after stop | $(ctx)" | tee -a "$OUT/bprime_ctx_after.txt"
[ $rc = 0 ] && "$PY" scripts/e7/bprime_verdict.py 2>"$LOG/verdict.stderr.txt"
exit $rc
