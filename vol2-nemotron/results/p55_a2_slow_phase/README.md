# Vol.2 · A2's slow first phase after READY: what the records on disk can and cannot say (no GPU run)

**Question.** Nemotron 3 Nano (A2, NIM 2.0.12, NVFP4) sometimes serves its first requests after READY at roughly half its steady rate. Is there a mechanism in the container's own logs, and how many warm-up requests does a deployment need? This is an analysis of records that already exist; no container was started for it. Program: `../../scripts/p55_a2_slow_phase.py` → `slow_phase.json`.

**Definition.** A request is "slow" when its generation rate is below 220 tok/s. That is the threshold the long-context addendum's warm-up used: every slow-phase rate seen was ≤ 209 tok/s and every steady rate ≥ 256 tok/s, at any prompt depth. The slow phase of a container is its run of leading slow requests.

## What the request records show

| Run · container (A2, `max_num_seqs` 32) | Position among the run's A2 containers | Leading slow requests / requests sent | Ended before stop | Seconds from first request to first fast one |
|---|---|---|---|---|
| `p53_longctx` · 1k | 1 | 5 / 6 | yes | 24 |
| `p53_longctx` · 4k | 2 | 3 / 6 | yes | 11 |
| `p53_longctx` · 16k | 3 | 1 / 6 (the discarded 1k-prompt request) | yes | 2 |
| `p53_longctx` · 64k | 4 | 1 / 6 (the same) | yes | 2 |
| `p53_longctx_addendum` · 1k | 1 | 7 / 21 | yes | 33 |
| `p53_longctx_addendum` · 4k, 16k, 64k | 2, 3, 4 | 0 | — | 0 |
| addendum harness test 05:43 · 1k | 1 | 6 / 6 | **no** | — (≥ 31 s) |
| addendum harness test 06:15 · 1k | 1 | 7 / 7 | **no** | — (≥ 36 s) |
| addendum harness test 06:56 · 1k | 1 | 2 / 8 | yes | 11 |

The last three rows come from harness tests whose directories are not published; their request records are summarised in `slow_phase.json`. Two further observations from unpublished records: a clock diagnosis on 2026-09-23 06:03 (a fresh A2 container, 1k prompts, `nvidia-smi` every 0.5 s) saw 3 slow requests while the SM clock already ran at 2.9 GHz at 130–230 W and 100% utilisation; the first A2 container after a Docker restart at 15:36 the same day, sent 200-token prompts at concurrency 1 for 20 s, showed none (302.9 tok/s over 31 requests).

## What the container logs show

For the eight containers whose full logs were saved, the latest line carrying a timestamp is the end of FlashInfer's kernel autotuning, 12–21 s **before** READY (READY taken as the recorded start event minus the harness's 5 s pause). After READY the engine writes only untimestamped access lines. Nothing in the logs coincides with the slow requests: no autotuning, compilation, JIT or graph-capture line. Autotuning itself runs in every container, saving 106 configurations each time into a cache directory that sits in the mounted NIM cache, and takes 12–67 s for its longest kernel. Its duration does not track the slow phase: 67 s preceded both the longest completed slow phase (7 requests) and one of the shortest (2 requests), and 12 s preceded none.

## Reading (the attribution field has three allowed values; this one is the third)

**Unverified: no mechanism found in the logs.** The engine logs nothing during the slow phase, so the logs cannot confirm or exclude a runtime cause. One pattern is visible and confounded: every long slow phase happened in the **first A2 container of its run**, and in both long-context runs that container was also the **1k-prompt** container. Position and prompt length cannot be separated with these records. The one first container sent short (200-token) prompts, after a Docker restart, showed no slow phase in 20 s; that argues against position alone, but it is a single container. No cache-mount difference between containers was found: all used the same mounted NIM cache.

## For a deployment or a demo

A2 can need a warm-up after READY. On these records the slow phase that ended lasted at most **7 requests, 33 s**. Two containers were still slow after 6 and 7 requests (31–36 s) when stopped. The rule this volume uses is safer than a fixed count: send warm-up requests until the generation rate has been at steady state for three requests in a row. In the long-context addendum that took 11–18 requests and 63–65 s per container, including a 60 s minimum. A1 (Nemotron Nano 9B v2, NIM 1.12.2, bf16) showed no slow phase in any container.

## Files

`slow_phase.json` (per container: requests in order with generation rates and TTFT, leading slow count, whether it ended, seconds to the first fast request, position in the run, READY time, and from the saved log the latest timestamped line and the autotune duration). Program `../../scripts/p55_a2_slow_phase.py`. The container logs it reads are under the runs' `logs/` directories and are not published.
