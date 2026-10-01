#!/usr/bin/env bash
# E9 · NIM Nemotron 9B（A1 上限配置容器，沿用臂 A1 的 nim-e7-a1）+ NeMo Guardrails 0.23.0
# 隔離 venv：以 GR0230_PY 指向裝有 nemoguardrails 0.23.0 的獨立 venv 之 python（0.21.0 系統環境不動）
set -u
cd "$(dirname "$0")/../.."
PY="${GR0230_PY:?set GR0230_PY to the python of an isolated venv with nemoguardrails 0.23.0}"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader | tr -d '\n'; }
v=$("$PY" -c "import nemoguardrails;print(nemoguardrails.__version__)"); echo "guardrails $v"; [ "$v" = "0.23.0" ] || { echo "VERSION-MISMATCH"; exit 1; }
curl -s --max-time 20 http://localhost:8000/v1/models | grep -qa nemotron-nano-9b-v2 || { echo "NO-9B-CONTAINER"; exit 1; }
echo "$(date +%FT%T) | $(ctx)" | tee results/e9/e9_ctx_before.txt
E3_GUARDRAILS_CONFIG_DIR="$PWD/scripts/guardrails_nothink" E3_RESULTS_FILE="$PWD/results/e9/e9_guardrails_0230.json" "$PY" scripts/run_e3_guardrails_vol2.py 2>&1 | tail -30
echo "$(date +%FT%T) | $(ctx)" | tee results/e9/e9_ctx_after.txt
"$PY" scripts/e9/e9_analyze.py
