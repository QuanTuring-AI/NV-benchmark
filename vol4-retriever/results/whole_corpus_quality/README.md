# Vol.4 · Retrieval quality on the whole MIRACL zh and ja corpora, by exact search

*Working data; nothing here has been published as an article. Pre-registration: [`prediction_whole_corpus.json`](prediction_whole_corpus.json), frozen 2026-10-05 20:41:19 (+0800), SHA-256 `129e21e6…bd7fa`, before the first cell. It supplements the pre-registrations of the two GPU sessions ([`../first_batch/`](../first_batch/README.md), [`../second_batch/`](../second_batch/README.md)). Run log: [`events.jsonl`](events.jsonl). Every command ran under `timeout`; none reached its limit.*

**State on 2026-10-05:** the three cells that need no card are done (A, C, B below). The two cells that need the card — reranking these results, and timing four embedding NIMs from two places — are pre-registered and have not run.

## The figures

Encoder: `nemotron-3-embed-1b:2.2.2` (NIM, pinned to fp16), vectors of size 2,048, encoded in the second session ([`../second_batch/README.md`](../second_batch/README.md), section 3). Queries: the dev split of MIRACL. Search: cosine of every query with every passage, no index; 100 results per query. Metric program: the one of every other cell of this volume (`pytrec_eval`).

| Corpus | Passages | Queries | nDCG@10 | Recall@100 | Wall time of the search on the host CPU |
|---|---|---|---|---|---|
| MIRACL zh, reduced (the first session's value) | 81,309 | 393 | 0.66199 | 0.98789 | — |
| **MIRACL zh, whole** | **4,934,368** | 393 | **0.64921** | **0.96419** | 90.1 s |
| MIRACL ja, reduced (the first session's value) | 185,319 | 860 | 0.74371 | 0.99163 | — |
| **MIRACL ja, whole** | **6,953,614** | 860 | **0.74122** | **0.98422** | 210.8 s |

- **The reduced corpus is the condition of the published model-card figure; the whole corpus is the condition of a deployment.** From one to the other nDCG@10 falls by 0.0128 (zh) and 0.0025 (ja), Recall@100 by 0.0237 and 0.0074.
- The two rows of a language use the same queries and the same judgements: the reduced task has MIRACL dev's query ids, query texts and judgements (zh 3,928 judgements, 994 relevant; ja 8,354 and 1,790), and every relevant passage is in the reduced corpus. With the same vectors, more passages can only push a relevant passage down; a whole-corpus value above the reduced one would have been a fault, and the pre-registration said so beforehand.
- Every judged passage id was found among the ids of the whole corpus (zh 3,786, ja 8,066).
- **The wall time is not a speed of the NIM or of any search service.** It is reading 38.6 GB and 54.4 GB of vectors from an NVMe disk, comparing every file with its recorded SHA-256, and multiplying on the host CPU (numpy; a Core i7-14700), one piece of 100,000 passages in memory at a time.
- Files: [`whole_corpus/miracl-zh/`](whole_corpus/miracl-zh/), [`whole_corpus/miracl-ja/`](whole_corpus/miracl-ja/) — `score.json` (the two metrics with their per-query values) and `search_progress.jsonl` (one line per piece). The rankings list passage ids of a data set and are kept outside the repository.

## Why these figures can be trusted: two checks, both set beforehand

**A · The search program gives the results that exist.** The program is new ([`../../scripts/search_whole_corpus.py`](../../scripts/search_whole_corpus.py)). It was run on the reduced corpora with the first session's stored vectors, cut into pieces of 10,000 rows so that the merging across pieces runs.

| Vectors | Data set | nDCG@10: this program · first session | Recall@100: this program · first session | Per-query values |
|---|---|---|---|---|
| reference arm (open weights) | miracl-hn-zh | 0.6631311979964787 · 0.6631311979964787 | 0.9878892523930691 · 0.9878892523930691 | identical |
| the NIM | miracl-hn-zh | 0.6619852203579513 · 0.6619852203579513 | 0.9878892523930691 · 0.9878892523930691 | identical |
| reference arm (open weights) | miracl-hn-ja | 0.743834393831563 · 0.743834393831563 | 0.9920172656800562 · 0.9920172656800562 | identical |
| the NIM | miracl-hn-ja | 0.7437135090703177 · 0.7437135090703177 | 0.9916296687808315 · 0.9916296687808315 | identical |

The first session kept 1,000 results per query and this program keeps 100; neither metric looks beyond 100. Files: [`check_of_the_search_program/`](check_of_the_search_program/).

**C · Ids and vectors of the whole corpus belong together.** The stored vectors of the whole corpus were searched with only the passages of the reduced corpus taking part. That is the reduced task again, computed from the whole-corpus files; it fails if ids and vectors of a piece are shifted against each other, if a piece is missing or doubled, or if the stored query vectors are not those of the queries.

| Corpus | Ids of the reduced corpus found in the whole corpus | nDCG@10 · the NIM on the reduced corpus | Recall@100 · the same |
|---|---|---|---|
| MIRACL zh | 81,309 of 81,309 | 0.6619852203579513 · 0.6619852203579513 | 0.9878892523930691 · 0.9878892523930691 |
| MIRACL ja | 185,319 of 185,319 | 0.7437135090703177 · 0.7437135090703177 | 0.9916296687808315 · 0.9916296687808315 |

The limit set beforehand was 0.001 for nDCG@10; the values came out equal. Files: [`ids_and_vectors_belong_together/`](ids_and_vectors_belong_together/).

Before the pre-registration was frozen the program had two checks that are not cells ([`before_the_run/`](before_the_run/)): on `beir-scifact` it gave the first session's score with identical per-query values, and on the first two pieces of MIRACL zh it was stopped after confirming the calling form and the hash comparison (no ranking, no metric). Its tests are in [`../../tests/test_search_whole_corpus.py`](../../tests/test_search_whole_corpus.py); each rule they guard was broken once in a copy of the program, and the tests failed each time.

## What was expected and what came out

| Pre-registered | Outcome |
|---|---|
| A: equal to the first session's values at five decimals, in all four runs | equal without rounding, per-query values identical |
| C: every id found; nDCG@10 within 0.001 and Recall@100 within 0.002 | every id found; both equal |
| B, zh: nDCG@10 between 0.630 and 0.662, Recall@100 between 0.945 and 0.988 | 0.64921 and 0.96419: inside both ranges |
| B, ja: nDCG@10 between 0.710 and 0.744, Recall@100 between 0.955 and 0.992 | 0.74122 and 0.98422: inside both ranges |
| B: not above the reduced-corpus value | below it on both languages |
| Seconds: about 1.5 minutes for zh and 2.5 for ja | 90.1 s and 210.8 s: ja took longer than estimated (the products for 860 queries, not the reading, were the larger part) |

## What this does not show

- Anything about a search service or an index: the search here is a matrix product on the host CPU, chosen so that the search is not a second variable beside the encoder.
- Quality of any other encoder on the whole corpora: one encoder's vectors exist.
- The whole-corpus value of the open weights: the reference arm was run on the reduced corpora only.
- The reranker on these results and the timing from two places: pre-registered (cells D and E), not run.
- That passages never judged are not relevant: the judgements cover 3,786 (zh) and 8,066 (ja) passages of millions. A passage of the whole corpus that answers a query and was never judged counts against the encoder here, as in every figure reported on MIRACL.
