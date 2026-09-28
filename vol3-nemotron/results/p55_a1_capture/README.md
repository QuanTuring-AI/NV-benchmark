# Vol.3 · A1's generation-rate step past 8k tokens: is it the loss of CUDA graphs? (run 2026-09-23, 17:02–17:28)

**Question.** In `../p53_longctx/` and its addendum, A1 (Nemotron Nano 9B v2, NIM 1.12.2, vLLM V0) generated at about 72 tok/s at 1k and 4k prompt tokens, about 45 tok/s at 16k, and about 44 at 57k: a step, then flat. Every A1 engine config dump reads `"max_seq_len_to_capture": 8192`, and the README attributed the step to decode running without CUDA graphs past that length. That was an inference. This run measures it. Pre-registration `prediction_p55_a1_capture.json`, frozen 2026-09-23T16:27:31+0800 after harness tests (disclosed in its basis) and scanned before its sidecar was written (`prediction_scan.txt`); first request 17:06:10.

**What the image allows.** The direct test would raise the capture limit to 32,768. NIM 1.12.2 cannot receive that: it builds the engine arguments itself (`--async-engine-args` JSON) from a fixed set of `NIM_*` variables, and `NIM_PASSTHROUGH_ARGS` is not one of them. The only CUDA-graph variable it reads is `NIM_DISABLE_CUDA_GRAPH`, which it maps to `enforce_eager` (`nim_llm_sdk/entrypoints/args.py:53`). So the run does the reverse test with one variable: switch graphs off at ~3.8k tokens, where the default uses them, and at ~14k, where it does not. The forward attempt is run too, to record that the setting does not arrive. Every condition's engine config is read back from its startup log.

Every row: **A1** Nemotron Nano 9B v2 · bf16 · NIM 1.12.2 · `max_num_seqs` 32 · `max_tokens` 256 · one container per condition · warm-up of at least 60 s and 6 requests at the measured depth · five measured requests, medians. The eager and capture conditions are control arms, not A1's configuration; they do not replace A1's numbers.

## Result

| Condition | `NIM_MAX_MODEL_LEN` | Engine config read back | Prompt tokens | TTFT (ms) | Generation (tok/s) | Memory at READY |
|---|---|---|---|---|---|---|
| ~4k · default | 8,192 | `enforce_eager` false · capture 8,192 | 3,769 | 391 | **76.4** | 28,404 MiB |
| ~4k · `NIM_DISABLE_CUDA_GRAPH=1` | 8,192 | `enforce_eager` **true** | 3,769 | 423 | **52.3** | 28,330 MiB |
| ~14k · default | 32,768 | `enforce_eager` false · capture 8,192 | 14,213 | 1,341 | **55.7** | 23,264 MiB |
| ~14k · `NIM_DISABLE_CUDA_GRAPH=1` | 32,768 | `enforce_eager` **true** | 14,213 | 1,322 | **51.7** | 23,190 MiB |
| ~14k · `NIM_PASSTHROUGH_ARGS "--max-seq-len-to-capture 32768"` | 32,768 | capture still **8,192**: not delivered | 14,213 | 1,341 | 51.5 | 23,264 MiB |

All preconditions held on the four reverse-test conditions. The capture condition fails P3 by design: the engine never saw the setting.

| Ratio | Value |
|---|---|
| 4k: graphs off / on | **0.685** |
| 14k: graphs off / on | **0.928** |
| 4k with graphs off / 14k default | 0.939 |

**Attribution: measured.** The pre-registered rule is: 4k ratio ≤ 0.75 and 14k ratio within 0.90–1.10. Turning CUDA graphs off at 4k reproduces most of the step: 76 falls to 52 tok/s, within 6% of the 14k default rate. At 14k, where the default already runs without graphs past the 8,192-token capture limit, switching them off changes little. The step A1 shows past 8k tokens is the loss of CUDA-graph replay in decode on this vLLM V0 build, not a cost that grows with context.

**Forward test: unverified**, as expected. With the capture setting passed, the engine config still read 8,192 and the rate did not rise (51.5 tok/s).

## Two things this run also shows

- **A1's rates were higher in this session than last night.** At ~14k tokens A1 measured 44.7 and 45.8 tok/s in the two long-context runs (03:xx and 07:xx), 52.5 in a harness test at 15:55, and 55.7 here. At ~4k: 71.6 then, 76.4 now. The container configuration is identical. The machine was rebooted in between and Docker Desktop restarted. The cause was not measured. The reverse test compares conditions within this one session, so its verdict does not depend on it, but A1's absolute rates carry this session-to-session spread of up to about 20%.
- **With graphs off, the first request pays a one-time cost**: the first warm-up request took 12.2–12.6 s to its first token, against 1.1–1.9 s with graphs on.

**Pre-registered predictions.** **R1** 4k default 68–76 tok/s and 16k default 42–50: **failed** on both (76.4 and 55.7, the session difference above). **R2** reverse verdict 'measured': held. **R3** forward attempt 'unverified': held. **R4** memory at READY lower with graphs off by less than 1 GB: held (74 MiB lower at both depths).

## Files

`prediction_p55_a1_capture.json` + `.sha256` + `prediction_scan.txt` · `requests.jsonl` (warm-up rows marked; digests and lengths, no text) · `events.jsonl` (per condition: env, engine config read back from the log, cache, warm-up rates) · `analysis.json` · `ctx.txt`. Harness `../../scripts/p55_depth.py`, analysis `../../scripts/p55_depth_analyze.py`, runner `../../scripts/run_p55_depth.sh` (`EXP=a1_capture`); SHA-256 in the pre-registration. `logs/` (startup and container logs) and `harness_test/` are not published.
