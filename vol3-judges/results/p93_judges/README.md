# P93 · Seven safety judges on one RTX 5090: what each one flags, what it flags wrongly, and what a verdict costs

*Run on 2026-10-02, 04:26–06:18 (+0800), one judge container on the card at a time. Every judge read the same stored text; no answer was generated. This is working data of the judge study and has not been published as an article.*

**What is in this directory, and what is not.** The pre-registration, the run log, and for every arm its own directory with the per-item verdict files, the cell records, the prechecks and the summary. A per-item line holds the item id, the verdict, the rail's decision where there is one, token counts, the duration and SHA-256 values; each file's own SHA-256 is recorded in the arm's `cells.jsonl` (`result_sha256`) and in `summary.json` (`files_read`). The text of the test sets, the judges' raw answers and their reasoning are not in this repository: files here carry item ids, SHA-256, lengths, labels, verdicts and counts.

**Scope rule.** Every figure is about one arm. Nothing here combines the per-item verdicts of two arms (no agreement between judges, no joint misses, no paired differences, no votes). [`table.md`](table.md) lists the arms side by side, each with its own Wilson 95% interval, and is built from the per-arm summaries only.

## The arms

| Arm | Judge | Served by | How it is asked | Output limit | Reasoning |
|---|---|---|---|---|---|
| J0 | Llama 3.1 8B Instruct | NIM 2.0.12, bf16 profile | NeMo Guardrails self-check action, Vol.1 rail prompts | 3 tokens | — |
| J1 | Llama 3.1 8B Instruct | NIM 2.0.12, bf16 profile | the same | Guardrails' default (1,024) | — |
| J2 | Nemotron 3 Nano | NIM 2.0.12, NVFP4 profile | the same | 1,024 | on |
| J3 | Nemotron 3 Nano | NIM 2.0.12, NVFP4 profile | the same | 1,024 | off (`enable_thinking: false`) |
| J4 | Nemotron 3.5 Content Safety | upstream vLLM 0.20.2 | direct request, the model's own taxonomy template | 100 | off |
| J5 | Nemotron 3.5 Content Safety | upstream vLLM 0.20.2 | the same | 1,024 | on |
| J6 | Llama 3.1 Nemotron Safety Guard 8B v3 | upstream vLLM 0.20.2 (**not a NIM**) | direct request, the model card's prompt | 100 | — |
| J4G, J5G | Nemotron 3.5 Content Safety | upstream vLLM 0.20.2 | J4 / J5 through Guardrails' content-safety rail, 200 items | 100 / 1,024 | off / on |

Sampling is greedy (temperature 0.0) for every arm. Guardrails is 0.24.1, the newest release on the day.

*Added on 2026-10-03, in its own directory ([`../p102_followup/`](../p102_followup/README.md)): Llama Guard 3 8B as a reference arm on upstream vLLM, and a check of arm J2 with a reasoning parser on the server side.*

## The text

| Set | Items used | Harmful / harmless | Licence |
|---|---|---|---|
| Aegis AI Content Safety Dataset 2.0, test split (NVIDIA) — prompts | 1,928 of 1,964 | 1,039 / 889 | CC-BY-4.0 |
| the same — responses (output track) | 813 | 394 / 419 | CC-BY-4.0 |
| XSTest (Röttger et al.) — prompts | 450 | 200 / 250 | CC-BY-4.0 |
| The 45 Vol.1 questions (`benchmark/e3_questions.json`), as an anchor | 45 | 15 / 30 | this repository |

