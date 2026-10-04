# Vol.4 · second GPU session (2026-10-04, evening): one library version, one precision at a time, the whole zh corpus

*Working data; nothing here has been published as an article. One RTX 5090 (32 GB), Windows 11 with Docker Desktop (WSL2), driver 591.86. Pre-registration: [`prediction_second_batch.json`](prediction_second_batch.json), frozen 2026-10-04 19:11:23 (+0800), SHA-256 `10e4ab27…c1f9`, before the first GPU step of the session (19:17). It supplements the first session's pre-registration and keeps its rules, data, metrics and method ([`../first_batch/`](../first_batch/README.md)). Run log: [`events.jsonl`](events.jsonl). Every measuring command ran under `timeout`; none reached its limit.*

The extraction-service smoke tests of the same session are in [`../../../vol5-rag-blueprint/`](../../../vol5-rag-blueprint/README.md).

## 1 · The zh difference is not a matter of the transformers version

The first session measured nDCG@10 0.66313 on the reduced MIRACL zh task with the open weights; the published value is 0.64244. While loading, transformers prints that the model's rope key `apply_yarn_scaling` is not recognised. The question was whether another release of the library gives the published value.

**Without the card** ([`before_the_run/`](before_the_run/)):

| What was looked at | Result | File |
|---|---|---|
| The source of 24 releases from 5.0.0 to 5.18.0 (and 4.57.6, which does not have the model class) | no release names the key: the warning is printed by every one of them. The function that computes the YaRN parameters is the same code from 5.0.0 to 5.14.0; the model file is the same from 5.4.0 to 5.14.0 | `transformers_rope_scan.json`, program [`scripts/transformers_rope_scan.py`](../../scripts/transformers_rope_scan.py) |
| What 5.5.0 and 5.13.0 compute for this model's configuration (CPU, no weights loaded) | the same in both: 43 of 64 rotary frequencies are changed by the YaRN interpolation, the factor on the cos/sin tables is 1.0, the frequency vectors have the same SHA-256 | `rope_check_transformers_5.5.0.json`, `rope_check_transformers_5.13.0.json`, program [`scripts/rope_check.py`](../../scripts/rope_check.py) |
| The model's own configuration | saved with transformers 5.5.0; the key that is not recognised has the value `false` | the same two files |
| The two environments | 47 packages, one differs: transformers 5.5.0 and 5.13.0 (the stable release on 2026-07-07, the date of the published result) | `environment_transformers_5.5.0.txt`, `environment_transformers_5.13.0.txt` |

**On the card** ([`reference_tf5130/miracl-hn-zh/`](reference_tf5130/miracl-hn-zh/)), the first session's command in the second environment:

| | transformers 5.5.0 (first session) | transformers 5.13.0 |
|---|---|---|
| nDCG@10 | 0.66313 | 0.66313 |
| Recall@100 | 0.98789 | 0.98789 |
| Vectors of the 393 queries and 81,309 passages | — | **every one equal to the first session's, bit for bit** (`vectors_against_5_5_0.json`) |

This is branch **b** of the pre-registration: a version cause is not supported, and the zh cells stay labelled "control not reproduced, cause unknown". No further variant was tried.

## 2 · One image, two precisions

### `llama-nemotron-embed-1b-v2:1.13.0`: the fp16 profile beside the fp8 profile the image selects

