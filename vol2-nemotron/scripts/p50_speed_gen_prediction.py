#!/usr/bin/env python3
"""Vol.2 speed table · write prediction_p50_speed.json once, before the measured run.
usage: p50_speed_gen_prediction.py <written_at>   (pass "$(date +%FT%T%z)")"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p50_speed")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

BYTES = {"A1": 17776454656, "A2": 3590938272}
p = {
 "experiment": "Vol.2 · speed table · Nemotron Nano 9B v2 (bf16, NIM 1.12.2) and Nemotron 3 Nano (NVFP4, NIM 2.0.12), alternated on one RTX 5090",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p50_speed.sh refuses to start if this file or its .sha256, or the sample or its .sha256, is missing or changed, or if requests.jsonl exists.",
 "runs": "one run; not repeated to obtain a different outcome",
 "what_is_compared": "two deployment options, each in its own NIM image and NIM version (no common version exists: vol2/results/p50_availability), each at the only precision its image can run on this card (A1 bf16, A2 NVFP4). Architecture, precision and NIM version all differ between the arms and are part of what each option is; this is not a single-variable comparison and is not written as one.",
 "stack": {"card": "NVIDIA GeForce RTX 5090, 32,607 MiB, driver 591.86, peak memory bandwidth 1,792 GB/s (vendor figure)",
           "A1": "nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2:1.12.2 (index sha256:a2f4a5ae...), profile 5cf34bab... vllm-bf16-tp1-pp1, NIM_MAX_MODEL_LEN=4096, NIM_MAX_NUM_SEQS=32, other settings default",
           "A2": "nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12 (index sha256:bd38d2d5...), profile 1fba9ecf... vllm-nvfp4-tp1-pp1, NIM_MAX_MODEL_LEN=4096, other settings default",
           "launcher": "vol2/scripts/p50_footprint.py start()/stop() (same as the footprint run's default configuration)"},
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p50_speed.py", "vol2/scripts/p50_speed_analyze.py", "vol2/scripts/run_p50_speed.sh",
                                      "vol2/scripts/p50_footprint.py", "vol2/scripts/p50_bytes_per_token.py", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {"vol1b/results/p20_coresidence/sample.json": h("vol1b/results/p20_coresidence/sample.json"),
                         "benchmark/questions.json": h("benchmark/questions.json")},
 "design": {
   "sample": "the 50 questions and run order of vol1b/results/p20_coresidence/sample.json (a pre-registered stratified draw from the Vol.1 question set)",
   "blocks": "A1 on positions 0-24, A2 on 0-24, A1 on 25-49, A2 on 25-49; one container at a time (the two images cannot share the card); each block starts its container, discards one 16-token request, then sends one request per question with 2 s between requests",
   "payload": "Vol.1 run_benchmark.py payload plus temperature 0.0 and top_p 0.9, max_tokens 500, stream with usage; no system prompt, so both models reason as they do by default under a Vol.1-style request",
   "records": "per request: TTFT, total latency, Vol.1 word count, engine prompt/completion tokens, finish_reason, response SHA-256 and length, GPU state before and after, containers up; per block: image, profile, env, seconds to READY, engine cache_config, log memory lines",
   "why_no_no_think": "the footprint probe uses /no_think to test that a start can serve to completion; the speed table keeps the Vol.1 request shape, and reports finish_reason counts so a reader sees how many completions hit max_tokens"},
 "analysis_rules": {
   "preconditions": "P1 no errors, all HTTP 200, usage present on every row · P2 every row's served model is its arm's and exactly one container up · P3 50 rows per arm, one per question, blocks alternating A1/A2. Any failure -> conclusions null.",
   "arm_health_gate": "generation rate = completion_tokens / (total - TTFT) per request, median per arm; effective bandwidth = that median x bytes read per token; share of 1,792 GB/s; an arm under 10% fails the gate and no ratio is reported (validity null)",
   "bytes_read_per_token": {"A1": BYTES["A1"], "A2": BYTES["A2"],
                            "how": "vol2/scripts/p50_bytes_per_token.py on the safetensors headers in the NIM cache: A1 dense = all stored weight bytes; A2 MoE = non-expert tensors 2,558,227,600 + shared expert 258,177,392 + routed experts 16,523,376,640 x 6/128. Six experts per token is the NVFP4 model card's figure; the NGC container page says five, which gives 3,461,849,392 (3.6% less) and is reported as a sensitivity. Stored bytes count NVFP4 weights at 4 bits plus scales, so this is bytes moved, not parameters."},
   "statistics": "ratio of means A2/A1 over the 50 questions, 95% bootstrap CI over questions (2000 resamples, seed 20260921), median per-question ratio",
   "program": "vol2/scripts/p50_speed_analyze.py (13 self-test cases)"},
 "predictions": {
   "basis": "E7 (different images, no usage): A1 tps 74.1, A2 287.9 by word count; bytes per token above; Vol.1-B Llama 8B bf16 generation 96.8 tok/s at 16.06 GB/token = 1,555 GB/s = 87% of peak; footprint harness tests 2026-09-21 (default configuration, /no_think probes): A1 TTFT 51-758 ms, A2 33-817 ms on three short questions. Seen before this file was written, in the speed harness test on the three harness-test questions (not in the sample): A1 generation 71.5-72.4 tok/s, A2 290-309 tok/s, all six completions ended at max_tokens (length), health shares 71% (A1) and 61% (A2), A2/A1 ratio about 4.2. The predictions below were fixed before that test except R1, which was raised from 2.5 to 3.5 after seeing it; R2-R4 are unchanged.",
   "R1": "A2 generation rate (median) is at least 3.5 times A1's",
   "R2": "both arms pass the health gate: A1 share of peak between 60% and 100%; A2 share between 25% and 80% (an MoE reads fewer bytes per token but its kernels are less bandwidth-bound)",
   "R3": "A1 median generation rate between 70 and 100 tok/s",
   "R4": "the majority of completions on both arms end with finish_reason 'length' at 500 tokens (reasoning on by default)",
   "confidence": "R1 medium, R2 low for A2, R3 medium, R4 medium",
   "recorded_not_predicted": "TTFT, prompt tokens, per-block drift, tps by Vol.1 word count",
   "reading": "a failed R is reported as failed and does not void the run; pass is P1-P3 plus the health gate"},
 "outputs": ["requests.jsonl", "events.jsonl", "analysis.json", "ctx.txt", "logs/ (not published)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p50_speed.json")
if os.path.exists(path):
    sys.exit("prediction_p50_speed.json exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
