# BEIR HotpotQA, the whole corpus: every passage encoded with the embedding NIM, exact search, two controls, and the reranker on the results

*Working data, 2026-10-06 to 2026-10-07. One RTX 5090 (32 GB), Windows 11 with Docker Desktop (WSL2), graphics driver 610.88. Addendum [`../whole_corpus_quality/addendum_hotpotqa.json`](../whole_corpus_quality/addendum_hotpotqa.json), frozen 2026-10-06T17:07:15+0800 before the first container of this cell (SHA-256 `51ae6332f6472a534aff11e37fafed8f06477bbb760c916410586a8b1167ec90`). The method is the one of the two MIRACL corpora ([`../whole_corpus_quality/`](../whole_corpus_quality/README.md)); the programs are the same files.*

## The figures

| Corpus | Passages | Queries (test) | nDCG@10 | Recall@100 |
|---|---|---|---|---|
| **HotpotQA, whole (BEIR packaging)** | **5,233,329** | 7,405 | **0.80079** | **0.91567** |

- `nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2`, fp16, 2,048 dimensions; a passage is its title, one space, its text; queries with input type `query`, passages with `passage`; cosine, exact search (no index), one piece of 100,000 passages in memory at a time.
- Every judged passage of the test split is in the corpus (13,783 of 13,783); every query has results; no query counted as zero.
- **No public value for this model**: the public MTEB results of the open weights hold no HotpotQA file (read 2026-10-03, [`../../MODEL_CARD_CLAIMS.json`](../../MODEL_CARD_CLAIMS.json)), and the model card gives HotpotQA only inside a four-set average. This figure has no published partner to be checked against; its support is the two controls below and the controls of the method on MIRACL.

## The two controls, both set before the run

| Control | What was done | Result |
|---|---|---|
| **C_H** · ids and vectors belong together | 1,000 passages spread evenly over the corpus file (they fall in 53 of the 53 pieces) encoded again in a new container and compared with the stored row at each passage's position | the id at the position is the passage's id for 1,000 of 1,000; cosine at least 0.999999999 (required 0.999); failed 0 |
| **A_H** · the search and the metric computed a second way | a subset of 111,926 passages (the 13,783 with a judgement and the first 100,000 of the file; 1,857 are in both) searched by the program's restricted mode and by a separate program with one matrix product and a stable sort | nDCG@10 0.91199 · 0.91199, Recall@100 0.97698 · 0.97698: equal, and equal for 7,405 of 7,405 queries one by one |

- The two control programs were written after the addendum was frozen, as it says; their SHA-256 values were recorded before their first use ([`control_programs.json`](control_programs.json), 2026-10-07T01:21:26+0800). Their tests ([`../../tests/test_hotpotqa_controls.py`](../../tests/test_hotpotqa_controls.py)) include stores that are wrong in the ways each control is meant to catch (rows shifted by one, two pieces exchanged, another passage's vector under the right id).
- The subset's own figures (0.912 and 0.977) are higher than the whole corpus's: the subset has every judged passage and few others. They are a check of the programs, not a result.

## The encoding

5,233,329 passages in 53 pieces, in one night stretch: 2026-10-06T12:01:50+0000 to 2026-10-06T17:21:00+0000 (UTC, the container's clock), 18,865 s in the pieces. A full piece took 353 to 374 s (median 359.6), 277 passages per second over the pieces' seconds; 394,339,309 tokens reported, 75.4 per passage. Every vector finite, norms 0.99995 to 1.00004. The 7,405 queries were encoded once at the start. Not a throughput measurement: the timed figure of this NIM is in [`../whole_corpus_quality/`](../whole_corpus_quality/README.md), cell E. Checkpoints (counts, seconds, SHA-256 of every piece): [`full_corpus/beir-hotpotqa/checkpoints.jsonl`](full_corpus/beir-hotpotqa/checkpoints.jsonl). The vectors (41 GB) stay outside the repository.

Before the night a short check encoded the first 2,000 passages into a separate folder ([`check_before_the_night/`](check_before_the_night/)); it is not part of the corpus encoding.

## H-R · The reranker on the whole-corpus results

`llama-nemotron-rerank-1b-v2:1.10.0` (ready after 37.7 s, 4,551 MiB on the card once ready), on the 100 results per query of the search above, one call per query; the programs of cell D.

| Corpus | nDCG@10 before → after | Recall@100 before → after | Queries · pairs |
|---|---|---|---|
| HotpotQA, whole | 0.80079 → **0.86467** (+0.0639) | 0.91567 → 0.91567 | 7,405 · 740,500 |

| Pass | Calls | p50 ms | p90 ms | p99 ms | min · max ms | Pairs per second |
|---|---|---|---|---|---|---|
| 1 | 7,405 | 102.6 | 120.9 | 137.0 | 52.6 · 180.9 | 978.0 |
| 2 | 7,405 | 102.6 | 120.9 | 137.2 | 52.1 · 176.9 | 978.2 |

- One call with its 100 passages, one after the other on one kept connection, the client in a container on the NIM's Docker network; two passes over all queries, each behind the idle-card gate. The second pass's median is -0.0% of the first's.
- Recall@100 is equal before and after, as it must be: the 100 passages of a query are the same ones in another order.

## What was expected and what came out

| Pre-registered | Outcome |
|---|---|
| Encoding: 400 to 1,000 passages per second; finished in one night stretch | **no** for the rate: 277; finished in one stretch (5.2 h) |
| H: nDCG@10 between 0.66 and 0.82, Recall@100 between 0.85 and 0.97 | 0.80079 and 0.91567: inside both ranges |
| Both controls pass | yes |
| H-R: nDCG@10 rises by 0.02 to 0.08; Recall@100 equal | +0.0639; equal |

## What this does not show

- A comparison with another model: this is one model on one data set, with no published figure for it.
- Search speed with an index: the search is exact, on the host CPU, to give the quality figure.
- Anything about the other splits of the data set (train, dev).
