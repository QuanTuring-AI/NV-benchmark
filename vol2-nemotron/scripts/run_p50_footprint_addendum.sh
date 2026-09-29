#!/usr/bin/env bash
# Vol.2 footprint addendum · A2 with NIM_MAX_BATCH_SIZE=32 · one run.
# env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR · PYTHON (optional)
set -u
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python}"
RES=vol2/results/p50_footprint_addendum
TAG="p50fpa_$(date +%Y%m%dT%H%M%S)"
mkdir -p "$RES/logs"
ctx(){ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version --format=csv,noheader | tr -d '\r\n'; }

echo "run $TAG · $(date +%FT%T%z)"
(cd $RES && tr -d '\r' < prediction_p50_footprint_addendum.sha256 | sha256sum -c -) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
[ ! -f "$RES/configs.jsonl" ] || { echo "RESULT EXISTS — one run only"; exit 2; }
[ -z "$(timeout 30s docker ps -q)" ] || { echo "GPU-BUSY"; exit 3; }
for i in 1 2 3; do echo "$(date +%FT%T%z) | idle $i | $(ctx)" >> "$RES/ctx.txt"; sleep 2; done
MSYS_NO_PATHCONV=1 "$PY" vol2/scripts/p50_footprint_addendum.py --out "$RES" 2>"$RES/logs/${TAG}.stderr.txt"; rc=$?
echo "$(date +%FT%T%z) | end | $(ctx)" >> "$RES/ctx.txt"
echo "harness rc=$rc $(date +%FT%T%z)"
# the main analyzer expects arm labels A1/A2/A2FP8: relabel A2B32 -> A2 into a scratch copy for analysis
"$PY" - "$RES" <<'PY'
import json, os, sys, importlib.util
d = sys.argv[1]
rows = [json.loads(l) for l in open(os.path.join(d, "configs.jsonl"), encoding="utf-8")]
for r in rows:
    r["arm_as_run"] = r["arm"]; r["arm"] = "A2"
spec = importlib.util.spec_from_file_location("an", os.path.join("vol2", "scripts", "p50_footprint_analyze.py"))
an = importlib.util.module_from_spec(spec); spec.loader.exec_module(an)
a = an.analyse(rows)
a["note"] = "rows carry arm_as_run = A2B32 (NIM_MAX_BATCH_SIZE=32); analysed under the A2 label"
json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
c = (a.get("conclusions") or {}).get("per_arm", {}).get("A2") or {}
print("preconditions", a["preconditions_pass"], "| min_viable", (c.get("min_viable") or {}).get("kvcache_percent"), "budget", (c.get("min_viable") or {}).get("budget_mib"), "| bound", c.get("bound_reached"), "| fail@", c.get("first_failure"), c.get("first_failure_reason"))
PY
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
