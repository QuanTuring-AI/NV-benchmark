# Vol.4 · the retrieval NIMs with more than one request in flight (2026-10-12)

[← Vol.4 README](../../README.md) · pre-registration: [`prediction_concurrency_sweep.json`](prediction_concurrency_sweep.json), frozen 2026-10-12T04:13:26+0800, before the first serving container of the session (two probe containers ran before it and are named as such in it) · run log: [`events.jsonl`](events.jsonl) · [the second night](../concurrency_sweep_second_night/README.md), where the NIM stopped here was swept and five were run again

**What was measured.** One retrieval NIM alone on one RTX 5090, and a load tool that keeps a fixed number of requests in flight (closed loop: a finished request is replaced at once) for 40 seconds per level: 1, 2, 4, 8, 16, 32, 64, and one more level while the rate still rose by more than 5%. Per NIM two request shapes. 5 of the six NIMs of the plan were swept in this session (90 levels); llama-nemotron-embed-300m-v2 was stopped before its sweep by the calibration rule (see below).

**Nothing passes or fails here.** There is no published limit for the duration of an embedding or a reranking request. The tables give the rate and the duration per level; two round numbers (a p99 of at most 100 ms, and of at most 500 ms) are used to read them, and that is all they are.

## How

- **Load tool:** AIPerf 0.11.0 in its own container on the NIM's Docker network (no host port in between), [`../../client_aiperf/Dockerfile`](../../client_aiperf/Dockerfile). It replays request bodies that [`../../scripts/sweep_payloads.py`](../../scripts/sweep_payloads.py) wrote beforehand with this volume's own request builders, verbatim; [`../../scripts/sweep_level.py`](../../scripts/sweep_level.py) runs one level and keeps AIPerf's figures.
- **Request shapes:** embeddings: one query per request (the 393 queries of the reduced MIRACL zh task), and 64 passages per request (the first 4,096 passages of that corpus, the sample of every timed embedding cell of this volume). Reranking: one query with the first 100 passages of its first-stage ranking over the whole MIRACL zh corpus, and with the first 10. `truncate` END on every request.
- **Per NIM:** a new container; this volume's own client at one request in flight (the calibration); the sweep; the container removed; a second new container and the two highest levels again. Both containers are shown, not pooled.
- **A rate is requests per second as AIPerf reports it;** items per second is that rate times the items per request. A duration is AIPerf's `request_latency`, measured in the client.
- **Is a flat rate the NIM's or the load tool's?** Two checks per level, both in [`table.json`](table.json): the CPU time of the load-tool container (a level at 85% or more of all its cores would be marked client-limited), and whether the level was held: requests per second times the mean duration is the mean number of requests in flight, and a tool that sends late falls below the level it was asked to hold. The second check does not see a tool that is slow to read an answer (that time is inside the duration), and it is not read where one request lasts more than 5% of a level's 40 seconds. It fails on nemotron-3-embed-1b, one query per request, 1 in flight (p50 3.0 ms); nemotron-3-embed-1b, one query per request, 2 in flight (p50 4.4 ms); llama-nemotron-embed-vl-1b-v2, one query per request, 1 in flight (p50 2.8 ms); llama-nemotron-embed-vl-1b-v2, one query per request, 2 in flight (p50 4.1 ms): requests of a few milliseconds at 1, 2 in flight, where the tool's own time between two requests is a visible share. Those rates are lower bounds; every readable level from 4 in flight on was held.
- **Host:** Windows 11, Docker Desktop on WSL2, graphics driver 617.42. The idle-card gate ran before every container and, in its timed form, before every level (127 gates in the log).

## Calibration: the load tool beside this volume's own client, one request in flight

| NIM | Own client, items/s | AIPerf at 1 in flight, items/s | Difference | Within 20% |
|---|---|---|---|---|
| nvidia/nemotron-3-embed-1b | 245.1 | 251.8 | +2.7% | yes |
| nvidia/llama-nemotron-rerank-1b-v2 | 680.9 | 678.3 | -0.4% | yes |
| nvidia/llama-nemotron-embed-1b-v2 | 498.3 | 593.7 | +19.1% | yes |
| nvidia/llama-nemotron-embed-vl-1b-v2 | 274.0 | 290.5 | +6.0% | yes |
| nvidia/llama-nemotron-rerank-500m-v2 | 1127.5 | 1112.9 | -1.3% | yes |
| nvidia/llama-nemotron-embed-300m-v2 | 824.4 | 1120.1 | +35.9% | **no: stopped** |

