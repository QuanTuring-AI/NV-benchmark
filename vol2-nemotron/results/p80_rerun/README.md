# P80 · the concurrency sweeps repeated on a clean night, with a container sentinel

One night (2026-10-01, 02:29:44 – 06:20:52, exit code 0), seven groups, nine containers:

- **six sweeps repeated** — `s256_C`, `s256_R` (Nemotron 3 Nano, NIM 2.0.12, NVFP4, image-default sequence cap 256: the main sweeps of `../p55_concurrency_a2_256/`) and `v2_A2_C`, `v2_A2_R`, `v2_A1_C`, `v2_A1_R` (both arms at cap 32: the main sweeps of `../p53_concurrency_v2/`). Same image, profile, environment, AIPerf command and level ladder as the originals; the harness imports theirs.
- **G5** — Nemotron Nano 9B v2 (the A1 weights) on upstream `vllm/vllm-openai:v0.30.0`, levels 16 / 32 / 64 on the chat profile and two prompt depths.

Why it was run: most cells of the original sweeps do not match the idle-card fingerprint in their end-of-cell GPU record (`../p78_audit/`: 21 of 26 main-sweep cells in `p53_concurrency_v2`, 15 of 20 in `p55_concurrency_a2_256`), so an idle card could not be shown for them; and a first attempt at this re-run on the morning of 2026-09-30 ran 6–20× slow and was stopped (kept on the machine, not published; `../p79_host_state/` is the diagnosis).

Pre-registrations: the two P78 files stay in force unchanged (`../p78_clean_rerun/prediction_p78_clean_rerun.json`, `../p78_n2_upstream/prediction_p78_n2_upstream.json`). The gates added for this night are in `prediction_p80_gates.json`, frozen 2026-09-30T23:39:56, before the first container (02:30:03).

## Boundary

| | |
|---|---|
| Card · driver | RTX 5090, 32,607 MiB · 591.86 |
| Load generator | AIPerf 0.11.0, closed loop, profiles C (200 / 200) and R (3,500 / 500), `ignore_eos`, 60 s levels after a discarded 120 s warm-up level at c=1 |
| Host | Windows boot 2026-09-30T13:28:30, not rebooted before the night (the owner's decision); WSL shut down and Docker restarted at 02:17–02:24 |
| Displays | both of this host's displays are connected to the RTX 5090 (the owner's statement of 2026-10-01; added here after the run, it is not in `ctx.txt`) |
| Dedicated GPU memory before the first container | other processes 0.482 GB (14 processes), desktop compositor 1.342 GB; no game client, no browser window (`ctx.txt`) |
| Statistic | per level: output tok/s (avg), p99 TTFT, p99 ITL from AIPerf's `profile_export_aiperf.json` |

Nothing here is a single-variable comparison between the two models; each row is one configuration.

## Gates, and what they did

| Gate | Rule | This night |
|---|---|---|
| G8 (idle card before every cell) | utilization p50 ≤ 2% and power p50 ≤ 45 W over 10 s, retried up to 15 min | 52 of 52 passed, longest wait 10.8 s |
| Sentinel (per group, after the warm-up level and the calibration) | R c=1 TTFT p50 and C at the group's reference level ITL p50, each ≤ 2 × the original's value; fail → restart once → fail → group null | 6 of 6 judged groups passed on the first container; G5 recorded, not judged (no reference) |
| Arm health (before and after every cell) | c=1 for 10 s; after ÷ before < 0.8 → the cell is run again in a new container; again → null | 3 cells had no "after" value (the engine was dead, see below): `v2_A1_R` c=16 re-run and kept; c=32 null after two runs |
| Stop time | no new group or cell after 08:00 | not reached |
| The shape of 2026-09-30 morning | utilization ≥ 95%, power ≤ 200 W, throughput ≤ 0.5 × original | 0 cells |

`judge.json` (`p80_judge.py`): 39 cells normal (≥ 0.8 × original), 4 grey (0.5–0.8), 0 abnormal, 6 with no original. The judge's positive control is the stopped morning run's two cells (99.8 vs 273.5 tok/s and 543.3 vs 3,902.1 tok/s), which it calls abnormal.

## Result 1 · the SLO ceilings, by the original runs' own rules

`slo_ceilings.json` (`p80_slo.py`, written after the run, no new rule): each P80 sweep is passed to the analysis function of the run it repeats, so the preconditions and the ceilings are the ones those runs pre-registered. SLOs: MLPerf Inference v5.1 Llama 3.1-8B server (p99 TTFT ≤ 2,000 ms and p99 ITL ≤ 100 ms) and interactive (500 ms and 30 ms) — another model's rulers, the same on every row.

