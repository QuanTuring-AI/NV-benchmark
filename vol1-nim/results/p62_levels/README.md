# Vol.1-A revisit · P62 Q2 + Q4 · the chat profile at 1, 2, 4 and 8 concurrent requests, and where Ollama 4-bit stops being flat (run 2026-09-26, 14:53–15:53)

**Why.** P59 measured 1, 8, 16, 32, 64 and 128 concurrent requests. On the chat profile, N-BF16 was behind Ollama 4-bit (O-Q4) at 1 and ahead at 8, so the crossing could only be placed "between 1 and 8". Q2 adds 2 and 4 on all five P59 configurations, with 1 and 8 in the same session as anchors.

P59 also left an oddity. O-Q4, with 16 slots, served no more at 8 concurrent requests than at 1: 175 against 172 tok/s. Before this run, P59's own per-request timestamps were read without the GPU. At c=8, up to 8 requests were decoding at the same moment, and all 8 were for about two thirds of the level. So the slots were in use, and that reading could not say why eight decodes add nothing. Q4 is the ticket's one targeted re-run: O-Q4 at 4, 8, 9, 12 and 16 in one container, with `ollama ps` sampled throughout.

**Pre-registration and harness.**
- The pre-registration is `prediction_p62_levels.json`, frozen 2026-09-26T14:52:44+0800 after a harness test and scanned before its sidecar was written (`prediction_scan.txt`, with a planted-control rescan). The first container started at 14:53:31.
- The harness is `vol1-nim/scripts/p62_levels.py`, which imports P59's harness unchanged: images, models, context 8,192, isolation check, prefix-cache detector, discarded 120 s warm-up, 20-request calibration, 60 s levels and `--use-legacy-max-tokens`.
- Slot counts are the ones P59 found: O-Q4 16, O-FP16 8, O-Q4-def not set.
- The analysis is `vol1-nim/scripts/p62_levels_analyze.py`, which runs P59's frozen analysis program on these files.
- c=9 was added to the ticket's 4, 8, 12, 16 to test one hypothesis (below). `ollama ps` was sampled about every 1.3 s, not every second, because each sample is a `docker exec`.
- The G1 scorer controls of Q1 (CPU only) ran during this run's O-Q4 arm.

**Checks.**
- Every arm passed residency and health: 55.6–83.0% of peak bandwidth at c=1 (`analysis.json` → `arms.*.gate_health.share_of_peak`).
- Every arm passed its container checks and its profile-C calibration (`arms.*.calibration.C.pass`).
- Every anchor is within 0.85–1.15 of P59's value for the same cell, ranging from 0.955 to 1.146 (`anchors_vs_p59`).
- All 433 `ollama ps` samples show 100% GPU (`q4.ollama_ps_samples`).
- As in P59, every level is flagged "truncation unverified": AIPerf did not request server token counts.

## Q2 · profile C, 1–8 concurrent requests

Each cell gives total tok/s · per-user tok/s (1 / inter-token latency) · p99 TTFT (ms). Source: `analysis.json` → `levels.<arm>|C|main.<c>` → `total_tps`, `per_user_tps`, `ttft_p99_ms`.

| c | O-Q4 | O-Q4-def | O-FP16 | N-BF16 | N-FP8 |
|---|---|---|---|---|---|
| 1 | 175 · 203 · 203 | 176 · 202 · 178 | 82 · 87 · 189 | 92 · 93 · 39 | 149 · 150 · 21 |
| 2 | 183 · 119 · 218 | 191 · 202 · 1,585 | 94 · 53 · 208 | 173 · 89 · 56 | 284 · 145 · 33 |
| 4 | 188 · 54 · 268 | 190 · 201 · 3,806 | 109 · 30 · 1,896 | 335 · 86 · 81 | 580 · 149 · 161 |
| 8 | 186 · 27 · 4,729 | 190 · 201 · 9,114 | 363 · 51 · 2,565 | 633 · 82 · 142 | 1,093 · 141 · 179 |

End-to-end speed per user (output tokens / request latency, queue and prefill included; `e2e_per_user.json` → `levels.<arm>|C|main.<c>.e2e_output_token_throughput_per_user_avg`):

| c | O-Q4 | O-Q4-def | O-FP16 | N-BF16 | N-FP8 |
|---|---|---|---|---|---|
| 1 | 175 | 175 | 82 | 92 | 149 |
| 2 | 105 | 97 | 50 | 88 | 143 |
| 4 | 51 | 50 | 29 | 85 | 146 |
| 8 | 25 | 29 | 48 | 81 | 138 |