The own client is `embed_cell.py throughput` (64 passages per request, three passes, the median) for an embedding NIM and `rerank_latency.py` (100 passages per call, one pass) for a reranking NIM. The pre-registration stops an arm that is more than 20% apart before its sweep; that happened to llama-nemotron-embed-300m-v2, which has no sweep here.

The same two instruments by the duration of one request instead of by the rate (embedding NIMs; the own client times every request of its three passes):

| NIM | Own client, p50 of one request, ms | AIPerf at 1 in flight, p50, ms | Difference | Own client: 64 passages ÷ its rate, ms |
|---|---|---|---|---|
| nvidia/nemotron-3-embed-1b | 247.3 | 250.9 | +1.5% | 261.1 |
| nvidia/llama-nemotron-embed-1b-v2 | 106.0 | 103.9 | -2.0% | 128.4 |
| nvidia/llama-nemotron-embed-vl-1b-v2 | 218.7 | 217.4 | -0.6% | 233.6 |
| nvidia/llama-nemotron-embed-300m-v2 | 55.7 | 54.1 | -2.8% | 77.6 |

The two instruments agree on how long a request takes. They differ in the rate because the own client's rate is passages divided by the wall time of a pass, and that wall time also holds what the client does between two requests (it reads every returned number into an array before it sends the next request); AIPerf at one request in flight sends the next request at once. The last column minus the first is that time per request. It is between 13.8 and 22.4 ms on these NIMs, so it is the largest share on the NIM whose requests are shortest. **Every "passages per second" of this volume's own client, in this file and in the other result folders, is the rate of that client, not the most the server gives.**

## Per NIM

### nvidia/nemotron-3-embed-1b

`nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2` · started with: NIM_ENGINE_PRECISION=fp16, weights from the NIM's own download · card memory once ready: 6,008 MiB

**one query per request**

| In flight | Requests/s | Queries/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 268.7 | 269 | 3.0 | 3.5 | 4.2 | 10,800 | 0 |  |
| 2 | 371.1 | 371 | 4.4 | 5.2 | 6.4 | 14,926 | 0 |  |
| 4 | 384.3 | 384 | 9.5 | 10.3 | 11.3 | 15,457 | 0 |  |
| 8 | 382.4 | 382 | 19.8 | 21.1 | 22.6 | 15,375 | 0 |  |
| 16 | 377.2 | 377 | 41.1 | 43.3 | 46.2 | 15,173 | 0 |  |
| 32 | 378.6 | 379 | 82.8 | 86.2 | 89.3 | 15,233 | 0 | 378.5 · 98.2 |
| 64 | 377.9 | 378 | 166.8 | 172.7 | 188.3 | 15,196 | 0 | 373.3 · 221.7 |

The rate stops rising at 2 in flight (the lowest level within 5% of the highest rate, 384.3 requests per second = 384 queries per second); from 1 in flight to the highest rate it rises 1.43-fold. Highest level with a p99 of at most 100 ms: 32; of at most 500 ms: 64. Levels at which the mean number in flight was below 90% of the level: [1, 2] (lowest share 82%): at these the rate is also held down by the load tool's own time between two requests. Load-tool container: at most 2.05 of 28 cores.

**64 passages per request**

| In flight | Requests/s | Passages/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 3.9 | 252 | 250.9 | 270.7 | 310.3 | 158 | 0 |  |
| 2 | 4.2 | 271 | 465.3 | 508.6 | 533.9 | 170 | 0 |  |
| 4 | 4.2 | 272 | 931.1 | 991.0 | 1,021.5 | 168 | 0 |  |
| 8 | 4.2 | 272 | 1,865.5 | 1,937.2 | 1,968.0 | 168 | 0 |  |
| 16 | 4.2 | 270 | 3,763.1 | 3,855.7 | 3,864.4 | 160 | 0 |  |
| 32 | 4.2 | 267 | 7,553.9 | 7,722.9 | 7,733.5 | 160 | 0 | 4.2 · 7,770.6 |
| 64 | 4.2 | 271 | 15,110.3 | 15,134.2 | 15,139.3 | 128 | 0 | 4.2 · 15,309.1 |

