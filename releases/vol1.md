Forum post: <https://forums.developer.nvidia.com/t/why-nim-llama-3-1-8b-on-one-rtx-5090-from-1-to-128-concurrent-requests/384818>

Llama 3.1 8B Instruct on one RTX 5090 with NIM 2.0.12, from one request at a time up to 128, with Ollama as the reference point.

- **One user: Ollama's 4-bit build is faster** (172–183 vs 87 tok/s), because it reads about 3.3× fewer bytes per token. NIM adds nothing on top of the vLLM it ships with: same weights, same speed, the same 50 answers byte for byte.
- **Once requests overlap, NIM pulls ahead.** The crossover is between 2 and 4 concurrent requests; NIM is 3.5× ahead at 8 and 7.4× at 128 (5,458 vs 741 tok/s).
- **NIM held the MLPerf Inference server latency target up to 128 concurrent requests.** None of the Ollama configurations held it past one.
- **NIM's default on this card is FP8:** another 1.5× over bf16. MMLU showed no measurable change; GSM8K was 1.5 points lower, which we could not separate from zero.

Synthetic chat requests, 200 tokens in / 200 out, closed loop, one engine on the GPU at a time.

**Read:** [Vol.1 README](https://github.com/QuanTuring-AI/NV-benchmark/blob/vol1/vol1-nim/README.md) — results, method, and a claim-to-evidence table for every number.
**Check every number:** `python tools/check_claims.py vol1-nim/README.md`
**Reproduce:** `git checkout vol1`
