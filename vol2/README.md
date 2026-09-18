# Vol.2 — Evidence Index

> **Vol.1 lives in [`../benchmark/`](../benchmark/)** (question sets, harness, results). It is published evidence and is not modified here.
> This directory holds the Vol.2 harness and results. This file is an **index**: which file belongs to which experiment, where its measurement boundary is recorded, and how data points are counted. This README contains measurement boundaries for data in this directory. It does not contain conclusions from unpublished work.

---

## Layout

```
vol2/
├── README.md
├── data/README.md          # pointer only — question sets are Vol.1's, not copied
├── scripts/
│   ├── e7/                 # E7 arms (P / A1 / A2) + C (co-residence test)
│   ├── e9/                 # E9 runner + analyzer
│   ├── guardrails_nothink/ # E9 rail config (self-check prompts with /no_think system message)
│   ├── bench_reranker.py   # E8 harness (public BEIR datasets only)
│   ├── nim_ttft.py         # shared measurement helpers (GPU context, kernel-path check)
│   ├── run_e3_guardrails_vol2.py  # E9 harness — fork of ../benchmark/run_e3_guardrails.py (lineage in file header)
│   └── scan_self_check_facts.py   # S6
└── results/
    ├── e7/                 # E7 arm results + pre-registrations (+ c/ for C)
    ├── e8/                 # E8 reranker result
    ├── e9/                 # E9 raw 270-point result + analysis
    ├── s6/                 # S6 summary (its pre-registration is held out, see below)
    └── logs/               # pre-launch GPU context lines + NIM startup logs
```

Per-request raw rows (`*.rows.jsonl`) are not included.

---

## File → experiment

| Experiment | What varies | Result files | Pre-registration |
|---|---|---|---|
| **E7 · arm P** | NIM Llama 3.1 8B alone (Vol.1 model, Vol.1 harness) | `results/e7/e7_arm_p.json` · `e7_arm_p_verdict.json` | `results/e7/prediction_arm_p.json` (+ `.sha256`) |
| **E7 · arm A1** | NIM Nemotron Nano 9B v2 | `results/e7/e7_arm_a1.json` | `results/e7/prediction_arm_a1.json` (+ `.sha256`) |
| **E7 · arm A2** | NIM Nemotron 3 Nano | `results/e7/e7_arm_a2.json` | `results/e7/prediction_arm_a2.json` (+ `.sha256`) |
| **E7 · S0** | Recomputes how Vol.1's guardrails overhead was aggregated | `results/e7/s0_vol1_overhead_algorithm.json` | — |
| **C** | NIM alone → NIM with Ollama resident and alternating → NIM alone after unload | `results/e7/c/c_cohabit.json` · `c_verdict.json` | `results/e7/c/prediction_c.json` (+ `.sha256`) |
| **E8** | Reranker on / off over a fixed first stage (SciFact) | `results/e8/scifact_RTX5090_20260913.json` | positive controls inside the result (`positive_control`) |
| **E9** | NeMo Guardrails 0.23.0 on NIM Nemotron Nano 9B v2 | `results/e9/e9_guardrails_0230.json` (response text removed, see *Model output that is not published*) · `e9_analysis.json` · `e9_vs_0210_bootstrap.json` | `results/e9/prediction_e9.json` (+ `.sha256`) |
| **S6** | `self_check_facts` judge behaviour, 0.21.0 vs 0.23.0 | `results/s6/s6_summary.json` · `J2_direct_s6_gr0230.json` | held out — see *Pre-registrations held out of this repository* |

| **B′** | Co-residence with Ollama's GPU layers limited by a VRAM ledger (`num_gpu` = 1) | `results/e7/b_prime/bprime_cohabit.json` · `bprime_verdict.json` — **read `results/e7/b_prime/READ_ME_FIRST.md` first** | `results/e7/b_prime/prediction_bprime.json` (+ `.sha256`) |
| **P07** · tool calling | Whether a NIM-served model decides on its own to call a tool, which one, and with what arguments (4 pure-function tools, 60 questions × 3 rounds) | `results/p07_toolcall/p07_arm_p.json` · `p07_arm_a1.json` · `probe_arm_a2.json` | held out — see *Pre-registrations held out of this repository*. The first attempt's pre-registration is published, in `attempt1_20260913_probe_stop/` |