The rate stops rising at 2 in flight (the lowest level within 5% of the highest rate, 4.2 requests per second = 272 passages per second); from 1 in flight to the highest rate it rises 1.08-fold. Highest level with a p99 of at most 100 ms: none; of at most 500 ms: 1. The level was held wherever that can be read (rate times mean duration: at least 99% of the level). Load-tool container: at most 1.03 of 28 cores.

### nvidia/llama-nemotron-rerank-1b-v2

`nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0` · started with: no profile set · card memory once ready: 5,564 MiB

**one query with 100 passages**

| In flight | Requests/s | Pairs/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 6.8 | 678 | 140.1 | 187.4 | 227.2 | 272 | 0 |  |
| 2 | 8.2 | 825 | 238.2 | 285.0 | 339.1 | 331 | 0 |  |
| 4 | 8.5 | 850 | 459.0 | 551.6 | 627.2 | 341 | 0 |  |
| 8 | 9.3 | 933 | 828.5 | 974.2 | 1,187.6 | 374 | 0 |  |
| 16 | 9.8 | 983 | 1,521.8 | 2,058.6 | 2,392.2 | 394 | 0 |  |
| 32 | 9.8 | 978 | 3,198.8 | 3,588.6 | 3,890.8 | 389 | 0 | 9.8 · 3,882.5 |
| 64 | 9.8 | 977 | 6,481.3 | 6,869.0 | 7,143.3 | 392 | 0 | 9.8 · 7,276.4 |

The rate stops rising at 16 in flight (the lowest level within 5% of the highest rate, 9.8 requests per second = 983 pairs per second); from 1 in flight to the highest rate it rises 1.45-fold. Highest level with a p99 of at most 100 ms: none; of at most 500 ms: 2. The level was held wherever that can be read (rate times mean duration: at least 98% of the level). Load-tool container: at most 1.07 of 28 cores.

**one query with 10 passages**

| In flight | Requests/s | Pairs/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 36.0 | 360 | 27.3 | 33.8 | 42.0 | 1,445 | 0 |  |
| 2 | 49.0 | 490 | 39.3 | 49.5 | 58.2 | 1,971 | 0 |  |
| 4 | 53.8 | 538 | 72.2 | 87.2 | 102.3 | 2,159 | 0 |  |
| 8 | 66.0 | 660 | 118.9 | 136.1 | 154.5 | 2,653 | 0 |  |
| 16 | 72.2 | 722 | 217.8 | 250.8 | 279.9 | 2,898 | 0 |  |
| 32 | 72.1 | 721 | 439.3 | 484.5 | 519.8 | 2,894 | 0 | 72.1 · 523.3 |
| 64 | 71.7 | 717 | 885.4 | 938.7 | 975.4 | 2,880 | 0 | 71.8 · 970.3 |

The rate stops rising at 16 in flight (the lowest level within 5% of the highest rate, 72.2 requests per second = 722 pairs per second); from 1 in flight to the highest rate it rises 2.01-fold. Highest level with a p99 of at most 100 ms: 2; of at most 500 ms: 16. The level was held wherever that can be read (rate times mean duration: at least 97% of the level). Load-tool container: at most 1.25 of 28 cores.

### nvidia/llama-nemotron-embed-1b-v2

`nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2:1.13.0` · started with: no profile set (fp8, selected by the image) · card memory once ready: 5,564 MiB

**one query per request**

| In flight | Requests/s | Queries/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 110.5 | 110 | 8.2 | 8.6 | 9.7 | 4,436 | 0 |  |
| 2 | 182.6 | 183 | 10.0 | 10.5 | 11.4 | 7,330 | 0 |  |
| 4 | 183.4 | 183 | 20.8 | 21.4 | 22.3 | 7,360 | 0 |  |
| 8 | 183.7 | 184 | 42.4 | 43.4 | 45.1 | 7,369 | 0 |  |
| 16 | 182.1 | 182 | 86.5 | 88.1 | 91.8 | 7,305 | 0 |  |
| 32 | 182.1 | 182 | 173.9 | 176.5 | 184.1 | 7,308 | 0 | 182.0 · 184.5 |
| 64 | 181.7 | 182 | 349.6 | 355.5 | 375.4 | 7,289 | 0 | 182.6 · 381.9 |

