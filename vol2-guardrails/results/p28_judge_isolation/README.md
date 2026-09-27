# Vol.1-B · judge isolation (P28) — what is here

The same stored answer texts judged by two output judges that differ in one line of the rails config: **J1024** (the cell ④
config; `max_tokens` unset, so the library default 1024 applies) and **J3** (the same file plus `max_tokens: 3` on the two
self-check prompt entries). No answer is generated. The result is written up in `vol1b/BASELINE.md` §9.

| File | What it is |
|---|---|
| `prediction_p28_v2.json` + `.sha256` | the pre-registration this run was made under |
| `prediction_p28.json` + `.sha256` | v1, superseded before any judgement was made — see `PREDICTION_V1_SUPERSEDED.md` |
| `judgements.jsonl` | one line per text: two controls and 115 corpus texts, three calls per judge. Answer text and judge text are not published — see `judgements_deidentification.json`, which also gives the rules to recompute every published number from this file |
| `analysis.json` | the pre-registered analysis, reproduced byte for byte from the published `judgements.jsonl` |
| `excluded_segments.json` | source rows that could not be judged again as themselves, with the reason for each (bound by both pre-registrations, unmodified) |
| `reconciliation.json` | how the source run's 408 rows divide: 316 covered by the corpus + 89 excluded + 3 warm-up rows = 408 |
| `corpus.sha256` | digest of the input corpus; the corpus itself holds full model answers and is not published |
| `meta.json` · `ctx_*.txt` · `idle_baseline.txt` · `memory_clamp_line.txt` · `metrics_at_ready.txt` · `gr_config_*/config.yml` | run boundary: stack, GPU context, NIM's memory setting and KV size at READY, the two rails configs actually used |
| `START_ATTEMPT_1_FAILED.md` · `start_attempt_*/` · `start_gate.txt` | the eighteen start attempts before the run; each failed or was withheld because the v1 pre-registration held the wrong profile value (see the correction at the top of the first two) |

## What the corpus can and cannot show

Of the 115 segments, 15 derive from adversarial questions. Both judges refused **one** of them and passed the other 14.
**Exactly one segment in the corpus is text both judges refused** (`1b93baff1b4e`, 2,111 characters). This is structural:
adversarial prompts are mostly stopped at the input rail (84 of the 89 excluded rows are input-rail blocks), so they never
produce an answer for the output judge to see. The agreement measured here is therefore mostly agreement on passing, and the
evidence on the refusing side is that one segment plus one synthetic control.

## Judge latency against completion length — post-hoc, not pre-registered

A straight line fitted to the 345 J1024 calls (completion lengths 62–202 tokens) gives

> duration ≈ 34.2 ms + 10.17 ms × completion tokens  (about 98 tokens/s)

and predicts 64.8 ms for a 3-token verdict against a measured J3 median of 60.4 ms: the difference between the two judges'
call times is accounted for by completion length. Applied to the per-call averages of the 2×2 bridge
(`../bridge_2x2/p18_gr_vs_gr_decomposition.json`), a different experiment:

| Container | Call | Tokens (avg) | Measured ms | Line ms | Measured / line − 1 |
|---|---|---|---|---|---|
| NIM 2.0.12 | output self-check | 94.1 | 995.1 | 991 | +0.4% |
| NIM 2.0.12 | answer generation | 482.0 | 4,937.1 | 4,936 | +0.0% |
| NIM 2.0.12 | input self-check | 50.5 | 599.3 | 548 | +9.4% |
| NIM 1.13.1 | output self-check | 93.5 | 1,178.1 | 985 | +19.6% |
| NIM 1.13.1 | answer generation | 456.5 | 5,326.6 | 4,677 | +13.9% |
| NIM 1.13.1 | input self-check | 51.8 | 700.3 | 561 | +24.8% |

On the same NIM version the line matches the bridge's calls closely; on NIM 1.13.1 every kind of call is slower than the line,
consistent with the bridge's own finding that the NIM upgrade made generation faster. Two limits: the answer-generation rows
are an extrapolation to about 2.4 times the longest completion the line was fitted on, and the intercept depends on prompt
length (the input self-check, with the longest prompt, sits highest), so the line is not a formula for other prompt shapes.

This run's NIM was not clamped (`gpu_memory_utilization` 0.92, KV 97,328 tokens), while the bridge's NIM 2.0.12 container
was clamped to 0.86 (recorded in its startup log, which is not published; its KV size was not recorded; the section 8 run under the same clamp had 81,504 tokens). The line fitted
here still matches the bridge's output self-check and answer-generation calls to within 0.4%, so the KV budget does not enter
single-request latency in this comparison.

## Verifying the hash chain on a clone

Both pre-registrations (`prediction_p28.json`, `prediction_p28_v2.json`) and `corpus.sha256` record the digest of `corpus.json`. On any clone those three entries resolve to no file, and a checker will list them as unresolved. That is by design, not a broken chain: `corpus.json` holds full model answers (free text that cannot be reviewed line by line) and is kept out of the repository; the published artefact is its digest. The file is rebuilt with `scripts/p28_build_corpus.py` from the P19 run's `rows.jsonl` (kept out of the repository for the same reason), and a rebuilt copy must hash to the digest in `corpus.sha256` to be the input this section describes.
