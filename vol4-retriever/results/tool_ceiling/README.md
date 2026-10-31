# Vol.4 · the load tool against a server that answers at once

[← the concurrency sweep](../concurrency_sweep/README.md) · run log: [`events.jsonl`](events.jsonl) · table: [`table.json`](table.json)

Several NIMs stop at nearly the same rate for one query per request. To see whether that is the NIMs or the instrument, the same load tool (the same container, the same request bodies) was run against a server that holds no model and answers every request at once with a body of the size the largest NIM answer of that shape had. What the tool reaches there is what it can send, receive and record by itself. No card is used.

Pre-registered and frozen 2026-10-13T22:25:54+0800 ([`prediction_tool_ceiling.json`](../tool_ceiling/prediction_tool_ceiling.json)); two runs, each with new server containers; 20 seconds per level. **Rule written before the runs:** room of 2 or more: the tool was not what held that level's rate. Below 2: the level is marked, and every NIM rate at that level is to be read as 'at least'. A tool level with errors in either run is not read.

| Request shape | Answer the server sends, bytes | Lowest room over the seven levels | Levels with room below 2 |
|---|---|---|---|
| one query per request | 39,884 | 2.99 | none |
| 64 passages per request | 2,544,489 | 9.68 | none |
| one query with 100 passages | 3,395 | 58.77 | none |
| one query with 10 passages | 390 | 14.43 | none |

**At every level of every shape the tool could send at least 2.99 times what the fastest NIM took: the flat rates in the tables above are the NIMs', not the tool's.**

## Per request shape

**one query per request** (the request bodies of the sweep: `e300/emb_query.inputs.json`; answer 39,884 bytes, target 39,787)

| In flight | Tool, first run: requests/s | Tool, second run | Fastest NIM at that level: requests/s | Room (lower run ÷ NIM) |
|---|---|---|---|---|
| 1 | 889 | 1,134 | 296.8 (llama-nemotron-embed-vl-1b-v2) | 2.99 |
| 2 | 1,556 | 1,956 | 421.2 (llama-nemotron-embed-vl-1b-v2) | 3.69 |
| 4 | 3,060 | 3,419 | 418.8 (llama-nemotron-embed-vl-1b-v2) | 7.31 |
| 8 | 4,314 | 5,007 | 418.8 (llama-nemotron-embed-vl-1b-v2) | 10.30 |
| 16 | 4,970 | 5,446 | 416.2 (llama-nemotron-embed-300m-v2) | 11.94 |
| 32 | 6,813 | 5,138 | 417.2 (llama-nemotron-embed-300m-v2) | 12.32 |
| 64 | 8,018 | 6,935 | 418.7 (llama-nemotron-embed-vl-1b-v2) | 16.56 |

**64 passages per request** (the request bodies of the sweep: `e300/emb_passage.inputs.json`; answer 2,544,489 bytes, target 2,539,304)

| In flight | Tool, first run: requests/s | Tool, second run | Fastest NIM at that level: requests/s | Room (lower run ÷ NIM) |
|---|---|---|---|---|
| 1 | 263 | 169 | 17.5 (llama-nemotron-embed-300m-v2) | 9.68 |
| 2 | 466 | 312 | 31.1 (llama-nemotron-embed-300m-v2) | 10.04 |
| 4 | 632 | 624 | 33.3 (llama-nemotron-embed-300m-v2) | 18.73 |
| 8 | 761 | 788 | 33.3 (llama-nemotron-embed-300m-v2) | 22.82 |
| 16 | 850 | 795 | 33.4 (llama-nemotron-embed-300m-v2) | 23.80 |
| 32 | 849 | 858 | 33.3 (llama-nemotron-embed-300m-v2) | 25.46 |
| 64 | 811 | 843 | 33.3 (llama-nemotron-embed-300m-v2) | 24.37 |

**one query with 100 passages** (the request bodies of the sweep: `rr500/rank_100.inputs.json`; answer 3,395 bytes, target 3,406)

| In flight | Tool, first run: requests/s | Tool, second run | Fastest NIM at that level: requests/s | Room (lower run ÷ NIM) |
|---|---|---|---|---|
| 1 | 804 | 660 | 11.2 (llama-nemotron-rerank-500m-v2) | 58.77 |
| 2 | 1,549 | 1,478 | 16.1 (llama-nemotron-rerank-500m-v2) | 91.79 |
| 4 | 2,520 | 2,245 | 16.7 (llama-nemotron-rerank-500m-v2) | 134.13 |
| 8 | 3,436 | 3,519 | 18.4 (llama-nemotron-rerank-500m-v2) | 186.68 |
| 16 | 4,248 | 3,583 | 19.1 (llama-nemotron-rerank-500m-v2) | 187.70 |
| 32 | 4,602 | 4,615 | 19.0 (llama-nemotron-rerank-500m-v2) | 242.03 |
| 64 | 5,094 | 4,252 | 19.1 (llama-nemotron-rerank-500m-v2) | 222.27 |

**one query with 10 passages** (the request bodies of the sweep: `rr500/rank_10.inputs.json`; answer 390 bytes, target 390)

| In flight | Tool, first run: requests/s | Tool, second run | Fastest NIM at that level: requests/s | Room (lower run ÷ NIM) |
|---|---|---|---|---|
| 1 | 963 | 1,055 | 55.0 (llama-nemotron-rerank-500m-v2) | 17.51 |
| 2 | 1,302 | 2,032 | 90.2 (llama-nemotron-rerank-500m-v2) | 14.43 |
| 4 | 2,256 | 3,558 | 99.5 (llama-nemotron-rerank-500m-v2) | 22.67 |
| 8 | 4,490 | 5,055 | 123.0 (llama-nemotron-rerank-500m-v2) | 36.50 |
| 16 | 4,886 | 6,710 | 141.2 (llama-nemotron-rerank-500m-v2) | 34.60 |
| 32 | 6,789 | 7,789 | 139.7 (llama-nemotron-rerank-500m-v2) | 48.61 |
| 64 | 8,131 | 9,125 | 139.9 (llama-nemotron-rerank-500m-v2) | 58.14 |

## What was written before the runs, and what came

| Expectation | Came |
|---|---|
| query: room of at least 2 at every level and of at least 8 from 8 in flight on | lowest room 2.99; from 8 in flight on the lowest is 10.30 |
| passage: room of at least 5 at every level | lowest room 9.68 |
| ranking: room of at least 20 at every level, both shapes | 100 passages: lowest 58.77; 10 passages: lowest 14.43 (below 20 at 1 and 2 in flight: **wrong there**) |
| two runs: within 15% of each other at every level | **wrong**: 13 of 28 levels are more than 15% apart, the furthest 58% |
| errors: none | 0 |

The two runs are far apart at many levels. The tool's ceiling moves with whatever else the host is doing; the run log notes what other containers were running when each server started (first run: 0 and 0; second run: 1 and 1, a container of another project; the log keeps the number, not the name). That is why the lower of the two runs is the one the rule uses, and why a room near 2 would not have been enough to say much.

## What this does not show

- How fast a NIM is.
- The tool beside a real NIM that also uses the host's CPU (the instant server uses almost none).
- A ceiling of the tool that is higher than this server's own: the figure is 'the tool reaches at least this'.
- Answers larger than the ones the sweep met, or other request bodies.
- The probes and an earlier unregistered run are named in the pre-registration; their records (`probe_*.json`) are not results.