- **Input track:** the judge sees the user's text alone. **Output track:** the user's text and the response.
- Left out, counted in [`items_summary.json`](items_summary.json): 36 Aegis prompts that are redacted in the release; 39 rows with a response label and an empty response (output track only).
- Aegis labels are used as given. The 148 prompts whose only category is "Needs Caution" are labelled *safe* in this release; they count as safe and have their own line in the table.
- In the output track every *unsafe* label and 81 of the 419 *safe* labels come from an LLM jury; the other 338 safe labels come from human annotators. The two classes were not labelled by the same process.
- WildGuardTest was not used: the original release is behind an access gate that requires agreeing to its terms on the hosting site.
- Pinned revisions and file hashes: [`prediction_p93.json`](prediction_p93.json) → `inputs.pinned`.

## How an answer is read

[`../../scripts/p93_parse.py`](../../scripts/p93_parse.py): *unsafe*, *safe*, or *no verdict*. An answer without a verdict is never counted as either; it is counted as truncated (cut by the output limit), unreadable, or error. For the arms through Guardrails two things are recorded and kept apart: **verdict** (what this study reads from the judge's answer) and **rail** (what the library's action decided: allow or block).

## Results

All figures: [`table.md`](table.md) (same content as JSON in [`table.json`](table.json)). The main lines, each arm's own figure with its Wilson 95% interval:

**Aegis 2.0 prompts (input track, 1,039 harmful / 889 harmless)**

| Arm | Detection | False alarm | No verdict | F1 (unsafe) |
|---|---|---|---|---|
| J0 | 72.9% [70.1, 75.5] | 15.4% [13.2, 17.9] | 0.8% | 0.788 |
| J1 | 73.0% [70.2, 75.6] | 15.4% [13.2, 17.9] | 0.9% | 0.789 |
| J2 | 66.5% [63.6, 69.3] | 10.9% [9.0, 13.1] | 0.2% | 0.758 |
| J3 | 54.9% [51.8, 57.9] | 3.8% [2.7, 5.3] | 0.6% | 0.695 |
| J4 | 89.3% [87.3, 91.1] | 20.8% [18.3, 23.6] | 0.0% | 0.862 |
| J5 | 87.7% [85.5, 89.5] | 20.8% [18.3, 23.6] | 0.3% | 0.854 |
| J6 | 87.8% [85.6, 89.6] | 15.4% [13.2, 17.9] | 0.0% | 0.874 |

**XSTest prompts (200 harmful / 250 harmless)**

| Arm | Detection | False alarm on the 250 harmless prompts | F1 (unsafe) |
|---|---|---|---|
| J0 | 86.5% [81.1, 90.6] | 18.4% [14.1, 23.7] | 0.828 |
| J1 | 86.5% [81.1, 90.6] | 18.4% [14.1, 23.7] | 0.828 |
| J2 | 89.5% [84.5, 93.0] | 6.0% [3.7, 9.7] | 0.909 |
| J3 | 72.5% [65.9, 78.2] | 1.6% [0.6, 4.0] | 0.831 |
| J4 | 99.0% [96.4, 99.7] | 25.6% [20.6, 31.4] | 0.857 |
| J5 | 98.0% [95.0, 99.2] | 25.6% [20.6, 31.4] | 0.852 |
| J6 | 94.0% [89.8, 96.5] | 24.0% [19.1, 29.7] | 0.839 |

**Aegis 2.0 responses (output track, 394 harmful / 419 harmless)**

| Arm | Detection | False alarm | F1 (unsafe) |
|---|---|---|---|
| J0 | 78.9% [74.6, 82.7] | 18.4% [15.0, 22.4] | 0.796 |
| J1 | 78.7% [74.4, 82.4] | 18.4% [15.0, 22.4] | 0.795 |
| J2 | 61.2% [56.3, 65.8] | 14.1% [11.1, 17.7] | 0.695 |
| J3 | 58.9% [54.0, 63.6] | 10.3% [7.7, 13.5] | 0.694 |
| J4 | 86.3% [82.5, 89.3] | 16.7% [13.4, 20.6] | 0.846 |
| J5 | 81.0% [76.8, 84.5] | 13.8% [10.9, 17.5] | 0.830 |
| J6 | 88.1% [84.5, 90.9] | 13.8% [10.9, 17.5] | 0.869 |

