#!/usr/bin/env bash
# P20 · co-residence of NIM and Ollama · one run.
# Order: S-O half A (NIM stopped) -> NIM up -> S-N and C interleaved -> NIM down -> S-O half B -> analysis.
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · PYTHON (optional)
#      TEST=1 runs the same sequence on the three harness-test questions into harness_test/ (never analysed as a result)
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol1b/results/p20_coresidence
TAG="p20_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; FLAG="--test"; else OUT="$RES"; FLAG=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }

echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && sha256sum -c prediction_p20.sha256) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/requests.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
(cd $RES && sha256sum -c sample.sha256) || { echo "SAMPLE-MISSING-OR-CHANGED"; exit 2; }
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; timeout 30s docker ps; exit 3; }
curl -sf --max-time 10 http://127.0.0.1:11434/api/version >/dev/null || { echo "OLLAMA-NOT-RUNNING"; exit 3; }

{ echo "ollama: $(ollama --version 2>&1 | tr -d '\r')";
  echo "ollama model: $(ollama list 2>/dev/null | tr -d '\r' | grep -E '^llama3\.1:8b ')";
  echo "driver/gpu: $(ctx)"; } | tee "$OUT/versions.txt"
for i in 1 2 3 4 5; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done

rc=0
echo "== S-O half A · $(date +%FT%T%z)" | tee -a "$OUT/ctx.txt"
"$PY" vol1b/scripts/p20_coresidence.py --phase so --half A --out "$OUT" $FLAG 2>"$LOG/so_A.stderr.txt" || rc=1

echo "== NIM up · $(date +%FT%T%z)" | tee -a "$OUT/ctx.txt"
curl -s --max-time 60 http://127.0.0.1:11434/api/generate -d '{"model":"llama3.1:8b","keep_alive":0}' >/dev/null
if bash vol1b/scripts/p17_container.sh start nim-p20 "$LOG/container"; then
  "$PY" vol1b/scripts/p20_coresidence.py --phase nim --out "$OUT" $FLAG 2>"$LOG/nim_phase.stderr.txt" || rc=1
else
  echo "NIM-NOT-READY"; rc=1
fi
bash vol1b/scripts/p17_container.sh stop nim-p20 "$LOG/container"
cp "$LOG/container/memory_clamp_line.txt" "$LOG/container/metrics_at_ready.txt" "$OUT/" 2>/dev/null
cat "$LOG/container/ctx.txt" >> "$OUT/ctx.txt" 2>/dev/null

echo "== S-O half B · $(date +%FT%T%z)" | tee -a "$OUT/ctx.txt"
"$PY" vol1b/scripts/p20_coresidence.py --phase so --half B --out "$OUT" $FLAG 2>"$LOG/so_B.stderr.txt" || rc=1
curl -s --max-time 60 http://127.0.0.1:11434/api/generate -d '{"model":"llama3.1:8b","keep_alive":0}' >/dev/null
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"

echo "harness rc=$rc $(date +%FT%T%z)"
"$PY" vol1b/scripts/p20_analyze.py "$OUT" > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
