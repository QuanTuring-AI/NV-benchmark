#!/usr/bin/env bash
# Vol.2 footprint decomposition · one run over the three arms (A1, A2, A2FP8).
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · PYTHON (optional)
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol2/results/p50_footprint
TAG="p50fp_$(date +%Y%m%dT%H%M%S)"
mkdir -p "$RES/logs"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }

echo "run $TAG · $(date +%FT%T%z)"
(cd $RES && sha256sum -c prediction_p50_footprint.sha256) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
[ ! -f "$RES/configs.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; timeout 30s docker ps; exit 3; }
curl -s --max-time 5 http://127.0.0.1:11434/api/ps | grep -q '"models":\[\]' || { echo "OLLAMA-MODEL-LOADED"; exit 3; }
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$RES/ctx.txt"; sleep 2; done

rc=0
for arm in A1 A2 A2FP8; do
  echo "== $arm · $(date +%FT%T%z)" | tee -a "$RES/ctx.txt"
  MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p50_footprint.py --arm "$arm" --out "$RES" 2>"$RES/logs/${TAG}_${arm}.stderr.txt" || rc=1
  echo "$(date +%FT%T%z) | after $arm | $(ctx)" >> "$RES/ctx.txt"
done
echo "harness rc=$rc $(date +%FT%T%z)"
"$PY" vol2/scripts/p50_footprint_analyze.py "$RES" > "$RES/logs/${TAG}_analyze.stdout.txt" 2>"$RES/logs/${TAG}_analyze.stderr.txt"
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
