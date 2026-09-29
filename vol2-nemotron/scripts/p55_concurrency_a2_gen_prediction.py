#!/usr/bin/env python3
"""Vol.2 · A2 concurrency with the sequence cap raised · write prediction_p55_concurrency_a2_<NNN>.json once, before the run.
usage: p55_concurrency_a2_gen_prediction.py <N: 64|128|256> <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

N = int(sys.argv[1]); assert N in (64, 128, 256)
NN = f"{N:03d}"
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", f"p55_concurrency_a2_{NN}")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()
levels, n = [], 1
while n <= 2 * N:
    levels.append(n); n *= 2

p = {
 "experiment": f"Vol.2 · closed-loop concurrency of Nemotron 3 Nano (A2) at max_num_seqs {N}" + (" (the image default, no override)" if N == 256 else " (an intermediate state between the shared 32 and the image default 256)") + ", profiles C and R, levels " + ", ".join(map(str, levels)),
 "written_at": sys.argv[2],
 "written_before": f"the measured run. run_p55_concurrency_a2.sh (SEQS={N}) refuses to start if this file or its .sha256 is missing or changed, or if levels.jsonl exists.",
 "runs": "one run",
 "why": "in results/p53_concurrency_v2/ both arms ran at max_num_seqs 32 so that they shared one configuration; A2's Server- and Interactive-SLO maximum on profile C came out at 32 = the cap, with the engine's num_requests_running gauge at exactly 32 and requests beyond it waiting for capacity. 32 is therefore our ceiling, not A2's: a lower bound. A1 is not re-run: its engine dies at 32. " + ("256 is what the image runs when nothing is set; the footprint run showed 256 sequences fit this card at the default budget." if N == 256 else f"{N} is run at the request of the lab lead as an intermediate state, so that the shape between 32 and 256 is measured rather than interpolated."),
 "stack": {"image": "nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12, NVFP4 profile 1fba9ecf..., as every A2 row of this volume",
           "env": {"NIM_MAX_MODEL_LEN": "8192"} if N == 256 else {"NIM_MAX_MODEL_LEN": "8192", "NIM_PASSTHROUGH_ARGS": f"--max-num-seqs {N}"},
           "as_p53_concurrency_v2": "profiles C (200±50 / 200±50) and R (3,500±300 / 500±50), synthetic, ignore_eos, temperature 0; AIPerf 0.11.0 with the same flags; discarded 120 s warm-up level at c=1; back-to-back calibration on the profile's prompt length (gate: medians within 20%, TTFT alternatively within 20 ms); engine-death detection; level durations min(600, max(60, 4 x previous p99 latency scaled)); fresh-container repeat of the two highest levels; container logs saved before removal — all imported from vol2/scripts/p53_concurrency_v2.py unchanged",
           "levels": levels},
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p55_concurrency_a2.py", "vol2/scripts/p55_concurrency_a2_analyze.py", "vol2/scripts/run_p55_concurrency_a2.sh",
                                      "vol2/scripts/p53_concurrency_v2.py", "vol2/scripts/p53_concurrency.py", "vol2/scripts/p50_footprint.py", "vol1b/scripts/prediction_guard.py")},
 "analysis_rules": {"preconditions": f"per (profile, container): P1 and P2 exactly as p53_concurrency_v2 · P3 the sequence cap is {N}: env as listed above (for 256: no max-num-seqs override present), and the engine's vllm:num_requests_running maximum recorded by AIPerf never exceeds {N} at any level and is recorded at >= 1 level. Any failure -> that sweep's conclusions null.",
                    "slo": "MLPerf Inference v5.1 Llama 3.1-8B: server p99 TTFT <= 2,000 ms and p99 TPOT <= 100 ms; interactive 500 ms / 30 ms — the same rulers as p53_concurrency_v2",
                    "pools": "per level from AIPerf's server_metrics_export.json: running max/p50, waiting max (and by reason), kv_cache_usage_perc max/p50, preemptions; reading of what bound admission: 'sequence cap' (running max >= N and waiting > 0) · 'KV blocks' (running < N, waiting > 0, kv usage max >= 0.90 or preemptions > 0) · 'all admitted' (waiting max 0) · 'other (scheduler)' (waiting with free slots and KV < 0.90)",
                    "program": "vol2/scripts/p55_concurrency_a2_analyze.py (19 self-test cases; four mutations of the P3 and pool rules each fail one case)"},
 "predictions": {
   "basis": "harness test at the image default 256 (2026-09-23 15:36, profile C, c=1 and 4, 20-60 s): 305 and 742 tok/s, running gauge 1 and 4, KV usage 0.7% and 2.7%, calibration TTFT 40.7 vs AIPerf 29.0 ms (11.8 ms), ITL 1.3% apart, KV record 3.06M tokens -- nothing above c=4 was run. p53_concurrency_v2 at max_num_seqs 32 (A2, 2026-09-23): profile C p99 ITL 3.2 (c=1), 6.6 (4), 9.6 (8), 15.1 (16), 22.2 ms (32); p99 TTFT 94-379 ms through 32; 1,540 tok/s at 32, 1,490 at 64 with running gauge 32 and 32 waiting (capacity); profile R server SLO max 8, interactive 4, p99 ITL <= 24 ms at every level, kv_cache_usage max 22% at c=64; decode step time rising roughly linearly with batch size. Footprint: each extra sequence reserves about 14.6 MiB of Mamba state, so raising the cap shrinks the KV pool, which held 3.1M fp8 tokens at 32.",
   "R1": f"profile C: the largest concurrency inside the server SLO is above 32 (at least 64)",
   "R2": f"profile C: the largest concurrency inside the interactive SLO is at most 64 (p99 TPOT passes 30 ms between c=32 and c=128), so the interactive answer does not grow with the cap the way the server answer does",
   "R3": "profile C: peak output throughput is at least 1.3 x 1,540 = 2,000 tok/s at some level >= 64" if N >= 128 else "profile C: peak output throughput is at least 1.15 x 1,540 = 1,770 tok/s at c=64 or 128",
   "R4": "profile R: the server-SLO maximum stays within one level of the 32-cap result (8 or 16): on long prompts prefill queueing binds, not the sequence cap",
   "R5": "the pool reading is never 'KV blocks' on either profile, and at c=2N on profile C it is 'sequence cap'",
   "R6": "the engine does not die at any level",
   "confidence": "R1 high, R2 medium, R3 medium, R4 medium, R5 medium, R6 high",
   "reading": "a failed R is reported as failed; pass is P1-P3 per sweep. No sentence of the form 'serves N users' is produced here: the numbers are p99 latencies at closed-loop concurrency levels under a stated SLO."},
 "outputs": ["levels.jsonl", "events.jsonl", "analysis.json", "versions.txt", "ctx.txt", "A2_<profile>_<container>/c<N>/ and warmup/ AIPerf summaries (profile_export_aiperf.json, server_metrics_export.json; per-request exports not published)", "deidentification_ledger.json (the P27 section 2 procedure, applied before publication)", "logs/ (not published)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, f"prediction_p55_concurrency_a2_{NN}.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
