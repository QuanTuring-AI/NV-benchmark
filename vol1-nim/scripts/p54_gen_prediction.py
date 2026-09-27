#!/usr/bin/env python3
"""Vol.1-A revisit (P54) · write prediction_p54_engine.json once, before the measured run.
usage: p54_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p54_engine")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()
HT = json.load(open(os.path.join(OUT, "harness_test_record.json"), encoding="utf-8"))   # what the harness test showed (disclosed)

p = {
 "experiment": "Vol.1-A revisit · one engine against itself: Llama 3.1 8B Instruct bf16 on one RTX 5090, served by the NIM container (arm N, NIM 2.0.12, built on vLLM 0.27.1) and by the upstream vLLM 0.27.1 container (arm V) from the same weight files. Items A (single stream, answer time, concurrency within SLO) and B (settings needed to reach a serving configuration)",
 "written_at": sys.argv[1],
 "written_before": "the measured run's first container start. run_p54_engine.sh refuses to start if this file or its .sha256 is missing or changed, and each stage refuses to run twice.",
 "runs": "one run, stages in order: stack (zero GPU) -> attempts -> single -> conc; one container on the card at any time",
 "why": "Vol.1-A's 7.3x compared two engines on two precisions with one arm outside GPU memory. A healthy engine's single-stream decode is bandwidth-bound (rate <= bandwidth / bytes read per token), so two healthy engines on the same card, model, weights and precision cannot differ by several times. NIM 2.0.12 contains vLLM 0.27.1; the question is what NIM's pre-selected configuration is worth against the same engine run by hand.",
 "arms": {
   "N": {"image": "nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12", "digest": "sha256:d2c94c1d654c3e80b8bc08cc83298d2ba4e219dff41d1092555795edb93c6545",
         "engine": "NIM 2.0.12 (vLLM 0.27.1, build commit 6e448d0ea9bf3d88d898b65449ca6dc2aec170ac, image built FROM vllm/vllm-openai:v0.27.1-ubuntu2404)",
         "profile": "092ed4213624e774d24cdaf84e3b6222839bab2008a21d3c214ab46626366f90", "precision": "bf16",
         "measured_env": {"NIM_MODEL_PROFILE": "(the profile above)", "NIM_MAX_MODEL_LEN": "8192", "VLLM_USE_V2_MODEL_RUNNER": "0"},
         "why_this_configuration": "Vol.1-B's cell-4 configuration, the Vol.1 baseline of record: NIM_MAX_MODEL_LEN 8192 so bf16 fits beside its KV cache on 32 GB; VLLM_USE_V2_MODEL_RUNNER=0 because NIM 2.0.12 did not start without it on this card"},
   "V": {"image": "vllm/vllm-openai:v0.27.1", "digest": "sha256:0a51ea5b4ae2dc5d81890e5173f54203d2a3ae0cfffe51b8fd2afd4391bfd967",
         "engine": "vLLM 0.27.1 (build commit 6e448d0ea9bf3d88d898b65449ca6dc2aec170ac, the same commit and build pipeline as N's)",
         "precision": "bf16 (the checkpoint's dtype; no quantization argument)",
         "measured_configuration": "the vLLM argument list NIM itself resolves for arm N's measured configuration (`nim-serve --dry-run`, run by the harness before any measured start and saved), with these edits only: the model path (NIM's workspace -> the snapshot it links to); '--port 8001' and '--host 127.0.0.1' dropped (NIM's backend sits behind its nginx; V listens on 8000 on all interfaces, vLLM's defaults); the two '--middleware nim_llm.*' entries dropped (NIM's own ASGI middlewares, a redirect and a request-id stamp: NIM server-layer modules that do not exist in the upstream image). Plus the one engine variable N carries (VLLM_USE_V2_MODEL_RUNNER=0).",
         "expected_argument_list_from_the_harness_test_dry_run": HT.get("v_args"),
         "expected_nim_argument_list_from_the_harness_test_dry_run": HT.get("n_backend_args")}},
 "weights": {"source": "the same snapshot in the NIM cache for both arms, mounted at the same path in both containers (N read-write as NIM requires; V read-only)",
             "snapshot": "ngc/hub/models--nim--meta--llama-3.1-8b-instruct/snapshots/8c22764a7e3675c50d4c7c9a4edb474456022b16",
             "identity": "file list, sizes and SHA-256 of every file recorded by the stack stage (stack.json); safetensors total 16,060,522,496 bytes (header sum)"},
 "alignment": {
   "set_equal_by_construction": {
     "max_model_len": "8192 (N: NIM_MAX_MODEL_LEN; V: the same value in NIM's argument list)",
     "max_num_seqs": "not set on either arm (neither in NIM's argument list nor in its resolved configuration) -> vLLM's default for a card under 70 GiB, 256 (vllm/engine/arg_utils.py); checked per container from the startup log's decode CUDA-graph count (35 sizes = capture up to 256) and in conc from the running gauge",
     "gpu_memory_utilization": "NIM's resolved value in its argument list (NIM may clamp it for memory already in use at the dry-run); V receives that value; N resolves it again at each start -> compared per block from each engine's own cache_config_info at READY",
     "kv_cache_dtype": "not set on either arm unless NIM's argument list sets it (then both)",
     "all other engine arguments": "NIM's argument list, verbatim, on both",
     "sampling": "temperature 0, top_p 0.9 (single); temperature 0 (conc, AIPerf --extra-inputs as p53_concurrency); both arms read the checkpoint's generation_config.json",
     "questions and order": "the 50 questions of vol1b/results/p20_coresidence/sample.json in its run order, blocks N, V, N, V (halves 0-24, 25-49)",
     "max_tokens": "4096 (single) · AIPerf profiles C and R as p53_concurrency (OSL 200 / 500, ignore_eos)",
     "streaming and usage": "stream with usage on every request, both arms, one client",
     "warm-up": "single: one discarded 'Hello' and three discarded questions per block; conc: p53_concurrency_v2's discarded 120 s level, then calibration"},
   "not_aligned_and_why": [
     "NIM's two ASGI middlewares (NIMRedirectMiddleware, RequestIdMiddleware) run in N's API server and not in V's: they cannot be loaded outside NIM. Part of NIM; request routing and a request-id header, not the engine.",
     "request path: N answers through NIM's nginx proxy in front of vLLM (NIM_SERVER_PORT 8000 -> backend 8001); V's vLLM listens on 8000 directly. Part of what NIM is; it adds at most a proxy hop to every request.",
     "NIM loads four vLLM plugins into every engine process (vllm.general_plugins: cpu_runtime, engine_oom_recover, mamba_prefix_reuse, memory_reporter) and one pre-import patch (hw_video_decoding), and appends --media-io-kwargs (video decoder) at launch; V runs vLLM without them. Part of NIM; none acts on a dense text model's decode path by its description (memory reporting, OOM recovery, Mamba prefix reuse, CPU-only runtime, video).",
     "OS base: N Ubuntu 24.04 (the -ubuntu2404 build of v0.27.1), V Ubuntu 22.04 (the default tag); Python 3.12.3 vs 3.12.13. vLLM, torch 2.13.0+cu130, CUDA 13.0.2, flashinfer 0.6.16.post3, triton 3.7.1, transformers 5.15.0, cuBLAS 13.1.1.3, cuDNN 9.20.0.48, xgrammar 0.2.3 identical; NCCL 2.29.7 (N) vs 2.30.7 (V), unused on one GPU (stack.json).",
     "served model name: whatever NIM's argument list sets is given to V too; the /v1/models id is read at READY per block, so the client never assumes it",
     "V never reports usage statistics (VLLM_NO_USAGE_STATS=1, DO_NOT_TRACK=1; the NIM image sets VLLM_NO_USAGE_STATS=1 in its own env); V's weights mount is read-only",
     "cache parity: N keeps compiled graphs, autotune results and kernels in the mounted NIM cache (HOME=/opt/nim, TORCHINDUCTOR_CACHE_DIR under it); V gets a persistent host directory at /root/.cache and the same inductor variable. Both are warm in the measured run (the harness test and attempts stage run first); this touches start time, not the engine configuration",
     "N receives the NGC credentials file (--env-file); V does not need it. No engine effect.",
     "KV cache size is an outcome of each engine's own memory profiling at start, not a setting: in the harness test N held 97,328 KV tokens (6,083 blocks) and V 107,728 (6,733) at the same gpu_memory_utilization 0.92. V's log attributes its larger share to a smaller non-torch and activation footprint (15.30 + 0.84 GiB against 16.12 + 1.29 GiB in its own cold-cache start, which also gave 97,328); N's log does not print these lines at NIM's log level. Not adjusted in either direction; recorded per block from cache_config_info. It can matter only at levels where KV binds (profile R at the top of the ladder), not for single-stream rates."]},
 "item_B": {
   "ladders": {"N": ["nothing set (profile pinned only if NIM's own dry-run with nothing set would select another profile)", "+ NIM_MAX_MODEL_LEN=8192", "+ VLLM_USE_V2_MODEL_RUNNER=0"],
               "V": ["the model path only", "+ --max-model-len 8192", "+ VLLM_USE_V2_MODEL_RUNNER=0"]},
   "rule": "each step only after the previous start failed; a start counts as reaching a serving configuration when it is READY and a probe request answers HTTP 200 with finish_reason stop. Every attempt is one row of attempts.jsonl. Reported: attempts and settings per arm to the first serving start, and the settings each arm carries in the measured configuration (a NIM variable = 1, a vLLM option = 1; the model path, V's usage-statistics variables and V's cache-parity mount are listed, not counted). Seconds are listed per attempt and never summed into a conclusion (a second walk of a known ladder is always faster than a first).",
   "program": "vol2/scripts/p54_attempts_analyze.py"},
 "analysis_rules": {
   "single": "vol2/scripts/p54_single_analyze.py: p53_answer_analyze's rules (and p50_speed_analyze's) run unchanged with N in place of A1 and V in place of A2 -- P1 no errors, HTTP 200, usage on every row; P2 served model = the arm's; P3 50 rows per arm, blocks alternate; arm-health gate BEFORE any ratio: median generation rate x 16,060,522,496 bytes / 1,792 GB/s, an arm under 10% -> validity false and no ratio. Added: P4 the one container up is the block's own; P5 every row carries model, precision, engine, max_model_len, max_num_seqs, max_tokens. Alignment at READY (cache_config_info per block) is reported and named where it differs, not gated. Ratios V over N: ratio of means over questions, 95% bootstrap CI over questions, median per-question ratio",
   "conc": "vol2/scripts/p54_conc_analyze.py --seqs 256: p55_concurrency_a2_analyze's rules run unchanged on both arms (P1 levels clean below any engine crash; P2 AIPerf c=1 against the harness's own calibration, TTFT within max(20 ms, 20%), ITL within 20%, calibration after the warm-up level; P3 no sequence-cap override on either arm and the running gauge never above 256; SLOs MLPerf Llama 3.1-8B server p99 TTFT 2,000 ms and TPOT 100 ms, interactive 500 / 30 ms; per-level pools and binding reading); side-by-side table per profile",
   "tested_on": "each analyser's self-test (single 10 cases, conc 9, attempts 8; mutations of every guarded rule each fail one case) and a run on the harness test's real rows before this file was written (harness_test_record.json)"},
 "predictions": {
   "basis": "written before the harness test except where marked. Vol.1-B: this card, NIM 2.0.12, this profile, NIM_MAX_MODEL_LEN 8192, generated 96.8 tok/s single-stream = 1,555 GB/s at 16.06 GB per token = 87% of 1,792 GB/s; KV 97,328 tokens at gpu_memory_utilization 0.92. Same vLLM commit on both arms; NIM's argument list given verbatim to V. Harness test (disclosed): " + HT.get("summary", "(none)"),
   "R1": "both arms pass the health gate with 70-95% of peak each",
   "R2": "single-stream generation rate, V over N ratio of means, within 0.95-1.05",
   "R3": "N's median TTFT is higher than V's by 0-15 ms (the proxy hop), not lower by more than 5 ms",
   "R4": "answer time (total latency) V over N within 0.93-1.07, and completion tokens identical in distribution: at temperature 0 with the same weights and kernels, at least 45 of 50 questions produce byte-identical responses across the two arms (response_sha256)",
   "R5": "concurrency: each arm's maximum concurrency within the Server SLO is the same ladder level on each profile (C and R), and maximum throughput within 10% of each other per profile",
   "R6": "item B: both arms reach a serving start on the same ladder step, with the same settings (the context length and the model-runner switch); V's measured configuration carries 2-8 more counted settings than N's (NIM's argument list, made explicit)",
   "confidence": "R1 high, R2 medium, R3 low, R4 medium, R5 medium, R6 low",
   "reading": "a failed R is reported as failed. No arm is re-run or retuned toward a result. If an arm fails the health gate the single-stream conclusions are null and no ratio is printed"},
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p54_engine.py", "vol2/scripts/p54_single_analyze.py", "vol2/scripts/p54_conc_analyze.py", "vol2/scripts/p54_attempts_analyze.py",
                                      "vol2/scripts/run_p54_engine.sh", "vol2/scripts/p50_footprint.py", "vol2/scripts/p50_speed.py", "vol2/scripts/p53_answer.py",
                                      "vol2/scripts/p53_concurrency.py", "vol2/scripts/p53_concurrency_v2.py", "vol2/scripts/p50_speed_analyze.py",
                                      "vol2/scripts/p53_answer_analyze.py", "vol2/scripts/p55_concurrency_a2_analyze.py", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {k: h(k) for k in ("benchmark/questions.json", "vol1b/results/p20_coresidence/sample.json")},
}
check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p54_engine.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
