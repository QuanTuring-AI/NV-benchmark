# Vol.3 · Llama 3.1 Nemotron Safety Guard 8B v3 through its NIM, on one RTX 5090

*Working data; nothing here has been published as an article. Run on 2026-10-06, 04:04 to 05:11 (+0800), one RTX 5090 (32 GB), Windows 11 with Docker Desktop (WSL2), **graphics driver 610.88** (the runs of this volume before this day recorded 591.86; see section 2). Pre-registration: [`prediction_safety_guard_nim.json`](prediction_safety_guard_nim.json), frozen 2026-10-06 04:03:56, SHA-256 `bb6df52e…c211`, before the first serving container (04:04:43). It supplements the judge study's pre-registration and changes nothing in it. Run log: [`events.jsonl`](events.jsonl); 21 idle-card gates, all passed; 10 prechecks, all passed; 16 cells, all complete.*

**Why this exists.** The judge study ([`../p93_judges/`](../p93_judges/README.md)) served this model with upstream vLLM and called the arm "not a NIM". The NIM had not been tried: its support matrix opens with "The model requires 48 GB of GPU memory", and that sentence was taken as the answer. The same page lists a generic profile (vLLM, BF16, one GPU, 14.97 GB). This directory tries it.

Every figure below is about one arm. No per-item result of one arm is read together with a per-item result of another arm; the tables are built from each arm's `summary.json`.

## 1 · The NIM serves on this card, and gives the verdicts the study measured

