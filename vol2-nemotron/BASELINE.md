# Vol.2 · BASELINE

Vol.2 measures two NVIDIA NIM deployment options on one RTX 5090 (32,607 MiB, driver 591.86): **A1** Nemotron Nano 9B v2 (hybrid Mamba-2 + MLP, dense, bf16, NIM 1.12.2) and **A2** Nemotron 3 Nano (hybrid Mamba-2 + MoE, 30B total / 3.5B active, NVFP4, NIM 2.0.12). No common NIM version exists for the two models (`results/p50_availability/`), and each runs at the only precision its image can execute on this card; every table therefore carries model, precision, NIM version, `max_num_seqs` and `max_tokens` per row, and nothing in this volume is a single-variable comparison. The methods and gates are Vol.3's (pre-registration frozen before each run, positive controls, preconditions that null the conclusions, the arm-health gate before any ratio); the numbers are new. Llama 3.1 8B appears only where an earlier record or the MLPerf benchmark name is quoted; the Vol.1 non-NIM runtime does not appear.

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

**Cross-check of the single-stream rates (P78).** The four cells of the speed run do not match the idle-card fingerprint in their end-of-cell GPU record (`results/p78_audit/`), and the run was not repeated. The same quantity was measured again in P78, where an idle-card gate passed before every cell: A1 72.9 tok/s here against 72.4 at the arm-health probe that opens the P78 quality run (`results/p78_quality/analysis.json`, `arm_health.N2`; 0.7% apart); A2 305.1 here against 316.8 at the health probe of the NIM arm in `results/p78_nim_vs_vllm/` (`events_public.jsonl`, kind `health`) and a 50-question median of 292.5 (`analysis.json`, `P2`) — within ±4%. The footprint cells were not re-run either.

**A2 needs a warm-up after READY (P55, `results/p55_a2_slow_phase/`, no GPU run).** In some containers A2's first requests after READY run at roughly half its steady rate. In the records on disk the slow phase that ended lasted at most **7 requests, 33 s**. Two containers were still slow after 6 and 7 requests (31–36 s) when stopped. Nothing in the container logs coincides with it: autotuning ends 12–21 s before READY, and the engine logs nothing after READY. So the cause is unverified. Every long slow phase was in the first A2 container of its run; shorter ones (1–3 requests) also appeared later. For a demo or a measurement, send warm-up requests until the rate has held steady for three requests in a row; in this volume that took 11–18 requests and about a minute. A1 showed no slow phase.

## C · How many at once — concurrency (`results/p53_concurrency/`)

