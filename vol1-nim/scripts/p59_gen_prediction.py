#!/usr/bin/env python3
"""Vol.1-A revisit, P59 · write prediction_p59_nim_value.json once, before the measured run.
usage: p59_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "vol1b", "scripts"))
from prediction_guard import check_prediction
sys.path.insert(0, HERE)
import p59_analyze as A

OUT = os.path.join(REPO, "vol1a-revisit", "results", "p59_nim_value")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()
HT = json.load(open(os.path.join(OUT, "harness_test_record.json"), encoding="utf-8"))
p = {
 "experiment": "Vol.1-A revisit, P59 · Llama 3.1 8B Instruct on one RTX 5090 · what the NIM container is worth once several people use it at the same time: total throughput, per-user speed and p99 time to first token at 1, 8, 16, 32, 64 and 128 concurrent requests, on a chat profile and a RAG profile, for two NIM configurations and three Ollama configurations. The headline is where the curves cross, never a single ratio.",
 "written_at": sys.argv[1],
 "written_before": "the measured run's first container. run_p59.sh refuses to start if this file or its .sha256 is missing or changed, or if levels.jsonl exists.",
 "why": "earlier single-stream measurements put the 4-bit Ollama model ahead of NIM's bf16 on this card, which is what a bandwidth-bound decoder does with fewer bytes per token. A serving engine's advantage, if any, is in concurrent use (continuous batching, paged KV cache), which had not been measured for the Ollama side. A single-user comparison cannot stand for a serving engine; this run adds the concurrent half.",
 "scope": "NIM on this card: the Llama profiles NIM 2.0.12 offers for an RTX 5090 are vLLM only (bf16, fp8; no TensorRT-LLM profile). Nothing here says what NIM does on data-centre GPUs. Speed and capacity only; answer quality is not compared.",
 "arms": {
   "O-Q4": "ollama/ollama:latest (Ollama 0.34.4), llama3.1:8b (manifest 46e0c10c039e, 4-bit GGUF 4,920,738,944 bytes), OLLAMA_CONTEXT_LENGTH 8192, OLLAMA_NUM_PARALLEL = the largest of 64, 32, 16, 8, 4, 2, 1 that loads 100% on GPU",
   "N-BF16": "NIM 2.0.12, profile 092ed421 (vllm-bf16), NIM_MAX_MODEL_LEN 8192, VLLM_USE_V2_MODEL_RUNNER=0 (as P54's arm N)",
   "O-FP16": "ollama/ollama:latest, llama3.1:8b-instruct-fp16 (manifest 4aacac419454, 16-bit GGUF 16,068,895,872 bytes), OLLAMA_CONTEXT_LENGTH 8192, OLLAMA_NUM_PARALLEL = the largest on the same ladder that loads 100% on GPU",
   "N-FP8": "NIM 2.0.12, profile c4789f7a (vllm-fp8, the profile NIM selects on this card when nothing is set; weights from the cached fp8-tool-calling snapshot, 9,081,280,648 bytes), NIM_MAX_MODEL_LEN 8192, VLLM_USE_V2_MODEL_RUNNER=0",
   "O-Q4-def": "as O-Q4 with OLLAMA_NUM_PARALLEL not set (the value Ollama chooses is read from its log)",
   "note": "FP16 and bf16 are both 16-bit formats with different ranges: 'comparable precision', not 'the same precision'"},
 "order": "O-Q4 -> N-BF16 -> O-FP16 -> N-FP8 -> O-Q4-def; chat then RAG in the same container; then a fresh container per arm for the two highest levels of both profiles; after each Ollama arm with a tuned NUM_PARALLEL, the same ladder at context 4,096 (reported, not measured)",
 "isolation": "one engine on the card at a time; before each container: no other compute process listed on the GPU, ports 8000 / 11434 held only by that arm, no Windows-native Ollama process (the runner stops it before and starts it after the run); every endpoint on 127.0.0.1",
 "load": "AIPerf 0.11.0 closed loop, profiles C (200+-50 / 200+-50) and R (3,500+-300 / 500+-50) as p53_concurrency (ignore_eos requested; Ollama may not honour it), the output cap sent as max_tokens on every arm (--use-legacy-max-tokens: Ollama 0.34.4 ignores max_completion_tokens), temperature 0, levels 1, 8, 16, 32, 64, 128, 60 s each, token counts from the Llama 3.1 tokenizer on the client for every arm (no server token counts)",
 "harness_fixes": "P58 section 3-2: (1) a prefix-cache detector before calibration - one ~3,500-token prompt twice as a positive control (its second TTFT should drop where an engine reuses a cached prefix), then two prompts of the calibration form, which differ from their first token on, whose second TTFT must not drop below 0.70 of the first, else the container stops (null); (2) calibration prompts (20 measured, lengths at the profile means) each start with their own nonce, a discarded prompt precedes the detector, and the discarded warm-up level has its own seed (P54's RAG profile hit the cache because warm-up and c=1 shared one). Prefix caching itself is left as each engine ships it.",
 "analysis_rules": {"program": "vol1a-revisit/scripts/p59_analyze.py (12 self-test cases; mutations of each gate, the truncation and early-stop rules, the detector and calibration rules and the crossing rule each fail one case; run on the harness test's real rows before this file was written)",
   "gates": "per arm: residency (Ollama: `ollama ps` 100% GPU; NIM: READY with CUDA graphs captured) and health (decode rate at c=1, profile C, = 1000 / AIPerf p50 inter-token latency, x bytes per token / 1,792 GB/s >= 0.40; bytes: " + json.dumps(A.BYTES) + "). An arm failing either: every comparison involving it is null.",
   "levels": "usable only if rc 0, a summary, 0 request errors, engine alive, the container's isolation and detector passed and (main) its profile's calibration passed; any request whose server-reported prompt tokens < 98% of the client count -> level null (truncation); no server count at all -> 'truncation unverified' (kept, flagged; the chat template makes the server count exceed the client count, so the check is one-sided); median completion tokens < 90% of the target -> 'early stop': that level's total throughput and per-user speed are not compared, TTFT and TPOT are",
   "crossings": "pairs N-BF16 vs O-Q4, N-BF16 vs O-Q4-def, N-BF16 vs O-FP16, N-FP8 vs N-BF16; per profile and metric (total tok/s, per-user tok/s); a change of sign between two consecutive usable levels is reported as 'between X and Y', no change as 'ahead throughout', never interpolated",
   "slo": "MLPerf Inference v5.1 Llama 3.1-8B server (p99 TTFT <= 2,000 ms and p99 TPOT <= 100 ms) and interactive (500 ms, 30 ms), marked per cell"},
 "predictions": {
   "basis": "R1-R5 are the predictions the experiment was set up with, restated without multipliers; R6-R10 are this lab's own, all written before any P59 GPU measurement except the harness test, which is disclosed: " + HT.get("summary", ""),
   "R1": "single stream (c=1, profile C): O-Q4 ahead of N-BF16 on per-user speed; O-Q4 decode >= 200 tok/s, N-BF16 <= 110 tok/s",
   "R2": "the O-Q4 vs N-BF16 total-throughput crossing (profile C) lies at or below 8 concurrent requests",
   "R3": "O-Q4's total throughput (profile C) stops growing or falls somewhere around 32 concurrent requests",
   "R4": "at c=1 (profile C) O-FP16 and N-BF16 per-user speeds within 20% of each other",
   "R5": "N-FP8 single-stream decode rate 130-190 tok/s (N-BF16 ~98 in P54)",
   "R6": "O-Q4's largest NUM_PARALLEL loading 100% on GPU is 16 at context 8,192 and 32 at 4,096",
   "R7": "O-Q4-def: Ollama chooses NUM_PARALLEL 4 on this card",
   "R8": "O-FP16's largest NUM_PARALLEL loading 100% on GPU at context 8,192 is 8 or 4",
   "R9": "every arm passes both gates (O-FP16 the most at risk of partial GPU residency)",
   "R10": "N-BF16 and N-FP8 keep the server SLO on profile C through at least 64 concurrent requests; no Ollama arm does beyond its NUM_PARALLEL",
   "confidence": "R1 high, R2 medium, R3 low, R4 medium, R5 medium, R6 low, R7 low, R8 low, R9 medium, R10 medium",
   "reading": "a failed R is reported as failed. If the curves run opposite to the external reports (the Ollama total throughput flattening after about 32 requests), the instrument is suspected first, then reported as measured; nothing is re-run until it agrees"},
 "harness_sha256": {k: h(k) for k in ("vol1a-revisit/scripts/p59_nim_value.py", "vol1a-revisit/scripts/p59_analyze.py", "vol1a-revisit/scripts/run_p59.sh",
                                      "vol2/scripts/p53_concurrency.py", "vol2/scripts/p54_engine.py", "vol2/scripts/p50_footprint.py", "vol1b/scripts/prediction_guard.py")},
}
check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p59_nim_value.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
