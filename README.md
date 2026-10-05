<div align="center">

# NVIDIA's inference stack on one RTX 5090, measured

### QuanTuring · NV-benchmark · Pre-registered measurements of NIM, Nemotron and NeMo Guardrails on a single RTX 5090 (Blackwell, sm_120), one volume at a time

[![NVIDIA Inception](https://img.shields.io/badge/NVIDIA-Inception%20Member-76B900?logo=nvidia&logoColor=white)](https://www.nvidia.com/en-us/startups/)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA-NIM%202.0.12-76B900?logo=nvidia&logoColor=white)](#)
[![GPU](https://img.shields.io/badge/GPU-RTX%205090%20Blackwell-76B900)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Part of [QuanCog](https://quanturing.ai) — QuanTuring's audit-grade cognitive layer for Physical AI.**

</div>

---

## Volumes

| Volume | Topic | Page | Release |
|---|---|---|---|
| **Vol.1** | **NIM for LLMs.** Why NIM? Llama 3.1 8B on one RTX 5090, 1 to 128 concurrent requests | [`vol1-nim/README.md`](vol1-nim/README.md) | [Releases → `vol1`](https://github.com/QuanTuring-AI/NV-benchmark/releases/tag/vol1) |
| **Vol.2** | **Nemotron on NIM.** Nemotron 3 Nano on one RTX 5090 with NIM | [`vol2-nemotron/README.md`](vol2-nemotron/README.md) | [Releases → `vol2`](https://github.com/QuanTuring-AI/NV-benchmark/releases/tag/vol2) |
| **Vol.3** | **Judges in NeMo Guardrails on NIM.** Baseline data published; the judge study (verdict quality against latency) is in progress | [`vol3-judges/README.md`](vol3-judges/README.md) | at publication |
| **Vol.4** | **NeMo Retriever.** Embedding and reranking NIMs on one card (planned) | — | — |
| **Vol.5** | **The NVIDIA RAG Blueprint on one card.** The whole pipeline end to end (planned) | — | — |

Each volume's page opens with its headline and a run command, then gives a **claim → evidence** table (every number, its file, its key), how it was measured, and the measurement conditions including what we could not explain. The March 2026 original of Vol.1 is archived in [`benchmark/`](benchmark/) and [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md), frozen as published.

## What this repository is

Measurements of NVIDIA's inference stack on one workstation GPU. So far the stack covers NIM, Nemotron and NeMo Guardrails; NeMo Retriever and the RAG Blueprint come next. Each volume follows the same method:
- Every measurement is pre-registered before its first container: predictions and rules in a file whose SHA-256 is fixed before the run.
- Container images are recorded by digest.
- Each arm passes a health gate: an engine that runs from system memory instead of the GPU is caught before any comparison.
- Every "no difference" carries a positive control.
- Every analysis recomputes byte for byte from the published files.

Every number that leaves this repository is quoted with its measurement boundary: model, versions, precision, concurrency, input shape and statistic.

Vol.1 as first published (2026-03) is in [`benchmark/`](benchmark/) and [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md). It is kept exactly as published and is not modified. The comparison that led it is closed out, as an account of how it was measured, in [`vol3-judges/BASELINE.md`](vol3-judges/BASELINE.md) §12.

## How to check a number

1. **Open the tag** of the article you are reading (table below), on GitHub or with `git checkout <tag>`.
2. **Find the number** in that volume's README, in the *Claim → evidence* table. Each row gives a file and a key.
3. **Open the file and follow the key.** The files are JSON; a key such as `levels.N-BF16|C|main.128.total_tps` is a path through it. The stored value should round to the number in the article.
4. **Recompute it if you want to.** Each result directory's README names the analysis script that produced its `analysis.json` from the raw rows; the scripts run on the published files alone.
5. **Or check every row at once:** `python tools/check_claims.py vol1-nim/README.md vol2-nemotron/README.md` reads each table, opens each file and compares each key; it exits non-zero if any row does not match.
6. **Check that nothing was edited after the fact.** `python tools/bound_files.py --history` lists every file a pre-registration binds by SHA-256 and verifies it.

### Tags

| Tag | What it is |
|---|---|
| `vol1` | Vol.1, *Why NIM?* — the repository as the article describes it |
| `vol2` | Vol.2, *Nemotron 3 Nano on one RTX 5090* — the repository as the article describes it |
| `vol3` | Vol.3 baseline data (NIM × NeMo Guardrails). The judge study is not yet published; this tag moves once, on the day it is |
| `chronicle` | The chronicle of this repository's tags, [`CHRONICLE.md`](CHRONICLE.md): every earlier tag, its full hash and what it held |

A tag opens the whole repository as it was at one commit; all four point to the same one. Earlier tags were retired on 2026-10-01 and are listed in [`CHRONICLE.md`](CHRONICLE.md).

*Directories were renamed on 2026-09-28 and 2026-09-29: [`PATH_MAP.md`](PATH_MAP.md) maps every old path. Every change to this repository: [`CHANGELOG.md`](CHANGELOG.md).*

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
4. To rerun a harness byte for byte at the paths it was written with, check out the commit that [`PATH_MAP.md`](PATH_MAP.md) gives for its volume (a full hash). Frozen harnesses import each other by the paths they were written with, and those paths exist only at those commits; at the current tags, `PATH_MAP.md` gives the mapping.

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

- NVIDIA Developer Forum · [Vol.1 thread (2026-10)](https://forums.developer.nvidia.com/t/why-nim-llama-3-1-8b-on-one-rtx-5090-from-1-to-128-concurrent-requests/384818)
- NVIDIA Developer Forum · [Vol.2 thread (2026-10)](https://forums.developer.nvidia.com/t/nemotron-3-nano-on-one-rtx-5090-with-nim-300-tok-s-flat-to-120k-context-128-concurrent-requests/384859)
- NVIDIA Developer Forum · [March 2026 thread (superseded; see its reply #2)](https://forums.developer.nvidia.com/t/365275)
<!-- website link: to be added on publication -->

## About QuanTuring

[QuanTuring Inc.](https://quanturing.ai) (量識科技) builds **QuanCog — an audit-grade cognitive layer for Physical AI**. It grounds every answer in an enterprise's own data, cites the source line by line, and governs high-stakes decisions. It deploys in the cloud or fully on-premise and air-gapped, for industries where data sovereignty is non-negotiable: semiconductor, finance and manufacturing.

**NVIDIA Inception Program Member** · **Microsoft for Startups** · **AWS Activate** · **Google for Startups**

## License · Citation

MIT. If you use these measurements, please link back to this repository and name the volume and results directory you quote.

**Contact:** Allen Chen, Founder & CEO · <allen.chen@quanturing.ai> · [quanturing.ai](https://quanturing.ai)
