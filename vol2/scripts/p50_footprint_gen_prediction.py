#!/usr/bin/env python3
"""Vol.2 footprint · write prediction_p50_footprint.json once, before the measured run.
usage: p50_footprint_gen_prediction.py <written_at>   (pass "$(date +%FT%T%z)")"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p50_footprint")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.2 · footprint decomposition · minimum GPU memory budget of Nemotron Nano 9B v2 (bf16) and Nemotron 3 Nano (NVFP4) on one RTX 5090, and whether the Nemotron 3 Nano FP8 profile starts at all",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p50_footprint.sh refuses to start if this file or its .sha256 is missing or changed, or if configs.jsonl exists.",
 "runs": "one run per arm; a start that fails is recorded, never retried to obtain a different outcome",
 "question": "On this card: (a) what memory does each model hold after the engine fills its default budget (the level, not the footprint); "
             "(b) what is the smallest engine budget at which each model starts and serves three short questions to completion at "
             "NIM_MAX_MODEL_LEN 4096; (c) does the FP8 profile of Nemotron 3 Nano, whose image states >= 34 GB, start on a 32,607 MiB card at that context length.",
 "why_this_design": "the memory a NIM shows in nvidia-smi is the budget it was allowed (gpu_memory_utilization x card), filled with KV cache, "
                    "so it grows and shrinks with the card and says nothing about what the model needs. NIM_KVCACHE_PERCENT sets that budget "
                    "directly in both images (it is the variable both map to vLLM gpu_memory_utilization). Lowering it until the engine refuses "
                    "to start -- it refuses when the KV cache that fits cannot hold NIM_MAX_MODEL_LEN -- finds the physical lower bound.",
 "stack": {"card": "NVIDIA GeForce RTX 5090, 32,607 MiB, driver 591.86",
           "A1": "nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2:1.12.2 (index sha256:a2f4a5ae...), profile 5cf34bab... vllm-bf16-tp1-pp1, NIM_MAX_MODEL_LEN=4096, NIM_MAX_NUM_SEQS=32 (as the earlier E7 arm)",
           "A2": "nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12 (index sha256:bd38d2d5...), profile 1fba9ecf... vllm-nvfp4-tp1-pp1, NIM_MAX_MODEL_LEN=4096 (as the earlier E7 arm)",
           "A2FP8": "same image, profile 8c91cce8... vllm-fp8-tp1-pp1 (image states >= 34 GB/GPU), NIM_MAX_MODEL_LEN=4096",
           "nim_versions_differ": "A1 is NIM 1.12.2 and A2 is NIM 2.0.12; no common version exists (vol2/results/p50_availability). The arms are two deployment options, each in its own image; nothing here is a single-variable comparison.",
           "other_settings": "all other NIM settings default; VLLM_USE_V2_MODEL_RUNNER not set (the E7 arms started without it)"},
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p50_footprint.py", "vol2/scripts/p50_footprint_analyze.py",
                                      "vol2/scripts/run_p50_footprint.sh", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {"benchmark/questions.json": h("benchmark/questions.json")},
 "design": {
   "sequence_per_arm": "default (no budget override) -> NIM_KVCACHE_PERCENT 0.85, 0.80, ... down in steps of 0.05 until a start or probe fails -> one more start at the last passing value minus 0.025",
   "records_per_start": "nvidia-smi before launch, at READY, after the probe, after stop; /metrics cache_config_info (gpu_memory_utilization, num_gpu_blocks, block_size); startup-log lines for clamping, model loading, GPU KV cache size, maximum concurrency; failure reason text",
   "viable": "the start reached READY and all three probe questions (benchmark q001, q004, q011: factual short answers) returned HTTP 200 with finish_reason 'stop' at max_tokens 512, temperature 0.0, top_p 0.9. A completion cut at max_tokens is not viable. Response text is not stored (SHA-256 and length only).",
   "sweep_resolution": "0.05 of the card (1,630 MiB), refined once to 0.025 (815 MiB). The minimum lies between the smallest passing and the largest failing budget.",
   "desktop_state": "the desktop holds about 2.8-3.0 GB of the card during the run; NIM clamps the default budget on a busy card (recorded from the log). Budgets set explicitly are used as given.",
   "arm_order": "A1, then A2, then A2FP8; each start on an otherwise idle GPU (no other container)"},
 "analysis_rules": {
   "preconditions": "P1 default row per arm · P2 every READY row has a gpu_ready reading and a three-row probe · P3 probe ids are the three pre-registered ones. Any failure -> conclusions null.",
   "statistics": "single readings per start; no averaging. bound_reached is true only when a smaller budget was tried and failed.",
   "program": "vol2/scripts/p50_footprint_analyze.py (11 self-test cases)"},
 "predictions": {
   "basis": "measured weight bytes in the NIM cache: A1 17.78 GB bf16, A2 19.34 GB NVFP4 (vol2/results/p50_availability); Vol.1-B: Llama 8B bf16 (16.06 GB) at NIM_MAX_MODEL_LEN 8192 ran inside a 0.86 x 32,607 MiB budget with KV 81,504-97,328 tokens; the images' own profile requirements (A2 nvfp4 >= 21 GB, A2 fp8 >= 34 GB); E7 levels A1 29,287 and A2 31,730 MiB. Seen before this file was written, in two harness tests of the default configuration only (2026-09-21, harness_test/, not part of this run): A1 READY at 31,575 MiB with 2,744 before launch, log 'Model loading took 16.5842 GiB', 'Maximum concurrency for 4096 tokens: 106.21x'; A2 READY at 29,677 MiB with 2,682 before, clamp 0.92 -> 0.86, KV 2,289,664 tokens; all six probe questions ended with finish_reason stop under /no_think (without it, A1 hit max_tokens on all three, which is why the probe carries that system message). No budget below the default was tried before this file.",
   "R1": "A1 smallest passing budget between 0.60 and 0.75 of the card (19.6-24.5 GB)",
   "R2": "A2 (NVFP4) smallest passing budget between 0.65 and 0.80 of the card (21.2-26.1 GB)",
   "R3": "A2FP8 does not reach READY at the default budget on this card (the engine refuses or runs out of memory)",
   "R4": "for A1 and A2 the default-level memory at READY (delta over pre-launch) is within 2,000 MiB of the effective gpu_memory_utilization x card total, i.e. the level is the budget, not the model",
   "confidence": "R1 medium, R2 medium, R3 low, R4 medium",
   "recorded_not_predicted": "KV tokens at each budget; the engine's model-loading line; seconds to READY",
   "reading": "a failed R is reported as failed and does not void the run; pass is P1-P3"},
 "outputs": ["configs.jsonl", "analysis.json", "ctx.txt", "logs/<container>.startup.log.txt (not published)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p50_footprint.json")
if os.path.exists(path):
    sys.exit("prediction_p50_footprint.json exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
