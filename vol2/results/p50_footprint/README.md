# Vol.2 · footprint decomposition (run 2026-09-21)

**Question.** What does each model need on one GPU — as opposed to what a NIM shows in `nvidia-smi`, which is the budget it was allowed and filled with KV cache. Pre-registration `prediction_p50_footprint.json` (frozen before the run, `.sha256` beside it); per-start records in `configs.jsonl`; analysis in `analysis.json`.

**Method.** `NIM_KVCACHE_PERCENT` is the variable both images map to vLLM `gpu_memory_utilization`, the share of the card the engine may use for weights, activations and KV. Each arm was started as its earlier E7 configuration (no override), then restarted with the budget stepped down 0.85, 0.80, … until a start or the probe failed, then once more at the last passing value − 0.025. vLLM refuses to start when the cache that fits inside the budget cannot serve `NIM_MAX_MODEL_LEN` (4,096 here); that refusal is the physical lower bound. A start counts as viable only if three short factual questions (`q001`, `q004`, `q011`, with the `/no_think` system message) returned HTTP 200 with `finish_reason = stop` at `max_tokens 1024`. Card: RTX 5090, 32,607 MiB, driver 591.86; the desktop held 90–540 MiB during the run. One start per configuration, in this order; no start was repeated.

| Arm | Image · profile | Budget (share · MiB) | READY? | Probe | Memory in use at READY (MiB) | Added over pre-launch (MiB) | KV tokens | Failure text |
|---|---|---|---|---|---|---|---|---|
| A1 | `nvidia-nemotron-nano-9b-v2:1.12.2` · bf16 `5cf34bab…` · `NIM_MAX_MODEL_LEN 4096`, `NIM_MAX_NUM_SEQS 32` | default (0.90 · 29,348) | yes | stop ×3 | 29,420 | 28,930 | 435,036 | |
| | | 0.85 · 27,716 | yes | stop ×3 | 27,790 | 27,263 | 330,711 | |
| | | 0.80 · 26,086 | yes | stop ×3 | 26,164 | 25,637 | 226,386 | |
| | | 0.75 · 24,455 | yes | stop ×3 | 24,539 | 24,012 | 122,020 | |
| | | **0.70 · 22,825** | **yes** | **stop ×3** | **22,909** | **22,375** | **17,695** | |
| | | 0.675 · 22,010 | no | — | — | — | — | `No available memory for the cache blocks` (after `Model loading took 16.5842 GiB`) |
| | | 0.65 · 21,195 | no | — | — | — | — | same |
| A2 | `nemotron-3-nano:2.0.12` · NVFP4 `1fba9ecf…` · `NIM_MAX_MODEL_LEN 4096` | default (0.92 · 29,998; no clamp) | yes | stop ×3 | 31,468 | 30,932 | 3,002,368 | |
| | | 0.85 · 27,716 | yes | stop ×3 | 29,195 | 29,106 | 2,236,416 | |
| | | 0.80 · 26,086 | yes | stop ×3 | 27,570 | 27,468 | 1,691,648 | |
| | | **0.75 · 24,455** | **yes** | **stop ×3** | **25,972** | **25,835** | **1,146,880** | |
| | | 0.725 · 23,640 | no | — | — | — | — | `max_num_seqs (256) exceeds available Mamba cache blocks (146)` |
| | | 0.70 · 22,825 | no | — | — | — | — | same |
| A2, FP8 | same image · FP8 `8c91cce8…` (image states ≥ 34 GB) | default | no (20 min) | — | — | — | — | the start spent the window downloading the FP8 weights (cache grew from 19.4 to 52.1 GB); no engine verdict |
| | | 0.85 · 27,716 | no | — | — | — | — | `No available memory for the cache blocks`; the FP8 weights are 32,682,163,544 bytes on disk, more than the card |

KV tokens: for A2 from the engine's `cache_config_info` on `/metrics` (blocks × block size); for A1, whose NIM 1.12.2 does not expose it, derived from the startup log's `Maximum concurrency for 4096 tokens per request: K×` as K × 4,096. A1's memory at READY tracks the budget within 100 MiB at every step (the engine reports `total_gpu_memory (31.84 GiB) × gpu_memory_utilization`); A2's sits 1,400–2,200 MiB above its budget, the part of a NIM 2.0.12 process that lives outside the vLLM budget.

## What the run says

| | A1 · Nemotron Nano 9B v2, bf16 | A2 · Nemotron 3 Nano, NVFP4 |
|---|---|---|
| Weights the engine loaded | 16.58 GiB (16,982 MiB, engine log); 17,776,454,656 bytes on disk | 19,342,796,720 bytes on disk (the 2.0.12 log prints no loading size) |
| Level after the default budget is filled | 29,420 MiB in use (the E7 record's 29,287 was the same quantity) | 31,468 MiB in use (E7: 31,730) |
| Smallest budget that served, at 4,096 context | **0.70 = 22,825 MiB** (0.675 refused) | **0.75 = 24,455 MiB** (0.725 refused) |
| Memory in use at that budget | 22,909 MiB | 25,972 MiB |
| What set the floor | KV cache: no room for cache blocks after the weights | the Mamba state cache for the default 256 sequences, not the KV cache — see the addenda |
| KV at the floor | 17,695 tokens (4.3 × 4,096) | 1,146,880 tokens (280 × 4,096) |
| **Floor at 32 sequences** (the limit A1 ran with) | 0.70 = 22,825 MiB (this run) | **0.65 = 21,195 MiB; 21,872 MiB in use; KV 163,840 tokens** (`../p50_footprint_addendum2/`; refused at 0.625 on KV blocks) |

The pre-registered predictions: **R1** A1 floor between 0.60 and 0.75 — held (0.70). **R2** A2 floor between 0.65 and 0.80 — held (0.75). **R3** the FP8 profile does not reach READY at the default budget — held, but for a reason the prediction did not name: the default attempt ran out of its 20-minute window while downloading, and only the 0.85 attempt produced an engine verdict; the weights alone (32.7 GB) exceed the card, so no budget can hold them. **R4** default-level memory within 2,000 MiB of budget × card — held for A1 (28,930 vs 29,348) and for A2 (30,932 vs 29,998).

**Reading the two floors.** They are not the same kind of number until the sequence limit is equalised. A1's 22.8 GB is weights plus the least KV that serves one 4,096-token request at 32 sequences. A2's 24.5 GB at the engine's default includes Mamba state for 256 concurrent sequences; two addenda repeat A2 at 32 sequences. `NIM_MAX_BATCH_SIZE=32` (`../p50_footprint_addendum/`) did not reach the engine — the sweep reproduced this run to the same refusal. `NIM_PASSTHROUGH_ARGS="--max-num-seqs 32"` (`../p50_footprint_addendum2/`) did: the floor moved to **0.65 = 21,195 MiB (21,872 MiB in use)** and the refusal below it became a KV-block refusal. At the same 32-sequence limit, then, A2 (NVFP4, 19.3 GB of weights) needs about 1,600 MiB less budget than A1 (bf16, 17.8 GB of weights): A1's KV per token is larger. Both models fit a 128 GB system with a large margin — the question for a small system is bandwidth, not fit (section 4 of `../p50_availability/README.md`).

**Not shown here.** Anything about speed; behaviour at other context lengths (the floor moves with `NIM_MAX_MODEL_LEN`); the FP8 profile on a card that can hold 32.7 GB of weights; whether NIM 2.0.12's classification of every profile as "low memory" on a busy desktop (see `../p50_availability/`) affects anything beyond the listing.
