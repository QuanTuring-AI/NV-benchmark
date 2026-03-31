# NIM vs Ollama Benchmark on RTX 5090

**First public benchmark of NVIDIA NIM (TensorRT-LLM) vs Ollama on RTX 5090 (Blackwell, sm_120)**

By [QuanTuring Inc.](https://quanturing.ai) — Enterprise AI Middleware | NVIDIA Inception Member

---

## TL;DR

Same GPU. Same model. Only variable: the inference engine.

| Metric | NIM | Ollama | NIM Advantage |
|--------|-----|--------|---------------|
| **Throughput** | 73.8 tok/s | 10.1 tok/s | **7.3x faster** |
| **Time to First Token** | 221 ms | 2,876 ms | **13x faster** |
| **Total Latency** | 4.3 s | 27.7 s | **6.5x faster** |
| **Guardrails Overhead** | +123 ms (+2.1%) | — | Negligible |
| **Adversarial Detection** | 93.3% | — | Zero false positives |

## Why This Matters

Most enterprise AI benchmarks are run on cloud GPUs (A100, H100). But many companies — especially semiconductor, defense, and financial services — need **fully on-premise, air-gapped AI deployment**.

This benchmark answers a practical question: **What can a single workstation GPU do with the right inference engine?**

The answer: an RTX 5090 running NIM delivers near-instant AI responses (0.2s to first token) with enterprise-grade safety guardrails, at negligible overhead.

---

## Hardware & Software

| Component | Specification |
|-----------|--------------|
| GPU | NVIDIA GeForce RTX 5090 (32GB GDDR7, sm_120 Blackwell) |
| NIM | v1.13.1, vLLM engine, BF16 precision |
| Ollama | Latest, llama.cpp engine, Q4 quantized |
| Model | Meta Llama 3.1 8B Instruct |
| Guardrails | NVIDIA NeMo Guardrails 0.21.0 |
| OS | Windows 11 + Docker Desktop + NVIDIA Container Toolkit |

---

## Key Metrics Explained

Before diving into results, here's what each metric measures — these are different things:

```
|← TTFT (Time to First Token) →|←——— Token Generation ———→|
[Waiting.....................][First token...........Last token]
|←——————————— Total Latency (end-to-end) ——————————————————→|
```

| Metric | What it measures | User experience |
|--------|-----------------|-----------------|
| **TTFT** (Time to First Token) | How fast the AI *starts* responding | "It's thinking..." → "It's talking!" |
| **TPS** (Tokens per Second) | How fast tokens stream after the first one | Speed of the text appearing |
| **Total Latency** | Time from question to complete answer | "I got my full answer" |

**Why this matters for reading E2 vs E3:**
- E2 highlights **TTFT** (221ms vs 2,876ms) — the "instant response" feel
- E3 measures Guardrails overhead against **Total Latency** (~5.8s) — because guardrails wrap the entire request, not just the first token
- E3 tests only deep technical questions (longer responses), so its baseline (~5.8s) is higher than E2's average across all categories (~4.3s)

---

## Experiments

### E2: NIM vs Ollama — Inference Speed

**100 questions × 3 rounds × 2 engines = 600 data points**

Questions span 5 categories: factual short answers, explanations, multilingual (EN/ZH/JA), technical (semiconductor/AI), and RAG simulation (with context).

#### Results by Category

| Category | NIM TPS | Ollama TPS | Speedup | NIM TTFT | Ollama TTFT | TTFT Speedup |
|----------|---------|------------|---------|----------|-------------|-------------|
| Factual Short | 63.4 | 9.6 | 6.6x | 225ms | 2,919ms | 13.0x |
| Explanation | 80.8 | 11.4 | 7.1x | 224ms | 2,894ms | 12.9x |
| Multilingual | 79.1 | 9.8 | **8.1x** | 229ms | 2,919ms | 12.7x |
| Technical | 77.0 | 11.2 | 6.9x | 213ms | 2,978ms | **14.0x** |
| RAG Simulation | 68.7 | 8.8 | 7.8x | 214ms | 2,668ms | 12.4x |

**Key finding:** Multilingual (EN/ZH/JA) shows the largest gap at 8.1x — NIM's BF16 full precision outperforms Ollama's Q4 quantization significantly on non-English tokens. This is critical for APAC enterprise deployment.

#### User Experience Translation

```
Ollama:  Wait 2.9s for first token → 28s for full response  (feels "stuck")
NIM:     Wait 0.2s for first token →  4s for full response  (feels "instant")
```

---

### E3: NeMo Guardrails — Safety Without Sacrifice

**45 questions × 3 rounds × 2 modes = 270 data points**

Three question categories: clean passthrough (20), edge cases (10), adversarial inputs (15).

#### Results

| Category | NIM-only Latency | NIM + Guardrails | Overhead | Accuracy |
|----------|-----------------|------------------|----------|----------|
| Clean (tech/semiconductor) | 5,765 ms | 5,888 ms | **+123ms (+2.1%)** | 100% pass |
| Edge (security education) | 5,958 ms | 5,959 ms | **+1ms (~0%)** | 100% pass |
| Adversarial (hacking/malware) | 707 ms | 301 ms | **-406ms (saved)** | 93.3% blocked |

**Key findings:**

1. **+2.1% overhead for safety** — Users cannot perceive 123ms on a 5.8s response
2. **Zero false positives** — No legitimate question was incorrectly blocked
3. **Blocking saves GPU time** — Adversarial requests are caught in 94ms, saving 5.7s of wasted inference per blocked request
4. **93.3% detection with a local 8B model** — No external API needed; fully on-premise safety

#### Architecture

```
User Input
  → [Input Rail] Self-check call (~50ms)
    → Violates policy? → YES → BLOCK (94ms total, no inference)
    → Violates policy? → NO  → NIM inference (~5.8s) → [Output Rail] → Response
```

#### Why NIM Makes Guardrails Viable

Each guardrail check is a minimal LLM call — just 3 tokens ("yes" or "no"). The cost of that call is dominated by TTFT, not token generation.

| Engine | TTFT | Guardrail check cost | Overhead on full response |
|--------|------|---------------------|--------------------------|
| **NIM** | 221 ms | ~50 ms | **+2.1%** (imperceptible) |
| **Ollama** | 2,876 ms | ~3,000 ms | **+21%** (unusable) |

On Ollama, adding two guardrail checks (input + output) would add ~6 seconds to every request — most teams would disable safety to preserve usability.

On NIM, the same two checks add ~100ms. Safety becomes a default, not a luxury.

**NIM's fast TTFT isn't just about user experience — it's what makes enterprise safety features practically free.**

---

## Enterprise Deployment Implications

| Stack | Latency | Safety | Air-Gap Ready |
|-------|---------|--------|--------------|
| Ollama (no guardrails) | ~28s | None | Yes |
| Ollama + Guardrails | ~28.2s | Yes | Yes |
| NIM (no guardrails) | ~4.3s | None | Yes |
| **NIM + Guardrails** | **~4.4s** | **Yes** | **Yes** |

NIM's speed advantage makes guardrails **practically free**. Adding 123ms to a 4.3-second response is imperceptible — but the safety guarantee is real.

---

## Deployment Notes (RTX 5090 Specific)

Lessons learned deploying NIM on the RTX 5090 (Blackwell sm_120):

| Issue | Solution |
|-------|---------|
| NIM latest (2.0.1) requires CUDA 13.0 | Use NIM 1.13.1 (compatible with CUDA 12.9 / driver 577.00) |
| Default max_model_len=131072 exceeds KV cache | Set `NIM_MAX_MODEL_LEN=8192` |
| TensorRT profile stalls on sm_120 | Use `NIM_MODEL_PROFILE` to specify vLLM profile hash |
| `NGC_API_KEY=` with trailing space fails auth | Ensure no whitespace after `=` |
| NeMo Guardrails `is_content_safe` parser inverted | Prompts must ask about policy **violations**, not compliance |

See [DEPLOYMENT_NOTES.md](DEPLOYMENT_NOTES.md) for full details and working configurations.

---

## Upcoming Experiments

| Experiment | Description | Status |
|------------|-------------|--------|
| E2 ✅ | NIM vs Ollama inference benchmark | Complete |
| E3 ✅ | NeMo Guardrails latency overhead | Complete |
| E4 | RAG + NIM + Guardrails full-stack accuracy | Planned |
| E5 | Air-gap mode verification (offline operation) | Planned |
| E6 | Concurrency stress test (1-50 concurrent users) | Planned |

---

## Repository Structure

```
nim-benchmark/
├── README.md
├── LICENSE
├── DEPLOYMENT_NOTES.md
├── requirements.txt
├── docker-compose.yml
├── progress.json
├── scripts/
│   └── check_env.py                # Environment validation
├── benchmark/
│   ├── questions.json              # 100 benchmark questions (E2, 5 categories)
│   ├── e3_questions.json           # 45 guardrails questions (E3, 3 categories)
│   ├── run_benchmark.py            # E2: NIM vs Ollama benchmark script
│   ├── run_e3_guardrails.py        # E3: Guardrails latency benchmark script
│   ├── analyze_e3.py               # E3: Results analyzer
│   ├── guardrails/
│   │   └── config.yml              # NeMo Guardrails configuration
│   ├── results/
│   │   ├── e1_nim_setup.json       # E1 setup validation data
│   │   ├── e2_nim_vs_ollama.json   # Raw E2 data (600 data points)
│   │   ├── e3_guardrails.json      # Raw E3 data (270 data points)
│   │   └── e3_metrics.json         # E3 summary metrics
│   └── report/
│       ├── e2_report.md            # E2 detailed analysis
│       └── e3_report.md            # E3 detailed analysis
```

---

## About QuanTuring

[QuanTuring Inc.](https://quanturing.ai) (量識科技) builds enterprise AI middleware for industries where data sovereignty is non-negotiable. Our stack — Multi-Model LLM Router + Hybrid-Cloud Architecture + NIM-powered on-premise inference — enables semiconductor, financial, and manufacturing companies to deploy AI without any data leaving their premises.

**NVIDIA Inception Program Member** | **Google for Startups Cloud Program Member**

2 US Provisional Patents | 94.4% RAG Accuracy in Production

---

## License

MIT — Feel free to use this benchmark data. If you cite it, a link back to this repo is appreciated.

---

## Contact

- **Allen Chen** — Founder & CEO
- **Email:** allen.chen@quanturing.ai
- **LinkedIn:** [linkedin.com/in/allenjwchen](https://linkedin.com/in/allenjwchen)
- **Website:** [quanturing.ai](https://quanturing.ai)
