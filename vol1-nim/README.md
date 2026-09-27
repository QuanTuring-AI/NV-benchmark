# Vol.1 (renewed 2026-09) · 7.4× at 128 concurrent users: what NIM buys you on one RTX 5090
*For one user the 4-bit build is faster. From 4 users on NIM leads; at 128 it delivers 7.4× the throughput — 13.6× at matched precision — and still holds the server SLO. Both arms healthy this time.*

## 0 · Headline

Llama 3.1 8B Instruct on one RTX 5090. The concurrency results use synthetic chat requests (200 tokens in, 200 out) and the MLPerf v5.1 Llama 3.1-8B SLOs. Every arm passed its health gate.

1. **For one user, NIM is the engine it contains.** NIM 2.0.12 and upstream vLLM 0.27.1 (the build inside it) ran the same weight files at the same precision. They wrote the same 50 answers byte for byte at the same speed: rate ratio 0.990 [0.963, 1.020]. → §A
2. **For one user, precision decides the speed.** The 4-bit build reads fewer bytes per token and decodes faster than a 16-bit one. At comparable 16-bit precision, NIM bf16 and 16-bit Ollama differ by 1.10× in total throughput for one user. → §D · `results/p59_nim_value/`
3. **From 4 concurrent requests on, NIM leads on total throughput and on each user's speed, and the lead grows with load.**
   - The crossing lies between 2 and 4 concurrent requests.
   - At 8 requests the lead is 3.5×: 607 vs 175 tok/s total, and 77 vs 24 tok/s per user end to end.
   - At 128 requests it is 7.4×.
   - All against the fastest 4-bit configuration we could build with Ollama (16 slots). → §D · `results/p62_levels/` · `results/p59_nim_value/`
4. **NIM kept the MLPerf v5.1 server SLO up to 128 concurrent requests.** In the same sweep (1, 8, 16, 32, 64 and 128 concurrent requests), none of the Ollama configurations we tested kept it beyond 1. → `results/p59_nim_value/`
5. **At comparable precision, the single-user gap is precision and the multi-user gap is the engine.** 16-bit Ollama and bf16 NIM serve 79 vs 87 tok/s for one user, and 402 vs 5,458 at 128. → `results/p59_nim_value/`
6. **General-knowledge accuracy held. On multi-step math the 4-bit build lost measurably, and FP8's loss could not be separated from zero.**
   - MMLU (2,850-question sample): FP8, 16-bit Ollama and 4-bit were all within ±2 points of bf16 NIM.
   - GSM8K: the 4-bit build scored −2.4 points (95% CI −4.4 to −0.5) and FP8 −1.5 points (CI −3.1 to 0.0).
   - Serving 32 requests at once did not change FP8's GSM8K accuracy measurably.

   → §E · `results/p62_quality/` · `results/p63_gsm8k/`
7. **NIM's own profile choice on this card is FP8.**
   - Speed: it was the fastest configuration at every concurrency level, 151 vs 87 tok/s for one user and 8,713 vs 5,458 at 128.
   - Accuracy: 1.5 points lower on GSM8K (95% CI −3.1 to 0.0), and within ±2 points on MMLU.

   → §D · §E
8. **NeMo Guardrails 0.23.0 blocks the same prompts as 0.21.0** (42/45 adversarial, 0/90 false blocks on this set), but asks the judge for up to 1,024 tokens instead of 3. That one default costs about 1.5 s per request, and setting it back is one line. → `../vol2-guardrails/BASELINE.md` §2, §8

| Concurrent requests | NIM bf16 ÷ 4-bit (16 slots), total | NIM FP8 ÷ 4-bit, total | NIM bf16 ÷ 16-bit, total (matched precision) | NIM bf16 ÷ 4-bit, per-user end-to-end |
|---|---|---|---|---|
| 1 | 0.51 | 0.88 | 1.10 | 0.51 |
| 8 | 3.5 | 6.3 | 1.9 | 3.2 |
| 16 | 2.0 | 3.6 | 2.9 | 1.9 |
| 32 | 3.0 | 5.1 | 5.8 | 2.8 |
| 64 | 5.1 | 8.0 | 9.4 | 4.1 |
| **128** | **7.4** (5,458 / 741) | **11.8** (8,713 / 741) | **13.6** (5,458 / 402) | **4.1** (45 / 11) |

