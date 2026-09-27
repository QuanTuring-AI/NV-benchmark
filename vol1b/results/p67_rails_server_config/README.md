# Vol.2 · P67 · The Guardrails server's own limits, separated from the rails' cost: worker processes and keep-alive at 32–128 concurrent requests (run 2026-09-27, 15:26–17:08)

**Why.** P66 (`../p66_rails_under_load/`) left two things at 64 and 128 concurrent requests that it could not tell apart from the rails' own cost:
- both rails arms' Guardrails server stayed at one full core at 128 (`server_bound`);
- the default rails (R1024) had connection errors above 1% at 64 and 128 (`ServerDisconnectedError` / `ConnectionResetError 10054`, no HTTP status).

Both point at how the server is run, not at the rails. This run changes only the server: the number of uvicorn worker processes **W** (1, uvicorn's default, or 4) and uvicorn's keep-alive timeout **K** (5 s, its default, or 75 s).

**Pre-registration.** `prediction_p67.json`, frozen 2026-09-27T15:26:22+0800 after two harness tests (`harness_test_record.json`), scanned before its sidecar was written (`prediction_scan.txt`, with a planted-control rescan). The run started at 15:26:34. Stack, versions and every setting's source: `stack.json`.

## Setup

**Unchanged from P66:**
- the NIM container: Llama 3.1 8B Instruct, NIM 2.0.12, bf16 profile `092ed421…`, `NIM_MAX_MODEL_LEN` 8192, `VLLM_USE_V2_MODEL_RUNNER=0`;
- the three Guardrails configs, byte for byte: P `passthrough` (no rails), R3 `mt3` (self-check `max_tokens: 3`), R1024 `default` (0.23.0's default);
- the load: AIPerf 0.11.0 closed loop, non-streaming, synthetic chat 200 ± 50 tokens in and 200 ± 50 out, temperature 0, no `ignore_eos`, max(10 c, 200) requests per level with every request its own prompt;
- the seeds: 20260927 + c, so every level's request payloads are P66's.

**What changes: the server.** `../../scripts/p67_gr_server.py` is P66's server (the CLI's `server` with `--default-config-id`, bound to 127.0.0.1) with W and K exposed. Every P67 server runs it, the P66-equivalent W1K5 included. Four differences from P66's launcher, the same for every P67 server:
- the app is loaded by import string, so that each worker sets its own config;
- two response headers name the worker and the config it read;
- uvicorn's HTTP protocol logs its keep-alive closes and the connections it loses with an exception;
- the access log carries the worker's pid.

**Plan.** One NIM container and one session. W = 1 and W = 4 alternate:
- N at 32, 64 and 128;
- R1024 at 64 and 128 in all four W × K cells (W1K5, W4K75, W1K75, W4K5);
- R3 at 32, 64 and 128 as W1K5 and W4K75;
- P at 64 and 128 as W4K75 and W1K5;
- Part D on R1024 W4K75.

That is 21 cells. A pre-registered branch would have added W8 for R3 at 128 if W4 were still `server_bound` there; it was not, so W8 did not run.

**Windows.** uvicorn's workers are spawned processes that share one listening socket. In the harness tests several workers calling `listen()` at once failed and were restarted by uvicorn. The harness therefore:
- waits until all W workers answer, each from a process of the server it started;
- counts those restarts (0 in the measured run).

## Gates

- **G1 (NIM health):** 92.8 tok/s at c=1, 83.2% of the card's bandwidth, against 60%. It passed.
- **G2 (per worker):** passed at every server start. Every worker answered one adversarial and one clean E3 item:
  - on the rails configs the adversarial item was blocked at input (1 LLM call) and the clean item passed (3 LLM calls);
  - on P neither was blocked (1 call each).

  Every response carried the expected config sha256, and in every probe round the NIM request count equalled the LLM calls the responses reported.
- **G4 (client pool):** 1,000, above every level.
- **G5 (identical payloads):** every level's payload sha256 is identical across the cells that ran it.
- **G6 (errors ≤ 1%):** no cell is null. R1024 W1K5 had 6 errors at 64 (0.94%) and 6 at 128 (0.47%). R3 W1K5 had 2 at 128 (0.16%). Every other cell had 0.
- **G7 (anchor against P66): failed.** The run is valid; the gate only decides whether this run's cells may be compared with P66's.

| Anchor | P66 | P67 | Difference |
|---|---|---|---|
| N · 32 | 1,943 | 2,024 | +4.2% |
| N · 64 | 3,026 | 3,187 | **+5.3%** |
| N · 128 | 3,794 | 3,948 | +4.1% |
| R3 W1K5 · 32 | 1,350 | 1,457 | **+7.9%** |
| R3 W1K5 · 64 | 1,534 | 1,867 | **+21.7%** |
| R3 W1K5 · 128 | 1,590 | 1,809 | **+13.8%** |

  By the pre-registered rule every comparison with P66 is `null`. The table below shows P66's rows beside this run's but gives no ratio between them.
  - What this run can say: the P66-equivalent server (R3 W1K5) was 8–22% faster today, while the per-request load was the same (2.94–2.95 NIM calls per client request, the same prefix-cache hit share as P66).
  - N was 4–5% faster, and NIM's own health read 0.832 today against 0.790 in P66.
  - The cause of the rest is not determined here. One untested difference: in P66 each rails server had served the 1–32 levels, 13–21 minutes, before its 64 and 128 levels; here each server went from its warm-up straight to its levels.

## Results

### Head table: P66's 64 and 128 beside this run's W4K75

Total output tok/s. Source: `analysis.json` → `head_table`.

| c | Arm | Run | W | K (s) | Total tok/s | Errors | server_bound |
|---|---|---|---|---|---|---|---|
| 64 | N | P66 | — | — | 3,026 | 0 | no |
| 64 | N | P67 | — | — | 3,187 | 0 | no |
| 64 | P | P66 | 1 | 5 | 3,002 | 0 | no |
| 64 | P | P67 | 4 | 75 | 3,353 | 0 | no |
| 64 | R3 | P66 | 1 | 5 | 1,534 | 0 | no |
| 64 | R3 | P67 | 4 | 75 | 2,046 | 0 | no |
| 64 | R1024 | P66 | 1 | 5 | 855 *(null, G6)* | 3.12% | no |
| 64 | R1024 | P67 | 4 | 75 | 1,355 | 0 | no |
| 128 | N | P66 | — | — | 3,794 | 0 | no |
| 128 | N | P67 | — | — | 3,948 | 0 | no |
| 128 | P | P66 | 1 | 5 | 3,861 | 0 | no |
| 128 | P | P67 | 4 | 75 | 4,195 | 0 | no |
| 128 | R3 | P66 | 1 | 5 | 1,590 | 0.16% | **yes** |
| 128 | R3 | P67 | 4 | 75 | 2,301 | 0 | no |
| 128 | R1024 | P66 | 1 | 5 | 878 *(null, G6)* | 1.56% | **yes** |
| 128 | R1024 | P67 | 4 | 75 | 1,565 | 0 | no |

The ratio between the two runs is `null` (G7). The comparison that holds is inside this run: W1K5 against W4K75 under the same conditions, in the next two tables.

### R1024: the two factors

Default rails. Per cell: total tok/s, latency p50 / p99 (s), errors, uvicorn keep-alive closes counted on the server, and the longest run of one server process at ≥ 95% CPU (s). Source: `analysis.json` → `r1024_2x2`, `cells`.

| c | W · K | Total tok/s | p50 / p99 (s) | Errors | Keep-alive closes | Longest run ≥ 95% CPU (s) |
|---|---|---|---|---|---|---|
| 64 | W1 · K5 | 1,133 | 9.92 / 19.63 | 6 (0.94%) | 97 | 4 |
| 64 | W1 · K75 | 1,377 | 8.75 / 12.87 | 0 | 0 | 2 |
| 64 | W4 · K5 | 1,432 | 8.44 / 11.54 | 0 | 56 | 0 |
| 64 | W4 · K75 | 1,355 | 8.95 / 12.57 | 0 | 0 | 0 |
| 128 | W1 · K5 | 1,277 | 18.67 / 31.56 | 6 (0.47%) | 228 | 7 |
| 128 | W1 · K75 | 1,405 | 16.90 / 24.31 | 0 | 0 | 7 |
| 128 | W4 · K5 | 1,647 | 14.13 / 21.36 | 0 | 154 | 1 |
| 128 | W4 · K75 | 1,565 | 15.20 / 24.71 | 0 | 0 | 5 |

- **Errors occurred only in W1 · K5**, the one cell with both a single process and a 5 s keep-alive. Either change alone removed them: K75 at W1, or W4 at K5. W4 · K5 closed 56 and 154 idle connections without an error.
  - The errors were `ServerDisconnectedError` and `ClientOSError`, 2.6–561 ms after the request was sent, with no HTTP status.
  - The server logged nothing that matches them: at most one lost connection per level, in cells with and without client errors alike (`connections_lost`).
- **Throughput at 128:** W4 is 1.29× W1 at K5 and 1.11× at K75; K75 is 1.10× K5 at W1 and 0.95× at W4. At 64: W4 1.26× W1 at K5 and 0.98× at K75.
- **Not one of the eight cells is `server_bound`.** On the default rails this run does not show one server process as the limit.

### R3, P and N: W1K5 against W4K75

Total tok/s · p50 / p99 (s). Source: `cells`.

| Server | 32 | 64 | 128 |
|---|---|---|---|
| N (NIM directly) | 2,024 · 2.78 / 4.33 | 3,187 · 3.55 / 5.74 | 3,948 · 5.88 / 9.19 |
| R3 · W1 K5 | 1,457 · 4.10 / 6.57 | 1,867 · 6.42 / 11.01 | 1,809 · 13.13 / 23.63 · **server_bound**, 2 errors |
| R3 · W4 K75 | 1,548 · 3.86 / 5.96 | 2,046 · 5.92 / 9.38 | 2,301 · 10.65 / 16.83 |
| P · W1 K5 | — | 3,227 · 3.77 / 6.04 | 4,147 · 5.93 / 9.73 |
| P · W4 K75 | — | 3,353 · 3.62 / 5.67 | 4,195 · 5.86 / 9.67 |

- **With one process, R3 stops at one core.** R3 W1K5 gains nothing from 64 to 128 (1,867 → 1,809), and its server process sits at ≥ 95% of a core for 11 s in a row at 128. That is the same flag and roughly the same length as P66's 12 s.
- **With four workers the flag goes away and R3 keeps gaining:** 2,046 → 2,301 tok/s from 64 to 128, which is 1.27× W1K5 at 128.
- **The server with no rails costs nothing at either W:** P ÷ N is 1.01–1.06.

### Ratios in this run

Total output tok/s of one server over another at the same concurrency, all bf16, synthetic chat 200 ± 50 / 200 ± 50, non-streaming. Source: `ratios`.

| Server · c | R3 ÷ R1024 | R3 ÷ N | R1024 ÷ N | P ÷ N |
|---|---|---|---|---|
| W1K5 · 32 | — | 0.72 | — | — |
| W1K5 · 64 | 1.65 | 0.59 | 0.36 | 1.01 |
| W1K5 · 128 | 1.42 | 0.46 | 0.32 | 1.05 |
| W4K75 · 32 | — | 0.77 | — | — |
| W4K75 · 64 | 1.51 | 0.64 | 0.43 | 1.05 |
| W4K75 · 128 | **1.47** | **0.58** | 0.40 | 1.06 |

**With four workers, the rails with the one line keep 0.58 of direct NIM's throughput at 128**, against 0.46 with one process in the same session. The rest is the rails' own work: each request makes 2.95 NIM calls, and together they carry 4.3 times the prompt tokens that N's requests carry at 128 (NIM counters).

### Requests per worker

The OS gives each new connection to one worker, and a keep-alive connection stays with that worker. Under AIPerf's load one worker took 60–74% of the requests in most W4 cells (`cells.*.requests_by_worker`). The exception was R1024 W4K5 at 64: 177 / 173 / 153 / 121. Its 5 s keep-alive closed idle connections, and the new ones were spread again. No W4 worker was `server_bound`. The load is uneven, and this run does not measure what an even spread would give.

## Part D · detection under 128 concurrent requests on four workers

The Vol.1 E3 set (`../../../benchmark/e3_questions.json`, read only): 15 adversarial and 30 passable items, 3 rounds each. They ran through R1024 W4K75 while AIPerf kept 128 concurrent chat requests on the same server. The background ran for the whole pass. Source: `analysis.json` → `part_d`; per-request verdicts in `part_d_verdicts.jsonl` (no response text).

| Condition | Adversarial blocked | Passable blocked | Missed | Median latency | Flips against P66 R1024 alone (c=1) |
|---|---|---|---|---|---|
| R1024 · W4 K75 · under 128 | **42 / 45** | **0 / 90** | `e3_adv_04` × 3 | 23.5 s | **0 of 135** |

The verdicts are the same (item by item, round by round) as the default rails alone in P66. Changing the server's configuration did not change what the rails decide.

## Predictions (`prediction_p67.json` → `predictions`)

| # | Prediction | Result |
|---|---|---|
| R1 | N at 32, 64, 128 within 5% of P66 | ❌ 64 is +5.3% (32 +4.2%, 128 +4.1%) |
| R2 | K75 brings R1024's errors to ≤ 0.5%, and W does not matter | ❌ K75 gave 0 errors at both W and both levels, but W4 also removed them at K5 (−0.94 pp at 64, −0.47 pp at 128) |
| R3 | W4 removes `server_bound` from the rails cells at 128, and R3 W4K75 > R3 W1K5 at 128 | ✅ no W4 rails cell is `server_bound`; 2,301 against 1,809 |
| R4 | W4K75 R3 ÷ R1024 at 64 and 128 within 1.5–1.8 | ❌ 1.51 and 1.47 |
| R5 | Part D: 42/45, 0/90, 0 of 135 flips against P66 R1024 c1 | ✅ |

## What this does not show

- why the P66-equivalent server was faster today than in P66 (G7);
- why the errors need both one process and a 5 s keep-alive;
- the rails at W > 4, or with an even spread of connections over the workers;
- any other operating system: on Linux, uvicorn's workers share the socket differently;
- streaming;
- NemoGuard NIMs as the judge.

## Recompute

`recompute_check.txt` confirms that `analysis.json` recomputes byte for byte from the published files alone:
- this run's `levels.jsonl`, `events_public.jsonl`, `part_d_verdicts.jsonl`, `stack.json` and `prediction_p67.json`;
- P66's `analysis.json` and `part_d_verdicts.jsonl`.

Flipping one Part D verdict changes it. AIPerf's summaries and `levels.jsonl` had the local home prefix replaced by `<HOME>` (`deidentification_ledger.json`, 35 files); `analysis.json` is identical before and after.

## Files

| File | What |
|---|---|
| `prediction_p67.json` · `.sha256` · `prediction_scan.txt` · `harness_test_record.json` | pre-registration and its records |
| `stack.json` · `configs/` | versions, settings and their sources (plus `workers_observed`: each worker's pid and the config sha256 it read, added after the run; every other key equals the copy in the pre-registration); the three rails configs (P66's bytes) |
| `levels.jsonl` | one record per level: AIPerf summary, NIM counter deltas, server CPU per process, requests per worker, keep-alive closes and lost connections, errors by type, payload hashes |
| `events_public.jsonl` | NIM start and health; per server start the workers, G2 per worker and the prefix calibration; Part D background (the desktop-process list reduced to counts) |
| `part_d_verdicts.jsonl` | per Part D request: item, round, blocked, judge completion tokens, latency, response sha256 and length |
| `analysis.json` · `recompute_check.txt` · `deidentification_ledger.json` | analysis; recompute check; de-identification ledger |
| `<server>/c<nnnn>/profile_export_aiperf.json` | AIPerf's per-level summary (de-identified) |

Not published (local process files): response texts, AIPerf's per-request and raw exports, request inputs, server logs (they hold prompt text) and raw events.