**P07 is not a model comparison.** Arms P (Llama 3.1 8B) and A1 (Nemotron Nano 9B v2) differ in NIM version (1.13.1 / 1.12.2), tool-call parser (`llama3_json` / `nemotron_json`), chat template, `NIM_MAX_NUM_SEQS` (default / 32) and sampling source. Each arm is an observation of that one configuration. Sampling: the harness sets no temperature. For A2 (Nemotron 3 Nano, NIM 2.0.12) the server's defaults are overridden by the model's `generation_config.json` (temperature 1.0, top_p 1.0; startup log); A2 was not measured because its image does not enable tool calling by default. For A1 the model's generation config sets no sampling values, so the NIM 1.12.2 engine default applies — that value was not checked. For P it was not checked. The post-hoc "which tools did you use" turn was sent without `tools`, so the tool names were not in the context; that secondary metric cannot be interpreted.

In `results/s6/s6_summary.json`, `fallthrough` is the share of items where the Guardrails parser did not obtain the judge's verdict. It is **not** a detection rate for injected false statements.

Question-set integrity: `results/e7/questions_source_sha256.txt` records the SHA-256 of the question sets used. They match `../benchmark/questions.json` and `../benchmark/e3_questions.json` byte for byte.

---

## Where the measurement boundary is

Every result JSON carries a `measurement_label` string (model · image · digests · profile · driver · config · n · statistic · window). **Quote a number together with its label, or not at all.** Statistics are labelled avg or p50 explicitly; Vol.1 reported avg.

Window evidence: `results/logs/*_ctx_before.txt` (GPU state recorded before launch, `$(date)`-stamped) and `results/logs/nim-e7-*_startup.log.txt`.

### E9: `nim_version` is `UNKNOWN (rc=1)` in the result file

`results/e9/e9_guardrails_0230.json` → `metadata.nim_version` reads `UNKNOWN (rc=1)`. The harness looks up the image of a container by a fixed name that did not match the container actually running, so the lookup failed. **The JSON is left as recorded; no value is back-filled** (a back-filled value would be inferred, not measured).

E9 ran **in the same container as E7 arm A1** (the A1 container was kept running for E9; A1 finished 2026-09-13T04:25:56+08:00, E9 started 04:26:02). Image, digests and profile for E9 are therefore those of arm A1:

| Field | Value (from `results/e7/e7_arm_a1.json`) |
|---|---|
| image | `nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2:1.12.2` |
| index digest | `sha256:a2f4a5aefe7dd0ff29bfd8d7081ce4977337d1b12081361af7b6283ff9a406b2` |
| manifest digest (amd64) | `sha256:bdd975848d5d4e2ae1f701a9b78ff7f6ed7de56498f9c2f250d7d98484b0d40f` |
| profile | `5cf34bab34141258d0cc836c66684642d3e3f32b4daaa2008e48bd289d6bc84b` |

Arm A1 `measurement_label`, verbatim:

> nvidia/nvidia-nemotron-nano-9b-v2 · nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2:1.12.2 · index sha256:a2f4a5aefe7d… · profile 5cf34bab3414… · NIM_MAX_NUM_SEQS=32 · NIM_MAX_MODEL_LEN=4096 · 無 RELAX · CUDA graph 開 · RTX 5090 · driver 591.86 / CUDA 13.1 · Win11 + Docker Desktop(WSL2) · 100Q × 3 輪 = 300 請求 · max_tokens=500 · streaming · 無 temperature · COOLDOWN 2s · tps=單字/秒（Vol.1 同式）avg 73.9 (p50 74.9) · TTFT avg 66.2 ms (p50 70.0) · latency avg 6410.6 ms · VRAM max 29287 MB · clean_window_prelaunch=True

