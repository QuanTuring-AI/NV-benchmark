# Vol.4 · the whole-corpus vectors as 16-bit floats, with the 32-bit files still provable

[← Vol.4 README](../../README.md) · program: [`../../scripts/fp16_store.py`](../../scripts/fp16_store.py) · why 16 bits lose nothing here: [`../storage_precision/`](../storage_precision/)

The vectors of the three whole corpora were written as 32-bit `.npy` pieces; the checkpoint file of each corpus, in this repository, records the SHA-256 of every piece. The vectors themselves are not in the repository. This folder is the record of a 16-bit copy of them, made on the machine that holds them, and of three proofs per corpus:

1. **per piece, at the conversion:** the 32-bit piece has the recorded SHA-256; every value comes back unchanged from 16 bits; the 16-bit file, read back from disk, gives the same values; and the 32-bit file rebuilt from it in memory has the recorded SHA-256 ([`pieces.jsonl`](miracl-zh/pieces.jsonl) per corpus: both SHA-256 values, rows and sizes of every piece);
2. **from the copy alone:** the same rebuilt-file proof for every piece without reading the 32-bit files (`verify.json`);
3. **by search:** the exact search over the 16-bit copy gives, for every query, the same 100 passages in the same order as the existing ranking of the 32-bit files, and the same nDCG@10 and Recall@100 (`search.json`).

| Corpus | Pieces | Passages | 32-bit files, GB | 16-bit files, GB | Every value equal, read back from disk | Every rebuilt file has the recorded SHA-256 | Queries with the same 100 passages in the same order | nDCG@10 · Recall@100 (both stores) |
|---|---|---|---|---|---|---|---|---|
| MIRACL zh, whole corpus ([checkpoints](../second_batch/full_corpus/miracl-zh/checkpoints.jsonl)) | 50 | 4,934,368 | 40.42 | 20.21 | 50 of 50 | 50 of 50 | 393 of 393 | 0.64921 · 0.96419 |
| MIRACL ja, whole corpus ([checkpoints](../second_batch/full_corpus/miracl-ja/checkpoints.jsonl)) | 71 | 6,953,614 | 56.96 | 28.48 | 71 of 71 | 71 of 71 | 860 of 860 | 0.74122 · 0.98422 |
| BEIR HotpotQA, whole corpus ([checkpoints](../hotpotqa_whole_corpus/full_corpus/beir-hotpotqa/checkpoints.jsonl)) | 53 | 5,233,329 | 42.87 | 21.44 | 53 of 53 | 53 of 53 | 7,405 of 7,405 | 0.80079 · 0.91567 |

Together 140.26 GB as 32-bit files and 70.13 GB as 16-bit files. Free space on the drive before and after: 296.3 and 230.4 GiB ([`space_before.json`](space_before.json), [`space_after.json`](space_after.json)). The 32-bit files were only read; nothing was deleted.

## What this does and does not show

- For this encoder as it was run here, a 16-bit store is not an approximation: the numbers it returned are 16-bit floats, and the search result is the same, not close.
- Whoever holds only the 16-bit copy can still check every SHA-256 the published records carry, by rebuilding the 32-bit file in memory (`fp16_store.py verify`). That depends on `numpy.save` writing the same header as when the pieces were made (numpy version in each list).
- It is not a property of 16-bit floats in general. Another encoder, or this one at another precision setting, has to be measured again.
- The 8-bit store of `../storage_precision/` is a different thing: there the rankings change.
