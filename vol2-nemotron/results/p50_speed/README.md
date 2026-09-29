# Vol.3 · speed: Nemotron Nano 9B v2 vs Nemotron 3 Nano on one RTX 5090 (run 2026-09-21)

**What is compared.** Two deployment options, each in its own NIM image and at the only precision its image can run on this card: **A1** Nemotron Nano 9B v2, bf16, NIM 1.12.2; **A2** Nemotron 3 Nano (30B total, 3.5B active per token), NVFP4, NIM 2.0.12. Architecture, precision and NIM version all differ and are part of what each option is. No common NIM version exists for the two models (`../p50_availability/`), so **this is not a single-variable comparison** and the numbers below are not written as one. Pre-registration `prediction_p50_speed.json`, frozen before the run (`.sha256` beside it).

**Design.** The two images cannot share the card (17.8 + 19.3 GB of weights), so the arms alternate as containers: four blocks A1, A2, A1, A2 — the first pair on positions 0–24 and the second on 25–49 of the Vol.2 co-residence sample (50 questions from the Vol.1 set, fixed order, `../../../vol3-judges/results/p20_coresidence/sample.json`). Each block starts its container in the footprint run's default configuration (`NIM_MAX_MODEL_LEN 4096`; A1 also `NIM_MAX_NUM_SEQS 32`), discards one 16-token request, then sends one request per question with 2 s between. Payload is Vol.1's plus temperature 0.0, top_p 0.9, `max_tokens 500`, streaming with usage; **no system prompt, so both models reason as they do by default**. Measured requests 21:09–21:38 (+0800); GPU idle at 464 MiB before launch; one container up at every request (checked per row).

**All preconditions held**: 0 errors in 100 requests, engine usage present on every row, every row's served model is its arm's, 50 rows per arm, one per question, blocks alternating.

## Arm health before any ratio (pre-registered gate)

| Arm | Generation rate, median (tok/s) | Bytes read per token | Effective bandwidth | Share of the card's 1,792 GB/s | Gate (≥ 10%) |
|---|---|---|---|---|---|
| A1 · dense bf16 | 72.9 | 17,776,454,656 (all weights) | 1,297 GB/s | **72%** | pass |
| A2 · MoE NVFP4 | 305.1 | 3,590,938,272 (non-expert 2.56 GB + shared expert 0.26 GB + 6 of 128 routed experts) | 1,096 GB/s | **61%** | pass |