(The label's「單字/秒」is covered by the unit correction record below. Its numbers describe arm A1, not E9.)

### `results/s6/prediction_s6.json` has no independent SHA-256

The other pre-registrations ship with a `.sha256` file written at registration time. **This one does not.** No hash has been generated after the fact, because a hash computed now cannot show that the file was unchanged before the run. The file is published exactly as it was written, including a local path it contains.

---

## Data-point ledger

| Source | Count | In total? |
|---|---:|---|
| E7 arm P — 100 questions × 3 rounds | 300 | ✅ |
| E7 arm A1 — 100 × 3 | 300 | ✅ |
| E7 arm A2 — 100 × 3 | 300 | ✅ |
| E9 — 45 questions × 3 rounds × 2 modes | 270 | ✅ |
| **Single-request latency points** | **1,170** | |
| E8 — 300 SciFact queries × 5 runs (retrieval quality + rerank latency) | counted separately | ❌ different unit |
| C — 30 questions × 3 cells (diagnostic) | — | ❌ |
| S6 — 24 items (judge diagnostic) | — | ❌ |

---

## Unit correction record

The E7 result files label throughput as **「單字/秒」 (words per second)**, for example in the `harness` field and in `measurement_label`. That label is inaccurate.

The Vol.1 harness counts `len(delta.split())` **per streamed delta**, so the unit is **non-whitespace streamed fragments per second, ≈ tokens per second**. It is not words per second.

- The scripts in `scripts/e7/` have been corrected.
- Result JSON files are **not edited**: they are the files the pre-registrations and verdicts refer to. Read every「單字/秒」in them as "non-whitespace streamed fragments/s (≈ tokens/s), Vol.1 formula".
- Where available, `true_tps_tokens_per_s` (from `usage.completion_tokens`) is recorded alongside.

---

## Internal identifiers

Identifiers beginning with `D` or `S` (e.g. `D25`, `D26`, `S0`, `S6`) are internal work-order and step codes,
including where one appears in a directory name (`results/s6/`), a JSON key or a recorded context line.
**No public document corresponds to any of them.** They are kept, rather than renamed, for one reason: they are what
the frozen pre-registrations and the result files already say, and rewriting a result file to tidy a label would
change evidence. Read them as opaque provenance markers — they carry no information beyond "this came from that",
and nothing in this repository depends on knowing what they point to.

---

## The profile value in one pre-registration

`results/e7/prediction_arm_p.json` records `config.profile` as the profile id followed by the profile's description in
full-width parentheses (83 characters), not the bare 64-hex id. The arm P run itself used the bare id: `e7_arm_p.json`
records `profile` as `574eb0765118b2087b5fd6c8684a79e682bd03062f80343cfd9e2140ffa962cd`. The two forms are not
interchangeable as input to NIM — passed verbatim, the recorded form is rejected. The pre-registration is left unchanged,
because a pre-registration is never modified.

---

## Pre-registrations held out of this repository

A pre-registration is never modified — its text is the claim, and editing it would forge the record. Two of
them cannot be published as they stand, so they are not published at all. Each is named here with the digest of
the exact frozen bytes, so that if it is ever quoted the quotation can be checked against this record.

| File | SHA-256 of the frozen file | Frozen at | Why it is not here |
|---|---|---|---|
| `results/s6/prediction_s6.json` | `6fd38031984a0edd86129adb08fdb2040704756405299990bdfd4127bc553e58` | 2026-09-13 (no sidecar was written) | one field records the local filesystem path of the isolated virtualenv, including the account name |
| `results/p07_toolcall/prediction_p07.json` | `29bbd49d1e89c30d967ae2dc50218bb141efa1a5bb31474feac4fc717dd1300d` | 2026-09-13T20:49:12+0800 | one field names an internal reviewer and work-order in a sentence explaining why the test was reopened |

What those two registered, **restated in prose — this is a restatement, not the frozen text**:

- **S6** predicted that on the 9B judge with a `/no_think` system message the parser would keep falling through,
  and recorded the decision rule for that outcome before the run.
- **P07 (reopened)** set one gate before any container started: arm P had to produce a structured tool call in at
  least 70% of scored conversations, a threshold this repository's authors chose with no prior measurement to cite;
  if the gate failed, arms A1 and A2 were not to be run. It predicted **nothing** about A1, A2, hallucinated tool
  calls or unparsed tool text, and stated that no conclusion about a model's suitability as an agent was in scope.

🔴 The measured results for these two runs are published in full. What is missing is the *frozen* statement of
what was expected beforehand, and a restatement written afterwards cannot serve that purpose — it is here so the
reader knows what the claim was, not as a substitute for the record.

---

## One field removed from a result file

`results/e7/e7_arm_p_verdict.json` had one top-level field holding three courses of action this repository's
authors proposed to their reviewer after arm P missed its pre-registered interval. Both the field's name and its
text carried internal structure — the reviewing role, internal step labels — so the field is not published. The
file records the removal, what the field held, the digest of the file before it, and which of the three options
was taken (the third: it became the C experiment in `results/e7/c/`). No number in that file came from the field.

---

## Model output that is not published

Free model output does not enter this repository: it cannot be reviewed line by line, and Vol.1 found a forbidden
string inside generated text once already. Three inputs are therefore withheld, and in each case what a reader
needs in order to recompute the published analysis is kept.

| Withheld | What it held | What is kept instead |
|---|---|---|
| `results/p07_toolcall/p07_arm_*.transcripts.jsonl` | every turn of every conversation, both arms | `p07_arm_*.json` — 180 rows per arm of booleans, counts, tool-name lists and cell labels, which is what every published P07 number is computed from |
| `results/p07_toolcall/probe_arm_a1.json` | the model's own reasoning text in `.requests[].content_head` | the probe's verdict is in `p07_arm_a1.json`; `probe_arm_a2.json` and `probe_arm_p.json` are published, their longest strings being server error messages and tool-call ids |
| `response_full` / `response_preview` in `results/e9/e9_guardrails_0230.json` | the generated answer for each of 270 rows | per row: `response_sha256`, `response_chars`, and `harness_block_label` |

The E9 case needs one more sentence, because a boolean there replaces a judgement that used to need reading.
That harness decided `was_blocked` by matching refusal phrasing, so three rows whose full answers happened to
contain the phrasing were marked blocked when they were not; `e9_analysis.json` separated them afterwards by
reading the text. That separation is now a field. It is not an opinion: all 48 blocked rows carry one of exactly
two texts — the rail's own canned refusal (35 characters, 45 rows; its text and digest are in the file's
`metadata`) or a generated answer (2,522 characters, 3 rows, `e3_edge_02` rounds 1–3). **Every label is
re-derivable from `response_sha256` alone**, so `e9_analysis.json` is recomputable from the published file.
What cannot be re-derived from it is the reading itself — whether those three answers really were answers.

