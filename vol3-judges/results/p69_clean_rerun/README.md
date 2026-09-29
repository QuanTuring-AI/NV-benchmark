# Vol.2 · P69 · The P66 / P67 levels that ran with other GPU load, measured again (run 2026-09-28, 03:56–06:05)

**Why.** P66's N, P and R3 arms (morning of 2026-09-27) and P67's first levels ended with the GPU at 3–19% utilization. A window with no other load ends at 0%. The user confirms desktop GPU use (a game) in those windows. The contamination also reached P66's headline ratio: R3 ÷ R1024 had its numerator from a contaminated window and its denominator from a clean one. The decision to repeat those levels was made from the contamination, before any clean result was seen.

**Pre-registration.** `prediction_p69.json`, frozen 2026-09-28T03:56:42+0800, scanned before its sidecar was written (`prediction_scan.txt`). The run started at 03:56:51.

## What was repeated, and how

- **The list comes from a rule, not from memory:** every level of P66's and P67's `levels.jsonl` whose `gpu_end.util_pct` was above 2, warm-ups included. That gives 33 levels: 21 in P66 and 12 in P67. The two P67 levels beyond the 10 first expected (R1024 W4K5's warm-up, P W1K5 at 64) come from the same rule. Each level is marked in `contamination_marks.jsonl`; the original files are not changed.
- **Same level, same means:** each was repeated with the same arm, server configuration (W, K), concurrency, request count and seed, through the harness function that first ran it (`../../scripts/p66_rails_under_load.py`, `p67_rails_server_config.py`, imported unchanged). All ran on one NIM container.
- **Same window for the ratio:** P66's R3 at 1, 8, 16 and 32 alternated with R1024 at the same levels, so that R3 ÷ R1024 has both terms from one window.
- **Gates:**
  - **G8 before every level:** the GPU otherwise idle, utilization p50 ≤ 2% and power p50 ≤ 45 W (`../../../tools/g8_gate.py`). All 46 checks passed, each after 11 s. The positive control, sampled while NIM decoded, read 99% and 428 W.
  - **No-overwrite check after every level:** passed.
  - **Wall-clock timeout per level** (`../../../tools/cell_timeout.py`). None fired. It was added after the first harness test stopped progressing on P67's R1024 W4K75 at 64; that state was recorded before it was stopped (`hang_evidence_p69_test_20260927T214149.json`).
- **Not repeated:** Part D. A verdict does not depend on speed.

## 🔴 What this run found: the GPU was clean, the host was not the same

**NIM directly (arm N) was 5–12% faster at every level than in its contaminated run**, as expected from a clean GPU. P67's N and P66's N, both re-run here, agree within 0.4% at 32, 64 and 128 (R2 ✅).

**Every level that goes through the Guardrails server was slower than in P66 and P67, and more so the higher the load.** The server process spent two to three times as much CPU on the same work. Source: `levels.jsonl` → `server_cpu`, against P66's and P67's own records.

| Level | Original: tok/s · server CPU p50 | This run: tok/s · server CPU p50 |
|---|---|---|
| P · 8 | 587 · 6% | 630 · 21% |
| P · 32 | 1,900 · 18% | 2,064 · 42% |
| P · 128 | 3,861 · 49% | 2,528 · 92% |
| R3 · 8 | 514 · 17% | 496 · 46% |
| R3 · 32 | 1,350 · 51% | 1,026 · 84% |
| R3 · 128 | 1,590 · 94% | 1,095 · 97% |
| P W1K5 · 64 (P67) | 3,227 · 32% | 2,573 · 59% |

G8 checks the GPU only; nothing checked the host. The cause is **not determined**. One candidate, not tested: this host has performance and efficiency cores, and Windows may schedule a background process such as the server onto efficiency cores or a lower clock in these hours. The core type and clock were not recorded.

⇒ **This run does not give clean replacements for the server-side levels.** Their numbers carry a second variable (the host's state) that the original run did not have, or had in a different measure. They are reported below as measured, and not used to replace P66's or P67's server-side numbers in any headline.

## Results

### Same window: R3 and R1024 at 1–32 (P66's servers: one process, keep-alive 5 s)

Source: `analysis.json` → `same_window_R3_over_R1024`.

| c | R3 tok/s | R1024 tok/s | R3 ÷ R1024 |
|---|---|---|---|
| 1 | 83 | 48 | 1.74 |
| 8 | 496 | 311 | 1.60 |
| 16 | 815 | 551 | 1.48 |
| 32 | 1,026 | 835 | 1.23 |

The ratio falls as the load rises, where P66's did not (1.70 → 1.59). With the server itself slower in this run, the fall cannot be attributed to the rails.

### NIM directly, clean (`analysis.json` → `p66_clean_view.cells`)

| c | 1 | 8 | 16 | 32 | 64 | 128 |
|---|---|---|---|---|---|---|
| N tok/s | 98 | 653 | 1,192 | 2,171 | 3,340 | 4,144 |
| against the contaminated original | 1.11 | 1.11 | 1.10 | 1.12 | 1.10 | 1.09 |

### Contaminated against re-run, every level (`analysis.json` → `contaminated_vs_clean`, descriptive only)

What the other load was doing in the original windows is not known, and the server-side re-runs carry the host difference above. So these ratios are recorded, not interpreted.

## Predictions (`prediction_p69.json` → `predictions`)

| # | Prediction | Result |
|---|---|---|
| R1 | G8's positive control does not pass; G8 passes before every level | ✅ 99% / 428 W refused; 46 / 46 passed |
| R2 | P67's N anchors within ±5% of P66's N, both clean | ✅ +0.0%, +0.4%, +0.3% |
| R3 | R3 ÷ R1024 at 1–32 within 1.5–1.8 | ❌ 1.74, 1.60, 1.48, 1.23 |
| R4 | contaminated against clean, reported only | reported (table above) |

G7 recomputed on clean N cells passes on N. It fails on P67's R3 W1K5 anchors: P67's afternoon cells are 42–85% above this run's. That is the host difference again, not a finding about the rails.

**In `p67_clean_view`, cells replaced from this run sit beside P67's own afternoon cells. Its cross-cell ratios mix the two host states and must not be quoted.**

## Recompute

`recompute_check.txt` confirms that `analysis.json` recomputes byte for byte from `levels.jsonl`, `events_public.jsonl` and `contamination_marks.jsonl`, plus P66's and P67's published files. Flipping the positive control's record changes it. AIPerf's summaries were de-identified (`deidentification_ledger.json`).

## Files

| File | What |
|---|---|
| `prediction_p69.json` · `.sha256` · `prediction_scan.txt` | pre-registration and its scan |
| `contamination_marks.jsonl` | the 33 original levels, their fingerprint and the user's report |
| `levels.jsonl` · `events_public.jsonl` | every re-run level (AIPerf summary, NIM counters, server CPU per process, G8 record, timeout); server starts, G2, G8 samples, no-overwrite checks |
| `analysis.json` · `recompute_check.txt` · `deidentification_ledger.json` | analysis; recompute check; de-identification ledger |
| `hang_evidence_p69_test_20260927T214149.json` | the state of the first harness test when it stopped progressing |
| `configs/` | P67's three Guardrails configs (same bytes) |
| `<run>_<label>/c<nnnn>/profile_export_aiperf.json` | AIPerf's per-level summary (de-identified) |

Not published: AIPerf per-request exports, server logs (they hold prompt text), raw events, the harness tests.
