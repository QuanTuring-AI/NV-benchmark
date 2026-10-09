#!/usr/bin/env python3
"""Vol.2 (directory vol1b/), P67 · write prediction_p67.json once, before the measured run.
The prefix-hit thresholds are computed here from the second harness test's calibration requests (its events file is
read, and its path and the two requests are recorded) and P66's published c=32 cells (mean prompt tokens per NIM request).
usage: p67_gen_prediction.py <harness_test_events.jsonl> <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from prediction_guard import check_prediction

OUT = os.path.join(REPO, "vol1b", "results", "p67_rails_server_config")
P66 = os.path.join(REPO, "vol1b", "results", "p66_rails_under_load")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()
HT = json.load(open(os.path.join(OUT, "harness_test_record.json"), encoding="utf-8"))
ST = json.load(open(os.path.join(OUT, "stack.json"), encoding="utf-8"))
ev_path = sys.argv[1]
cal = {e["arm"]: e["prefix_calibration"] for e in (json.loads(l) for l in open(ev_path, encoding="utf-8"))
       if e.get("kind") == "server_start" and e.get("arm") in ("N", "P") and e.get("prefix_calibration")}
lv66 = {(r["arm"], r["concurrency"]): r for r in (json.loads(l) for l in open(os.path.join(P66, "levels.jsonl"), encoding="utf-8")) if not r.get("warmup")}
thr = {}
for arm in ("N", "P"):
    second = cal[arm][1]; n = lv66[(arm, 32)]["nim"]
    mean_prompt = n["prompt_tokens"] / n["request_success"]
    thr[arm] = {"template_fixed_prefix_tokens": second["prefix_cache_hits"], "kv_block_tokens": 16, "mean_prompt_tokens_per_nim_request": round(mean_prompt, 2),
                "threshold": round((16 + second["prefix_cache_hits"]) / mean_prompt, 4),
                "sources": {"template_fixed_prefix_tokens": f"prefix-cache hits of the second calibration request ({os.path.relpath(ev_path, REPO).replace(os.sep, '/')}, server_start {arm})",
                            "kv_block_tokens": "stack.json prefix_cache", "mean_prompt_tokens_per_nim_request": f"vol1b/results/p66_rails_under_load/levels.jsonl, {arm} c=32: prompt_tokens / request_success"},
                "calibration_requests": cal[arm]}
p = {
 "experiment": "Vol.2 (directory vol1b/), P67 · the Guardrails server's own limits separated from the rails' cost: NeMo Guardrails 0.23.0 served with W = 1 or 4 uvicorn worker processes and a keep-alive timeout K of 5 s (uvicorn's default) or 75 s, in front of Llama 3.1 8B Instruct on NIM 2.0.12 (bf16) on one RTX 5090, at 32, 64 and 128 concurrent requests; and the rails' detection under 128 concurrent requests on four workers.",
 "written_at": sys.argv[2],
 "written_before": "the measured run's first container. run_p67.sh refuses to start if this file or its .sha256 is missing or changed, or if levels.jsonl exists.",
 "why": "In P66 two things could not be told apart at 64 and 128 concurrent requests. (1) R3 gained 18% from 32 to 128 (1,350 -> 1,590 tok/s) while both rails arms were flagged server_bound at 128 (one core >= 95% for 11-12 s in a row), so part of 'the rails keep 42% of direct NIM at 128' may be the one Python process of the server. (2) R1024 at 64 and 128 had 20 connection errors each (ServerDisconnectedError / ConnectionResetError 10054, 0.01-0.5 s after sending, no HTTP status); one untested explanation is uvicorn closing idle keep-alive connections after 5 s while the client reuses them. Both point at the server's configuration, not at the rails.",
 "scope": "Only the Guardrails server's worker count and keep-alive timeout change; NIM, the configs, the load and the Part D set are P66's. Non-streaming requests, self-check rails, one RTX 5090. Windows host: uvicorn's workers share one listening socket (stack.json server_factors.windows_workers).",
 "stack": ST,
 "plan": {"order": ["N c 32 64 128", "R1024 W1K5 c 64 128", "R1024 W4K75 c 64 128, then Part D", "R1024 W1K75 c 64 128", "R1024 W4K5 c 64 128",
                    "R3 W1K5 c 32 64 128", "R3 W4K75 c 32 64 128 (then the w8 branch if it applies)", "P W4K75 c 64 128", "P W1K5 c 64 128"],
          "cells": 21, "one_nim_container": True, "server_restart_per_config": True,
          "per_server_start": "port checked free; all W workers must answer (fresh connections, 64 at a time) with pids that descend from the started server; G2 per worker; prefix calibration on N and P; one discarded warm-up level (c=8, 100 requests, seed 20260927 + 9000); 30 s between server configs"},
 "load": "P66's, unchanged: AIPerf 0.11.0 closed loop, non-streaming, synthetic chat 200 +- 50 tokens in / 200 +- 50 out (max_tokens drawn per request), temperature 0, no ignore_eos on any arm, requests = conversations = max(10 c, 200) per level, seed 20260927 + c (so each level's payloads are P66's), no per-level warm-up, 10 s between levels",
 "part_d": "after R1024 W4K75's levels, on the same server: benchmark/e3_questions.json (15 adversarial, 30 passable) x 3 rounds while AIPerf keeps 128 concurrent chat requests on it (started 30 s before); condition label c128_W4K75. Kept per request: item, round, blocked, judge completion tokens (server call log), latency, response sha256 and length. Compared with P66's R1024 c1 verdicts on the same (item, round).",
 "gates": {"G1": "NIM health as P66 (decode rate at c=1 x 16.06 GB / 1,792 GB/s >= 0.60); else every cell null",
           "G2": "per server start: every worker answered an adversarial and a clean E3 item. Rails: adversarial blocked with 1 LLM call, clean passed with 3. P: neither blocked, 1 LLM call each. Every response carries the expected config sha256; each probe round's NIM request delta equals the LLM calls the responses report. Not all W workers answering is a G2 failure. Else that start's cells null.",
           "G3": "server CPU per process at 1 Hz; one process >= 95% for >= 10 s in a row -> cell flagged server_bound (kept). For W1 the one server process is the one that counts, as in P66.",
           "G4": "client pool 1,000 (stack.json) >= every level",
           "G5": "each level's request payloads (AIPerf inputs.json, sha256 over all payloads) identical across every cell at that concurrency; else those cells null",
           "G6": "errors <= 1% of requests; else the cell null (its error rate is still reported and used in the R1024 2 x 2 error table)",
           "G7": "anchor: N at 32 / 64 / 128 and R3 W1K5 at 32 / 64 / 128 within +-5% of P66's same cells (total tok/s, vol1b/results/p66_rails_under_load/analysis.json). Any of the six outside or missing -> every comparison with P66 null; comparisons inside this run are made as usual."},
 "analysis_rules": {"program": "vol1b/scripts/p67_analyze.py (16 self-test cases; each of 17 mutations of a gate, flag, bound, band, sign or direction makes at least one case fail), reading only the published files",
                    "cells": "label x concurrency; total output tok/s, latency p50 / p99, per-user tok/s, error rate and types, requests per worker, keep-alive closes and connections lost (server log slice of the level), server CPU per process",
                    "r1024_2x2": "at 64 and 128: error rate and total tok/s for W1K5, W1K75, W4K5, W4K75; simple effects: K75 - K5 at each W and W4 - W1 at each K (error rate, percentage points); tok/s ratios for both cells usable",
                    "ratios": "per server config (W1K5, W4K75) and concurrency: R3 / R1024, R3 / N, P / N, R1024 / N on total tok/s, N from this run",
                    "head_table": "P66's 64 and 128 rows beside this run's W4K75 rows, each with W, K, server_bound and error rate; the ratio to P66's same arm only when G7 passes",
                    "prefix_thresholds": thr,
                    "prefix_rule": "adopted for this run: flag prefix_hits on N and P only when the hit share exceeds (one 16-token KV block + the template's fixed prefix) / mean prompt tokens, the fixed prefix measured before freezing (replaces P66's fixed 2%)"},
 "branches": {"w8": "if R3 W4K75 at c=128 is server_bound: R3 W8K75 at c=128 once (variant w8), then nothing more",
              "k75_errors_not_lower": "reported as is; the server-side counts per level (uvicorn keep-alive closes, connections lost with the exception type) are the record of who closed; R1024's affected cells stay null under G6",
              "default_config_id_not_in_effect_with_workers": "G2 per worker detects it; the fallback would be a config_id in the body with G5 relaxed to 'identical except config_id' -- not needed if G2 passes",
              "g7_fails": "the run is completed and reported; only comparisons with P66 are null; nothing is re-run"},
 "harness_test": HT.get("summary", ""),
 "predictions": {
   "source": "set with the run's design, before any P67 measurement",
   "R1": "N anchors: each of N at 32, 64, 128 within 5% of P66's same cell",
   "R2": "R1024 errors: K75 brings the error rate to <= 0.5% at 64 and 128 on both W, and W does not matter (|W4 - W1| <= 0.5 pp at each K and level)",
   "R3": "W4 removes server_bound from the rails cells at c=128 (R3 W4K75, R1024 W4K75, R1024 W4K5), and R3 W4K75's total tok/s at 128 is above R3 W1K5's",
   "R4": "under W4K75, R3 / R1024 at 64 and 128 is within 1.5-1.8 (the band of 1-32 in P66)",
   "R5": "Part D c128_W4K75: 42/45 blocked, 0/90 false blocks, 0 of 135 verdicts flip against P66's R1024 c1",
   "confidence": "R1 high (same image, profile and settings; P66's N cells had no errors). R2 medium: the keep-alive explanation was never tested. R3 medium on the flag, low on the throughput: with the rails each client request makes about 3 NIM calls and about 4.3 times the prompt tokens of N (P66 c=128: 1,314,990 vs 303,193), so NIM may be the limit once the server is not. R4 low. R5 medium: greedy decoding under batching is not bit-deterministic.",
   "reading_of_predictions": "a failed prediction is reported as failed; nothing is re-run to chase a result"},
 "harness_sha256": {k: h(k) for k in ("vol1b/scripts/p67_rails_server_config.py", "vol1b/scripts/p67_gr_server.py", "vol1b/scripts/p67_gr_app.py", "vol1b/scripts/p67_analyze.py",
                                      "vol1b/scripts/p67_postrun.py", "vol1b/scripts/run_p67.sh", "vol1b/scripts/p66_rails_under_load.py", "vol1a-revisit/scripts/p59_nim_value.py",
                                      "vol2/scripts/p54_engine.py", "vol1b/scripts/prediction_guard.py",
                                      "vol1b/results/p67_rails_server_config/configs/default/config.yml", "vol1b/results/p67_rails_server_config/configs/mt3/config.yml",
                                      "vol1b/results/p67_rails_server_config/configs/passthrough/config.yml", "benchmark/e3_questions.json")},
 "fixed_inputs_sha256": {k: h(k) for k in ("vol1b/results/p66_rails_under_load/analysis.json", "vol1b/results/p66_rails_under_load/part_d_verdicts.jsonl",
                                           "vol1b/results/p66_rails_under_load/levels.jsonl")},
}
check_prediction(p)
path = os.path.join(OUT, "prediction_p67.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path); print(json.dumps(thr, indent=1))
