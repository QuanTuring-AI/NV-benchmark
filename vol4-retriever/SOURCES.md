# Vol.4 · Sources read before any measurement

Everything below was read on **2026-10-03**. Each entry gives where it was read and what it says. Nothing in this file was measured here; where a page and a later measurement disagree, the measurement will be reported beside the page.

## 1 · API of the retrieval NIMs

The request and response shapes in `scripts/nim_retrieval_clients.py` come from the OpenAPI files that the documentation's "API Reference" pages offer for download.

| API | Documentation version | OpenAPI file (as downloaded) | SHA-256 | What it fixes |
|---|---|---|---|---|
| Embedding, `POST /v1/embeddings` | text-embedding 1.13.0 | <https://docs.nvidia.com/nim/nemo-retriever/text-embedding/1.13.0/reference.html> → `openai-api.openapi.yaml` (says version 1.13.0) | `e3fcdd237fe2fbebe3b1133d248ae04f97ea398413f0bc583c1aed2c27f3892f` | required `input` (a string or up to 8,192 strings) and `model`; optional `input_type` (`query`, `passage`), `truncate` (`START`, `END`, `NONE`; default `NONE`), `encoding_format`, `embedding_type`, `dimensions`, `modality`, `user` |
| Embedding | embedding 2.2 and 2.3 | <https://docs.nvidia.com/nim/nemo-retriever/embedding/2.3/reference.html> → same file name (says version 2.2.0; the 2.2 and 2.3 pages serve the same bytes) | `7dca79070202e7d33ca93f464b12e46e4433084ca10d68f2d4d5fb93d424f000` | the same fields; `dimensions` is limited to 128, 256, 384, 512, 768, 1024, 1536, 2048 |
| Reranking, `POST /v1/ranking` | text-reranking 1.10.0 | <https://docs.nvidia.com/nim/nemo-retriever/text-reranking/1.10.0/reference.html> → `ranking.openapi.yaml` (says version 1.10.0) | `503a561faeb0c5c01aea2b7c5bb7f87eabec10fb086ede8205309ac185c1e715` | required `model`, `query` (`{"text": …}`), `passages` (1 to 512 of `{"text": …}`); optional `truncate` (`END`, `NONE`; default `NONE`); the answer is `rankings`: `{index, logit}` per passage |
| Reranking | reranking 2.3 | <https://docs.nvidia.com/nim/nemo-retriever/reranking/2.3/reference.html> → same file name (says version 1.11.0) | `2228fa8a10e1cc5b5193d6681dce62ecca7b232514c50370bf77e13baeefa0cb` | the same request fields |

From the usage pages of the same documentation:

- Query mode and passage mode. The embedding page says that models with the two modes need `input_type`, that passages are embedded with `passage` at indexing time and questions with `query` at query time, and that using the wrong one costs a large part of the retrieval accuracy. The mode can also be given as a `-query` or `-passage` suffix of the model name instead of the field.
- Truncation. With `truncate` set to `NONE` the server answers an over-long input with an error; with `END` it drops the tokens past the limit. The reranking page adds that query and passage share one token limit, so a query close to the limit leaves no room for the passage.
- One reranking call takes at most 512 passages.

The harness sends `input_type` and `truncate` explicitly on every request and records them per run. It does not split a reranking request of more than 512 passages; whether scores from separate calls share a scale has not been checked on a server.

## 2 · What the model cards report

Machine-readable copy with every number, condition and source: [`MODEL_CARD_CLAIMS.json`](MODEL_CARD_CLAIMS.json) (26 figures, each checked to occur in the card text).

| Model | Card | Metric on the card | Largest text figure | Conditions the card states |
|---|---|---|---|---|
| `llama-nemotron-embed-1b-v2` | Hugging Face, revision `113abe4a…2348` | average Recall@5 over a group of data sets | 68.60% over NQ, HotpotQA, FiQA, TechQA | PyTorch checkpoint on A100 GPUs, not the NIM; at most 8,192 tokens; `query:` and `passage:` prefixes in the card's example |
| `llama-nemotron-rerank-1b-v2` | Hugging Face, revision `82876565…1443` | average Recall@5 of the pipeline embed-1b-v2 + rerank-1b-v2 | 73.64% over the same four | number of reranked candidates not stated; at most 8,192 tokens; a `question:… passage:…` prompt template |
| `llama-nemotron-embed-vl-1b-v2` | Hugging Face, revision `582e3bf7…7ee`, and build.nvidia.com | average Recall@5 | 69.19% on "BEIR retrieval + TechQA" | evaluated up to 10,240 tokens; 8,192 for text in the card's example |
| `nemotron-3-embed-1b` | build.nvidia.com | average nDCG@10 over each benchmark's tasks | 72.38 on RTEB (BF16), 72.00 (NVFP4) | evaluated at 4,096 tokens; the NVFP4 figure on a GB200 |
| `llama-nemotron-embed-300m-v2`, `llama-nemotron-rerank-500m-v2` | none found | — | — | the links in the support matrix lead to the site's not-found page; the NGC model pages ask for a login; no Hugging Face repository under either name |

