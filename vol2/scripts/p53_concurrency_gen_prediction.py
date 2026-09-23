#!/usr/bin/env python3
"""Vol.2 concurrency · write prediction_p53_concurrency.json once, before the measured run.
usage: p53_concurrency_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p53_concurrency")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.2 · concurrency · closed-loop AIPerf sweeps on Nemotron Nano 9B v2 (bf16, NIM 1.12.2) and Nemotron 3 Nano (NVFP4, NIM 2.0.12), two ISL/OSL profiles, both arms at max_num_seqs 32",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p53_concurrency.sh refuses to start if this file or its .sha256 is missing or changed, or if levels.jsonl exists.",
 "runs": "one run per (arm, profile); the two highest levels are repeated once in a fresh container and both results are reported",
 "answer_form": "per (arm, profile): the largest concurrency whose p99 TTFT and p99 ITL are inside the Server SLO and inside the Interactive SLO; the throughput saturation level; whether a level failing the Server SLO was reached. Not 'N requests with 0 failures'.",
 "slo": {"server": "p99 TTFT <= 2,000 ms and p99 TPOT <= 100 ms", "interactive": "p99 TTFT <= 500 ms and p99 TPOT <= 30 ms",
         "source": "MLPerf Inference v5.1, Llama 3.1-8B benchmark limits (MLCommons inference rules, server and interactive scenarios); applied here to different models as a fixed yardstick, not as a claim of MLPerf comparability"},
 "stack": {"card": "NVIDIA GeForce RTX 5090, 32,607 MiB, driver 591.86",
           "A1": "nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2:1.12.2, profile 5cf34bab... bf16, NIM_MAX_MODEL_LEN 8192, NIM_MAX_NUM_SEQS 32",
           "A2": "nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12, profile 1fba9ecf... NVFP4, NIM_MAX_MODEL_LEN 8192, NIM_PASSTHROUGH_ARGS --max-num-seqs 32 (the variable that reaches the engine, vol2/results/p50_footprint_addendum2)",
           "why_8192": "the RAG profile's ISL+OSL (up to about 4,350 tokens) does not fit 4096",
           "tool": "AIPerf 0.11.0 (--streaming, --use-server-token-count, warm-up N requests excluded, benchmark-grace-period 0), tokenizer files copied from each model's NIM cache snapshot"},
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p53_concurrency.py", "vol2/scripts/p53_concurrency_analyze.py", "vol2/scripts/run_p53_concurrency.sh", "vol2/scripts/p50_footprint.py", "vol1b/scripts/prediction_guard.py")},
 "design": {"profiles": {"C": "synthetic ISL 200±50 / OSL 200±50, ignore_eos, temperature 0", "R": "synthetic ISL 3500±300 / OSL 500±50, ignore_eos, temperature 0"},
            "levels": "1, 2, 4, 8, 16, 32, 64 (one level above max_num_seqs, so queueing is visible); first level 60 s, later levels min(600, max(60, 4 x expected request time)) as in vol1b/scripts/p17_sweep.py; completed < 3N is flagged",
            "calibration": "before each main sweep, one discarded warm-up request and then 10 requests at concurrency 1 through the harness's own streaming client, each on a new TCP connection (~200-token fixed prompt, ignore_eos, 200 output tokens, TTFT = arrival of the first streamed chunk carrying a choice, read chunk by chunk); AIPerf's c=1 ITL median must be within 20% of the client's median, and its TTFT median within 20% or within 15 ms (whichever is larger), or that sweep's conclusions are null. The 15 ms floor is a default, not confirmed by anyone. Why a new connection per request and why medians: four calibration attempts on 2026-09-22 reused one connection (requests.Session, then http.client with TCP_NODELAY) and measured 85-96 ms TTFT against AIPerf's 44-50 ms with ITL agreeing within 0.4-4%; the diagnosis of 2026-09-23 on the same server showed the first request on a fresh connection at 43-54 ms (AIPerf 46-57 ms on its own connection) and every later request on the same kept-alive connection at 83-99 ms, while curl reached the response headers in 6-8 ms. The mechanism was not identified; the condition is avoided and disclosed. A single cold first request (117-205 ms) moves a 10-request average by 10-15 ms, hence medians. A side measurement through the requests library (new connection per request, iter_lines 512-byte buffering) is recorded but not gated: it quantifies the client-side TTFT offset that the speed, answer and long-context tables carry",
            "fresh_container": "after each main sweep the container is replaced and the two highest levels run again; both are reported side by side",
            "no_guardrails": "the concurrency measurement does not go through Guardrails"},
 "analysis_rules": {"preconditions": "P1 every level rc 0 with a summary and 0 request errors · P2 calibration medians within 20% (TTFT alternatively within 15 ms) · P3 max_num_seqs 32 on both arms (from the recorded container env). Any failure -> that sweep's conclusions null.",
                    "program": "vol2/scripts/p53_concurrency_analyze.py (9 self-test cases)"},
 "predictions": {
   "basis": "harness test 2026-09-22 (A1, profile C, levels 1 and 4, 20-60 s): TTFT p99 53 and 100 ms, ITL avg 13.2-14.4 ms, throughput 75 and 268 tok/s, 0 errors; AIPerf c=1 TTFT avg 44-49 ms across five short runs of the same container configuration. single-stream: A1 72.9, A2 305 tok/s; KV at the footprint default budget; max_num_seqs 32 caps in-batch concurrency on both arms; P17 (Llama 8B bf16 on this card) reached the Server SLO ceiling between 128 and 256 on the C profile and far lower on R",
   "R1": "on profile C both arms stay inside the Server SLO up to concurrency 32 and fail it at 64 (queueing beyond max_num_seqs)",
   "R2": "on profile R the Server-SLO maximum is below 32 for A1 (TTFT of 3,500-token prefills at high concurrency) and at least as high for A2 as for A1",
   "R3": "the Interactive-SLO maximum is at most 8 on profile R for both arms",
   "R4": "A2's output token throughput at its saturation level is at least 2.5x A1's on profile C",
   "R5": "the fresh-container repeats agree with the main sweep's top levels within 25% on output throughput",
   "confidence": "R1 medium, R2 low, R3 low, R4 medium, R5 low (D25 saw 2.5-12x differences on another model)",
   "reading": "a failed R is reported as failed; pass is P1-P3 per sweep. No sentence of the form 'serves N users' is produced here."},
 "outputs": ["levels.jsonl", "events.jsonl", "analysis.json", "versions.txt", "ctx.txt", "<arm>_<profile>_<container>/c<N>/ AIPerf artifacts (profile_export_aiperf.json kept; per-request exports are under the ignore rules)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p53_concurrency.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