| Sweep | Original run | Original: server · interactive | P80: server · interactive | P80 preconditions (P1 · P2 · P3) | SLO test alone (P1 set aside) |
|---|---|---|---|---|---|
| `s256_C` | `p55_concurrency_a2_256` A2 · C | 128 · 32 | 128 · 32 | pass · pass · pass | 128 · 32 |
| `s256_R` | `p55_concurrency_a2_256` A2 · R | 8 · 2 | null | **fail** · pass · pass | 8 · 2 |
| `v2_A2_C` | `p53_concurrency_v2` A2 · C | 32 · 32 | 32 · 32 | pass · pass · pass | 32 · 32 |
| `v2_A2_R` | `p53_concurrency_v2` A2 · R | 8 · 4 | 8 · 4 | pass · pass · pass | 8 · 4 |
| `v2_A1_C` | `p53_concurrency_v2` A1 · C | 16 · 16 | 8 · 8 | pass · pass · pass | 8 · 8 |
| `v2_A1_R` | `p53_concurrency_v2` A1 · R | 4 · 1 | 4 · 1 | pass · pass · pass | 4 · 1 |

- **Four of the six sweeps reproduce their ceilings exactly.**
- `s256_R`: one request of 2,579 failed at c=512 (`ServerDisconnectedError`), far above its ceiling. The original rule P1 (no failed request at any live level) therefore makes this sweep's conclusion **null**. The SLO test alone gives 8 · 2, the original's values; that column is not a pre-registered conclusion and is marked so in the file.
- `v2_A1_C`: the engine exited during c=16, so the largest level with a value is 8. Throughput at c=1–8 is 1.01–1.03 × the original. The two values stand side by side: **16 (P53) / 8 (P80, engine exit at c=16)**.
- `v2_A1_R`: the analyser prints "engine crash at c=64" for P80 because the null level (32) is not passed to it; where each engine was actually found dead is in the ledger below.

## Result 2 · throughput beside the originals

Both values are given for every level; neither replaces the other.

| c | `s256_C` original tok/s | P80 tok/s | P80 ÷ original | `s256_R` original tok/s | P80 tok/s | P80 ÷ original |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 300 | 275 | 0.92 | 274 | 290 | 1.06 |
| 2 | 465 | 399 | 0.86 | 405 | 430 | 1.06 |
| 4 | 733 | 594 | 0.81 | 626 | 635 | 1.01 |
| 8 | 1,088 | 833 | 0.77 | 804 | 883 | 1.10 |
| 16 | 1,543 | 1,165 | 0.75 | 1,046 | 1,131 | 1.08 |
| 32 | 2,238 | 1,644 | 0.73 | 1,279 | 1,408 | 1.10 |
| 64 | 2,991 | 2,274 | 0.76 | 1,504 | 1,742 | 1.16 |
| 128 | 3,902 | 3,188 | 0.82 | 2,133 | 2,146 | 1.01 |
| 256 | 3,999 | 3,305 | 0.83 | 1,884 | 2,246 | 1.19 |
| 512 | 3,993 | 3,327 | 0.83 | 1,857 | 2,166 (1 failed request) | 1.17 |

| c | `v2_A2_C` original tok/s | P80 tok/s | P80 ÷ original | `v2_A2_R` original tok/s | P80 tok/s | P80 ÷ original |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 285 | 286 | 1.00 | 289 | 289 | 1.00 |
| 2 | 422 | 420 | 0.99 | 430 | 429 | 1.00 |
| 4 | 640 | 634 | 0.99 | 655 | 648 | 0.99 |
| 8 | 877 | 863 | 0.98 | 883 | 882 | 1.00 |
| 16 | 1,134 | 1,127 | 0.99 | 1,150 | 1,128 | 0.98 |
| 32 | 1,540 | 1,507 | 0.98 | 1,461 | 1,416 | 0.97 |
| 64 | 1,490 | 1,451 | 0.97 | 1,464 | 1,483 | 1.01 |

| c | `v2_A1_C` original tok/s | P80 tok/s | P80 ÷ original | `v2_A1_R` original tok/s | P80 tok/s | P80 ÷ original |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 74 | 76 | 1.03 | 73 | 73 | 1.01 |
| 2 | 146 | 149 | 1.02 | 137 | 137 | 1.00 |
| 4 | 271 | 274 | 1.01 | 234 | 235 | 1.00 |
| 8 | 466 | 472 | 1.01 | 365 | 361 | 0.99 |
| 16 | 777 | engine exit | — | 514 | 514 (second run) | 1.00 |
| 32 | engine exit | not run | — | engine exit | null (two runs completed, 513 and 615 tok/s, no failed request; the engine was dead after each) | — |
| 64 | not run | not run | — | not run | engine exit | — |