**What a verdict costs** (input track; the output track and p99 values are in `table.md`)

| Arm | c=1 p50 per verdict | c=16 verdicts per second | Output tokens p50 / p99 | Answers with reasoning | Same outcome when judged again |
|---|---|---|---|---|---|
| J0 | 51 ms | 26.4 | 3 / 3 | 0 of 2,423 | 199 of 200 |
| J1 | 568 ms | 18.5 | 57 / 184 | 0 of 2,423 | 199 of 200 |
| J2 | 383 ms | 9.4 | 112 / 626 | 2,419 of 2,423 | 192 of 200 |
| J3 | 42 ms | 26.4 | 2 / 2 | 0 of 2,423 | 191 of 200 |
| J4 | 89 ms | 87.0 | 11 / 22 | 0 of 2,423 | 200 of 200 |
| J5 | 762 ms | 10.8 | 137 / 503 | 2,423 of 2,423 | 193 of 200 |
| J6 | 204 ms | 45.9 | 18 / 33 | 0 of 2,423 | 199 of 200 |

Through Guardrails' content-safety rail, one call at a time on the 100-item input subset: J4G 90 ms p50 (176 ms p99); J5G 790 ms p50 (2,815 ms p99). On the 100-item output subset: J4G 162 ms p50; J5G 1,452 ms p50.

### The rail and the verdict are not always the same thing

For J2 (Nemotron 3 Nano with reasoning on, through the self-check rail) the library's action **blocked every item: 2,423 of 2,423 in the input track and 813 of 813 in the output track**, harmless ones included. The judge's own answers were readable: read after the reasoning, they flag 66.5% of the harmful Aegis prompts and 10.9% of the harmless ones. The cause is in how the reasoning arrives: this NIM returns the reasoning inline in the answer, closed by `</think>` with no opening tag (2,419 of 2,423 answers; the other 4 were cut by the output limit). Guardrails 0.24.1 removes a reasoning block only when both tags are present, logs the answer as malformed, and hands the whole text to the yes/no parser, which treats anything that is not a clean "no" as a block. With reasoning off (J3) the same rail's decisions follow the answers. A follow-up check started the same NIM with a reasoning parser (`NIM_PASSTHROUGH_ARGS="--reasoning-parser nemotron_v3"`): on 100 input items the rail then blocked 45 and allowed 55, after blocking 100 of 100 without the argument in the same session ([`../p102_followup/`](../p102_followup/README.md)).

For J5G the reasoning arrives with both tags and the library removes it before parsing; the content-safety rail's decisions follow the answers there (no answer was left unparsed in the 200 items).

For J0 and J1 the rail blocks slightly more than the verdict column says (Aegis prompts: 768 and 770 harmful, 142 harmless each): an answer the study counts as *no verdict* is a block for the rail.

## What was expected, and what happened

All expectations were written before the run ([`prediction_p93.json`](prediction_p93.json), frozen at 04:25:55; the first container started at 04:26). Each is about one arm.

| Expectation | Outcome |
|---|---|
| J0: at most 1% of answers without a verdict | 0.7% (17 of 2,423 input), 0.1% (1 of 813 output) |
| J0: at most 200 ms per input verdict at c=1 (p50) | 51 ms |
| J1: 300–2,000 ms per verdict; median 30–200 completion tokens | 568 ms / 57 tokens (input); 917 ms / 88 tokens (output) |
| J0 and J1 on the 45 Vol.1 questions: 14 of 15 adversarial, 0 of 30 others | 14 of 15 and 0 of 30, each |
| J2: reasoning in at least 90% of answers | 2,419 of 2,423 (input), 813 of 813 (output); truncated: 4 and 0 |
| J3: reasoning in no answer; median at most 10 completion tokens | none; 2 tokens |
| J4: at most 1% without a verdict; median at most 30 completion tokens | 0; 11 tokens (input), 18 (output) |
| J4: harmful F1 on Aegis prompts within 0.81–0.91 (the model card reports 0.86) | 0.862 |
| J5: reasoning in at least 90% of answers | 2,423 of 2,423 and 813 of 813; truncated: 6 and 6 |
| J6: at most 1% without a verdict | 0 |

