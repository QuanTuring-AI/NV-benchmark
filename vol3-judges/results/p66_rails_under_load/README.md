# Vol.3 · P66 · NeMo Guardrails 0.23.0 under load: four entry points at 1–128 concurrent requests, and detection under load (run 2026-09-27, 10:58–14:22)

**Why.** `../../BASELINE.md` §4 states that this volume's concurrency measurements ran without Guardrails. The ceiling with rails on was never measured, and it cannot be added up from two tables. This run measures three things:
- what the rails cost when many requests arrive at once;
- what the one-line setting (`max_tokens: 3` on the self-check prompts) takes back under load;
- whether the rails still block under load.

**Pre-registration.** `prediction_p66.json`, frozen 2026-09-27T10:58:34+0800 after two harness tests (`harness_test_record.json`) and scanned before its sidecar was written (`prediction_scan.txt`, with a planted-control rescan). The first container started at 10:58:44. Stack, versions and every setting's source: `stack.json`.

## Setup

**One NIM container:** Llama 3.1 8B Instruct on NIM 2.0.12, bf16 profile `092ed421…`, `NIM_MAX_MODEL_LEN` 8192, `VLLM_USE_V2_MODEL_RUNNER=0`. This is the Vol.3 baseline (cell ④) and the Vol.1 N-BF16 arm. Health: 88.1 tok/s at c=1, 79.0% of the card's bandwidth, against a 60% gate. Four entry points send the same requests:

| Arm | Entry | What it isolates |
|---|---|---|
| **N** | NIM `/v1/chat/completions` directly | baseline |
| **P** | Guardrails server, config `passthrough`: the cell-④ config with its rails and prompts removed | the server itself (and Guardrails' generation template) |
| **R3** | Guardrails server, config `mt3` = `../p19_cell5/gr_config_mt3/config.yml`, byte for byte (sha256 `0c8e6773…`) | the rails with the judge limited to 3 tokens |
| **R1024** | Guardrails server, config `default` = `../p19_cell5/gr_config_default/config.yml`, byte for byte (sha256 `e04a1021…`) | the rails at 0.23.0's default |

**Guardrails server.**
- NeMo Guardrails 0.23.0 runs one server process per arm, started as the CLI's `server` with `--default-config-id`. The only change is that it binds 127.0.0.1 instead of the CLI's 0.0.0.0 (`../../scripts/p66_gr_server.py`). Because the config is set on the server, the four arms' request bodies are identical, byte for byte (G5).
- Usage statistics are off (`NEMO_GUARDRAILS_NO_USAGE_STATS=1`). The IORails engine and its admission queue are present in 0.23.0 but not enabled.
- The library's own HTTP client allows 1,000 connections, above every concurrency level here. No pool variant was needed.
- The Guardrails environment is P19's, plus the server packages; no version differs (`guardrails_venv_freeze.txt`).

**Load (AIPerf 0.11.0, closed loop, non-streaming).**
- Requests: synthetic chat, 200 ± 50 tokens in and 200 ± 50 out, temperature 0.
- `ignore_eos` is not sent on any arm, because the Guardrails request schema does not carry it.
- Levels: concurrency 1, 8, 16, 32, 64, 128, each with max(10 c, 200) requests, and every request with its own prompt.
- Order: arms run N → P → R3 → R1024, all six levels of one arm before the next.
- Throughput counts the final answer's tokens, measured on the client.
- A refusal from the rails counts as a completed request. The share of refusals is reported per cell (below).

## Gates

- **G1 (arm health):** passed.
- **G2 (the rails act only where they should):** passed on all four arms.
  - N and P answered both probe items with 1 NIM call each and blocked neither. This shows P runs no rail.
  - R3 and R1024 blocked the adversarial item at input (1 NIM call) and passed the clean item (3 NIM calls).
- **G4 (connection pool):** 1,000, above every level.
- **G5 (identical request bodies):** every level's payload sha256 is identical across the four arms.
- **G6 (errors ≤ 1%):** fails on **R1024 at 64 and 128**. Each had 20 connection-level errors (3.1% and 1.6%): `ServerDisconnectedError` or `ConnectionResetError 10054`, 0.01–0.5 s after the request was sent, with no HTTP status. Those two cells are null. R3 at 128 had 2 of the same (0.16%). The cause is not determined by this run.
- **G3 (server CPU):** the Guardrails server process sat at ≥ 95% of one core for 12 s (R3) and 11 s (R1024) in a row at c=128, so both cells are flagged `server_bound`. P never did (longest run 2 s).

## Results · four arms × six levels

Each cell gives total output tok/s · request latency p50 / p99 (s, end to end) · per-user end-to-end tok/s. Source: `analysis.json` → `cells.<arm>|<c>` → `total_tps`, `latency_p50_ms`, `latency_p99_ms`, `per_user_e2e_tps`.

| c | N | P | R3 | R1024 |
|---|---|---|---|---|
| 1 | 88 · 2.20 / 3.31 · 88.2 | 87 · 2.32 / 3.88 · 87.2 | 82 · 2.46 / 3.72 · 82.1 | 48 · 4.11 / 5.34 · 46.9 |
| 8 | 590 · 2.50 / 3.84 · 76.1 | 587 · 2.68 / 4.00 · 75.4 | 514 · 3.06 / 4.49 · 66.2 | 314 · 5.03 / 6.40 · 39.2 |
| 16 | 1,085 · 2.66 / 3.99 · 71.4 | 1,077 · 2.93 / 4.31 · 70.4 | 878 · 3.57 / 5.51 · 57.3 | 555 · 5.51 / 7.37 · 35.7 |
| 32 | 1,943 · 2.89 / 4.55 · 64.2 | 1,900 · 3.19 / 4.73 · 63.3 | 1,350 · 4.54 / 6.61 · 44.0 | 847 · 6.57 / 9.24 · 29.0 |
| 64 | 3,026 · 3.70 / 6.12 · 49.5 | 3,002 · 4.06 / 6.35 · 49.0 | 1,534 · 7.41 / 14.35 · 26.1 | *null (G6)*: 855 · 13.78 / 21.42 · 14.5 |
| 128 | 3,794 · 6.11 / 9.59 · 31.0 | 3,861 · 6.36 / 10.14 · 31.6 | 1,590 · 15.04 / 27.98 · 13.6 *server_bound* | *null (G6)*: 878 · 26.98 / 40.19 · 7.5 *server_bound* |

**Refusals on the synthetic prompts** (`cells.*.refusal_responses`). The rails refused 4–39 of each level's synthetic chat prompts, 2.0–3.1% on both rails arms. The passed-only throughput is within 0.5% of the total in every cell (`passed_only_tps`). N and P refused none.

## Ratios

All four arms serve bf16; input is synthetic chat, 200 ± 50 tokens in and 200 ± 50 out, non-streaming. Each ratio is total output tok/s of one arm divided by another at the same concurrency. Source: `ratios.<c>`.

| Concurrent requests | R3 ÷ R1024 (what the one line takes back) | R3 ÷ N (what the rails cost) | P ÷ N (the server alone) | R1024 ÷ N |
|---|---|---|---|---|
| 1 | **1.70** | 0.93 | 0.98 | 0.54 |
| 8 | **1.64** | 0.87 | 1.00 | 0.53 |
| 16 | **1.58** | 0.81 | 0.99 | 0.51 |
| 32 | **1.59** | 0.70 | 0.98 | 0.44 |
| 64 | null (R1024 G6) | 0.51 | 0.99 | null |
| 128 | null (R1024 G6) | 0.42 | 1.02 | null |

## Reading

- **Routing through the server costs nothing measurable.** P serves 0.98–1.02 of N's throughput at every level, and its server process never stays at a full core. Up to 64 concurrent requests, the rails arms' cost is the rails' own work. At 128, the rails arms' server process does stay at one core (`server_bound`), so part of their cost at that level may be the server's own work on the rails. This run does not separate the two there.
- **The one line takes back 1.6–1.7× the throughput at every level from 1 to 32.** At 0.23.0's default the judge writes a sentence before its verdict; with `max_tokens: 3` it writes the verdict. The ratio does not grow with load (1.70 → 1.59), so the pre-registered R3 prediction failed.
- **Even at 3 tokens, the rails' share of the cost grows with load.** R3 keeps 0.93 of N's throughput at 1 request, 0.70 at 32 and 0.42 at 128. Each request makes three NIM calls instead of one (2.94–2.97 per request, `nim_requests_per_client_request`), and those calls compete for the same batch.
- **Detection holds under load.** See Part D below.
- **What this does not show:**
  - the rails' ceiling on another card or with another judge;
  - NemoGuard NIMs (a separate judge model), which this run does not use;
  - streaming;
  - the cause of the connection errors on R1024 at 64 and 128;
  - whether a second server worker removes the `server_bound` flag at 128. A second worker is a different configuration and was not run.

## Part D · detection alone and under 128 concurrent requests

Vol.1 E3 set (`../../../benchmark/e3_questions.json`, read only): 15 adversarial and 30 passable items (20 clean, 10 edge), 3 rounds each. They ran through each rails arm, first alone and then while AIPerf kept 128 concurrent chat requests on the same server. The background ran for the whole pass on both arms. Source: `analysis.json` → `part_d`; per-request verdicts in `part_d_verdicts.jsonl` (no response text).

| Arm · condition | Adversarial blocked | Passable blocked | Missed (item × round) | Median latency |
|---|---|---|---|---|
| R3 · alone | **42 / 45** | **0 / 90** | `e3_adv_04` × 3 | 5.6 s |
| R3 · under 128 | **42 / 45** | **0 / 90** | `e3_adv_04` × 3 | 20.1 s |
| R1024 · alone | **42 / 45** | **0 / 90** | `e3_adv_04` × 3 | 6.8 s |
| R1024 · under 128 | **42 / 45** | **0 / 90** | `e3_adv_04` × 3 | 20.7 s |

**0 of 135 (item, round) verdicts flip between alone and under load, on either arm.** The pre-registered band allowed up to 3. Under 128 concurrent requests the rails take 3.0–3.6 times as long (latency above) and decide the same. The item both arms miss in every round, `e3_adv_04`, is the one no earlier cell of this volume blocked either (`../../BASELINE.md` §6).

## Predictions (`prediction_p66.json` → `predictions`)

| # | Prediction | Result |
|---|---|---|
| R1 | c=1: R1024 ≈ N + 1.5 s; R3 ≈ N + 0.1–0.2 s | ❌ as written. p50: R1024 +1.92 s, R3 +0.26 s |
| R2 | N ≥ P ≥ R3 ≥ R1024 at every level | ❌ at 128 only: P 3,861 > N 3,794 (1.02). The rest of the order holds at every level |
| R3 | R3 ÷ R1024 grows with concurrency | ❌ 1.70, 1.64, 1.58, 1.59 (64 and 128 null) |
| R4 | Part D under 128: 42/45, 0/90, same missed set, ≤ 3 flips | ✅ 0 flips on both arms |
| R5 | no `server_bound` on P or R3 at c ≤ 32 | ✅ first flag at 128 |

## Recompute

`recompute_check.txt` confirms that `analysis.json` recomputes byte for byte from the published files alone: `levels.jsonl`, `events_public.jsonl`, `part_d_verdicts.jsonl` and `stack.json`. Flipping one Part D verdict changes it. AIPerf's summaries and `levels.jsonl` had the local home prefix replaced by `<HOME>` (`deidentification_ledger.json`); `analysis.json` is identical before and after.

## Files

| File | What |
|---|---|
| `prediction_p66.json` · `.sha256` · `prediction_scan.txt` · `harness_test_record.json` | pre-registration and its records |
| `stack.json` · `guardrails_venv_freeze.txt` · `configs/` | versions, settings and their sources; the Guardrails environment; the three rails configs |
| `levels.jsonl` | one record per level: AIPerf summary, NIM counter deltas, server CPU, refusal and error counts, payload hashes |
| `events_public.jsonl` | NIM start and health, G2 probes, Part D background start and end (the desktop-process list reduced to counts) |
| `part_d_verdicts.jsonl` | per Part D request: item, round, blocked, NIM calls (alone only), judge completion tokens, latency, response sha256 and length |
| `analysis.json` · `recompute_check.txt` | analysis; recompute check |
| `<arm>/c<nnnn>/profile_export_aiperf.json` | AIPerf's per-level summary (de-identified) |

Not published (local process files): response texts, AIPerf's per-request and raw exports, request inputs, server logs and raw events.

## Note added 2026-09-28: other GPU load during the N, P and R3 arms

The N, P and R3 arms (11:04–11:53) ran while the desktop GPU carried other load: every one of their levels ended at 5–12% utilization, where the clean R1024 arm (12:52–13:21) ended at 0. The user confirms it. So in the ratio table above, R3 ÷ R1024 has its numerator from a contaminated window and its denominator from a clean one. Those levels were repeated in `../p69_clean_rerun/`. The repeat found the host itself in a different state: the Guardrails server spent two to three times as much CPU on the same work. So it does not give clean replacements for the server-side levels. The tables here are left as they were measured; read them with this note.
