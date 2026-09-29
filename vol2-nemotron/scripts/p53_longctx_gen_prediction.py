#!/usr/bin/env python3
"""Vol.2 long context · write prediction_p53_longctx.json once, before the measured run.
usage: p53_longctx_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p53_longctx")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.2 · long context · TTFT, generation rate and memory at READY at prompt depths of about 1k, 4k, 16k and 64k tokens, both Nemotron arms, each depth in a container sized for it",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p53_longctx.sh refuses to start if this file or its .sha256 is missing or changed, or if requests.jsonl exists.",
 "runs": "one run",
 "why": "both models are hybrid Mamba-2 architectures whose state does not grow with context (only the few attention layers keep a KV cache); this is their stated advantage and Vol.3's RAG prompts are long. Nothing here has been measured before in this repository.",
 "stack": "as vol2/results/p50_footprint for images and profiles; both arms at max_num_seqs 32 (A1 NIM_MAX_NUM_SEQS, A2 NIM_PASSTHROUGH_ARGS); NIM_MAX_MODEL_LEN per depth = smallest of 4096, 8192, 32768, 131072 holding depth + 512",
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p53_longctx.py", "vol2/scripts/p53_longctx_analyze.py", "vol2/scripts/run_p53_longctx.sh", "vol2/scripts/p50_footprint.py", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {"benchmark/questions.json": h("benchmark/questions.json")},
 "design": {"prompt": "questions from benchmark/questions.json (public, Vol.1's set) concatenated until 3.6 x depth characters, five prompts per depth from different offsets, plus a one-line summary instruction; synthetic by repetition, not natural long text -- the attention pattern of a real RAG prompt is not reproduced and the README says so",
            "requests": "5 per depth, max_tokens 256, temperature 0, no system prompt; one discarded request after READY; the engine's prompt_tokens is the depth measured",
            "memory": "GPU memory in use and KV tokens recorded at READY for every (arm, depth) container: each depth's own level, not the footprint run's",
            "ceiling": "a container that fails to start at a depth is recorded as that arm's context ceiling at that NIM_MAX_MODEL_LEN; the other arm is not lowered to match"},
 "analysis_rules": {"preconditions": "per (arm, depth): P1 all HTTP 200 with usage · P2 prompt_tokens median within 25% of the target · P3 one container up. Any failure -> that depth's timing null.",
                    "shape": "TTFT and generation-rate ratios of each depth to the shallowest depth per arm",
                    "program": "vol2/scripts/p53_longctx_analyze.py (6 self-test cases)"},
 "predictions": {
   "basis": "harness test 2026-09-22 (A1, depths 1k and 4k, 2 requests each): prompt_tokens 1,099-1,135 and 3,764-3,789, TTFT 128-130 and 378-401 ms, generation 72.7-75.3 tok/s at both depths. external DGX Spark measurement of Nemotron 3 Nano: generation 56.19 -> 51.4 tok/s from 0 to 100k context (down 8.5%) (P52 section 6); prefill cost grows with prompt length on any architecture; both models advertise 128k contexts",
   "R1": "generation rate at 64k is within 15% of the 1k rate on both arms (the Mamba state does not grow; only the attention layers' KV does)",
   "R2": "TTFT grows roughly linearly with depth: 64k TTFT between 30x and 120x the 1k TTFT on both arms",
   "R3": "both arms start at NIM_MAX_MODEL_LEN 131072 on this card at max_num_seqs 32 (no context ceiling within the depths tried)",
   "R4": "memory at READY at 131072 exceeds the 4096-context level by less than 6 GB on A2 and by less than 10 GB on A1",
   "confidence": "R1 medium, R2 low, R3 low, R4 low",
   "reading": "a failed R is reported as failed; pass is P1-P3 per depth. No number here transfers to another machine: the README compares only the decay shape with the external measurement."},
 "outputs": ["requests.jsonl", "events.jsonl", "analysis.json", "ctx.txt", "logs/ (not published)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p53_longctx.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
