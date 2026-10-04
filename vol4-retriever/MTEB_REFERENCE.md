# Vol.4 · The model-level reference: two published values and the conditions behind them

**Nothing in this file was measured here.** It records two values that the public MTEB results repository holds for the open weights of one of the models this volume serves, and every condition of them that could be found, each with the file and key it was read from. These conditions are the settings of the reference arm this volume will run first: the open weights on the same task. Whether that arm reproduces the two values is a result that does not exist yet.

## The two values

| | zh | ja |
|---|---|---|
| nDCG@10 (the task's main score) | **0.64244** | **0.74194** |
| Recall@100 | 0.99022 | 0.99243 |
| nDCG@5 / Recall@5 | 0.58674 / 0.62620 | 0.70816 / 0.76605 |

Model `nvidia/Nemotron-3-Embed-1B-BF16`, task `MIRACLRetrievalHardNegatives`, split `dev`.
Source: <https://github.com/embeddings-benchmark/results>, commit `4abe26c645a2adec358ce761c1dded42a5b6e6fa` (2026-10-03), file `results/nvidia__Nemotron-3-Embed-1B-BF16/f880174635613cff04033875fc6a69296cb72006/MIRACLRetrievalHardNegatives.json` (SHA-256 `e341f1a7…836b`), `scores.dev[hf_subset = zh | ja]`.

## The conditions, and where each one is written

`R:` is the results repository at the commit above, folder `results/nvidia__Nemotron-3-Embed-1B-BF16/f880174635613cff04033875fc6a69296cb72006/`. `M:` is the MTEB source at tag `2.14.3` (<https://github.com/embeddings-benchmark/mteb>). `H:` is the model repository <https://huggingface.co/nvidia/Nemotron-3-Embed-1B-BF16> at revision `f880174635613cff04033875fc6a69296cb72006`.

| Condition | Value | Read from |
|---|---|---|
| Model and revision | `nvidia/Nemotron-3-Embed-1B-BF16` at `f880174635613cff04033875fc6a69296cb72006` | `R:model_meta.json` → `name`, `revision` |
| MTEB version | 2.14.3 | `R:MIRACLRetrievalHardNegatives.json` → `mteb_version` |
| Task data | `mteb/MIRACLRetrievalHardNegatives` at `d7d94fa4b946cec4a27c84653aa0cf6b33f74a3c`, split `dev` | the same file → `dataset_revision`; `M:mteb/tasks/retrieval/multilingual/miracl_retrieval.py` lines 4 and 79–82 (`_EVAL_SPLIT`, `dataset.path`, `dataset.revision`) |
| Main score | `ndcg_at_10` | `M:` the same file, line 34 (`main_score`) |
| How the model is loaded | Sentence Transformers, through MTEB's `SentenceTransformerEncoderWrapper` | `R:model_meta.json` → `loader` |
| Longest input | **4,096 tokens** (the model itself allows 32,768) | `R:model_meta.json` → `loader_kwargs.processor_kwargs.model_max_length`; `max_tokens` |
| Device | `cuda` | `R:model_meta.json` → `loader_kwargs.device` |
| Precision | bf16 weights; `output_dtypes` `bfloat16` | `H:config.json` → `dtype`; `R:model_meta.json` → `output_dtypes` |
| Prefix of a query | `query: ` | `H:config_sentence_transformers.json` → `prompts.query` |
| Prefix of a passage | `passage: ` | `H:config_sentence_transformers.json` → `prompts.document` |
| Why those prefixes apply | the wrapper takes the model's built-in prompts when none are given, and encodes with `encode_query` / `encode_document` | `M:mteb/models/sentence_transformer_wrapper.py` lines 110–112 and 219–235; `R:model_meta.json` → `use_instructions: false` (no task instruction is added) |
| Text of a passage | title, one space, text, then stripped; the text alone when there is no title | `M:mteb/_create_dataloaders.py` lines 59–62 (`_corpus_to_dict`) |
| Text of a query | the `text` column as it is | `M:mteb/_create_dataloaders.py` lines 75–86 (an instruction is prepended only when the data has an `instruction` column; this data set has none) |
| Pooling | mean over the tokens, prompt tokens included | `H:1_Pooling/config.json` → `pooling_mode_mean_tokens: true`, `include_prompt: true` |
| Normalisation | yes (a `Normalize` module ends the pipeline) | `H:modules.json`, third module |
| Embedding size | 2,048 | `R:model_meta.json` → `embed_dim`; `H:1_Pooling/config.json` → `word_embedding_dimension` |
| Similarity | cosine | `R:model_meta.json` → `similarity_fn_name`; `H:config_sentence_transformers.json` → `similarity_fn_name` |
| Search | exact, over the whole corpus of the task in chunks of 50,000 passages; the 1,000 highest scores per query are kept | `M:mteb/models/search_wrappers.py` lines 45 and 270–280; `M:mteb/abstasks/retrieval.py` lines 154–155 (`k_values`, `_top_k = max(k_values)`) |
| A passage with the id of the query | kept (`ignore_identical_ids = False`) | `M:mteb/abstasks/retrieval.py` line 152 |
| Metric program | `pytrec_eval`, measures `ndcg_cut` and `recall` among others | `M:mteb/_evaluators/retrieval_metrics.py` lines 582–591 |
| Averaging and rounding | the mean over the queries `pytrec_eval` scored, rounded to five decimals | `M:mteb/_evaluators/retrieval_metrics.py` lines 498 and 500 |
| Date of the result | 2026-07-07 09:12 UTC; 15,316 s for the task's 18 languages together | `R:MIRACLRetrievalHardNegatives.json` → `date`, `evaluation_time` |

**Not recorded anywhere we could find**

| | What is known |
|---|---|
| Batch size | `R:experiments/…/run_settings.jsonl` has 125 lines, all for other tasks (`encode_kwargs.batch_size` 16 in 115 of them, 32 in eight, 2 in one, not given in one); it has **no line for this task** |
| Versions of torch, sentence-transformers and transformers for this result | the same file gives them for other tasks only: 76 lines with MTEB 2.18.1 (torch 2.10.0+cu126, sentence-transformers 5.5.1, transformers 5.8.1) and 49 with MTEB 2.18.7 (sentence-transformers 5.6.1, transformers 5.14.1). Both are later than this result's 2.14.3. The model repository's own `config_sentence_transformers.json` names sentence-transformers 5.4.1, transformers 5.5.0, torch 2.11.0+cu130 as the versions it was saved with |
| GPU model | not stated |
| Which side of an over-long input is cut | the tokenizer configuration has no `truncation_side` entry (the library's default is the right side); `padding_side` is `left` |

The reference arm records the versions it runs with. If its values differ from the two above, these unrecorded conditions are where a difference can come from, and the difference is reported as measured.

## The task is not the full MIRACL

| | zh | ja |
|---|---|---|
| Passages in the task's corpus | 81,309 | 185,319 |
| Passages in the full MIRACL corpus | 4,934,368 | 6,953,614 |
| Queries (dev) | 393 | 860 |
| Judgements; of these relevant | 3,928; 994 | 8,354; 1,790 |

- The task description says the reduced corpus was made "by pooling the 250 top documents per query from BM25, e5-multilingual-large and e5-mistral-instruct" (`M:` task file, line 78).
- The counts are the publishers': the data-set card (`dataset_info`) and `M:mteb/descriptive_stats/Retrieval/MIRACLRetrievalHardNegatives.json`. The downloaded files have exactly these counts ([`tests/test_retrieval_datasets.py`](tests/test_retrieval_datasets.py), with `VOL4_DATASETS` set).
- Checked on the downloaded files, not stated by the publishers: the queries and the judgements are those of MIRACL dev, pair for pair; every relevant passage is in the reduced corpus (994 of 994, 1,790 of 1,790); of the passages judged non-relevant, 2,516 of 2,934 (zh) and 5,768 of 6,564 (ja) are in it.
- For every passage of both corpora, the title-and-text rule of this repository (`passage_text` in [`scripts/retrieval_datasets.py`](scripts/retrieval_datasets.py)) gives the same string as MTEB's rule above (0 of 81,309 and 0 of 185,319 differ).
- A score on this task is **not** a score on the full MIRACL corpus and is never listed as one. The reader `miracl-hn-zh` / `miracl-hn-ja` refuses to hand a corpus of another size to a run (`check_published_counts`).

## Licence of the task data

The data-set card of `mteb/MIRACLRetrievalHardNegatives` states `license: cc-by-sa-4.0`, and so does the MTEB task definition (`M:` task file, line 38). The repository is not gated. No file of it is in this repository.

## The same weights are in the NIM

The file `model.safetensors` of `H:` (SHA-256 `f959c3b04e66b42de280bfb97c140cb7e0bfe25e3ecb0b4464c68a8436b2d04f`) is byte-identical to the one the NIM `nemotron-3-embed-1b:2.2.2` writes in its download-only mode; `config.json`, the tokenizer files, the pooling configuration and the Sentence Transformers configuration are identical as well. The reference arm and the NIM therefore start from the same weights; what differs between them is the serving path.
