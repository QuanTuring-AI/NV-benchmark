# Vol.3 · A2: the CUDA-graph capture size, not the sequence cap, sets the rate at a fixed concurrency (run 2026-09-23, 22:38–23:05)

**Question.** In the three sweeps with the cap raised (`../p55_concurrency_a2_256/`, `_128/`, `_064/`), A2 ran at different rates at the same concurrency depending on its `max_num_seqs`. On the chat profile at c=32: 1,540 / 1,130 / 1,738 / 2,238 tok/s at caps 32 / 64 / 128 / 256 (cap 32 from `../p53_concurrency_v2/`). The cap is a limit on how many sequences run; at c=32 none of those caps binds. vLLM 0.27.1 also derives its largest CUDA-graph capture size from the cap: min(2 × `max_num_seqs`, 512) tokens (`vllm/config/vllm.py`, `_set_cudagraph_sizes`). A batch step larger than that runs without a graph. The startup logs of the sweeps agree: 11 / 35 / 51 mixed prefill-decode sizes captured at caps 32 / 128 / 256. This run changes only the capture size, at cap 256, in one session. It was added after the sweeps, not planned with them; it answers their question and took under 30 minutes of GPU time. Pre-registration `prediction_p55_capture_control.json`, frozen 2026-09-23T22:37:51+0800 after a harness test (disclosed in its basis) and scanned before its sidecar was written (`prediction_scan.txt`); first request 22:44:09.

Every row: **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 (vLLM 0.27.1) · `NIM_MAX_MODEL_LEN` 8192 · `max_num_seqs` 256 (image default) · profile **C** (200 ± 50 / 200 ± 50, `ignore_eos`, temperature 0) · harness, AIPerf flags, warm-up level and calibration as the sweeps · levels 1, 16, 32, main containers only. The two containers ran back to back: `s256_default` (nothing else set) and then `s256_cg064` (`NIM_PASSTHROUGH_ARGS "--max-cudagraph-capture-size 64"`, the capture size cap 32 implies). The second is a control arm, not A2's configuration.

All preconditions held: every level clean; calibration (default: TTFT 32.5 vs 36.3 ms, ITL 3.29 vs 3.19 ms; capture 64: 76.8 vs 94.5 ms, 3.18 vs 3.13 ms); and the setting reached the engine (captured sizes read from each startup log: default 51 mixed prefill-decode and 35 decode; capture 64: 11 and 11).

## Result

| c | output tok/s: default · capture 64 | ratio | p50 · p99 TPOT (ms): default · capture 64 | p99 TTFT (ms): default · capture 64 |
|---|---|---|---|---|
| 1 | 293 · 279 | 0.95 | 3.3 · 3.4 / 3.2 · 3.4 | 39 · 93 |
| 16 | 1,512 · 744 | **0.49** | 10.2 · 10.8 / 20.0 · 23.1 | 181 · 307 |
| 32 | 2,028 · 956 | **0.47** | 15.1 · 16.3 / 31.1 · 34.4 | 437 · 585 |

**Verdict: measured** (pre-registered rule: the c=32 ratio ≤ 0.85). At cap 256, lowering only the capture size to what cap 32 implies halves the throughput at c=16 and c=32. Single-stream speed is barely affected (−5%).

## Reading

**At a fixed concurrency, A2's rate on this card is set by how many batch shapes the engine has captured as CUDA graphs, and in vLLM 0.27.1 that number follows `max_num_seqs` unless it is set separately.** That explains the direction of the differences between the sweeps: a lower cap captures fewer sizes, and more of its mixed prefill-decode steps run without a graph. It does not explain their size. Cap 32 in `../p53_concurrency_v2/` (1,540 tok/s at c=32, another session) ran faster than cap 256 with the cap-32 capture size here (956). Cap 64, with a capture size of 128, was the slowest sweep. The sizes captured are not the only difference between those runs, and the sweeps also varied between containers of one configuration by up to 31%. The Nemotron Nano 9B v2 control in `../p55_a1_capture/` measured the same kind of cost on a different engine: 31% per decode step with graphs off at ~4k tokens.

**For a deployment:** lowering `max_num_seqs` to "reserve" capacity for fewer users does not make each of them faster on this image; it makes the engine capture fewer graphs and can make every level below the cap slower. The capture size can be set independently (`--max-cudagraph-capture-size`, through `NIM_PASSTHROUGH_ARGS` on NIM 2.0.12). This run measured the direction that removes graphs at cap 256. The reverse, a small cap with a large capture size, was not run.

**Pre-registered predictions.** **R1** both settings reach the engine: held. **R2** verdict 'measured', r ≤ 0.85: held (0.47). **R3** c=1 within 5% between the two: held, barely (4.9%). **R4** the default container at c=32 within 15% of the cap-256 sweep's 2,238 tok/s: held (2,028, 0.91). The 9% between this container and the sweep's at the same configuration is the container-to-container spread; it is why the reference was measured in this run.

## Files

`prediction_p55_capture_control.json` + `.sha256` + `prediction_scan.txt` · `levels.jsonl` · `events.jsonl` (per container: env, captured graph sizes from the startup log, cache config, warm-up level, calibration) · `analysis.json` · `A2_C_{s256_default,s256_cg064}/` (AIPerf exports per level, paths de-identified, see `deidentification_ledger.json`) · `versions.txt` · `ctx.txt`. Harness `../../scripts/p55_capture_control.py` (imports `p53_concurrency_v2.py`), analysis `../../scripts/p55_capture_control_analyze.py`, runner `../../scripts/run_p55_capture_control.sh`. `logs/`, `harness_test/` and the console output (`console.txt`) are not published.
