# Vol.3 · A2 concurrency at the image's own sequence cap, `max_num_seqs` 256 (run 2026-09-23, 17:46–19:43)

**Question.** In `../p53_concurrency_v2/` both arms ran at `max_num_seqs` 32 so that they shared one configuration. A1's engine dies at 32, so 32 is A1's real boundary. For A2 it is only the number we set: the Server- and Interactive-SLO maximum of 32 there is a lower bound, not A2's own ceiling. This run repeats A2's sweep with no sequence-cap override at all (the image default, 256) and asks where the ceiling lies and which pool sets it. Pre-registration `prediction_p55_concurrency_a2_256.json`, frozen 2026-09-23T16:27:29+0800 after a harness test at c=1 and 4 (disclosed in its basis) and scanned before its sidecar was written (`prediction_scan.txt`); first request (the warm-up level) 17:52:52.

Every row: **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 (vLLM 0.27.1) · `NIM_MAX_MODEL_LEN` 8192 · `max_num_seqs` 256 (image default, nothing passed) · `gpu_memory_utilization` 0.92 · KV cache fp8_e4m3, 733 blocks × 4,176 tokens · driver 591.86 · AIPerf 0.11.0 closed loop · profiles **C** (synthetic 200 ± 50 in / 200 ± 50 out) and **R** (3,500 ± 300 / 500 ± 50), `ignore_eos`, temperature 0 · levels 1, 2, 4 … 512 (one level past the cap), each ≥ 60 s and ≥ 3 × N completions · a discarded 120 s level at c=1 after READY, then the harness's own calibration · a fresh container repeating the two highest levels. Harness, SLOs and judgement rules are `../p53_concurrency_v2/`'s, imported unchanged; only the cap and the ladder differ. SLOs: MLPerf Inference v5.1 Llama 3.1-8B server (p99 TTFT ≤ 2,000 ms and p99 TPOT ≤ 100 ms) and interactive (500 ms and 30 ms).

All preconditions held on all four sweeps: every level below the top clean (0 errors), the instrument calibrated (profile C: TTFT 29.9 vs 47.5 ms, within the 20 ms floor; ITL 3.15 vs 3.16 ms · profile R: TTFT 157.7 vs 161.9 ms; ITL 3.29 vs 3.29 ms), and the engine's running gauge never above 256. The engine did not die at any level.

## Result

| Profile | Max concurrency, Server SLO | Max concurrency, Interactive SLO | Throughput at saturation | Ceiling fails on | Pool binding at the top levels |
|---|---|---|---|---|---|
| **C** 200/200 | **128** (p99 TTFT 1,054 ms · TPOT 32.6 ms) | **32** (TPOT 14.6 ms; 64 fails on TTFT 569 ms) | 3,902 tok/s at c=128 (max 3,999 at 256) | TTFT at c=256 | **KV blocks**: 146 running, 99.7% of blocks in use, the rest waiting |
| **R** 3,500/500 | **8** (p99 TTFT 1,251 ms) | **2** | 2,133 tok/s at c=128 | TTFT at c=16 | **KV blocks** from c=128 (90%); 145 running at 256 and 512, with preemptions |

Profile C, main container, per level (p99 unless marked):

| c | 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 | 512 |
|---|---|---|---|---|---|---|---|---|---|---|
| output tok/s | 300 | 465 | 733 | 1,088 | 1,543 | 2,238 | 2,991 | 3,902 | 3,999 | 3,993 |
| TTFT (ms) | 41 | 59 | 108 | 106 | 177 | 359 | 569 | 1,054 | 7,555 | 19,537 |
| TPOT (ms) | 3.2 | 4.2 | 5.5 | 7.4 | 10.4 | 14.6 | 21.7 | 32.6 | 37.4 | 37.2 |
| running max · waiting max | 1 · 0 | 2 · 0 | 4 · 0 | 8 · 0 | 16 · 0 | 32 · 0 | 64 · 25 | 128 · 75 | **146** · 223 | **146** · 447 |

Profile R, main container:

| c | 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 | 512 |
|---|---|---|---|---|---|---|---|---|---|---|
| output tok/s | 274 | 405 | 626 | 804 | 1,046 | 1,279 | 1,504 | 2,133 | 1,884 | 1,857 |
| TTFT p50 · p99 (ms) | 158 · 252 | 176 · 307 | 181 · 520 | 208 · 1,251 | 294 · 2,639 | 306 · 5,208 | 396 · 10,675 | 488 · 19,845 | 29,032 · 51,903 | 94,418 · 119,796 |
| TPOT (ms) | 3.7 | 4.9 | 6.3 | 9.8 | 16.0 | 26.0 | 42.2 | 58.2 | 74.6 | 76.4 |
| running max · waiting max · preemptions | 1 · 0 · 0 | 2 · 0 · 0 | 4 · 1 · 0 | 8 · 5 · 0 | 16 · 14 · 0 | 32 · 29 · 0 | 64 · 60 · 0 | 128 · 123 · 0 | **145** · 248 · 29 | **145** · 500 · 70 |

