# NV-benchmark series map · last updated 2026-09-13

Measurements of NVIDIA inference-stack components (NIM, NeMo Guardrails, Nemotron) on a single RTX 5090 workstation GPU, published as numbered volumes.
This file lists where each volume's evidence lives and which NVIDIA component each experiment exercises.

---

## Volumes

| Volume | Status | Evidence directory | Index |
|---|---|---|---|
| **Vol.1** · NIM vs Ollama on RTX 5090 | Published 2026-03-31 · [forum thread 365275](https://forums.developer.nvidia.com/t/nim-vs-ollama-on-rtx-5090-7-3x-faster-inference-nemo-guardrails-at-2-1-overhead-870-data-points/365275) | [`benchmark/`](benchmark/) | [`benchmark/README.md`](benchmark/README.md) |
| **Vol.2** | Not yet published · evidence being assembled | [`vol2/`](vol2/) | [`vol2/README.md`](vol2/README.md) |
| Follow-ups to Vol.1's planned E4–E6 | See [`ROADMAP_STATUS.md`](ROADMAP_STATUS.md) | [`roadmap-e456/`](roadmap-e456/) | — |

---

## NVIDIA components × experiments

`●` = the component is what the experiment measures · `○` = the component is used, but the experiment measures something else

| Experiment | Vol. | NIM | NeMo Guardrails | Nemotron | Other (not NVIDIA) |
|---|---|:-:|:-:|:-:|---|
| E1 · NIM bring-up | 1 | ● 1.13.1 · Llama 3.1 8B | | | |
| E2 · NIM vs Ollama | 1 | ● 1.13.1 · Llama 3.1 8B | | | Ollama `llama3.1:8b` (baseline) |
| E3 · Guardrails overhead | 1 | ○ 1.13.1 · Llama 3.1 8B | ● 0.21.0 | | |
| E7 arm P · Vol.1 stack re-measured | 2 | ● 1.13.1 · Llama 3.1 8B | | | |
| E7 arm A1 | 2 | ● | | ● Nemotron Nano 9B v2 | |
| E7 arm A2 | 2 | ● | | ● Nemotron 3 Nano | |
| C · co-residence | 2 | ● 1.13.1 · Llama 3.1 8B | | | Ollama `llama3.1:8b` (co-resident) |
| E8 · reranker on SciFact | 2 | | | | `all-MiniLM-L6-v2` + `bge-reranker-v2-m3` |
| E9 · Guardrails overhead | 2 | ○ | ● 0.23.0 | ○ Nemotron Nano 9B v2 | |
| S6 · self-check judge behaviour | 2 | ○ | ● 0.21.0 → 0.23.0 | ○ Nemotron Nano 9B v2 | |

Exact images, digests and profiles are in each experiment's result file (`measurement_label`), not here.
E8 uses no NVIDIA component. It is listed because it belongs to Vol.2's evidence.

---

## Layout conventions

```
NV-benchmark/
├── README.md             # repository landing page
├── SERIES.md             # this file
├── ROADMAP_STATUS.md     # what happened to Vol.1's planned experiments
├── DEPLOYMENT_NOTES.md   # 🔒 fixed path — linked from the published Vol.1 post
├── LICENSE
├── requirements.txt · docker-compose.yml · progress.json · scripts/   # Vol.1-period files
├── benchmark/            # 🔒 Vol.1 evidence — fixed path, published content unchanged
├── roadmap-e456/         # Follow-up experiments for Vol.1's planned E4–E6
└── vol2/                 # Vol.2 evidence
    ├── README.md         # index: file → experiment · measurement boundary · data-point ledger
    ├── data/             # pointers to question sets (not copies)
    ├── scripts/          # harness
    └── results/          # result JSON, pre-registrations, window logs
```

Rules for adding to this repo:

1. **A new volume gets a new top-level directory** (`vol3/`, …) with the same four parts as `vol2/`. Earlier volumes are never moved.
   **Exception: follow-ups to a published volume's stated plans get their own directory named after that plan** (today: `roadmap-e456/` for Vol.1's E4–E6). They complete an earlier volume's commitments rather than start a new volume, so filing them under a later volume would blur which volume the evidence belongs to.
2. **Paths linked from anything published are fixed.** Today these are `DEPLOYMENT_NOTES.md` and `benchmark/`.
3. **Published files are not edited.** Corrections and later status go in a new, dated file (for example `ROADMAP_STATUS.md` or a volume README's correction record).
4. **Question sets are reused by reference, not copied.** Record their SHA-256 in the volume index.
