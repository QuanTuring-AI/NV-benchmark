#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q3 · write prediction_p62_rag.json once, before the measured run.
usage: p62_gen_prediction_rag.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "vol1b", "scripts"))
from prediction_guard import check_prediction

OUT = os.path.join(REPO, "vol1a-revisit", "results", "p62_rag")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()
HT = json.load(open(os.path.join(OUT, "harness_test_record.json"), encoding="utf-8"))
p = {
 "experiment": "Vol.1-A revisit, P62 Q3 · Llama 3.1 8B Instruct on one RTX 5090 · the RAG profile (R: 3,500+-300 input / 500+-50 output tokens) for the two NIM configurations, N-BF16 and N-FP8, with prefix-cache reuse read from the server's own counters instead of inferred from time to first token.",
 "written_at": sys.argv[1],
 "written_before": "the measured run's first container. run_p62_rag.sh refuses to start if this file or its .sha256 is missing or changed, or if levels.jsonl exists.",
 "why": "P54's RAG profile was null because its warm-up level and its c=1 level shared a seed, so the same prompts were served twice and the engine reused their cached prefixes. P59 removed every shared prompt by design and checked reuse through time to first token only; its N-FP8 RAG calibration then failed (AIPerf p50 time to first token 208 ms against the harness's own 156 ms), without a way to tell whether a cached prefix was involved. This run counts reuse on the server: vLLM's prefix-cache query and hit counters (tokens), read before and after every calibration request and around every level.",
 "scope": "Speed only, profile R, NIM arms only (P59's three Ollama arms passed their RAG calibration and are not re-run). P54's RAG result stays null and is not re-run. NIM on this card uses vLLM profiles only.",
 "arms": "N-BF16 (profile 092ed421, vllm-bf16) and N-FP8 (profile c4789f7a, vllm-fp8) as P59: NIM 2.0.12, NIM_MAX_MODEL_LEN 8192, VLLM_USE_V2_MODEL_RUNNER=0",
 "order": "N-BF16 main, N-BF16 fresh, N-FP8 main, N-FP8 fresh",
 "harness": "vol1a-revisit/scripts/p62_rag.py, which imports P59's harness unchanged and adds the counter reads. Per main container: isolation, the counter-based detector (a discarded long prompt; one ~3,500-token prompt twice, whose second request must show hits >= 50% of its queried tokens: the positive control; two nonce-led prompts, whose second must show hits <= 2%), a discarded 60 s profile-C warm-up and one 60 s profile-C c=1 level (only for P59's health gate), a discarded 120 s R warm-up level (seed 20260927+9000), the 20-request R calibration with counters per request, then R levels 1, 8, 16, 32, 64, 128 (60 s, seed 20260927+n). Fresh container: the detector, the R warm-up, then 64 and 128.",
 "harness_test": HT.get("summary", ""),
 "analysis_rules": {"program": "vol1a-revisit/scripts/p62_rag_analyze.py (8 self-test cases), which runs P59's frozen analysis program and adds: the detector must fire and its negative form stay <= 2%, else that container's levels are unusable; any calibration request with hits > 2% of its queried tokens (or no counter reading) rejects the calibration, so every main-container R level of that arm is unusable; any level whose counter delta shows hits > 2% -> that level unusable ('prefix-cache hits'); no counter delta -> unusable ('no counter'). The calibration comparison itself is P59's: AIPerf c=1 p50 TTFT within max(20 ms, 20%) and p50 inter-token latency within 20% of the harness's own.",
   "conclusion": "per arm: the table of usable R levels (total and per-user tok/s, p99 TTFT, p99 TPOT, server and interactive SLO flags) with the largest level inside each SLO, or null with the reason; the N-FP8 vs N-BF16 crossing by P59's rule. 2% allows for the chat template's fixed preamble, which every request shares.",
   "anchors": "each level's total tok/s beside P59's value for the same cell, reported and not used by any rule",
   "server_side_reading": "reported, not a gate: the server's own TTFT and prefill time (vLLM histograms' sum and count, read around each calibration request) for the harness's prompts, and AIPerf's own server-metrics export for each level; they show whether a gap between AIPerf and the harness's own client is in the client or in the server",
   "secondary_table": "never the conclusion: for an arm whose primary calibration failed, if AIPerf's c=1 mean TTFT is within max(20 ms, 20%) of the server's own mean TTFT for the same requests, its R levels that were otherwise clean (rc 0, no errors, engine alive, hits <= 2%) are listed under rag.<arm>.secondary_not_the_conclusion, labelled as such"},
 "predictions": {
   "basis": "P59's R values (N-BF16 total 81 / 393 / 587 tok/s at 1 / 8 / 128, p99 TTFT 388 ms at c=1 and 2,202 ms at c=8; N-FP8 138 / 637 / 999, p99 TTFT 238 / 933 / 2,119 ms at 1 / 8 / 16) and the harness test of this run",
   "Q3-1": "the positive control fires on every container of both arms (second request of the repeated prompt: hits >= 50% of queried tokens)",
   "Q3-2": "every calibration request and every level shows hits <= 2% of queried tokens (only the shared template preamble)",
   "Q3-3": "N-BF16's R calibration passes",
   "Q3-4": "N-FP8's R calibration fails again on time to first token, with no prefix-cache hits (both harness tests already showed this; the prediction is stated so that the real run can contradict it)",
   "Q3-4b": "N-FP8: AIPerf's c=1 mean TTFT agrees with the server's own within max(20 ms, 20%), and the server's own TTFT is shorter for the harness's prompts than for AIPerf's (so a secondary table exists)",
   "Q3-5": "largest R level inside the server SLO (among 1, 8, 16, ...): N-BF16 1, N-FP8 8",
   "Q3-6": "N-FP8 ahead of N-BF16 on R total throughput at every level both have usable (if both conclusions exist)",
   "Q3-7": "anchors: every N-BF16 level within 0.85-1.15 of P59",
   "confidence": "Q3-1 high, Q3-2 high, Q3-3 medium, Q3-4 high, Q3-4b high, Q3-5 medium, Q3-6 high, Q3-7 medium",
   "reading_of_predictions": "a failed prediction is reported as failed. If N-FP8's calibration fails again, its RAG conclusion is null with that reason; nothing is re-run and no tolerance is changed."},
 "harness_sha256": {k: h(k) for k in ("vol1a-revisit/scripts/p62_rag.py", "vol1a-revisit/scripts/p62_rag_analyze.py", "vol1a-revisit/scripts/run_p62_rag.sh",
                                      "vol1a-revisit/scripts/p59_nim_value.py", "vol1a-revisit/scripts/p59_analyze.py", "vol2/scripts/p54_engine.py",
                                      "vol1a-revisit/results/p59_nim_value/analysis.json", "vol1b/scripts/prediction_guard.py")},
}
check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p62_rag.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
