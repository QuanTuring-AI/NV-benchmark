# Vol.3 · A2 concurrency at an intermediate sequence cap, `max_num_seqs` 128 (run 2026-09-23, 19:44–21:07)

**Question.** The same sweep as `../p55_concurrency_a2_256/` with the cap set to 128 (`NIM_PASSTHROUGH_ARGS "--max-num-seqs 128"`), an intermediate state between the 32 that `../p53_concurrency_v2/` shared with A1 and the image default 256. The point is to measure the shape between those two rather than to interpolate it. Pre-registration `prediction_p55_concurrency_a2_128.json`, frozen 2026-09-23T16:27:29+0800 and scanned before its sidecar was written (`prediction_scan.txt`); first request (the warm-up level) 19:50:27.

Every row: **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 (vLLM 0.27.1) · `NIM_MAX_MODEL_LEN` 8192 · `max_num_seqs` 128 · `gpu_memory_utilization` 0.92 · KV cache fp8_e4m3, 734 blocks × 4,176 tokens · driver 591.86 · AIPerf 0.11.0 closed loop · profiles **C** (200 ± 50 / 200 ± 50) and **R** (3,500 ± 300 / 500 ± 50), `ignore_eos`, temperature 0 · levels 1 … 256 · a discarded 120 s warm-up level, then calibration · a fresh container for the two highest levels. Harness, SLOs and judgement rules as `../p53_concurrency_v2/`, imported unchanged.

All preconditions held on all four sweeps (calibration C: TTFT 32.1 vs 31.5 ms, ITL 3.15 vs 3.14 ms; R: 145.1 vs 140.2 ms, 3.16 vs 3.15 ms; running gauge never above 128). The engine did not die.

## Result

| Profile | Max concurrency, Server SLO | Max concurrency, Interactive SLO | Throughput at saturation | Ceiling fails on | Pool binding at the top levels |
|---|---|---|---|---|---|
| **C** 200/200 | **128** (p99 TTFT 1,284 ms · TPOT 48.2 ms) | **32** (TPOT 19.5 ms; 64 fails on TTFT 623 ms and TPOT 31.1 ms) | 2,679 tok/s at c=128 | TTFT at c=256 | **sequence cap**: 128 running, 87.3% of KV blocks in use |
| **R** 3,500/500 | **8** (p99 TTFT 1,002 ms) | **2** | 2,161 tok/s at c=128 (2,240 at 256) | TTFT at c=16 | **sequence cap** (128 running) with KV at 90% |

Per level, main containers (output tok/s · p99 TTFT ms · p99 TPOT ms):

| c | 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 |
|---|---|---|---|---|---|---|---|---|---|
| C | 297 · 85 · 3.2 | 458 · 90 · 4.5 | 706 · 101 · 6.0 | 1,031 · 142 · 8.3 | 1,370 · 203 · 12.1 | 1,738 · 398 · 19.5 | 2,129 · 623 · 31.1 | 2,679 · 1,284 · 48.2 | 2,568 · 10,956 · 51.9 |
| R | 289 · 187 · 3.2 | 432 · 238 · 4.6 | 653 · 551 · 6.0 | 885 · 1,002 · 8.8 | 1,154 · 2,098 · 14.7 | 1,433 · 4,285 · 22.2 | 1,749 · 8,581 · 35.3 | 2,161 · 17,484 · 55.8 | 2,240 · 43,018 · 56.3 |

Fresh containers (c=128 · c=256, tok/s): C 2,688 · 2,587 (main 2,679 · 2,568); R 1,567 · 2,205 (main 2,161 · 2,240). On C, main and fresh agree within 1% at both levels. On R, the fresh container's first level (c=128) ran 27% below the main one; its second agreed within 2%.

## Reading

**At cap 128 the cap is what binds, and the KV pool is close behind.** 128 sequences at 5 blocks each is 640 of 734 blocks, 87.2%; the gauge read 87.3% on C (the block count per sequence is derived in `../p55_concurrency_a2_256/README.md`). On R, 90% of blocks were in use with 128 running: some 4,000-token sequences take a second attention block. At cap 256 the same pool stops the engine at 146 sequences.

**The Server-SLO maximum on C is 128 at both caps, 128 and 256.** A higher cap does not raise it, because at c=256 the queue pushes p99 TTFT past 2 s on both. The throughput at the same concurrency is not the same: at c=128, cap 128 gives 2,679 tok/s with a 48 ms p99 TPOT, and cap 256 gives 3,902 tok/s with 33 ms. The difference begins at low concurrency (c=32: 1,738 against 2,238 tok/s). The mechanism is tested separately in `../p55_capture_control/`.

**On R the order is reversed:** cap 128 ran faster than cap 256 at every level from 1 to 128 (c=64: 1,749 against 1,504 tok/s; p99 TPOT 35 against 42 ms). It was faster at c=1 too (289 against 274 tok/s), where the cap cannot act, so part of this gap is the difference between two containers two hours apart and not the cap. This is observed, not explained.

**Pre-registered predictions** (the same six statements for every cap). **R1** server maximum on C above 32: held (128). **R2** interactive maximum on C at most 64: held (32). **R3** peak throughput ≥ 2,000 tok/s at a level ≥ 64: held (2,679). **R4** server maximum on R 8 or 16: held (8). **R5** the pool reading never "KV blocks", and "sequence cap" at c=2N on C: held. **R6** the engine does not die: held.

No sentence of the form "serves N users" follows from this.

## Files

`prediction_p55_concurrency_a2_128.json` + `.sha256` + `prediction_scan.txt` · `levels.jsonl` · `events.jsonl` · `analysis.json` · `A2_{C,R}_{main,fresh}/` (AIPerf exports per level, paths de-identified, see `deidentification_ledger.json`) · `versions.txt` · `ctx.txt`. Harness `../../scripts/p55_concurrency_a2.py`, analysis `../../scripts/p55_concurrency_a2_analyze.py`, runner `../../scripts/run_p55_concurrency_a2.sh` (`SEQS=128`). `logs/`, `harness_test/` and the console output (`console.txt`) are not published.
