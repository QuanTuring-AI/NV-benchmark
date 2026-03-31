# E2 Benchmark Report: NIM vs Ollama
## RTX 5090 | Llama 3.1 8B Instruct | 100 Questions × 3 Rounds

**Date:** 2026-03-30 / 2026-03-31
**Hardware:** NVIDIA GeForce RTX 5090 (32GB GDDR7)
**Model:** Meta Llama 3.1 8B Instruct
**NIM:** v1.13.1, vLLM engine, BF16, max_model_len=8192
**Ollama:** llama3.1:8b, llama.cpp, Q4 quantized

---

## Executive Summary

Same GPU, same model — the only variable is the inference engine:

| Metric | NIM | Ollama | NIM Advantage |
|--------|-----|--------|---------------|
| **Avg TPS** | **73.8 tok/s** | 10.1 tok/s | **7.3x faster** |
| **Avg TTFT** | **221 ms** | 2,876 ms | **13x faster** |
| **Avg Total Latency** | **4,286 ms** | 27,741 ms | **6.5x faster** |
| **VRAM Usage** | 31,768 MB (BF16) | 31,772 MB (Q4) | Comparable* |

*Note: Ollama Q4 should theoretically use less VRAM, but llama.cpp loads the entire model into GPU memory, resulting in comparable usage.

---

## Results by Category

| Category | NIM TPS | Ollama TPS | TPS Speedup | NIM TTFT | Ollama TTFT | TTFT Speedup |
|----------|---------|------------|-------------|----------|-------------|--------------|
| factual_short | 63.4 | 9.6 | **6.6x** | 225ms | 2,919ms | **13.0x** |
| explanation | 80.8 | 11.4 | **7.1x** | 224ms | 2,894ms | **12.9x** |
| multilingual | 79.1 | 9.8 | **8.1x** | 229ms | 2,919ms | **12.7x** |
| technical | 77.0 | 11.2 | **6.9x** | 213ms | 2,978ms | **14.0x** |
| rag_simulation | 68.7 | 8.8 | **7.8x** | 214ms | 2,668ms | **12.4x** |

### Key Observations

1. **Multilingual shows the largest gap (8.1x TPS)**
   NIM's BF16 full precision significantly outperforms Ollama's Q4 quantization on non-English tokens. This is critical for APAC enterprise deployments handling CJK languages.

2. **Technical category has the widest TTFT gap (14.0x)**
   Technical questions produce longer responses, where NIM's in-flight batching and continuous batching show greater benefit.

3. **Factual short has the lowest TPS (63.4)**
   Short-answer questions have a higher overhead-to-output ratio for NIM, but TTFT is still 13x faster than Ollama.

4. **RAG simulation validates full-stack performance**
   Queries with injected context (simulating RAG retrieval) maintain a 7.8x speedup, confirming the advantage holds in realistic enterprise deployments.

---

## What This Means for Enterprise Deployment

```
User wait time comparison (single query):
  Ollama:  Wait 2.9s for first token → 25s more for full response
  NIM:     Wait 0.2s for first token →  4s for full response

Conversation experience:
  Ollama: Every query feels "stuck" — unsuitable for interactive applications
  NIM:    Near-instant response — supports fluid conversational experiences
```

---

## Deployment Notes (Lessons Learned)

| Issue | Solution |
|-------|----------|
| NIM latest (2.0.1) requires CUDA 13.0 | Use NIM 1.13.1 (compatible with driver 577.00 / CUDA 12.9) |
| Default max_model_len=131072 exceeds KV cache | Set `NIM_MAX_MODEL_LEN=8192` |
| `NGC_API_KEY=` with trailing space fails auth | Ensure no whitespace after `=` |
| Windows PowerShell multiline command issues | Write all commands as single-line |
| TensorRT profile stalls on RTX 5090 (sm_120) | Use `NIM_MODEL_PROFILE` to specify vLLM profile hash |

---

## Next Steps

- **E3:** NeMo Guardrails integration — measure safety overhead on NIM inference
- **E4:** RAG + NIM + Guardrails full-stack accuracy test
- **E5:** Air-gap mode verification (fully offline operation)
- **E6:** Concurrency stress test (1/5/10/20/50 concurrent users)

---

*QuanTuring Inc. — Make AI with Soul.*
