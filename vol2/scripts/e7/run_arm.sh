#!/usr/bin/env bash
# E7 · 臂 A1／A2 · 一臂一容器
# stderr 保留 · 啟動 log 必存 · 啟動前桌面基線必記 · 時間戳一律 $(date) · ⛔ 不帶 RELAX / DISABLE_CUDA_GRAPH
set -u
cd "$(dirname "$0")/../.."
# NGC 憑證以 --env-file 路徑傳入（腳本不讀取其內容）；NIM 模型快取掛載到 /opt/nim/.cache
ENV="${NGC_ENV_FILE:?set NGC_ENV_FILE to your NGC env-file path}"; CACHE="${NIM_CACHE_DIR:?set NIM_CACHE_DIR to a local NIM cache dir}:/opt/nim/.cache"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader | tr -d '\n'; }
arm=$1
case $arm in
  A1) IMG="nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2:1.12.2"
      IDX="sha256:a2f4a5aefe7dd0ff29bfd8d7081ce4977337d1b12081361af7b6283ff9a406b2"
      MAN="sha256:bdd975848d5d4e2ae1f701a9b78ff7f6ed7de56498f9c2f250d7d98484b0d40f"
      PROF=5cf34bab34141258d0cc836c66684642d3e3f32b4daaa2008e48bd289d6bc84b
      EXTRA=(-e NIM_MAX_NUM_SEQS=32); EXTRA_S="NIM_MAX_NUM_SEQS=32 · NIM_MAX_MODEL_LEN=4096 · 無 RELAX · CUDA graph 開" ;;
  A2) IMG="nvcr.io/nim/nvidia/nemotron-3-nano@sha256:ac9d1cefa7ad958a4ad9727871a85c89f79c0d907d78415433b0c83e1a072aa3"
      IDX="sha256:ac9d1cefa7ad958a4ad9727871a85c89f79c0d907d78415433b0c83e1a072aa3"
      MAN="sha256:ac9d1cefa7ad958a4ad9727871a85c89f79c0d907d78415433b0c83e1a072aa3"   # 單平台 OCI manifest（非 index）⇒ 兩 digest 同值
      PROF=1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada
      EXTRA=(); EXTRA_S="全預設 · NIM_MAX_MODEL_LEN=4096 · 無 RELAX · CUDA graph 開" ;;
  *) echo "usage: run_arm.sh A1|A2"; exit 2 ;;
esac
name="nim-e7-$(echo $arm | tr A-Z a-z)"
mkdir -p results/logs
for c in $(timeout 30s docker ps -a --format '{{.Names}}' | grep -a '^nim-'); do timeout 60s docker rm -f "$c" >/dev/null && echo "removed stale $c"; done
sleep 15
PRE="results/logs/arm_$(echo $arm | tr A-Z a-z)_ctx_before.txt"
echo "$(date +%FT%T) | prelaunch arm $arm | $(ctx)" | tee "$PRE"
timeout 90s docker run -d --name "$name" --gpus all -p 8000:8000 --env-file "$ENV" -e NIM_MODEL_PROFILE="$PROF" -e NIM_MAX_MODEL_LEN=4096 "${EXTRA[@]}" -v "$CACHE" "$IMG" || { echo "RUN-FAILED rc=$?"; exit 1; }
echo "container started $(date +%FT%T)"
ok=0
for i in $(seq 1 120); do
  L=$(timeout 25s docker logs "$name" 2>&1)
  if echo "$L" | grep -qaE "Uvicorn running|Application startup complete"; then echo "READY $name $(date +%T)"; ok=1; break; fi
  if echo "$L" | grep -qaE "No available memory|OutOfMemory|Traceback"; then echo "FAILED $name $(date +%T)"; break; fi
  sleep 10
done
timeout 30s docker logs "$name" > "results/logs/${name}_startup.log.txt" 2>&1
[ $ok = 1 ] || exit 1
sleep 5
python scripts/e7/e7_arm.py --arm "$arm" --prelaunch-ctx "$PRE" --image "$IMG" --index-digest "$IDX" --manifest-digest "$MAN" --profile "$PROF" --extra-env "$EXTRA_S"
rc=$?
timeout 30s docker logs "$name" > "results/logs/${name}_full.log.txt" 2>&1
[ "${KEEP:-0}" = 1 ] && { echo "KEEP=1 · $name 保留供 E9 · $(date +%FT%T) | $(ctx)"; exit $rc; }
echo "$(date +%FT%T) | stop $name | $(ctx)"
timeout 60s docker rm -f "$name" >/dev/null; sleep 5; echo "after stop: $(ctx)"
exit $rc
