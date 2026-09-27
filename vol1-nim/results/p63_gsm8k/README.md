# Vol.1-A revisit · P63 · GSM8K on the four configurations with the generation cap at 1024 (run 2026-09-27, 00:24–01:11)

**Why.** P62's GSM8K cells came out null under two gates that were defined wrongly (see `../p62_quality/README.md`):
- The first was "output reached the cap in under 1% of items". With lm-eval's default cap of 256 tokens, even the reference reached it on 3.2% of items.
- The second was a noise floor that tested a quantity the paired interval already contains.

This is a new measurement under a new pre-registration, not P62's data re-scored under new rules. Only GSM8K was re-run, with two changes:
- The generation cap is 1024 instead of 256.
- N-BF16 is run twice, so that "N-BF16 against itself" serves as the positive control the ±2 pp verdicts require.

**Pre-registration and scope.**
- The pre-registration is `prediction_p63_gsm8k.json`, frozen 2026-09-27T00:24:15+0800 after one harness test (`harness_test_record.json`). It was scanned before its sidecar was written (`prediction_scan.txt`, with a planted-control rescan). The first container started at 00:24:59.
- Scope: answer quality on GSM8K (`gsm8k_cot_llama`, all 1,319 items) with lm-eval 0.4.13. The tool (package list `lmeval_venv_freeze.txt`, unchanged since P62), prompt format, 8-shot multi-turn chat, concurrency 8 and temperature 0 are all as in P62. The comparison is between arms, item by item. Absolute accuracies depend on the prompt format and are not set beside other publications' numbers.

**What changed from P62.** Harness `vol1-nim/scripts/p63_gsm8k.py`, which imports P62's harness unchanged:
1. lm-eval `gen_kwargs` `max_gen_toks=1024`. **Every request of every run carried `max_tokens` 1024**, per the proxy's own record (`analysis.json` → `runs.*.max_tokens_seen` = `[1024]`, 5 of 5 runs).
2. Each item is joined to its proxy record by lm-eval's own response, not only by prompt. This is P62's post-run correction, applied from the start; GSM8K has no repeated prompts, and every item joined in every run.

## Gates (all passed)