The rate stops rising at 2 in flight (the lowest level within 5% of the highest rate, 183.7 requests per second = 184 queries per second); from 1 in flight to the highest rate it rises 1.66-fold. Highest level with a p99 of at most 100 ms: 16; of at most 500 ms: 64. The level was held wherever that can be read (rate times mean duration: at least 92% of the level). Load-tool container: at most 1.53 of 28 cores.

**64 passages per request**

| In flight | Requests/s | Passages/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 9.3 | 594 | 103.9 | 122.2 | 158.7 | 372 | 0 |  |
| 2 | 12.4 | 794 | 157.6 | 179.8 | 203.7 | 497 | 0 |  |
| 4 | 12.4 | 795 | 318.3 | 349.8 | 367.6 | 498 | 0 |  |
| 8 | 12.4 | 796 | 639.7 | 677.4 | 693.7 | 499 | 0 |  |
| 16 | 12.4 | 795 | 1,284.4 | 1,328.5 | 1,352.4 | 498 | 0 |  |
| 32 | 12.4 | 795 | 2,565.0 | 2,604.1 | 2,633.6 | 498 | 0 | 12.4 · 2,622.6 |
| 64 | 12.3 | 790 | 5,141.0 | 5,189.6 | 5,226.9 | 496 | 0 | 12.4 · 5,201.8 |

The rate stops rising at 2 in flight (the lowest level within 5% of the highest rate, 12.4 requests per second = 796 passages per second); from 1 in flight to the highest rate it rises 1.34-fold. Highest level with a p99 of at most 100 ms: none; of at most 500 ms: 4. The level was held wherever that can be read (rate times mean duration: at least 98% of the level). Load-tool container: at most 1.19 of 28 cores.

### nvidia/llama-nemotron-embed-vl-1b-v2

`nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:2.3.0` · started with: no profile set, weights from the NIM's own download · card memory once ready: 7,717 MiB

**one query per request**

| In flight | Requests/s | Queries/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 292.7 | 293 | 2.8 | 3.0 | 3.2 | 11,763 | 0 |  |
| 2 | 418.4 | 418 | 4.1 | 4.3 | 4.5 | 16,805 | 0 |  |
| 4 | 418.8 | 419 | 8.8 | 9.1 | 9.4 | 16,832 | 0 |  |
| 8 | 418.8 | 419 | 18.3 | 18.7 | 19.4 | 16,823 | 0 |  |
| 16 | 411.1 | 411 | 37.4 | 38.4 | 60.6 | 16,505 | 0 |  |
| 32 | 417.1 | 417 | 75.3 | 76.9 | 78.8 | 16,761 | 0 | 424.7 · 77.3 |
| 64 | 418.7 | 419 | 151.0 | 153.0 | 157.9 | 16,830 | 0 | 425.7 · 155.7 |

The rate stops rising at 2 in flight (the lowest level within 5% of the highest rate, 418.8 requests per second = 419 queries per second); from 1 in flight to the highest rate it rises 1.43-fold. Highest level with a p99 of at most 100 ms: 32; of at most 500 ms: 64. Levels at which the mean number in flight was below 90% of the level: [1, 2] (lowest share 83%): at these the rate is also held down by the load tool's own time between two requests. Load-tool container: at most 1.92 of 28 cores.

**64 passages per request**

