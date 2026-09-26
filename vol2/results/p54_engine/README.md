# Vol.1-A revisit · NIM 2.0.12 and upstream vLLM 0.27.1 on the same Llama 3.1 8B bf16 weights (run 2026-09-24, 00:13–05:05)

**Question.** NIM 2.0.12 contains vLLM 0.27.1 (same build commit, same torch, CUDA, flashinfer, triton and transformers; `stack.json`). What does NIM's pre-selected configuration amount to, set against the same engine started by hand, on one card, one model, one set of weight files and one precision? Items: **A** single stream (generation rate, time to first token, time to a complete answer) and concurrency within the SLOs of `../p53_concurrency_v2/`; **B** how many settings each arm needs to reach a serving start. The write-up is in `../../../vol1a-revisit/README.md`. Pre-registration `prediction_p54_engine.json`, frozen 2026-09-24T00:12:58+0800 after harness tests (disclosed in `harness_test_record.json` and the basis) and scanned before its sidecar was written (`prediction_scan.txt`, with a planted-control rescan); first container 00:13:34 (the stack stage, CPU only), first GPU start 00:20:08.

**Arms.** RTX 5090, 32,607 MiB, driver 591.86, Docker Desktop on WSL2. Both arms serve the same snapshot of the NIM cache (16,060,556,376 bytes of safetensors; each file's SHA-256 recorded in `stack.json`, hashed inside a container through the same mount both arms use).

| | **N** · `nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12` (`d2c94c1d…`) | **V** · `vllm/vllm-openai:v0.27.1` (`0a51ea5b…`) |
|---|---|---|
| Settings | `NIM_MODEL_PROFILE` 092ed421… (bf16) · `NIM_MAX_MODEL_LEN` 8192 · `VLLM_USE_V2_MODEL_RUNNER=0` | NIM's own vLLM argument list for N's settings (`nim-serve --dry-run`): `--tensor-parallel-size 1 --pipeline-parallel-size 1 --gpu-memory-utilization 0.92 --max-model-len 8192 --served-model-name meta/llama-3.1-8b-instruct` · `VLLM_USE_V2_MODEL_RUNNER=0` |
| Edits to NIM's list for V | — | model path (NIM workspace → the snapshot); `--port 8001` and `--host 127.0.0.1` dropped; two `--middleware nim_llm.*` entries dropped (NIM server-layer modules, absent from the upstream image) |
| `max_num_seqs` | 256 (vLLM's default for a card under 70 GiB; not set on either arm; 35 decode graph sizes captured on every start) | 256 (same) |
| KV cache at READY | **97,328** tokens (6,083 blocks) | **107,728** tokens (6,733 blocks) |
| Memory at READY | 29,829–30,106 MiB | 31,080–31,454 MiB |

**Not aligned, and why** (all listed in the pre-registration): N answers through NIM's nginx proxy, V directly; NIM loads four vLLM plugins and two ASGI middlewares that V does not; the OS base (Ubuntu 24.04 / 22.04) and Python patch level differ, as does NCCL (unused on one GPU); V is given a persistent cache directory like the one NIM keeps in its mount, and never reports usage statistics. **KV cache size** is decided by each engine's memory profiling at start, not by a setting. V's log shows a smaller non-torch and activation footprint than its own cold-cache start, which also came to 97,328 tokens. N's log does not print these lines at NIM's log level. Neither arm was adjusted toward the other.

## A · Single stream (`single/`)

Four alternating blocks, N, V, N, V, on the 50 questions of the Vol.1-B sample (positions 0–24, then 25–49). p53_answer's request: `max_tokens` 4096, temperature 0, top_p 0.9, streaming with usage, 2 s between requests. Per block: a discarded "Hello" and three discarded questions. 00:40–01:06. **All preconditions held** (no errors, the served model of each block, 50 rows per arm alternating, one container up and it is the block's own, the six labels on every row).

| | N | V | V over N, ratio of means [95% CI over questions] |
|---|---|---|---|
| **Arm health**: median generation rate × 16,060,522,496 bytes per token | 98.4 tok/s · 1,580 GB/s · **88.2%** of 1,792 | 98.2 tok/s · 1,578 GB/s · **88.0%** | gate passes on both |
| Generation rate, median | 98.4 | 98.2 | 0.990 [0.963, 1.020] |
| Time to first token, median | 31.4 ms | 31.7 ms | 0.992 [0.881, 1.124] |
| Time to the end of the answer, median | 5,066 ms | 5,053 ms | 1.012 [1.004, 1.019] |
| Completion tokens, median (one row cut at 4,096 on each arm, the same question) | 483.5 | 483.5 | 1.000 |
| Responses byte-identical (SHA-256 of the streamed text) | | | **50 / 50** |

## A · Concurrency (`conc/`)

`p53_concurrency_v2`'s harness, profiles and SLOs, imported unchanged. MLPerf Llama 3.1-8B server: p99 TTFT ≤ 2 s and p99 TPOT ≤ 100 ms; interactive: 500 ms and 30 ms. Levels 1 … 512 (twice the cap). Order: C main N, C main V, R main N, R main V, then fresh containers for the two highest levels in the same order. 01:12–05:05.

**Profile C (chat, 200/200): all preconditions held on all four sweeps.**

| | Largest c inside the server SLO | inside the interactive SLO | Output tok/s: c=128 · peak | What stops admission at the top |
|---|---|---|---|---|
| N | **256** (p99 TTFT 1,752 ms, TPOT 39.5 ms) | **32** | 6,068 · 6,257 | the cap: 256 running, KV 60% |
| V | **256** (1,808 ms, 41.3 ms) | **32** | 5,857 · 6,056 | the cap: 256 running, KV 54% |

In the main sweeps V's throughput ran 3–5% below N's from c=32 upward. The fresh containers agree within 0.2% at c=256 and 512 (N 6,110 · 6,306; V 6,104 · 6,321). So the main-sweep gap is container to container, not engine to engine.

**Profile R (RAG, 3,500/500): conclusions are null under the frozen rules**, and the level tables are published. Two preconditions failed:

- **N, P2 (instrument calibration).** AIPerf's c=1 TTFT was 284.7 ms; the harness's own calibration measured 39.4 ms. The calibration prompt is one repeated sentence with a counter at its end. After its first request (405–421 ms, cold), every calibration request found the prompt in vLLM's prefix cache and paid ~30 ms. **The calibration measured cache hits, not prefill.** This defect is in the imported harness. It did not bind in the earlier runs with Nemotron: on Nemotron 3 Nano's R sweeps, calibration and AIPerf agreed within 4% at 140–162 ms (`../p55_concurrency_a2_*/`), which a cache hit on one side would have broken.
- **V main, P1.** One request of 955 at c=256 ended with `ServerDisconnectedError`; the engine stayed up. V's calibration "passed" (27.5 vs 28.0 ms) only because AIPerf's c=1 level hit the cache too. The warm-up level and the c=1 level draw the same prompts (both seeded with 20260921 + 1), and V's larger KV cache still held them. That pass is not evidence.

What the R tables show without a conclusion: both arms run out of KV blocks at 26–39 running sequences, with preemptions. A ~4,000-token sequence needs about 4,000 of the 97–108 thousand KV tokens. At the KV-bound levels (c ≥ 64) V's throughput is 7–8% above N's (e.g. c=128: 798 against 746 tok/s), about what its 10.7% larger KV cache allows.

## B · Starts (`attempts.jsonl`, `attempts_summary.json`)

NIM's own dry-run with nothing set selects profile `c4789f7a…` (`vllm-fp8-tp1-pp1`), so every N rung carries the bf16 profile. Rungs, taken only after a failed start: nothing more → + context length 8192 → + `VLLM_USE_V2_MODEL_RUNNER=0`.

| | Rung 0 | Rung 1 | Rung 2 | Settings at the first serving start |
|---|---|---|---|---|
| N | failed, 88.5 s: `RuntimeError: UVA is not available` | failed, 88.7 s: same | **READY + probe**, 284.4 s | 3 (profile, context length, runner) |
| V | failed, 28.8 s: same error | failed, 28.6 s: same | **READY + probe**, 186.7 s | 2 (context length, runner) |

The default model runner fails on both arms at the same point. vLLM logs that it detected WSL and disabled pinned memory, which unified virtual addressing relies on. So this is most likely a property of this host (Docker Desktop on WSL2) rather than of either image. It was not tested on another host. In the measured configuration N carries 3 settings and V 6 (the runner variable and NIM's five engine options, made explicit). Seconds are recorded and not summed: the ladder was known from the harness test, so a second walk is faster than a first by construction.

## Pre-registered predictions

**R1** both arms pass the health gate at 70–95% of peak: held (88.2%, 88.0%). **R2** single-stream generation rate V over N within 0.95–1.05: held (0.990). **R3** N's median TTFT higher than V's by 0–15 ms (the proxy hop): **failed** (31.4 against 31.7 ms). **R4** answer time within 0.93–1.07 and ≥ 45 of 50 answers byte-identical: held (1.012; 50 of 50). **R5** the same server-SLO level on each profile and peak throughput within 10%: held on C (256 on both; 3.2% main, 0.2% fresh); **not evaluable on R** (conclusions null). **R6** both arms reach a serving start on the same rung with the same settings, and V's measured configuration carries 2–8 more settings: **failed in part**. Same rung (2), but N needs the profile setting V does not; V carries 3 more.

## Files

`prediction_p54_engine.json` + `.sha256` + `prediction_scan.txt` · `harness_test_record.json` · `stack.json` · `attempts.jsonl` · `attempts_summary.json` · `v_args.json` (NIM's resolved argument list and configuration, V's list and the edits) · `single/` (`requests.jsonl`: timings, tokens, response digests, no text; `events.jsonl`; `analysis.json`) · `conc/` (`levels.jsonl`, `events.jsonl`, `analysis.json`, per-level AIPerf summaries and vLLM gauges, paths de-identified, see `deidentification_ledger.json`) · `ctx.txt`. Harness `../../scripts/p54_engine.py`; analysis `../../scripts/p54_single_analyze.py`, `p54_conc_analyze.py`, `p54_attempts_analyze.py`; runner `../../scripts/run_p54_engine.sh`. `logs/` (startup and container logs, NIM dry-run output), `harness_test/` and the console output are not published.
