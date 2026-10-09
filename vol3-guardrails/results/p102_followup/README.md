# P102 · Two follow-up checks to the judge study: a reasoning parser on the server, and Llama Guard 3 as a reference arm

*Run on 2026-10-03, 22:34–23:03 (+0800), one container on the card at a time. Every judge read stored text; no answer was generated. This is data of the judge study ([`../p93_judges/`](../p93_judges/README.md)).*

**What is in this directory, and what is not.** The pre-registration, the run log, and for each check its own directory with the per-item files, the cell records, the prechecks and the summary. A per-item line holds the item id, the verdict, the rail's decision where there is one, token counts, the duration and SHA-256 values. The text of the test sets, the judges' raw answers and their reasoning are not in this repository.

**Scope rule, unchanged.** Every figure is about one arm. Nothing here combines the per-item verdicts of two arms. The reasoning-parser check has two server settings of one judge; each setting is counted on its own, and no item of one setting is compared with the same item of the other.

## 1 · A reasoning parser on the server side

**Why.** In the judge study, Nemotron 3 Nano with reasoning on (arm J2) returned its reasoning inside the answer, closed by `</think>` with no opening tag, and the NeMo Guardrails 0.24.1 self-check rail then blocked every item. This check asks one thing: does starting the same NIM with a reasoning parser change what the rail decides?

**The two settings.** The same image, profile and rail config as J2; 100 input items (the `gr_path.input` subset of the judge study: 52 harmful, 48 harmless), one call at a time.

| | Without the argument (control) | With `NIM_PASSTHROUGH_ARGS="--reasoning-parser nemotron_v3"` |
|---|---|---|
| Rail decision on the 100 items | **block 100, allow 0** | **block 45, allow 55** |
| Verdict read from the judge's answer | unsafe 42, safe 58 | unsafe 45, safe 55 |
| Items where the rail's decision is the verdict | 42 of 100 (the 58 answers that read *safe* were blocked too) | 100 of 100 |
| Blocked, by the data sets' labels | 52 of 52 harmful, 48 of 48 harmless | 42 of 52 harmful, 3 of 48 harmless |
| Answers whose `content` still carries `</think>` | 100 of 100 | 0 of 100 |
| Guardrails log lines "Malformed `<think>` tags detected" | 101 (100 items and the warm-up call) | 0 |
| Three direct requests with `enable_thinking: true`: reasoning | inside `content`, closed by `</think>`, no `<think>`; the `reasoning` field is empty | in the message's `reasoning` field (1,331, 131 and 117 characters); `content` carries neither tag |
| Per call, p50 | 354 ms, 93 completion tokens | 380 ms, 109 completion tokens |

