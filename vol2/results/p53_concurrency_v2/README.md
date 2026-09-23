# Vol.2 · concurrency, second run: closed-loop AIPerf sweeps on both Nemotron NIMs with the repaired instrument gate (run 2026-09-23, 07:51–10:04)

**What this is.** The first run (`../p53_concurrency/`) produced valid level tables but no conclusions: its calibration gate compared a warming engine with a warm one and one prompt length with another, and its "all levels clean" rule could not survive A1's engine crash. This run repeats the same sweeps — same images, profiles, `NIM_MAX_MODEL_LEN` 8192, `max_num_seqs` 32 on both arms, levels 1–64, AIPerf 0.11.0 flags, fresh-container repeat of the two highest levels, all imported from the first run's harness, which is not modified — with four changes, each from a first-run observation and each written into the pre-registration before this run: a discarded 120 s closed-loop level at c=1 before the calibration; a calibration prompt of the profile's length, sent back to back; engine death recorded as the ceiling with the levels below it standing and the levels above skipped; container logs saved before removal. The calibration gate: AIPerf's c=1 TTFT and ITL medians within 20% of the harness's own client (TTFT alternatively within 20 ms), a floor raised from the first run's 15 ms after three harness tests, as the pre-registration states. Pre-registration `prediction_p53_concurrency_v2.json`, frozen 2026-09-23T07:06:20+0800, first measured level 08:01 (`.sha256` beside it). The predictions in it were written from the first run's numbers and say so.

Every row: **A1** Nemotron Nano 9B v2 · bf16 · NIM 1.12.2 (vLLM V0 0.10.0) · `max_num_seqs` 32 · `max_tokens` = profile OSL; **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 (vLLM 0.27.1) · `max_num_seqs` 32 · `max_tokens` = profile OSL. Profiles: **C** ISL 200±50 / OSL 200±50, **R** 3,500±300 / 500±50, synthetic, `ignore_eos`, temperature 0. SLOs fixed before any number: MLPerf Inference v5.1 Llama 3.1-8B **server** (p99 TTFT ≤ 2,000 ms ∧ p99 TPOT ≤ 100 ms) and **interactive** (500 ms ∧ 30 ms) — another model's limits, applied to both arms identically. Not a single-variable comparison.

## Preconditions and the instrument gate

