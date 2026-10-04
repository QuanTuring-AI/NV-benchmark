## Embedding cells: nDCG@10 · Recall@100 · passages per second (median of three timed passes)

| Encoder | beir-scifact | miracl-hn-zh | miracl-hn-ja |
|---|---|---|---|
| `nim_llama-nemotron-embed-1b-v2_auto` | 0.77537 · 0.96333 · 259.1 (258.4–259.8) | 0.64458 · 0.98326 · 485.6 (474.7–495.2) | 0.71579 · 0.98450 · 428.8 (428.5–436.3) |
| `nim_llama-nemotron-embed-300m-v2_auto` | 0.71259 · 0.95000 · 484.8 (478.9–500.2) | 0.59313 · 0.97396 · 796.0 (755.8–836.8) | 0.67644 · 0.96605 · 742.9 (727.5–743.4) |
| `nim_llama-nemotron-embed-vl-1b-v2_auto` | 0.76704 · 0.96667 · 175.3 (175.2–175.4) | 0.64837 · 0.98127 · 279.7 (279.5–281.0) | 0.71875 · 0.98708 · 249.7 (248.7–250.5) |
| `nim_nemotron-3-embed-1b_auto` | 0.75188 · 0.95667 · 154.3 (153.8–154.4) | 0.66199 · 0.98789 · 243.7 (243.0–249.1) | 0.74371 · 0.99163 · 226.0 (226.0–227.0) |
| `reference_bf16` | not run | 0.66313 · 0.98789 · 368.7 (362.5–378.9) | 0.74383 · 0.99202 · no timed passes |

Published values for the open weights of `nemotron-3-embed-1b` (MTEB results, nDCG@10): miracl-hn-zh 0.64244, miracl-hn-ja 0.74194.

## Containers

| Tag | Image | Seconds to ready | Card memory at ready, MiB (before the start) | What its start-up log names | Outcome |
|---|---|---|---|---|---|
| `n3embed_auto` | `nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2` | 52.9 | 5005 (1072) | 7 kernel files for `sm120` in the image | ready |
| `n3embed_fp16` | `nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2` | 26.9 | 5005 (1072) | nothing about a profile or precision | ready |
| `embed1bv2` | `nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2:1.13.0` | 48.1 | 4474 (982) | profile `ee7364e4eba4…`, engine folder `cc_12_0-fp8-b04c9dd3`, engine 1542 MiB | ready |
| `embed300m` | `nvcr.io/nim/nvidia/llama-nemotron-embed-300m-v2:1.13.0` | 33.5 | 3654 (985) | profile `ee7364e4eba4…`, engine folder `rtx5090x1-trt-fp8-85n4shahyq`, engine 925 MiB | ready |
| `embedvl` | `nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:2.3.0` | 63.1 | 6621 (987) | 7 kernel files for `sm120` in the image | ready |
| `rerank1b` | `nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0` | 63.3 | 4497 (1005) | profile `c10e0d36e760…`, engine folder `rtx6000-blackwell-svx1-trt-fp8-kdrhsvesdq`, engine 1542 MiB | ready |
| `rerank500m` | `nvcr.io/nim/nvidia/llama-nemotron-rerank-500m-v2:1.10.0` | 47.7 | 4025 (1008) | profile `c10e0d36e760…`, engine folder `rtx6000-blackwell-svx1-trt-fp8-c8-5o8nwxg`, engine 1068 MiB | ready |
| `ocr` | `nvcr.io/nim/nvidia/nemotron-ocr-v1:1.3.0` | 73.7 | 13246 (1005) | profile `2e1ac3d2b2e8…`, engine 101 MiB | ready |
| `ocr_pool0` | `nvcr.io/nim/nvidia/nemotron-ocr-v1:1.3.0` | 422.3 | 1005 (1005) | profile `2e1ac3d2b2e8…`, engine folder `rtx6000-blackwell-svx1-trt-fp16-yravuwlokw` | not_ready: no ready answer within the wait |

## Reranking the first 100 results of `nim_nemotron-3-embed-1b_auto`: nDCG@10 before → after · pairs per second

| Reranker | beir-scifact | miracl-hn-zh | miracl-hn-ja |
|---|---|---|---|
| `rerank_llama-nemotron-rerank-1b-v2_auto` | 0.75188 → 0.79422 · 340.6 (339.5–341.0) | 0.66199 → 0.68592 · 655.5 (654.4–656.9) | 0.74371 → 0.77157 · 611.1 (609.8–611.9) |
| `rerank_llama-nemotron-rerank-500m-v2_auto` | 0.75188 → 0.79420 · 600.2 (597.0–602.2) | 0.66199 → 0.67344 · 1120.3 (1110.4–1124.8) | 0.74371 → 0.75220 · 1039.6 (1032.9–1048.1) |

## Method cell: the same requests to the same NIM from two places

| Client | Connection | Passages per request | Passages per second | Request ms p10 / p50 / p90 / p99 | Requests more than 10 ms above p10 |
|---|---|---|---|---|---|
| container | one kept connection | 1 | 220.0 | 3.4 / 4.0 / 5.77 / 7.41 | 0 of 300 |
| container | one kept connection | 64 | 241.1 | 231.07 / 252.55 / 283.74 / 308.65 | 136 of 192 |
| container | a new connection per request | 1 | 176.2 | 4.31 / 5.05 / 6.69 / 8.45 | 0 of 300 |
| container | a new connection per request | 64 | 239.9 | 232.87 / 253.33 / 287.5 / 325.87 | 134 of 192 |
| host | one kept connection | 1 | 171.3 | 4.32 / 5.33 / 7.25 / 9.71 | 0 of 300 |
| host | one kept connection | 64 | 214.9 | 243.37 / 267.94 / 292.93 / 359.86 | 144 of 192 |
| host | a new connection per request | 1 | 70.1 | 5.24 / 7.48 / 31.23 / 42.11 | 96 of 300 |
| host | a new connection per request | 64 | 208.9 | 251.83 / 276.07 / 306.31 / 342.14 | 146 of 192 |

## Gates

34 gates, 34 passed on utilization and power; 0 flagged for desktop memory; launcher processes seen at 0 gates; other containers at 0 gates. Desktop memory at the first gate: 1003 MiB; range over the gates without a container of the session: 312–1072 MiB.
