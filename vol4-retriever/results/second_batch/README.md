# Vol.4 · second GPU session (2026-10-04, evening): one library version, one precision at a time, the whole zh corpus

*Working data; nothing here has been published as an article. One RTX 5090 (32 GB), Windows 11 with Docker Desktop (WSL2), driver 591.86. Pre-registration: [`prediction_second_batch.json`](prediction_second_batch.json), frozen 2026-10-04 19:11:23 (+0800), SHA-256 `10e4ab27…c1f9`, before the first GPU step of the session (19:17). It supplements the first session's pre-registration and keeps its rules, data, metrics and method ([`../first_batch/`](../first_batch/README.md)). Run log: [`events.jsonl`](events.jsonl). Every measuring command ran under `timeout`; none reached its limit.*

The extraction-service smoke tests of the same session belong to Vol.5 and are published with it. The pre-registration binds one of their programs by SHA-256 (`../vol5-rag-blueprint/scripts/extraction_smoke.py`); that file is not part of this volume, so this one binding can be checked only against the Vol.5 publication.

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

- The weights mounted for these three starts are the ones this NIM wrote in its download-only mode with nothing set. **Followed up the same evening:** the download-only mode was run again with a precision pinned. With `fp8` it wrote the same 14 files, byte for byte (same `model.safetensors`). With `nvfp4` it wrote another set: 18 files, 997 MiB, a quantised checkpoint with its own manifest. A start with `NIM_ENGINE_PRECISION=nvfp4` and those files mounted ended the same way after 16.7 s, with the same list of one compatible pipeline, `padded-naive-fp16` (run on a card shared with the encoding job of section 3; record in [`nvfp4_followup_events.jsonl`](nvfp4_followup_events.jsonl), name `p111_n3embed_nvfp4`: its two lines, copied byte for byte from the run log of the Vol.5 smoke tests of that evening, lines 27 and 28). So on this card this image offers the fp16 pipeline only, whichever weights are mounted. The image holds fp8 kernels for this card's architecture and no fp8 calibration file for this model.
- **The timed passes at fp16, on two days** (same image, same sample, another container): 243.7 passages per second in the first session (243.0 · 243.7 · 249.1) and 230.3 in this one (230.3 · 228.6 · 239.5), a difference of 5.5%. The first session's passes overlapped CPU work of another session on the same host; they were not the slower ones.

## 3 · Every passage of MIRACL zh and of MIRACL ja

`nemotron-3-embed-1b:2.2.2` pinned to fp16, in two stretches. The first ran from 20:05 on 2026-10-04 until the stop time of 08:00 on 2026-10-05: the program stopped by itself at 08:00:03, the container was removed at 08:00:13 and the closing gate found no container and an idle card. The second, in a new container on the afternoon of 2026-10-05, went on from the last record and ended with the corpus at 17:24:00; again the container was removed and the closing gate passed (no container, 0%).

| Corpus | Passages encoded | Pieces | From → to (+0800) | State |
|---|---|---|---|---|
| MIRACL zh | **4,934,368 of 4,934,368** | 50 | 20:05:35 → 02:04:57 | finished |
| MIRACL ja | **6,953,614 of 6,953,614** | 71 | 02:05:05 → 08:00:03 (5,132,768 passages, 52 pieces, stopped at the stop time), then 15:17:47 → 17:24:00 on 2026-10-05 (the remaining 1,820,846 in 19 pieces) | finished |

- Records: [`full_corpus/miracl-zh/checkpoints.jsonl`](full_corpus/miracl-zh/checkpoints.jsonl), [`full_corpus/miracl-ja/checkpoints.jsonl`](full_corpus/miracl-ja/checkpoints.jsonl) — one line per piece of 100,000 passages: counts, seconds, the SHA-256 of the piece's vectors and ids; no text. Every piece: vectors of size 2,048, all finite. The vectors are kept outside the repository (float32, 38.6 GB and 54.4 GB).
- **The stop and the later continuation are in the record**: the ja file holds a `stopped` line at 5,132,768 passages, a second `session` line that says 5,132,768 passages were already done, and a `finished` line. Before it went on, the program read back the 52 stored pieces and compared each with its recorded SHA-256.
- The queries of the dev split were encoded once per corpus (393 and 860).
- **Wall times in these files are not speeds.** No gate guards them and the card was shared on purpose: between 21:48 and 21:57, and again between 03:31 and 03:38, other containers of this repository's work ran on the same card (smoke tests of Vol.5). On 2026-10-05 two such containers ran between 15:12 and 15:14, while the program was still reading back the stored pieces and before it encoded anything. A full piece took 358 to 487 s for zh and 388 to 451 s for ja; the slowest ones overlap those tests and the downloads before them.
- The Docker health check of this image reported "unhealthy" for the whole run while the server answered every request; the health check is the image's own and was not looked into.

The program is new ([`scripts/encode_corpus_resumable.py`](../../scripts/encode_corpus_resumable.py)); before the run it encoded the first 512 passages of the reduced zh corpus against the real NIM, in two pieces, and the result was compared with the first session's vectors: same ids in the same order, smallest cosine 0.999999998 ([`full_corpus/program_check/against_embed_cell.json`](full_corpus/program_check/against_embed_cell.json)).

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
- A quality figure on the whole MIRACL corpus: the vectors exist, no search over them was run.
