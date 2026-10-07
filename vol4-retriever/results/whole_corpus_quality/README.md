# Vol.4 · Retrieval quality on the whole MIRACL zh and ja corpora, by exact search

*Working data; nothing here has been published as an article. Pre-registration: [`prediction_whole_corpus.json`](prediction_whole_corpus.json), frozen 2026-10-05 20:41:19 (+0800), SHA-256 `129e21e6…bd7fa`, before the first cell. It supplements the pre-registrations of the two GPU sessions ([`../first_batch/`](../first_batch/README.md), [`../second_batch/`](../second_batch/README.md)). Run log: [`events.jsonl`](events.jsonl). Every command ran under `timeout`; none reached its limit.*

**State on 2026-10-06:** all five cells are done. A, C and B need no card and ran on 2026-10-05 (20:41 to 20:49). D and E ran on the card on 2026-10-06, 04:32 to 05:00, with graphics driver 610.88 (the earlier sessions of this volume recorded 591.86); 20 gates, all passed, the closing gate included.

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

## D · Reranking the whole-corpus results

`llama-nemotron-rerank-1b-v2:1.10.0` (the image selected a TensorRT fp8 profile on this card, as in the first session; ready after 54.6 s, 3.4 GiB added to the card). For every query the 100 results of cell B, one call per query; the program and the scoring are the first session's (`rerank_cell.py`, `score_run.py`).

| Corpus | nDCG@10 before → after | Recall@100 before → after | Queries · pairs |
|---|---|---|---|
| MIRACL zh, whole | 0.64921 → **0.68296** (+0.0338) | 0.96419 → 0.96419 | 393 · 39,300 |
| MIRACL ja, whole | 0.74122 → **0.77134** (+0.0301) | 0.98422 → 0.98422 | 860 · 86,000 |

- Recall@100 is equal before and after to the last stored digit, as it must be: the 100 passages of a query are the same ones in another order.
- On the reduced corpora the same reranker had added 0.024 (zh) and 0.028 (ja) in the first session ([`../first_batch/table.md`](../first_batch/table.md)).

**What one reranking call costs** ([`../../scripts/rerank_latency.py`](../../scripts/rerank_latency.py)): every query of the run, one call with its 100 passages, one after the other on one kept connection, the client in a container on the NIM's Docker network; two passes over all queries, each behind the gate. Duration measured in the client; percentiles by nearest rank.

| Corpus | Pass | Calls | p50 ms | p90 ms | p99 ms | min · max ms | Pairs per second |
|---|---|---|---|---|---|---|---|
| MIRACL zh | 1 | 393 | 143.1 | 185.8 | 242.0 | 77.9 · 367.2 | 679.4 |
| MIRACL zh | 2 | 393 | 143.0 | 188.1 | 238.5 | 76.0 · 357.9 | 677.7 |
| MIRACL ja | 1 | 860 | 154.1 | 194.4 | 251.9 | 87.4 · 339.7 | 638.5 |
| MIRACL ja | 2 | 860 | 154.1 | 195.3 | 254.3 | 86.8 · 342.1 | 636.0 |

- The two passes of a corpus agree within 0.1% at the median and within 2% at p99. The duration of every call is in the files (numbers only).
- One stream of calls: nothing here is about concurrent calls. Files: [`rerank_llama-nemotron-rerank-1b-v2/`](rerank_llama-nemotron-rerank-1b-v2/).

## Second reranker (500m) · on the same whole-corpus results

Addendum [`addendum_second_reranker.json`](addendum_second_reranker.json), frozen 2026-10-06T14:50:41+0800 before the first container of this cell; in that frozen file the cell is keyed `cell_D2` (SHA-256 `3feb764bbb83785c37782c090c1c16cc3b697bc62f0c8a4ad3de1170ea62d9a6`). `llama-nemotron-rerank-500m-v2:1.10.0`, started as in the first session (ready after 28.2 s, 3,525 MiB on the card once ready), on the 100 results per query of cell B, with cell D's programs and limits. Each reranker's own values, side by side:

| Corpus | nDCG@10 before | after · 500m reranker | after · 1b reranker (cell D) | Recall@100 before → after (500m) |
|---|---|---|---|---|
| MIRACL zh, whole | 0.64921 | **0.66932** (+0.0201) | 0.68296 (+0.0338) | 0.96419 → 0.96419 |
| MIRACL ja, whole | 0.74122 | **0.75233** (+0.0111) | 0.77134 (+0.0301) | 0.98422 → 0.98422 |

| Corpus | Pass | Calls | 500m: p50 ms | p90 ms | p99 ms | Pairs per second | 1b (cell D): p50 ms · pairs per second |
|---|---|---|---|---|---|---|---|
| MIRACL zh | 1 | 393 | 84.5 | 111.5 | 139.7 | 1138.9 | 143.1 · 679.4 |
| MIRACL zh | 2 | 393 | 85.2 | 110.5 | 142.4 | 1136.1 | 143.0 · 677.7 |
| MIRACL ja | 1 | 860 | 91.3 | 115.6 | 147.5 | 1073.9 | 154.1 · 638.5 |
| MIRACL ja | 2 | 860 | 91.6 | 116.0 | 147.5 | 1072.8 | 154.1 · 636.0 |

- Recall@100 is equal before and after, as it must be.
- The 500m reranker adds 60% (zh) and 37% (ja) of what the 1b reranker adds, and its call takes 59% and 59% of the 1b reranker's median.
- Measured 2026-10-06 in the afternoon (cell D: the same day, early morning), graphics driver 610.88, each NIM alone on the card. Files: [`rerank_llama-nemotron-rerank-500m-v2/`](rerank_llama-nemotron-rerank-500m-v2/).

