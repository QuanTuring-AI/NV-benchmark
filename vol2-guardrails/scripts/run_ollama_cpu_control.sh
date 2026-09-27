#!/usr/bin/env bash
# Ollama CPU control · the final Ollama measurement in this repository · one run.
# env: PYTHON (optional) · TEST=1 runs the same sequence on the harness-test questions into harness_test/
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol1b/results/ollama_cpu_control
SAMPLE_DIR=vol1b/results/p20_coresidence
TAG="cpu_$(date +%Y%m%dT%H%M%S)"
if [ "${TEST:-0}" = 1 ]; then OUT="$RES/harness_test/$TAG"; FLAG="--test"; PLAN="--plan-g 1 --plan-cpu 3"
else OUT="$RES"; FLAG=""; PLAN=""; fi
LOG="$RES/logs/$TAG"; mkdir -p "$OUT" "$LOG"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }

echo "run $TAG · test=${TEST:-0} · $(date +%FT%T%z)"
if [ "${TEST:-0}" != 1 ]; then
  (cd $RES && sha256sum -c prediction_ollama_cpu_control.sha256) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
  [ ! -f "$OUT/requests.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
fi
(cd $SAMPLE_DIR && sha256sum -c sample.sha256) || { echo "SAMPLE-MISSING-OR-CHANGED"; exit 2; }
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; timeout 30s docker ps; exit 3; }
curl -sf --max-time 10 http://127.0.0.1:11434/api/version >/dev/null || { echo "OLLAMA-NOT-RUNNING"; exit 3; }

{ echo "ollama: $(ollama --version 2>&1 | tr -d '\r')";
  echo "ollama model: $(ollama list 2>/dev/null | tr -d '\r' | grep -E '^llama3\.1:8b ')";
  echo "driver/gpu: $(ctx)";
  powershell.exe -NoProfile -Command "\$p = Get-CimInstance Win32_Processor; 'cpu: ' + \$p.Name + ', cores ' + \$p.NumberOfCores + ', logical ' + \$p.NumberOfLogicalProcessors; Get-CimInstance Win32_PhysicalMemory | ForEach-Object { 'memory module: ' + \$_.DeviceLocator + ', ' + [math]::Round(\$_.Capacity / 1GB) + ' GiB, speed ' + \$_.Speed + ', configured ' + \$_.ConfiguredClockSpeed + ', SMBIOS type ' + \$_.SMBIOSMemoryType }; 'memory total bytes: ' + (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory" | tr -d '\r'
} | tee "$OUT/versions.txt"
for i in 1 2 3 4 5; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$OUT/ctx.txt"; sleep 2; done

rc=0
"$PY" vol1b/scripts/ollama_cpu_control.py --out "$OUT" $FLAG 2>"$LOG/harness.stderr.txt" || rc=$?
curl -s --max-time 60 http://127.0.0.1:11434/api/generate -d '{"model":"llama3.1:8b","keep_alive":0}' >/dev/null
echo "$(date +%FT%T%z) | end | $(ctx)" | tee -a "$OUT/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
if [ "$rc" = 0 ]; then
  "$PY" vol1b/scripts/ollama_cpu_control_analyze.py "$OUT" $PLAN > "$LOG/analyze.stdout.txt" 2>"$LOG/analyze.stderr.txt"
  echo "analyze rc=$? $(date +%FT%T%z)"
else
  echo "analysis not run: the harness stopped (rc=$rc); no conclusion is produced"
fi
exit $rc