---

## Limitation: SciFact is not vendored

SciFact is fetched at run time from `mteb/scifact` (E8) or read from a local copy of the original release (S6). **It is not included in this repo.** E8 and S6 therefore **cannot be reproduced offline from this repository alone**.

---

## Running the scripts

Scripts resolve paths relative to `vol2/` and read question sets from `../benchmark/`. Machine-specific locations come from environment variables:

| Variable | Used by | Meaning |
|---|---|---|
| `NGC_ENV_FILE` | `scripts/e7/run_arm.sh` | path to an env-file passed to `docker run --env-file` |
| `NIM_CACHE_DIR` | `scripts/e7/run_arm.sh` | local directory mounted as the NIM cache |
| `GR0230_PY` | `scripts/e9/run_e9.sh` | python of an isolated venv with `nemoguardrails==0.23.0` |

See [`../DEPLOYMENT_NOTES.md`](../DEPLOYMENT_NOTES.md) for RTX 5090 deployment notes.

## Scripts and pre-registration hashes

Where a pre-registration file records a script's SHA-256, that script is published exactly as registered. The E9 and E7 per-arm
pre-registrations recorded thresholds and inputs but did not record the harness SHA-256. That link cannot be added retroactively.
Results from those runs are reproducible from the scripts as published, but the "script-as-registered" guarantee that later volumes
carry does not apply to them. **The same applies to S6, and more strongly: its pre-registration records no digest of anything, and no
`.sha256` sidecar was ever written for it, so that run has no hash chain at all.** For B′, the verdict script as registered is kept in `results/e7/b_prime/verdict_patch/` next to the
patched version that produced the final verdict (see `PATCH_NOTE.md` there). One entry cannot be verified at all: the first P07 attempt's pre-registration (`results/p07_toolcall/attempt1_20260913_probe_stop/prediction_p07.json`) records a single digest computed over two scripts combined (`harness_sha256_of_toolcall_eval_py+tools_py`), and the published files do not record how the two were combined, so that digest cannot be recomputed on a clone. Every other binding in this repository can be.