The J4 line is the outside value of this run: the model card's own figures for this model are accuracy 0.85 / harmful F1 0.86 on Aegis prompts, 0.85 / 0.85 on Aegis responses and 0.85 / 0.85 on XSTest prompts; this run measured 0.846 / 0.862, 0.847 / 0.846 and 0.853 / 0.857.

## Checks

- **Controls, per arm and track, before its cells:** a synthetic text that plainly violates must be read as unsafe and a harmless one as safe. 32 of 32 prechecks passed (18 in the main and Guardrails-path phases, 14 before the second judging).
- **Reasoning switch:** ten harmless prompts per precheck. Arms with reasoning on showed reasoning in 10 of 10, arms with it off in 0 of 10.
- **Idle card:** `tools/g8_gate.py` before every container start and every cell (55 gates, 55 passed on the first sample, longest wait 10.9 s). The 10-second sample taken right after each cell did not meet the idle limit twice (J4 input c=1: 48.2 W; J2 input, second judging: 50.1 W; limit 45 W); the gate before the following cell passed both times.
- **Completeness:** 46 cells, each with every item returned (27,952 judge calls: 27,880 with a verdict, 41 truncated, 31 unreadable, 0 errors).
- **Judged a second time:** 200 input and 100 output items per arm, in a newly started container, at c=16. The share with the same outcome is in the table above and in `table.md`.

## Measurement conditions

| | |
|---|---|
| GPU, driver | one RTX 5090 (32 GB), driver 591.86 (CUDA 13.1 as reported by the driver), Windows 11 + Docker Desktop (WSL2) |
| Llama NIM | `nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12`, `sha256:d2c94c1d…6545`, profile `092ed421…6f90` (bf16), `NIM_MAX_MODEL_LEN=8192`, `VLLM_USE_V2_MODEL_RUNNER=0` |
| Nemotron 3 Nano NIM | `nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12`, `sha256:bd38d2d5…e6f9`, profile `1fba9ecf…eada` (NVFP4), `NIM_MAX_MODEL_LEN=8192` |
| vLLM | `vllm/vllm-openai:v0.20.2`, `sha256:70a098d9…5923` (inside the range the Nemotron 3.5 Content Safety model card gives); `--max-model-len 8192` |
| Weights | `nvidia/Nemotron-3.5-Content-Safety` at `35645ed3…497c`; `nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3` at `8fdc246b…fafa` |
| Guardrails | 0.24.1 (recorded by every worker process), Python 3.10.6 |
| Load | closed loop: c=1 on the 200-item subset of a track; c=16 on the whole track |
| Statistics | detection and false alarm: Wilson 95%; durations and tokens: nearest-rank p50 and p99 of per-call values; every figure from one run of its cell |
| Connections | direct arms open a new connection per call; arms through Guardrails use the library's client. Each precheck timed a minimal request both ways: medians between 16 and 45 ms, the reused connection 0.5 to 16 ms lower |
| Warm-up | five discarded requests after READY (the first took 23 s on the Llama NIM and on Safety Guard 8B); Nemotron 3 Nano reached 304 and 303 tok/s on the first warm-up request of its two containers; every cell starts with one discarded call |

Full records: [`events.jsonl`](events.jsonl) (every gate, start, precheck and cell), each arm's `cells.jsonl`, `precheck_*.json` and, for the arms through Guardrails, the rail config as used (`gr_config/`).

## What this does not show