**Crossings** (`crossings`, P59's rule; a change of sign between two measured levels, never interpolated):

| Pair | Total throughput | Per-user (1 / ITL) |
|---|---|---|
| N-BF16 vs O-Q4 | **between 2 and 4**: N-BF16 ahead from 4 | **between 2 and 4**: N-BF16 ahead from 4 |
| N-BF16 vs O-Q4-def | **between 2 and 4**: N-BF16 ahead from 4 | O-Q4-def ahead throughout 1–8 (it decodes one request at a time; the others wait, see its TTFT) |
| N-BF16 vs O-FP16 | N-BF16 ahead throughout 1–8 | N-BF16 ahead throughout 1–8 |
| N-FP8 vs N-BF16 | N-FP8 ahead throughout 1–8 | N-FP8 ahead throughout 1–8 |

At 2 concurrent requests, O-Q4 serves 183 tok/s in total against N-BF16's 173. At 4, it serves 188 against 335.

## Q4 · O-Q4 from 1 to 16 concurrent requests, one container

Total tok/s and the share of the level's time during which *k* requests were decoding at once (first token to last, from AIPerf's per-request timestamps). Sources: `analysis.json` → `q4.total_tps_by_level`, `q4.decoding_at_once`; `concurrency.jsonl`.

| c | Total tok/s | Most decoding at once | Share of time with all *c* decoding |
|---|---|---|---|
| 1 | 175 | 1 | 86% |
| 2 | 183 | 2 | 86% |
| 4 | 188 | 4 | 82% |
| 8 | 186 | 8 | 63% |
| 9 | 184 | 9 | 73% |
| 12 | 243 | 12 | 65% |
| 16 | 656 | 16 | 43% |

- **flat_to_8 holds.** Total at c=4 is 1.073× and at c=8 1.062× the total at c=1 (`q4.flat_to_8`).
- **The step is between 12 and 16, not between 8 and 9.** c=9 is 0.988× and c=12 1.306× of c=8; c=16 is 3.522× (`q4.step`).
- **All 433 `ollama ps` samples show 100% GPU** (`q4.ollama_ps_samples`), so the flat range is not a spill to the CPU.

**Reading.** The slots are in use: at c=8, all 8 requests decode at once 63% of the time. Yet from 1 to 12 concurrent requests the total stays at 175–243 tok/s, and at 16 it reaches 656. The pre-registered hypothesis was a batch-size limit of 8 on one code path, which would put the step between 8 and 9. **That hypothesis failed (L7).** Why the total stays flat up to 12 and rises by 16 **cannot be determined from this run**. It measures throughput and residency, not the decoder's internal choices.

O-FP16 shows a similar shape at a lower scale (82, 94, 109, then 363 tok/s at 1, 2, 4, 8). Its level 8 equals its slot count. P59's O-FP16 reached 408 at 16.

P59's O-Q4 at c=8 and this run's agree: 175 and 186 tok/s. The ticket asked why c=8 is slower than c=1.
- In total throughput it is not slower in either run; the two are equal.
- Per user it is about 7 times slower: 25 against 175 tok/s end to end. This follows from an equal total shared by 8 requests.

The open question is therefore why the total does not grow, and it remains open.

One level stands out. O-Q4's p99 TTFT at c=8 is 4,729 ms, against 652 ms at c=9. It is reported as measured; nothing was re-run.

## Predictions (`prediction_p62_levels.json` → `predictions`)

| # | Prediction | Result |
|---|---|---|
| L1 | N-BF16 vs O-Q4 total crossing between 2 and 4 | ✅ between 2 and 4 |
| L2 | N-BF16 vs O-Q4-def total crossing between 2 and 4 | ✅ between 2 and 4 |
| L3 | N-BF16 vs O-Q4 per-user crossing between 2 and 4 | ✅ between 2 and 4 |
| L4 | N-BF16 ahead of O-FP16, N-FP8 ahead of N-BF16 at every level 1–8 | ✅ |
| L5 | every anchor within 0.85–1.15 of P59 | ✅ 0.955–1.146 |
| L6 | O-Q4 flat to 8 | ✅ 1.073 / 1.062 |
| L7 | O-Q4 step between 8 and 9 | ❌ between 12 and 16 |
| L8 | every `ollama ps` sample 100% GPU | ✅ 433 / 433 |

## Files

| File | What |
|---|---|
| `prediction_p62_levels.json` · `.sha256` · `prediction_scan.txt` | pre-registration, sidecar, scan record |
| `levels.jsonl` | one record per level (AIPerf summary, checks) |
| `events_public.jsonl` | container starts, detector, calibration, gates. The raw `events.jsonl` lists desktop processes holding a GPU context with personal paths and is not published; `events_public.jsonl` replaces that list with counts. The analysis run on it reproduces `analysis.json` byte for byte. |
| `concurrency.jsonl` | per level: most requests decoding at once, share of time by count |
| `ollama_ps_O-Q4.jsonl` | the `ollama ps` row sampled during O-Q4's levels |
| `analysis.json` · `e2e_per_user.json` | analysis; end-to-end per-user speed |
| `<arm>_C_main/c<nnnn>/profile_export_aiperf.json` (and, NIM arms only, `server_metrics_export.json`) | AIPerf's per-level summary and server-metrics export (Ollama exposes no metrics endpoint). The local home prefix is replaced by `<HOME>` (`deidentification_ledger.json`); the analysis is byte-identical on the originals. |
| `versions.txt` · `ctx.txt` | image digests, AIPerf version, GPU state before and after |