| Gate | Result | Source (`analysis.json`) |
|---|---|---|
| G1 scorer controls (P62's; same tool and task, and the cap does not affect the scorer) | reference answers 100%, permuted 1.4% | `g1_scorer_controls` |
| cap check | `max_tokens` 1024 on every request, 5 / 5 runs | `runs.*.max_tokens_seen` |
| G2a prompt tokens (±5% of N-BF16 after the constant template offset) | 0 items outside. Offset 25 tokens on both Ollama arms, 0 on the NIM arms | `cells.*.g2a` |
| G3 residency and health | health 56.3% (O-Q4), 78.3% (O-FP16), 83.3% (N-BF16), 73.6% (N-FP8) of peak bandwidth; all resident | `cells.*.g3` |
| G4 identical requests | 0 request-hash mismatches | `cells.*.g4` |
| join | 1,319 / 1,319 on every run; 0 text mismatches | `runs.*.join` |

## The equivalence method passes its own test

N-BF16 was run twice in the same container. The second run minus the first is **0.00 pp [−0.83, +0.83]**, McNemar p 1.00. The two runs are both 85.60%; 15 items flipped each way, and 69.7% of the outputs are identical. The interval lies inside ±2 pp, so the method can call a configuration equal to itself at this size (`positive_control`).

## Results

Accuracy % (strict-match exact match) with its Wilson 95% interval, and the share of outputs that reached the 1024-token cap. An output at the cap is scored as lm-eval scores it (wrong in practice), because it is the model's own behaviour. Source: `cells.<arm>.accuracy_pct`, `.wilson95_pct`, `.correct`/`.n`, `.length_share`.

| Arm | Accuracy | Correct | Reached the cap |
|---|---|---|---|
| N-BF16 | **85.6** [83.6, 87.4] | 1,129 / 1,319 | 0.83% (repeat 0.76%) |
| N-FP8 | **84.1** [82.0, 86.0] | 1,109 | 0.91% |
| O-FP16 | **84.3** [82.2, 86.2] | 1,112 | 0.30% |
| O-Q4 | **83.2** [81.1, 85.1] | 1,097 | 0.38% |

**Paired against N-BF16:** arm minus reference, paired bootstrap 95% interval, exact McNemar p, verdict against ±2 pp. Source: `comparisons.<arm>`.

| Arm | Difference | 95% interval | McNemar p | Verdict |
|---|---|---|---|---|
| N-FP8 | −1.52 pp | [−3.11, 0.00] | 0.067 | **undetermined** |
| O-FP16 | −1.29 pp | [−2.88, +0.30] | 0.13 | **undetermined** |
| O-Q4 | −2.43 pp | [−4.40, −0.53] | 0.015 | **undetermined** |

**Sensitivity reading.** This is the same comparison over the items where neither arm reached the cap. It is reported and is never a verdict (`comparisons.<arm>.sensitivity_items_where_neither_hit_the_cap`):
- N-FP8: −1.54 [−3.08, 0.00]
- O-FP16: −1.61 [−3.14, −0.08]
- O-Q4: −2.69 [−4.60, −0.84]

## Reading

- **No arm is shown to be within ±2 pp of N-BF16 on GSM8K, and none is shown to be beyond it.** Every interval extends past −2 pp, so none is "within". None lies entirely below −2 pp, so none is "outside".
- **For N-FP8 and O-FP16** the interval reaches zero (N-FP8's upper end is 0.00; O-FP16's is +0.30). At this size a loss of up to about 3 pp cannot be ruled out, and neither can no loss.
- **For O-Q4** the interval lies entirely below zero: −2.43 pp [−4.40, −0.53], McNemar p 0.015. The 4-bit model answers fewer GSM8K items correctly than N-BF16, by between about 0.5 and 4.4 pp. Whether the loss exceeds 2 pp is not determined.
- **The reference is the highest of the four in this run.** Its two runs agree exactly (85.60% and 85.60%). The three other arms score within 1.2 pp of each other (83.2–84.3%).
- **Per item the arms differ more than they do from themselves.** Correctness differs on 8.2% of items for N-FP8, 8.4% for O-FP16 and 12.4% for O-Q4 against N-BF16. It differs on 2.3% between N-BF16's two runs.

## Predictions (`prediction_p63_gsm8k.json` → `predictions`)

| # | Prediction | Result |
|---|---|---|
| P63-1 | cap share below 1% on every arm, not zero | ✅ 0.30–0.91%, none zero |
| P63-2 | N-BF16 slightly above P62's 84.2% | ✅ 85.6% |
| P63-3 | positive control inside ±2 pp | ✅ [−0.83, +0.83] |
| P63-4 | N-FP8 within | ❌ undetermined, −1.52 [−3.11, 0.00] |
| P63-5 | O-FP16 within | ❌ undetermined, −1.29 [−2.88, +0.30] |
| P63-6 | O-Q4 between −1 and −3 pp, most likely undetermined | ✅ −2.43, undetermined |
| P63-7 | every request carries `max_tokens` 1024 | ✅ 5 / 5 runs |

## Recompute check

`recompute_check.txt`: `python vol1-nim/scripts/p63_gsm8k_analyze.py <dir>` was run on this directory and on a copy holding only `items/`, `events_public.jsonl` and `g1_scorer_controls.json`.
- The two `analysis.json` files are byte-identical, and the diff output is empty.
- Flipping one item's `correct` in a third copy changes the result.

## Files

| File | What |
|---|---|
| `prediction_p63_gsm8k.json` · `.sha256` · `prediction_scan.txt` · `harness_test_record.json` | pre-registration and its records |
| `g1_scorer_controls.json` · `lmeval_venv_freeze.txt` | P62's scorer controls (copied; same tool and task); the tool's package list |
| `items/<arm>__gsm8k__<run>.jsonl` | per item, machine fields only: item id, correct, the number the filter extracted, request / messages / output sha256, output length, prompt and completion tokens, `finish_reason` |
| `events_public.jsonl` | arm gates, template probes, `ollama show`, generation settings and `max_tokens` seen per run, joins (the desktop-process list reduced to counts) |
| `analysis.json` · `recompute_check.txt` | analysis; recompute check |

Not published (local process files): full model outputs, lm-eval's logged samples, the proxy records (`raw/`), and the raw `events.jsonl`.