| In flight | Requests/s | Passages/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 4.5 | 290 | 217.4 | 234.5 | 251.5 | 182 | 0 |  |
| 2 | 4.7 | 298 | 425.6 | 456.4 | 472.3 | 187 | 0 |  |
| 4 | 4.7 | 300 | 847.6 | 890.4 | 915.8 | 188 | 0 |  |
| 8 | 4.7 | 300 | 1,693.2 | 1,764.3 | 1,791.6 | 188 | 0 |  |
| 16 | 4.7 | 299 | 3,406.5 | 3,496.1 | 3,522.4 | 187 | 0 |  |
| 32 | 4.7 | 299 | 6,804.4 | 6,903.7 | 6,955.9 | 187 | 0 | 4.7 · 6,877.8 |
| 64 | 4.7 | 300 | 13,578.3 | 13,672.3 | 13,765.1 | 187 | 0 | 4.7 · 13,533.6 |

The rate stops rising at 1 in flight (the lowest level within 5% of the highest rate, 4.7 requests per second = 300 passages per second); from 1 in flight to the highest rate it rises 1.03-fold. Highest level with a p99 of at most 100 ms: none; of at most 500 ms: 2. The level was held wherever that can be read (rate times mean duration: at least 98% of the level). Load-tool container: at most 1.02 of 28 cores.

### nvidia/llama-nemotron-rerank-500m-v2

`nvcr.io/nim/nvidia/llama-nemotron-rerank-500m-v2:1.10.0` · started with: no profile set · card memory once ready: 5,099 MiB

**one query with 100 passages**

| In flight | Requests/s | Pairs/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 11.1 | 1,113 | 85.3 | 111.8 | 139.6 | 446 | 0 |  |
| 2 | 16.1 | 1,611 | 120.8 | 147.0 | 175.5 | 646 | 0 |  |
| 4 | 16.7 | 1,674 | 232.7 | 283.9 | 319.8 | 672 | 0 |  |
| 8 | 18.2 | 1,822 | 427.4 | 510.3 | 594.4 | 729 | 0 |  |
| 16 | 19.1 | 1,909 | 817.4 | 958.6 | 1,086.4 | 765 | 0 |  |
| 32 | 19.0 | 1,901 | 1,653.6 | 1,826.5 | 1,949.0 | 762 | 0 | 19.1 · 1,954.8 |
| 64 | 19.1 | 1,913 | 3,312.6 | 3,519.3 | 3,638.1 | 766 | 0 | 19.0 · 3,702.7 |

The rate stops rising at 8 in flight (the lowest level within 5% of the highest rate, 19.1 requests per second = 1,913 pairs per second); from 1 in flight to the highest rate it rises 1.72-fold. Highest level with a p99 of at most 100 ms: none; of at most 500 ms: 4. The level was held wherever that can be read (rate times mean duration: at least 97% of the level). Load-tool container: at most 1.14 of 28 cores.

**one query with 10 passages**

| In flight | Requests/s | Pairs/s | p50 ms | p90 ms | p99 ms | Requests in 40 s | Errors | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 54.8 | 548 | 17.6 | 21.4 | 26.2 | 2,192 | 0 |  |
| 2 | 90.2 | 902 | 20.7 | 26.3 | 32.4 | 3,614 | 0 |  |
| 4 | 99.5 | 995 | 38.8 | 47.2 | 56.4 | 3,984 | 0 |  |
| 8 | 123.0 | 1,230 | 63.5 | 75.7 | 86.9 | 4,928 | 0 |  |
| 16 | 140.2 | 1,402 | 111.7 | 130.5 | 145.8 | 5,615 | 0 |  |
| 32 | 139.7 | 1,396 | 226.5 | 249.1 | 271.9 | 5,594 | 0 | 139.8 · 266.5 |
| 64 | 139.9 | 1,399 | 455.1 | 481.0 | 505.6 | 5,600 | 0 | 139.7 · 503.6 |

The rate stops rising at 16 in flight (the lowest level within 5% of the highest rate, 140.2 requests per second = 1,402 pairs per second); from 1 in flight to the highest rate it rises 2.56-fold. Highest level with a p99 of at most 100 ms: 8; of at most 500 ms: 32. The level was held wherever that can be read (rate times mean duration: at least 95% of the level). Load-tool container: at most 1.45 of 28 cores.

## The Blueprint's default embedding image, 1.12.0

`nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:1.12.0` is the image the RAG Blueprint's compose files name; the cells above ran the same model as 2.3.0. It had never been started on this card.

