# Vol.1 (renewed) · what NIM is worth on this card once several people use it at the same time (run 2026-09-25, 02:29–06:51)

**A single-user comparison cannot stand for a serving engine. This run adds the concurrent half.** Earlier single-stream measurements put Ollama's 4-bit Llama ahead of NIM's bf16 on this card. That is what a bandwidth-bound decoder does when it reads fewer bytes per token. A serving engine's advantage, if it has one, lies in serving many requests at once (continuous batching, a paged KV cache), and the Ollama side of that had never been measured. Pre-registration `prediction_p59_nim_value.json`, frozen 2026-09-25T02:29:04+0800 after two harness tests (disclosed in `harness_test_record.json` and the basis) and scanned before its sidecar was written (`prediction_scan.txt`, with a planted-control rescan); first container 02:29:39.

**Scope.** The Llama 3.1 8B profiles NIM 2.0.12 offers for an RTX 5090 are vLLM only (bf16 and fp8; no TensorRT-LLM profile). This measures NIM on this card and says nothing about data-centre GPUs. It compares speed and capacity only; answer quality is not compared. FP16 and bf16 are both 16-bit formats with different ranges, so this README calls them *comparable* precision, not the same precision.

## Setup

One RTX 5090 (32,607 MiB, 1,792 GB/s, driver 591.86), Docker Desktop on WSL2, one engine on the card at a time. Before every container: no Windows-native Ollama process (the runner stopped it before the run and started it again afterwards), ports 8000 and 11434 held only by that arm, and every endpoint on `127.0.0.1`.

