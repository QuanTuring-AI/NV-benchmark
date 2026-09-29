# Vol.3 · long context at ~120k prompt tokens on both arms (run 2026-09-23, 17:29–17:46)

**Question.** `../p53_longctx/` stopped at 57k prompt tokens because of its character budget, not because of a limit. The external DGX Spark measurement of Nemotron 3 Nano runs to 100k context. This run adds one point at ~120k on each arm, so the shape can be compared over that range. Only the shape is compared; absolute values from another machine and stack are never set side by side. Pre-registration `prediction_p55_longctx_120k.json`, frozen 2026-09-23T16:27:31+0800 after a harness test (its basis discloses that test's numbers; the prediction ranges were written before it) and scanned before its sidecar was written (`prediction_scan.txt`); first request 17:35:52.

Every row: `NIM_MAX_MODEL_LEN` 131,072 · `max_num_seqs` 32 · `max_tokens` 256 · temperature 0 · prompts built exactly as in `../p53_longctx/` (Vol.1 questions concatenated; synthetic, not natural text) with a character budget sized from that run's measured tokens-per-character, targeting 120,000 prompt tokens · warm-up at the measured depth (A2: until the last three rates agree within 5% and are ≥ 180 tok/s; A1: the minimum of 60 s and 6 requests) · five measured requests, medians. **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12; **A1** Nemotron Nano 9B v2 · bf16 · NIM 1.12.2. All preconditions held on both arms.

## Result

| | A2 · NVFP4 · NIM 2.0.12 | A1 · bf16 · NIM 1.12.2 |
|---|---|---|
| Starts at `NIM_MAX_MODEL_LEN` 131,072 | yes (401 s to READY) | yes (216 s) |
| Measured prompt tokens (median) | 119,725 | 119,721 |
| **TTFT**, median (ms) | **7,281** (7,256–7,392) | **14,263** (14,234–14,308) |
| **Generation rate**, median (tok/s) | **308.4** (304.0–309.7) | **52.4** (50.8–54.0) |
| First request at this depth (TTFT) | 13.6 s | 36.6 s |
| Memory at READY · KV tokens | 29,448 MiB · 3,173,760 (fp8) | 29,542 MiB · 456,131 (bf16; chunked prefill on) |

### The shape, against this volume's earlier depths

| Arm | Reference | Generation at ~120k ÷ reference | TTFT at ~120k ÷ reference |
|---|---|---|---|
| A2 | `../p53_longctx_addendum/` (warmed), 1k: 304.8 tok/s, 95 ms; 57k: 309.0 tok/s, 2,371 ms | **1.01** of 1k · 1.00 of 57k | 76× of 1k for 105× the tokens · 3.1× of 57k for 2.1× the tokens |
| A1 | `../p55_a1_capture/` (same session), ~14k default: 55.7 tok/s, 1,341 ms | **0.94** of 14k | 10.6× for 8.4× the tokens |

**A2's generation rate does not fall with context from 1k to 120k prompt tokens on this card** (304.8 → 308.4 tok/s). The external DGX Spark measurement reports −8.5% from 0 to 100k. On this card and stack the decay is inside the run-to-run spread. TTFT grows a little faster than the token count from 57k to 120k (3.1× for 2.1×), consistent with the attention layers' cost growing faster than linearly at this depth (not measured separately).

**A1 serves ~120k prompts, with a plateau past 8k that continues to 120k.** It generates at 52.4 tok/s, 0.94 of its same-session 14k rate, past the CUDA-graph step that `../p55_a1_capture/` measured. At `NIM_MAX_MODEL_LEN` 131,072 the image switches chunked prefill on and keeps 456k KV tokens, enough for 3.8 requests of this length.

**Neither arm has a context ceiling within 131,072 tokens on this card.** 131,072 is the largest model length tried; the models advertise 128k contexts.

## Two readings to keep straight

- `analysis.json` compares each arm with a reference run passed on the command line. For A2 it picked the unwarmed main run (1k: 128 tok/s), because both reference runs have four depths and the tie went to the first one given. The analyser's own description says A2 should use the addendum. The frozen analyser was run again, unchanged, on a copy of this run's rows with the reference order swapped; the result is `analysis_ref_order_addendum_first.json`. Every field is identical except `vs_reference`, and the A2 figures above come from it.
- A1's absolute rates in this session ran up to about 20% above the earlier runs' (see `../p55_a1_capture/README.md`). That is why A1 is compared with the same session's 14k point rather than with the earlier run's 57k point (44.4 tok/s); against that older point the ratio would read 1.18.

**Pre-registered predictions.** **R1** both arms start and serve at 131,072 with a ~120k prompt: held. **R2** A2 generation within 10% of its 1k value: held (1.01). **R3** A2 TTFT 4.5–9 s: held (7.3 s). **R4** A1 generation 38–48 tok/s: **failed** (52.4, the session difference). **R5** A1 TTFT 12–30 s: held (14.3 s).

## Files

`prediction_p55_longctx_120k.json` + `.sha256` + `prediction_scan.txt` · `requests.jsonl` (warm-up rows marked; digests and lengths, no text) · `events.jsonl` · `analysis.json` (frozen analyser as run) · `analysis_ref_order_addendum_first.json` (the same analyser, reference order swapped) · `ctx.txt`. Harness `../../scripts/p55_depth.py`, analysis `../../scripts/p55_depth_analyze.py`, runner `../../scripts/run_p55_depth.sh` (`EXP=longctx_120k`). `logs/` and `harness_test/` are not published.
