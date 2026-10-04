# Vol.4 · First GPU session: the open weights against a published value, the NIM of the same model, three more embedding NIMs, two rerankers

*Run on 2026-10-04, 12:12 to 14:35 (+0800), on one RTX 5090, one model on the card at a time. Working data of Vol.4; nothing here has been published as an article. Two preparation cells for Vol.5 ran afterwards in the same session and are in [`../../../vol5-rag-blueprint/`](../../../vol5-rag-blueprint/README.md).*

**What is in this directory, and what is not.** The pre-registration, the run log, and for every encoder its own directory with the scores (the two metrics and their per-query values), the timed passes and the records of each step. Vectors, run files and container logs are outside the repository; a run file lists passage ids of a data set. No text of a data set is here.

All figures: [`table.md`](table.md), built from the result files by [`../../scripts/first_batch_table.py`](../../scripts/first_batch_table.py).

## 1 · Does this repository's path reproduce a published value? One language yes, one no

The model-level check of this volume ([`../../MTEB_REFERENCE.md`](../../MTEB_REFERENCE.md)): the open weights `nvidia/Nemotron-3-Embed-1B-BF16` on the reduced MIRACL task, run through this repository's own programs with the conditions of the published MTEB result.

| nDCG@10 (Recall@100) | zh | ja |
|---|---|---|
| Published in the MTEB results repository | 0.64244 (0.99022) | 0.74194 (0.99243) |
| **This repository's path, open weights (the reference arm)** | **0.66313** (0.98789) | **0.74383** (0.99202) |
| MTEB itself (source tag 2.14.3) in this environment, same weights and loader arguments | 0.66251 (0.98789) | not run |
| The NIM `nemotron-3-embed-1b:2.2.2` (fp16) | 0.66199 (0.98789) | 0.74371 (0.99163) |

- **ja is reproduced**: +0.0019, inside the 0.005 written down beforehand.
- **zh is not**: +0.021. The pre-registration's rule for that case was to run MTEB itself once as the arbiter. MTEB in this environment gives 0.66251, which is this repository's figure to 0.0006 and not the published one. By the rule this is the case "neither reproduces": the environment differs from the published run in a condition that is not recorded anywhere (library versions, batch size, GPU; see `MTEB_REFERENCE.md`), the difference is reported as measured, and nothing was tuned to make it fit.
- What this does establish: on the same weights, this repository's path and MTEB's own code agree, and the NIM agrees with both (zh within 0.0011, ja within 0.0001). The zh cells below carry the label **control not reproduced**: they are compared with the reference arm of this session, not with the published figure.
- One thing seen while loading the weights and not explained: `transformers` 5.5.0 prints that it does not recognise the key `apply_yarn_scaling` in the model's configuration. Whether the published run used a version that does is not known.
- MTEB 2.14.3 is not on the package index (2.14.5 to 2.14.9 are); the arbiter used the source tag.

## 2 · The NIM of the same model: what the serving path does

`nemotron-3-embed-1b:2.2.2`, weights fetched beforehand by the image's download-only mode (`model.safetensors` byte-identical to the open weights).

| Question | What was seen |
|---|---|
| Does it start on this card? | Yes: `GPU SM120 detected`, 280 attention plans compiled at the first start; ready after 52.9 s, and after 26.9 s at the next start with the plan cache. Its support matrix does not list the RTX 50 series |
| Profiles | The image has no `list-model-profiles` step (its documentation says so; given the command, it starts the server). Precision is picked at start-up or set with `NIM_ENGINE_PRECISION` |
| Which precision did it pick? | The log does not say. A second start pinned to `fp16` returned vectors with cosine 1.0 to the first start's on sixteen texts: it ran in fp16. There is therefore no separate fp16 cell; fp8 and nvfp4 were not tried |
| `input_type` and the prefix | The NIM's vector with `input_type` has cosine 0.99993 to 0.99999 with the reference arm's vector of the same text with `query: ` or `passage: ` written out. `input_type` is the prefix |
| The wrong `input_type` | A query sent as a passage: cosine 0.56 to 0.76 with its query-mode vector |
| A prefix written by the client as well | Applied on top, not recognised: cosine 0.957 to 0.999 with the plain request. A client must not add it |
| An over-long input | `truncate: END`: HTTP 200, 4,096 tokens used. `truncate: NONE`: HTTP 400, "exceeds maximum of 65536 characters". In the task, 1 zh and 3 ja passages are longer than 4,096 tokens |
| Vector size | 2,048; a request for 1,024 is refused ("dimensions must be one of 2048") |
| Memory | 5,005 MiB on the card once ready, about 1,070 MiB of it the desktop's |

