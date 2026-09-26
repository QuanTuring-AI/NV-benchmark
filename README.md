<div align="center">

# 7.4× at 128 concurrent users: what NIM buys you on one RTX 5090

### QuanTuring · NV-benchmark · Llama 3.1 8B and Nemotron on a single RTX 5090 (Blackwell, sm_120)

[![NVIDIA Inception](https://img.shields.io/badge/NVIDIA-Inception%20Member-76B900?logo=nvidia&logoColor=white)](https://www.nvidia.com/en-us/startups/)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA-NIM%202.0.12-76B900?logo=nvidia&logoColor=white)](#)
[![GPU](https://img.shields.io/badge/GPU-RTX%205090%20Blackwell-76B900)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Part of [QuanCog](https://quanturing.ai) — QuanTuring's audit-grade cognitive layer for Physical AI.**

</div>

---

## What this repository is

Measurements of NVIDIA's inference stack on one workstation GPU. The stack covers NIM, NeMo Guardrails and Nemotron. Each volume follows the same method:
- Every measurement is pre-registered before its first container: predictions and rules in a file whose SHA-256 is fixed before the run.
- Container images are recorded by digest.
- Each arm passes a health gate: an engine that runs from system memory instead of the GPU is caught before any comparison.
- Every "no difference" carries a positive control.
- Every analysis recomputes byte for byte from the published files.

Every number that leaves this repository is quoted with its measurement boundary: model, versions, precision, concurrency, input shape and statistic.

Vol.1 as first published (2026-03) is in [`benchmark/`](benchmark/) and [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md). It is kept exactly as published and is not modified. The comparison that led it is closed out, as an account of how it was measured, in [`vol1b/BASELINE.md`](vol1b/BASELINE.md) §12.

## The series

| Volume | Formerly | Question | Directory | Status |
|---|---|---|---|---|
| **Vol.1 (renewed 2026-09)** | Vol.1-A, re-measured and merged | Does NIM change one user's speed? Where does serving start to pay? Does answer quality hold? | [`vol1a-revisit/`](vol1a-revisit/README.md) (first edition: [`benchmark/`](benchmark/), frozen) | this release |
| **Vol.2** | Vol.1-B | NeMo Guardrails 0.23.0 on NIM 2.0.12: what the upgrade costs and how to take it back | [`vol1b/`](vol1b/README.md) | data published 2026-09-19 |
| **Vol.3** | Vol.2 | Two Nemotron deployment options on 32 GB | [`vol2/`](vol2/README.md) | data published 2026-09-25; write-up to follow |
| Vol.4–5 | — | NeMo Retriever and Nemotron as judge in a RAG system | not yet created | planned |

*We renumber volumes, not directories. Directory names predate the renumbering of 2026-09-27 and are kept as they are: pre-registrations bind file paths by SHA-256, and renaming would break those chains.*

## Headline results (Vol.1)

Llama 3.1 8B Instruct, one RTX 5090, synthetic chat requests (200 tokens in, 200 out), MLPerf server SLO. Each line links to its table.

- **One user: NIM is the engine it contains.** NIM 2.0.12 and upstream vLLM 0.27.1 ran the same bf16 weights. At temperature 0 they wrote 50 of 50 answers byte-identical, at a generation-rate ratio of 0.990 [0.963, 1.020]. → [`vol1a-revisit/README.md` §A](vol1a-revisit/README.md)
- **For one user the 4-bit build is faster; NIM leads from 4 on.** Against the fastest 4-bit configuration we could build with Ollama (16 slots), NIM bf16's total throughput overtakes it between 2 and 4 concurrent requests. → [§D](vol1a-revisit/README.md) · [`results/p62_levels/`](vol1a-revisit/results/p62_levels/README.md)
- **At 128 concurrent requests, NIM delivers:**
  - 7.4× the 4-bit build's total throughput with NIM bf16;
  - 11.8× with NIM's own FP8 choice;
  - 13.6× at matched 16-bit precision.

  NIM was still inside the server SLO at 128. In the same sweep (1, 8, 16, 32, 64 and 128 concurrent requests) the Ollama configurations were outside it from 8 on. → [`vol1a-revisit/README.md` §0](vol1a-revisit/README.md) · [`results/p59_nim_value/`](vol1a-revisit/results/p59_nim_value/README.md)
- **Answer quality.**
  - MMLU (2,850-item sample): every faster configuration is within ±2 pp of NIM bf16.
  - GSM8K: the 4-bit build −2.43 pp [−4.40, −0.53]; NIM FP8 −1.52 pp [−3.11, 0.00]. Both are undetermined against ±2 pp.

  → [§E](vol1a-revisit/README.md) · [`results/p63_gsm8k/`](vol1a-revisit/results/p63_gsm8k/README.md)
- **Guardrails (Vol.2).**
  - NeMo Guardrails 0.23.0 detects the same attacks as 0.21.0: 42 / 45, with 0 / 90 false blocks.
  - It costs +1,515 ms per request by default.
  - One config line (`max_tokens: 3` on the self-check) brings each judge call from a median 970 ms to 60 ms, and the two judges' verdicts agree on 115 / 115 texts.

  → [`vol1b/BASELINE.md`](vol1b/BASELINE.md) §2, §8, §9
- **Nemotron (Vol.3).**
  - Fit: both deployment options fit the 32 GB card (22,909 / 25,972 MiB in use at their smallest passing budgets).
  - Speed: the MoE option generates 4.14× faster per token and finishes an answer about 2.9× sooner.
  - Concurrency: on the chat profile it stays inside the server SLO up to 128 concurrent requests, where the dense option's engine crashes at 32.

  → [`vol2/BASELINE.md`](vol2/BASELINE.md) §A–§C

## How to read a number here

- **A ratio is a function of concurrency, not a property of an engine.** Every ratio is quoted with four things: the concurrency, the precision of both arms, the input shape, and whether the SLO held.
- **SLOs** are MLPerf Inference v5.1's for Llama 3.1-8B:
  - server: p99 time to first token ≤ 2 s and p99 time per output token ≤ 100 ms;
  - interactive: 500 ms and 30 ms.
- **Arm health.** The decode rate × the bytes read per token must reach at least 40% of the card's memory bandwidth, or the arm is excluded from every comparison.
- **Pre-registration.** Predictions are written and frozen before the first container. A failed prediction is reported as failed.
- **Null is an answer.** A result whose gate did not pass is `null`, with its reason.

## Reproduce

1. Clone with `git -c core.autocrlf=false clone …`. SHA-bound files are stored byte for byte (`.gitattributes`).
2. Verify the hash chain: `python tools/bound_files.py` lists every file a pre-registration or sidecar binds, and whether each one matches.
3. Each results directory's README gives its harness, runner and environment variables. The analysers run on the published files alone.

## Deployment notes (RTX 5090)

| Topic | Where |
|---|---|
| Pin the profile. On this card NIM 2.0.12 selects its FP8 profile when nothing is set, and for these models it offers vLLM profiles only. | [`vol1a-revisit/README.md` §B](vol1a-revisit/README.md) · [`vol2/results/p50_availability/`](vol2/results/p50_availability/README.md) |
| `VLLM_USE_V2_MODEL_RUNNER=0` on Docker Desktop / WSL2 (the default runner fails with "UVA is not available") | [`vol1a-revisit/README.md` §B](vol1a-revisit/README.md) |
| `NIM_MAX_MODEL_LEN=8192` (the default context does not leave room for the KV cache) | [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md) §3 |
| NGC key without a trailing space · PowerShell single-line commands · Windows console encoding (cp950) with multilingual output | [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md) §4–§6 |
| NeMo Guardrails self-check prompts | [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md) (Guardrails section) · [`vol1b/BASELINE.md`](vol1b/BASELINE.md) §8–§9 |

`DEPLOYMENT_NOTES.md` records the stack of March 2026 and is kept as published. The current stack is NIM 2.0.12 on driver 591.86.

## Publications

- NVIDIA Developer Forum · [Vol.1 thread (2026-03; revised 2026-09)](https://forums.developer.nvidia.com/t/365275)
<!-- website link: to be added on publication -->

## About QuanTuring

[QuanTuring Inc.](https://quanturing.ai) (量識科技) builds **QuanCog — an audit-grade cognitive layer for Physical AI**. It grounds every answer in an enterprise's own data, cites the source line by line, and governs high-stakes decisions. It deploys in the cloud or fully on-premise and air-gapped, for industries where data sovereignty is non-negotiable: semiconductor, finance and manufacturing.

**NVIDIA Inception Program Member** · **Microsoft for Startups** · **AWS Activate** · **Google for Startups**

## License · Citation

MIT. If you use these measurements, please link back to this repository and name the volume and results directory you quote.

**Contact:** Allen Chen, Founder & CEO · <allen.chen@quanturing.ai> · [quanturing.ai](https://quanturing.ai)
