# Changelog

Every change to this repository that reached `main`, newest first. Volumes are named by their current numbers throughout; directory and tag names are given as they were at the time. To read the volumes themselves, start from the [README](README.md).

## 2026-09-29 · Vol.2 and Vol.3 swapped; directories renamed again; this changelog

- **Vol.2 and Vol.3 swapped places** so that the reading order is NIM (Vol.1), then Nemotron on NIM (Vol.2), then judges (Vol.3): a reader meets Nemotron before reading about Nemotron as a judge.
- **Directories renamed to match**, as pure moves (1,228 files): `vol3-nemotron/` → [`vol2-nemotron/`](vol2-nemotron/README.md), `vol2-guardrails/` → [`vol3-judges/`](vol3-judges/README.md). Neither new name had been used before. [`PATH_MAP.md`](PATH_MAP.md) follows every path through both renames.
- **Tags** `vol2-nemotron-published` (`e4f0ec5`) and `vol3-judges-baseline` (`3efa794`). This tag marks the baseline data; the judge study has not been published. The two tags pushed on 2026-09-28 for these volumes stay as they were (see the table below).
- **Vol.3** is titled as baseline data. Its Llama judge measurements (the Guardrails version bridge, the self-check `max_tokens` setting, the rails under load) are the baseline for a judge study that is in progress.
- **Vol.1:** its README no longer carries a Guardrails point, and it names no other volume.
- **This changelog** was added, and the README lists only the current tags.

## 2026-09-28 · Directories renamed; clean-window rechecks; Vol.3 additions

- **Directories renamed to match the volume numbers**, as pure moves (1,832 files): `vol1a-revisit/` → `vol1-nim/` (with the NIM-against-vLLM run that sat in `vol2/results/p54_engine/`), `vol1b/` → `vol2-guardrails/`, `vol2/` → `vol3-nemotron/`. [`PATH_MAP.md`](PATH_MAP.md) maps every old path. Files written before the rename, including frozen pre-registrations, keep the paths they were written with; `python tools/bound_files.py --history` checks each binding in the commit where its pre-registration was frozen.
- **Tags** `vol1-nim-published` and `vol2-guardrails-published` (both `3efa794`) and `vol3-nemotron-published` (`e4f0ec5`). Each points to the last commit before the rename that holds its volume's runs, so every path in those runs is correct there.
- **Vol.1:** the 128-request headline re-checked with the GPU otherwise idle, on 27 September. It reproduced the published ratios within 6%. The FP8 arm has no clean-window figure: its calibration gate failed. → [`vol1-nim/results/p70_clean_recheck/`](vol1-nim/results/p70_clean_recheck/README.md)
- **Vol.3:** NeMo Guardrails 0.23.0 under load at 1–128 concurrent requests → [`results/p66_rails_under_load/`](vol3-judges/results/p66_rails_under_load/README.md). The Guardrails server's own limits (worker processes, keep-alive) → [`results/p67_rails_server_config/`](vol3-judges/results/p67_rails_server_config/README.md).
- **Vol.3:** the levels of those two runs that had run with other GPU load, repeated with the GPU idle. The NIM-direct levels reproduced. The server-side levels ran with the host in a different state, so they are recorded but do not replace the earlier numbers. → [`results/p69_clean_rerun/`](vol3-judges/results/p69_clean_rerun/README.md)
- **README:** the headline is stated in concurrent requests; the documents use the volume numbers of that day only.

## 2026-09-27 · Vol.1 (renewed); volume numbers changed

- **Vol.1 (renewed)** published in `vol1a-revisit/`, now [`vol1-nim/`](vol1-nim/README.md). It covers NIM 2.0.12 against the engine it contains, what NIM is worth once several requests run at once, and answer quality (MMLU, GSM8K). Tag `vol1-revisit-published` → `f6b73b2`.
- **Volume numbers changed:** the NeMo Guardrails volume (now Vol.3) was numbered 2 and the Nemotron volume (now Vol.2) was numbered 3, until 2026-09-29. Directory names stayed as they were until 2026-09-28.

## 2026-09-25 · Vol.2 data

- **Vol.2 data:** two Nemotron deployment options on one RTX 5090 (fit, speed, concurrency, long context, NeMo Guardrails), published in `vol2/`, now [`vol2-nemotron/`](vol2-nemotron/README.md). Tag `vol2-published` → `e4f0ec5`. The write-up is to follow.

## 2026-09-19 · Vol.3 baseline data; the March 2026 comparison closed

- **Vol.3 baseline data:** NIM 1.13.1 → 2.0.12 × NeMo Guardrails 0.21.0 → 0.23.0 on one RTX 5090, published in `vol1b/`, now [`vol3-judges/`](vol3-judges/README.md). Tag `vol1b-published` → `40dfce0`.
- **The March 2026 NIM-versus-Ollama comparison** is closed as an account: [`vol3-judges/BASELINE.md`](vol3-judges/BASELINE.md) §12.

## 2026-06-28 · README

- The repository landing page was rewritten.

## 2026-03-31 · Vol.1 first published

- **Vol.1:** NIM against Ollama, and NeMo Guardrails' latency, on one RTX 5090, published on the NVIDIA Developer Forum with its evidence in [`benchmark/`](benchmark/) and [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md). Both are kept exactly as published.

## Tags from earlier pushes

These tags were pushed before the volumes took their current numbers and directories. Their names follow the volume numbers and directory names of their day. They stay on the remote unchanged because links that have already been sent point to them. To rerun a volume, use the current tags in the [README](README.md#tags).

| Tag | Commit | Holds | Pushed |
|---|---|---|---|
| `vol2-guardrails-published` | `3efa794` | Vol.3, in `vol1b/` | 2026-09-28 |
| `vol3-nemotron-published` | `e4f0ec5` | Vol.2, in `vol2/` | 2026-09-28 |
| `vol1-revisit-published` | `f6b73b2` | Vol.1 (renewed), in `vol1a-revisit/` | 2026-09-27 |
| `vol1b-published` | `40dfce0` | Vol.3, in `vol1b/` | 2026-09-19 |
| `vol2-published` | `e4f0ec5` | Vol.2, in `vol2/` | 2026-09-25 |