> Every ratio above is a division of two cells in `results/p59_nim_value/README.md`. At 128 concurrent requests NIM was still inside the MLPerf server SLO; the Ollama arms had left it at 8, so the ratios above 8 compare a configuration that is serving with one that is queueing. A ratio is a function of concurrency, not a property of an engine, and is quoted only with the concurrency, the precision of both arms, the input shape (synthetic chat, 200 in / 200 out) and whether the SLO held.

## Scope

Vol.1 as first published (2026-03) is `../benchmark/` and is not changed by anything here; this directory is the renewed Vol.1. This directory holds the write-up of a revisit that asks a narrower question than Vol.1-A's E2 did: on one card, one model, one set of weight files and one precision, what does the NIM container's pre-selected configuration amount to against the same inference engine started by hand? The measurements live in `../vol1-nim/results/p54_engine/`; the section of record is in `../vol3-nemotron/BASELINE.md`.

**Codes.** P54, P59, P62 and P63 (and the Q1–Q4 inside P62) are this lab's run identifiers: one per measurement request, numbered in order. They appear in directory, script and pre-registration names so that a file can be traced to the run that produced it. They carry no other meaning, and each run's README states what it measured.

**Setup.** Llama 3.1 8B Instruct, bf16, one RTX 5090 (32,607 MiB, 1,792 GB/s, driver 591.86), both arms from the same snapshot of the NIM cache: 16,060,556,376 bytes of safetensors, the same file hashes in both containers (`stack.json`, hashed inside a container through the same mount both arms use).

- **Arm N** is the NIM container: NIM 2.0.12, profile `092ed421…` (bf16), `NIM_MAX_MODEL_LEN` 8192 and `VLLM_USE_V2_MODEL_RUNNER=0`. This is Vol.1-B's baseline configuration.
- **Arm V** is the upstream `vllm/vllm-openai:v0.27.1` container. It has the same vLLM build commit (`6e448d0e`) and the same torch, CUDA, flashinfer, triton and transformers as the engine inside N.
- **V's engine arguments are NIM's own.** They are the argument list NIM resolves for N's configuration (`nim-serve --dry-run`), with four edits: the model path; NIM's internal port and host; and NIM's two server-layer middlewares, which do not exist outside NIM.

What still differs is listed in the pre-registration and in `../vol1-nim/results/p54_engine/README.md`: the request path through NIM's proxy, NIM's in-process plugins, the OS base, and the KV cache the engine sizes for itself at start (N 97,328 tokens, V 107,728). Pre-registration `prediction_p54_engine.json`, frozen 2026-09-24T00:12:58+0800, before the first container.

## A · Single stream: the same engine, the same answers

Four alternating blocks (N, V, N, V) over the 50 questions of the Vol.1-B sample, one request at a time, `max_tokens` 4096, temperature 0, top_p 0.9, streaming with usage; 2026-09-24 00:40–01:06. All preconditions held.

| | N · NIM 2.0.12 | V · vLLM 0.27.1 | V over N (ratio of means, 95% CI over questions) |
|---|---|---|---|
| Arm health: generation rate × 16.06 GB per token, share of 1,792 GB/s | 98.4 tok/s · **88.2%** | 98.2 tok/s · **88.0%** | gate passes on both |
| Generation rate, median | 98.4 tok/s | 98.2 tok/s | 0.990 [0.963, 1.020] |
| Time to first token, median | 31.4 ms | 31.7 ms | 0.992 [0.881, 1.124] |
| Time to the end of the answer, median | 5,066 ms | 5,053 ms | 1.012 [1.004, 1.019] |
| Completion tokens, median | 483.5 | 483.5 | 1.000 |
| Answers byte-identical across the two arms | | | **50 of 50** |

**At temperature 0 the two arms wrote the same 50 answers, byte for byte, at the same speed.** Both run at 88% of the card's memory bandwidth, the ceiling a bandwidth-bound decoder can approach. The rate difference is inside the run-to-run spread; the answer-time difference is about 1%. NIM's proxy hop does not show in the median time to first token. The pre-registered prediction that it would add up to 15 ms **failed**.

