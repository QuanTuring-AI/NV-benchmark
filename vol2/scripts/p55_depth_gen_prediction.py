#!/usr/bin/env python3
"""Vol.2 · depth probes after P53 · write prediction_p55_<EXP>.json once, before the measured run.
usage: p55_depth_gen_prediction.py <a1_capture|longctx_120k> <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

EXP = sys.argv[1]; assert EXP in ("a1_capture", "longctx_120k")
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", f"p55_{EXP}")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()
common = {
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p55_depth.py", "vol2/scripts/p55_depth_analyze.py", "vol2/scripts/run_p55_depth.sh",
                                      "vol2/scripts/p53_longctx.py", "vol2/scripts/p50_footprint.py", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {"benchmark/questions.json": h("benchmark/questions.json")},
 "design_common": "one container per condition; warm-up at the measured depth: discarded requests until >= 60 s and >= 6 requests and, on A2, the last three generation rates within 5% and >= 180-220 tok/s (cap 25 requests / 600 s); A1 has shown no slow phase in any container and gets the minimum only; then five measured requests (offsets 0/13/26/39/52), max_tokens 256, temperature 0, top_p 0.9, 2 s apart; request, prompt builder and client exactly p53_longctx's (TTFT client-side through requests); memory and KV tokens at READY; the container's full log saved before removal",
 "analysis_rules": {"preconditions": "per condition, on the measured rows: P1 all HTTP 200 with usage · P2 prompt_tokens median within 25% of the target · P3 one container up at every request and, where a capture length or an eager setting is intended, the engine's own config dump in the startup log shows it. A condition that does not start is recorded with the engine's refusal as that arm's ceiling at that model length.",
                    "program": "vol2/scripts/p55_depth_analyze.py (12 self-test cases; five mutations of the attribution and precondition rules each fail one case); run on the harness tests' real rows before this file was written"}}

if EXP == "a1_capture":
    p = {
     "experiment": "Vol.2 · A1 (Nemotron Nano 9B v2, NIM 1.12.2): is its 38% generation-rate step past 8k prompt tokens the loss of CUDA graphs? Reverse test with one variable (NIM_DISABLE_CUDA_GRAPH) at ~3.8k and ~14k tokens, plus the forward attempt (raise the capture limit) recorded as not delivered",
     "written_at": sys.argv[2],
     "written_before": "the measured run. run_p55_depth.sh (EXP=a1_capture) refuses to start if this file or its .sha256 is missing or changed, or if requests.jsonl exists.",
     "runs": "one run, five conditions in order: a1_4k_default, a1_4k_eager, a1_16k_default, a1_16k_eager, a1_16k_capture",
     "why": "p53_longctx and its addendum measured A1 at 71.7 / 71.6 tok/s at 1k / 4k and 44.7 / 45.8 at 16k and 44.4 at 57k: a step, then flat. Every A1 engine config dump reads \"max_seq_len_to_capture\": 8192, and the README attributed the step to decode running without CUDA graphs past that length. That attribution was an inference; P55 asks for a measurement.",
     "what_the_image_allows": "the forward test (raise the capture limit to 32768) cannot reach this engine: NIM 1.12.2 builds the engine arguments itself (--async-engine-args JSON, entrypoints/launch.py) and reads a fixed set of NIM_* variables; NIM_PASSTHROUGH_ARGS is not among them, and a harness test with it set showed the config dump still at 8192. The only CUDA-graph variable the image reads is NIM_DISABLE_CUDA_GRAPH, mapped to enforce_eager (nim_llm_sdk/entrypoints/args.py:53). Hence the reverse test: remove graphs where the default uses them (~3.8k tokens) and where it does not (~14k).",
     "conditions": {"a1_4k_default": {"NIM_MAX_MODEL_LEN": "8192", "NIM_MAX_NUM_SEQS": "32"},
                    "a1_4k_eager": {"NIM_MAX_MODEL_LEN": "8192", "NIM_MAX_NUM_SEQS": "32", "NIM_DISABLE_CUDA_GRAPH": "1"},
                    "a1_16k_default": {"NIM_MAX_MODEL_LEN": "32768", "NIM_MAX_NUM_SEQS": "32"},
                    "a1_16k_eager": {"NIM_MAX_MODEL_LEN": "32768", "NIM_MAX_NUM_SEQS": "32", "NIM_DISABLE_CUDA_GRAPH": "1"},
                    "a1_16k_capture": {"NIM_MAX_MODEL_LEN": "32768", "NIM_MAX_NUM_SEQS": "32", "NIM_PASSTHROUGH_ARGS": "--max-seq-len-to-capture 32768"}},
     "attribution_rule": "reverse (the attribution of record): r4 = 4k eager/default, r16 = 16k eager/default generation-rate medians; r4 <= 0.75 and 0.90 <= r16 <= 1.10 -> 'measured: turning CUDA graphs off reproduces the step at 4k and changes nothing at 16k'; r4 >= 0.90 -> 'withdrawn: CUDA graphs do not explain the step'; otherwise 'partial'; any 2x2 condition failing its preconditions (including its engine config not showing the intended enforce_eager) -> 'unverified'. Forward: capture/default at 16k >= 1.40 'measured', <= 1.10 'withdrawn', else 'partial'; the capture setting absent from the engine config -> 'unverified' (expected)",
     "note": "the eager and capture conditions are not A1's default configuration; they are control arms and do not replace A1's numbers",
     "predictions": {"basis": "harness tests on 2026-09-23 (2 measured requests each): a1_16k_default 52.5 tok/s, a1_16k_capture 46.4 with its config dump at 8192; a1_4k_eager tested for the eager read-back only. above; at 72 tok/s a decode step takes ~14 ms and at 45 tok/s ~22 ms, a constant per-step difference across 16k-57k, which is the signature of losing graph replay rather than of a state growing with context",
                     "R1": "a1_4k_default reproduces 68-76 tok/s and a1_16k_default 42-50 tok/s",
                     "R2": "the reverse verdict is 'measured' (4k eager lands near the 16k rate; 16k eager equals 16k default)",
                     "R3": "the forward attempt is 'unverified': the capture condition's engine config shows 8192",
                     "R4": "memory at READY is lower with graphs off by less than 1 GB (graph pools)",
                     "confidence": "R1 high, R2 medium, R3 high, R4 low",
                     "reading": "a failed R is reported as failed"},
     **common}
else:
    p = {
     "experiment": "Vol.2 · long context at ~120k prompt tokens on both arms (NIM_MAX_MODEL_LEN 131072, max_num_seqs 32): TTFT, generation rate, memory at READY",
     "written_at": sys.argv[2],
     "written_before": "the measured run. run_p55_depth.sh (EXP=longctx_120k) refuses to start if this file or its .sha256 is missing or changed, or if requests.jsonl exists.",
     "runs": "one run, conditions in order a2_120k, a1_120k",
     "why": "p53_longctx reached 57k prompt tokens: its character budget, not a limit found. The external DGX Spark measurement of Nemotron 3 Nano runs to 100k context; a ~120k point on this card lets the decay shape be compared over the same range (shape only, never absolute values).",
     "character_budget": "build_prompt depth 138,620 (the 64k point measured 0.866 prompt tokens per budget token) targeting ~120,000 prompt tokens; target recorded as 120,000",
     "predictions": {"basis": "the ranges below were written before the harness test; the harness test (2026-09-23, 2 measured requests each) then measured A2 at 119,729 prompt tokens 307 tok/s, TTFT 7.3 s, and A1 at 119,725 tokens 41-53 tok/s, TTFT 14.3 s, both starting at 131072 -- the ranges are kept as written. p53_longctx_addendum after warm-up: A2 304.8 / 298.9 / 315.2 / 309.0 tok/s at 1k / 4k / 16k / 57k, TTFT 95 / 155 / 489 / 2,371 ms; A1 71.7 / 71.6 / 44.7 / 44.4 tok/s, TTFT 157 / 408 / 1,398 / 6,201 ms; A1 at NIM_MAX_MODEL_LEN 131072 holds 456,131 KV tokens with chunked prefill switched on by the image; A2 holds ~3.1M fp8 KV tokens; the first request at a new depth pays a one-time cost (A2 8.7 s, A1 20.4 s at 57k)",
                     "R1": "both arms start and serve at NIM_MAX_MODEL_LEN 131072 with a ~120k prompt (no ceiling below 120k)",
                     "R2": "A2 generation at ~120k is within 10% of its 1k value (304.8 tok/s)",
                     "R3": "A2 TTFT at ~120k is between 4.5 and 9 s",
                     "R4": "A1 generation at ~120k is between 38 and 48 tok/s (the post-8k plateau continues)",
                     "R5": "A1 TTFT at ~120k is between 12 and 30 s",
                     "confidence": "R1 medium, R2 medium, R3 low, R4 medium, R5 low",
                     "reading": "a failed R is reported as failed. If an arm does not start at 131072, the deepest measured depth is that arm's maximum on this card and the other arm is not lowered to match"},
     **common}
check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, f"prediction_p55_{EXP}.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
