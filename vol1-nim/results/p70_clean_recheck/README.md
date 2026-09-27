# Vol.1 · P70 · The 128-request headline re-checked in a clean window (run 2026-09-27, 20:58–21:41)

**Why.** P59 is the source of this volume's headline: at 128 concurrent chat requests, NIM bf16 delivered 5,458 tok/s against 741 for the 4-bit Ollama build, a ratio of 7.4×. P59 ran on 2026-09-25 from 02:32 to 06:44 with other load on the desktop GPU:
- its idle sample before the first container read 19% utilization and 50 W (`../p59_nim_value/ctx.txt`);
- its levels ended at 3–23% utilization.

A window with no other load ends at 0%. P59's arms ran one after another, 30–60 minutes apart, so the background need not have been the same for each arm, nor cost each arm the same share. The decision to re-measure was made from that fingerprint, before any clean number was seen.

**Pre-registration.** `prediction_p70.json`, frozen 2026-09-27T20:58:07+0800, scanned before its sidecar was written (`prediction_scan.txt`, with a planted-control rescan). The run started at 20:58:29.

## Setup

- **P59's harness, imported unchanged** (`../../scripts/p59_nim_value.py`). Everything that defines a cell is the same:
  - images, recorded by digest: NIM 2.0.12 `d2c94c1d…`, Ollama `8262851b…` (0.34.4);
  - NIM profiles: bf16 `092ed421…`, fp8 `c4789f7a…`;
  - Ollama models, and the slot counts P59 fitted (4-bit 16, fp16 8), set directly rather than fitted again;
  - context 8,192;
  - isolation check, prefix-cache detector, a discarded 120 s warm-up, calibration;
  - the AIPerf command: streaming, profile C (200 / 200 tokens), 60 s per level, seed 20260925 + c;
  - driver 591.86.
- **Levels and order:** 1, 32 and 128 concurrent requests. One container per configuration, in the order N-BF16 → O-Q4 → N-FP8 → O-FP16, each running its three levels. That is four container starts instead of twelve.
- **Differences from P59, per cell:** P59's containers also ran 8, 16 and 64, and profile R after C; here only 1, 32 and 128. The slot counts were set, not re-fitted. Nothing else differs.
- **G8 environment gate before every cell** (`tools/g8_gate.py`): the GPU is sampled for 10 s at 1 Hz and must show utilization p50 ≤ 2% and power p50 ≤ 45 W, or the cell is null after at most 15 min of retries.
  - The positive control, sampled while the first NIM container decoded four streams, read 99% and 446 W, so the gate can fail.
  - All nine run cells passed at 0% utilization and 15–38 W, after waiting 11–152 s.
- **No-overwrite gate after every cell** (`tools/overwrite_gate.py`): tracked files unchanged, and new files only under this directory. All nine checks passed.

## Result

Total output tok/s; P59's same cell; this run ÷ P59. Source: `analysis.json` → `cells`, `ratios_128`.

| Configuration | c=1 | c=32 | c=128 |
|---|---|---|---|
| N-BF16 (NIM, bf16) | 97 · 87 · 1.115 | 2,538 · 2,262 · 1.122 | **6,043** · 5,458 · 1.107 |
| O-Q4 (Ollama, 4-bit) | 191 · 172 · 1.111 | 776 · 755 · 1.028 | **780** · 741 · 1.053 |
| O-FP16 (Ollama, fp16) | 88 · 79 · 1.108 | 440 · 390 · 1.130 | 440 · 402 · 1.096 |
| N-FP8 (NIM, fp8) | *null* | *null* | *null* |

| Ratio at 128 | This run | P59 | This ÷ P59 |
|---|---|---|---|
| **N-BF16 ÷ O-Q4 (the headline)** | **7.75** | 7.37 | 1.05 |
| N-BF16 ÷ O-FP16 | 13.72 | 13.59 | 1.01 |
| N-FP8 ÷ O-Q4 | *null* | 11.76 | — |

At one request the 4-bit build is still faster: N-BF16 ÷ O-Q4 = 0.507 (P59 0.505).

**N-FP8 is null.** Its container was refused by P59's prefix-cache detector.
- **What the detector checks:** it sends two different prompts, and the second's time to first token must not fall below 0.70 × the first's. Here it was 117 ms against 219 ms (0.535).
- **Not autotuning:** the engine's fp8 autotuning ran from 13:27:32 to 13:28:11 UTC, before the server reported ready (`logs/p70-n-fp8.startup.log.txt`), and the detector ran after that.
- **Borderline before:** in P59 the same check read 0.716 and 0.859 on this configuration.
- **What was done:** the cause is not determined here. The gate was not changed, and the arm was not run a second time.

## Predictions (`prediction_p70.json` → `predictions`)

| # | Prediction | Result |
|---|---|---|
| R1 | N-BF16 ÷ O-Q4 at 128 within 6.7–8.1 | ✅ 7.745 |
| R2 | N-FP8 ÷ O-Q4 and N-BF16 ÷ O-FP16 at 128 each within P59 ± 10% | ❌ N-FP8 ÷ O-Q4 is null; N-BF16 ÷ O-FP16 is 13.72 against 13.59 (+1%) |
| R3 | at 1 request, O-Q4 faster than N-BF16 | ✅ 0.507 |
| R4 | each cell beside P59's, reported only | every cell that ran was 3–13% faster than in P59 (table above). This run does not say by how much the other load slowed P59. |

## Recompute

`recompute_check.txt` confirms that `analysis.json` recomputes byte for byte from `levels.jsonl` and `events_public.jsonl` alone (P59's `analysis.json` is read from its own directory). Setting the G8 record before N-BF16 at 128 to failed changes it.

## Files

| File | What |
|---|---|
| `prediction_p70.json` · `.sha256` · `prediction_scan.txt` | pre-registration and its scan |
| `levels.jsonl` · `events_public.jsonl` | per level: AIPerf summary and checks; per container: isolation, detector, calibration, G8 records with every sample, no-overwrite checks (the desktop-process list reduced to counts) |
| `analysis.json` · `recompute_check.txt` | analysis; recompute check |
| `versions.txt` · `ctx.txt` | image digests, driver, AIPerf version; idle and end GPU samples |
| `<arm>_C_main/c<nnnn>/profile_export_aiperf.json` | AIPerf's per-level summary (de-identified) |

Not published (local process files): AIPerf's per-request exports and inputs, container logs, raw events.