Closed-loop AIPerf 0.11.0, levels 1–64, two synthetic profiles (**C** chat 200/200, **R** RAG 3,500/500, `ignore_eos`), both arms at `max_num_seqs` 32 and `NIM_MAX_MODEL_LEN` 8192, a fresh container repeating the two highest levels, and an instrument calibration (the harness's own client against AIPerf at c=1) gating every sweep. SLOs fixed before any number: MLPerf Inference v5.1 Llama 3.1-8B server (p99 TTFT ≤ 2,000 ms ∧ p99 TPOT ≤ 100 ms) and interactive (500 ms ∧ 30 ms) — another model's rulers, the same on every row. Two runs: the first (`results/p53_concurrency/`) has valid level tables and null conclusions (its gate compared a warming A2 engine with a warm one and one prompt length with another; A1's engine crash broke its "all levels clean" rule); the second (`results/p53_concurrency_v2/`, gate repaired, pre-registered from the first run's numbers) is the record. Numbers below are the second run's.

| Arm · profile | Largest c inside the server SLO | inside the interactive SLO | Throughput at that c · saturation | Ceiling |
|---|---|---|---|---|
| A1 · bf16 · 1.12.2 · seqs 32 · `max_tokens` 200 · **C** | **16** (p99 TTFT 434 ms, p99 ITL 20.6 ms) — P80 re-run: **8** (engine exit at c=16) | **16** — P80: **8** | 777 tok/s · not reached before the crash | **engine crash at c=32** (`IndexError` in the Mamba constant-size cache; 3 of 4 containers at 32, the fourth at 64) — P80: at c=16 in 2 of 4 containers, at c=32 in the other 2 |
| A1 · … · `max_tokens` 500 · **R** | **4** (c=8: p99 TTFT 2.5 s) | **1** (c=2: 631 ms) | 234 tok/s · not reached | engine crash at c=32 |
| A2 · NVFP4 · 2.0.12 · seqs 32 · `max_tokens` 200 · **C** | **32** (p99 TTFT 379 ms, p99 ITL 22.2 ms) | **32** | **1,540 tok/s** · saturates at 32 (1,490 at 64) | reached at c=64: queueing (p99 TTFT 4.6 s, ITL unchanged) |
| A2 · … · `max_tokens` 500 · **R** | **8** (p99 TTFT 1.0 s) | **4** (492 ms) | 884 tok/s · saturates at 32 (1,462 → 1,464) | reached at c=16 (p99 TTFT 2.1 s); p99 ITL < 24 ms up to c=64 |

A1 does not reach a latency ceiling on the chat profile: its engine exits first. In this run that happened at concurrency = `max_num_seqs` (32); the P80 re-run below saw the same exit at 16 as well, so the level is not fixed at the cap. The traceback ends where the engine takes a free Mamba-state slot from an empty list (`constant_size_cache.py`, `free_cache_indices.pop()`); this NIM 1.12.2 image logs that it falls back to vLLM's V0 engine for this model. A2 (vLLM 0.27.1) queues instead. On the RAG profile both arms are bound by prefill queueing (TTFT), not decode: A2's p99 ITL never exceeds 24 ms while its p99 TTFT passes 2 s at c=16. Fresh-container repeats agree with the main sweeps within 0.3–3.5% on A2. Calibration: ITL within 1–3% on every sweep; TTFT within 1% on A1 and 12–14 ms on A2. No sentence of the form "serves N users" follows from any of this.

**A2 with its sequence cap raised (P55: `results/p55_concurrency_a2_256/`, `…_128/`, `…_064/`, `results/p55_capture_control/`).** The 32 above is the cap both arms shared, not A2's ceiling. The same harness, profiles, SLOs and rules, run again on A2 at `max_num_seqs` 64, 128 and 256 (the image default, nothing passed); each run pre-registered, all preconditions held, no engine death:

| A2 · NVFP4 · 2.0.12 · `max_num_seqs` | C: largest c in server SLO · interactive SLO | C: throughput at c=32 · peak | R: server · interactive | What stops admission at the top |
|---|---|---|---|---|
| 32 (above, earlier session) | 32 · 32 | 1,540 · 1,540 | 8 · 4 | the cap (32 running) |
| 64 | 64 · 16 | 1,130 · 1,470 (fresh container 1,804) | 8 · 2 | the cap (64 running; KV blocks 42%) |
| 128 | 128 · 32 | 1,738 · 2,679 | 8 · 2 | the cap (128 running; KV blocks 87%) |
| **256 (image default)** | **128 · 32** | **2,238 · 3,999** | **8 · 2** | **the KV block pool: 146 running, 99.7% of 733 blocks** |

Three readings. (1) **On the chat profile A2 keeps p99 TTFT under 2 s up to 128 concurrent requests at the image default, and the interactive ceiling stays at 32 (16 at cap 64).** On the RAG profile the server ceiling is 8 at every cap: long prompts queue for prefill whatever the cap. (2) **At the default cap the ceiling on this card is about 146 concurrent sequences, set by the KV block pool, not the cap.** The pool is counted per sequence: 5 cache groups (1 attention and 4 Mamba, after one padding layer), one block each below 4,176 tokens, and 733 / 5 ≈ 146. This is derived from the model config and the startup log and matches the running gauge at every cap: 87.3% at 128, 42.4% at 64. The engine's "3.06 million KV tokens" is not this model's capacity. (3) **At a fixed concurrency, the rate follows the CUDA-graph capture size that vLLM derives from the cap** (min(2 × cap, 512) tokens). At cap 256, lowering only the capture size to cap 32's (64) cut the chat-profile rate to 0.47× at c=32 and 0.49× at c=16 in one session (`results/p55_capture_control/`). The measurement covers that direction only. The size of the differences between the sweeps is not explained by it alone, and containers of one configuration differed by up to 31% at c=64. For a deployment: lowering the cap to "reserve" speed for fewer users makes this image slower, not faster.

**The main sweeps repeated on a gated night (P80: `results/p80_rerun/`, 2026-10-01).** Most cells of the two runs above do not match the idle-card fingerprint in their end-of-cell GPU record (`results/p78_audit/`), so their six main sweeps were run again with an idle-card gate before every cell, a speed sentinel per container and an arm-health probe around every cell. Each re-run is judged by the analysis function of the run it repeats (`scripts/p80_slo.py`). Both values are given; neither replaces the other.

| Sweep (main container) | Largest c in server · interactive SLO: original | P80 | Throughput, P80 ÷ original, lowest–highest level ratio |
|---|---|---|---|
| A2 · cap 256 · **C** (`p55_concurrency_a2_256`) | 128 · 32 | **128 · 32** | 0.73–0.92 (c=32: 2,238 → 1,644 tok/s; c=128: 3,902 → 3,188) |
| A2 · cap 256 · **R** | 8 · 2 | null by the run's own rule P1 (one failed request of 2,579 at c=512); the SLO test alone: 8 · 2 | 1.01–1.19 |
| A2 · cap 32 · **C** (`p53_concurrency_v2`) | 32 · 32 | **32 · 32** | 0.97–1.00 |
| A2 · cap 32 · **R** | 8 · 4 | **8 · 4** | 0.97–1.01 |
| A1 · cap 32 · **C** | 16 · 16 | **8 · 8** (engine exit at c=16) | 1.01–1.03 at c=1–8 |
| A1 · cap 32 · **R** | 4 · 1 | **4 · 1** | 0.99–1.01 at c=1–16 |

Three readings. (1) **Four of the six sweeps reproduce their SLO ceilings exactly;** the fifth (A2 · cap 256 · R) has the original's values under the SLO test and a null conclusion under its own precondition, and the sixth (A1 · C) is lower because the engine exited one level earlier, not because it was slower. (2) **One container was 8–27% below its original at every level while the next one, from the same image with the same settings on the same night, was not** (12–16% apart on the identical sentinel probes); the cause was not identified, the amount of the container's GPU memory held in system RAM at READY does not separate the two, and the SLO ceilings are the same. Throughput figures at a given concurrency therefore carry a container-to-container spread of this size (the cap-64 sweep above already showed 31% at c=64). (3) **The A1 engine exit is not tied to c=32.** Over the two nights all eight A1 containers ended with the same `IndexError('pop from empty list')`: twice at c=16, five times at c=32 (in two of them after the level had completed), once at c=64. Upstream vLLM 0.30.0 on the same weights ran 16, 32 and 64 without an engine exit (817 / 1,318 / 1,807 tok/s, p99 TTFT 339 / 665 / 1,273 ms; a different engine version and build, not a single-variable comparison). The A1 containers' logs record a fall-back to vLLM's V0 engine (v0.10.0) and the upstream container's log a V1 engine (v0.30.0); the lines are quoted with their line numbers in `results/p80_rerun/engine_log_excerpts.json`.

## D · Does long context hold — depth sweep (`results/p53_longctx/`)

Each depth in its own container (`NIM_MAX_MODEL_LEN` 4096 / 8192 / 32768 / 131072), both arms at `max_num_seqs` 32, five synthetic prompts per depth (Vol.1 questions concatenated), `max_tokens` 256; medians. All preconditions held; **no context ceiling: both arms serve at `NIM_MAX_MODEL_LEN` 131,072 on this card.**

| Measured prompt tokens | A1 · bf16 · 1.12.2 · seqs 32 · `max_tokens` 256: TTFT · generation (main run) | A2 · NVFP4 · 2.0.12 · seqs 32 · `max_tokens` 256: TTFT · generation (addendum, after warm-up) |
|---|---|---|
| ~1,135 | 157 ms · 71.7 tok/s | 95 ms · **304.8** |
| ~3,770 | 408 ms · 71.6 | 155 ms · **298.9** |
| ~14,215 | 1,398 ms · **44.7** (addendum: 1,348 · 45.8) | 489 ms · **315.2** |
| ~56,730 | 6,201 ms · **44.4** | 2,371 ms · **309.0** |
| ~119,720 *(P55, `results/p55_longctx_120k/`)* | 14,263 ms · **52.4** (same session's 14k: 55.7) | 7,281 ms · **308.4** |

A1's generation rate steps down 38% between 4k and 16k and is then flat to 57k: the engine's `max_seq_len_to_capture` is 8,192 (config dump), so longer sequences decode without CUDA graphs on this vLLM V0 build — a per-step cost, not a growing state. That attribution is measured (`results/p55_a1_capture/`, P55): switching graphs off at ~3.8k tokens drops A1 from 76.4 to 52.3 tok/s, and at ~14k changes 55.7 to 51.7 (same session; A1's absolute rates in that session ran up to ~20% above the earlier runs'). At `NIM_MAX_MODEL_LEN` 32,768 the same image keeps only 53k KV tokens (no chunked prefill); at 131,072 it turns chunked prefill on by itself and keeps 456k. **A2's generation rate is flat from 1k to 120k** (304.8 → 308.4 tok/s; the external DGX Spark measurement reports −8.5% from 0 to 100k; shape only, no absolute values compared) and its TTFT grows sub-linearly (24.8× for 50× the tokens). A2's first requests after READY run at 40–60% of its rate for a variable 10–50 s (`results/p53_longctx_addendum/`, warm-up rows and a clock diagnosis; cause not identified), which contaminated the main run's A2 medians at 1k, 4k and 64k; the addendum's numbers, measured after an adaptive warm-up, are the A2 record. Memory at READY does not track context (both engines take a fixed share of the card); the KV-token counts are the memory record.

## E · What Guardrails costs — NeMo Guardrails 0.23.0 on both arms (`results/p53_guardrails/`)

The March 2026 Vol.1's 45 E3 questions × 3 rounds, three request arms rotated per question in one container per arm: nim-only, the rail with Vol.1's config verbatim (G), and the rail with E9's `/no_think` judge message (H). Both arms `NIM_MAX_MODEL_LEN` 8192, `max_num_seqs` 32, `max_tokens` 500. 810 rows; all preconditions held. Block labels re-derived from response digests (`analysis_digest.json`; the frozen analyser's text-based predicate saw none, see the README).

| | A1 · bf16 · 1.12.2 · seqs 32 · `max_tokens` 500 | A2 · NVFP4 · 2.0.12 · seqs 32 · `max_tokens` 500 |
|---|---|---|
| Rail with Vol.1's config (G): true blocks, clean / edge / adversarial | **60/60 · 30/30 · 45/45** — the judge answers with 214 tokens of reasoning (2.9 s), the parser reads it as unsafe | **60/60 · 30/30 · 45/45** — 79 tokens (415 ms) |
| Rail with the `/no_think` judge (H) | **0/60 · 0/30 · 45/45** — one-word verdicts (3 and 5 tokens) | 60/60 · 30/30 · 45/45 — the message has no effect on this model's judge (78 tokens) |
| End-to-end clean_passthrough overhead (March 2026 Vol.1 algorithm) | H: **−0.2%** avg; paired −0.25% [−0.49%, −0.02%] over 30 questions | not measurable: no rail row answered |
| Rail cost per request (judge calls alone) | H: input check 113 ms / 3 tokens · output check 135 ms / 5 tokens ≈ 250 ms, 3.6% of a 500-token answer | input check 415–426 ms / 78–79 tokens, then a refusal |
| Judge calls at the 1,024-token budget · empty verdicts | 0 · 0 | 0 · 0 |

The stack runs end to end on both arms. What the library's default self-check prompts get back from a reasoning-by-default model is a paragraph, and the rail treats a paragraph as a block, on every question; the −53% and −77% "overheads" the frozen analyser prints for those cells are the cost of a refusal, not of an answer. On A1 the `/no_think` judge restores one-word verdicts and the rail behaves as on Llama in Vol.3 (45/45 adversarial, 0/90 false blocks on this sample); the end-to-end overhead is nil because both nim-only and the rail's answer run to the 500-token cap, so there is no output-length effect, and the rail's non-streamed answer call is about 300 ms faster than the streamed request. On A2 the request shape that yields a one-word verdict from its judge was not found within the two pre-registered configs, so the Vol.1 rail config cannot be used with Nemotron 3 Nano as published.

**The A2 judge with its reasoning switched off** (`results/p55_judge_thinking/`, P55). Nemotron 3 Nano's switch is `chat_template_kwargs: {enable_thinking: false}`, not `/no_think`. Guardrails 0.23.0 delivers it to the two judge calls alone when they are given task-typed models (`self_check_input`, `self_check_output`) carrying that parameter; the answer model keeps reasoning on. No Guardrails code was changed.

| A2 · NVFP4 · 2.0.12 · seqs 32 · `max_tokens` 500 | Straight to the NIM (L1, 135 calls per check) | Through Guardrails 0.23.0 (L2, 45 questions × 3 rounds) |
|---|---|---|
| judge reply with the switch | one word in 2 tokens, ~106 ms (without it: 67–79 tokens of reasoning, never yes/no) | input check 113 ms, output check 87 ms, 2 tokens each |
| verdicts / true blocks: clean · edge · adversarial | input check yes on 0 · 0 · 45 of 60 · 30 · 45 | blocked 0/60 · 0/30 · **45/45** |
| end-to-end clean_passthrough overhead | — | **+16.8%** [+16.2%, +17.4%] (1,698 → 1,983 ms; no output-length effect: both arms' answers run to the cap) |

Vol.1's rail config assumes a judge that answers yes or no directly. Nemotron reasons by default, and the two generations switch it off differently. With the right switch each Nemotron judge behaves as the Llama judge did in Vol.3 on this question set: A1 at about 250 ms of rail cost, A2 at about 200 ms. When quoting E, use `analysis_digest.json` in `results/p53_guardrails/` (a post-run analyser, disclosed) and `results/p55_judge_thinking/`.

## F · Which precisions this card can run — precision availability (`results/p50_availability/`, `results/p50_footprint/`)

| Model | Executable on this card | Not executable, with the measured reason |
|---|---|---|
| A1 · Nemotron Nano 9B v2 (NIM 1.12.2) | bf16 (profile `5cf34bab…`) | the image ships no other single-GPU precision profile (its only other profile is bf16 tp2) |
| A2 · Nemotron 3 Nano (NIM 2.0.12) | NVFP4 (profile `1fba9ecf…`, image states ≥ 21 GB) | FP8 (`8c91cce8…`, image states ≥ 34 GB): weights are 32.7 GB on disk, start refused at 0.85 budget, never READY · bf16 (`352d88f8…`, ≥ 63 GB): not attempted, exceeds the card |

This is a precision *availability* table, not a precision ladder: each model has exactly one executable precision on a 32 GB card, and that is the result.

## G · Vol.1 (renewed): NIM against the engine it contains (`results/p54_engine/`; written up in `../vol1-nim/README.md`)

Llama 3.1 8B Instruct, bf16, one RTX 5090, the same weight files. **N** is NIM 2.0.12 (profile `092ed421…`, `NIM_MAX_MODEL_LEN` 8192, `VLLM_USE_V2_MODEL_RUNNER=0`). **V** is upstream vLLM 0.27.1: the same build commit as the engine inside N, started with NIM's own resolved vLLM argument list. The only edits to that list are the model path, NIM's internal port and host, and its two server-layer middlewares. Pre-registered; every difference that could not be aligned is listed there, including the KV cache each engine sizes for itself at start (97,328 / 107,728 tokens).

| | N | V |
|---|---|---|
| Arm health, single stream (share of 1,792 GB/s) | 88.2% | 88.0% |
| Generation rate, TTFT, answer time, median (50 questions, `max_tokens` 4096) | 98.4 tok/s · 31.4 ms · 5,066 ms | 98.2 tok/s · 31.7 ms · 5,053 ms |
| Answers byte-identical across the arms | 50 / 50 | |
| Chat profile: largest c in server · interactive SLO; peak tok/s | 256 · 32; 6,257 (fresh 6,306) | 256 · 32; 6,056 (fresh 6,321) |
| RAG profile | null: the harness's calibration prompt hits the prefix cache (P2); level tables published | null: one disconnected request at c=256 (P1) |
| Settings to the first serving start · in the measured configuration | 3 (bf16 profile, context length, V1 runner) · 3 | 2 (context length, V1 runner) · 6 |

On this card and precision the two arms are the same engine within the run-to-run spread, down to the text they write. The pre-registered ratio V over N is 0.990 [0.963, 1.020] for generation rate and 1.012 [1.004, 1.019] for answer time. On this host (Docker Desktop on WSL2), NIM selects its FP8 profile when nothing is set, and both engines' default model runner fails with `UVA is not available`. The 7.3× of the March 2026 Vol.1 belongs to that configuration: two engines, two precisions, one arm largely outside GPU memory (`../vol3-judges/BASELINE.md`, section 12).

## H · Are the answers right — answer quality and the reasoning switch (`results/p78_quality/`)

GSM8K (`gsm8k_cot_llama`, all 1,319 test items, 8-shot) and MMLU (`mmlu_llama` on a fixed 50 × 57 sample, 2,850 items, 5-shot) through lm-eval 0.4.13 at temperature 0, client concurrency 16, each model with its reasoning on (`max_tokens` 8,192) and off (1,024; Nemotron 3 Nano: `chat_template_kwargs {enable_thinking: false}`; Nemotron Nano 9B v2: the system message `/no_think`). Scored on the whole output by the last "final answer is …" / "best answer is …" match; no match counts as wrong. Idle-card gate before every cell; all cells kept. The two columns are two deployment options, not one variable changed.

| | Nemotron 3 Nano · NVFP4 · NIM 2.0.12 · cap 256 | Nemotron Nano 9B v2 · bf16 · NIM 1.12.2 · seqs 32 |
|---|---|---|
| GSM8K, reasoning on (run 1 · run 2) | **95.68%** · 95.60% | **95.15%** · 94.92% |
| GSM8K, reasoning off | 90.22% | 89.46% |
| MMLU sample, reasoning on | **88.00%** | **84.04%** |
| MMLU sample, reasoning off | 75.75% | 74.84% |
| on − off, GSM8K (paired, 95% CI) | +5.46 pp [4.02, 6.90] | +5.69 pp [4.12, 7.25] |
| on − off, MMLU | **+12.25 pp** [10.78, 13.71] | **+9.19 pp** [7.71, 10.68] |
| Median completion tokens on GSM8K, off · on | 117 · 300 (39%) | 104 · 331 (31%) |
| Items at the 8,192-token cap, reasoning on | ≤ 0.67% | ≤ 0.46% |
| Run 2 − run 1, same cell (GSM8K on) | −0.08 pp [−0.93, 0.78]; 20 of 1,319 outputs byte-identical | −0.23 pp [−0.48, 0.03]; 1,120 of 1,319 |

Pre-registered predictions: the four accuracy floors pass (≥ 88% / ≥ 75% and ≥ 85% / ≥ 70%); "reasoning helps on GSM8K" passes for both; the cap share passes. **Two predictions fail for both models, and both were wrong about the model, not about the measurement.** "MMLU on − off within [−2, +6] pp": the measured gain is 9–12 points — reasoning helps on multiple choice far more than the band allowed. "Completion tokens with reasoning off ≤ 25% of on (GSM8K)": measured 31–39% — with reasoning off both models still write out worked steps (a median of 104–117 tokens) before the answer.

**Concurrency and the answer (C1), inconclusive.** Nemotron 3 Nano, reasoning off, the first 200 GSM8K items at client concurrency 1 against the same items at 16: 95.0% vs 93.0%, difference 2.0 pp [−0.39, 4.39], 29 of 200 outputs byte-identical. The pre-registered line was "within ±3 pp" and did not say how to read an interval that straddles it. The rule used — pass if the whole interval is inside, fail if the point is outside, otherwise inconclusive — **was added after the run** and is marked so in `analysis.json`; it is not a pre-registered rule.

Two things the run showed that it was not designed to measure. Nemotron 3 Nano at temperature 0 does not repeat its own text (20 of 1,319 identical between two runs of one cell) while its accuracy does repeat. And the 9B v2 container slowed down over the night: the same GSM8K cell took a median 7.6 s per item at the start and 29.6 s four hours later in the same container, with accuracy unchanged (95.15% → 94.92%); its timing figures are therefore not stationary and are not quoted.

## I · NIM against the engine it contains, on Nemotron 3 Nano (`results/p78_nim_vs_vllm/`)

Section G's question on this volume's model. Nemotron 3 Nano NVFP4, the same weight files, one session: **N3** is NIM 2.0.12 (`NIM_MAX_MODEL_LEN` 16,384); **V3B1** is `vllm/vllm-openai:v0.27.1` (the version inside the NIM) given only the snapshot path; **V3B2** is the same image started with NIM's own resolved vLLM argument list.

| | N3 (NIM) | V3B1 (upstream, bare) | V3B2 (upstream, NIM's arguments) |
|---|---|---|---|
| Arm health, single stream, tok/s | 316.8 | 311.1 | 317.9 |
| Generation rate, median over 50 questions (`max_tokens` 4096) | 292.5 | 287.5 | 295.6 |
| Chat profile, tok/s at c = 1 · 8 · 32 · 64 · 128 | 300 · 1,062 · 2,152 · 2,801 · 3,572 | 296 · 1,069 · 2,043 · 2,716 · 3,506 | 303 · 1,072 · 2,188 · 2,823 · 3,679 |
| Inside the server SLO at every level to 128 | yes (p99 TTFT 1,189 ms at 128) | yes (1,209 ms) | yes (1,057 ms) |
| GSM8K, reasoning off | 90.22% | 90.83% (+0.61 pp [−0.58, 1.80]) | 90.75% (+0.53 pp [−0.65, 1.71]) |
| Responses byte-identical to N3's, of 50 | — | 1 | 1 |
| Each arm repeating its own text, of 10 | 0 | 0 | 0 |

Pre-registered: V3B2 over N3 single-stream rate 1.01 (band [0.95, 1.05], pass); throughput ratio at every level 1.01–1.03 (band [0.90, 1.10], pass). The byte-identity prediction (≥ 45 of 50) is **not interpretable**: no arm repeats its own text, so a difference between arms cannot be attributed to the engine. **What was measured is that NIM is not slower than the engine it contains, on this model and card. What was not measured is NIM choosing settings a user would otherwise get wrong:** the bare upstream arm set the same values by itself (Mamba cache dtype float32, MoE backend `FLASHINFER_CUTLASS`, CUDA graphs `FULL_AND_PIECEWISE`, attention `FLASHINFER`, KV cache `float8_e4m3fn`, read from both upstream start logs; NIM's own log at its default level prints none of them).

## J · Was the card idle — end-of-cell GPU state and the host (`results/p78_audit/`, `results/p79_host_state/`)

`results/p78_audit/` applies one fingerprint — utilization 0% and 26–42 W — to the end-of-cell GPU record of every measured cell of the P50, P53 and P55 runs above: 12 cells match, 176 do not, 23 have no such record. A cell that does not match is not shown to be wrong; it is a cell for which an idle card at its end could not be shown. `z3_audit.md` lists every cell with its record and the written number it feeds. What was done about them:

| Cells | Status |
|---|---|
| Main sweeps of `p53_concurrency_v2` (26 cells, 21 not matching) and `p55_concurrency_a2_256` (20 cells, 15 not matching) | **re-measured in P80** with an idle-card gate before every cell; both values are published (section C, `results/p80_rerun/`) |
| Single-stream rates of `p50_speed` | not re-run; cross-checked against P78's gated cells (section B) |
| Everything else: footprint, answer time, long context, the first concurrency run, caps 64 and 128, the capture control, the fresh-container repeats, the Guardrails and judge cells (no per-cell record) | not re-run; they keep the audit's label |

The P78 and P80 cells were gated before each cell (utilization ≤ 2% and ≤ 45 W over 10 s), which is a different check from the audit's end-of-cell fingerprint.

`results/p79_host_state/` is the diagnosis of the stopped re-run of 2026-09-30 morning (throughput 6–20× below the originals, utilization near 100% at 140–180 W; kept on the machine, not published). The same configuration was measured in fresh containers before a reboot (host up 7 days) and after it: 18 of 18 cells normal. The cause of the morning's state was not identified. Every one of the six container loads behind those 18 cells left one WSL `make_resident` failure and 0.367 GiB of the container's GPU allocation in system RAM, so neither signal separates a slow container from a normal one; they are recorded, not gated on, and the gate used in P80 is a speed probe against the original run's values.

## What this volume does not do

Compare the two models as if one variable changed; quote any figure from the Vol.1 non-NIM runtime; reuse Llama 3.1 8B as an arm; transfer any tok/s to another machine (only the long-context decay shape is compared with an external DGX Spark measurement); or produce a sentence of the form "serves N users" — the concurrency numbers are p99 latencies at closed-loop concurrency levels, with the SLO and its source on every row.
