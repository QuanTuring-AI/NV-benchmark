# Vol.3 · time to a complete answer: the speed run at `max_tokens 4096` (run 2026-09-23)

**Why this run exists.** `../p50_speed/` measured generation rate with Vol.1's `max_tokens 500`, and 79 of its 100 completions were cut at that cap because both models reason by default. A generation-rate ratio says nothing about how long an answer takes when the model writes until it stops. This run repeats the speed design with `max_tokens 4096` and records, per question, the total time, the engine's completion tokens, whether the completion was truncated, and whether a reasoning channel is exposed. Pre-registration `prediction_p53_answer.json`, frozen 2026-09-23T00:30:40+0800, first request 00:36:34 (`.sha256` beside it).

**What is compared.** The same two deployment options as the speed run: **A1** Nemotron Nano 9B v2, bf16, NIM 1.12.2; **A2** Nemotron 3 Nano (30B total, 3.5B active per token), NVFP4, NIM 2.0.12. Architecture, precision and NIM version all differ; no common NIM version exists (`../p50_availability/`). **This is not a single-variable comparison.**

**Design.** Identical to `../p50_speed/` except where stated: four alternating container blocks A1, A2, A1, A2 over the 50-question Vol.2 co-residence sample in fixed order (`../../../vol3-judges/results/p20_coresidence/sample.json`, SHA-256 checked); one discarded 16-token request after READY; one request per question, 2 s apart; Vol.1's payload plus temperature 0.0, top_p 0.9, streaming with usage; no system prompt. **Changed from the speed run:** `max_tokens 4096`, request timeout 900 s, and the containers run at `NIM_MAX_MODEL_LEN 8192` (at the footprint run's 4096 every request with `max_tokens 4096` was refused with HTTP 400 in the harness test, since prompt plus `max_tokens` must fit the model length). Per row the harness also records any `reasoning_content` delta, any `<think>…</think>` span in `content`, and the time to the first answer token after reasoning. Measured requests 00:36–01:20 (+0800); GPU at 273 MiB after the last container stopped; one container up at every request (checked per row). Free model output is not stored: per row `response_sha256` and `response_chars` only.

**All preconditions held**: 0 errors in 100 requests, engine usage present on every row, every row's served model is its arm's, 50 rows per arm, one per question, blocks alternating.

## Arm health before any ratio (pre-registered gate, same as the speed run)

| Arm | Generation rate, median (tok/s) | Bytes read per token | Effective bandwidth | Share of 1,792 GB/s | Gate (≥ 10%) |
|---|---|---|---|---|---|
| A1 · dense bf16 | 71.1 | 17,776,454,656 | 1,264 GB/s | **70.5%** | pass |
| A2 · MoE NVFP4 | 298.9 | 3,590,938,272 | 1,074 GB/s | **59.9%** | pass |

## Result

Every row: model · precision · NIM version · `max_num_seqs` · `max_tokens 4096` · `NIM_MAX_MODEL_LEN 8192`.

| | A1 · Nemotron Nano 9B v2 · bf16 · NIM 1.12.2 · `max_num_seqs` 32 | A2 · Nemotron 3 Nano · NVFP4 · NIM 2.0.12 · `max_num_seqs` 256 (image default) |
|---|---|---|
| **Total time to the end of the answer, avg / p50 / p95 / min–max (ms)** | **19,814 / 20,102 / 39,185 / 2,294–47,235** | **6,796 / 7,314 / 13,736 / 279–13,832** |
| **Completion tokens, avg / p50 / p95 / min–max** | **1,405 / 1,421 / 2,779 / 155–3,378** | **2,017 / 2,145 / 4,096 / 51–4,096** |
| `finish_reason` | stop 50 · length 0 | stop 44 · **length 6** |
| Generation rate, avg / p50 / min–max (tok/s) | 71.0 / 71.1 / 67.7–72.4 | 294.5 / 298.9 / 226.1–306.5 |
| tps, engine tokens over total latency, avg / p50 | 70.5 / 70.8 | 287.2 / 296.7 |
| TTFT, avg / p50 / p95 / max (ms) | 66.1 / 60.9 / 75.9 / 272.2 | 42.7 / 37.8 / 60.2 / 62.5 |
| Prompt tokens, avg | 36.5 | 40.5 |
| Reasoning channel exposed (`reasoning_content` field or `<think>` markers) | **none** (0 of 50 rows) | **none** (0 of 50 rows) |
| Empty answers | 0 | 0 |
| By block, generation p50 · TTFT p50 | 71.3 · 62.0 (block 0) · 70.9 · 60.5 (block 2) | 297.5 · 41.4 (block 1) · 299.3 · 33.3 (block 3) |
| Container: seconds to READY · memory at READY | 235 / 278 s · 29,413 / 28,691 MiB | 389 / 389 s · 31,679 / 31,606 MiB |
| KV cache at READY (engine record) | 382,976 tokens (startup log) | 3,061,008 tokens = 733 blocks × 4,176, `cache_dtype fp8_e4m3`, `gpu_memory_utilization 0.92` (`/metrics`) |