- **The general-purpose judges were asked a different question than the labels answer.** J0–J3 use the Vol.1 self-check prompts, which state a short company policy; the Aegis and XSTest labels follow those data sets' own definitions of harm. Their figures say how often "violates this policy" coincides with the data set's label, not how well the model could do with a prompt written for that taxonomy.
- **Home ground.** Safety Guard 8B's model card lists Aegis 2.0 samples among its training sources, and Nemotron 3.5 Content Safety's card lists the Safety Guard v3 data and the Aegis taxonomy. On the Aegis test set J4, J5 and J6 are on home ground; XSTest is the line to read beside it.
- **One run per cell.** The second judging covers 300 items per arm; it shows how far an arm repeats itself, not a confidence interval on its durations.
- **c=16 for arms through Guardrails includes the client.** The Guardrails actions run in one Python process on the host; its CPU state was not gated. J0's p99 of 2.3 s at c=16 for a 3-token answer is time spent waiting on that side as well as on the server.
- **Durations of J4G / J5G** come from 100 items per track at c=1 and are not on the same items as J4 / J5's 200-item c=1 subsets.
- **No statement across judges.** Whether two judges miss the same items, or what a combination would do, is outside this study by design.

## Choices made where the plan left room

- Temperature 0.0 for all arms (the model cards' examples use 0.01 or the generation default).
- `request_categories: "/categories"` for Nemotron 3.5 Content Safety, as in its card's example and in the Guardrails example.
- J4G / J5G follow the Guardrails example written for this model (`examples/configs/nemotron-3.5-content-safety` at v0.24.1): model type `content_safety`, reasoning switched by `chat_template_kwargs.enable_thinking`, parsers `nemotron_content_safety_parse_*`. The `content_safety_reasoning` model type and `reasoning.enabled` belong to a different model (Nemotron Content Safety Reasoning 4B) and were not used.
- Context 8,192 tokens for every server.
- The second judging runs in a newly started container, after all first judgings.
- Subset sizes: 200 per track at c=1; 200 input + 100 output for the second judging; 100 + 100 for the Guardrails path.
- **Two requests were sent to a server during a timed cell.** To record the vLLM version, `GET /version` and `GET /v1/models` were sent by hand between 05:12:10 and 05:12:40; the J4 input c=1 cell ran from 05:12:14 to 05:12:32, so they very probably fell inside it. Neither request generates tokens; the cell (200 calls, p50 89 ms) was not repeated.
- The vLLM version shown as `None` in `events.jsonl` (`vllm_version_in_log`) is a pattern in the runner that did not match this version's log line; the running server's own `/version` endpoint answered `0.20.2`.

## Files

```
prediction_p93.json · .sha256     the pre-registration and its hash (binds the nine harness files by SHA-256)
items.jsonl · subsets.json · items_summary.json   the items (ids, labels, hashes, lengths), the fixed subsets, the counts
events.jsonl                      the run, step by step
table.md · table.json             the arms side by side, from the summaries
J0 … J6, J4G, J5G /
  <track>_<mode>.jsonl            one line per judged item: item_id, verdict, status, rail (arms through Guardrails), finish_reason,
                                  token counts, duration, SHA-256 of the answer and of the reasoning (no text). Modes: c1, c16,
                                  stability (the second judging), gr_path (J4G / J5G)
  summary.json                    the arm's figures
  cells.jsonl                     one record per cell (window, counts, request shape, SHA-256 of its per-item file)
  precheck_<track>[_stability].json   controls, reasoning switch, connection check
  gr_config/                      the rail config as used (arms through Guardrails)
```

To recompute an arm's figures from its per-item files: `python ../../scripts/p93_analyze.py --arm J4` (it reads that arm's directory, the item table and the subsets, and nothing else).

Harness: `../../scripts/p93_*.py` (`p93_run.py` runs the whole plan; `p93_judge.py` one cell; `p93_analyze.py --arm X` one arm; `p93_table.py` the table; `p93_mock_server.py` is a stand-in server for harness tests only).
