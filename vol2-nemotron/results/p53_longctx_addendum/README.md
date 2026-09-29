# Vol.3 · long context, addendum: A2 re-measured at every depth after a warm-up phase; A1 at 16k again (run 2026-09-23, 07:06–07:51)

**Why this run exists.** In the main run (`../p53_longctx/`) every A2 container's first requests were slower than its later ones, so its A2 medians at 1k and 4k (128 and 295 tok/s) and its A2 decay shape were not measurements of the engine's steady state. One discarded request is not a warm-up for this image. This addendum keeps the main run's design (same images, profiles, `max_num_seqs` 32, `NIM_MAX_MODEL_LEN` per depth, same prompts and offsets for the measured requests, `max_tokens` 256, temperature 0, 2 s between requests) and adds a **warm-up phase** in each container: discarded requests at the measured depth until at least 60 s and 6 requests have passed and the last three generation rates agree within 5% and are all ≥ 220 tok/s on A2 (0 on A1), capped at 25 requests / 300 s. Warm-up rows are recorded (`warmup: true`) and never enter the medians. A1 at 16k is included so the A1 step seen in the main run is measured a second time. Pre-registration `prediction_p53_longctx_addendum.json`, frozen 2026-09-23T07:06:19+0800, first request 07:14 (`.sha256` beside it). All preconditions held at every depth.

Every row: **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 · `max_num_seqs` 32 · `max_tokens` 256; **A1** Nemotron Nano 9B v2 · bf16 · NIM 1.12.2 · `max_num_seqs` 32 · `max_tokens` 256.

## Result (medians over 5 measured requests per depth, after the warm-up)

| Depth (target → measured prompt tokens) | `NIM_MAX_MODEL_LEN` | A2 TTFT (ms) | A2 generation (tok/s) | ratio to 1k: TTFT · generation | main run's A2 median (warm-up contaminated) |
|---|---|---|---|---|---|
| 1k → 1,139 | 4,096 | **95** | **304.8** | 1.00 · 1.00 | 276 · 128 |
| 4k → 3,773 | 8,192 | **155** | **298.9** | 1.63 · 0.98 | 165 · 295 |
| 16k → 14,217 | 32,768 | **489** | **315.2** | 5.12 · 1.03 | 516 · 311.5 |
| 64k → 56,734 | 131,072 | **2,371** | **309.0** | 24.8 · 1.01 | 3,223 · 259 |
| A1 · 16k → 14,213 | 32,768 | 1,348 | 45.8 | (main run: 1,398 · 44.7) | |

Per-request values in order — A2 1k: TTFT 86, 104, 95, 106, 71 ms · 318, 307, 304, 286, 305 tok/s; 4k: 141, 173, 155, 161, 150 · 297, 296, 309, 299, 312; 16k: 489, 465, 491, 502, 471 · 310, 311, 316, 316, 315; 64k: 2,371, 2,512, 2,398, 2,353, 2,330 · 307, 313, 309, 310, 308 (two of five stopped before 256 tokens: 215 and 223); A1 16k: 1,368, 1,344, 1,335, 1,348, 1,352 · 46.0, 45.8, 46.5, 44.7, 43.5.

**A2's generation rate does not change with prompt depth from 1k to 57k tokens** (298.9–315.2 tok/s, within ±3% of the 1k value), once the engine is past its first-minute state. The main run's −17% at 64k was that state, not the depth: its 64k rows were 257–262 tok/s for four requests and 311 for the fifth. The external DGX Spark measurement of this model reports −8.5% from 0 to 100k; on this card, at 57k, the decay is inside the noise. This is the Mamba-2 claim — a state that does not grow with context — holding on the decode side for this hybrid, where the few attention layers' KV reads at 57k are not yet visible against the 3.6 GB the MoE reads per token.