Fresh-container repeats (the two highest levels in a new container; the method reports both and chooses neither):

| | c=256: tok/s · p99 TTFT · p99 TPOT | c=512 |
|---|---|---|
| C main | 3,999 · 7.6 s · 37 ms | 3,993 · 19.5 s · 37 ms |
| C fresh | **981** · 39.6 s · **176 ms** | 1,357 · 73.3 s · 165 ms |
| R main | 1,884 · 51.9 s · 75 ms | 1,857 · 119.8 s · 76 ms |
| R fresh | 1,224 · 23.7 s · 71 ms | 1,980 · 113.0 s · 71 ms |

## Reading

**Raising the cap from 32 to 256 raises A2's Server-SLO maximum on the chat profile from 32 to 128.** The interactive maximum stays at 32: at c=64 the p99 time to first token passes 500 ms (569) while per-token time is still 21.7 ms. On the RAG profile the server maximum stays at 8. Long prompts queue for prefill well before any sequence or memory limit is reached, as they did at cap 32.

**Above 128 the sequence cap is not what binds; the KV block pool is.** On both profiles the engine never ran more than 145–146 sequences, with 99.7–100% of its 733 KV blocks in use and every other request waiting for capacity. That the ceiling is nearly the same for 400-token and 4,000-token sequences says the pool is counted in blocks per sequence, not in tokens. The model's config has 6 attention layers and 23 Mamba layers (its 23 MoE layers hold no cache). vLLM's hybrid cache manager groups cache layers in sixes. It padded the Mamba layers to 24 (the startup log's "Add 1 padding layers" warning), giving 1 attention group and 4 Mamba groups, 5 in all, each holding one block per sequence below 4,176 tokens. 733 / 5 = 146.6. This derivation matches the gauge; the engine does not log its group count at NIM's log level. **The "3.06 million KV tokens" the engine reports does not measure this model's capacity at this context length: about 146 concurrent sequences does.**

**Below 128 on the RAG profile the queue is not memory either.** From c=4 upward requests wait while KV use is 3–46%. The analysis labels these levels "other (scheduler)". The likely cause is the per-step prefill token budget admitting only a few 3,500-token prompts per step when a level starts. The gauges show the queue, not its cause. Median TTFT stays under 500 ms through c=128; the p99 is set by the requests that arrive together when each level starts, the closed-loop start that AIPerf uses.

**The fresh container at c=256 behaves differently from the main one.** On profile C it produced a quarter of the main container's throughput with 176 ms per token, and a TTFT five times longer. Both containers are at the same block limit (146 running). The main container reached c=256 after eight lower levels; the fresh one started there after its 120 s warm-up. High-concurrency levels depend on what the engine ran before them; both are reported and neither is chosen. At c=512 the two differ by 2.9× on C and by 7% on R.

**Pre-registered predictions.** **R1** server maximum on C above 32: held (128). **R2** interactive maximum on C at most 64: held (32). **R3** peak throughput ≥ 2,000 tok/s at a level ≥ 64: held (3,999). **R4** server maximum on R within one level of the 32-cap result: held (8). **R5** the pool reading never "KV blocks", and "sequence cap" at c=512 on C: **failed**: KV blocks bind from c=256 on C and from c=128 on R, and the cap is never reached. **R6** the engine does not die: held.

No sentence of the form "serves N users" follows from this. The numbers are p99 latencies at closed-loop concurrency levels, under an SLO set for another model, on synthetic prompts.

## Files

`prediction_p55_concurrency_a2_256.json` + `.sha256` + `prediction_scan.txt` · `levels.jsonl` (every level: command, AIPerf summary, engine check) · `events.jsonl` (per container: env, cache config at READY, warm-up level, calibration) · `analysis.json` · `A2_{C,R}_{main,fresh}/` (AIPerf exports per level, including `server_metrics_export.json` with the vLLM gauges; paths de-identified, see `deidentification_ledger.json`) · `versions.txt` · `ctx.txt`. Harness `../../scripts/p55_concurrency_a2.py` (imports `p53_concurrency_v2.py`), analysis `../../scripts/p55_concurrency_a2_analyze.py`, runner `../../scripts/run_p55_concurrency_a2.sh` (`SEQS=256`). `logs/`, `harness_test/` and the console output (`console.txt`) are not published.
