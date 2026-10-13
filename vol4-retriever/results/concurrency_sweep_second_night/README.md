# Vol.4 · the concurrency sweep, second night (2026-10-13)

[← the first night](../concurrency_sweep/README.md) · supplementary pre-registration: [`prediction_second_night.json`](prediction_second_night.json), frozen 2026-10-13T02:37:59+0800, before the first serving container of the night · run log: [`events.jsonl`](events.jsonl)

**What was run.** Three things the first night left open: the embedding NIM its calibration rule had stopped, now swept in full; the other five NIMs again, each in one new container, at one request in flight and at the level where the first night's rate stopped rising; and the calibration read by the duration of a request instead of by the rate. The load tool, the request bodies (the same files, by SHA-256), the 40 seconds per level and the gates are those of the first night.

**Both nights ran on the same graphics driver** (617.42; first night 617.42). The second night is a repeat, not a comparison of drivers. The idle-card gate ran 51 times in this night's log and refused 0 times.

## The calibration, read two ways, on both nights

| NIM | Night | Own client: p50 of one request, ms | AIPerf at 1 in flight: p50, ms | Difference | By rate: own client · AIPerf, items/s | Difference |
|---|---|---|---|---|---|---|
| llama-nemotron-embed-300m-v2 | first | 55.7 | 54.1 | -2.8% | 824.4 · 1120.1 | +35.9% **(outside 20%)** |
| llama-nemotron-embed-300m-v2 | second | 55.3 | 56.6 | +2.4% | 822.5 · 1073.0 | +30.5% **(outside 20%)** |
| nemotron-3-embed-1b | first | 247.3 | 250.9 | +1.5% | 245.1 · 251.8 | +2.7% |
| nemotron-3-embed-1b | second | 249.0 | 248.9 | -0.0% | 241.6 · 255.1 | +5.6% |
| llama-nemotron-rerank-1b-v2 | first | 141.5 | 140.1 | -1.0% | 680.9 · 678.3 | -0.4% |
| llama-nemotron-rerank-1b-v2 | second | 141.6 | 140.0 | -1.1% | 681.1 · 681.7 | +0.1% |
| llama-nemotron-embed-1b-v2 | first | 106.0 | 103.9 | -2.0% | 498.3 · 593.7 | +19.1% |
| llama-nemotron-embed-1b-v2 | second | 106.3 | 103.8 | -2.4% | 497.6 · 596.8 | +19.9% |
| llama-nemotron-embed-vl-1b-v2 | first | 218.7 | 217.4 | -0.6% | 274.0 · 290.5 | +6.0% |
| llama-nemotron-embed-vl-1b-v2 | second | 214.1 | 214.7 | +0.3% | 279.4 · 296.4 | +6.1% |
| llama-nemotron-rerank-500m-v2 | first | 85.5 | 85.3 | -0.2% | 1127.5 · 1112.9 | -1.3% |
| llama-nemotron-rerank-500m-v2 | second | 84.6 | 85.2 | +0.7% | 1134.4 · 1122.7 | -1.0% |

By the duration of a request the two instruments are at most 2.8% apart on every NIM and night. By the rate they are up to 35.9% apart, the same NIM on both nights: the own client's rate is items divided by the wall time of a pass, which also holds the time the client spends reading each answer. The first night's rule (rate) is reported as it was; the rule that stops an arm on this night is the duration, and no arm was stopped.

## llama-nemotron-embed-300m-v2: the whole arm

`nvcr.io/nim/nvidia/llama-nemotron-embed-300m-v2:1.13.0` · started with: no profile set · card memory once ready: 4,749 MiB (first container), 4,678 MiB (second)

**one query per request**

| In flight | Requests/s | Queries/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 170.4 | 170 | 5.0 | 5.7 | 6.8 | 6,815 | 0 |  |
| 2 | 281.3 | 281 | 6.1 | 7.3 | 9.0 | 11,251 | 0 |  |
| 4 | 373.2 | 373 | 9.2 | 12.3 | 15.5 | 14,934 | 0 |  |
| 8 | 399.6 | 400 | 18.6 | 22.9 | 28.3 | 15,994 | 0 |  |
| 16 | 416.2 | 416 | 37.1 | 42.3 | 50.5 | 16,653 | 0 |  |
| 32 | 417.2 | 417 | 75.2 | 81.8 | 94.3 | 16,693 | 0 | 413.5 · 94.8 |
| 64 | 416.5 | 416 | 151.6 | 162.2 | 184.9 | 16,662 | 0 | 413.8 · 181.9 |

The rate stops rising at 8 in flight (the lowest level within 5% of the highest rate, 417.2 requests per second = 417 queries per second); from 1 in flight to the highest rate it rises 2.45-fold. Highest level with a p99 of at most 100 ms: 32; of at most 500 ms: 64. Levels at which the mean number in flight was below 90% of the level: [1, 2, 4] (lowest share 88%): at these the rate also holds the load tool's own time between two requests. Load-tool container: at most 2.2 of 28 cores.

**64 passages per request**

| In flight | Requests/s | Passages/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 16.8 | 1,073 | 56.6 | 66.8 | 89.9 | 670 | 0 |  |
| 2 | 31.1 | 1,990 | 60.8 | 72.5 | 94.0 | 1,244 | 0 |  |
| 4 | 33.3 | 2,133 | 117.6 | 129.6 | 138.0 | 1,333 | 0 |  |
| 8 | 33.3 | 2,133 | 238.1 | 252.2 | 259.2 | 1,333 | 0 |  |
| 16 | 33.4 | 2,138 | 477.5 | 494.9 | 505.2 | 1,336 | 0 |  |
| 32 | 33.3 | 2,133 | 957.1 | 971.8 | 986.1 | 1,333 | 0 | 33.3 · 993.9 |
| 64 | 33.3 | 2,131 | 1,915.6 | 1,933.1 | 1,953.7 | 1,332 | 0 | 33.2 · 1,958.3 |

