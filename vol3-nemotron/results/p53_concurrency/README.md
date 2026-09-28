# Vol.3 · concurrency, first run: closed-loop AIPerf sweeps on both Nemotron NIMs (run 2026-09-23, 01:21–03:18)

**Status under this run's own rules: every sweep's conclusions are null.** The pre-registered instrument gate (P2) failed on every A2 sweep and on both A1 R sweeps, for two reasons that are defects of the calibration design, and the "all levels clean" gate (P1) failed on every A1 sweep because **A1's engine died at concurrency 32**, which is a result. The level tables below are valid measurements (AIPerf reported 0 request errors on every A2 level and on every A1 level below the crash) and are published as such; the SLO readings a reader would draw from them are *not* this run's conclusions. The run is repeated with a repaired gate as **`../p53_concurrency_v2/`**, whose pre-registration is written from these numbers and says so. Nothing in this directory is modified.

Pre-registration `prediction_p53_concurrency.json` (frozen 2026-09-23T00:31:37+0800; the first frozen version of 00:30 was set aside unrun because its SLO-source text and the harness docstring named an internal reviewer role — both are in `logs/superseded_prediction_20260923T003126/`, not published). First measured request 01:27.

## What was measured

Closed-loop concurrency with **AIPerf 0.11.0** (`--streaming`, `--use-server-token-count`, warm-up = N requests excluded, grace period 0, temperature 0, `ignore_eos`), levels **1, 2, 4, 8, 16, 32, 64**, first level 60 s, later levels sized from the previous level's p99 latency as Vol.2's sweep did. Two synthetic ISL/OSL profiles from the NIM benchmarking guide's categories: **C** (chat) 200±50 / 200±50 and **R** (summarization/RAG) 3,500±300 / 500±50. Per (arm, profile) one container runs the whole sweep (`main`); a fresh container then repeats the two highest levels (`fresh`) so state dependence is visible rather than averaged. **Both arms at `max_num_seqs` 32** (A1 `NIM_MAX_NUM_SEQS`, A2 `NIM_PASSTHROUGH_ARGS "--max-num-seqs 32"`), `NIM_MAX_MODEL_LEN` 8192, otherwise the footprint configuration. Before each main sweep the harness's own streaming client sent 10 requests at concurrency 1 (one discarded warm-up, new TCP connection per request, ~200-token prompt, 200 output tokens) as the instrument check. No Guardrails in this run. SLOs, fixed before any number: MLPerf Inference v5.1 Llama 3.1-8B **server** (p99 TTFT ≤ 2,000 ms ∧ p99 TPOT ≤ 100 ms) and **interactive** (500 ms ∧ 30 ms) — another model's limits, applied to both arms identically.

Every row: **A1** Nemotron Nano 9B v2 · bf16 · NIM 1.12.2 (vLLM V0 0.10.0) · `max_num_seqs` 32 · `max_tokens` = profile OSL; **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 (vLLM 0.27.1) · `max_num_seqs` 32 · `max_tokens` = profile OSL. Not a single-variable comparison (see `../p50_speed/README.md`).

## Preconditions per sweep

