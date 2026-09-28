#!/usr/bin/env bash
# Chain after C: wait for the C result → arm A2 → arm A1 (container kept) → E9 (0.23.0, same A1 container) → stop
set -u
cd "$(dirname "$0")/../.."
until [ -f results/e7/c/c_cohabit.json ]; do sleep 20; done
echo "C 產物已落地 $(date +%FT%T)"; sleep 10
timeout 30s ollama ps
echo "===== 臂 A2 · $(date +%FT%T) ====="; bash scripts/e7/run_arm.sh A2; echo "A2 rc=$?"
echo "===== 臂 A1 · $(date +%FT%T) ====="; KEEP=1 bash scripts/e7/run_arm.sh A1; rc=$?; echo "A1 rc=$rc"
if [ $rc = 0 ]; then echo "===== E9 · $(date +%FT%T) ====="; bash scripts/e9/run_e9.sh; echo "E9 rc=$?"; fi
echo "$(date +%FT%T) | stop nim-e7-a1"; timeout 60s docker rm -f nim-e7-a1 >/dev/null 2>&1; sleep 5
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
echo CHAIN-DONE
