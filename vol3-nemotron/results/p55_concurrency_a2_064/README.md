# Vol.3 · A2 concurrency at an intermediate sequence cap, `max_num_seqs` 64 (run 2026-09-23, 21:08–22:23)

**Question.** The same sweep as `../p55_concurrency_a2_256/` and `../p55_concurrency_a2_128/` with the cap set to 64 (`NIM_PASSTHROUGH_ARGS "--max-num-seqs 64"`), the second intermediate state between 32 and the image default 256. Pre-registration `prediction_p55_concurrency_a2_064.json`, frozen 2026-09-23T16:27:29+0800 and scanned before its sidecar was written (`prediction_scan.txt`); first request (the warm-up level) 21:15:36.

Every row: **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 (vLLM 0.27.1) · `NIM_MAX_MODEL_LEN` 8192 · `max_num_seqs` 64 · `gpu_memory_utilization` 0.92 · KV cache fp8_e4m3, 755 blocks × 4,176 tokens (744 in the last container) · driver 591.86 · AIPerf 0.11.0 closed loop · profiles **C** (200 ± 50 / 200 ± 50) and **R** (3,500 ± 300 / 500 ± 50), `ignore_eos`, temperature 0 · levels 1 … 128 · a discarded 120 s warm-up level, then calibration · a fresh container for the two highest levels. Harness, SLOs and judgement rules as `../p53_concurrency_v2/`, imported unchanged.

All preconditions held on all four sweeps (calibration C: TTFT 73.2 vs 77.0 ms, ITL 3.17 vs 3.20 ms; R: 153.3 vs 150.4 ms, 3.32 vs 3.31 ms; running gauge never above 64). The engine did not die.

## Result

| Profile | Max concurrency, Server SLO | Max concurrency, Interactive SLO | Peak throughput | Ceiling fails on | Pool binding at the top levels |
|---|---|---|---|---|---|
| **C** 200/200 | **64** (p99 TTFT 844 ms · TPOT 48.4 ms) | **16** (TPOT 15.9 ms; 32 fails on TPOT 46.2 ms) | 1,470 tok/s at c=128 | TTFT at c=128 | **sequence cap**: 64 running, 42.4% of KV blocks in use |
| **R** 3,500/500 | **8** (p99 TTFT 1,209 ms) | **2** | 1,827 tok/s at c=128 | TTFT at c=16 | **sequence cap** (64 running), KV at 44% |

Per level, main containers (output tok/s · p99 TTFT ms · p99 TPOT ms):

| c | 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 |
|---|---|---|---|---|---|---|---|---|
| C | 283 · 95 · 3.2 | 413 · 145 · 4.9 | 635 · 175 · 6.7 | 853 · 191 · 9.9 | 1,091 · 238 · 15.9 | **1,130** · 398 · **46.2** | 1,366 · 844 · 48.4 | 1,470 · 10,433 · 45.1 |
| R | 273 · 249 · 3.4 | 407 · 296 · 4.9 | 624 · 649 · 6.4 | 876 · 1,209 · 9.2 | 1,067 · 2,186 · 15.6 | 1,379 · 4,469 · 23.7 | 1,637 · 8,848 · 39.5 | 1,827 · 24,040 · 36.8 |

Fresh containers (c=64 · c=128, tok/s): C **1,785** · 1,804 (main 1,366 · 1,470); R 1,565 · 1,809 (main 1,637 · 1,827). On R, main and fresh agree within 5%. On C, the fresh container ran **31% and 23% faster** than the main one at the same levels, with p50 TPOT 34 ms against 44 ms.

## Reading

**Cap 64 is where A2's chat-profile rate is lowest of the four caps measured.** At c=32 the main container produced 1,130 tok/s, hardly more than at c=16 (1,091), and p50 per-token time doubled from 13.8 to 28.3 ms, although the cap was not reached (32 running, KV at 21%). At the same concurrency, cap 32 gave 1,540 tok/s (`../p53_concurrency_v2/`, an earlier session), cap 128 gave 1,738 and cap 256 gave 2,238. The fresh container at cap 64 did better than the main one by 23–31% at c=64 and 128. So part of the low reading is this container's state, not the cap alone. Neither reading is chosen; both are reported.

**At cap 64 the cap binds, and the KV pool is far from full.** 64 sequences at 5 blocks each is 320 of 755 blocks, 42.4%; the gauge read 42.4% on C. The pool is larger than at cap 128 or 256 (755 against 734 and 733 blocks): the engine reserves less memory for sequences it will never hold.

**On R the server maximum is 8 at every cap measured (32, 64, 128, 256).** Long prompts queue for prefill from c=4 upward whatever the cap. Only the throughput above c=64 moves with it.

**Pre-registered predictions** (the same six statements for every cap). **R1** server maximum on C above 32: held (64). **R2** interactive maximum on C at most 64: held (16). **R3** peak throughput ≥ 2,000 tok/s at a level ≥ 64: **failed** (1,470 main; 1,804 fresh). **R4** server maximum on R 8 or 16: held (8). **R5** the pool reading never "KV blocks", and "sequence cap" at c=2N on C: held. **R6** the engine does not die: held.

No sentence of the form "serves N users" follows from this.

## Files

`prediction_p55_concurrency_a2_064.json` + `.sha256` + `prediction_scan.txt` · `levels.jsonl` · `events.jsonl` · `analysis.json` · `A2_{C,R}_{main,fresh}/` (AIPerf exports per level, paths de-identified, see `deidentification_ledger.json`) · `versions.txt` · `ctx.txt`. Harness `../../scripts/p55_concurrency_a2.py`, analysis `../../scripts/p55_concurrency_a2_analyze.py`, runner `../../scripts/run_p55_concurrency_a2.sh` (`SEQS=64`). `logs/`, `harness_test/` and the console output (`console.txt`) are not published.