**TTFT grows sub-linearly**: 24.8× for 50× the prompt tokens (prefill throughput 12k tokens/s at 1k, where fixed costs dominate, and 24k tokens/s at 57k). A1, whose decode steps lose CUDA graphs past 8k tokens (`../p53_longctx/README.md`), measures 45.8 tok/s at 16k here against 44.7 in the main run: the step is reproduced, warm-up or not.

## The warm-up phase itself (recorded, not analysed)

| Arm · depth | warm-up requests · seconds | generation rate, first → last warm-up request | stabilized | first-request TTFT → last |
|---|---|---|---|---|
| A2 · 1k | 16 · 63 s | **194** → 296 (194, 195, 194, 195, 198, 190, 209, 271, 291, 316, …) | yes | 1,760 → 93 ms |
| A2 · 4k | 18 · 65 s | 293 → 309 (no slow phase) | yes | 5,540 → 155 ms |
| A2 · 16k | 16 · 64 s | 316 → 315 (no slow phase) | yes | 6,331 → 516 ms |
| A2 · 64k | 11 · 64 s | 308 → 308 (no slow phase) | yes | 6,371 → 2,374 ms |
| A1 · 16k | 7 · 67 s | 46 → 45 | yes | 2,386 → 1,336 ms |

The slow phase appeared in this run only in the 1k container (seven requests at 190–209 tok/s, then 271, 291, 316); at 4k, 16k and 64k the first request already ran at the steady rate. In the main run it appeared at 1k and 4k; in the two harness tests of this addendum it lasted more than six and more than seven requests; in a clock diagnosis the same morning (`harness_test/a2_warm_diag_*`, nvidia-smi every 0.5 s) it lasted three requests while the SM clock was already 2.9 GHz at 130–230 W and 100% utilisation — an engine-side condition, not a clock ramp, and one the container log says nothing about (kernel autotuning and CUDA-graph capture finish before READY). It did not return after 20–30 s idle; back-to-back requests ran 5–8% faster than requests 2 s apart (340–355 W against 150–185 W). Its cause was not identified and this addendum does not claim one; it measures around it and records it. The first request at a new depth pays a separate one-time cost on both arms (TTFT 5.5–6.4 s at 4k–64k here), as in the main run.

**Pre-registered predictions.** **R1** A2 at 1k and 4k between 280 and 330 tok/s — held (304.8, 298.9). **R2** 64k within 15% of 4k — held (1.03). **R3** 64k TTFT between 15× and 40× the warm 1k TTFT — held (24.8×). **R4** a rising warm-up sequence at every A2 depth — **failed**: only the 1k container had a slow phase to rise out of. **R5** A1 16k at 42–48 tok/s — held (45.8). **R6** warm-up stabilizes within 25 requests at every A2 depth — held (11–18).

Containers (seconds to READY · memory at READY · KV tokens): A2 4,096: 485 s · 29,928 MiB · 3,067,904; 8,192: 421 · 29,868 · 3,127,824; 32,768: 432 · 29,549 · 3,173,760; 131,072: 495 · 29,870 · 3,127,824; A1 32,768: 337 · 23,370 · 53,412 (the same 1.6-sequence KV pool as the main run's 32k container). TTFT is client-side (`requests`), as in the main run.

## Files

`prediction_p53_longctx_addendum.json` + `.sha256` · `requests.jsonl` (93 rows: 68 warm-up marked `warmup: true`, 25 measured; digests and lengths, no text) · `events.jsonl` (depth starts, `warmup_end` with the rate sequence, depth ends) · `analysis.json` (main-run analyser on the measured rows, plus the warm-up summary and the ratio to the main run's medians) · `ctx.txt`. Harness `../../scripts/p53_longctx_addendum.py` (imports the main harness), analysis `../../scripts/p53_longctx_addendum_analyze.py`, runner `../../scripts/run_p53_longctx_addendum.sh`; SHA-256 in the pre-registration. `logs/` (startup and full container logs), `harness_test/` (three harness tests and the clock diagnosis) and the console output (`console.txt`) are not published.
