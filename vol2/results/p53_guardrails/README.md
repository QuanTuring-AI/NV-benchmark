# Vol.2 · NeMo Guardrails 0.23.0 on the two Nemotron NIMs: end-to-end overhead and rail cost, E3 question set (run 2026-09-23, 04:12–05:32)

**What was measured.** Per container arm, three request arms rotated per question over Vol.1-A's 45 E3 questions (20 clean_passthrough, 10 edge_case, 15 adversarial_input) × 3 rounds, 2 s between requests, one warm-up request per request arm excluded: **N** nim-only (Vol.1's E3 payload: `max_tokens 500`, temperature 0, streaming, plus top_p 0.9 and usage); **G** NIM + NeMo Guardrails 0.23.0 with **Vol.1's rail config verbatim** (model name substituted, top_p 0.9 added, as the Vol.1-B bridge did; the library's default self-check prompts and their `max_tokens 1024`); **H** the same rail config with E9's variant of the judge prompts, sent under a `/no_think` system message (`../../scripts/guardrails_nothink/config.yml`). The Guardrails worker is Vol.1-B's (`vol1b/scripts/gr_worker.py`, nemoguardrails 0.23.0 in its own venv, one persistent event loop); everything about the timed regions is that harness. Containers: the footprint configuration plus `NIM_MAX_MODEL_LEN 8192` and `max_num_seqs 32`. Pre-registration `prediction_p53_guardrails.json`, frozen 2026-09-23T00:30:40+0800 (`.sha256` beside it). No generated answer is stored: per row `response_sha256` and `response_chars`. The harness's local `rows.jsonl` also holds, per judge call, the first 200 characters of the judge's reply (`completion_head`); that is model output and is not published. The published `rows_public.jsonl` is the same 816 rows with each `completion_head` replaced by its SHA-256 and length and nothing else changed; both analyses below recompute byte for byte from it (copy it to `rows.jsonl` in a scratch directory and run either analyser).

Every row: **A1** Nemotron Nano 9B v2 · bf16 · NIM 1.12.2 · `max_num_seqs` 32 · `max_tokens` 500; **A2** Nemotron 3 Nano · NVFP4 · NIM 2.0.12 · `max_num_seqs` 32 · `max_tokens` 500. 810 rows (2 arms × 3 request arms × 135), all preconditions held on both arms: 0 errors and HTTP 200 on every N row, 135 rows per request arm, one container up at every row.

## Two analyses of the same rows, and why

`analysis.json` is the output of the frozen analyser. **Its detection and false-block counts are wrong (all zero)**: it imports Vol.1-B's `true_block()`, which reads the response *text*, and this harness stores digests, not text. Its self-test passed because the mock rows carried text — the check verified an assumption the real rows do not satisfy. `analysis_digest.json`, from `../../scripts/p53_guardrails_analyze_digest.py` (written after the run, not in the pre-registration), applies the same rules with the block predicate read from the digest: a row is a true block when `was_blocked` is set and `response_sha256` equals the SHA-256 of the rail's canned refusal (`04c378ea…`, 35 characters). Every label below is re-derivable from the published rows (`rows_public.jsonl`). The end-to-end statistics that do not depend on the predicate (clean_passthrough averages, rail costs) are identical in both files.

## Result

### What the rail did with each question set (true blocks / rows)

| Container arm · judge config | clean (60) | edge (30) | adversarial (45) | judge output per self-check call | answered rows |
|---|---|---|---|---|---|
| A1 · **G** Vol.1 config | **60 blocked** | **30 blocked** | 45 blocked | 214 tokens avg (p50 207, p95 303, max 571) in 2.9 s | 0 / 135 |
| A1 · **H** `/no_think` judge | 0 blocked | 0 blocked (3 phrase-match false positives, see below) | **45 blocked** | 3 tokens (input) · 5 tokens (output) in 113 / 135 ms | 90 / 135 |
| A2 · **G** Vol.1 config | **60 blocked** | **30 blocked** | 45 blocked | 79 tokens avg (p50 65, p95 131, max 378) in 415 ms | 0 / 135 |
| A2 · **H** `/no_think` judge | **60 blocked** | **30 blocked** | 45 blocked | 78 tokens avg (max 329) in 426 ms | 0 / 135 |

No judge call reached the 1,024-token budget (pre-registered R2: failed); no G/H row came back empty; no stale-loop retries; usage present on all 270 N rows; N completions: A1 96 of 135 cut at 500 tokens, A2 95 of 135.

**Under Vol.1's rail config, both Nemotron models answer the self-check prompt with reasoning instead of "yes"/"no", and the rail reads that as a block — every question, clean or adversarial, on both arms.** The judge's reply is 65–571 tokens where the prompt asks for one word; the library's parser takes anything that is not a clean "no" as unsafe. This is the request-shape change Vol.1-B documented (`../../../vol1b/BASELINE.md` §5.1) meeting a model that reasons by default. It is not a detection rate: 45/45 adversarial blocked next to 90/90 clean and edge blocked is a rail that has stopped discriminating.

**With the `/no_think` judge, A1 works as the Vol.1 stack did: 45/45 adversarial blocked, 0/90 false blocks** (this sample; not a property of the model). Three edge rows (`e3_edge_02`, rounds 1–3, 2,522 characters each) carry `was_blocked` from the worker's phrase match on a generated answer that contains refusal wording — the same three E9 found, separated here by digest, not by reading. **On A2 the `/no_think` message changes nothing**: the Nemotron 3 Nano judge still writes 78 tokens of reasoning and the rail blocks everything. (Nemotron 3 Nano's reasoning switch is not the `/no_think` system message that Nemotron Nano 9B v2 honours; finding the request shape that gives a one-word verdict from this model is outside this run, which does not change the rail config beyond the two pre-registered variants.)

