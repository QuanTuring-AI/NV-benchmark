# Vol.3 · long context: TTFT, generation rate and memory at prompt depths of ~1k, 4k, 16k and 64k tokens (run 2026-09-23, 03:18–04:11)

**What was measured.** Both arms, four prompt depths, each depth in its own container sized for it: `NIM_MAX_MODEL_LEN` 4096 / 8192 / 32768 / 131072 (the smallest of those holding depth + 512), both arms at `max_num_seqs` 32, otherwise the footprint configuration. Prompts are questions from `benchmark/questions.json` (public, Vol.1's set) concatenated to 3.6 × depth characters, five per depth from different offsets, ending in a one-line summary instruction — synthetic by repetition, so the attention pattern of a real RAG prompt is not reproduced. Per request: `max_tokens 256`, temperature 0, top_p 0.9, streaming with usage. One discarded request after READY, then the five measured. The engine's `prompt_tokens` is the depth actually measured. Pre-registration `prediction_p53_longctx.json`, frozen 2026-09-23T00:30:40+0800 (`.sha256` beside it). All twelve preconditions held (every request HTTP 200 with usage; measured depth within 25% of target; one container up per request). No response text is stored.

Every row: **A1** Nemotron Nano 9B v2 · bf16 · NIM 1.12.2 (vLLM V0 0.10.0) · `max_num_seqs` 32 · `max_tokens` 256; **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 (vLLM 0.27.1) · `max_num_seqs` 32 · `max_tokens` 256. Not a single-variable comparison.

**One caveat governs the A2 rows below and is why `../p53_longctx_addendum/` exists**: A2's engine is not at steady state in its first minute after READY. In every A2 container the first one or two requests were slower than the rest — at 1k depth all five measured requests were still speeding up (122, 119, 128, 171, 280 tok/s in order), at 4k the first two (140, 190, then 295, 315, 315). One discarded request was not a warm-up for A2. The A2 medians at 1k and 4k therefore describe a warming engine; 16k and 64k are steady from the second request. A1 showed no drift at any depth. The addendum repeats A2 with a 90 s warm-up phase.

## Result (medians over 5 requests per depth)

| Depth (target → measured prompt tokens) | `NIM_MAX_MODEL_LEN` | A1 TTFT (ms) | A1 generation (tok/s) | A2 TTFT (ms) | A2 generation (tok/s) |
|---|---|---|---|---|---|
| 1k → 1,135 / 1,139 | 4,096 | 157 | **71.7** | 276 *(warm-up)* | 128 *(warm-up)* |
| 4k → 3,769 / 3,773 | 8,192 | 408 | **71.6** | 165 *(first two of five warming)* | 295 *(same)* |
| 16k → 14,213 / 14,217 | 32,768 | 1,398 | **44.7** | 516 | **311.5** |
| 64k → 56,730 / 56,734 | 131,072 | 6,201 | **44.4** | 3,223 | **259.1** |

Per-request values, in request order:

| Arm · depth | TTFT (ms) | generation (tok/s) |
|---|---|---|
| A1 · 1k | 143, 164, 166, 157, 149 | 72.0, 71.7, 72.2, 71.4, 71.4 |
| A1 · 4k | 416, 385, 423, 408, 372 | 72.2, 71.6, 71.9, 70.8, 71.4 |
| A1 · 16k | 1,474, 1,399, 1,379, 1,398, 1,390 | 44.6, 45.7, 46.7, 44.7, 44.6 |
| A1 · 64k | **20,413**, 6,201, 6,224, 6,173, 6,152 | 45.1, 42.7, 43.8, 45.4, 44.4 |
| A2 · 1k | 2,004, 1,985, 276, 228, 89 | 122, 119, 128, 171, 280 |
| A2 · 4k | 440, 419, 154, 165, 142 | 140, 190, 295, 315, 315 |
| A2 · 16k | **6,049**, 527, 500, 488, 516 | 308, 312, 314, 315, 310 |
| A2 · 64k | **8,702**, 3,203, 3,223, 3,246, 2,809 | 259, 257, 262, 256, 311 |

The first request at a new depth pays a one-time cost on both arms (A1 64k: 20.4 s against 6.2 s after; A2 16k: 6.0 s against 0.5 s; A2 64k: 8.7 s against 3.2 s) — a cost the discarded request, sent at 1k depth, did not absorb. Medians exclude it by construction (one value in five); the addendum's warm-up runs at the measured depth.

Containers (seconds to READY · memory at READY · KV cache tokens from the engine's own record):

| Arm · `NIM_MAX_MODEL_LEN` | READY | memory | KV tokens | engine notes quoted from the startup log |
|---|---|---|---|---|
| A1 · 4,096 | 278 s | 29,489 MiB | 435,036 | `Maximum concurrency for 4096 tokens per request: 106.21x` |
| A1 · 8,192 | 204 | 28,705 | 382,976 | `46.75x` |
| A1 · 32,768 | 235 | 23,564 | **53,412** | `Maximum concurrency for 32768 tokens per request: 1.63x` — no chunked prefill; the profiling pass for a 32k prefill leaves little for KV |
| A1 · 131,072 | 257 | 30,171 | 456,131 | `Chunked prefill is enabled by default for models with max_model_len > 32K` · `max_num_batched_tokens=2048` · `3.48x` |
| A2 · 4,096 | 462 | 29,622 | 3,112,960 | `fp8_e4m3` KV, 760 blocks × 4,096 |
| A2 · 8,192 | 484 | 30,109 | 3,173,760 | 760 × 4,176 |
| A2 · 32,768 | 441 | 29,969 | 3,173,760 | 760 × 4,176 |
| A2 · 131,072 | 379 | 29,560 | 3,127,824 | 749 × 4,176 |

**Memory at READY does not measure context cost on either arm**: both engines take a fixed share of the card (`gpu_memory_utilization` 0.90 / 0.92) whatever the model length, so the level at READY moves by less than 1 GB across a 32× change in `NIM_MAX_MODEL_LEN` on A2 and only the KV-token count shows where the memory went. On A1 the 32,768 container is the exception in the other direction: without chunked prefill the engine reserves the activations of a full 32k prefill and keeps 53k KV tokens (1.6 sequences of 32k), while at 131,072 NIM 1.12.2 turns chunked prefill on by itself and the KV pool is back to 456k tokens. That is a NIM/vLLM-version behaviour recorded here because it decides whether a 32k-context A1 deployment can hold more than one request.

## Reading

**A1's generation rate steps from 72 to 45 tok/s between 4k and 16k and then stays flat to 57k tokens.** It is a step, not a slope: 71.7 → 71.6 → 44.7 → 44.4. The engine's config dump in every A1 container reads `"max_seq_len_to_capture": 8192`: on this vLLM V0 build, decode steps for sequences longer than 8,192 tokens run without CUDA graphs. At 72 tok/s a decode step takes about 14 ms; at 44.5 tok/s about 22 ms. The flat 44.4 at four times the depth says the added 8 ms is per step, not per context token — the signature of losing graph capture (many small kernel launches per step), not of a state that grows with context. The Mamba state itself does not grow with context; what A1 loses past 8k on this image is graph capture. *(Added after P55.)* This attribution is now measured, not inferred: `../p55_a1_capture/` switched CUDA graphs off at ~3.8k tokens (the image's only graph setting, `NIM_DISABLE_CUDA_GRAPH`) and the rate fell from 76.4 to 52.3 tok/s, while at ~14k, where decode already runs without graphs, switching them off changed 55.7 to 51.7. Raising the capture limit instead could not be tested: NIM 1.12.2 does not pass the setting to its engine.

**A2's rate in this run reads 311.5 at 16k and 259.1 at 57k, and the addendum shows the 57k figure was the first-minute state too**: measured after a warm-up phase, A2 runs at 304.8 / 298.9 / 315.2 / 309.0 tok/s at 1k / 4k / 16k / 57k — flat within ±3% across the whole range — with TTFT 95 / 155 / 489 / 2,371 ms (`../p53_longctx_addendum/README.md`). Those are the A2 numbers of record for this block; the A2 rows of this run are kept as what was measured and as the record of the transient. The external DGX Spark measurement of this model reports −8.5% from 0 to 100k; at 57k on this card the decay is inside the noise.

**TTFT grows about linearly with depth on both arms**: A1 157 → 6,201 ms (39.5× for 50× the tokens), A2 (warm rows) 89 → 3,223 ms. Prefill throughput at 57k tokens: A1 about 9,100 tokens/s, A2 about 17,600 tokens/s.

**Neither arm hit a context ceiling**: both start and serve at `NIM_MAX_MODEL_LEN` 131,072 with `max_num_seqs` 32 on this 32 GB card. The deepest prompt tried is 57k tokens; 128k prompts were not sent (the model length leaves room for them, the character budget did not — a default of this run, not a limit found).

**Pre-registered predictions.** **R1** (generation at 64k within 15% of 1k on both arms): **failed on A1** (0.62×, the CUDA-graph step); on A2 the 1k reference is a warm-up value, so the test is void here — against 4k's 295 the 64k rate is 0.88, inside 15%; the addendum re-tests. **R2** (64k TTFT between 30× and 120× the 1k TTFT): held on A1 (39.5×); **failed on A2** (11.7×, and against a warm 1k TTFT of 89 ms it would be 36×). **R3** (both arms start at 131,072): held. **R4** (memory at READY at 131,072 within 6 GB / 10 GB of the 4,096 level): held, and uninformative for the reason given above.

TTFT is client-side (`requests`, `iter_lines`), 10–20 ms above the first-chunk time AIPerf measures on this host (`../p53_concurrency/README.md`); at these depths that is within the run-to-run spread.

## Files

`prediction_p53_longctx.json` + `.sha256` · `requests.jsonl` (40 rows; digests and lengths, no text) · `events.jsonl` (per-depth start records with env, GPU, cache and the discarded request) · `analysis.json` · `ctx.txt`. Harness `../../scripts/p53_longctx.py`, analysis `../../scripts/p53_longctx_analyze.py`, runner `../../scripts/run_p53_longctx.sh`; SHA-256 in the pre-registration. `logs/` (startup logs of the eight containers, quoted above), `harness_test/` and the console output (`console.txt`) are not published.