Records: `nim_nemotron-3-embed-1b_auto/*/probe.json`, `nim_nemotron-3-embed-1b_fp16/`, [`events.jsonl`](events.jsonl).

## 3 · The method of this volume, and what it replaces

From this volume on the timing client runs in a container on the NIM's Docker network, with one kept connection. The method cell sent the same requests to the same NIM from the container and from the host through the published port:

| Client | Connection | 1 passage per request: p50 / p90 / p99 ms | Requests more than 10 ms above p10 | 64 passages per request: passages per second |
|---|---|---|---|---|
| container | kept | 4.0 / 5.8 / 7.4 | 0 of 300 | 241.1 |
| container | new per request | 5.1 / 6.7 / 8.5 | 0 of 300 | 239.9 |
| host | kept | 5.3 / 7.3 / 9.7 | 0 of 300 | 214.9 |
| host | new per request | 7.5 / **31.2 / 42.1** | **96 of 300** | 208.9 |

- Written down beforehand: through the host port with a new connection per request the durations fall into two groups, in the container they do not. That is what happened. The slow group is the one found in the judge study of Vol.3 (about 16 ms on top of a call).
- Not expected: with 64 passages per request the host path is about 11% slower than the container even on a kept connection (214.9 against 241.1 passages per second). The answers of such a request are large (64 vectors of 2,048 numbers as text).
- For the batch of 64 the column "more than 10 ms above p10" says nothing: those requests differ in length.

## 4 · The embedding cells

Per encoder and data set: nDCG@10 and Recall@100 over the whole corpus, and passages per second on the first 4,096 passages (64 per request, median of three timed passes after one discarded pass). The same cells with the range of the three passes are in [`table.md`](table.md).

| Encoder (what it ran as) | SciFact | MIRACL reduced, zh | MIRACL reduced, ja |
|---|---|---|---|
| `nemotron-3-embed-1b:2.2.2` (fp16) | 0.752 · 0.957 · 154/s | 0.662 · 0.988 · 244/s | 0.744 · 0.992 · 226/s |
| `llama-nemotron-embed-1b-v2:1.13.0` (TensorRT fp8) | 0.775 · 0.963 · 259/s | 0.645 · 0.983 · 486/s | 0.716 · 0.985 · 429/s |
| `llama-nemotron-embed-vl-1b-v2:2.3.0` (its log names no precision) | 0.767 · 0.967 · 175/s | 0.648 · 0.981 · 280/s | 0.719 · 0.987 · 250/s |
| `llama-nemotron-embed-300m-v2:1.13.0` (TensorRT fp8) | 0.713 · 0.950 · 485/s | 0.593 · 0.974 · 796/s | 0.676 · 0.966 · 743/s |
| open weights, in the client's process (bf16) | not run | 0.663 · 0.988 · 369/s | 0.744 · 0.992 · no figure |