**Concurrency, the same.** With `p53_concurrency_v2`'s harness and SLOs unchanged (`../vol1-nim/results/p54_engine/README.md`), the chat profile (200/200) gives both arms the same ceilings: **256** concurrent requests inside the MLPerf server SLO and **32** inside the interactive one, at about 6,100–6,300 tok/s at the top. The fresh-container repeats agree within 0.2%, and the 3–5% gap in the main sweeps is container to container. The RAG profile (3,500/500) has **no conclusion**. The harness's own calibration prompt hits vLLM's prefix cache on this model, and its pre-registered gate refuses the sweep. That defect is the harness's, not either engine's. Its level tables show both arms running out of KV cache at 26–39 sequences. V is 7–8% ahead there, in line with the 10.7% more KV cache it sized for itself at start.

This is what the physics allows. A healthy engine decoding one stream reads the weights once per token, so two healthy engines on one card, one model and one precision can differ by little. The ratio that originally led Vol.1-A belongs to that configuration: two engines, two precisions, and one arm largely outside GPU memory (`../vol2-guardrails/BASELINE.md`, section 12).

## B · What it takes to get a serving configuration

Each arm started from nothing set and added one setting after each failed start, along a ladder written in the pre-registration. A start counts once it is READY and answers a probe request. Every attempt is a row in `../vol1-nim/results/p54_engine/attempts.jsonl`.

| | Attempts to a serving start | Settings needed | Settings in the measured configuration |
|---|---|---|---|
| N · NIM | 3 | **3**: the bf16 profile, `NIM_MAX_MODEL_LEN` 8192, `VLLM_USE_V2_MODEL_RUNNER=0` | 3 (the same) |
| V · vLLM | 3 | **2**: `--max-model-len 8192`, `VLLM_USE_V2_MODEL_RUNNER=0` | 6: the runner variable and NIM's own five engine options, made explicit |

Two findings about this host (Docker Desktop on WSL2). **Left to itself, NIM selects its FP8 profile on this card** (`vllm-fp8-tp1-pp1`, from its own dry-run). This comparison is bf16, so NIM's first rung already carried the profile setting, a setting V does not need. NIM's own FP8 choice was not started: it is a different precision and outside this question. **Both engines' default model runner fails to start here** with the same error, `RuntimeError: UVA is not available`, at the same step. vLLM logs that it detected WSL and disabled pinned memory, which points to the host rather than either image (no other host was tried), and the V1 model-runner switch fixes it on both. With only the profile chosen, NIM did not start on this host; with nothing set, vLLM did not either. The first bf16 start that served needed three settings on NIM and two on vLLM. Seconds per attempt are recorded and not summed: the ladder was known before this run.

## C · Was anything else resident on the card during E3? (read from the code and the records, no GPU)

Vol.1-B (`../vol2-guardrails/BASELINE.md`, section 12) showed that in Vol.1-A's E2 the comparison engine's model ran largely outside GPU memory. A later reading of E3 (NIM alone against NIM + NeMo Guardrails, the source of the published `+2.1%`) called it "not co-resident" because E3's time to first token was 51 ms where the co-resident E2 measured 221 ms. That was an inference from a timing. The question here is whether the code and the records say it.

**What the code says.**

- `benchmark/run_e3_guardrails.py` sends every request to one address, `NIM_URL = http://localhost:8000/v1/chat/completions` (line 31). Phase 1 (lines 238–262) calls it directly; phase 2 (lines 264–287) goes through NeMo Guardrails, whose rail config `benchmark/guardrails/config.yml` names one model, engine `nim`, `base_url http://localhost:8000/v1` (lines 6–11). The runner has no code path to the comparison engine and starts, loads or stops nothing.
- `benchmark/run_benchmark.py` (E2) builds the comparison engine's requests from the model, the messages, `stream` and `num_predict` only (lines 97–102): no setting of how long the model stays loaded, so the server's own setting applied.

**What the records say.**

- E2's results file records its window as 2026-03-30 23:11:53 → 2026-03-31 01:45:18 (`metadata`).
- `benchmark/results/e3_guardrails.json` records 09:08:24 → 09:35:50. The runner resets `started` on every invocation and can resume from its results file (lines 216 and 221–230), so the window alone could hide an earlier partial run. It does not: the 270 rows' recorded latencies sum to 1,102 s, plus 2 s cooldown after each of 270 requests = 1,642 s, against a 1,646 s window. All of E3 ran in that one invocation, 7 h 23 min after E2's last request.
- No record from either run states GPU memory, the running processes, or the comparison server's configuration. E3's rows carry no timestamps and no GPU state.