**One container was slow from its first request.** The `s256_C` container ran at 0.73–0.92 × the original at every level (four levels in the grey band), and its c=1 arm health was flat from the first cell to the last (after ÷ before 1.00–1.01, 291–293 tok/s). The next container, `s256_R`, loaded immediately afterwards from the same image with the same settings, ran at 1.01–1.19 × its original (arm health 320–321 tok/s). Both containers ran the same two sentinel probes, which gives a like-for-like figure: R c=1 254 vs 290 tok/s (ITL p50 3.50 vs 3.13 ms), C c=128 2,934 vs 3,494 tok/s — the first container 12–16% lower. In the 500 ms `nvidia-smi` rows with utilization ≥ 80%, both containers show the same median SM clock (2,910 MHz); median power is 344 W in the slow container and 372 W in the next (different profiles); the throttle-reason field reads `0x4` (NVML: software power cap) in 3% of those rows in the slow container and 29% in the next one, and `0x0` otherwise — so that field does not single out the slow container either. This is not the shape of the stopped morning run (utilization near 100% at 140–180 W). **On the same machine, the same image and the same night, two consecutive containers differed by 12–16% on identical probes, and the slower one sits up to 27% below the original sweep; the cause was not identified; the SLO ceilings are not affected.** The sentinel's 2× line is not meant to catch a difference of this size and did not. The four grey cells were not re-run (decided after the run): another night would add one more container sample, and the spread between containers is itself the finding. P78's prediction "every `s256_C` level ≥ 0.95 × the original" fails (0.73–0.92); its prediction "the largest level inside the server SLO is 128" passes.

What the records show about the containers' loads (10 s Windows counter samples; `slo_ceilings.json` → `containers`):

| Container | Load (s) | System memory during the load, max (GiB) | System memory at READY (GiB) | On the card at READY (GiB) | Compositor during the load, max (GiB) | Other processes during the load, max (GiB) |
|---|---:|---:|---:|---:|---:|---:|
| `p80-s256-c-1` | 346 | 2.357 | 0.357 | 30.64 | 1.342 | 0.406 |
| `p80-s256-r-1` | 346 | 2.006 | 0.357 | 30.64 | 1.218 | 0.332 |
| `p80-v2-a2-c-1` | 419 | 2.311 | 1.445 | 28.31 | 1.177 | 0.296 |
| `p80-v2-a2-r-1` | 377 | 2.002 | 0.883 | 28.87 | 1.131 | 0.265 |
| `p80-v2-a1-c-1` | 214 | 0.084 | 0.084 | 27.42 | 1.050 | 0.124 |
| `p80-v2-a1-r-1` | 192 | 0.084 | 0.084 | 27.42 | 1.052 | 0.136 |
| `p80-v2-a1-r-11` | 192 | 0.084 | 0.084 | 27.42 | 1.106 | 0.231 |
| `p80-v2-a1-r-12` | 192 | 0.084 | 0.084 | 27.42 | 1.078 | 0.157 |
| `p80-g5-0` | 388 | 2.207 | 0.082 | 29.41 | 1.083 | 0.161 |

"System memory" is the WSL VM process's shared GPU memory: the part of the container's GPU allocation that Windows holds in system RAM. **The amount at READY does not separate the slow container from the normal ones**: the slow and the next container both show 0.357 GiB, and a container with 1.445 GiB ran at 0.97–1.00 × its original. The slow container's load coincided with the night's highest readings of all three other columns. That is one container; it is an observation, not a cause.

## Result 3 · where the A1 engine exited

Every A1 container of this night ended with a dead engine. `slo_ceilings.json` → `a1_engine_exits`:

| Container | Levels it ran | Engine found dead |
|---|---|---|
| `p80-v2-a1-c-1` | 1, 2, 4, 8, 16 | during c=16 (no result) |
| `p80-v2-a1-r-1` | 1, 2, 4, 8, 16 | after c=16 completed: the c=1 health probe that follows got no answer |
| `p80-v2-a1-r-11` | 16, 32 | after c=32 completed |
| `p80-v2-a1-r-12` | 32, 64 | after c=32 completed (c=64 was then sent to the dead engine) |

The server's error body is the same in every case and the same as in `../p53_concurrency_v2/`: `Engine loop is not running … IndexError('pop from empty list')`. Counting both nights (P53: four containers; P80: four), **all eight A1 containers ended this way: twice at c=16, five times at c=32 (in two of them after the level had completed), once at c=64. Upstream vLLM 0.30.0 on the same weights (G5) ran 16, 32 and 64 without an engine exit.**

