#!/usr/bin/env python3
"""Vol.2 concurrency v2 · write prediction_p53_concurrency_v2.json once, before the measured run.
usage: p53_concurrency_v2_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p53_concurrency_v2")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.2 · closed-loop concurrency, second run: the v1 sweeps (results/p53_concurrency/, conclusions null under their own gate) repeated with a repaired instrument gate — warm-up level before calibration, calibration prompt matched to the profile, engine death treated as the ceiling",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p53_concurrency_v2.sh refuses to start if this file or its .sha256 is missing or changed, or if levels.jsonl exists.",
 "runs": "one run",
 "relation_to_v1": "v1's pre-registration, harness, results and analysis are published unchanged; every v1 sweep's conclusions are null because its calibration gate (P2) failed on all A2 and A1-R sweeps and its P1 failed on every A1 sweep with an engine crash. The v1 level tables are valid measurements (P1 held on every A2 level) and are what the predictions below are built from — so this pre-registration is informed by v1's numbers and says so; what v2 tests is whether they reproduce under a gate that can pass.",
 "why_v1_gate_failed": {"A2_ITL": "the calibration ran first after READY; over its ten requests A2's per-token time fell from 5.2 to 4.3 ms and AIPerf's c=1 level a minute later measured 3.7 ms (a 25% gap against a 20% tolerance): the engine's first minute of traffic is not its steady state (FlashInfer NVFP4 MoE kernels are tuned on first use). A1 (bf16, no JIT) showed no such drift (13.9 vs 13.8 ms).",
                        "R_TTFT": "the calibration prompt was ~200 tokens on both profiles, so on the R profile it was compared with AIPerf's c=1 TTFT on 3,500-token prompts (57 vs 339 ms): a comparison of prompt lengths, not of instruments.",
                        "A1_crash": "A1's engine died at c=32 (IndexError 'pop from empty list' in vllm/model_executor/models/constant_size_cache.py, reached from the model's Mamba cache); every later level of that sweep measured a dead server, so v1's P1 (all levels clean) could never hold. That is a result, not an instrument fault, and v2's rules say so before the run."},
 "ttft_floor": "20 ms, changed from v1's 15 ms before this file was frozen and after the v2 harness test of 2026-09-23 05:33: with ITL agreeing within 2%, the own client's first-chunk median has sat 9.5, 12.3 and 15.05 ms above AIPerf's in three C-profile calibrations (fresh connection per request, medians). That is the difference between two HTTP stacks on this host, and a gate meant to catch an instrument error (the mock that once added 115 ms) should not null a sweep for it. 20 ms covers the observed offsets with a margin and is still an order of magnitude below such an error. The own-client prompt was also 235 tokens against AIPerf's 203 in that test; the repeats are now sized from the measured 10.7 tokens per repeat. Both are defaults, not confirmed by anyone.",
 "stack": {"as_v1": "images, profiles, NIM_MAX_MODEL_LEN 8192, max_num_seqs 32 on both arms (A1 NIM_MAX_NUM_SEQS, A2 NIM_PASSTHROUGH_ARGS), levels 1-64, durations, AIPerf 0.11.0 flags, fresh-container repeat of the two highest levels — all imported from vol2/scripts/p53_concurrency.py, which is not modified",
           "changed": "order per main container: discard request → 120 s AIPerf level at c=1 (recorded with warmup=true, excluded from analysis; 120 s rather than 60 because A2's slow phase after READY lasted more than 45 s in two long-context harness tests on 2026-09-23) → own-client calibration (one discarded request + 10, back to back as AIPerf's closed loop at c=1 -- on A2 requests 2 s apart ran 5-8% slower than back-to-back ones in the clock diagnosis of 2026-09-23 -- new connection each, prompt of ~ISL tokens: 19 or 328 repeats of a sentence measured at 10.7 tokens, i.e. ~203 or ~3,500 prompt tokens, max_tokens = OSL 200 or 500, ignore_eos) → the sweep. After any level with errors the harness sends a one-token request; if the engine answers anything but 200 the level is marked engine_dead, the remaining levels are skipped and recorded as skipped. Container logs (trimmed) are saved before removal."},
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p53_concurrency_v2.py", "vol2/scripts/p53_concurrency_v2_analyze.py", "vol2/scripts/run_p53_concurrency_v2.sh",
                                      "vol2/scripts/p53_concurrency.py", "vol2/scripts/p50_footprint.py", "vol1b/scripts/prediction_guard.py")},
 "analysis_rules": {"preconditions": "per (arm, profile, container): P1 every level below the first engine-death level has rc 0, a summary and 0 request errors, at least one such level exists, and no level was run after the death · P2 AIPerf's c=1 TTFT and ITL medians within 20% of the own client's medians (TTFT alternatively within 20 ms), both on the profile's prompt length, after the warm-up level; fresh sweeps use the main calibration · P3 max_num_seqs 32 (recorded env). Any failure -> that sweep's conclusions null.",
                    "ceiling": "engine crash at c=N (levels below stand) · reached at c=N (first level failing the Server SLO) · not reached within the range",
                    "slo": "MLPerf Inference v5.1 Llama 3.1-8B: server p99 TTFT ≤ 2,000 ms and p99 TPOT ≤ 100 ms; interactive 500 ms / 30 ms. These are another model's limits, chosen here because no Nemotron SLO exists in MLPerf; they are the same on every row.",
                    "program": "vol2/scripts/p53_concurrency_v2_analyze.py (16 self-test cases)"},
 "predictions": {
   "basis": "v1 (2026-09-23 01:21-03:18, same containers and levels): A1 engine died at c=32 on C-main, C-fresh (at 64; c=32 survived once), R-main and R-fresh; A1 C levels 1-16: p99 TTFT 75-573 ms, p99 ITL 14-22 ms, 71-721 tok/s; A1 R levels 1-16: p99 TTFT 0.5-7.3 s (c=8 7.3 s, c=16 6.5 s), p99 ITL 14-42 ms. A2 C: p99 TTFT 113-449 ms and p99 ITL 3.7-27.8 ms through c=32, 1,323 tok/s at 32 and 1,327 at 64 with p99 TTFT 5.1 s; fresh 1,403 / 1,282. A2 R: p99 TTFT 269 ms (c=1), 520 (c=4), 1,151 (c=8), 2,481 (c=16), 5,118 (c=32), 16.3 s (c=64); p99 ITL ≤ 27 ms throughout; 1,197 tok/s at 32, 1,309 at 64; fresh 1,244 / 1,324. v1 calibration on A1 C after repair of the connection reuse: own 60.8 vs AIPerf 51.3 ms TTFT, ITL within 0.7%.",
   "R1": "A1's engine dies at c=32 on both profiles in the main sweep (all requests HTTP 500 after AIPerf's warm-up requests), and the harness records it as the ceiling with levels 1-16 intact",
   "R2": "A2 on profile C: largest concurrency inside the Server SLO = 32 and inside the Interactive SLO = 32; throughput saturation at 32; c=64 fails the Server SLO on TTFT (queueing beyond max_num_seqs)",
   "R3": "A2 on profile R: largest concurrency inside the Server SLO = 8 and inside the Interactive SLO = 2",
   "R4": "the calibration gate passes on all four main sweeps (ITL within 10% on A1 and within 20% on A2 after the warm-up level; TTFT within 20% or 20 ms on the matched prompt)",
   "R5": "fresh-container repeats agree with the main sweep within 25% on output throughput at every level both ran (A2 all four; A1 only where both survived)",
   "R6": "A1 on profile C, levels 1-16: inside the Interactive SLO through c=8 and inside the Server SLO through c=16 (the last live level), so its Server-SLO maximum is bounded by the crash, not by latency",
   "confidence": "R1 high (4 of 5 attempts in v1), R2 medium, R3 medium, R4 low (this is the gate that failed twice), R5 medium, R6 medium",
   "reading": "a failed R is reported as failed; pass is P1-P3 per sweep. No sentence of the form 'serves N users' is produced here; the numbers are p99 latencies at closed-loop concurrency levels under a stated SLO."},
 "outputs": ["levels.jsonl", "events.jsonl", "analysis.json", "versions.txt", "ctx.txt", "<arm>_<profile>_<container>/c<N>/ and warmup/ AIPerf artifacts (profile_export_aiperf.json kept; per-request exports are under the ignore rules)", "logs/ (not published; trimmed container logs)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p53_concurrency_v2.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