**Answer: ③ cannot be determined from the code and the records.** Nothing in E3 loaded the comparison engine's model. Whether it was still resident at 09:08 depends on two things that were not recorded: the comparison server's keep-loaded setting (its default unloads an idle model after five minutes, which would have emptied the card long before E3; a server-side setting can extend that indefinitely), and whether any other client used that server during the 7 h 23 min. The timing argument (51 ms against 221 ms) is consistent with an empty card and remains an inference.

**If it was resident**, the direction is known and the size is not: NIM-only latency would carry the co-residence cost in the denominator, so the published `+2.1%` would understate the rail's relative overhead. No corrected figure is computed here. The Vol.1-B re-measurement of the rail on NIM 2.0.12 alone on the card (`../vol2-guardrails/BASELINE.md`) does not depend on this question.

## D · Several users at once: NIM against Ollama (`results/p59_nim_value/`)

A single-user comparison cannot stand for a serving engine; this run adds the concurrent half. Llama 3.1 8B on this card, five configurations at 1, 8, 16, 32, 64 and 128 concurrent requests: NIM 2.0.12 bf16 and fp8, and Ollama 0.34.4 with the 4-bit model (slots tuned, and left to Ollama) and the 16-bit model. On the chat profile, Ollama's 4-bit model decodes fastest for one user. NIM answers first. From 8 users on, NIM leads on total throughput and on each user's end-to-end speed. NIM keeps the MLPerf server SLO to 128 users; no Ollama configuration keeps it past one. At comparable precision the two engines are close for one user and part as soon as users overlap: the single-user gap is precision, the multi-user gap is the engine. Scope: NIM's profiles on this card are vLLM only. This section covers speed and capacity; answer quality is in section E. Details, crossing points, predictions and what is not settled: `results/p59_nim_value/README.md`.

**Three follow-ups (P62, 2026-09-26).**

