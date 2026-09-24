# Vol.1-A revisit · the same engine, run two ways

Vol.1-A (`benchmark/`, published 2026-03-31) is not changed by anything here. This directory holds the write-up of a revisit that asks a narrower question than Vol.1-A's E2 did: on one card, one model, one set of weight files and one precision, what does the NIM container's pre-selected configuration amount to against the same inference engine started by hand? The measurements live in `../vol2/results/p54_engine/`; the section of record is in `../vol2/BASELINE.md`.

**Setup.** Llama 3.1 8B Instruct, bf16, one RTX 5090 (32,607 MiB, 1,792 GB/s, driver 591.86), both arms from the same snapshot of the NIM cache: 16,060,556,376 bytes of safetensors, the same file hashes in both containers (`stack.json`, hashed inside a container through the same mount both arms use).

- **Arm N** is the NIM container: NIM 2.0.12, profile `092ed421…` (bf16), `NIM_MAX_MODEL_LEN` 8192 and `VLLM_USE_V2_MODEL_RUNNER=0`. This is Vol.1-B's baseline configuration.
- **Arm V** is the upstream `vllm/vllm-openai:v0.27.1` container. It has the same vLLM build commit (`6e448d0e`) and the same torch, CUDA, flashinfer, triton and transformers as the engine inside N.
- **V's engine arguments are NIM's own.** They are the argument list NIM resolves for N's configuration (`nim-serve --dry-run`), with four edits: the model path; NIM's internal port and host; and NIM's two server-layer middlewares, which do not exist outside NIM.

What still differs is listed in the pre-registration and in `../vol2/results/p54_engine/README.md`: the request path through NIM's proxy, NIM's in-process plugins, the OS base, and the KV cache the engine sizes for itself at start (N 97,328 tokens, V 107,728). Pre-registration `prediction_p54_engine.json`, frozen 2026-09-24T00:12:58+0800, before the first container.

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

**Concurrency, the same.** With `p53_concurrency_v2`'s harness and SLOs unchanged (`../vol2/results/p54_engine/README.md`), the chat profile (200/200) gives both arms the same ceilings: **256** concurrent requests inside the MLPerf server SLO and **32** inside the interactive one, at about 6,100–6,300 tok/s at the top. The fresh-container repeats agree within 0.2%, and the 3–5% gap in the main sweeps is container to container. The RAG profile (3,500/500) has **no conclusion**. The harness's own calibration prompt hits vLLM's prefix cache on this model, and its pre-registered gate refuses the sweep. That defect is the harness's, not either engine's. Its level tables show both arms running out of KV cache at 26–39 sequences. V is 7–8% ahead there, in line with the 10.7% more KV cache it sized for itself at start.

This is what the physics allows. A healthy engine decoding one stream reads the weights once per token, so two healthy engines on one card, one model and one precision can differ by little. The 7.3× in Vol.1-A belongs to that configuration: two engines, two precisions, and one arm largely outside GPU memory (`../vol1b/BASELINE.md`, section 12).

## B · What it takes to get a serving configuration

Each arm started from nothing set and added one setting after each failed start, along a ladder written in the pre-registration. A start counts once it is READY and answers a probe request. Every attempt is a row in `../vol2/results/p54_engine/attempts.jsonl`.

| | Attempts to a serving start | Settings needed | Settings in the measured configuration |
|---|---|---|---|
| N · NIM | 3 | **3**: the bf16 profile, `NIM_MAX_MODEL_LEN` 8192, `VLLM_USE_V2_MODEL_RUNNER=0` | 3 (the same) |
| V · vLLM | 3 | **2**: `--max-model-len 8192`, `VLLM_USE_V2_MODEL_RUNNER=0` | 6: the runner variable and NIM's own five engine options, made explicit |

Two findings about this host (Docker Desktop on WSL2). **Left to itself, NIM selects its FP8 profile on this card** (`vllm-fp8-tp1-pp1`, from its own dry-run). This comparison is bf16, so NIM's first rung already carried the profile setting, a setting V does not need. NIM's own FP8 choice was not started: it is a different precision and outside this question. **Both engines' default model runner fails to start here** with the same error, `RuntimeError: UVA is not available`, at the same step. vLLM logs that it detected WSL and disabled pinned memory, which points to the host rather than either image (no other host was tried), and the V1 model-runner switch fixes it on both. With only the profile chosen, NIM did not start on this host; with nothing set, vLLM did not either. The first bf16 start that served needed three settings on NIM and two on vLLM. Seconds per attempt are recorded and not summed: the ladder was known before this run.

## C · Was anything else resident on the card during E3? (read from the code and the records, no GPU)

Vol.1-B (`../vol1b/BASELINE.md`, section 12) showed that in Vol.1-A's E2 the comparison engine's model ran largely outside GPU memory. A later reading of E3 (NIM alone against NIM + NeMo Guardrails, the source of the published `+2.1%`) called it "not co-resident" because E3's time to first token was 51 ms where the co-resident E2 measured 221 ms. That was an inference from a timing. The question here is whether the code and the records say it.

**What the code says.**

- `benchmark/run_e3_guardrails.py` sends every request to one address, `NIM_URL = http://localhost:8000/v1/chat/completions` (line 31). Phase 1 (lines 238–262) calls it directly; phase 2 (lines 264–287) goes through NeMo Guardrails, whose rail config `benchmark/guardrails/config.yml` names one model, engine `nim`, `base_url http://localhost:8000/v1` (lines 6–11). The runner has no code path to the comparison engine and starts, loads or stops nothing.
- `benchmark/run_benchmark.py` (E2) builds the comparison engine's requests from the model, the messages, `stream` and `num_predict` only (lines 97–102): no setting of how long the model stays loaded, so the server's own setting applied.

**What the records say.**

- E2's results file records its window as 2026-03-30 23:11:53 → 2026-03-31 01:45:18 (`metadata`).
- `benchmark/results/e3_guardrails.json` records 09:08:24 → 09:35:50. The runner resets `started` on every invocation and can resume from its results file (lines 216 and 221–230), so the window alone could hide an earlier partial run. It does not: the 270 rows' recorded latencies sum to 1,102 s, plus 2 s cooldown after each of 270 requests = 1,642 s, against a 1,646 s window. All of E3 ran in that one invocation, 7 h 23 min after E2's last request.
- No record from either run states GPU memory, the running processes, or the comparison server's configuration. E3's rows carry no timestamps and no GPU state.

**Answer: ③ cannot be determined from the code and the records.** Nothing in E3 loaded the comparison engine's model. Whether it was still resident at 09:08 depends on two things that were not recorded: the comparison server's keep-loaded setting (its default unloads an idle model after five minutes, which would have emptied the card long before E3; a server-side setting can extend that indefinitely), and whether any other client used that server during the 7 h 23 min. The timing argument (51 ms against 221 ms) is consistent with an empty card and remains an inference.

**If it was resident**, the direction is known and the size is not: NIM-only latency would carry the co-residence cost in the denominator, so the published `+2.1%` would understate the rail's relative overhead. No corrected figure is computed here. The Vol.1-B re-measurement of the rail on NIM 2.0.12 alone on the card (`../vol1b/BASELINE.md`) does not depend on this question.

## Files

`../vol2/results/p54_engine/` (pre-registration, stack record, start attempts, single-stream and concurrency runs, analyses). Harness `../vol2/scripts/p54_engine.py`; analysis `../vol2/scripts/p54_single_analyze.py`, `p54_conc_analyze.py`, `p54_attempts_analyze.py`; runner `../vol2/scripts/run_p54_engine.sh`.