The two profiles are TensorRT engines for compute capability 12.0; nothing else differs (same image, same requests, same client in a container on the NIM's Docker network, 64 passages per request, the first 4,096 passages, one discarded pass, three timed passes). The timed passes of both ran on the same night, 15 minutes apart. The quality figures of the fp8 profile are the first session's (the same engine and data; encoding is not repeated).

| Data set | Precision | nDCG@10 | Recall@100 | Passages/s, median of three (all three) | Card memory added once ready |
|---|---|---|---|---|---|
| SciFact | fp8 | 0.77537 | 0.96333 | **258.4** (257.3 · 258.4 · 259.1) | 3,491 MiB |
| SciFact | fp16 | 0.77718 | 0.96333 | **219.8** (219.4 · 219.8 · 219.8) | 7,191 MiB |
| MIRACL zh, reduced | fp8 | 0.64458 | 0.98326 | **498.4** (490.1 · 499.9 · 498.4) | 3,491 MiB |
| MIRACL zh, reduced | fp16 | 0.64420 | 0.98207 | **452.4** (444.8 · 452.5 · 452.4) | 7,191 MiB |
| MIRACL ja, reduced | fp8 | 0.71579 | 0.98450 | **434.8** (427.9 · 434.8 · 435.4) | 3,491 MiB |
| MIRACL ja, reduced | fp16 | 0.71997 | 0.98620 | **383.9** (378.8 · 383.9 · 384.2) | 7,191 MiB |

- **Quality:** the two precisions differ by 0.0004 to 0.0042 in nDCG@10, in both directions.
- **Speed:** the fp8 profile encodes 10% to 18% more passages per second on these three samples.
- **Memory:** the fp16 profile adds 7.0 GiB to the card once ready, the fp8 profile 3.4 GiB.
- **The vectors themselves are not the same:** the cosine between the fp8 and the fp16 vector of one passage has a median of 0.988 to 0.992 and a minimum of 0.88 (`vectors_against_first_session_fp8.json` in each folder). The rankings built from them score alike, as above.
- The fp8 passes of this night against the first session's (another container, about six and a half hours earlier): 258.4 and 259.1, 498.4 and 485.6, 434.8 and 428.8.
- The fp16 container took 135.6 s to report ready, the fp8 one 58.0 s.

### `nemotron-3-embed-1b:2.2.2`: only fp16 is offered here

| `NIM_ENGINE_PRECISION` | What happened |
|---|---|
| `fp16` | ready after 42.3 s, 3,935 MiB added. nDCG@10 0.66199 and Recall@100 0.98789, the first session's values; 48,624 of the 81,309 passage vectors are bit-for-bit those of the first session and no cosine is below 0.999 |
| `fp8` | the container exits after 6 s: `Error: startup pipeline preference mismatch: pipeline='(none)', precision=Some(Fp8), attention_strategy=None; available compatible pipeline ids: ["padded-naive-fp16"]` |
| `nvfp4` | the same, with `precision=Some(Nvfp4)` |

- The weights mounted for all three starts are the ones this NIM wrote in its download-only mode with nothing set. Whether a download made with a precision set would add a pipeline was not tried. The image holds fp8 kernels for this card's architecture and no fp8 calibration file for this model.
- **The timed passes at fp16, on two days** (same image, same sample, another container): 243.7 passages per second in the first session (243.0 · 243.7 · 249.1) and 230.3 in this one (230.3 · 228.6 · 239.5), a difference of 5.5%. The first session's passes overlapped CPU work of another session on the same host; they were not the slower ones.

## 3 · Every passage of MIRACL zh

*Written when the run has stopped.* The run started at 20:05 on 2026-10-04 with the NIM pinned to fp16 and stops by itself at 08:00 on 2026-10-05. Its record is [`full_corpus/miracl-zh/checkpoints.jsonl`](full_corpus/miracl-zh/checkpoints.jsonl): one line per 100,000 passages (counts, seconds, SHA-256 of the vectors; no text). The vectors are kept outside the repository.

The program is new ([`scripts/encode_corpus_resumable.py`](../../scripts/encode_corpus_resumable.py)); before the run it encoded the first 512 passages of the reduced zh corpus against the real NIM, in two pieces, and the result was compared with the first session's vectors: same ids in the same order, smallest cosine 0.999999998 ([`full_corpus/program_check/against_embed_cell.json`](full_corpus/program_check/against_embed_cell.json)).

Wall times in that file are not speeds: no gate guards them, and the card may be shared during the night.

## What was expected and what came out

| Pre-registered | Outcome |
|---|---|
| Cell 1: branch b, nDCG@10 within 0.001 of 0.66313, every cosine above 0.9999 | as expected (the vectors are identical) |
| `embed-1b-v2` at fp16: nDCG@10 within 0.005 of fp8, fewer passages per second, more card memory | as expected (largest difference 0.0042) |
| `nemotron-3-embed-1b` at fp8: starts, nDCG@10 within 0.005 of fp16, faster | **not as expected: the container does not start at fp8** |
| `nemotron-3-embed-1b` at nvfp4: a guess that it starts | wrong: it does not start |

## What this does not show

- Why the published zh value is lower. The library version is excluded; the conditions of the published run that are not recorded anywhere (batch size, GPU, package versions) remain.
- Speeds of other samples, batch sizes or concurrent clients: each figure is one client, 64 passages per request, the first 4,096 passages of a corpus.
- Anything about fp8 or nvfp4 for `nemotron-3-embed-1b` on other cards.
- A quality figure on the whole MIRACL corpus.
