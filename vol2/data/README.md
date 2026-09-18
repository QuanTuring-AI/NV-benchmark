# Vol.2 data

Vol.2 reuses Vol.1's public question sets. They are **not copied** here:

| File | Used by | SHA-256 |
|---|---|---|
| [`../../benchmark/questions.json`](../../benchmark/questions.json) | E7 arms, C | `262f2339d55ec6b855f7b0180704bd225fdbc561ea37f902b99e1ab405add1f9` |
| [`../../benchmark/e3_questions.json`](../../benchmark/e3_questions.json) | E9 | `5d7eeeaa9408977e28366e7b31a6f01905695a0c8ce10a6c314fa40de4a1c3ea` |

E8 and S6 use **SciFact**, a public dataset. It is not stored in this repo:

- E8 (`scripts/bench_reranker.py`) downloads the BEIR version from Hugging Face (`mteb/scifact`) at run time.
- S6 (`scripts/scan_self_check_facts.py`) expects the original SciFact release (`corpus.jsonl`, `claims_train.jsonl`, `claims_dev.jsonl`) under `data/scifact/data/`, plus a `data/scifact/scifact.manifest.json`. These are not included.