**The reference arm's timing on the reduced MIRACL ja corpus** (the same addendum). The first session had no timed passes for this arm on ja: at 64 passages per batch it filled the card's memory. At 16 per batch, three passes over the first 4,096 passages after one discarded pass: **290.6 passages per second** (median). The batch differs from the NIM cells (64 per request) and from this arm's zh figure (64 per batch), so this figure stands by itself. File: [`reference_bf16_batch16/miracl-hn-ja/throughput.json`](reference_bf16_batch16/miracl-hn-ja/throughput.json).

## E · Four embedding NIMs timed from a container, from the host, and from a container again

The sample and request of every timed cell of this volume: the first 4,096 passages of the reduced MIRACL zh corpus, 64 per request, one kept connection, one discarded pass over the first 4 requests, three timed passes; passages per second, median of the three (all three in the files). Per NIM three runs, each behind the gate: the client in a container on the NIM's Docker network (`embed_cell.py throughput`, the program of the first session's cells), the client on the host through the published port (`method_cell.py --where host`), the container again.

| NIM (how started) | Container, first | Host | Container, second | Host against the mean of the two container runs | First session, container (2026-10-04) |
|---|---|---|---|---|---|
| `nemotron-3-embed-1b:2.2.2` (fp16) | 237.6 | 227.4 | 233.0 | −3.4% | 243.7 |
| `llama-nemotron-embed-1b-v2:1.13.0` (fp8, selected by the image) | 495.0 | 445.7 | 492.6 | −9.7% | 485.6 |
| `llama-nemotron-embed-300m-v2:1.13.0` (selected by the image) | 798.6 | 717.1 | 848.3 | −12.9% | 796.0 |
| `llama-nemotron-embed-vl-1b-v2:2.3.0` | 278.7 | 267.1 | 277.7 | −4.0% | 279.7 |

- **The host path is slower for every NIM, and by more the faster the NIM is**: 3% to 4% for the two that encode about 230 to 280 passages per second, 10% at about 490, 13% at about 800. A request of 64 passages returns 64 vectors as text; what the path through the published port adds is a larger share of a shorter request.
- **The second container run is there to tell the place of the client from a drift.** Three NIMs repeat their first container run within 2%; the 300m encoder came out 6.2% higher the second time (its passes: 798.6 · 845.1 · 794.7, then 820.3 · 848.3 · 849.0), so for that one the 12.9% carries a spread of that size.
- **Against the first session**, two days earlier and with another driver version, the first container run of each NIM is within 2.5%.
- The work order asked for these cells "beside the host-side values of the first session". The first session's cells were measured from a container already; a host-side value existed for one NIM only (the method cell: 214.9 against 241.1). Hence this design, set in the pre-registration.
- Files: [`timing_container_and_host/`](timing_container_and_host/) (`container_1.json`, `host.json`, `container_2.json` per NIM; the host file holds every request's duration).

## What was expected and what came out

| Pre-registered | Outcome |
|---|---|
| A: equal to the first session's values at five decimals, in all four runs | equal without rounding, per-query values identical |
| C: every id found; nDCG@10 within 0.001 and Recall@100 within 0.002 | every id found; both equal |
| B, zh: nDCG@10 between 0.630 and 0.662, Recall@100 between 0.945 and 0.988 | 0.64921 and 0.96419: inside both ranges |
| B, ja: nDCG@10 between 0.710 and 0.744, Recall@100 between 0.955 and 0.992 | 0.74122 and 0.98422: inside both ranges |
| B: not above the reduced-corpus value | below it on both languages |
| Seconds: about 1.5 minutes for zh and 2.5 for ja | 90.1 s and 210.8 s: ja took longer than estimated (the products for 860 queries, not the reading, were the larger part) |
| D: nDCG@10 rises by 0.015 to 0.04 on both languages; Recall@100 equal | +0.0338 and +0.0301; equal |
| D: a call's median 130 to 190 ms (zh) and 140 to 200 ms (ja); p99 below 600 ms; the second pass's median within 5% of the first | 143 and 154 ms; 242 and 254 ms at most; within 0.1% |
| E: each NIM's first container run within 6% of its first-session value | yes: −2.5% · +1.9% · +0.3% · −0.4% |
| E: the host slower for every NIM | yes |
| E: by 5% to 15% for the two 1b text encoders and the vl encoder | **two of three no**: 3.4% and 4.0% (below the range), 9.7% (inside) |
| E: by 15% to 30% for the 300m encoder | **no**: 12.9% (the largest of the four, as expected; below the range) |
| E: the two container runs within 3% of each other | **one of four no**: the 300m encoder, 6.2% |

| Second reranker (500m), addendum: nDCG@10 rises by 0.005 to 0.02 on both languages; Recall@100 equal | **zh no**: +0.0201 (just above the range); ja +0.0111; equal |
| Second reranker (500m): a call's median 75 to 110 ms (zh) and 80 to 115 ms (ja); p99 below 400 ms; the second pass within 5% of the first | 84.5 and 91.3 ms; p99 at most 148 ms; within 0.9% |
| Reference arm, ja, batch 16: completes; 200 to 350 passages per second | 290.6 |

## What this does not show

- Anything about a search service or an index: the search here is a matrix product on the host CPU, chosen so that the search is not a second variable beside the encoder.
- Quality of any other encoder on the whole corpora: one encoder's vectors exist.
- The whole-corpus value of the open weights: the reference arm was run on the reduced corpora only.
- Reranking under concurrent calls, or of more than 100 results per query.
- Why the host path costs what it costs: the two places were timed, the path between them was not taken apart.
- That passages never judged are not relevant: the judgements cover 3,786 (zh) and 8,066 (ja) passages of millions. A passage of the whole corpus that answers a query and was never judged counts against the encoder here, as in every figure reported on MIRACL.