**Which figures fall on the data sets this volume uses (SciFact, HotpotQA, MIRACL zh and ja): none.** Every figure is an average over a group. HotpotQA is one of four members of a group; the cards' MIRACL figures are on an internal, subsampled version over 26 languages; SciFact is in no named group. A card figure can therefore not serve as a per-data-set target for this volume.

### What the MTEB results repository holds (kept apart from the cards)

<https://github.com/embeddings-benchmark/results> at commit `4abe26c645a2` (2026-10-03): 710 model folders, 12 of them NVIDIA's. Machine-readable copy: [`MODEL_CARD_CLAIMS.json`](MODEL_CARD_CLAIMS.json) → `mteb_results`.

| Model of this volume | Folder | On SciFact, HotpotQA, MIRACL zh or ja |
|---|---|---|
| `llama-nemotron-embed-1b-v2`, `llama-nemotron-embed-300m-v2`, `llama-nemotron-rerank-1b-v2`, `llama-nemotron-rerank-500m-v2` | none | 0 results |
| `llama-nemotron-embed-vl-1b-v2` | `nvidia__llama-nemotron-embed-vl-1b-v2` (19 result files) | 0: its `MIRACLRetrieval` file holds one language, Korean |
| `nemotron-3-embed-1b` (open weights `nvidia/Nemotron-3-Embed-1B-BF16`) | `nvidia__Nemotron-3-Embed-1B-BF16` (118 result files) | 0 on the four data sets. It has `MIRACLRetrievalHardNegatives` for 18 languages, zh and ja among them; `MIRACLReranking` for German only; `LMEB_SciFact`, another packaging of SciFact (1,936 documents and queries together, against 5,183 passages and 300 test queries in the BEIR packaging); and a Dutch translation of SciFact |

The two values this volume takes as its model-level reference come from the third row: `MIRACLRetrievalHardNegatives`, dev, nDCG@10 **0.64244 (zh)** and **0.74194 (ja)**. That task has a reduced corpus, so it is a different measurement from the full MIRACL corpus. Its conditions, each with its source: [`MTEB_REFERENCE.md`](MTEB_REFERENCE.md).

Open weights for that model exist under names that differ from the NIM's: `nvidia/Nemotron-3-Embed-1B-BF16` and `nvidia/Nemotron-3-Embed-1B-NVFP4` (revision `f630128278eb`), both under OpenMDW 1.1 and neither gated. The published result names the BF16 revision `f880174635613cff04033875fc6a69296cb72006`; the repository's newest commit on the day (`c0c9fea93ea4`) differs from it in `README.md` only.

## 3 · What the support matrices say about this card and about WSL2

The RTX 5090 has CUDA compute capability 12.0.

| Model | Page | What the page lists |
|---|---|---|
| `llama-nemotron-embed-1b-v2`, `llama-nemotron-embed-300m-v2` | <https://docs.nvidia.com/nim/nemo-retriever/text-embedding/1.13.0/support-matrix.html> | optimized configuration by compute capability: 12.0 with FP16 and FP8. Approximate GPU memory at 12.0: embed-1b-v2 2.98 GiB (FP8), 6.53 GiB (FP16); embed-300m-v2 2.04 GiB (FP8), 3.53 GiB (FP16). The non-optimized configuration takes at most 4,096 tokens instead of 8,192 |
| `llama-nemotron-rerank-1b-v2`, `llama-nemotron-rerank-500m-v2` | <https://docs.nvidia.com/nim/nemo-retriever/text-reranking/1.10.0/support-matrix.html> | optimized configuration by compute capability: 12.0 with FP16 and FP8. Approximate GPU memory for rerank-1b-v2 at 12.0: 3.68 GB (FP8), 7.59 GB (FP16) |
| `llama-nemotron-embed-vl-1b-v2` (1.12.0) | text-embedding 1.13.0 support matrix | optimized configurations for named data-centre GPUs only; no compute-capability row. Non-optimized: 4.4 to 21 GiB of GPU memory, FP16 |
| `llama-nemotron-embed-vl-1b-v2` (2.x) | <https://docs.nvidia.com/nim/nemo-retriever/embedding/2.3/support-matrix.html> | a list of GPUs that does not include the RTX 50 series; the default profile takes 2,048 tokens |
| `nemotron-3-embed-1b` | the same 2.3 page | NVFP4 and FP16 on RTX PRO 6000 Blackwell Server Edition and GB200, FP16 on six more GPUs; the RTX 50 series is not listed. The page says: "Fallback behavior on GPUs that are not listed has not been verified for this model." Validated at 4,096 tokens |

