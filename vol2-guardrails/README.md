# Vol.2 (formerly Vol.1-B; directory `vol2-guardrails/`) · NeMo Guardrails 0.23.0 on NIM 2.0.12: the same verdicts, a 16× cheaper judge with one line
*Upgrading the rails cost about 1.5 s per request by default; the detection did not change; one config line takes the cost back. The old ratio is closed as an account, not a claim.*
The measurements, their boundaries and their results are in [`BASELINE.md`](BASELINE.md). Harnesses are in `scripts/`, results in `results/`.

## Internal identifiers

Identifiers made of `P` and two digits (e.g. `P17`, `P20`, `P28`) are internal work-order codes. They appear in script and directory names, docstrings, pre-registrations and result files.
**No public document corresponds to any of them.** They are kept, rather than renamed, because the frozen pre-registrations bind these scripts and inputs by SHA-256, and changing one character would break that binding. Read them as opaque provenance markers — nothing in this repository depends on knowing what they point to.
`P1`–`P4` (one digit) inside an analysis are precondition labels, not work-order codes.