| Sweep | P1 levels clean below the ceiling | P2 calibration: own client vs AIPerf c=1 (medians) | P3 | Conclusions |
|---|---|---|---|---|
| A1 · C · main | ✅ 1–16 clean; engine crash at 32; 64 skipped | ✅ TTFT 49.8 vs 49.4 ms (0.7%) · ITL 13.38 vs 13.26 (0.9%) · prompt 205 tokens | ✅ | computed |
| A1 · C · fresh | ❌ its only level (32) crashed: no live level | ✅ (main's) | ✅ | **null** (by rule: at least one clean level) |
| A1 · R · main | ✅ 1–16 clean; crash at 32; 64 skipped | ✅ TTFT 320.6 vs 318.9 ms (0.5%) · ITL 13.48 vs 13.12 (2.7%) · prompt 3,295 tokens | ✅ | computed |
| A1 · R · fresh | ✅ 32 clean; crash at 64 | ✅ (main's) | ✅ | computed |
| A2 · C · main | ✅ 1–64 clean | ✅ TTFT 85.3 vs 71.5 ms (16%, 13.8 ms) · ITL 3.18 vs 3.13 (1.6%) · prompt 209 | ✅ | computed |
| A2 · C · fresh | ✅ | ✅ (main's) | ✅ | computed |
| A2 · R · main | ✅ 1–64 clean | ✅ TTFT 156.7 vs 144.1 ms (8%) · ITL 3.18 vs 3.14 (1.2%) · prompt 3,299 | ✅ | computed |
| A2 · R · fresh | ✅ | ✅ (main's) | ✅ | computed |

With the calibration after a 120 s warm-up level and back to back, the two clients agree on ITL within 1–3% on every sweep and on TTFT within 1% on A1 (both profiles); on A2 the own client reads 12–14 ms above AIPerf. The first run's 25% ITL gap on A2 was the engine's first minute, not the instrument.

## Conclusions (per sweep, from the analysis)

| Arm · profile | Largest c inside the **server** SLO | Largest c inside the **interactive** SLO | Throughput saturation | Ceiling |
|---|---|---|---|---|
| **A1 · C** | **16** | **16** | not reached before the crash | **engine crash at c=32** (main; fresh container crashed at 32 too) |
| **A1 · R** | **4** | **1** | not reached before the crash | **engine crash at c=32** (server SLO already failed at 8); the fresh container survived c=32 (417 tok/s, p99 TTFT 14.7 s, p99 ITL 67.7 ms) and crashed at 64 |
| **A2 · C** | **32** | **32** | **32** (1,540 → 1,490 tok/s) | reached at c=64 (queueing: p99 TTFT 4.6 s, ITL unchanged) |
| **A2 · R** | **8** | **4** | **32** (1,462 → 1,464) | reached at c=16 (p99 TTFT 2.1 s) |

These are p99 latencies at closed-loop concurrency levels under a stated SLO. They are not a number of users.

## Level tables (AIPerf summaries; TTFT and ITL in ms; ITL = (e2e − TTFT)/(tokens − 1); throughput in output tokens/s)

**A1 · profile C** (ISL/OSL measured 201–232 / 186–210)

| c | completed | TTFT p50 / p90 / p99 | ITL p50 / p99 | tok/s | container |
|---|---|---|---|---|---|
| 1 | 23 | 49.4 / 63.8 / 69.5 | 13.26 / 13.57 | 74.0 | main |
| 2 | 45 | 55.8 / 66.2 / 75.0 | 13.29 / 13.89 | 145.6 | main |
| 4 | 77 | 58.3 / 74.6 / 120.4 | 14.24 / 14.80 | 271.3 | main |
| 8 | 138 | 56.9 / 80.2 / 334.5 | 16.33 / 17.16 | 466.4 | main |
| 16 | 250 | 57.2 / 85.1 / 434.1 | 19.69 / 20.63 | 776.9 | main |
| 32 | — | **engine died** during warm-up (main and fresh) | | | |

**A1 · profile R** (ISL/OSL 3,462–3,598 / 486–509)

| c | completed | TTFT p50 / p90 / p99 | ITL p50 / p99 | tok/s | container |
|---|---|---|---|---|---|
| 1 | 8 | 318.9 / 346.6 / 350.3 | 13.12 / 13.19 | 72.6 | main |
| 2 | 16 | 333.9 / 400.8 / 630.6 | 13.54 / 13.91 | 136.5 | main |
| 4 | 28 | 343.6 / 811.4 / 1,415.1 | 15.67 / 16.21 | 234.1 | main |
| 8 | 58 | 351.1 / 836.0 / 2,507.1 | 19.60 / 20.85 | 365.2 | main |
| 16 | 110 | 426.7 / 2,003.6 / 5,434.3 | 28.01 / 33.39 | 513.6 | main |
| 32 | — | **engine died** | | | main |
| 32 | 51 | 5,045.6 / 13,380.0 / 14,714.7 | 50.94 / 67.73 | 417.5 | fresh |
| 64 | — | **engine died** | | | fresh |

**A2 · profile C** (ISL/OSL 210–232 / 186–208)

| c | completed | TTFT p50 / p90 / p99 | ITL p50 / p99 | tok/s | container |
|---|---|---|---|---|---|
| 1 | 86 | 71.5 / 76.9 / 94.4 | 3.13 / 3.23 | 285.3 | main |
| 2 | 128 | 82.0 / 95.5 / 144.7 | 4.29 / 4.75 | 422.2 | main |
| 4 | 184 | 84.6 / 112.0 / 157.1 | 5.75 / 6.60 | 639.7 | main |
| 8 | 260 | 90.2 / 155.1 / 174.4 | 8.51 / 9.61 | 877.1 | main |
| 16 | 366 | 98.1 / 174.3 / 223.8 | 13.26 / 15.11 | 1,134.5 | main |
| 32 | 464 | 116.3 / 191.6 / 378.7 | 19.40 / 22.18 | **1,540.0** | main |
| 64 | 470 | 4,037.5 / 4,269.0 / 4,606.8 | 20.42 / 22.41 | 1,490.0 | main |
| 32 | 461 | 114.1 / 198.6 / 381.7 | 19.55 / 22.95 | 1,527.1 | fresh |
| 64 | 468 | 4,088.5 / 4,376.0 / 4,603.6 | 20.56 / 22.93 | 1,485.3 | fresh |

**A2 · profile R** (ISL/OSL 3,421–3,616 / 487–511)

| c | completed | TTFT p50 / p90 / p99 | ITL p50 / p99 | tok/s | container |
|---|---|---|---|---|---|
| 1 | 34 | 144.1 / 163.6 / 234.5 | 3.14 / 3.16 | 288.9 | main |
| 2 | 52 | 163.0 / 223.1 / 327.2 | 4.26 / 4.58 | 429.7 | main |
| 4 | 76 | 165.1 / 236.9 / 491.7 | 5.69 / 6.01 | 654.6 | main |
| 8 | 103 | 182.1 / 301.5 / 1,003.1 | 8.37 / 9.00 | 883.5 | main |
| 16 | 141 | 248.5 / 474.3 / 2,097.2 | 12.65 / 14.77 | 1,150.3 | main |
| 32 | 188 | 260.9 / 2,154.5 / 4,520.8 | 19.33 / 21.62 | 1,461.5 | main |
| 64 | 337 | 10,253.8 / 10,952.9 / 14,454.5 | 20.15 / 23.15 | 1,464.3 | main |
| 32 | 169 | 266.3 / 2,262.5 / 4,246.9 | 19.48 / 23.31 | 1,410.0 | fresh |
| 64 | 354 | 10,184.4 / 10,790.1 / 14,166.0 | 19.93 / 22.10 | 1,488.1 | fresh |

Level durations: 60 s at c ≤ 8 on both arms; sized from the previous level's p99 latency above that (A1 R c=16 105 s; A2 R c=64 113–117 s; the A1 R fresh c=64 attempt ran 336 s against a dead engine before the harness checked it). Fresh-container repeats sit within 0.3–3.5% of the main sweep's throughput at every A2 level. Containers (seconds to READY · memory at READY): A1 272–294 s · 28,606–30,065 MiB; A2 422–474 s · 30,535–30,735 MiB; A2's KV cache `fp8_e4m3`, 749–760 blocks × 4,176 tokens. The discarded warm-up levels measured 73.6–75.1 tok/s on A1 and 237.8–283.8 on A2 (the A2 figure is the first two minutes after READY and includes its slow phase).

## Reading

**A1 (NIM 1.12.2, vLLM V0) ends at concurrency 32 by dying, on both profiles, in three of four containers; the fourth died at 64.** The traceback is the first run's (`../p53_concurrency/README.md`: `constant_size_cache._assign_seq_id_to_cache_index → free_cache_indices.pop()`, the Mamba state cache with one slot per `max_num_seqs`), now saved from every container by the harness (`logs/`, not published). Below the crash A1 is well inside both SLOs on the chat profile through c=16 (p99 TTFT 434 ms, p99 ITL 20.6 ms, 777 tok/s) — its usable range on this image is bounded by the crash, not by latency. On the RAG profile the server SLO fails at c=8 on TTFT (2.5 s: 3,500-token prefills queueing behind each other on a V0 engine without chunked prefill at this model length) and the interactive SLO at c=2 (631 ms); the crash at 32 comes after the SLOs are already gone.

**A2 (NIM 2.0.12, vLLM 0.27.1) queues instead of dying.** On the chat profile both SLOs hold through c=32 = `max_num_seqs` (p99 TTFT 379 ms, p99 ITL 22.2 ms, 1,540 tok/s) and c=64 fails only on TTFT (4.6 s) with ITL unchanged: requests beyond 32 wait, they are not served slower. Throughput saturates at 32 (1,540 → 1,490). On the RAG profile the server SLO holds through c=8 (p99 TTFT 1.0 s), the interactive SLO through c=4 (492 ms), and p99 ITL stays below 24 ms at every level up to 64: with 3,500-token prompts the binding quantity is prefill queueing, not decode. Throughput saturates at 32 here too (1,462 → 1,464).

**Against the first run**, whose A2 sweeps ran with the engine partly in its first-minute state: A2 C at c=32 measured 1,323 tok/s there and 1,540 here (+16%); c=1 265 → 285. The level tables of the first run are therefore lower bounds for A2, and this run's are the numbers of record.

**Pre-registered predictions.** **R1** A1 dies at c=32 on both profiles (main) — held. **R2** A2 C: server 32, interactive 32, saturation 32, c=64 fails on TTFT — held. **R3** A2 R: server 8, interactive 2 — **failed on the interactive half**: 4 (c=4 p99 TTFT 492 ms, 8 ms under the limit). **R4** the gate passes on all four main sweeps — held. **R5** fresh within 25% of main on throughput where both ran — held (A2: 0.8%, 0.3%, 3.5%, 1.6%; on A1 no level ran in both containers). **R6** A1 C interactive through c=8 and server through c=16 — **failed on the interactive half**: interactive through 16 as well (the prediction was too low).

## What this block does not say

It does not say how many people either deployment serves; closed-loop concurrency is a number of simultaneously open requests with no think time, and the SLOs are another model's MLPerf limits used as fixed rulers. It does not compare the two arms as if one variable changed. A1's crash is a property of this NIM version's engine build for this model at this `max_num_seqs`; whether a larger `max_num_seqs` (more Mamba state, less KV) moves the crash was not tested.

## De-identified fields in the AIPerf outputs

As Vol.1-B did (`../../../vol1b/results/p17_concurrency/README.md`), the local user-home prefix that AIPerf records in its outputs — the tokenizer path in `profile_export_aiperf.json` and `server_metrics_export.json`, `run_info.cli_command`, and each entry of the `command` list in `levels.jsonl` — is replaced by `<HOME>` before publication; no other byte changes. `deidentification_ledger.json` lists every file with the SHA-256 of the original and of the de-identified content (60 files, 237 replacements); the originals are kept outside the repository. `analysis.json` does not read any of the replaced fields and recomputes identically from the published files. AIPerf's per-level console output (`c<N>_console.txt`), per-request exports and its own logs, and the run's console output (`console.txt`), are not published.

## Files

`prediction_p53_concurrency_v2.json` + `.sha256` · `deidentification_ledger.json` · `levels.jsonl` (warm-up levels marked, engine-death levels marked, skipped levels recorded) · `events.jsonl` (container starts with env, GPU, cache, warm-up summary and calibration; ends with the log record) · `analysis.json` · `versions.txt` · `ctx.txt` · `<arm>_<profile>_<container>/c<N>/profile_export_aiperf.json` and `warmup/c0001/…` (AIPerf summaries; per-request exports and AIPerf logs are not published). Harness `../../scripts/p53_concurrency_v2.py` (imports the first run's), analysis `../../scripts/p53_concurrency_v2_analyze.py` (16 self-test cases), runner `../../scripts/run_p53_concurrency_v2.sh`; SHA-256 in the pre-registration. `harness_test/` (three tests) and `logs/` (harness stderr, trimmed container logs with the crash tracebacks) are not published.