The rate stops rising at 4 in flight (the lowest level within 5% of the highest rate, 33.4 requests per second = 2,138 passages per second); from 1 in flight to the highest rate it rises 1.99-fold. Highest level with a p99 of at most 100 ms: 2; of at most 500 ms: 8. The level was held wherever that can be read (at least 96%). Load-tool container: at most 1.51 of 28 cores.

What was written before the run, and what came:

| Expectation | Came |
|---|---|
| calibration: within 5% by duration (first night: -2.83%); outside 20% by rate again | +2.40% by duration; +30.46% by rate |
| passage shape: the rate stops rising at 1 or 2 in flight; at one in flight between 1,000 and 1,250 passages per second (first night, one level: 1120.1) | stops rising at 4; 1,073 passages per second at one in flight |
| query shape: the rate stops rising at 2 or 4 in flight; the levels 1 and 2 may be below 90% held, as on the two fastest arms of the first night (requests of a few milliseconds) | stops rising at 8; levels below 90% held: [1, 2, 4] |
| errors: none | 0 |

Wrong about where the rate stops rising: passage shape and query shape. This NIM goes on gaining to a higher level than was guessed.

## Five NIMs, two nights

| NIM | Shape | In flight | First night: requests/s · p50 ms | Second night: requests/s · p50 ms | Second against first: rate · p50 |
|---|---|---|---|---|---|
| nemotron-3-embed-1b | one query per request | 1 | 268.7 · 3.0 | 268.5 · 3.0 | -0.1% · +0.0% |
| nemotron-3-embed-1b | one query per request | 2 | 371.1 · 4.4 | 373.8 · 4.5 | +0.7% · +1.6% |
| nemotron-3-embed-1b | 64 passages per request | 1 | 3.9 · 250.9 | 4.0 · 248.9 | +1.3% · -0.8% |
| nemotron-3-embed-1b | 64 passages per request | 2 | 4.2 · 465.3 | 4.3 · 465.9 | +0.7% · +0.1% |
| llama-nemotron-rerank-1b-v2 | one query with 100 passages | 1 | 6.8 · 140.1 | 6.8 · 140.0 | +0.5% · -0.1% |
| llama-nemotron-rerank-1b-v2 | one query with 100 passages | 16 | 9.8 · 1,521.8 | 9.9 · 1,573.1 | +0.5% · +3.4% |
| llama-nemotron-rerank-1b-v2 | one query with 10 passages | 1 | 36.0 · 27.3 | 35.8 · 27.4 | -0.3% · +0.4% |
| llama-nemotron-rerank-1b-v2 | one query with 10 passages | 16 | 72.2 · 217.8 | 72.6 · 215.5 | +0.7% · -1.0% |
| llama-nemotron-embed-1b-v2 | one query per request | 1 | 110.5 · 8.2 | 112.5 · 8.1 | +1.8% · -1.3% |
| llama-nemotron-embed-1b-v2 | one query per request | 2 | 182.6 · 10.0 | 184.5 · 10.0 | +1.0% · -0.7% |
| llama-nemotron-embed-1b-v2 | 64 passages per request | 1 | 9.3 · 103.9 | 9.3 · 103.8 | +0.5% · -0.1% |
| llama-nemotron-embed-1b-v2 | 64 passages per request | 2 | 12.4 · 157.6 | 12.5 · 156.6 | +0.9% · -0.6% |
| llama-nemotron-embed-vl-1b-v2 | one query per request | 1 | 292.7 · 2.8 | 296.8 · 2.8 | +1.4% · -1.1% |
| llama-nemotron-embed-vl-1b-v2 | one query per request | 2 | 418.4 · 4.1 | 421.2 · 4.0 | +0.7% · -1.8% |
| llama-nemotron-embed-vl-1b-v2 | 64 passages per request | 1 | 4.5 · 217.4 | 4.6 · 214.7 | +2.0% · -1.2% |
| llama-nemotron-rerank-500m-v2 | one query with 100 passages | 1 | 11.1 · 85.3 | 11.2 · 85.2 | +0.9% · -0.1% |
| llama-nemotron-rerank-500m-v2 | one query with 100 passages | 8 | 18.2 · 427.4 | 18.4 · 423.7 | +1.0% · -0.9% |
| llama-nemotron-rerank-500m-v2 | one query with 10 passages | 1 | 54.8 · 17.6 | 55.0 · 17.5 | +0.4% · -0.7% |
| llama-nemotron-rerank-500m-v2 | one query with 10 passages | 16 | 140.2 · 111.7 | 141.2 · 111.1 | +0.7% · -0.5% |

19 levels were run on both nights with the same request bodies and without errors. The rate of the second night differs from the first by at most 2.05% on any of them (written before the run: within 5% at the saturation level). Dates and drivers per row, and the p99, are in [`two_nights.md`](two_nights.md) and [`two_nights.json`](two_nights.json).

## What this does not show

- A ceiling. A rate seen on two nights is the rate of two nights on this host and this driver.
- A difference between drivers: both nights ran on one.
- A number of users, two services on the card at once, requests of other sizes or languages: as on the first night.
- The first night's figure does not draw this night's NIM; its file was not changed.
