# READ ME FIRST — B′ results

本目錄的 bprime_verdict.json 內 "reproduced" 一詞不可引用。效度閘（A1≈A2 差 <10%）未過（16.8%），而判決程式未將效度閘設為前提。有效的結論只有三句，見下。

**The word "reproduced" in `bprime_verdict.json` must not be quoted.** The validity gate (A1 and A2 within 10%) failed at 16.8%, and the verdict program did not treat that gate as a precondition. `bprime_verdict.json` is kept exactly as the program wrote it.

## The only valid conclusions from this run

1. **Memory pressure is ruled out.** During B′ the NIM process's GPU memory footprint did not move (span 0.0 MiB; noise 2 MiB).
2. **Ollama using the GPU during NIM requests was not observed.** 0 of the 5 qualifying samples had engine utilization above 5% — a small n.
3. **The mechanism of the TTFT rise is not established.**

These three do not depend on the failed validity gate: (1) and (2) are measured inside cell B′ itself.

## Why validity failed

The first request after the container became ready took 579.4 ms in cell A1; the other 29 were ≤ 76.0 ms. The pre-registered rule compared cell averages and did not exclude that first request. The rule was not changed after the run.

## Other files

- `verdict_patch/` — a post-run fix to the verdict script's timestamp parsing (no rule changed); the registered script is kept there unchanged.
- `precheck/calibration_numgpu.jsonl` — measured Ollama GPU footprint for `num_gpu` 0–7 (llama3.1:8b, Ollama 0.33.3, NIM not running). Reusable for other co-residence designs.
- `counters/` — per-process Windows GPU counter samples. Not intended for publication (they record unrelated desktop processes).