What the container logs say about the code path (`engine_log_excerpts.json`: first matching line per pattern, with each log's SHA-256; the logs themselves stay on the machine):

- A1 containers (NIM 1.12.2), line 71: `Mamba is experimental on VLLM_USE_V1=1. Falling back to V0 Engine.`; line 84: `Initializing a V0 LLM engine (v0.10.0)`.
- The traceback (lines 472–483 in three of the four logs) passes `vllm/model_executor/models/mamba_cache.py` line 72 (`current_run_tensors`) and ends in `vllm/model_executor/models/constant_size_cache.py` line 102 (`_assign_seq_id_to_cache_index`: `self.free_cache_indices.pop()`), `IndexError: pop from empty list`. The same frames are quoted in `../p53_concurrency/README.md`.
- G5 container, line 13: `Initializing a V1 LLM engine (v0.30.0)`.

## G5 · Nemotron Nano 9B v2 on upstream vLLM 0.30.0

Started at the first step of the pre-registered ladder (no extra flag). Arm health 74.6 tok/s (74% of the card's peak bandwidth for 17.78 GB read per token); ten single requests, median 74.7 tok/s.

| c (profile C) | tok/s | p99 TTFT (ms) | p99 ITL (ms) | failed requests | engine |
|---:|---:|---:|---:|---:|---|
| 16 | 817 | 339 | 19.3 | 0 | alive |
| 32 | 1,318 | 665 | 23.9 | 0 | alive |
| 64 | 1,807 | 1,273 | 34.3 | 0 | alive |

Generation rate at ~3.8k prompt tokens 74.6 tok/s, at ~15k 71.4 tok/s. P78's predictions for this group: P1 (a ladder step ≤ 2 starts and serves) pass, P2 (no engine exit at 16, 32 or 64) pass, P3 (the rate at ~16k ≥ 80% of ~4k) pass. This is a different engine version and a different engine build from the A1 arm; it is not a single-variable comparison with it.

## Disclosures

- `prediction_p80_gates.json` was frozen twice. The first freeze (2026-09-30T19:46:38) was replaced when the harness gained one test-only flag (`--sentinel-scale`, refused without `--test`) so that the path "sentinel fails → restart → fails again → group null → next group" could be run with the real command line; no real container had started. The file says so.
- `p80_slo.py` and this README were written after the run. `p80_slo.py` applies the originals' analysis functions; its adapter (which rows are levels, the second run of a repeated level, null levels left out) has a self-test with three mutation tests, and it reproduces two published original ceilings from their `levels.jsonl` as a positive control.
- Decisions taken after seeing the data: the four grey `s256_C` cells are not re-run and both values are published; the `s256_R` conclusion is null by the original rule and the SLO test alone is shown beside it.
- `recompute_check.txt`: `judge.json` and `slo_ceilings.json` are reproduced byte for byte from a scratch copy holding only published inputs; two negative controls (one level's throughput × 0.4; one level's p99 TTFT + 5,000 ms) change them.
- De-identification (`deidentification_ledger.json`): the local user-home prefix in AIPerf's recorded paths is replaced by `<HOME>` in 125 files (614 replacements); nothing else changes. `events.jsonl` is published as written: the harness records GPU memory as the WSL VM process, the compositor, the adapter totals and a sum over all other processes with a count, and no process names.

## Files

| File | What |
|---|---|
| `prediction_p80_gates.json` · `.sha256` · `prediction_scan_prediction_p80_gates.txt` | the gates' pre-registration, its sidecar, and the scan done before freezing |
| `ctx.txt` · `versions.txt` · `exit_code.txt` | pre-run checks, driver and AIPerf version, exit code |
| `events.jsonl` | every event: G8 samples, container starts with memory state, calibrations, sentinel verdicts, cell ends with arm health and state, overwrite checks |
| `levels.jsonl` | one row per AIPerf level (warm-up, sentinel and measured), with the command and AIPerf's summary |
| `<group>/…/profile_export_aiperf.json` · `server_metrics_export.json` | AIPerf's per-level exports (per-request exports are not published) |
| `smi_<container>.csv` | `nvidia-smi` every 500 ms for each container's life (clocks, throttle reasons, power, utilization, memory), paused during G8 samples |
| `windows_gpu_memory_public.jsonl` | the Windows GPU counters every 10 s, reduced as described above |
| `judge.json` | per-cell verdicts and the P78 predictions (`p80_judge.py`) |
| `slo_ceilings.json` | the tables of this README (`p80_slo.py`) |
| `engine_log_excerpts.json` | the log lines quoted above, with line numbers and log hashes |
| `recompute_check.txt` · `deidentification_ledger.json` | see Disclosures |

Not published: the container logs, AIPerf's per-request exports and inputs, the harness test directories (a 3-group short test and the sentinel trigger test), the superseded first freeze, and the stopped run of 2026-09-30 morning.