- **Where the chat-profile curves cross** (`results/p62_levels/`). Measured at 2 and 4 concurrent requests, with 1 and 8 in the same session, for all five configurations. The N-BF16 vs O-Q4 crossing lies **between 2 and 4**, on both total and per-user throughput. At 2 requests O-Q4 serves 183 tok/s in total and N-BF16 173; at 4 they serve 188 and 335 (`analysis.json` → `crossings`, `levels.<arm>|C|main`). Every anchor is within 0.955–1.146 of P59.
- **O-Q4's flat total** (same directory, `q4`). With 16 slots, O-Q4's total stays at 175–188 tok/s from 1 to 9 concurrent requests, reaches 243 at 12 and 656 at 16. Up to *c* requests decode at the same moment the whole way (8 at once for 63% of the c=8 level), and every `ollama ps` sample shows 100% GPU. The pre-registered explanation, a batch-size limit of 8 that would put the step between 8 and 9, failed. Why the total stays flat cannot be determined from this run.
- **The RAG profile for the NIM arms, with prefix-cache reuse counted on the server** (`results/p62_rag/`). The positive control (the same prompt twice) fired on all four containers at 99.5–99.9%; no calibration request showed more than 0.9%.
  - **N-BF16:** calibration passes, and the server SLO holds at 1 concurrent request (p99 TTFT 353 ms), not at 8 (2,229 ms) (`rag.N-BF16.conclusion`).
  - **N-FP8:** the conclusion stays **null**. Its calibration failed again without any prefix-cache hit. The server's own TTFT histogram places the gap in the server: 138 ms for the harness's prompts against 220 ms for AIPerf's prompts of the same length, and AIPerf agrees with the server. The FP8 arm's prefill time depends on the prompt content (BF16's does not: 309 against 302 ms), for a reason this run cannot see (`server_side_reading`).

## E · Answer quality: is the faster configuration faster because it answers worse? (`results/p62_quality/`, `results/p63_gsm8k/`)

lm-evaluation-harness 0.4.13 was run against the four configurations: N-BF16, N-FP8, O-Q4 (`ollama show`: Q4_K_M) and O-FP16. It used the same task configuration and request bodies on every arm (0 request-hash mismatches over every item).

Task sets:
- GSM8K `gsm8k_cot_llama`: all 1,319 items.
- IFEval: all 541 items.
- MMLU `mmlu_llama`: a seeded 50 × 57 sample (2,850 items).

The comparison is item by item against N-BF16, with a pre-registered equivalence bound of ±2 pp.

- **MMLU (every gate passed; noise floor 1.0%): each faster configuration is within ±2 pp of N-BF16.** Paired differences with 95% intervals: N-FP8 −0.04 [−0.81, +0.74], O-FP16 +0.11 [−0.53, +0.74], O-Q4 −0.25 [−1.23, +0.74] (`analysis.json` → `paired_vs_ref.<arm>|mmlu`). Accuracies are 68.9, 68.9, 69.1 and 68.7% (`cells.<arm>|mmlu.accuracy_pct`).
- **In P62, GSM8K and IFEval carried no conclusion.** On every arm, 2.0–3.3% of outputs reached the task's output cap. The pre-registered gate allows under 1%, so the cells are null (`cells.*.g2.length_share`). N-BF16 run twice at temperature 0 also changed its correctness on 3.26% (GSM8K) and 5.55% (IFEval) of items. That is more than the ±2 pp bound can separate, so the bound is void there and was not widened (`noise_floor`). The accuracies as measured are kept but are not conclusions: The ticket later ruled both gate definitions wrong (`results/p62_quality/README.md`).
  - GSM8K (P62, cap 256): 84.2 / 84.1 / 84.2 / 82.6%.
  - IFEval: 75.8 / 75.4 / 76.0 / 73.9%.
- **GSM8K, measured again (P63, `results/p63_gsm8k/`), cap 1024, all gates passed.** The equivalence method passes its own test: N-BF16 run twice gives 0.00 pp [−0.83, +0.83] (`analysis.json` → `positive_control`). Against N-BF16 (85.6%) the arms differ as follows (`comparisons.<arm>`):
  - N-FP8 (84.1%): −1.52 pp [−3.11, 0.00].
  - O-FP16 (84.3%): −1.29 [−2.88, +0.30].
  - O-Q4 (83.2%): −2.43 [−4.40, −0.53], McNemar p 0.015.
  - **All three verdicts are undetermined against ±2 pp.** No arm is shown within the bound, and none is shown beyond it. For O-Q4 the interval lies entirely below zero, so its loss is detected but its size relative to 2 pp is not. Outputs reaching the cap: 0.30–0.91%.
- **IFEval is descriptive only.** At n = 541 the reference against itself spans [−2.77, +1.29] pp, already wider than ±2.
- **Concurrency does not move accuracy measurably.** N-FP8 on GSM8K scored 84.38% at 1 concurrent request, 84.08% at 8 and 84.61% at 32. c=32 against c=1 is +0.23 pp [−1.21, +1.59], McNemar p 0.83, although only 25% of the answers were identical (`concurrency_fp8_gsm8k`).
- **Scorer controls** passed on all three tasks before any model output: reference answers score 100%, permuted answers score chance (`g1_scorer_controls.json`).
- **Publication.** Only per-item machine fields are published, and `analysis.json` recomputes from them byte for byte (`recompute_check.txt`). A post-run correction of the join between lm-eval's samples and the proxy records (MMLU contains three pairs of identical prompts) is disclosed in that README.

Details, gates, predictions: `results/p62_quality/README.md` and `results/p63_gsm8k/README.md`.

## Files

`../vol1-nim/results/p54_engine/` (pre-registration, stack record, start attempts, single-stream and concurrency runs, analyses) · `results/p59_nim_value/` (section D) · `results/p62_levels/`, `results/p62_rag/` (section D, follow-ups) · `results/p62_quality/`, `results/p63_gsm8k/` (section E). P62 and P63 harnesses, analysers and runners: `scripts/p62_*.py`, `scripts/p63_*.py`, `scripts/run_p62_*.sh`, `scripts/run_p63_gsm8k.sh`. Harness `../vol1-nim/scripts/p54_engine.py`; analysis `../vol1-nim/scripts/p54_single_analyze.py`, `p54_conc_analyze.py`, `p54_attempts_analyze.py`; runner `../vol1-nim/scripts/run_p54_engine.sh`.
