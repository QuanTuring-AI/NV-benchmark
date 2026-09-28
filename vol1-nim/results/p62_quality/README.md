# Vol.1 (renewed) · P62 Q1 · answer quality of the four configurations whose speed P59 measured (run 2026-09-26, 17:59–19:58)

**The question.** P59 and Q2 found NIM's FP8 profile the fastest configuration at every concurrency level on this card, and Ollama's 4-bit model the fastest for a single user. Is either faster because it answers worse?

**Arms** (P59's images, profiles and slot counts):

| Arm | Configuration |
|---|---|
| N-BF16 (reference) | NIM 2.0.12, profile `092ed421…` |
| N-FP8 | NIM's own choice on this card, profile `c4789f7a…` |
| O-Q4 | Ollama 0.34.4, `llama3.1:8b`; `ollama show` reports quantization **Q4_K_M** |
| O-FP16 | `llama3.1:8b-instruct-fp16`; `ollama show` reports F16 |

All four run Llama 3.1 8B Instruct with context 8,192 on one RTX 5090. FP16 and bf16 are *comparable* precision, not the same precision.

**Scope.** Answer quality only, on these three task sets, with this tool, task version and prompt format, at temperature 0. The absolute accuracies depend on the prompt format, so they are not set beside other publications' numbers as a result. The comparison is between arms, item by item. This says nothing about speed.

**Pre-registration.** `prediction_p62_quality.json`, frozen 2026-09-26T16:52:18+0800 after four harness tests (`harness_test_record.json`). It was scanned before its sidecar was written (`prediction_scan.txt`, with a planted-control rescan). The first container started at 17:59:28.

## How it was measured

**Tool.** lm-evaluation-harness **0.4.13** (package list: `lmeval_venv_freeze.txt`) with backend `local-chat-completions`. It runs from `vol1-nim/scripts/p62_quality.py` through lm-eval's Python API, with each server applying its own chat template and few-shot examples sent as multi-turn chat. Concurrency is 8. A logging proxy on `127.0.0.1` sits between lm-eval and each server.

| Task (lm-eval name) | Items | Settings (as sent, `events_public.jsonl` → `task_run.gen_settings_seen`) | Primary metric |
|---|---|---|---|
| `gsm8k_cot_llama` | all 1,319 | 8-shot · `max_tokens` 256 (lm-eval's default; the task sets none) · 4 stop strings · temperature 0 | exact match, strict-match filter |
| `ifeval` | all 541 | 0-shot · `max_tokens` 1,280 · temperature 0.0 | prompt-level strict |
| `mmlu_llama` | 2,850 = 50 × 57 subjects (`mmlu_sample_ids.json`, seeded per subject) | 5-shot · the task's assistant prefix "The best answer is" · `max_tokens` 10 · stop "." | exact match |

`mmlu_llama` ends each prompt with an assistant message holding the start of the answer. Every request therefore carries `continue_final_message=true, add_generation_prompt=false` on every arm, so that vLLM continues that message the way Ollama already does. The harness test showed every answer on both engines was a single letter continuing the prefix.

**Extra runs.**
- N-BF16 ran all three task sets twice (the noise floor). The ticket asked for GSM8K; IFEval and MMLU were added.
- N-FP8 ran GSM8K again at concurrency 1 and 32.

## Gates

| Gate | Result | Source |
|---|---|---|
| **G1 scorer controls** (before any model output) | ✅ all three tasks. GSM8K: reference answers score 100%, permuted 1.4%. MMLU: 100%, permuted 24.8%. IFEval: 113 / 113 on the prompts whose instruction can be satisfied mechanically; empty answers 0% on the other 428; permuted 2.7% | `g1_scorer_controls.json`; `analysis.json` → `g1_scorer_controls` |
| **G2a prompt tokens** (±5% of N-BF16's per item, after the arm's constant template offset) | ✅ every item on every arm. NIM counts exactly 25 more prompt tokens than Ollama on every item (the template's preamble; one-word probe 36 against 11). Largest remaining difference 0.95% (IFEval, Ollama arms) | `cells.<arm>|<task>.g2.template_offset_tokens`, `.items_outside_5pct`, `.max_abs_rel_diff` |
| **G2b output cap** (`finish_reason` "length" < 1%) | ❌ **GSM8K and IFEval on every arm: 2.0–3.3%** of outputs reached the cap. MMLU 0% | `cells.*.g2.length_share` |
| **G3 residency and health** | ✅ health 53.1% (O-Q4), 74.5% (O-FP16), 79.8% (N-BF16), 77.2% (N-FP8) of peak bandwidth; all resident | `cells.*.g3` |
| **G4 identical requests** (sha256 of each request body without "model") | ✅ 0 mismatches on every item | `cells.*.g4.request_sha_mismatches` |
| **join** (each item to its proxy record, same output text) | ✅ after the post-run join correction (below) | `cells.*.join` |

**G2b nulls every GSM8K and IFEval cell, as the gate is written.** An output that hits the cap is not a truncated prompt. In the one capped output inspected, in the harness test, the model had repeated a sentence until the cap; the capped outputs of this run were not read. The gate still counts it, and the cells are null. Their accuracies are kept under `accuracy_pct_if_gates_passed`, and the paired comparison is still computed and listed. Neither is a conclusion.

## Results

Accuracy % with Wilson 95% interval. Source: `analysis.json` → `cells.<arm>|<task>` → `accuracy_pct` (valid cells) or `accuracy_pct_if_gates_passed` (null cells, marked *null*), `wilson95_pct`, `correct`/`n`.

| Arm | GSM8K (*null*: G2b) | IFEval (*null*: G2b) | **MMLU** |
|---|---|---|---|
| N-BF16 | 84.2 [82.1, 86.0] · 1,110 / 1,319 | 75.8 [72.0, 79.2] · 410 / 541 | **68.9 [67.2, 70.6] · 1,965 / 2,850** |
| N-FP8 | 84.1 [82.0, 86.0] · 1,109 | 75.4 [71.6, 78.9] · 408 | **68.9 [67.2, 70.6] · 1,964** |
| O-FP16 | 84.2 [82.2, 86.1] · 1,111 | 76.0 [72.2, 79.4] · 411 | **69.1 [67.3, 70.7] · 1,968** |
| O-Q4 | 82.6 [80.5, 84.6] · 1,090 | 73.9 [70.1, 77.5] · 400 | **68.7 [67.0, 70.4] · 1,958** |

**Paired against N-BF16:** arm minus reference in pp, paired bootstrap 95% interval, exact McNemar p. The equivalence bound is ±2 pp. Source: `paired_vs_ref.<arm>|<task>` → `paired.diff_pp`, `.ci95_pp`, `.mcnemar_p`, `verdict`.

| Arm | MMLU | GSM8K (verdict null) | IFEval (verdict null) |
|---|---|---|---|
| N-FP8 | −0.04 [−0.81, +0.74] · p 1.00 · **within ±2 pp** | −0.08 [−1.67, +1.52] · p 1.00 | −0.37 [−3.14, +2.40] · p 0.90 |
| O-FP16 | +0.11 [−0.53, +0.74] · p 0.83 · **within ±2 pp** | +0.08 [−1.59, +1.74] · p 1.00 | +0.19 [−3.14, +3.51] · p 1.00 |
| O-Q4 | −0.25 [−1.23, +0.74] · p 0.68 · **within ±2 pp** | −1.52 [−3.41, +0.38] · p 0.13 | −1.85 [−5.18, +1.29] · p 0.31 |

The GSM8K and IFEval verdicts are null for two reasons: both cells are null (G2b), and the task's noise floor exceeds the bound.

**Noise floor.** N-BF16 answered each task twice in the same container at temperature 0. Source: `noise_floor.<task>`.

| | GSM8K | IFEval | MMLU |
|---|---|---|---|
| items whose correctness differs between the two runs | **3.26%** (17 + 26 of 1,319) | **5.55%** (17 + 13 of 541) | 1.02% (12 + 17 of 2,850) |
| identical output text | 63.5% | 29.0% | 98.7% |
| accuracy difference (second − first) | +0.68 pp [−0.30, +1.67] | −0.74 pp [−2.77, +1.29] | +0.18 pp [−0.18, +0.56] |

On GSM8K and IFEval the reference disagrees with itself on more items than the ±2 pp bound allows. By the pre-registered rule the bound is not valid for those two tasks, and it was not widened. On MMLU the noise floor is 1.02%.

**Sensitivity reading.** This is reported and is never a verdict. It repeats the paired comparison over the items where neither arm hit the output cap (`paired_vs_ref.*.sensitivity_items_where_neither_hit_the_cap`):

| Arm | GSM8K | IFEval |
|---|---|---|
| N-FP8 | −0.64 [−2.15, +0.79] | 0.00 [−2.72, +2.72] |
| O-FP16 | −0.40 [−1.98, +1.19] | +0.19 [−3.10, +3.49] |
| O-Q4 | −2.21 [−4.03, −0.47], p 0.017 | −1.54 [−4.81, +1.54] |

**No measurable accuracy change with concurrency.** N-FP8 on GSM8K at 1, 8 and 32 concurrent requests. Source: `concurrency_fp8_gsm8k`.

| | c=1 | c=8 | c=32 |
|---|---|---|---|
| accuracy % | 84.38 | 84.08 | 84.61 |
| `finish_reason` "length" | 2.35% | 2.73% | 1.90% |

- c=32 against c=1: +0.23 pp [−1.21, +1.59], McNemar p 0.83.
- Correctness differs on 6.75% of items, and only 25.4% of the outputs are identical.
- The individual answers change with concurrency; the accuracy does not move measurably.

## Two gate definitions were wrong, and P63 replaces them for GSM8K (added 2026-09-27)

The ticket that defined this run has since ruled that two of its gates were **wrong as defined**. The execution was not at fault. This run's pre-registration, `analysis.json` and tables above stay as they were.

- **G2b ("length" below 1%)** mixed two different things. One is a truncated prompt, which G2a checks separately and which passed on every item. The other is an output that reaches the cap. That is the model's behaviour, and it is part of the score: with lm-eval's default cap of 256 tokens, even the reference reached it on 3.2% of GSM8K items.
- **The noise floor ("correctness differs on at most 2% of items between two runs of the reference")** tested a total that the paired interval already contains. The question an equivalence test has to answer first is different: can it call a configuration equal to itself? Using this run's own numbers, N-BF16 against itself gives:
  - GSM8K [−0.30, +1.67] pp, inside ±2;
  - IFEval [−2.77, +1.29] pp, outside ±2.

**GSM8K** was measured again as P63 (`../p63_gsm8k/`), under a new pre-registration. The cap is 1024 tokens, and outputs that reach it are scored as the model's answer. N-BF16 against itself is the positive control that the ±2 pp verdicts require.

**IFEval is descriptive only in this volume and is not re-run.** With n = 541, the reference against itself spans [−2.77, +1.29] pp, which is already wider than ±2. At this size the task cannot support a ±2 pp verdict.

## Reading

- **MMLU** (every gate passed, noise floor 1.0%): **N-FP8, O-FP16 and O-Q4 are each within ±2 pp of N-BF16.** The faster configurations show no measurable accuracy loss on this task.
- **GSM8K and IFEval** carry no conclusion under the pre-registered gates. Two things are measured instead:
  - The reference itself changes its correctness on 3.3% and 5.5% of items between two identical runs.
  - Every paired interval includes zero, except one sensitivity reading, which is not a verdict: O-Q4 on GSM8K over the items where neither arm hit the cap, −2.2 pp [−4.0, −0.5].
- In every table O-Q4 is the arm furthest below the reference, and O-FP16 the closest. This fits the arm design: precision, not the engine. It is a direction, not a result.

## Post-run join correction (disclosed)

The MMLU sample holds 3 pairs of items with byte-identical prompts: the same question appears twice in a subject's test split (college physics 30 / 77 and 43 / 90, public relations 56 / 106). The harness joined each item to its proxy record by the sha256 of the messages. For both items of a pair it took the last record. Where the two answers to one prompt differed, one item carried the other's output hash: N-BF16 and O-Q4, college physics 43, one item each. That fails the join rule.

`vol1-nim/scripts/p62_quality_rejoin.py` was written after the run and applies the pre-registered rule correctly: among the records with the item's messages, the one whose output equals lm-eval's own response for that item. It changed only those two items' `output_sha` (`join_corrections.json`). Correctness and extracted answers come from lm-eval and did not change. The harness's own join figures are kept in `events_public.jsonl` as `join_as_run`, next to the corrected `join`. The harness, analyser and post-run programs bound in the pre-registration are unchanged.

Two answers to the same prompt at temperature 0 differed on N-BF16 and on O-Q4. This is the same nondeterminism the noise floor measures.

## Recompute check (acceptance 7)

`recompute_check.txt`: `python vol1-nim/scripts/p62_quality_analyze.py <dir>` was run on (a) this directory and (b) a copy holding only the published inputs: `items/`, `events_public.jsonl`, `g1_scorer_controls.json` and `mmlu_sample_ids.json`.
- The two `analysis.json` files are byte-identical, and the diff output is empty.
- Negative control: one item's `correct` was flipped in a third copy, and the result changed.

## Predictions (`prediction_p62_quality.json` → `predictions`; point estimates as written)

| # | Prediction | Result |
|---|---|---|
| Q1-1 | N-FP8 within ±1 pp on each task | ✅ −0.08 / −0.37 / −0.04 (GSM8K / IFEval / MMLU; the first two cells are null) |
| Q1-2 | O-FP16 within ±1 pp | ✅ +0.08 / +0.19 / +0.11 |
| Q1-3 | O-Q4 no lower than −3 pp | ✅ −1.52 / −1.85 / −0.25 |
| Q1-4 | N-BF16 GSM8K 78–88% | ✅ 84.2 (cell null by G2b) |
| Q1-5 | noise floor ≤ 2% on each task | ❌ GSM8K 3.26, IFEval 5.55; MMLU 1.02 ✅ |
| Q1-6 | N-FP8 GSM8K c=1 and c=32 within 1 pp, < 100% identical outputs | ✅ +0.23 pp, 25.4% identical |
| Q1-7 | every arm passes G2, G3, G4 on every task | ❌ G2b on GSM8K and IFEval |
| Q1-8 | O-Q4 is Q4_K_M | ✅ |
| Q1-9 | GSM8K "length" < 1% on every arm | ❌ 2.0–3.2% |

## Files

| File | What |
|---|---|
| `prediction_p62_quality.json` · `.sha256` · `prediction_scan.txt` · `harness_test_record.json` | pre-registration and its records |
| `g1_scorer_controls.json` · `mmlu_sample_ids.json` · `lmeval_venv_freeze.txt` | scorer controls; the MMLU sample; the tool's package list |
| `items/<arm>__<task>__<run>.jsonl` | per item, machine fields only: task, item id, correct, extracted answer (GSM8K the number, MMLU the letter or `[other]`, IFEval one boolean per instruction), request / messages / output sha256, output length, prompt and completion tokens, `finish_reason` |
| `events_public.jsonl` | arm gates, template probes, `ollama show`, the generation settings seen per task, join figures (the desktop-process list reduced to counts) |
| `analysis.json` · `recompute_check.txt` · `join_corrections.json` | analysis; recompute check; post-run join correction |

Not published (local process files): the model outputs in full, lm-eval's logged samples, the proxy records (`raw/`), and the raw `events.jsonl`. IFEval's answers are free text, and an amount that cannot be reviewed line by line does not go into this repository.
