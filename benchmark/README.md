# Vol.1 — Evidence Index

> **This README is an index added in September 2026. It is not part of the March 2026 publication.** Adding it did not modify any other file in this directory.
>
> **Vol.1: NIM vs Ollama on RTX 5090**, published 2026-03-31 on the [NVIDIA Developer Forum (thread 365275)](https://forums.developer.nvidia.com/t/nim-vs-ollama-on-rtx-5090-7-3x-faster-inference-nemo-guardrails-at-2-1-overhead-870-data-points/365275).
> The files in this directory are the published evidence. **They are kept exactly as published and their paths do not change.**
> This README only indexes them. Vol.2 lives in [`../vol2/`](../vol2/); the series map is in [`../SERIES.md`](../SERIES.md).

---

## File → experiment

| Experiment | What it measures | Harness | Input | Result |
|---|---|---|---|---|
| **E1** · setup | NIM container bring-up on RTX 5090: image, profile, VRAM, first inference | — (recorded once) | — | `results/e1_nim_setup.json` |
| **E2** · NIM vs Ollama | TTFT, throughput and total latency, same model, same GPU | `run_benchmark.py` | `questions.json` | `results/e2_nim_vs_ollama.json` |
| **E3** · NeMo Guardrails | Latency with and without input + output self-check rails; block / pass-through per category | `run_e3_guardrails.py` · rail config `guardrails/config.yml` | `e3_questions.json` | `results/e3_guardrails.json` (raw) · `results/e3_metrics.json` (summary) · `analyze_e3.py` |

Written analysis: `report/e2_report.md`, `report/e3_report.md`.

---

## Configuration as recorded in the files

| Item | Value | Source |
|---|---|---|
| GPU | NVIDIA GeForce RTX 5090 · 32,607 MB | `results/e1_nim_setup.json` |
| Driver / CUDA | 577.00 / 12.9 | `results/e1_nim_setup.json` |
| NIM image | `nvcr.io/nim/meta/llama-3.1-8b-instruct:1.13.1` | `results/e1_nim_setup.json` |
| NIM profile · engine · precision | `vllm-bf16-tp1-pp1` · vLLM · BF16 | `results/e1_nim_setup.json` |
| `max_model_len` | 8192 | `results/e1_nim_setup.json` |
| Ollama model | `llama3.1:8b` (Q4, llama.cpp) · Ollama version not recorded | `results/e1_nim_setup.json` · `results/e2_nim_vs_ollama.json` → `metadata` |
| NeMo Guardrails | 0.21.0 | `results/e3_guardrails.json` → `metadata` |
| Request settings | `max_tokens=500` · streaming · 3 rounds · 2 s cooldown | `run_benchmark.py`, `run_e3_guardrails.py` |
| Temperature | E2: not set (server default) · E3: `0.0` (harness and rail config) | `run_benchmark.py` · `run_e3_guardrails.py`, `guardrails/config.yml` |
| E2 window | 2026-03-30T23:11:53 → 2026-03-31T01:45:18 | `results/e2_nim_vs_ollama.json` → `metadata` |
| E3 window | 2026-03-31T09:08:24 → 09:35:50 | `results/e3_guardrails.json` → `metadata` |

Image digests were not recorded in Vol.1. Vol.2 records both digests for every image.

---

## Data-point ledger

| Source | Count |
|---|---:|
| E2 · 100 questions × 3 rounds × 2 engines | 600 |
| E3 · 45 questions × 3 rounds × 2 modes | 270 |
| **Total** | **870** |

Question sets:

| File | Questions | Categories |
|---|---:|---|
| `questions.json` | 100 | factual_short 20 · explanation 20 · multilingual 20 · technical 20 · rag_simulation 20 |
| `e3_questions.json` | 45 | clean_passthrough 20 · adversarial_input 15 · edge_case 10 |

SHA-256: `questions.json` `262f2339d55ec6b855f7b0180704bd225fdbc561ea37f902b99e1ab405add1f9` · `e3_questions.json` `5d7eeeaa9408977e28366e7b31a6f01905695a0c8ce10a6c314fa40de4a1c3ea`. Vol.2 reuses both files byte for byte.

---

## How the numbers are computed (read before quoting)

- **Statistic.** Every Vol.1 headline number is an **average (avg)**, not a median. Vol.2 reports both, so the two volumes' figures are not interchangeable unless the statistic matches.
- **Throughput unit.** The harness adds `len(delta.split())` for each streamed delta and divides by total request time. The unit is **non-whitespace streamed fragments per second, ≈ tokens per second**. It is not a tokenizer count.
- **TTFT.** NIM: time from sending the request to the first SSE `data:` line (which may carry only the role, not text). Ollama: time to the first chunk with non-empty content. The two endpoints stream different formats, so the harness uses a different first-event rule for each.
- **Guardrails overhead.** The report's **+123 ms (+2.1%, NeMo Guardrails 0.21.0, Llama 3.1 8B on NIM 1.13.1)** is the `clean_passthrough` category: average latency with rails vs without, 20 questions × 3 rounds, all passed (`report/e3_report.md`, category table). `results/e3_metrics.json` also holds an all-categories aggregate that includes blocked requests, whose latency is very short. **The two are different quantities and must not be quoted interchangeably.**

---

## Files outside this directory from the Vol.1 period

| File | Note |
|---|---|
| [`../DEPLOYMENT_NOTES.md`](../DEPLOYMENT_NOTES.md) | Linked from the published post. **Path is fixed at the repo root.** |
| `../scripts/check_env.py` | Environment check: GPU, CUDA, Docker, Python packages |
| `../requirements.txt` | Python dependencies. Includes packages for experiments that were planned but not run (see [`../ROADMAP_STATUS.md`](../ROADMAP_STATUS.md)) |
| `../docker-compose.yml` | Uses the `:latest` tag and a different profile variable. **It does not reproduce the Vol.1 configuration above.** Use the `docker run` commands in `DEPLOYMENT_NOTES.md` |
| `../progress.json` | Experiment progress log written during the Vol.1 runs |

---

## What Vol.1 listed as next

E4–E6 were listed as planned in the published post. Their current status is in [`../ROADMAP_STATUS.md`](../ROADMAP_STATUS.md). The published text is not edited.
