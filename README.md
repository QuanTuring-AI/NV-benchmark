<div align="center">

# NIM on one RTX 5090: Llama 3.1 8B and Nemotron 3 Nano, measured

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

## The volumes

**Vol.1 · [Why NIM? Llama 3.1 8B on one RTX 5090, from 1 to 128 concurrent requests](vol1-nim/README.md)**
For one user the 4-bit Ollama build is faster; from 4 concurrent requests on NIM leads, 7.4× at 128, and it holds the MLPerf server latency target the whole way. NIM's FP8 default adds another 1.5×, with no measurable change on MMLU.
→ [`vol1-nim/README.md`](vol1-nim/README.md) · tag `vol1-nim-renewed`

**Vol.2 · [Nemotron 3 Nano on one RTX 5090 with NIM: ~300 tok/s, flat to 120k context, 128 concurrent requests](vol2-nemotron/README.md)**
It fits in 21–25 GiB, generates about 300 tok/s at any context length up to 120k, keeps the server latency target up to 128 concurrent chat requests (8 with long RAG-shaped prompts), and scores 95.7% on GSM8K with reasoning on.
→ [`vol2-nemotron/README.md`](vol2-nemotron/README.md) · tag `vol2-nemotron-published`

**Vol.3 · [Judges in NeMo Guardrails on NIM 2.0.12](vol3-judges/README.md)** (baseline data; the judge study is in progress)
With Llama 3.1 8B as its own judge, NeMo Guardrails 0.23.0 blocks the same adversarial prompts as 0.21.0 on this set (42 / 45, with 0 / 90 false blocks); the time it adds comes from the judge's answer length.
→ [`vol3-judges/BASELINE.md`](vol3-judges/BASELINE.md) §2, §8 · tag `vol3-judges-baseline`

**Vol.1 · March 2026 original (archived)** is in [`benchmark/`](benchmark/) and [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md), frozen as published. Vol.4–5 (NeMo Retriever and Nemotron in a RAG system) are planned.

Each volume's README has the same shape: the headline and a run command first, then a **claim → evidence** table (every number, its file, its key), how it was measured, and the measurement conditions including what we could not explain.

*Directories were renamed on 2026-09-28 to match the volume numbers, and again on 2026-09-29 when Vol.2 and Vol.3 swapped places: [`PATH_MAP.md`](PATH_MAP.md) maps every old path, and [`CHANGELOG.md`](CHANGELOG.md) records both changes.*

## How to check a number

1. **Open the tag** of the article you are reading (table below), on GitHub or with `git checkout <tag>`.
2. **Find the number** in that volume's README, in the *Claim → evidence* table. Each row gives a file and a key.
3. **Open the file and follow the key.** The files are JSON; a key such as `levels.N-BF16|C|main.128.total_tps` is a path through it. The stored value should round to the number in the article.
4. **Recompute it if you want to.** Each result directory's README names the analysis script that produced its `analysis.json` from the raw rows; the scripts run on the published files alone.
5. **Check that nothing was edited after the fact.** `python tools/bound_files.py --history` lists every file a pre-registration binds by SHA-256 and verifies it.

### Tags

| Tag | Which article it is for | What you see when you open it |
|---|---|---|
| `vol1-nim-renewed` | Vol.1, *Why NIM?* | Every Vol.1 run, the 29 September FP8 recheck, and the READMEs with their claim → evidence tables. It points to the commit that adds this row. |
| `vol2-nemotron-published` | Vol.2, *Nemotron 3 Nano on one RTX 5090* | Every Vol.2 run through 1 October (commit `6af6168`). Its READMEs are the version before the claim → evidence tables were added; the tables are on `main` and in `vol1-nim-renewed`. |
| `vol3-judges-baseline` | Vol.3 baseline data | The Vol.3 runs at the paths their harnesses were written with (commit `3efa794`, the last one before the directory renames). The judge study has not been published. |
| `vol1-nim-published` | Vol.1, to rerun a harness byte for byte | The Vol.1 runs at the paths their harnesses were written with (commit `3efa794`, before the renames). It does not contain the FP8 recheck. |

**Earlier tags.** These were pushed before the volumes took their current numbers and directory names. They are kept so that links already sent keep working; nothing new points to them.

| Tag | Commit | What it holds |
|---|---|---|
| `vol2-guardrails-published` | `3efa794` | Vol.3, in `vol1b/` |
| `vol3-nemotron-published` | `e4f0ec5` | Vol.2, in `vol2/` |
| `vol1-revisit-published` | `f6b73b2` | Vol.1 (renewed), in `vol1a-revisit/` |
| `vol2-published` | `e4f0ec5` | Vol.2, in `vol2/` |
| `vol1b-published` | `40dfce0` | Vol.3, in `vol1b/` |

*Every change to this repository: [`CHANGELOG.md`](CHANGELOG.md).*

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
4. To rerun a harness byte for byte, check out a tag that holds it at the paths it was written with (`vol1-nim-published`, `vol3-judges-baseline`, or the earlier tags above); at later tags, [`PATH_MAP.md`](PATH_MAP.md) gives the mapping. Frozen harnesses import each other by the paths they were written with, and those paths exist only at those tags.

## Deployment notes (RTX 5090)

| Topic | Where |
|---|---|
| Pin the profile. On this card NIM 2.0.12 selects its FP8 profile when nothing is set, and for these models it offers vLLM profiles only. | [`vol1-nim/README.md` §B](vol1-nim/README.md) · [`vol2-nemotron/results/p50_availability/`](vol2-nemotron/results/p50_availability/README.md) |
| `VLLM_USE_V2_MODEL_RUNNER=0` for the Llama 3.1 8B image on Docker Desktop / WSL2 (its default runner fails with "UVA is not available"). The Nemotron 3 Nano image started without it. | [`vol1-nim/README.md` §B](vol1-nim/README.md) · [`vol2-nemotron/README.md`](vol2-nemotron/README.md) (claim → evidence, *Run it* rows) |
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