Generation rate = `completion_tokens / (total − TTFT)`. Bytes per token come from the safetensors headers in the NIM cache (`../../scripts/p50_bytes_per_token.py`); with five routed experts per token (the NGC page's figure) A2 reads 3,461,849,392 bytes and its share is 59%. Both arms generate at a bandwidth-bound rate on this card; neither is the kind of arm that the March 2026 Vol.1 comparison turned out to contain (`../../../vol3-judges/BASELINE.md` §12).

## Result

| | A1 · Nemotron Nano 9B v2, bf16 | A2 · Nemotron 3 Nano, NVFP4 |
|---|---|---|
| Generation rate, avg / p50 / min–max (tok/s) | 73.0 / 72.9 / 69.7–75.7 | 302.2 / 305.1 / 249.4–324.0 |
| tps, engine tokens over total latency, avg / p50 | 72.3 / 72.4 | 290.1 / 292.8 |
| tps, Vol.1 word formula, avg / p50 | 71.2 / 71.6 | 279.6 / 282.4 |
| TTFT, avg / p50 / p95 (ms) | 61.8 / 52.1 / 80.6 | 43.4 / 40.8 / 61.5 |
| Total latency, avg / p50 (ms) | 6,513 / 6,855 | 1,415 / 1,659 |
| Completion tokens, avg / p50 | 471 / 500 | 416 / 500 |
| `finish_reason` | length 42 · stop 8 | length 37 · stop 13 |
| Prompt tokens, avg | 36.5 | 40.5 |
| By block, generation p50 | 73.0 (block 0) · 72.9 (block 2) | 311.4 (block 1) · 298.7 (block 3) |
| Container: seconds to READY · memory at READY | 257 / 299 s · 29,368 / 29,086 MiB | 389 / 368 s · 31,540 / 31,823 MiB |

**A2 / A1, ratio of means over the 50 questions, 95% bootstrap CI over questions, median per-question ratio:**

| Quantity | Ratio | CI | Median |
|---|---|---|---|
| Generation rate | **4.14** | [4.08, 4.19] | 4.17 |
| tps (engine tokens / total) | 4.01 | [3.95, 4.07] | 4.05 |
| TTFT | 0.70 | [0.58, 0.83] | 0.76 |

Pre-registered predictions: **R1** A2 generation rate at least 3.5× A1's — held (4.14; the threshold was raised from 2.5 to 3.5 after the harness test, as the pre-registration states). **R2** both arms pass the health gate, A1 60–100%, A2 25–80% — held (72%, 61%). **R3** A1 median generation rate 70–100 tok/s — held (72.9). **R4** most completions on both arms end at `max_tokens` — held (42/50 and 37/50).

## Reading

On this card, per generated token, A2 moves about one fifth of the bytes A1 moves (3.59 vs 17.78 GB) and runs about four times faster; the difference between "one fifth" and "four times" is A2's lower bandwidth share (61% vs 72%) and its 2.5 GB of non-expert weights read every token. Per-block figures differ by less than 1% for A1 and by 4% for A2 (block 1 faster than block 3), so session drift does not enter the ratio. Both models answered at length: 79 of 100 completions ran to the 500-token cap because reasoning is on by default, which is what a Vol.1-style request receives; the A1/A2 texts never coincide (0 of 50 questions), as expected across different models.

**A2's first requests after READY are slower than its steady state** (found in the long-context run, `../p53_longctx/README.md`): here the first measured question of each A2 block ran at 271 and 299 tok/s against block medians of 311 and 299, and the second question was already at the steady rate, because one 500-token answer is longer than the transient. The effect on the median is nil and on the ratio of means below 1%; it is noted so that the per-question ratio of position 0 and 25 is not read as a property of those questions.

## Engine environment, from the containers' own startup logs

Each value is quoted from the startup log of the container that served the block (`logs/`, not published) or, where stated, from another record of the same image, profile and settings. "Not disclosed" means the log contains no line stating it; nothing is inferred from documentation.

| Field | A1 (NIM 1.12.2, vLLM V0 engine v0.10.0) | A2 (NIM 2.0.12, vLLM v0.27.1) |
|---|---|---|
| MoE backend selected | not applicable (dense model) | **not stated explicitly.** The log records FlashInfer JIT autotuning of `trtllm::fused_moe::gemm1` / `gemm2` kernels (88 lines, 106 configs saved to the FlashInfer autotune cache) and contains no line naming MARLIN or CUTLASS. The kernels being tuned are the FlashInfer TRT-LLM fused-MoE path; whether the engine then ran only that path is not something this log states. |
| `mamba_ssm_cache_dtype` | `"mamba_ssm_cache_dtype": "float32"` (engine config dump) | **not disclosed** (the only Mamba line is `Using default Mamba SSU config. Performance might be sub-optimal! Config file not found …`) |
| CUDA graph mode | `Capturing cudagraphs for decoding` (V0 engine; the mode name PIECEWISE / FULL is not printed by this version) | capture passes logged as `Capturing CUDA graphs (decode, FULL)` and `Capturing CUDA graphs (mixed prefill-decode, PIECEWISE)` — i.e. FULL_AND_PIECEWISE |
| `max_num_seqs` in effect | 32 (`"max_num_seqs": 32` in the engine config dump; `NIM_MAX_NUM_SEQS=32`) | 256 — not printed in this run's log; the same image, profile and settings refused at low budgets with `max_num_seqs (256) exceeds available Mamba cache blocks` (`../p50_footprint/`) |
| `max_tokens` sent | 500 | 500 |
| KV cache dtype | `kv_cache_dtype=auto` (bf16 model → bf16 KV) | `cache_dtype="fp8_e4m3"` (`/metrics` `cache_config_info`, recorded in `events.jsonl` at every A2 block start: 733 blocks × 4,096 tokens, `gpu_memory_utilization 0.92`). The image's default KV cache for this profile is FP8, which halves the per-token KV bytes against a bf16 cache; nothing in this run set it. *(Correction: an earlier version of this row said "auto" for A2; the recorded value is `fp8_e4m3`.)* |
| Weights dtype / quantization | `"dtype": "bfloat16"`, `quantization: None` | `Precision: nvfp4`; `Detected ModelOpt NVFP4 checkpoint (quant_algo=NVFP4) … the format is experimental` |

The two arms differ on every row that applies to both, which is one more reason the ratio above describes two options rather than one variable.

**Not shown.** Quality of either model's answers; behaviour under concurrency (every request here was alone); the same models on a card with different bandwidth (the DGX Spark figure in `../p50_availability/README.md` §4 is 15% of this card's); reasoning switched off; any NIM version other than the one each image carries.