What each container started as (seconds to ready; card memory once ready, of which about 1,000 MiB is the desktop's):

| Image | Selected | Ready after | Card memory |
|---|---|---|---|
| `nemotron-3-embed-1b:2.2.2` | kernels for `sm120` in the image; fp16 (shown by the pinned start) | 52.9 s first, 26.9 s with the plan cache | 5,005 MiB |
| `llama-nemotron-embed-1b-v2:1.13.0` | profile `ee7364e4…`: TensorRT fp8 for compute capability 12.0, engine 1,542 MiB | 48.1 s | 4,474 MiB |
| `llama-nemotron-embed-300m-v2:1.13.0` | the same profile id; engine folder `rtx5090x1-trt-fp8-…`, 925 MiB | 33.5 s | 3,654 MiB |
| `llama-nemotron-embed-vl-1b-v2:2.3.0` | kernels for `sm120` in the image | 63.1 s | 6,621 MiB |

The weights of the 1.x images were fetched beforehand without the GPU (`download-to-cache` with `NIM_CPU_ONLY=1`, for the fp16 and fp8 profiles of compute capability 12.0), so "ready after" contains no download.

- **Nothing in this section is a reproduction of an official score.** No published per-data-set value exists for these models on these data sets except the two of section 1.
- The cells of one encoder differ from another encoder's in more than the model: the 1.13.0 images selected a TensorRT fp8 profile for this card, the 2.x images run a 16-bit path. What each one selected is in the container table.
- Speed is client wall time through one kept connection inside the Docker network. It includes turning 64 vectors into text and back.
- The reference arm's speed is the open weights in the client's own process (no server, no HTTP), 64 per batch. On ja it has no figure: the step was stopped after ten minutes with the card's memory full (the 64 longest passages of the sample form one batch in Sentence Transformers and do not fit at 4,096 tokens).

## 5 · Reranking

The first 100 results per query of the NIM of section 2 were scored again by each reranking NIM, one call per query with its 100 passages (`truncate: END`); scores of different calls are never put on one scale. Pairs per second: the first 40 queries, three timed passes after four discarded calls.

| Reranker (what it ran as) | SciFact: nDCG@10 before → after · pairs/s | MIRACL reduced, zh | MIRACL reduced, ja |
|---|---|---|---|
| `llama-nemotron-rerank-1b-v2:1.10.0` (TensorRT fp8, engine 1,542 MiB; 4,497 MiB on the card; ready after 63.3 s) | 0.752 → 0.794 · 341/s | 0.662 → 0.686 · 656/s | 0.744 → 0.772 · 611/s |
| `llama-nemotron-rerank-500m-v2:1.10.0` (TensorRT fp8, engine 1,068 MiB; 4,025 MiB; ready after 47.7 s) | 0.752 → 0.794 · 600/s | 0.662 → 0.673 · 1,120/s | 0.744 → 0.752 · 1,040/s |

- Recall@100 does not change: the reranker orders the same 100 passages.
- Both engine folders are named after another card (`rtx6000-blackwell-svx1-trt-fp8-…`); they are the profile for compute capability 12.0, which this card has.
- The first stage is one encoder (the fp16 NIM of section 2). What a reranker adds on top of another first stage was not measured.

## 6 · Checks

- **Pre-registration**: [`prediction_first_batch.json`](prediction_first_batch.json), frozen at 12:12:17 (SHA-256 in the `.sha256` file), before the first GPU step. It binds the cell programs by SHA-256. Six programs were written after it, each before its first use and with its hash in `events.jsonl`: the arbiter, the method cell, the table program and the three Vol.5 programs. The pre-registration announces only "the programs of the Vol.5 cells"; the first three are a departure from it. The table program was changed once after its first use (the change and the new hash are in `events.jsonl`), and four tests of the search were added after the session (`tests/test_score_run.py`); the bound programs were not touched.
- **Controls before a cell**: a smoke step (finite vectors of the expected size and unit length; a passage sent in another batch size must be nearest to itself). All passed. The same step refuses a stand-in server that returns vectors of another length.
- **Negative control of `input_type`**: section 2, third row.
- **Timed parts**: each is one blocking call from the measuring session, with the idle-card gate right before it; nothing else was started from the session while one ran. Encoding a whole corpus is not timed: its wall time is recorded and is not a speed.
- **Gates**: utilization and power as before, and now also the memory the desktop holds on the card, a count of game-launcher processes and other containers. Counts are at the end of `table.md`.
- **The data**: before every cell on the reduced MIRACL task the reader checks the published counts (81,309 and 185,319 passages), so that the full corpus cannot stand in for it.

## 7 · What this does not show

- **One run per cell.** No interval on any speed; three timed passes show how far a cell repeats itself within one container.
- **Speeds are not comparable across precisions and engines without saying so.** fp8 TensorRT engines and a 16-bit path are different things; the table says which is which.
- **The zh figures have no outside anchor.** They agree among three independent paths on the same weights; the published figure is 0.021 lower and the reason is not known.
- **The full MIRACL corpus and HotpotQA were not run** (millions of passages each). A score on the reduced task is not a score on the full corpus.
- **No statement about why one model scores higher than another.**

## Files

```
prediction_first_batch.json · .sha256   the pre-registration and its hash
events.jsonl                            every gate, container start and stop, client step and note, in order
table.md                                the tables, from the files below
token_counts/                           how many queries and passages exceed 4,096 tokens (tokenizer of the open weights)
reference_bf16/<data set>/              smoke, throughput, encode, score; mteb_arbiter/zh.json
nim_<model>_<precision>/<data set>/     smoke, throughput, encode, score, probe (the 2.2.2 NIM)
method_host_vs_container/               eight runs: place x connection x passages per request, every request's duration
rerank_<model>/<data set>/              smoke, throughput, rerank, score_after
```
