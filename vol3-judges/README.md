# Vol.3 · Judges in NeMo Guardrails on NIM 2.0.12 — baseline data; the judge study is in progress
*The data here is the baseline for the judge study: Llama 3.1 8B judging its own answers through NeMo Guardrails 0.21.0 and 0.23.0, the self-check `max_tokens` setting, and the rails under load. The study itself (judge quality against latency) has not been published.*

> **Reproduce:** `git checkout vol3`. The harnesses here are frozen with the paths they were written with; [`../PATH_MAP.md`](../PATH_MAP.md) maps them to this directory and gives the commit at which those paths exist, for a byte-for-byte rerun.
The measurements, their boundaries and their results are in [`BASELINE.md`](BASELINE.md). Harnesses are in `scripts/`, results in `results/`.

## Internal identifiers

Identifiers made of `P` and two digits (e.g. `P17`, `P20`, `P28`) are internal work-order codes. They appear in script and directory names, docstrings, pre-registrations and result files.
**No public document corresponds to any of them.** They are kept, rather than renamed, because the frozen pre-registrations bind these scripts and inputs by SHA-256, and changing one character would break that binding. Read them as opaque provenance markers — nothing in this repository depends on knowing what they point to.
`P1`–`P4` (one digit) inside an analysis are precondition labels, not work-order codes.
