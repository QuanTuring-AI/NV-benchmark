# Vol.3 · Footprint — what each model needs on one GPU

Two deployment options on one RTX 5090 (32,607 MiB, driver 591.86): **A1** Nemotron Nano 9B v2 (bf16, NIM 1.12.2) and **A2** Nemotron 3 Nano (NVFP4, NIM 2.0.12). Everything below is measured on this card on 2026-09-21; the run records are in `results/p50_footprint/`, `results/p50_footprint_addendum/`, `results/p50_footprint_addendum2/`, each with a frozen pre-registration and its own README.

## 1 · Why `nvidia-smi` does not answer the question

A NIM fills the share of the card it is allowed — vLLM `gpu_memory_utilization`, 0.92 by default, clamped lower on a busy card — with KV cache. The number `nvidia-smi` shows at READY is therefore the **budget**, not the model: on a larger card it grows, on a smaller one it shrinks or the engine refuses to start. The earlier E7 run recorded 29,287 MiB for A1 and 31,730 MiB for A2; those are levels after the default budget was filled and are kept below under that name.

The measurement instead sets the budget directly (`NIM_KVCACHE_PERCENT`, the NIM variable both images map to `gpu_memory_utilization`) and steps it down until the engine refuses or a probe fails. vLLM refuses when the cache that fits inside the budget cannot serve `NIM_MAX_MODEL_LEN` tokens (4,096 here); the probe is three short factual questions with `/no_think`, all of which must end with `finish_reason = stop` at `max_tokens 1024`. The minimum therefore lies **between the smallest passing budget and the largest failing one**; it is a bracket, not a single number.

## 2 · The three arms

Units: MiB. *Budget* = `NIM_KVCACHE_PERCENT × 32,607` (the engine's allowed share); *added at READY* = `nvidia-smi` memory in use at READY minus the reading before launch (what the container actually added); *weights* = bytes on disk of the safetensors the profile loads (`results/p50_availability/`) and, where the engine printed it, its own loading line.

| Arm | Image · profile · settings | Weights | Level after default budget (memory in use at READY) | Smallest passing budget | Added at READY at that budget | KV tokens there | Largest failing budget and the engine's refusal |
|---|---|---|---|---|---|---|---|
| **A1** | `nvidia-nemotron-nano-9b-v2:1.12.2` · bf16 `5cf34bab…` · `NIM_MAX_MODEL_LEN 4096`, `NIM_MAX_NUM_SEQS 32` | 17,776,454,656 B on disk; engine log `Model loading took 16.5842 GiB` | 29,420 (default 0.90 → 29,348 budget) | **0.70 → 22,825** | **22,375** (22,909 in use) | 17,695 (4.3 × 4,096) | 0.675 → 22,010: `No available memory for the cache blocks` |
| **A2** (default 256 sequences) | `nemotron-3-nano:2.0.12` · NVFP4 `1fba9ecf…` · `NIM_MAX_MODEL_LEN 4096` | 19,342,796,720 B on disk (the 2.0.12 log prints no loading size) | 31,468 (default 0.92 → 29,998 budget, no clamp) | **0.75 → 24,455** | **25,835** (25,972 in use) | 1,146,880 | 0.725 → 23,640: `max_num_seqs (256) exceeds available Mamba cache blocks (213)` |
| **A2 at 32 sequences** (`NIM_PASSTHROUGH_ARGS "--max-num-seqs 32"`, addendum 2) | same image and profile | same | 29,850 | **0.65 → 21,195** | **21,519** (21,872 in use) | 163,840 (40 × 4,096) | 0.625 → 20,379: `No available memory for the cache blocks` |
| **A2, FP8 profile** — *negative control* | same image · FP8 `8c91cce8…` (image states ≥ 34 GB) | 32,682,163,544 B on disk — more than the card | did not reach READY: the default attempt spent its 20-minute window downloading the FP8 weights; the 0.85 attempt refused with `No available memory for the cache blocks` | — | — | — | no budget on a 32,607 MiB card can hold 32.7 GB of weights |

A table that answers "does it fit" has to contain something that does not: the FP8 row is that sample, and it is the real reason "this card runs Nemotron 3 Nano at NVFP4 only" is a measured statement rather than a reading of the profile list.

## 3 · The Mamba state is a second memory pool, and it set A2's floor

Both models are hybrid Mamba-2 architectures with a handful of attention layers (A1 four, A2 six). Only those attention layers keep a paged KV cache that grows with context; **every Mamba-2 layer keeps one fixed-size state per concurrent sequence**, allocated up front for `max_num_seqs` sequences. In the main run A2's refusals at 0.725 and 0.70 were not about KV blocks at all — the engine could not allocate Mamba state for its default 256 sequences ("Mamba cache blocks 213" at 0.725, 146 at 0.70). The first addendum tried `NIM_MAX_BATCH_SIZE=32` and reproduced the main run exactly: that variable does not reach the engine in NIM 2.0.12 for this profile. The second addendum passed `--max-num-seqs 32` through `NIM_PASSTHROUGH_ARGS`; the KV cache grew at every budget (the state of 224 fewer sequences was released), the floor moved from 0.75 to 0.65, and the refusal below it became a KV-block refusal. The per-sequence Mamba state of A2 at this profile is about 14.6 MiB (3,260 MiB of budget over 224 sequences).

Two consequences for reading any Nemotron memory figure: `NIM_MAX_MODEL_LEN` and `max_num_seqs` size two different pools, so a floor is only meaningful with both stated; and a floor measured at the engine's default 256 sequences describes a server, not a single user.

## 4 · What the floors say, at the same 32-sequence limit

| | A1 (bf16, 17.8 GB weights) | A2 (NVFP4, 19.3 GB weights) |
|---|---|---|
| Bracket for the minimum budget at 4,096 context, 32 sequences | 22,010 – 22,825 MiB | 20,379 – 21,195 MiB |
| Memory in use at the smallest passing budget | 22,909 MiB | 21,872 MiB |

A2 needs about 1,600 MiB less budget than A1 despite 1.5 GB more weights: A1's bf16 KV per token is larger and its floor is KV-bound. Both fit a 128 GB system with a wide margin.

**DGX Spark projection — a projection, not a measurement.** DGX Spark has 128 GB of unified memory (distributor quotation and NVIDIA's page agree) and 273 GB/s of bandwidth (NVIDIA's page; 15% of this card's 1,792 GB/s). On the memory axis both minima above are a fraction of 128 GB, so "only A1 fits" is not what the footprint says. The binding constraint on that machine is bandwidth: A1 generates at 72% of this card's peak bandwidth (`results/p50_speed/`), so its rate scales with the bandwidth ratio; A2 reads about a fifth of the bytes per token. An external measurement on DGX Spark reports Nemotron 3 Nano at 56.19 tok/s single-stream (NVIDIA Developer Forum, thread 359074, llama-benchy 0.1.1) — a different stack and tool, so it is an order-of-magnitude check, not a comparison with any number here.

## 5 · Not shown

The floors at other context lengths (they move with `NIM_MAX_MODEL_LEN`); the FP8 profile on a card that can hold 32.7 GB of weights; anything about speed (that is `results/p50_speed/`); and whether NIM 2.0.12's "low memory" classification of every profile on a busy desktop (`results/p50_availability/`) affects more than the listing.
