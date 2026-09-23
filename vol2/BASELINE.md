# Vol.2 · BASELINE

Vol.2 measures two NVIDIA NIM deployment options on one RTX 5090 (32,607 MiB, driver 591.86): **A1** Nemotron Nano 9B v2 (hybrid Mamba-2 + MLP, dense, bf16, NIM 1.12.2) and **A2** Nemotron 3 Nano (hybrid Mamba-2 + MoE, 30B total / 3.5B active, NVFP4, NIM 2.0.12). No common NIM version exists for the two models (`results/p50_availability/`), and each runs at the only precision its image can execute on this card; every table therefore carries model, precision, NIM version, `max_num_seqs` and `max_tokens` per row, and nothing in this volume is a single-variable comparison. The methods and gates are Vol.1-B's (pre-registration frozen before each run, positive controls, preconditions that null the conclusions, the arm-health gate before any ratio); the numbers are new. Llama 3.1 8B appears only where an earlier record or the MLPerf benchmark name is quoted; the Vol.1 non-NIM runtime does not appear.

Each section names its run directory; every run directory holds the frozen pre-registration, the raw rows and the analysis, and a README with the full boundary.

## A · Does it fit — footprint (`results/p50_footprint/`, `…_addendum/`, `…_addendum2/`; written up in `FOOTPRINT.md`)

| | A1 · bf16 · NIM 1.12.2 · `max_num_seqs` 32 | A2 · NVFP4 · NIM 2.0.12 · `max_num_seqs` 256 (default) | A2 · NVFP4 · `max_num_seqs` 32 | A2 · FP8 profile (negative control) |
|---|---|---|---|---|
| Weights on disk | 17,776,454,656 B (engine: 16.58 GiB loaded) | 19,342,796,720 B | same | 32,682,163,544 B |
| Level after the default budget | 29,420 MiB | 31,468 MiB | 29,850 MiB | never READY |
| Smallest passing budget at 4,096 context | 0.70 → 22,825 MiB (22,909 in use) | 0.75 → 24,455 MiB (25,972 in use) | **0.65 → 21,195 MiB (21,872 in use)** | — |
| Largest failing budget · engine's refusal | 0.675 · KV blocks | 0.725 · **Mamba state for 256 sequences** | 0.625 · KV blocks | 0.85 · KV blocks; weights alone exceed the card |

The minimum lies between the smallest passing and the largest failing budget; it is a bracket. A2's floor at the engine default was set by the per-sequence Mamba state (about 14.6 MiB per sequence), not by the KV cache; `NIM_MAX_BATCH_SIZE` did not reach the engine, `NIM_PASSTHROUGH_ARGS "--max-num-seqs 32"` did. At the same 32-sequence limit A2 needs about 1,600 MiB less than A1. Both fit 128 GB with a wide margin; on DGX Spark the binding axis is bandwidth (273 GB/s, 15% of this card), a projection, not a measurement.

## B · How fast — speed (`results/p50_speed/`) and time to answer (`results/p53_answer/`)

Fifty questions of the Vol.1 set in a fixed order, four alternating container blocks (A1, A2, A1, A2), Vol.1's request shape with usage recorded, no system prompt (both models reason by default).

| Quantity | A1 · bf16 · 1.12.2 · seqs 32 · `max_tokens` 500 | A2 · NVFP4 · 2.0.12 · seqs 256 · `max_tokens` 500 | A2 / A1 (ratio of means, 95% CI over questions) |
|---|---|---|---|
| Generation rate, median tok/s | 72.9 | 305.1 | **4.14** [4.08, 4.19] |
| tps, engine tokens / total latency | 72.4 | 292.8 | 4.01 [3.95, 4.07] |
| TTFT, median ms | 52.1 | 40.8 | 0.70 [0.58, 0.83] |
| Completions cut at 500 tokens | 42 / 50 | 37 / 50 | |
| Arm health: bytes read per token · effective bandwidth · share of 1,792 GB/s | 17.78 GB · 1,297 GB/s · **72%** | 3.59 GB (non-expert 2.56 + shared 0.26 + 6/128 routed) · 1,096 GB/s · **61%** | gate passes on both |

The 4.14× is a generation-rate ratio. It is not "answers a question 4.14× faster". The same design at `max_tokens 4096` and `NIM_MAX_MODEL_LEN 8192` (`results/p53_answer/`, 100 requests, all preconditions held, health gate 70.5% / 59.9%) measured the time to the end of the answer:

