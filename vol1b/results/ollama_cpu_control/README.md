# Ollama CPU control

This is the final Ollama measurement in this repository; it exists to close out the Vol.1-A comparison, not to open a new one.

It measures, in one run on one machine, the generation rate of the same Ollama model with none of it in GPU memory (**CPU**, `options.num_gpu = 0`) and with all of it in GPU memory (**G**, default placement). It does not reproduce any earlier machine state.

## Boundary

| | |
|---|---|
| Engine | Ollama 0.34.0 · `llama3.1:8b`, id `46e0c10c039e` (Q4_K_M GGUF) · addressed as `http://127.0.0.1:11434` only · NIM not started, no container running at any request |
| Machine | Intel Core i7-14700 (20 cores, 28 logical) · two 32 GiB DDR5 modules on two memory controllers, 4800 MT/s configured · GPU 32,607 MiB, driver 591.86 (all from `versions.txt`) · GPU model NVIDIA GeForce RTX 5090, read with `nvidia-smi --query-gpu=name` at 01:37 the same night (the run did not record it) |
| Sample | G: the first 3 questions of the run order in `../p20_coresidence/sample.json` · CPU: all 50, in that order (the file's SHA-256 is checked by the run) |
| Payload | Vol.1 `run_benchmark.py` payload plus temperature 0.0, top_p 0.9, max 500 tokens, keep_alive 60m · 2 s between requests · no response text stored |
| Placement | read from `/api/ps` before and after every request: CPU `size_vram` = 0 at all 100 readings, G `size_vram` = `size` at all 6. The run stops before any measured request if a warm-up leaves the wrong placement. |
| Window | measured requests 2026-09-18 01:12–01:37 (+0800) · pre-run GPU memory 1,098 MiB |
| Not recorded | the NVIDIA Control Panel setting *CUDA – Sysmem Fallback Policy*; the harness cannot read it |
| Pre-registration | `prediction_ollama_cpu_control.json`, frozen before the run (`.sha256` beside it) |

## Result

All preconditions held: 0 errors in 53 requests; placement as required at every request; 3 G rows and 50 CPU rows, one per question.

| Arm | n | generation rate, client (tok/s) p50 [min–max] | generation rate, engine (tok/s) p50 | TTFT p50 (ms) | GPU memory in use before each request, median |
|---|---|---|---|---|---|
| G | 3 | 213.9 [187.5–233.5] | 238.3 | 46.8 | 8,365 MiB |
| CPU | 50 | **11.27** [10.23–12.08] | 11.41 | 286.5 | 1,120 MiB |

Client rate = whitespace-counted tokens / (total latency − TTFT), as Vol.1 counts tokens; engine rate = `eval_count / eval_duration`. On the three questions both arms ran, the median G rate is 19.1 times the CPU rate (client) and 20.6 times (engine).

Pre-registered: **R1** median CPU client rate between 5 and 40 tok/s — held (11.27). **R2** placement at every request — held (precondition P2).

Seen before the pre-registration was written, and stated in it: one 16-token probe with `num_gpu = 0`, and two harness tests on three other questions (CPU 10.78 and 10.87 tok/s). The band in R1 was set before any of these.

GPU memory in use during the CPU arm stayed at the pre-run level, a second, independent reading that no weights were placed on the GPU.
