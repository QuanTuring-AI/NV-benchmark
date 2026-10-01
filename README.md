<div align="center">

# 7.4× at 128 concurrent requests: what NIM buys you on one RTX 5090

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

Vol.1 as first published (2026-03) is in [`benchmark/`](benchmark/) and [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md). It is kept exactly as published and is not modified. The comparison that led it is closed out, as an account of how it was measured, in [`vol3-judges/BASELINE.md`](vol3-judges/BASELINE.md) §12.

## The series

| Volume | Question | Directory | Status |
|---|---|---|---|
| **Vol.1 (renewed 2026-09)** | Does NIM change one user's speed? Where does serving start to pay? Does answer quality hold? | [`vol1-nim/`](vol1-nim/README.md) | this release |
| **Vol.2** | NIM + Nemotron: two deployment options on 32 GB | [`vol2-nemotron/`](vol2-nemotron/README.md) | data published 2026-09-25; write-up to follow |
| **Vol.3** | Judges in NeMo Guardrails on NIM 2.0.12 | [`vol3-judges/`](vol3-judges/README.md) | baseline data published 2026-09-19; the judge study is in progress |
| Vol.4–5 | NeMo Retriever and Nemotron in a RAG system | not yet created | planned |
| Vol.1 · March 2026 original (archived) | NIM against Ollama, and NeMo Guardrails' latency, as first published | [`benchmark/`](benchmark/) and [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md) | frozen |

*Directories were renamed on 2026-09-28 to match the volume numbers, and again on 2026-09-29 when Vol.2 and Vol.3 swapped places: [`PATH_MAP.md`](PATH_MAP.md) maps every old path, and [`CHANGELOG.md`](CHANGELOG.md) records both changes.*

### Tags

| Tag | Volume | Commit | Note |
|---|---|---|---|
| `vol1-nim-published` | Vol.1 | `3efa794` | rerun Vol.1 here |
| `vol2-nemotron-published` | Vol.2 | `e4f0ec5` | rerun Vol.2 here |
| `vol3-judges-baseline` | Vol.3 | `3efa794` | rerun the Vol.3 baseline here; the judge study has not been published |

Each tag points to the last commit before the renames that holds its volume's runs, so every path in those runs is correct there.

*Earlier tags and every change to this repository: [`CHANGELOG.md`](CHANGELOG.md).*

## Headline results (Vol.1)

Llama 3.1 8B Instruct, one RTX 5090, synthetic chat requests (200 tokens in, 200 out), MLPerf server SLO. Each line links to its table.

- **One user: NIM is the engine it contains.** NIM 2.0.12 and upstream vLLM 0.27.1 ran the same bf16 weights. At temperature 0 they wrote 50 of 50 answers byte-identical, at a generation-rate ratio of 0.990 [0.963, 1.020]. → [`vol1-nim/README.md` §A](vol1-nim/README.md)
- **For one user the 4-bit build is faster; NIM leads from 4 on.** Against the fastest 4-bit configuration we could build with Ollama (16 slots), NIM bf16's total throughput overtakes it between 2 and 4 concurrent requests. → [§D](vol1-nim/README.md) · [`results/p62_levels/`](vol1-nim/results/p62_levels/README.md)
- **At 128 concurrent requests, NIM delivers:**
  - 7.4× the 4-bit build's total throughput with NIM bf16;
  - 11.8× with NIM's own FP8 choice (*FP8 figures are from the 25 September run; a clean-window recheck is pending*);
  - 13.6× at matched 16-bit precision.

  NIM was still inside the server SLO at 128. In the same sweep (1, 8, 16, 32, 64 and 128 concurrent requests) the Ollama configurations were outside it from 8 on. → [`vol1-nim/README.md` §0](vol1-nim/README.md) · [`results/p59_nim_value/`](vol1-nim/results/p59_nim_value/README.md)

  *A clean-window recheck on 27 September reproduced these ratios within 6% (7.7× and 13.7× at 128 concurrent requests); absolute throughput was 3–13% higher in every cell it measured.* → [`results/p70_clean_recheck/`](vol1-nim/results/p70_clean_recheck/README.md)
- **Answer quality.**
  - MMLU (2,850-item sample): every faster configuration is within ±2 pp of NIM bf16.
  - GSM8K: the 4-bit build −2.43 pp [−4.40, −0.53]; NIM FP8 −1.52 pp [−3.11, 0.00]. Both are undetermined against ±2 pp.

  → [§E](vol1-nim/README.md) · [`results/p63_gsm8k/`](vol1-nim/results/p63_gsm8k/README.md)
- **Nemotron (Vol.2).**
  - Fit: both deployment options fit the 32 GB card (22,909 / 25,972 MiB in use at their smallest passing budgets).
  - Speed: the MoE option generates 4.14× faster per token and finishes an answer about 2.9× sooner.
  - Concurrency: on the chat profile it stays inside the server SLO up to 128 concurrent requests (the same ceiling on a gated re-run). The dense option's engine exits under concurrent load: over two nights all 8 of its containers ended with the same error — twice at 16 concurrent requests, five times at 32, once at 64 — while upstream vLLM 0.30.0 on the same weights ran 16, 32 and 64 without an engine exit.

  → [`vol2-nemotron/BASELINE.md`](vol2-nemotron/BASELINE.md) §A–§C
- **Judges (Vol.3).** Baseline data; the judge study is in progress.
  - With Llama 3.1 8B as its own judge, NeMo Guardrails 0.23.0 blocks the same adversarial prompts as 0.21.0 on this set: 42 / 45, with 0 / 90 false blocks.
  - The time it adds per request comes from the judge's answer length: by default 0.23.0 lets the self-check judge answer with up to 1,024 tokens, where 0.21.0 asked for 3.

  → [`vol3-judges/BASELINE.md`](vol3-judges/BASELINE.md) §2, §8

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
2. Verify the hash chain: `python tools/bound_files.py --history` lists every file a pre-registration or sidecar binds and checks each one in the commit where its pre-registration was frozen; it also reports whether the file at today's path is the same blob.
3. Each results directory's README gives its harness, runner and environment variables. The analysers run on the published files alone.
4. To rerun a harness byte for byte, check out its volume's tag (above). Frozen harnesses import each other by the paths they were written with, and those paths exist only at the tag.

## Deployment notes (RTX 5090)

| Topic | Where |
|---|---|
| Pin the profile. On this card NIM 2.0.12 selects its FP8 profile when nothing is set, and for these models it offers vLLM profiles only. | [`vol1-nim/README.md` §B](vol1-nim/README.md) · [`vol2-nemotron/results/p50_availability/`](vol2-nemotron/results/p50_availability/README.md) |
| `VLLM_USE_V2_MODEL_RUNNER=0` on Docker Desktop / WSL2 (the default runner fails with "UVA is not available") | [`vol1-nim/README.md` §B](vol1-nim/README.md) |
| `NIM_MAX_MODEL_LEN=8192` (the default context does not leave room for the KV cache) | [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md) §3 |
| NGC key without a trailing space · PowerShell single-line commands · Windows console encoding (cp950) with multilingual output | [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md) §4–§6 |
| NeMo Guardrails self-check prompts | [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md) (Guardrails section) · [`vol3-judges/BASELINE.md`](vol3-judges/BASELINE.md) §8–§9 |

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