- Selection order (1.x): a GPU-specific engine, then a compute-capability engine, then ONNX or PyTorch. From 2.0 the NIM picks a kernel set for the detected compute capability at start-up and falls back to an architecture-agnostic FP16 set when none is optimized.
- WSL2: the getting-started pages tell owners of an RTX AI PC or workstation to install WSL2 and point to the "NIM on WSL2" documentation; Kubernetes is not supported there. The support matrices themselves do not mention WSL2 or Docker Desktop.
- Weights ahead of time: from 2.0, a container started with `NIM_ENGINE_MODEL_DOWNLOAD_ONLY=1` and a folder mounted at `/model` downloads the weights and exits; the page says this run needs no GPU argument. For 1.x the documented `download-to-cache` example carries `--gpus all`.

## 4 · Known problems on RTX 50 cards, WSL2 and Docker Desktop

Searched on 2026-10-03: GitHub issues and pull requests of `NVIDIA/NeMo-Retriever` (the former `nv-ingest`), `NVIDIA-AI-Blueprints/rag`, `NVIDIA/GenerativeAIExamples`, `NVIDIA/nim-deploy` and `NVIDIA/nvidia-container-toolkit`, each for "5090", "RTX 50", "Blackwell", "WSL", "WSL2", "Docker Desktop", "compute capability", "sm_120"; and the NVIDIA developer forum for nine phrases naming these NIMs with "5090", "WSL2" or "Docker Desktop".

| Where | What | State |
|---|---|---|
| Forum, topic 351835 (2025-11-18) | the OCR NIM 1.1.0 on an RTX 5090 under WSL2: the container reports ready, every request fails with HTTP 500 from a Triton preprocessing stub | one post, no reply. This volume holds `nemotron-ocr-v1:1.3.0`, a later version; whether it behaves the same is not known |
| Forum, topic 339908 (2025-07-22) | an embedding NIM under WSL2 with Docker Desktop on an RTX 4070 laptop; the user took a warning about the GPU power limit for the fault | answered by staff: the warning is not an error |
| `NVIDIA/NeMo-Retriever` pull request 2731 (open, 2026-09-21) | lets the Helm chart select NVFP4 artifacts for embedding caches on SM120 | open |
| `NVIDIA/nvidia-container-toolkit` | general WSL2 and Docker Desktop reports, among them 1616 "Support Docker Desktop" (open), 1739 (a library not found on WSL2, open), 1967 (CUDA initialisation fails after an upgrade, closed) | not specific to these NIMs |
| `NVIDIA-AI-Blueprints/rag`, `NVIDIA/GenerativeAIExamples`, `NVIDIA/nim-deploy` | — | 0 reports that name one of the retrieval NIMs together with an RTX 50 card, WSL2 or Docker Desktop |

A search that finds nothing says only that nothing was found with these words in these places.

## 5 · The reference for the tool check

Pyserini's reproduction file for BEIR, `pyserini/2cr/beir.yaml` (<https://github.com/castorini/pyserini>, commit `2aa191adb329`, 2026-09-30), condition `bm25-flat`, data set `scifact`: nDCG@10 0.6789, R@100 0.9253, R@1000 0.9767, with the command the file gives. The check and its result are in [`positive_control/`](positive_control/).

## 6 · Data sets

| Data set | Published by | Version used | Licence stated at the source |
|---|---|---|---|
| SciFact (BEIR packaging) | <https://github.com/allenai/scifact>; packaged by <https://github.com/beir-cellar/beir> | the BEIR zip, MD5 `5f7d1de60b170fc8027bb7898e2efca1` (the value in the BEIR README) | claims and annotations CC BY 4.0; abstracts ODC-By 1.0 |
| HotpotQA (BEIR packaging) | <https://hotpotqa.github.io/>; packaged by BEIR | the BEIR zip, MD5 `f412724f78b0d91183a0e86805e16114` | CC BY-SA 4.0 |
| MIRACL zh, ja | <https://github.com/project-miracl/miracl>; files from `miracl/miracl` (revision `5be20db9…9c00`) and `miracl/miracl-corpus` (revision `d921ec7e…8f0d`) on Hugging Face | dev split | Apache-2.0 |
| MIRACL, reduced task of MTEB (`MIRACLRetrievalHardNegatives`), zh and ja | <https://huggingface.co/datasets/mteb/MIRACLRetrievalHardNegatives>, the data set the MTEB task definition names | revision `d7d94fa4b946cec4a27c84653aa0cf6b33f74a3c`, dev split; six parquet files (corpus, queries, qrels per language) | CC BY-SA 4.0 (the data-set card and the MTEB task definition) |

No data set file is in this repository. The readers take the folder that holds the downloads as an argument.