| Arm | Engine · model | Settings | Bytes read per token |
|---|---|---|---|
| **O-Q4** | Ollama 0.34.4 (`ollama/ollama` `8262851b…`) · `llama3.1:8b` 4-bit (manifest `46e0c10c039e`) | context 8,192 · `OLLAMA_NUM_PARALLEL` **16**, the largest on the ladder 64 → 1 that loads 100% on GPU | 4,920,738,944 |
| **O-Q4-def** | same | context 8,192 · `OLLAMA_NUM_PARALLEL` not set: Ollama chose **1** (runner log) | 4,920,738,944 |
| **O-FP16** | same image · `llama3.1:8b-instruct-fp16` (manifest `4aacac419454`) | context 8,192 · `OLLAMA_NUM_PARALLEL` **8**, largest 100% on GPU | 16,068,895,872 |
| **N-BF16** | NIM 2.0.12 (`d2c94c1d…`) · profile `092ed421…` (vllm-bf16) | `NIM_MAX_MODEL_LEN` 8192 · `VLLM_USE_V2_MODEL_RUNNER=0` (P54's arm N) | 16,060,522,496 |
| **N-FP8** | NIM 2.0.12 · profile `c4789f7a…` (vllm-fp8, NIM's own choice on this card) | same | 9,081,280,648 |

**Ollama pre-allocates a full context for every parallel slot, so capacity is set before a single request arrives.** At context 8,192 the 4-bit model loads fully on the GPU with 16 slots. At 32 slots it spills to the CPU (27% CPU / 73% GPU). At 64 the runner sized 524,288 context tokens and was killed. At context 4,096 the same model fits 32 slots. The FP16 model fits 8 slots at 8,192 (16 slots put 9% on the CPU) and 16 at 4,096. The NIM arms use a paged KV cache and need no such ceiling: `max_num_seqs` 256.

**Load.** AIPerf 0.11.0 closed loop, levels 1, 8, 16, 32, 64, 128, 60 s each. Profiles: **C** chat (200 ± 50 in, 200 ± 50 out) and **R** RAG (3,500 ± 300 in, 500 ± 50 out), synthetic, temperature 0. The output cap is sent as `max_tokens` on every arm, because Ollama ignores `max_completion_tokens`. Token counts come from the Llama 3.1 tokenizer on the client for every arm. A fresh container repeated the two highest levels. SLOs are MLPerf Inference v5.1 Llama 3.1-8B: server p99 TTFT ≤ 2 s and p99 TPOT ≤ 100 ms; interactive 500 ms and 30 ms.

**Checks that held on every arm.**

- **Residency:** Ollama `ollama ps` showed 100% GPU; NIM captured its CUDA graphs.
- **Health:** decode rate at c=1 × bytes per token as a share of 1,792 GB/s was O-Q4 53.9%, O-Q4-def 58.1%, O-FP16 75.1%, N-BF16 79.0% and N-FP8 77.5%, all above the 40% gate. No arm ran from system memory, which is the failure behind the March 2026 Vol.1's single ratio.
- **Prefix cache:** the detector passed on all 10 containers. Its positive control fired on every one: the same prompt sent twice was served from cache.
- **Calibration** held on every arm and profile except N-FP8 on R (below).
- **No prompt was truncated** at context 8,192. On the harness's own 3,500-token requests the server counted 1.003–1.010 of the client's prompt tokens on every arm (`truncation_evidence.json`).

## Chat profile (C): the main result

Main containers. Each cell gives total tok/s · end-to-end speed per user (tok/s, queue and prefill included) · p99 TTFT (ms).

| c | O-Q4 | O-Q4-def | O-FP16 | N-BF16 | N-FP8 |
|---|---|---|---|---|---|
| 1 | 172 · 172 · 184 | 183 · 183 · 213 | 79 · 79 · 176 | 87 · 87 · 39 | 151 · 152 · 23 |
| 8 | 175 · 24 · 5,014 | 199 · 30 · 8,156 | 317 · 46 · 9,753 | 607 · 77 · 148 | 1,099 · 140 · 172 |
| 16 | 597 · 40 · 4,833 | 196 · 19 · 15,831 | 408 · 27 · 4,749 | 1,178 · 75 · 272 | 2,120 · 134 · 209 |
| 32 | 755 · 26 · 5,771 | 198 · 15 · 32,858 | 390 · 15 · 16,463 | 2,262 · 73 · 522 | 3,817 · 122 · 341 |
| 64 | 745 · 15 · 14,401 | 197 · 14 · 57,818 | 408 · 12 · 28,210 | 3,826 · 62 · 1,013 | 5,988 · 96 · 357 |
| 128 | 741 · 11 · 31,912 | 196 · 13 · 57,956 | 402 · 10 · 55,690 | 5,458 · 45 · 1,842 | 8,713 · 70 · 751 |
| **Server SLO held to** | c=1 | c=1 | c=1 | **c=128** | **c=128** |
| **Interactive SLO held to** | c=1 | c=1 | c=1 | c=16 | c=64 |

**Alone with one user, Ollama's 4-bit model generates faster; NIM answers first.** O-Q4 decodes at 196 tok/s against N-BF16's 88. N-BF16's first token comes in 39 ms against 184 ms.

**From 8 concurrent requests on, NIM leads on both total throughput and each user's speed.** At 8 requests N-BF16 serves 607 tok/s and every user sees 77 tok/s with a p99 first token of 148 ms. O-Q4 serves 175 tok/s; each user sees 24 tok/s and waits up to 5 s for a first token.

At 128 users N-BF16 still meets the server SLO (1.8 s p99 first token, 5,458 tok/s). Every Ollama arm has requests waiting 32–58 s for a first token. No Ollama arm met the server SLO beyond one user; the first-token time is what fails.

**Ollama's total throughput stops growing at its slot count.** O-Q4 reaches about 750 tok/s at 32 users and stays there. O-FP16 stays at about 400 tok/s from 16 users on. O-Q4-def, with one slot, serves about 195 tok/s at every level: one user at a time, the rest in the queue.

**Engine or precision? Comparable precision, same card:** O-FP16 and N-BF16 are close alone (79 against 87 tok/s total; 84 against 88 tok/s decode). They separate as soon as there are concurrent requests: 317 against 607 tok/s at 8, and 402 against 5,458 at 128. On this card the single-user gap between Ollama and NIM comes from precision, and the multi-user gap comes from the engine.

**NIM's own FP8 choice:** N-FP8 is ahead of N-BF16 at every level: 151 against 87 tok/s alone, 8,713 against 5,458 at 128. It keeps the interactive SLO up to 64 users instead of 16.

## RAG profile (R)

Main containers, total tok/s · end-to-end per user · p99 TTFT (ms); *es* marks a level whose median output fell below 90% of its target ("early stop"; its throughput is not compared).

| c | O-Q4 | O-Q4-def | O-FP16 | N-BF16 |
|---|---|---|---|---|
| 1 | 142 *es* · 139 · 691 | 151 *es* · 147 · 641 | 72 *es* · 72 · 757 | 81 · 81 · 388 |
| 8 | 141 · 22 · 4,331 | 159 · 32 · 21,237 | 229 · 33 · 5,070 | 393 · 52 · 2,202 |
| 16 | 297 · 23 · 8,607 | 157 · 27 · 44,390 | 218 · 18 · 22,759 | 533 · 38 · 4,470 |
| 32 | 295 · 14 · 29,104 | 153 · 26 · 56,569 | 227 · 16 · 47,457 | 555 · 23 · 18,363 |
| 64 | 300 *es* · 13 · 40,987 | 152 *es* · 22 · 56,974 | 238 · 16 · 47,385 | 568 · 17 · 38,629 |
| 128 | 295 · 13 · 50,686 | 153 · 24 · 54,450 | 240 · 16 · 49,848 | 587 · 18 · 39,361 |
| **Server SLO held to** | c=1 | c=1 | c=1 | c=1 |

With 3,500-token prompts no arm holds the server SLO beyond one user. N-BF16 still leads total throughput from 8 users (393 against 141 tok/s for O-Q4) and plateaus near 580 tok/s, where its KV cache holds about two dozen 4,000-token sequences.

**N-FP8 has no R result.** Its calibration failed the pre-registered gate: AIPerf's c=1 TTFT was 208 ms against the harness's 156 ms. Its R levels are null. The level table is in `analysis.json`: 999–1,003 tok/s at 64–128 users.

## Crossing points (pre-registered rule)

A crossing is where the sign of NIM minus the other arm changes between two consecutive usable levels. It is reported as "between X and Y", never interpolated.

| Pair · profile | Total throughput | Decode speed per user (AIPerf's per-user metric, 1 / inter-token latency) |
|---|---|---|
| N-BF16 vs O-Q4 · C | **between 1 and 8** (NIM ahead from 8) | between 1 and 8, and again between 64 and 128 (O-Q4 ahead at 128) |
| N-BF16 vs O-Q4 · R | N-BF16 ahead throughout 8–128 (c=1 excluded: O-Q4 early stop) | N-BF16 ahead throughout 8–128 |
| N-BF16 vs O-Q4-def · C | between 1 and 8 | O-Q4-def ahead throughout 1–128 |
| N-BF16 vs O-Q4-def · R | N-BF16 ahead throughout 8–128 | O-Q4-def ahead throughout 8–128 |
| N-BF16 vs O-FP16 · C | **N-BF16 ahead throughout 1–128** | between 64 and 128 (O-FP16 ahead at 128) |
| N-BF16 vs O-FP16 · R | N-BF16 ahead throughout 8–128 | between 16 and 32 (O-FP16 ahead from 32) |
| N-FP8 vs N-BF16 · C | N-FP8 ahead throughout 1–128 | N-FP8 ahead throughout 1–128 |
| N-FP8 vs N-BF16 · R | null (N-FP8 calibration) | null |

**Read the per-user column with its definition.** AIPerf's per-user metric is 1 / inter-token latency. It counts decode speed once a request is being generated and leaves out any time spent waiting in a queue. An Ollama arm with fewer slots than users queues the rest, and the requests it is serving decode at single-slot speed. So O-Q4-def, one slot, "leads" per user at every level while its p99 first token is 58 s. The end-to-end per-user speed in the tables above counts output tokens over the whole request, waiting included (post-run, `e2e_per_user.json`; disclosed below). By that measure N-BF16 is ahead of O-Q4, O-Q4-def and O-FP16 on C from 8 users on, at every level.

## Pre-registered predictions

**R1** at c=1 on C, O-Q4 ahead of N-BF16 per user, O-Q4 ≥ 200 tok/s and N-BF16 ≤ 110: **failed on the threshold**. O-Q4 was ahead, but at 196 tok/s; N-BF16 88. **R2** total-throughput crossing at or below 8 users on C: held (between 1 and 8). **R3** O-Q4's total stops growing around 32 users: held (755 at 32, 741 at 128). **R4** O-FP16 and N-BF16 within 20% at c=1: held (84 and 88 decode). **R5** N-FP8 decode 130–190 tok/s: held (153). **R6** O-Q4 16 slots at 8,192 and 32 at 4,096: held. **R7** O-Q4-def chooses 4 slots: **failed** (1). **R8** O-FP16 8 or 4 slots: held (8). **R9** every arm passes both gates: held. **R10** both NIM arms keep the server SLO on C through at least 64 users, no Ollama arm beyond its slot count: held; the Ollama arms lost it at 8 users, below their slot counts.

## What is not settled

- **O-Q4 at c=8 did not gain on c=1, on both profiles:** 175 against 172 tok/s on C, 141 against 142 on R, then 597 and 297 at 16. It has 16 slots, and O-FP16 with 8 slots did gain at c=8. This is observed, not explained.
- **Fresh containers agree with main within about 10%.** The largest gap is O-FP16 on C: 365 and 356 against 408 and 402 tok/s.
- **N-FP8's R calibration failure is unexplained.** N-BF16 in the same harness passed on R (322 against 298 ms).

## Written after the run (disclosed; the frozen analysis is unchanged)

- `events_public.jsonl` is published in place of `events.jsonl`. On Windows, the isolation check's `nvidia-smi` process list includes every desktop program that holds a GPU context, with personal paths, so that field is replaced by counts: 37 processes listed, none with a memory figure, no inference engine among them. The frozen analyser run on `events_public.jsonl` reproduces `analysis.json` byte for byte (`p59_postrun.py` checks it).
- `e2e_per_user.json`: the end-to-end per-user speed above.
- `truncation_evidence.json`: AIPerf did not request usage (no `--use-server-token-count`), so the per-level truncation check had no server count to read on any arm, and every level carries "truncation unverified". The calibration requests did carry usage; they are the evidence for "no truncation".

## Files

`prediction_p59_nim_value.json` + `.sha256` + `prediction_scan.txt` · `harness_test_record.json` · `levels.jsonl` · `events_public.jsonl` · `analysis.json` · `e2e_per_user.json` · `truncation_evidence.json` · `<arm>_<profile>_<container>/c<N>/profile_export_aiperf.json` (and `server_metrics_export.json` on the NIM arms; paths de-identified, see `deidentification_ledger.json`) · `versions.txt` · `ctx.txt`. Harness `../../scripts/p59_nim_value.py`, analysis `../../scripts/p59_analyze.py`, post-run files `../../scripts/p59_postrun.py`, runner `../../scripts/run_p59.sh`. Not published: `events.jsonl` (the raw process list), `logs/`, `harness_test/`, AIPerf's per-request exports and inputs, the console output.