### End-to-end overhead (clean_passthrough, Vol.1-A's algorithm: avg latency with the rail over without it, minus 1; includes the output-length effect) and rail cost (the judge calls alone) — kept apart

| | A1 · N | A1 · H (rail with `/no_think` judge) | overhead |
|---|---|---|---|
| clean_passthrough avg latency | 6,819.6 ms | 6,805.1 ms | **−0.2%** |
| paired Σ(rail)/Σ(N) − 1 over the 30 questions that passed in both arms (90 pairs), 95% bootstrap CI over questions | | | **−0.25% [−0.49%, −0.02%]** |
| rail cost per request: `self_check_input` · `general` (the answer) · `self_check_output` | | 113 ms / 3 tokens · 6,495 ms / 500 tokens · 135 ms / 5 tokens | judge calls ≈ 250 ms, 3.6% of the answer |

Why the two agree at zero when the rail adds 250 ms of judge calls: both N and the rail's answer run to the 500-token cap (the model reasons by default), so there is no output-length effect this time, and the rail's answer call (non-streamed, 6,495 ms for 500 tokens) is about 300 ms faster than the streamed N request (6,820 ms total); the judge cost is paid inside that margin. Vol.1-B's +34.5% on Llama 8B was mostly output length (the rail's rewrite made short answers long); with a model that fills the budget either way, the measurable cost is the two judge calls, 250 ms here. The rail cost row is the number to carry; the end-to-end row says only that on this sample it was hidden.

| | A2 · N | A2 · G / H | |
|---|---|---|---|
| clean_passthrough avg latency | 1,946.9 ms | 420.5 / 446.6 ms | **not an overhead: every rail row is a refusal after one 415–426 ms judge call; no answer was generated** |
| A1 · G | 6,819.6 ms | 3,200.4 ms | same: a 2.9 s judge call and a refusal |

The negative "overheads" of −53% (A1 G) and −77% (A2) in `analysis.json` are the cost of a refusal, not of an answer, and must not be quoted as speed.

**Rail cost table (durations and completion tokens of the self-check calls, from `rails.explain()`)**

| Arm · judge | `self_check_input` n · avg / p50 / p95 ms · tokens avg | `self_check_output` |
|---|---|---|
| A1 · G | 135 · 2,908 / 2,799 / 4,117 ms · 214 | never reached (input blocked) |
| A1 · H | 135 · 113 / 110 / 144 ms · 3 | 90 · 135 / 137 / 158 ms · 4.6 |
| A2 · G | 135 · 415 / 390 / 609 ms · 79 | never reached |
| A2 · H | 135 · 426 / 395 / 627 ms · 78 | never reached |

The Nemotron 3 Nano judge writes its 79 tokens in 415 ms (190 tok/s, prefill included); the 9B judge writes 214 in 2.9 s. Where the judge does answer in one word (A1 · H), a self-check costs 110–140 ms, most of it the prompt's prefill and the request round trip.

## Pre-registered predictions

**R1** end-to-end clean overhead above +25% on both arms per judge arm — **failed**: A1 · H −0.2%; A1 · G, A2 · G, A2 · H have no answered clean rows. **R2** at least one arm with judge calls at 1,024 tokens or empty verdicts — **failed** (max 571 tokens; 0 empty). **R3** adversarial true blocks 30–45 of 45 under G on both arms — 45/45 on both, **held as written and meaningless as read**: G blocked 135/135. **R4** false blocks ≤ 5 of 90 under H, the majority under G — **held on A1** (0/90 vs 90/90), **failed on A2** (90/90 under H too).

## What this block establishes for the module ladder

NIM × Nemotron × NeMo Guardrails 0.23.0 runs end to end on both arms — the worker connected, the rail executed, `rails.explain()` recorded every call. What the default self-check prompts get back from a reasoning-by-default model is a paragraph, not a verdict, and the rail's parser treats a paragraph as unsafe. On Nemotron Nano 9B v2 a `/no_think` judge message restores one-word verdicts and the rail behaves as it did on Llama in Vol.1-B, at a rail cost of about 250 ms per request. On Nemotron 3 Nano the same message does not, so the Vol.1 rail config cannot be used with that model as published; the request shape that gives its judge a one-word answer is the next experiment, not this one.

## Files

`prediction_p53_guardrails.json` + `.sha256` · `rows_public.jsonl` (816 rows including the 6 warm-up rows; response digests and lengths; per rail row the `llm_calls` from `rails.explain()` with durations, token counts and the digest and length of each judge reply's first 200 characters; no model text) · `events.jsonl` (arm starts with image, profile, env, GPU, cache, rail-config provenance and worker versions) · `analysis.json` (frozen analyser; detection counts wrong as explained) · `analysis_digest.json` (corrected) · `gr_config_<arm>_<g|h>/config.yml` (the rail configs as used) · `versions.txt` · `ctx.txt` · `console.txt`. Harness `../../scripts/p53_guardrails.py`, frozen analysis `../../scripts/p53_guardrails_analyze.py`, corrected analysis `../../scripts/p53_guardrails_analyze_digest.py`, runner `../../scripts/run_p53_guardrails.sh`. `logs/` (container startup logs, worker stderr) and `harness_test/` are not published.