**A2 / A1, ratio of means over the 50 questions, 95% bootstrap CI over questions, median per-question ratio:**

| Quantity | Ratio | CI | Median | Reads as |
|---|---|---|---|---|
| Generation rate | 4.15 | [4.09, 4.20] | 4.20 | the speed run's 4.14, reproduced |
| **Total time to the end of the answer** | **0.343** | **[0.307, 0.377]** | 0.309 | **A2 finishes the same question in about one third of A1's wall-clock time (≈ 2.9× faster), not 4.15×** |
| Completion tokens | 1.44 | [1.28, 1.58] | 1.30 | A2 writes about 44% more tokens per question (mean); 30% at the median |
| tps (engine tokens / total) | 4.07 | [3.98, 4.14] | 4.17 | |
| TTFT | 0.65 | [0.54, 0.77] | 0.70 | |

Six A2 completions hit the 4,096 cap, so A2's token count and total time are **lower bounds** on those six questions, and the total-time ratio 0.343 is a lower bound on the true ratio (had those six run to their end, A2's advantage would be smaller, not larger). No A1 completion was cut.

**Pre-registered predictions.** **R1** A2/A1 total time between 0.35 and 0.80 — **failed**: 0.343, below the interval by 0.007; the CI straddles 0.35 and the result is reported as failed because the point estimate is outside. **R2** A2/A1 completion tokens between 1.1 and 2.5 — held (1.44). **R3** truncation at 4096 below 10% on both arms — **failed on A2** (6 of 50 = 12%; A1 0 of 50). **R4** a reasoning channel exposed as a separate field on at least one arm — **failed**, as the pre-registration's basis said it would: neither image returns `reasoning_content`, and no `<think>` marker appears in `content` on any of the 100 rows. The reasoning is inline in what the client receives.

## Reading

The speed run's 4.14× is a per-token rate. Per *answer*, A2 is about 2.9× faster on this sample (p50 7.3 s against 20.1 s), because it writes more tokens before it stops — 1.44× as many on average — and because six of its answers did not stop at all within 4,096 tokens. The external observation quoted in the pre-registration (that Nemotron 3 Nano's speed advantage is partly spent on longer reasoning) has the same shape here, on a different comparison model. Both numbers belong on the same table; neither replaces the other.

What could not be measured: the split between reasoning and answer. Both images stream the whole generation as `content`, with no field and no marker separating the two, so "time to the first answer token" has no defined value on either arm. This run does not install a parser or change the image to obtain one; it reports the totals and says so. A reader who needs the split needs a request shape or an image that exposes it.

TTFT here is client-side (the `requests` library, `iter_lines`), which on this host reads 10–20 ms above AIPerf's first-chunk time for the same server (`../p53_concurrency/README.md`, calibration); the figures are comparable with the speed run's, which used the same client, and not with the concurrency run's.

A2's first request after READY runs below its steady rate (264 and 301 tok/s for the first question of blocks 1 and 3 against block medians of 297 and 299; the long-context run documents the transient); one long answer is enough to pass it, so the medians and the ratio of means are not affected beyond 1%.

## Engine environment

As `../p50_speed/README.md` (same images, profiles and settings) except `NIM_MAX_MODEL_LEN 8192` and `max_tokens 4096`; A2's KV cache dtype `fp8_e4m3` is recorded there and here from `/metrics`. Startup logs for the four containers are in `logs/` (not published).

## Files

`prediction_p53_answer.json` + `.sha256` · `requests.jsonl` (100 rows; response digests and lengths, no text) · `events.jsonl` (block starts with image, profile, env, GPU and cache records) · `analysis.json` · `ctx.txt`. Harness `../../scripts/p53_answer.py` (imports the speed and footprint harnesses), analysis `../../scripts/p53_answer_analyze.py`, runner `../../scripts/run_p53_answer.sh`; their SHA-256 are in the pre-registration. `harness_test/`, `logs/` and the console output (`console.txt`) are not published.