| Quantity | A1 · bf16 · 1.12.2 · seqs 32 · `max_tokens` 4096 | A2 · NVFP4 · 2.0.12 · seqs 256 · `max_tokens` 4096 | A2 / A1 (ratio of means, 95% CI) |
|---|---|---|---|
| Time to the end of the answer, avg / p50 (ms) | 19,814 / 20,102 | 6,796 / 7,314 | **0.343** [0.307, 0.377] (≈ 2.9× faster per answer) |
| Completion tokens, avg / p50 | 1,405 / 1,421 | 2,017 / 2,145 | 1.44 [1.28, 1.58] |
| Cut at 4,096 tokens | 0 / 50 | 6 / 50 (A2's row is a lower bound) | |
| Generation rate, p50 tok/s | 71.1 | 298.9 | 4.15 [4.09, 4.20] |
| Reasoning channel exposed | none | none | |

Per answer A2 is about 2.9× faster, not 4.15×, because it writes 1.4× as many tokens before stopping. Neither image separates reasoning from answer in what it streams (no `reasoning_content`, no `<think>` marker on any of 100 rows), so the split could not be measured. A2's KV cache runs at `fp8_e4m3` by image default (`/metrics`).

Engine environment fields for both arms (MoE backend, `mamba_ssm_cache_dtype`, CUDA graph mode, `max_num_seqs`, `max_tokens`), quoted from the startup logs or marked "not disclosed", are in `results/p50_speed/README.md`.

## C · How many at once — concurrency (`results/p53_concurrency/`)

Closed-loop AIPerf 0.11.0, levels 1–64, two synthetic profiles (**C** chat 200/200, **R** RAG 3,500/500, `ignore_eos`), both arms at `max_num_seqs` 32 and `NIM_MAX_MODEL_LEN` 8192, a fresh container repeating the two highest levels, and an instrument calibration (the harness's own client against AIPerf at c=1) gating every sweep. SLOs fixed before any number: MLPerf Inference v5.1 Llama 3.1-8B server (p99 TTFT ≤ 2,000 ms ∧ p99 TPOT ≤ 100 ms) and interactive (500 ms ∧ 30 ms) — another model's rulers, the same on every row. Two runs: the first (`results/p53_concurrency/`) has valid level tables and null conclusions (its gate compared a warming A2 engine with a warm one and one prompt length with another; A1's engine crash broke its "all levels clean" rule); the second (`results/p53_concurrency_v2/`, gate repaired, pre-registered from the first run's numbers) is the record. Numbers below are the second run's.

| Arm · profile | Largest c inside the server SLO | inside the interactive SLO | Throughput at that c · saturation | Ceiling |
|---|---|---|---|---|
| A1 · bf16 · 1.12.2 · seqs 32 · `max_tokens` 200 · **C** | **16** (p99 TTFT 434 ms, p99 ITL 20.6 ms) | **16** | 777 tok/s · not reached before the crash | **engine crash at c=32** (`IndexError` in the Mamba constant-size cache; 3 of 4 containers at 32, the fourth at 64) |
| A1 · … · `max_tokens` 500 · **R** | **4** (c=8: p99 TTFT 2.5 s) | **1** (c=2: 631 ms) | 234 tok/s · not reached | engine crash at c=32 |
| A2 · NVFP4 · 2.0.12 · seqs 32 · `max_tokens` 200 · **C** | **32** (p99 TTFT 379 ms, p99 ITL 22.2 ms) | **32** | **1,540 tok/s** · saturates at 32 (1,490 at 64) | reached at c=64: queueing (p99 TTFT 4.6 s, ITL unchanged) |
| A2 · … · `max_tokens` 500 · **R** | **8** (p99 TTFT 1.0 s) | **4** (492 ms) | 884 tok/s · saturates at 32 (1,462 → 1,464) | reached at c=16 (p99 TTFT 2.1 s); p99 ITL < 24 ms up to c=64 |

A1 does not reach a latency ceiling on the chat profile: it dies first, at concurrency = `max_num_seqs`, because its NIM 1.12.2 vLLM V0 build keeps one Mamba-state slot per sequence and the free list empties when 32 sequences are placed in one step. A2 (vLLM 0.27.1) queues instead. On the RAG profile both arms are bound by prefill queueing (TTFT), not decode: A2's p99 ITL never exceeds 24 ms while its p99 TTFT passes 2 s at c=16. Fresh-container repeats agree with the main sweeps within 0.3–3.5% on A2. Calibration: ITL within 1–3% on every sweep; TTFT within 1% on A1 and 12–14 ms on A2. No sentence of the form "serves N users" follows from any of this.

## D · Does long context hold — depth sweep (`results/p53_longctx/`)

Each depth in its own container (`NIM_MAX_MODEL_LEN` 4096 / 8192 / 32768 / 131072), both arms at `max_num_seqs` 32, five synthetic prompts per depth (Vol.1 questions concatenated), `max_tokens` 256; medians. All preconditions held; **no context ceiling: both arms serve at `NIM_MAX_MODEL_LEN` 131,072 on this card.**

| Measured prompt tokens | A1 · bf16 · 1.12.2 · seqs 32 · `max_tokens` 256: TTFT · generation (main run) | A2 · NVFP4 · 2.0.12 · seqs 32 · `max_tokens` 256: TTFT · generation (addendum, after warm-up) |
|---|---|---|
| ~1,135 | 157 ms · 71.7 tok/s | 95 ms · **304.8** |
| ~3,770 | 408 ms · 71.6 | 155 ms · **298.9** |
| ~14,215 | 1,398 ms · **44.7** (addendum: 1,348 · 45.8) | 489 ms · **315.2** |
| ~56,730 | 6,201 ms · **44.4** | 2,371 ms · **309.0** |

A1's generation rate steps down 38% between 4k and 16k and is then flat to 57k: the engine's `max_seq_len_to_capture` is 8,192 (config dump), so longer sequences decode without CUDA graphs on this vLLM V0 build — a per-step cost, not a growing state. At `NIM_MAX_MODEL_LEN` 32,768 the same image keeps only 53k KV tokens (no chunked prefill); at 131,072 it turns chunked prefill on by itself and keeps 456k. **A2's generation rate is flat from 1k to 57k** (±3%; the external DGX Spark measurement reports −8.5% at 100k) and its TTFT grows sub-linearly (24.8× for 50× the tokens). A2's first requests after READY run at 40–60% of its rate for a variable 10–50 s (`results/p53_longctx_addendum/`, warm-up rows and a clock diagnosis; cause not identified), which contaminated the main run's A2 medians at 1k, 4k and 64k; the addendum's numbers, measured after an adaptive warm-up, are the A2 record. Memory at READY does not track context (both engines take a fixed share of the card); the KV-token counts are the memory record.

## E · What Guardrails costs — NeMo Guardrails 0.23.0 on both arms (`results/p53_guardrails/`)

Vol.1-A's 45 E3 questions × 3 rounds, three request arms rotated per question in one container per arm: nim-only, the rail with Vol.1's config verbatim (G), and the rail with E9's `/no_think` judge message (H). Both arms `NIM_MAX_MODEL_LEN` 8192, `max_num_seqs` 32, `max_tokens` 500. 810 rows; all preconditions held. Block labels re-derived from response digests (`analysis_digest.json`; the frozen analyser's text-based predicate saw none, see the README).

| | A1 · bf16 · 1.12.2 · seqs 32 · `max_tokens` 500 | A2 · NVFP4 · 2.0.12 · seqs 32 · `max_tokens` 500 |
|---|---|---|
| Rail with Vol.1's config (G): true blocks, clean / edge / adversarial | **60/60 · 30/30 · 45/45** — the judge answers with 214 tokens of reasoning (2.9 s), the parser reads it as unsafe | **60/60 · 30/30 · 45/45** — 79 tokens (415 ms) |
| Rail with the `/no_think` judge (H) | **0/60 · 0/30 · 45/45** — one-word verdicts (3 and 5 tokens) | 60/60 · 30/30 · 45/45 — the message has no effect on this model's judge (78 tokens) |
| End-to-end clean_passthrough overhead (Vol.1-A algorithm) | H: **−0.2%** avg; paired −0.25% [−0.49%, −0.02%] over 30 questions | not measurable: no rail row answered |
| Rail cost per request (judge calls alone) | H: input check 113 ms / 3 tokens · output check 135 ms / 5 tokens ≈ 250 ms, 3.6% of a 500-token answer | input check 415–426 ms / 78–79 tokens, then a refusal |
| Judge calls at the 1,024-token budget · empty verdicts | 0 · 0 | 0 · 0 |

The stack runs end to end on both arms. What the library's default self-check prompts get back from a reasoning-by-default model is a paragraph, and the rail treats a paragraph as a block, on every question; the −53% and −77% "overheads" the frozen analyser prints for those cells are the cost of a refusal, not of an answer. On A1 the `/no_think` judge restores one-word verdicts and the rail behaves as on Llama in Vol.1-B (45/45 adversarial, 0/90 false blocks on this sample); the end-to-end overhead is nil because both nim-only and the rail's answer run to the 500-token cap, so there is no output-length effect, and the rail's non-streamed answer call is about 300 ms faster than the streamed request. On A2 the request shape that yields a one-word verdict from its judge was not found within the two pre-registered configs, so the Vol.1 rail config cannot be used with Nemotron 3 Nano as published.

## F · Which precisions this card can run — precision availability (`results/p50_availability/`, `results/p50_footprint/`)

| Model | Executable on this card | Not executable, with the measured reason |
|---|---|---|
| A1 · Nemotron Nano 9B v2 (NIM 1.12.2) | bf16 (profile `5cf34bab…`) | the image ships no other single-GPU precision profile (its only other profile is bf16 tp2) |
| A2 · Nemotron 3 Nano (NIM 2.0.12) | NVFP4 (profile `1fba9ecf…`, image states ≥ 21 GB) | FP8 (`8c91cce8…`, image states ≥ 34 GB): weights are 32.7 GB on disk, start refused at 0.85 budget, never READY · bf16 (`352d88f8…`, ≥ 63 GB): not attempted, exceeds the card |

This is a precision *availability* table, not a precision ladder: each model has exactly one executable precision on a 32 GB card, and that is the result.

## What this volume does not do

Compare the two models as if one variable changed; quote any figure from the Vol.1 non-NIM runtime; reuse Llama 3.1 8B as an arm; transfer any tok/s to another machine (only the long-context decay shape is compared with an external DGX Spark measurement); or produce a sentence of the form "serves N users" — the concurrency numbers are p99 latencies at closed-loop concurrency levels, with the SLO and its source on every row.