| Sweep | P1 levels clean | P2 instrument (medians, 20% or 15 ms) | P3 seqs 32 | Conclusions |
|---|---|---|---|---|
| A1 · C · main | ❌ c=32, 64: engine dead | ✅ TTFT 60.8 vs 51.3 ms (15.6%) · ITL 13.92 vs 13.82 (0.7%) | ✅ | null |
| A1 · C · fresh | ❌ c=64: engine dead | ✅ (main's) | ✅ | null |
| A1 · R · main | ❌ c=32, 64: engine dead | ❌ TTFT 57.4 (200-token prompt) vs 338.8 ms (3,500-token) · ITL 13.84 vs 13.83 (0.1%) | ✅ | null |
| A1 · R · fresh | ❌ c=32, 64: engine dead | ❌ (main's) | ✅ | null |
| A2 · C · main | ✅ 0 errors, 7 levels | ❌ TTFT 97.8 vs 82.5 ms (15.7%, inside 20%) · **ITL 4.48 vs 3.34 ms (25.4%)** | ✅ | null |
| A2 · C · fresh | ✅ | ❌ (main's) | ✅ | null |
| A2 · R · main | ✅ 0 errors, 7 levels | ❌ TTFT 100.8 (200-token) vs 174.6 (3,500-token) · ITL 4.46 vs 3.34 (25.2%) | ✅ | null |
| A2 · R · fresh | ✅ | ❌ (main's) | ✅ | null |

### Why the instrument gate failed (both are the gate's fault, not AIPerf's)

1. **The calibration ran in the engine's first minute of traffic, on A2 a transient.** The own client's ten requests on A2 C measured per-token times of 5.22, 4.72, 4.78, 4.90, 4.45, 4.52, 4.44, 4.33, 4.31, 4.37 ms in that order; a second client (the `requests` library) immediately after: 4.20, 4.19, 4.13, 4.09, 4.04 ms; AIPerf's c=1 level a minute later: 3.7 ms per token. On A2 R the same shape (5.37 → 4.02, then 3.97 → 3.64, then AIPerf 3.33). A1 — bf16, no JIT kernels — showed no drift (13.9 vs 13.8 ms). The A2 image tunes its FlashInfer NVFP4 MoE kernels on first use (its startup log records 88 autotune lines, `../p50_speed/README.md`); the calibration caught that, not a client defect. The gate compared a warming engine with a warm one.
2. **The calibration prompt was ~200 tokens on both profiles.** On profile R that put a 57 ms first-chunk time against AIPerf's 339 ms on 3,500-token prompts (A1) — two prompt lengths, not two instruments. ITL, which the prompt length does not touch, agreed within 0.1% on A1 R.

Before the run the calibration client itself had been repaired: on this host a reused HTTP connection to the container adds ~45 ms to the first chunk (a fresh connection: 43–54 ms; the next requests on the same connection: 83–99 ms; ITL unchanged; curl reaches the response headers in 6–8 ms). Four earlier calibration attempts had reused the connection. The mechanism was not identified; the harness opens a new connection per request and reports it. The `requests` client used by the speed, answer and long-context harnesses measured 50.7 / 64.7 / 87.4 / 93.1 ms first-chunk medians here (A1 C, A1 R, A2 C, A2 R) against the calibration client's 60.8 / 57.4 / 97.8 / 100.8 ms.

## Finding: A1's engine dies at concurrency 32

At the first level with 32 concurrent requests, A1's engine process raised and never recovered; every request after AIPerf's 32 warm-up requests returned HTTP 500 `Engine loop is not running. Inspect the stacktrace to find the original error: IndexError('pop from empty list')`, and the level records 40,100 (main C c=32), 79,235 (c=64), 70,926 (fresh C c=64) failed requests in 60–95 s. Five attempts at ≥ 32:

| Container | Level | Outcome |
|---|---|---|
| A1 · C · main | c=32 | **died** during warm-up |
| A1 · C · fresh | c=32 | **survived** 60 s: 278 completed, 922 tok/s, p99 TTFT 729 ms, p99 ITL 34.8 ms |
| A1 · C · fresh | c=64 | **died** |
| A1 · R · main | c=32 | **died** (02:01:54, within a second of the first c=32 responses starting) |
| A1 · R · fresh | c=32 | **died** |

Traceback (from the A1 R main container's log, captured by hand before the harness removed the container — the harness's `stop()` does not save logs, a defect fixed in v2):

```
File ".../nim_llm_sdk/entrypoints/openai/out_of_tree_models/nemotron_h.py", line 585, in forward
    mamba_cache_params = self.mamba_cache.current_run_tensors(**kwargs)
File ".../vllm/model_executor/models/mamba_cache.py", line 72, in current_run_tensors
File ".../vllm/model_executor/models/constant_size_cache.py", line 124, in _prepare_current_run_cache
    self._assign_seq_id_to_cache_index(req_id, seq_id,
File ".../vllm/model_executor/models/constant_size_cache.py", line 102, in _assign_seq_id_to_cache_index
    destination_index = self.free_cache_indices.pop()
IndexError: pop from empty list
```

**Reading.** The Mamba state of this model lives in a constant-size cache with one slot per sequence, sized by `max_num_seqs` (`../p50_footprint/`: the same cache is what set A2's memory floor). When the number of sequences the scheduler places in one step reaches that size while a finished sequence's slot has not yet been released, the free list is empty and the engine process dies rather than queueing. At c=32 = `max_num_seqs` the condition is a race — one attempt survived — and at c=64 it is certain. On this image and version, A1's ceiling on both profiles is therefore **an engine crash at concurrency = `max_num_seqs`**, not a latency limit; the levels below it are the only ones that exist. The GPU memory that a larger `max_num_seqs` would need (about 14.6 MiB of Mamba state per sequence plus KV) is the footprint table's business. This is a property of NIM 1.12.2's vLLM V0 build of this model; A2 (NIM 2.0.12, vLLM 0.27.1) queued at c=64 without error.

## Level tables (AIPerf summaries; TTFT and ITL in ms; ITL = (e2e − TTFT)/(tokens − 1); throughput in output tokens/s)

**A1 · profile C** (ISL/OSL measured 201–232 / 188–211)

| c | duration | completed | TTFT p50 / p90 / p99 | ITL p50 / p99 | tok/s | container |
|---|---|---|---|---|---|---|
| 1 | 60 s | 21 | 51.3 / 64.7 / 74.6 | 13.82 / 14.08 | 71.1 | main |
| 2 | 60 | 45 | 56.5 / 66.6 / 73.1 | 13.17 / 13.68 | 147.1 | main |
| 4 | 60 | 72 | 59.0 / 89.0 / 114.4 | 15.17 / 15.94 | 258.0 | main |
| 8 | 60 | 133 | 56.7 / 72.2 / 224.4 | 17.18 / 18.17 | 447.0 | main |
| 16 | 60 | 230 | 57.9 / 89.1 / 572.9 | 21.21 / 22.18 | 720.9 | main |
| 32 | 60 | — | engine died | | | main |
| 32 | 60 | 278 | 68.8 / 505.7 / 728.6 | 32.48 / 34.76 | 922.4 | fresh |
| 64 | 82–95 | — | engine died (both containers) | | | main, fresh |

**A1 · profile R** (ISL/OSL 3,462–3,549 / 485–509)

| c | duration | completed | TTFT p50 / p90 / p99 | ITL p50 / p99 | tok/s | container |
|---|---|---|---|---|---|---|
| 1 | 60 s | 8 | 338.8 / 426.0 / 537.3 | 13.83 / 13.91 | 68.7 | main |
| 2 | 62 | 15 | 352.8 / 460.1 / 658.6 | 14.34 / 15.43 | 127.1 | main |
| 4 | 68 | 28 | 370.1 / 762.1 / 1,356.7 | 16.29 / 17.16 | 225.9 | main |
| 8 | 84 | 38 | 449.7 / 5,909.2 / 7,294.7 | 23.01 / 41.97 | 239.2 | main |
| 16 | 185 | 169 | 505.6 / 964.2 / 6,544.4 | 32.67 / 39.65 | 444.5 | main |
| 32, 64 | | — | engine died (main and fresh) | | | |

**A2 · profile C** (ISL/OSL 211–232 / 188–210)

| c | duration | completed | TTFT p50 / p90 / p99 | ITL p50 / p99 | tok/s | container |
|---|---|---|---|---|---|---|
| 1 | 60 s | 79 | 82.5 / 93.2 / 112.8 | 3.34 / 3.72 | 264.5 | main |
| 2 | 60 | 118 | 98.4 / 140.4 / 178.8 | 4.58 / 5.20 | 391.1 | main |
| 4 | 60 | 168 | 103.0 / 138.7 / 187.8 | 6.29 / 7.16 | 587.9 | main |
| 8 | 60 | 237 | 106.9 / 173.9 / 205.6 | 9.39 / 10.70 | 799.9 | main |
| 16 | 60 | 331 | 112.1 / 197.8 / 259.8 | 14.62 / 17.22 | 1,035.8 | main |
| 32 | 60 | 397 | 129.8 / 255.6 / 448.9 | 22.71 / 27.75 | 1,323.1 | main |
| 64 | 60 | 418 | 4,578.3 / 4,864.5 / 5,148.4 | 23.01 / 25.57 | 1,326.6 | main |
| 32 | 60 | 420 | 135.4 / 263.1 / 426.5 | 21.03 / 29.47 | 1,403.0 | fresh |
| 64 | 60 | 404 | 4,729.6 / 5,009.0 / 5,252.6 | 23.80 / 26.28 | 1,282.3 | fresh |

**A2 · profile R** (ISL/OSL 3,440–3,616 / 489–512)

| c | duration | completed | TTFT p50 / p90 / p99 | ITL p50 / p99 | tok/s | container |
|---|---|---|---|---|---|---|
| 1 | 60 s | 32 | 174.6 / 207.8 / 268.8 | 3.34 / 3.43 | 268.7 | main |
| 2 | 60 | 48 | 186.1 / 259.3 / 346.0 | 4.52 / 4.99 | 402.1 | main |
| 4 | 60 | 70 | 188.7 / 275.7 / 520.2 | 6.10 / 6.65 | 600.1 | main |
| 8 | 60 | 96 | 197.3 / 359.6 / 1,150.5 | 9.01 / 9.82 | 809.0 | main |
| 16 | 60 | 130 | 261.9 / 694.0 / 2,481.3 | 13.45 / 15.53 | 1,060.5 | main |
| 32 | 71 | 169 | 319.7 / 2,638.2 / 5,118.1 | 22.84 / 26.81 | 1,196.5 | main |
| 64 | 131 | 349 | 11,556.3 / 12,413.4 / 16,349.8 | 22.55 / 25.39 | 1,308.9 | main |
| 32 | 60 | 150 | 310.6 / 2,808.1 / 4,863.1 | 22.28 / 25.37 | 1,243.8 | fresh |
| 64 | 127 | 342 | 11,292.1 / 12,584.7 / 15,217.0 | 22.26 / 25.49 | 1,323.8 | fresh |

Containers (seconds to READY · memory at READY): A1 C 278 s · 28,606 MiB, fresh 246 · 28,883; A1 R 235 · 28,986, fresh 235 · 28,740; A2 C 410 · 30,513, fresh 431 · 30,013; A2 R 472 · 30,647, fresh 368 · 29,948. A2's KV cache: `fp8_e4m3`, 749–760 blocks × 4,176 tokens (`/metrics`).

**What the A2 tables show, read informally** (not this run's conclusion — the gate failed; v2 tests whether it reproduces): on profile C both SLOs hold through c=32 (p99 TTFT 449 ms, p99 ITL 27.8 ms) and c=64 fails the server SLO on TTFT alone (5.1 s: queueing beyond `max_num_seqs`, ITL unchanged) with throughput saturated at 32 (1,323 → 1,327 tok/s; fresh 1,403 / 1,282); on profile R the server SLO holds through c=8 (p99 TTFT 1.15 s) and fails at 16 (2.48 s), the interactive SLO holds through c=2 (346 ms) and fails at 4 (520 ms), while p99 ITL stays under 27 ms at every level — on long prompts the binding quantity is prefill queueing, not decode. Fresh-container repeats sit within 4–9% of the main sweep at every level both ran.

## Pre-registered predictions

None of R1–R5 is evaluated under this run's rules (conclusions null). Against the level tables: R1 (both arms inside the server SLO to 32, failing at 64) — A2 as predicted on C; A1 not: it crashed. R2 (A1's R-profile server-SLO maximum below 32; A2's at least A1's) — A1's maximum on R is bounded by the crash at 32, with p99 TTFT already over 2 s from c=8; A2's is 8. R3 (interactive maximum ≤ 8 on R for both) — A2: 2; A1: 1 (c=2 p99 TTFT 659 ms). R4 (A2 saturation throughput ≥ 2.5× A1's on C) — A2 1,323 tok/s at 32 against A1's last live level 721 at 16 (or 922 in the one surviving c=32): the comparison has no A1 saturation point. R5 (fresh within 25%) — A2 yes; A1 has one pair (C c=32) that cannot be compared because the main container died.

## De-identified fields in the AIPerf outputs

As Vol.2 did (`../../../vol2-guardrails/results/p17_concurrency/README.md`), the local user-home prefix that AIPerf records — the tokenizer path in `profile_export_aiperf.json` and `server_metrics_export.json`, `run_info.cli_command`, and each entry of the `command` list in `levels.jsonl` — is replaced by `<HOME>` before publication; no other byte changes. `deidentification_ledger.json` lists every file with the SHA-256 of the original and of the de-identified content (48 files, 195 replacements); the originals are kept outside the repository. `analysis.json` does not read any of the replaced fields. AIPerf's per-level console output, per-request exports, logs and the run's console output (`console.txt`) are not published.

## Files

`prediction_p53_concurrency.json` + `.sha256` · `deidentification_ledger.json` · `levels.jsonl` (one record per level with the AIPerf summary and the command line) · `events.jsonl` (container starts with env, GPU, cache and calibration records) · `analysis.json` · `versions.txt` · `ctx.txt` · `<arm>_<profile>_<container>/c<N>/profile_export_aiperf.json` (AIPerf's summary per level; per-request exports and AIPerf logs are not published). Harness `../../scripts/p53_concurrency.py`, analysis `../../scripts/p53_concurrency_analyze.py`, runner `../../scripts/run_p53_concurrency.sh`, hashed in the pre-registration and unchanged. `harness_test/` (five calibration attempts and the diagnosis of the connection-reuse offset) and `logs/` (harness stderr, the superseded first pre-registration, container logs) are not published.
