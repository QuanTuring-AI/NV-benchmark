# Vol.4 · NeMo Retriever on one RTX 5090 — tools, before any measurement

**Nothing in this folder has met a GPU yet.** It holds the tools the volume will measure with, the check that shows the metric tool agrees with a published score, and the sources that were read first. No embedding or reranking NIM has been started; there is no result about them here.

## What is here

| Path | What it is |
|---|---|
| [`scripts/retrieval_datasets.py`](scripts/retrieval_datasets.py) | readers for BEIR SciFact, BEIR HotpotQA, MIRACL zh and ja: one interface for corpus, queries and qrels |
| [`scripts/retrieval_metrics.py`](scripts/retrieval_metrics.py) | nDCG@10 and Recall@100 with `pytrec_eval`; every definition that decides a digit is written at the top of the file |
| [`scripts/nim_retrieval_clients.py`](scripts/nim_retrieval_clients.py) | the request bodies for the embedding and reranking NIMs, built from the OpenAPI files NVIDIA publishes |
| [`scripts/mock_nim_server.py`](scripts/mock_nim_server.py) | a stand-in server for the client tests |
| [`tests/`](tests/) | 36 unit tests (4 more run when the downloaded data sets are present) |
| [`positive_control/`](positive_control/) | the tool check: Pyserini's BM25 on SciFact, scored by our metric program |
| [`SOURCES.md`](SOURCES.md), [`MODEL_CARD_CLAIMS.json`](MODEL_CARD_CLAIMS.json) | what the documentation, the model cards and the issue trackers say, with links and the date they were read |

## The tool check

Before the metric program scores anything of ours, it has to give the published number on a ranking somebody else made.

| | nDCG@10 | Recall@100 |
|---|---|---|
| Published by Pyserini for BM25 on BEIR SciFact (`pyserini/2cr/beir.yaml`, `bm25-flat`) | 0.6789 | 0.9253 |
| Pyserini's own evaluation of the ranking we produced with its command | 0.6789 | 0.9253 |
| **Our program on that ranking, against the qrels of the BEIR download** | **0.6789** | **0.9253** |
| Control: the qrels given to the wrong queries | 0.0067 | 0.0250 |
| Control: half of the queries removed from the ranking | 0.3401 | 0.4627 |

- The ranking: 300 queries, 294,041 lines, SHA-256 `04cbcf1249e848ea915156359b49b56f6ccce781b01f3e89540eaf3b04859e19`; two runs gave the same bytes. It lists passage ids of a data set and is kept outside the repository.
- How it was made: [`positive_control/run_bm25_scifact.sh`](positive_control/run_bm25_scifact.sh) in the CPU-only image of [`positive_control/Dockerfile`](positive_control/Dockerfile) (Pyserini 2.4.0, Java 21, prebuilt index `beir-v1.0.0-scifact.flat`). No GPU.
- The record with every value and file hash: [`positive_control/bm25_scifact.json`](positive_control/bm25_scifact.json), written by [`positive_control/check_bm25_scifact.py`](positive_control/check_bm25_scifact.py).

This checks the metric program and the qrels reader. It says nothing about a NIM.

## Run the tests

```bash
python -m venv .venv && . .venv/bin/activate        # Python 3.11
pip install -r vol4-retriever/requirements.txt
python -m pytest vol4-retriever/tests -q
# with the data sets downloaded to a folder of your own (they are not in this repository):
VOL4_DATASETS=/path/to/datasets python -m pytest vol4-retriever/tests -q
```

`pytrec_eval` is installed from the distribution `pytrec-eval-terrier` (0.5.10), a build of the same library with ready-made wheels; the original distribution ships source only and needs a C++ compiler.

## What the tests can and cannot show

- **The metric tests** work each small case out by hand in a comment and compare the digits. A mutation check was run against them: fifteen single changes to the code (a cut-off, the averaging rule, the tie order, a dropped zero judgement, an unsorted answer, …), each in a copy; the tests fail for all fifteen.
- **The client tests run against a stand-in server.** The stand-in was written from the same published OpenAPI files as the client, so it checks the server we imagine. Which fields a real NIM needs, how it orders its answer, what it does with an over-long input and what an error looks like are settled by the first start of a real NIM, not by these tests.

## Data sets

Read from a folder outside the repository (`--datasets DIR` or `VOL4_DATASETS`), in the layout their publishers ship. Sources, versions and licences are in [`SOURCES.md`](SOURCES.md) §6. The counts of the downloaded files match the published ones: SciFact 5,183 passages and 300 test queries; HotpotQA 5,233,329 and 7,405; MIRACL zh 4,934,368 and 393 dev queries; MIRACL ja 6,953,614 and 860.

## What the model cards do not give

No model card reports a per-data-set score on the four data sets above: the cards give averages over groups of data sets ([`SOURCES.md`](SOURCES.md) §2). A check of the kind "our harness reproduces the card's number for this model on this data set" is therefore not available from the cards.
