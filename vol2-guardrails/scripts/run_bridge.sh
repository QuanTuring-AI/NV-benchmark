#!/usr/bin/env bash
# Vol.1-B 2×2 bridge · one container run (cells ①② on NIM 1.13.1, or ③④ on the newest runnable NIM).
# usage: run_bridge.sh <pair>      pair = c12 | c34
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · GR021_PY · GR023_PY · PYTHON (optional)
# One run per pair: refuses to start if that pair's rows.jsonl already exists. Logs named by run tag.
set -u
cd "$(dirname "$0")/../.."                                    # repo root
PAIR=$1
ENV="${NGC_ENV_FILE:?}"; CACHE="${NIM_CACHE_DIR:?}"; G21="${GR021_PY:?}"; G23="${GR023_PY:?}"; PY="${PYTHON:-python}"
OUT=vol1b/results/bridge_2x2/$PAIR
PRED=vol1b/results/bridge_2x2/prediction_${PAIR}.json
case $PAIR in
  c12) IMG="nvcr.io/nim/meta/llama-3.1-8b-instruct:1.13.1"; CELLS="1,2"; XENV=(); XENV_S="none" ;;
  c34) IMG="nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12"; CELLS="3,4"
       # vLLM in NIM ≥2.0.10 defaults dense models to Model Runner V2, which needs pinned memory; unavailable under
       # Docker Desktop/WSL2 ("UVA is not available"). V1 runner selected explicitly. Listed in the boundary.
       XENV=(-e VLLM_USE_V2_MODEL_RUNNER=0); XENV_S="VLLM_USE_V2_MODEL_RUNNER=0" ;;
  *) echo "usage: run_bridge.sh c12|c34"; exit 2 ;;
esac
IDX=$("$PY" -c "import json;print(json.load(open('$PRED',encoding='utf-8'))['stack']['index_digest'])")
MAN=$("$PY" -c "import json;print(json.load(open('$PRED',encoding='utf-8'))['stack']['manifest_digest_amd64'])")
PROF=$("$PY" -c "import json;print(json.load(open('$PRED',encoding='utf-8'))['stack']['profile'])")
NAME="nim-bridge-$PAIR"; RUN_TAG="${PAIR}_$(date +%Y%m%dT%H%M%S)"; LOG="$OUT/logs/$RUN_TAG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\n'; }

echo "run $RUN_TAG · $(date +%FT%T%z)"
(cd vol1b/results/bridge_2x2 && sha256sum -c prediction_${PAIR}.sha256) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
[ ! -f "$OUT/rows.jsonl" ] || { echo "RESULT EXISTS for $PAIR — one run only"; exit 2; }
mkdir -p "$LOG"
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; timeout 30s docker ps; exit 3; }
timeout 30s docker image inspect "$IMG" --format '{{join .RepoDigests " "}}' | grep -qF "${IDX#sha256:}" || { echo "INDEX-DIGEST-MISMATCH"; exit 4; }

for i in 1 2 3 4 5; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/idle_baseline.txt"; sleep 2; done
echo "$(date +%FT%T%z) | prelaunch | $(ctx)" | tee "$OUT/ctx_before.txt"
MSYS_NO_PATHCONV=1 timeout 90s docker run -d --name "$NAME" --gpus all -p 8000:8000 --env-file "$ENV" \
  -e NIM_MODEL_PROFILE="$PROF" -e NIM_MAX_MODEL_LEN=8192 "${XENV[@]}" -v "$CACHE:/opt/nim/.cache" "$IMG" 2>"$LOG/docker_run.stderr.txt" \
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
  grep -aF "sampling parameters have been overridden" "$LOG/nim_startup.log.txt" > "$OUT/sampling_override_lines.txt"; echo "sampling override lines: $(wc -l < "$OUT/sampling_override_lines.txt")"
  sleep 5
  "$PY" vol1b/scripts/bridge_2x2.py --container "$NAME" --cell-labels "$CELLS" --image "$IMG" --index-digest "$IDX" --manifest-digest "$MAN" \
    --profile "$PROF" --extra-env "NIM_MAX_MODEL_LEN=8192 · extra: $XENV_S · all other NIM settings default" --prediction "$PRED" --out "$OUT" \
    --gr021-py "$G21" --gr023-py "$G23" 2>"$LOG/bridge.stderr.txt"
  rc=$?
fi
echo "bridge rc=$rc $(date +%FT%T%z)"
timeout 30s docker logs "$NAME" > "$LOG/nim_full.log.txt" 2>&1
echo "$(date +%FT%T%z) | stop | $(ctx)" | tee "$OUT/ctx_after.txt"
timeout 60s docker rm -f "$NAME" >/dev/null; sleep 5
echo "$(date +%FT%T%z) | after stop | $(ctx)" | tee -a "$OUT/ctx_after.txt"
[ $rc = 0 ] && "$PY" vol1b/scripts/bridge_analyze.py "$OUT" > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
exit $rc