Same model, same prompt (the model card's), same items and subsets, same program asking and reading (`p93_judge.py --arm J6`, unchanged): only the server differs.

| Arm | Served by | Aegis 2.0 prompts: detection · false alarm | XSTest: detection · false alarm | Aegis 2.0 responses: detection · false alarm |
|---|---|---|---|---|
| J6 (the study, 2026-10-02) | upstream vLLM 0.20.2 | 87.8% (912/1039) · 15.4% (137/889) | 94.0% (188/200) · 24.0% (60/250) | 88.1% (347/394) · 13.8% (58/419) |
| **J6N** | **NIM 1.14.0, generic profile** (vLLM, BF16) | 87.8% (912/1039) · 15.6% (139/889) | 94.5% (189/200) · 24.4% (61/250) | 87.6% (345/394) · 14.1% (59/419) |

- **It starts.** `list-model-profiles` on this card names the generic profile "compatible with system and runnable" ([`before_the_run/list_model_profiles.txt`](before_the_run/list_model_profiles.txt)); pinned by id it reported ready after 327 s and 251 s (two containers), with 31.1 GiB of the card in use (31,892 MiB). Its log line: `Selected profile: 47804570… (vllm-bf16-tp1-pp1-…)`.
- **The verdicts are the study's**, inside every Wilson interval ([`table.md`](table.md) has them). No call without a verdict in any cell. A second reading of 200 prompts and 100 responses in a new container gave the same outcome on 200 of 200 and 99 of 100.
- Files: [`J6N/`](J6N/) (per-item verdict files without text, `cells.jsonl`, the four prechecks, `summary.json`).

## 2 · It is about a fifth slower than upstream vLLM, and the driver is not the reason

| Arm | Day · driver | Prompts: median ms at c=1 · verdicts/s at c=16 · p99 ms at c=16 | Responses: the same three |
|---|---|---|---|
| J6 (the study) | 2026-10-02 · 591.86 | 204.1 · 45.9 · 732.6 | 295.4 · 30.1 · 828.7 |
| J6-today | 2026-10-06 · 610.88 | 194.2 · 47.5 · 719.6 | 282.9 · 30.5 · 809.7 |
| **J6N** | 2026-10-06 · 610.88 | **234.9 · 38.5 · 872.1** | **337.5 · 24.5 · 1,045.2** |

- **J6N against J6-today, same night:** 19% fewer verdicts per second at 16 concurrent requests on prompts (38.5 against 47.5) and 20% fewer on responses (24.5 against 30.5); the median call at one request at a time is 21% and 19% longer.
- **Why there is a J6-today.** The pre-registration compared J6N with the study's J6 and named one difference, the serving package. The events of this run then showed a second one: the host's graphics driver had changed between the two days. So the study's arm was run again the same night ([`addendum_same_day_vllm.json`](addendum_same_day_vllm.json), written before its container started; program [`../../scripts/safety_guard_vllm_same_day.py`](../../scripts/safety_guard_vllm_same_day.py)). It repeats the study's figures within 5% (verdicts per second +3.5% and +1.1%, the c=1 median 5% and 4% shorter), and its verdicts too (911/1039 and 136/889). The driver and the day did not move this arm; the difference in the table belongs to the server. [`table_same_day.md`](table_same_day.md)
- **What the two servers say about themselves** (start-up logs, kept outside the repository): the NIM's engine line reads `Initializing a V1 LLM engine (v0.10.0+4019fef1.nv25.06.post1)`, the upstream one `(v0.20.2)`. Both load BF16 with a context of 8,192; the NIM reports a KV cache of 108,144 tokens, upstream 104,800. Which of the differences between the two builds costs the fifth was not looked for.
- The pre-registration expected "within 15%" on verdicts per second. Against the study's J6 it came out at 16% and 19%; against the same-night partner at 19% and 20%.

## 3 · The FP8 profiles built for RTX PRO 6000 Blackwell do not start on an RTX 5090

Both were downloaded and pinned by id, the throughput profile first. Each container exited 38 s after its start with:

```
Profile 'b5938999…' (tensorrt_llm-rtx6000_blackwell_sv-fp8-tp1-pp1-throughput-2bb5:10de-…) is incompatible with detected hardware. Please check the system information below and select a compatible profile.
SYSTEM INFO
- Free GPUs:
  -  [2b85:10de] (0) NVIDIA GeForce RTX 5090
```

and the same for `9325fdae…` (latency). The profile names carry the device id `2bb5:10de`; this card reports `2b85:10de`. `list-model-profiles` had said so beforehand: both stand under "Incompatible with system". There is no J6N-fp8 arm.

## 4 · The 23 blanks: the documentation's prompt is not quite the model card's

The study's prompt for this model is the template of the model card. The template in the NIM's documentation is the same text without the blank that ends each of the 23 category lines ([`before_the_run/prompt_template_comparison.json`](before_the_run/prompt_template_comparison.json)). J6N-tpl is J6N with that one change.

| Arm | Prompts: detection · false alarm | XSTest | Responses: detection · false alarm | verdicts/s at c=16 (prompts · responses) |
|---|---|---|---|---|
| J6N (model card's template) | 87.8% (912/1039) · 15.6% (139/889) | 94.5% · 24.4% | 87.6% (345/394) · 14.1% (59/419) | 38.5 · 24.5 |
| J6N-tpl (documentation's template) | 87.3% (907/1039) · 14.7% (131/889) | 93.0% (186/200) · 22.4% (56/250) | 85.0% (335/394) · 12.4% (52/419) | 39.2 · 25.5 |

- With the documentation's template the model flags a little less of everything: 5 fewer harmful prompts and 8 fewer harmless ones, 10 fewer harmful responses and 7 fewer harmless ones. Each pair of figures overlaps in its Wilson intervals; the direction is the same in all six.
- The expectation written beforehand was "within 1 point". On responses the detection differs by 2.5 points. Blanks at line ends are not nothing to this model.
- Files: [`J6N-tpl/`](J6N-tpl/). No stability rerun for this arm.

## 5 · Through the NeMo Guardrails content-safety rail, as the library documents it for this model

J6G: the generic profile again, asked through the library's content-safety action with the configuration of its own tutorial for this model at tag v0.24.1 — engine `nim`, model type `content_safety`, the prompts file of `examples/configs/content_safety_multilingual/` byte for byte (`max_tokens: 50`, parsers `nemoguard_parse_*`). The study's subset for the Guardrails path, 100 items per track, one call at a time.

| Track | Items (harmful · harmless) | Rail blocks: harmful · harmless | Verdict read from the same answers: detection · false alarm | Rail and verdict of the same call agree | Median ms per call · output tokens (median · max) |
|---|---|---|---|---|---|
| prompts | 52 · 48 | 46 of 52 · 5 of 48 | 46/52 · 5/48 | **100 of 100** | 206.8 · 17 · 33 |
| responses | 48 · 52 | 42 of 48 · 8 of 52 | 42/48 · 8/52 | **100 of 100** | 316.2 · 26 · 42 |

- **The rail does what the model says.** On every item the library's decision is the verdict this study's parser reads from the same completion. No answer was cut: the longest was 42 tokens, under the file's limit of 50, so the case the pre-registration had in mind (a cut JSON object that the library counts as unsafe) did not occur on these 200 items.
- Both synthetic controls were blocked and both harmless ones allowed, on each track.
- **One thing found before any server ran:** the tutorial's configuration for a local NIM names the model twice (`model` and `parameters.model_name`), and the library at the same tag refuses it — `Model name must be specified in exactly one place`. With the name given once it loads. That and the two other changes (the local base URL; the main model pointed at the same server, since nothing is generated here) are in [`J6G/gr_config/`](J6G/gr_config/) and in each precheck record.
- Files: [`J6G/`](J6G/). Its `summary.json` lists, for a track where rail and verdict differ, each such item by id and class; both lists are empty.

## What was expected and what came out

| Pre-registered | Outcome |
|---|---|
| J6N starts | yes |
| J6N: detection and false alarm inside J6's Wilson intervals | yes, on all three data sets and both tracks |
| J6N: verdicts per second at c=16 within 15% of J6 | **no**: 16% and 19% lower (19% and 20% against the same-night upstream arm) |
| J6N: c=1 median within 15% of J6; stability at least 98% | 15% and 14% longer; 100% and 99% |
| J6N-fp8: does not report ready (about 70%) | does not; the image refuses the profile for this card |
| J6N-tpl: within 1 point of J6N everywhere | **no**: up to 2.5 points on responses, the same direction everywhere |
| J6G: controls blocked and allowed; 0 to 10 items per track blocked although their answer reads safe | controls as expected; 0 and 0 |
| Addendum, J6-today: like the study's J6 within 5% | yes |

## What this does not show

- Why the NIM's engine is slower here: the two servers differ in more than a version number, and no cell took them apart.
- Anything about the FP8 TensorRT-LLM profiles on the card they were built for, or about this NIM on a card of its support matrix.
- More than 16 calls in flight, other prompts, or the request parameters of the documentation's example (`max_tokens` 2,048, `top_p` 1): every arm here keeps the study's 100 tokens and greedy sampling.
- The rail around the action: as in the study, the library's action is called on stored text; no answer is generated and the rest of the rails pipeline is not run.
- One run per cell.

**A slip in the frozen file:** the pre-registration gives the study's J6 as "30.3 GiB of the card in use once ready". The record says 30,278 MiB, which is 29.6 GiB. The file is frozen and stays as written; the figure is not used for any conclusion here.

## Files

```
prediction_safety_guard_nim.json (+ .sha256)   the pre-registration
addendum_same_day_vllm.json                    J6-today: why, what each outcome would mean, written before its container
before_the_run/                                the profile listing on this card; the two prompt templates compared
events.jsonl                                   every gate, container start and stop, precheck and cell, in order
J6N/  J6N-tpl/  J6-today/  J6G/                per arm: per-item verdict files without text, cells.jsonl, prechecks, summary.json
table.md / table.json                          one line per arm, track and data set, from the summaries
table_same_day.md / table_same_day.json        J6, J6-today, J6N
```

Programs: [`safety_guard_nim_run.py`](../../scripts/safety_guard_nim_run.py) (the runner; how the study's unchanged programs are pointed at another server and folder is written at its top), [`safety_guard_nim_rail.py`](../../scripts/safety_guard_nim_rail.py) (J6G), [`safety_guard_nim_summary.py`](../../scripts/safety_guard_nim_summary.py), [`safety_guard_vllm_same_day.py`](../../scripts/safety_guard_vllm_same_day.py), the generator of the pre-registration, and [`../../tests/test_safety_guard_nim.py`](../../tests/test_safety_guard_nim.py). Raw answers and container logs are kept outside the repository. The three profiles were fetched beforehand with `download-to-cache --profile <id>` (7.5, 4.4 and 5.1 minutes; not timed for any figure).
