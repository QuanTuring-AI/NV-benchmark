# Vol.2 · Nemotron 3 Nano as the self-check judge once its reasoning is switched off (run 2026-09-23, 16:27–17:01)

**Question.** In `../p53_guardrails/` the Nemotron 3 Nano judge (A2) answered NeMo Guardrails' self-check prompts with a paragraph of reasoning, and the rail blocked all 135 rows, clean questions included. A `/no_think` system message fixed Nemotron Nano 9B v2 and did nothing here. The Nemotron 3 model card and the NIM API reference name a different switch, `chat_template_kwargs: {"enable_thinking": false}`. This run tests it in two layers so that "the model cannot answer yes or no" and "Guardrails does not deliver the switch" are told apart. Pre-registration `prediction_p55_judge_thinking.json`, frozen 2026-09-23T16:27:30+0800 after a harness test (disclosed in its basis) and scanned before its sidecar was written (`prediction_scan.txt`); container READY and first (warm-up) request 16:33:52.

Every row: **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 · `NIM_MAX_MODEL_LEN` 8192 · `max_num_seqs` 32 (as `../p53_guardrails/`) · judge calls `max_tokens` 1024, answers `max_tokens` 500. Guardrails: nemoguardrails 0.23.0 through the Vol.3 worker. Warm-up: 25 discarded ~1k-token requests; the first two ran at 189 and 226 tok/s, the rest at 313–318. No model text is stored: replies are kept as a first-word label (yes / no / other), SHA-256 and length.

## L1 · straight to the NIM, the prompts Guardrails would send

Vol.1's two self-check prompts (`benchmark/guardrails/config.yml`, placeholder filled), sent exactly as Guardrails 0.23.0 sends a judge call: non-streamed, temperature 0.001, top_p 0.9, `max_tokens` 1024. 45 E3 questions × 3 rounds, each with and without the switch. The output check reads the Vol.1 E3 nim-only answer to the same question.

| Condition | Calls | First word yes / no / other | Completion tokens p50 · p95 · max | Duration p50 · p95 (ms) | "yes" by category (clean / edge / adversarial) |
|---|---|---|---|---|---|
| input check, no switch (control) | 135 | 0 / 0 / **135** | 67 · 125 · 376 | 319 · 515 | — |
| **input check, `enable_thinking: false`** | 135 | **45 / 90 / 0** | **2 · 2 · 2** | **106 · 132** | **0 / 0 / 45** |
| output check, no switch (control) | 135 | 0 / 0 / **135** | 79 · 214 · 482 | 364 · 781 | — |
| **output check, `enable_thinking: false`** | 135 | **22 / 113 / 0** | **2 · 2 · 2** | **106 · 128** | **0 / 0 / 22** |

0 errors in 540 judge calls; the NIM accepts the field. **Verdict: switch works.** Without the switch the judge never starts with yes or no; with it every reply is one word. On the input check it says "yes" (violates) to all 45 adversarial calls and to none of the 90 clean and edge calls. On the output check it flags 22 answers, all of them answers to adversarial questions (9 of the 15 questions, mostly answers of about 300 characters), and no answer to a clean or edge question. These are verdicts on this question set, not properties of the model.

## L2 · through NeMo Guardrails 0.23.0

Arm **J** is Vol.1's rail config (model name substituted, top_p 0.9 added) plus two task-typed models, `self_check_input` and `self_check_output`, identical to the main model except `parameters.chat_template_kwargs: {enable_thinking: false}` (`gr_config_a2_j/config.yml`). Guardrails 0.23.0 copies unknown model parameters into the request body (`nemoguardrails/llm/models/openai_chat.py:83`, `llm/clients/openai_compatible.py:48`) and gives a self-check action its task-typed model when one exists (`colang/v1_0/runtime/runtime.py:644-645`). So only the two judge calls change; the answer is written by the main model with reasoning on, as in the nim-only arm **N**. No Guardrails source was modified. N and J rotated per question, 45 questions × 3 rounds, 2 s apart. Blocks are read from the response digest, with the rules of `../p53_guardrails/` (`p53_guardrails_analyze_digest.py`, unchanged). All preconditions held: 0 errors and HTTP 200 on all 135 N rows, 135 rows per arm, one container at every row.

| | A2 · N (nim-only) | A2 · J (rail, judges with `enable_thinking: false`) |
|---|---|---|
| true blocks: clean / edge / adversarial | — | **0 / 60 · 0 / 30 · 45 / 45** |
| judge replies (first word) | — | input check yes 45 · no 90 · output check no 90 (all 2 tokens) |
| clean_passthrough avg latency (March 2026 Vol.1 algorithm) | 1,698.1 ms | 1,982.8 ms |
| **end-to-end overhead** | | **+16.8%**; paired over the 30 questions that passed in both arms (90 pairs) **+16.8% [+16.2%, +17.4%]** |
| **rail cost per request** (`rails.explain()`) | | input check **113 ms** (p95 135) · answer 1,705 ms / 500 tokens · output check **87 ms** (p95 114) |

**Verdict: judge usable through Guardrails.** The end-to-end overhead is about 285 ms on a 1.7 s answer. Two one-word judge calls account for about 200 ms of it, and the rest is Guardrails' own processing. N's answers hit the 500-token cap on 96 of 135 rows and the rail's answers all did, so there is no output-length effect in this figure.

## Pre-registered predictions

**R1** L1 verdict 'switch works': held. **R2** input check yes on ≥ 30 of 45 adversarial and ≤ 5 of 90 clean/edge: held (45 and 0). **R3** L2 verdict 'judge usable': held. **R4** median judge call ≤ 200 ms: held (113 and 87 ms). **R5** end-to-end overhead within ±10%: **failed** (+16.8%; the harness test had shown +17% on three questions, after R5 was written, as the pre-registration states).

## Reading

Vol.1's rail config assumes a judge that answers yes or no directly. Nemotron reasons by default, and the two generations switch reasoning off differently: Nemotron Nano 9B v2 honours a `/no_think` system message (`../p53_guardrails/`), Nemotron 3 Nano needs `chat_template_kwargs.enable_thinking = false`. Guardrails 0.23.0 can deliver that field to the judge calls alone with no change to its code. Delivered, the Nemotron 3 Nano judge gives one-word verdicts in about 0.1 s. On this question set it blocks every adversarial question and no clean or edge question, and it costs about 17% end to end on a reasoning-length answer.

This measures one image (NIM 2.0.12), one Guardrails version (0.23.0), one question set (March 2026 Vol.1 E3) and one request shape. It does not say how the judge behaves on other policies or languages.

## Files

`prediction_p55_judge_thinking.json` + `.sha256` + `prediction_scan.txt` · `l1_calls.jsonl` (675 rows: 540 judge calls and 135 answers; labels, tokens, durations, digests; no text) · `rows_public.jsonl` (272 rows including 2 warm-up rows; response digests; judge calls as label, digest and length) · `events.jsonl` · `analysis.json` · `gr_config_a2_j/config.yml` · `versions.txt` · `ctx.txt`. Harness `../../scripts/p55_judge_thinking.py`, analysis `../../scripts/p55_judge_thinking_analyze.py`, runner `../../scripts/run_p55_judge_thinking.sh`; SHA-256 in the pre-registration. `logs/`, `harness_test/` and the console output (`console.txt`) are not published.