- **The control held.** Without the argument the rail blocked 100 of 100, as in the judge study. Had it not, this check would have no conclusion.
- **The field is called `reasoning`.** No response carried a field named `reasoning_content`, with or without the argument. The server inside this NIM reports vLLM 0.27.1.
- **The start-up log says nothing about the argument.** The container log of the run with the argument (493 lines) has no line that names the argument, the parser or a refusal; neither has the one without (518 lines). That the argument took effect is shown by the shape of the responses, not by the log.
- **On the Guardrails side no reasoning text was seen with the parser on** (0 of 100 answers, neither in the response object nor in the library's reasoning trace): the parser removes it before the library reads the answer.
- **The two verdict counts (42 and 45 unsafe) are two runs of a judge that does not repeat itself exactly.** In the judge study this arm gave the same outcome for 192 of 200 items when judged a second time. This check does not say which items differ.
- The by-label line is not in the summary file: it joins each setting's `input_gr100.jsonl` with [`../p93_judges/items.jsonl`](../p93_judges/items.jsonl) on `item_id` (`rail` against `gold_input`). With 52 and 48 items it is a count, not a rate to quote.

### What this means for a deployment

A reasoning model behind the self-check rail of Guardrails 0.24.1 needs one of two things, or the rail blocks everything:

1. **Start the server with a reasoning parser**, so that the reasoning leaves `content`:

   ```bash
   docker run -d --gpus all -p 127.0.0.1:8000:8000 --env-file <file with the NGC key> \
     -e NIM_MODEL_PROFILE=1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada \
     -e NIM_MAX_MODEL_LEN=8192 \
     -e NIM_PASSTHROUGH_ARGS="--reasoning-parser nemotron_v3" \
     -v <cache folder>:/opt/nim/.cache \
     nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12
   ```

   The rail config is the one in [`passthrough/on/gr_config/`](passthrough/on/gr_config/) (the Vol.1 self-check prompts, `chat_template_kwargs.enable_thinking: true`). To repeat the 100-item check against a server started this way: `python ../../scripts/p102_cells.py passthrough --label on --prediction prediction_p102.json --gr-py <python with nemoguardrails 0.24.1>` (it needs the test-set text, which is not in this repository; [`../p93_judges/README.md`](../p93_judges/README.md) names the sources).
2. **Or switch reasoning off** (`enable_thinking: false`): arm J3 of the judge study, where the rail's decisions follow the answers.

This was checked for one model, one NIM version and one parser name, on 100 items. It says that the rail decides item by item again; it does not say how good those decisions are beyond the counts above.

## 2 · Llama Guard 3 8B as a reference arm (LG3)

**What it is here.** A reference arm, in the place the upstream vLLM arms have in the other volumes: open weights (`meta-llama/Llama-Guard-3-8B`) on upstream vLLM 0.20.2. **It is not a NIM.**

**How it is asked.** A direct request; the turns are sent as chat messages and the model's own chat template builds the prompt (input track: the user's text; output track: the user's text and the response). The answer is read in the model's native format: `safe`, or `unsafe` followed by a line of category codes. The first non-empty line is the verdict; anything else is *no verdict*. Output limit 100 tokens, temperature 0.0.

**Results**, each with its Wilson 95% interval ([`table.md`](table.md), [`LG3/summary.json`](LG3/summary.json)):

| Set | Detection | False alarm | No verdict | Accuracy / F1 (unsafe) |
|---|---|---|---|---|
| Aegis 2.0 prompts (1,039 harmful / 889 harmless) | 66.4% [63.5, 69.2] (690) | 6.7% [5.3, 8.6] (60) | 0 | 0.788 / 0.771 |
| — of which the 148 "Needs Caution" prompts, labelled *safe* | — | 8.8% [5.2, 14.4] (13) | 0 | — |
| XSTest prompts (200 harmful / 250 harmless) | 82.0% [76.1, 86.7] (164) | 2.8% [1.4, 5.7] (7) | 0 | 0.904 / 0.884 |
| The 45 Vol.1 questions (15 adversarial / 30 others) | 14 of 15 | 0 of 30 | 0 | — |
| Aegis 2.0 responses (394 harmful / 419 harmless) | 51.3% [46.3, 56.2] (202) | 4.1% [2.5, 6.4] (17) | 0 | 0.743 / 0.659 |

**What a verdict costs** (this run; the same four cells were run twice more on 2026-10-04, and the three runs are side by side in [`../lg3_timing_repeats/`](../lg3_timing_repeats/README.md))

| Track | c=1, per verdict p50 / p99 (200 items) | c=16, verdicts per second (whole track) | c=16, per verdict p50 / p99 | Output tokens p50 / p99 | Same outcome at c=1 and c=16 |
|---|---|---|---|---|---|
| Input | 51 ms / 106 ms | 98.1 (2,423 calls in 24.7 s) | 148 ms / 372 ms | 3 / 6 | 200 of 200 |
| Output | 52 ms / 101 ms | 64.8 (813 calls in 12.5 s) | 232 ms / 399 ms | 3 / 6 | 200 of 200 |

Over the three runs the c=16 rate stayed within 4% (input 98.1, 95.3, 94.6 verdicts per second; output 64.8, 64.1, 63.4); it is the figure to quote for this arm's speed. The c=1 median did not hold: 51, 60 and 66 ms on the input track, 52, 64 and 64 ms on the output track. It is given as that range and with its boundary: client wall time, a new connection per call, on a host whose published container port adds about 3 or about 19 ms to a call.

**Limits of this arm**

- **Its taxonomy is not the data sets' taxonomy.** The model card says Llama Guard 3 is trained to label 14 categories: the 13 hazards of the MLCommons taxonomy and code-interpreter abuse. The Aegis and XSTest labels follow those data sets' own definitions of harm. The figures say how often "unsafe under its own categories" coincides with the data set's label. The general-purpose judges of the judge study have the same kind of limit, for another reason (they were asked about a short company policy).
- **The model card's own figures are on another test set.** The card of the pinned revision reports, for English and the unquantized model on Meta's internal test set for the MLCommons taxonomy: prompt classification F1 0.947 with a false-positive rate of 0.057; response classification F1 0.939 with 0.040. They are given here for scale only. This run neither reproduces nor contradicts them: the test sets and the label definitions differ.
- **Durations are those of vLLM 0.20.2 with the bf16 weights**, a new connection per call, on this card. They are not durations of a NIM.
- **One run per cell in this directory; three runs of the timed cells in all.** Here the c=1 and c=16 cells judged the same 200 items of each track with the same outcome. Across the three containers of the three runs, 2 to 4 of the 2,423 input items and 0 to 3 of the 813 output items came out differently ([`../lg3_timing_repeats/`](../lg3_timing_repeats/README.md)).

## Written before the run

[`prediction_p102.json`](prediction_p102.json), frozen at 22:33:50 (SHA-256 in [`prediction_p102.sha256`](prediction_p102.sha256)); the runner started at 22:34:09 and the first container after the first idle-card gate at 22:35:30. It binds the three harness files of this check and six of the judge study by SHA-256, and fixes in advance:

| Decided in advance | What happened |
|---|---|
| The control: without the argument the rail must block 100 of 100, or the check has no conclusion | 100 of 100 |
| Three outcomes of the parser check are all valid results: the rail decides item by item; the server refuses or ignores the argument; the argument is accepted and the answers are unchanged | the first |
| If the Llama Guard 3 weights are not in the local cache, the step is recorded as "skipped - license" and no third-party copy is used | the weights were there (the licence was accepted on the hosting site before the run) |
| Per arm and track, before its cells: the violating control must be read as unsafe and the harmless one as safe | 2 of 2 prechecks passed |
| A cell counts only if every item has a result line | 6 of 6 cells complete |

## Checks

- **Idle card:** `tools/g8_gate.py` before every container start and every cell: 9 gates, 9 passed. Seven passed on the first sample; the two before the control needed 2 and 4 samples (81 s and 222 s of waiting). The 10-second sample after each cell met the idle limit all six times.
- **Completeness:** 3,836 judge calls in 6 cells (100 + 100 + 200 + 2,423 + 200 + 813), every one returned, 0 errors. Llama Guard 3: 0 answers without a verdict.
- **After the run:** the runner removed its containers; the card showed 392 MiB in use, 0% utilization and 12 W ([`events.jsonl`](events.jsonl), `card_after_the_run`).

## Measurement conditions

| | |
|---|---|
| GPU, driver | one RTX 5090 (32 GB), driver 591.86, Windows 11 + Docker Desktop (WSL2) |
| Nemotron 3 Nano NIM | `nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12`, `sha256:bd38d2d5…e6f9`, profile `1fba9ecf…eada` (NVFP4), `NIM_MAX_MODEL_LEN=8192`; the server reports NIM 2.0.12 and vLLM 0.27.1 |
| Guardrails | 0.24.1 (recorded by the worker process), Python 3.10.6; the rail config of arm J2 |
| vLLM for Llama Guard 3 | `vllm/vllm-openai:v0.20.2`, `sha256:70a098d9…5923`; `--max-model-len 8192`; the server reports 0.20.2 |
| Llama Guard 3 weights | `meta-llama/Llama-Guard-3-8B` at `7327bd9f…e425` (bf16), Llama 3.1 Community License |
| Load | parser check: one call at a time, 100 items. Llama Guard 3: closed loop, c=1 on the 200-item subset of a track, c=16 on the whole track |
| Statistics | detection and false alarm: Wilson 95%; durations and tokens: nearest-rank p50 and p99 of per-call values; every figure from one run of its cell |
| Warm-up | five discarded requests after READY (the first took 0.7 s and 1.2 s on the two NIM containers and 23.7 s on vLLM); Nemotron 3 Nano reached 292 and 306 tok/s on the first warm-up request of its two containers; every cell starts with one discarded call |

Full records: [`events.jsonl`](events.jsonl) (every gate, start, precheck and cell), `LG3/cells.jsonl`, `LG3/precheck_*.json`, `passthrough/<setting>/passthrough.json`.

## What this does not show

- **The parser check is 100 items of one judge.** It shows that the rail's decisions follow the answers again; the judge's quality with reasoning on is the J2 line of the judge study (read from the answers, on the whole track).
- **Other models, other NIM versions and other parser names were not tried.**
- **The host was not left alone during the Llama Guard 3 cells of this run.** While its four cells ran (23:00:18 to 23:02:26), short commands that had nothing to do with the run were started on the same host: web requests to other sites, small file reads, a listing of containers. None of them was a request to the model server. The four cells were run again twice on 2026-10-04 with nothing started from the measuring session ([`../lg3_timing_repeats/`](../lg3_timing_repeats/README.md)): this run's c=1 medians are lower than both repeats, not higher, and its c=16 rates are within 4% of them. There is no sign that those commands slowed this run; what the repeats did show is that the c=1 median of this arm changes from session to session for a reason on the host's side of the connection.
- **No statement across judges.** Llama Guard 3's lines stand beside the other arms' lines, each with its own interval; whether two judges flag the same items is outside this study by design.
- **A third cell exists in the harness and was not run.** `p102_cells.py n2` and `p102_analyze.py --arm N2R` are a path for Nemotron Nano 9B v2 at c=1. It was not in this run's plan and there is no result for it.

## Files

```
prediction_p102.json · .sha256    the pre-registration and its hash
events.jsonl                      the run, step by step
table.md                          the Llama Guard 3 lines, from its summary
passthrough/
  summary.json                    both settings, and whether the control held
  off/ · on/
    passthrough.json              the setting's counts, the three request shapes, the worker's versions
    input_gr100.jsonl             one line per item: item_id, rail, verdict, status, token counts, duration, SHA-256 (no text)
    gr_config/                    the rail config as used
LG3/
  <track>_<mode>.jsonl            one line per judged item (no text); modes c1 and c16
  summary.json · cells.jsonl · precheck_<track>.json
```

To recompute: `python ../../scripts/p102_analyze.py --passthrough`, `--arm LG3`, `--table` (each reads this directory, the item table and the subsets of the judge study, and nothing else).

Harness: `../../scripts/p102_cells.py` (one cell), `p102_run.py` (the plan, the gates, the containers), `p102_analyze.py`, `p102_gen_prediction.py`.
