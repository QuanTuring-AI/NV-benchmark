![Nemotron 3 Nano on one RTX 5090](https://raw.githubusercontent.com/QuanTuring-AI/NV-benchmark/main/vol2-nemotron/figures/cover_vol2.png)

![Chat-shaped requests: total output throughput against per-request output speed, one point per concurrency level](https://raw.githubusercontent.com/QuanTuring-AI/NV-benchmark/main/vol2-nemotron/figures/pareto_chat_dark.png)

Nemotron 3 Nano (30B total / 3.5B active, NVFP4) on one RTX 5090 with NIM 2.0.12: memory, speed, long context, concurrency and answer quality. Nemotron Nano 9B v2 is shown as a reference point.

- **It fits with room to spare:** about 21 GiB at 32 sequences, about 25 GiB at the image default of 256 (4k context).
- **~300 tok/s for a single stream**, 4.1× the 9B v2 in tokens per second; an answer comes back 2.9× faster.
- **Speed does not drop with context:** 305 tok/s at 1k tokens, 308 tok/s at 120k.
- **128 concurrent chat requests inside the MLPerf Inference server latency target;** 8 with long RAG-shaped prompts.
- **95.7% on GSM8K and 88.0% on a 2,850-question MMLU sample with reasoning on;** turning reasoning off cost 5.5 and 12.3 points.

**Read:** [Vol.2 README](https://github.com/QuanTuring-AI/NV-benchmark/blob/vol2/vol2-nemotron/README.md) — results, method, and a claim-to-evidence table for every number.
**Check every number:** `python tools/check_claims.py vol2-nemotron/README.md`
**Reproduce:** `git checkout vol2`
