# Vol.4 · NeMo Retriever on one RTX 5090 — tools and the first measurements

**This volume is in progress.** It holds the tools the volume measures with, the check that shows the metric tool agrees with a published score, the sources that were read first, and the results of the first GPU session of 2026-10-04: [`results/first_batch/`](results/first_batch/README.md) (four embedding NIMs and two reranking NIMs on SciFact and on the reduced MIRACL task in zh and ja, with the open weights of one model as the reference arm). HotpotQA and the full MIRACL corpus have not been run. Nothing here has been published as an article.

## What is here

| Path | What it is |
|---|---|
| [`scripts/retrieval_datasets.py`](scripts/retrieval_datasets.py) | readers for BEIR SciFact, BEIR HotpotQA, MIRACL zh and ja, and the reduced MIRACL task of MTEB (zh and ja): one interface for corpus, queries and qrels |
| [`scripts/retrieval_metrics.py`](scripts/retrieval_metrics.py) | nDCG@10 and Recall@100 with `pytrec_eval`; every definition that decides a digit is written at the top of the file |
| [`scripts/nim_retrieval_clients.py`](scripts/nim_retrieval_clients.py) | the request bodies for the embedding and reranking NIMs, built from the OpenAPI files NVIDIA publishes |
| [`scripts/mock_nim_server.py`](scripts/mock_nim_server.py) | a stand-in server for the client tests |
| [`scripts/embed_cell.py`](scripts/embed_cell.py), [`scripts/score_run.py`](scripts/score_run.py), [`scripts/rerank_cell.py`](scripts/rerank_cell.py) | one embedding cell (the same program for the open weights and for a NIM), the search and the two metrics (the same for every cell), one reranking cell |
| [`scripts/run_step.py`](scripts/run_step.py), [`client/Dockerfile`](client/Dockerfile) | the steps of a session (gate, container start and stop, the client in a container on the NIM's Docker network) and the client image |
| [`scripts/method_cell.py`](scripts/method_cell.py), [`scripts/mteb_arbiter.py`](scripts/mteb_arbiter.py), [`scripts/first_batch_table.py`](scripts/first_batch_table.py) | the method cell, MTEB itself as the arbiter of the reference arm, the tables from the result files |
| [`results/first_batch/`](results/first_batch/README.md) | the first GPU session: pre-registration, run log, results |
| [`tests/`](tests/) | 40 unit tests (6 more run when the downloaded data sets are present) |
| [`positive_control/`](positive_control/) | the tool check: Pyserini's BM25 on SciFact, scored by our metric program |
| [`MTEB_REFERENCE.md`](MTEB_REFERENCE.md) | the model-level reference: two values from the public MTEB results, and every condition of them with the file it was read from |
| [`SOURCES.md`](SOURCES.md), [`MODEL_CARD_CLAIMS.json`](MODEL_CARD_CLAIMS.json) | what the documentation, the model cards, the MTEB results repository and the issue trackers say, with links and the date they were read |

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

## The model-level reference (run on 2026-10-04: ja reproduced, zh not)

The tool check cannot show that a model is asked the right way: the prefix of a query and of a passage, where an over-long input is cut, how the similarity is computed. For that this volume uses two values someone else published for a model whose weights are open: the MTEB results repository's nDCG@10 of `nvidia/Nemotron-3-Embed-1B-BF16` on the task `MIRACLRetrievalHardNegatives`, **0.64244 (zh) and 0.74194 (ja)**.

Two steps: first the open weights on that task with the conditions of the published result, to see whether this harness arrives at the two values; then the NIM of the same model on the same task. [`MTEB_REFERENCE.md`](MTEB_REFERENCE.md) lists the conditions, each with its source, and the ones that are recorded nowhere.

What came out ([`results/first_batch/README.md`](results/first_batch/README.md) §1): on ja this repository's path gives 0.74383, inside the 0.005 set beforehand. On zh it gives 0.66313, which is 0.021 above the published value; MTEB itself (source tag 2.14.3), run in the same environment on the same weights, gives 0.66251. The published zh value is therefore not reproduced by either, the reason is not known, and nothing was tuned to make it fit. The NIM of the same model agrees with the open weights to 0.0011 (zh) and 0.0001 (ja).

On the other data sets of this volume (SciFact, HotpotQA, the full MIRACL corpus in zh and ja) no published per-data-set score of these models exists; results there are reported as measured, without a claim of having reproduced an official score.

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

- **The metric tests** work each small case out by hand in a comment and compare the digits. A mutation check was run against the tests: 22 single changes to the code (a cut-off, the averaging rule, the tie order, a dropped zero judgement, an unsorted answer, the reduced MIRACL task served from the full MIRACL corpus, …), each in a copy; the tests fail for all 22. The first run of that check found one test that passed with its rule broken (it claimed to check that an over-large corpus is refused without being read to the end, and did not count what was read); the test was corrected.
- **The client tests run against a stand-in server.** The stand-in was written from the same published OpenAPI files as the client, so it checks the server we imagine. Which fields a real NIM needs, how it orders its answer, what it does with an over-long input and what an error looks like are settled by the first start of a real NIM, not by these tests.

## Data sets

Read from a folder outside the repository (`--datasets DIR` or `VOL4_DATASETS`), in the layout their publishers ship. Sources, versions and licences are in [`SOURCES.md`](SOURCES.md) §6. The counts of the downloaded files match the published ones: SciFact 5,183 passages and 300 test queries; HotpotQA 5,233,329 and 7,405; MIRACL zh 4,934,368 and 393 dev queries; MIRACL ja 6,953,614 and 860.

The reduced MIRACL task (`miracl-hn-zh`, `miracl-hn-ja`) has the same queries and judgements as MIRACL dev over a much smaller corpus: 81,309 passages (zh) and 185,319 (ja). Because nothing but the size of the corpus tells the two apart, the reader carries the published counts and `check_published_counts` refuses a corpus of another size:

```bash
python vol4-retriever/scripts/retrieval_datasets.py --datasets /path/to/datasets --name miracl-hn-zh --check-published
```

## What the model cards do not give

No model card reports a per-data-set score on the four data sets above: the cards give averages over groups of data sets ([`SOURCES.md`](SOURCES.md) §2). A check of the kind "our harness reproduces the card's number for this model on this data set" is therefore not available from the cards. The public MTEB results repository has no result on those four data sets either, and no folder at all for four of the six models; what it does have is the reduced MIRACL task for one model, which is why that task was added ([`SOURCES.md`](SOURCES.md) §2, [`MODEL_CARD_CLAIMS.json`](MODEL_CARD_CLAIMS.json) → `mteb_results`).