**Started as pre-registered (no setting beyond the usual ones), it reports ready and then answers every embedding request with HTTP 500.** It selected its TensorRT fp8 profile, reported ready after 131 s (8,983 MiB on the card), and the first request of the smoke test came back as an error whose text names Triton's Python backend and `Failed to open the cudaIpcHandle` (the run log keeps the answer). The host is Docker Desktop on WSL2.

**Not pre-registered, added after that result and noted in the run log before it started:** the same image with its ONNX fp16 profile (`NIM_MODEL_PROFILE=f7391ddbcb95…`). It serves (ready after 146 s, 6,733 MiB). Another profile is another variable: the rows below are that arm, not the pre-registered cell.

| Data set | nDCG@10, 1.12.0 ONNX fp16 | nDCG@10, 2.3.0 (first session) | Difference | Recall@100, 1.12.0 · 2.3.0 | Passages · seconds to encode them (1.12.0) |
|---|---|---|---|---|---|
| beir-scifact | 0.77294 | 0.76704 | +0.00590 | 0.96667 · 0.96667 | 5,183 · 113 |
| miracl-hn-zh | 0.64750 | 0.64837 | -0.00087 | 0.98044 · 0.98127 | 81,309 · 1,360 |
| miracl-hn-ja | 0.70959 | 0.71875 | -0.00916 | 0.98379 · 0.98708 | 185,319 · 3,247 |

| In flight, one query per request | 1.12.0 ONNX fp16: requests/s · p50 ms · p99 ms | 2.3.0: requests/s · p50 ms · p99 ms |
|---|---|---|
| 1 | 35.5 · 26.6 · 35.6 | 292.7 · 2.8 · 3.2 |
| 2 | 42.0 · 45.1 · 68.3 | 418.4 · 4.1 · 4.5 |

The two images are not one variable apart: runtime 1.x against 2.x, an ONNX fp16 profile against the profile 2.3.0 selects, and one container each. Of this arm only the levels 1 and 2 of the query shape were run; the session's time limit ended it there, and the own-client passes and the 64-passage level were not run (the encoding of the ja corpus was still on the card when their gates were asked). The pre-registered reading (nDCG@10 within 0.002 of the 2.3.0 value on each of the three data sets (the first session's two serving paths of one model agreed to 0.0011) and the rate at one request in flight not lower by more than 5% => the older image becomes a candidate for removal; otherwise it stays) was written for an image that serves as it starts; as pre-registered, this one does not.

## The tool's own ceiling

Several NIMs stop at nearly the same rate for one query per request. To see whether that is the NIMs or the instrument, the same load tool (the same container, the same request bodies) was run against a server that holds no model and answers every request at once with a body of the size the largest NIM answer of that shape had. What the tool reaches there is what it can send, receive and record by itself. No card is used.

Pre-registered and frozen 2026-10-13T22:25:54+0800 ([`prediction_tool_ceiling.json`](../tool_ceiling/prediction_tool_ceiling.json)); two runs, each with new server containers; 20 seconds per level. **Rule written before the runs:** room of 2 or more: the tool was not what held that level's rate. Below 2: the level is marked, and every NIM rate at that level is to be read as 'at least'. A tool level with errors in either run is not read.

| Request shape | Answer the server sends, bytes | Lowest room over the seven levels | Levels with room below 2 |
|---|---|---|---|
| one query per request | 39,884 | 2.99 | none |
| 64 passages per request | 2,544,489 | 9.68 | none |
| one query with 100 passages | 3,395 | 58.77 | none |
| one query with 10 passages | 390 | 14.43 | none |

**At every level of every shape the tool could send at least 2.99 times what the fastest NIM took: the flat rates in the tables above are the NIMs', not the tool's.**

Per level and per run: [`../tool_ceiling/README.md`](../tool_ceiling/README.md).

## What this does not show

- A number of users. A level is a number of requests in flight; people pause between requests.
- Two services on the card at once (an encoder beside a reranker or a language model): every NIM was alone.
- Requests of other sizes or languages, or a search service behind the encoder.
- A second night. One request in flight and the saturation level of every NIM are to be run again on another night; until then every figure here is one session.
- A sweep of llama-nemotron-embed-300m-v2: stopped by the calibration rule, see above.
