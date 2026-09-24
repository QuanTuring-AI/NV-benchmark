#!/usr/bin/env python3
"""Vol.2 long context · addendum · write prediction_p53_longctx_addendum.json once, before the measured run.
usage: p53_longctx_addendum_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p53_longctx_addendum")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.2 · long context, addendum: the main run's depth measurement repeated on A2 (all four depths) and A1 (16k only) with a timed warm-up phase before the measured requests",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p53_longctx_addendum.sh refuses to start if this file or its .sha256 is missing or changed, or if requests.jsonl exists.",
 "runs": "one run",
 "why": "in the main run (results/p53_longctx/, 2026-09-23 03:18-04:11) every A2 container's first requests were slower than its later ones -- 1k depth: 122, 119, 128, 171, 280 tok/s across the five measured requests; 4k: 140, 190, 295, 315, 315; 16k: 308-315 (first TTFT 6.0 s, then 0.5 s); 64k: 257-262 then 311 -- so the A2 medians at 1k and 4k (128 and 295 tok/s) describe the engine's first minute after READY, not its steady state, and the A2 decay shape against the 1k depth is meaningless. A1 showed no drift (71.4-72.2 at 1k, 70.8-72.2 at 4k). One discarded request is not a warm-up for A2. The main run's files are not modified; this addendum adds a warm-up phase and re-measures. A1 at 16k is included so that the A1 step from 72 to 45 tok/s between 4k and 16k is measured a second time, in a container whose full log is saved.",
 "stack": "as results/p53_longctx/prediction_p53_longctx.json: same images, profiles, max_num_seqs 32, NIM_MAX_MODEL_LEN per depth, prompts (same question bank, same offsets 0/13/26/39/52 for the measured requests), max_tokens 256, temperature 0",
 "changed": "before the measured requests: discarded requests at the same depth (offsets 1000, 1007, ...) until at least 60 s and 6 requests have passed and the last three generation rates agree within 5% and all three are at or above 220 tok/s on A2 (0 on A1), or 25 requests / 300 s have been spent (the depth is then marked not stabilized and measured anyway). The 220 tok/s threshold is a default chosen from the observations so far: slow-phase rates 119-175 tok/s, steady rates 256-319 tok/s, no observation between; it exists because in the second harness test the slow phase's rates agreed within 5% (160, 167, 165) and a stability rule alone would have ended the warm-up inside the slow phase; every warm-up row recorded with warmup=true; the container's log is saved before removal. Why adaptive: the slow phase's length varied between observations (3 requests in the clock diagnosis, more than 6 and more than 7 in the addendum's two harness tests)",
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p53_longctx_addendum.py", "vol2/scripts/p53_longctx_addendum_analyze.py", "vol2/scripts/run_p53_longctx_addendum.sh",
                                      "vol2/scripts/p53_longctx.py", "vol2/scripts/p53_longctx_analyze.py", "vol2/scripts/p50_footprint.py", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {"benchmark/questions.json": h("benchmark/questions.json")},
 "analysis_rules": {"preconditions": "the main run's, on the measured rows only: per (arm, depth) P1 all HTTP 200 with usage · P2 prompt_tokens median within 25% of the target · P3 one container up. Warm-up rows are summarised (count, first/median/last generation rate) and never enter the medians.",
                    "shape": "TTFT and generation-rate ratios of each depth to the shallowest depth per arm, as the main run; plus the ratio of each addendum median to the main run's median",
                    "program": "vol2/scripts/p53_longctx_addendum_analyze.py (the main analyser's 6 self-test cases plus 3)"},
 "predictions": {
   "basis": "clock diagnosis 2026-09-23 06:03-06:13 (A2, 1k prompts, nvidia-smi every 0.5 s): the first three requests after READY ran at 147-162 tok/s with TTFT 2-3 s while the SM clock was already 2.9 GHz and power 122-143 W (not a clock limit: the engine is doing something else); from the fourth request 289-298 tok/s and TTFT 87-121 ms; the slow phase did not return after 20 s or 30 s idle; back-to-back requests ran 5-8% faster than requests 2 s apart (316-319 vs 292-318 tok/s, 340-355 W vs 150-185 W). The addendum's harness test the same morning saw six 1k requests over 43 s all at 146-161 tok/s. main run rows above; A2 single-stream steady state elsewhere in this volume 295-315 tok/s (p50_speed 305, p53_answer 299, concurrency c=1 265-269 by AIPerf); A1 16k main run 44.4-46.7 tok/s with the engine's max_seq_len_to_capture 8192 in its config dump (sequences longer than that run without CUDA graphs on this vLLM V0 build)",
   "R1": "A2 measured generation rate at 1k and 4k is 280-330 tok/s (the warm-up removes the main run's 128 and 295 medians' contamination; 4k is expected to move little)",
   "R2": "A2 generation rate at 64k is within 15% of its 4k rate (main run: 259 vs 295, 12% down)",
   "R3": "A2 TTFT at 64k is between 15x and 40x its 1k TTFT once both are warm (main run 1k TTFT was 275 ms during warm-up; the last warm 1k request measured 89 ms)",
   "R4": "the warm-up sequence on A2 shows a rising generation rate at every depth (first warm-up request below the last by more than 10%)",
   "R5": "A1 at 16k measures 42-48 tok/s again, warm-up or not (no drift on A1)",
   "R6": "the warm-up stabilizes (last three rates within 5%) within 25 requests at every A2 depth",
   "confidence": "R1 medium, R2 medium, R3 low, R4 medium, R5 high, R6 low",
   "reading": "a failed R is reported as failed; pass is P1-P3 per depth. No number transfers to another machine; only the decay shape is compared with the external DGX Spark measurement, and only for A2."},
 "outputs": ["requests.jsonl (warm-up rows marked)", "events.jsonl", "analysis.json", "ctx.txt", "logs/ (not published)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p53_longctx_addendum.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
