# Vol.2 · Nemotron 3 Nano on one RTX 5090 with NIM: ~300 tok/s, flat to 120k context, 128 concurrent requests

> **Reproduce:** `git checkout vol1-vol2-published`. That tag is the repository as the Vol.1 and Vol.2 articles describe it: every run of this volume through 2026-10-01 and this README. The harnesses are frozen with the paths they were written with; [`../PATH_MAP.md`](../PATH_MAP.md) maps them to this directory.

We wanted to know what Nemotron 3 Nano (30B total / 3.5B active, hybrid Mamba-2 + MoE) actually does on a single RTX 5090. So we ran it through NIM 2.0.12 with the NVFP4 profile and measured five things: memory, speed, long context, concurrency and answer quality. Nemotron Nano 9B v2, the other Nemotron option NIM offers for this card, is in the tables as a reference point.

**TL;DR**

- **It fits with room to spare.** About 21 GiB at 32 sequences, about 25 GiB at the image default of 256 (4k context). The FP8 build does not fit in 32 GB, so NVFP4 is the option on this card.
- **~300 tok/s for a single stream.** That is 4.1× the 9B v2 in tokens per second. An answer comes back 2.9× faster, because Nemotron 3 Nano writes about 1.4× more tokens before it stops.
- **The speed does not drop with context.** 305 tok/s with 1k tokens of context, 308 tok/s with 120k.
- **128 concurrent chat requests inside the MLPerf Inference server latency target.** With long RAG-shaped prompts the limit is 8.
- **The answers are good, and the reasoning switch matters.** With reasoning on: 95.7% on GSM8K and 88.0% on a 2,850-question MMLU sample. With reasoning off: 5.5 points lower on GSM8K and 12.3 lower on MMLU.

*Concurrency numbers: synthetic prompts, closed loop. Chat = 200 tokens in / 200 out; RAG-shaped = 3,500 in / 500 out. MLPerf server target = p99 TTFT ≤ 2 s and p99 TPOT ≤ 100 ms.*

## Run it

```bash
docker run -d --gpus all -p 8000:8000 \
  -e NGC_API_KEY \
  -e NIM_MODEL_PROFILE=1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada \
  -e NIM_MAX_MODEL_LEN=8192 \
  -v ~/.cache/nim:/opt/nim/.cache \
  nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12
```

That is the NVFP4 profile, everything else at the image default; this is what the concurrency runs set, and nothing else. To turn reasoning off for a request:

```json
{"model": "nvidia/nemotron-3-nano",
 "messages": [{"role": "user", "content": "..."}],
 "chat_template_kwargs": {"enable_thinking": false}}
```

## Results

| | **Nemotron 3 Nano** (NVFP4, NIM 2.0.12) | Nemotron Nano 9B v2 (bf16, NIM 1.12.2) |
|---|---|---|
| Memory the container adds at its smallest working budget (4k context, 32 sequences) | **21.0 GiB** | 21.9 GiB |
| Single-stream generation, median | **305 tok/s** | 73 tok/s |
| Time to finish an answer, median (`max_tokens` 4096) | **7.3 s** | 20.1 s |
| Generation at ~1k / ~14k / ~120k tokens of context | **305 / 315 / 308 tok/s** | 72 / 45 / 52 tok/s |
| Most concurrent chat requests inside the MLPerf server target | **128** (image default, 256 sequences) | 8 (32 sequences) |
| Same, RAG-shaped prompts | **8** | 4 |
| GSM8K · MMLU sample, reasoning on | **95.7% · 88.0%** | 95.2% · 84.0% |

*Each concurrency sweep was run twice on different nights. The limits are the same both times, with two exceptions: the 9B v2 chat row shows the lower second run (16 the first time; its engine exited at 16 the second), and the second run of the RAG-shaped sweep of Nemotron 3 Nano is void by its own rule (one failed request) while its latency test gives the same 8.*

The two models differ in architecture, precision and NIM version. Read this as two deployment options on one card, not a race.

**What NIM adds here.** We ran Nemotron 3 Nano's weights three ways: in the NIM container, in upstream vLLM 0.27.1 with only the model path, and in upstream vLLM with NIM's own arguments. With NIM's arguments, throughput was within 3% of NIM at every concurrency from 1 to 128; with only the model path it was within 5%. GSM8K accuracy was the same. Upstream vLLM picks the same settings by itself; what NIM gives you is the profile chosen for the card and a pinned image.

## Claim → evidence

Every number above and in the forum post, with the file it comes from and the key inside that file. Paths are relative to this directory. `Check`: `rounds` (the stored value rounds to the number), `approx` (within 5%), `equals`, or `text` (the quoted text is in the file).

In the files, **A2** and **N3** are Nemotron 3 Nano (NIM 2.0.12, NVFP4); **A1** and **N2** are Nemotron Nano 9B v2 (NIM 1.12.2, bf16); `C` is the chat profile, `R` the RAG-shaped one.

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| Memory at 32 sequences, GiB (Nemotron 3 Nano) | 21.0 | `results/p50_footprint_addendum2/analysis.json` | `conclusions.per_arm.A2.min_viable.delta_ready_mib / 1024` | rounds |
| Memory at the image default of 256 sequences, GiB | 25 | `results/p50_footprint/analysis.json` | `conclusions.per_arm.A2.min_viable.delta_ready_mib / 1024` | rounds |
| Memory, 9B v2 at 32 sequences, GiB | 21.9 | `results/p50_footprint/analysis.json` | `conclusions.per_arm.A1.min_viable.delta_ready_mib / 1024` | rounds |
| The FP8 build does not fit (it never became ready) | false | `results/p50_footprint/analysis.json` | `conclusions.per_arm.A2FP8.default_viable` | equals |
| ~300 tok/s for a single stream | ~300 | `results/p50_speed/analysis.json` | `conclusions.per_arm.A2.generation_rate.p50` | approx |
| Single-stream generation, median: Nemotron 3 Nano · 9B v2 | 305 · 73 | `results/p50_speed/analysis.json` | `conclusions.per_arm.{A2,A1}.generation_rate.p50` | rounds |
| 4.1× the 9B v2 in tokens per second | 4.1× | `results/p50_speed/analysis.json` | `conclusions.A2_over_A1.generation_rate.ratio_of_means` | rounds |
| An answer comes back 2.9× faster | 2.9× | `results/p53_answer/analysis.json` | `1 / conclusions.A2_over_A1.total_latency_ms.ratio_of_means` | rounds |
| … because it writes about 1.4× more tokens | 1.4× | `results/p53_answer/analysis.json` | `conclusions.A2_over_A1.completion_tokens.ratio_of_means` | rounds |
| Time to finish an answer, median, s: Nemotron 3 Nano · 9B v2 | 7.3 · 20.1 | `results/p53_answer/analysis.json` | `conclusions.per_arm.{A2,A1}.total_latency_ms.p50 / 1000` | rounds |
| Generation at ~1k · ~14k tokens of context (Nemotron 3 Nano) | 305 · 315 | `results/p53_longctx_addendum/analysis.json` | `per_arm.A2.depths.{1024,16384}.generation_tps_p50` | rounds |
| … at ~120k | 308 | `results/p55_longctx_120k/analysis.json` | `conditions.a2_120k.generation_tps_p50` | rounds |
| 9B v2 at ~1k · ~14k | 72 · 45 | `results/p53_longctx/analysis.json` | `per_arm.A1.depths.{1024,16384}.generation_tps_p50` | rounds |
| 9B v2 at ~120k | 52 | `results/p55_longctx_120k/analysis.json` | `conditions.a1_120k.generation_tps_p50` | rounds |
| 128 concurrent chat requests inside the server target (first night) | 128 | `results/p55_concurrency_a2_256/analysis.json` | `sweeps.A2\|C\|main.conclusions.max_concurrency_within_server_slo` | equals |
| … the same on the second night | 128 | `results/p80_rerun/slo_ceilings.json` | `groups.s256_C.p80.conclusions.max_concurrency_within_server_slo` | equals |
| RAG-shaped prompts: the limit is 8 (first night) | 8 | `results/p55_concurrency_a2_256/analysis.json` | `sweeps.A2\|R\|main.conclusions.max_concurrency_within_server_slo` | equals |
| … second night: void by its own rule | null | `results/p80_rerun/slo_ceilings.json` | `groups.s256_R.p80.conclusions` | equals |
| … second night, the latency test alone | 8 | `results/p80_rerun/slo_ceilings.json` | `groups.s256_R.p80.largest_level_inside_slo_without_p1.server` | equals |
| 9B v2, chat: 16 the first night | 16 | `results/p53_concurrency_v2/analysis.json` | `sweeps.A1\|C\|main.conclusions.max_concurrency_within_server_slo` | equals |
| 9B v2, chat: 8 the second night (shown in the table) | 8 | `results/p80_rerun/slo_ceilings.json` | `groups.v2_A1_C.p80.conclusions.max_concurrency_within_server_slo` | equals |
| 9B v2, RAG-shaped: 4, both nights | 4 · 4 | `results/p53_concurrency_v2/analysis.json` | `{sweeps.A1\|R\|main.conclusions.max_concurrency_within_server_slo,results/p80_rerun/slo_ceilings.json::groups.v2_A1_R.p80.conclusions.max_concurrency_within_server_slo}` | rounds |
| GSM8K · MMLU sample, reasoning on (Nemotron 3 Nano) | 95.7% · 88.0% | `results/p78_quality/analysis.json` | `cells.N3\|{on_gsm8k_1,on_mmlu}.accuracy_pct` | rounds |
| GSM8K · MMLU sample, reasoning on (9B v2) | 95.2% · 84.0% | `results/p78_quality/analysis.json` | `cells.N2\|{on_gsm8k_1,on_mmlu}.accuracy_pct` | rounds |
| Reasoning off: points lower on GSM8K · MMLU | 5.5 · 12.3 | `results/p78_quality/analysis.json` | `models.N3.{Q2_gsm8k_on_minus_off,Q2_mmlu_on_minus_off}.diff_pp` | rounds |
| On MMLU the median answer fell from 198 tokens to 7 | 198 · 7 | `results/p78_quality/analysis.json` | `models.N3.reasoning_really_off.mmlu.{on_median,off_median}` | rounds |
| Upstream vLLM with NIM's arguments ÷ NIM, at 1 · 8 · 32 · 64 · 128 | 1.01 · 1.01 · 1.02 · 1.01 · 1.03 | `results/p78_nim_vs_vllm/analysis.json` | `P4.ratio_V3B2_over_N3_by_level.{1,8,32,64,128}` | rounds |
| Upstream vLLM with only the model path ÷ NIM, lowest level ratio (c=32) | 0.95 | `results/p78_nim_vs_vllm/analysis.json` | `tok_s_by_level.V3B1\|32 / tok_s_by_level.N3\|32` | rounds |
| GSM8K the same: upstream arms minus NIM, points | +0.61 · +0.53 | `results/p78_quality/analysis.json` | `G4_quality_arms_vs_N3_off_gsm8k.{V3B1,V3B2}.diff_pp` | rounds |
| About 14.6 MiB of Mamba state per sequence | 14.6 | `results/p50_footprint/analysis.json` | `(conclusions.per_arm.A2.min_viable.budget_mib - results/p50_footprint_addendum2/analysis.json::conclusions.per_arm.A2.min_viable.budget_mib) / 224` | rounds |
| Warm up: ten to twenty requests, about a minute | — | `BASELINE.md` | `that took 11–18 requests and about a minute` | text |
| … the first requests ran at about half speed | — | `BASELINE.md` | `run at roughly half its steady rate` | text |
| 9B v2 image: the engine exited at 16 (two containers) | 16 · 16 | `results/p80_rerun/slo_ceilings.json` | `a1_engine_exits.containers[{0,1}].engine_exit.level` | rounds |
| … and at 32 (two containers) | 32 · 32 | `results/p80_rerun/slo_ceilings.json` | `a1_engine_exits.containers[{2,3}].engine_exit.level` | rounds |
| The same weights on upstream vLLM 0.30.0 did not exit at 16 | false | `results/p80_rerun/slo_ceilings.json` | `G5_levels[0].engine_dead` | equals |
| … at 32 | false | `results/p80_rerun/slo_ceilings.json` | `G5_levels[1].engine_dead` | equals |
| … at 64 | false | `results/p80_rerun/slo_ceilings.json` | `G5_levels[2].engine_dead` | equals |
| Run it: the NVFP4 profile id | — | `scripts/p50_footprint.py` | `"profile": "1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada", "precision": "nvfp4"` | text |
| Run it: the only environment the concurrency runs set | — | `scripts/p55_concurrency_a2.py` | `env = {"NIM_MAX_MODEL_LEN": "8192"}` | text |
| Nemotron 3 Nano starts on this host without the runner switch | — | `results/p80_rerun/events.jsonl` | `"name": "p80-s256-c-1", "ready": true, "reason": null, "env": {"NIM_MAX_MODEL_LEN": "8192"}` | text |
| NIM 1.12.2 is the newest tag offered for the 9B v2 | — | `results/p50_availability/README.md` | `A1's newest image is NIM 1.12.2` | text |

**How to check a row:** open the file, follow the key, compare. Or check every row at once: `python ../tools/check_claims.py README.md` (from this directory). To recompute: each result directory's README names its analysis script (for example `python scripts/p80_slo.py` rebuilds `results/p80_rerun/slo_ceilings.json`); `results/p78_quality/recompute_check.txt` and `results/p80_rerun/recompute_check.txt` show the analysis files reproduced byte for byte from the published inputs.

## How it was measured

- **Decided before the run.** Each run has a pre-registration file (`prediction_*.json`) with its thresholds, predictions and the SHA-256 of the harness, frozen and hashed before the first container starts. Failed predictions are reported as failed (two in the quality run, one in the re-run sweeps).
- **Both arms must be healthy.** A single-stream generation rate implies a memory bandwidth; an arm under 10% of the card's 1,792 GB/s fails the gate and no ratio is reported (measured: 61% and 72%).
- **Closed-loop concurrency.** AIPerf 0.11.0 keeps exactly N requests in flight; synthetic prompts with fixed lengths (`ignore_eos`), 60 s per level after a discarded warm-up level, an instrument calibration at c=1 that gates every sweep.
- **The latency target is fixed first.** MLPerf Inference v5.1, Llama 3.1-8B server scenario (p99 TTFT ≤ 2 s and p99 TPOT ≤ 100 ms): another model's ruler, the same on every row. A sweep's conclusion is null if any live level has a failed request, the calibration fails, or the sequence cap is not the intended one.
- **Quality is scored item by item.** lm-evaluation-harness 0.4.13 at temperature 0; reasoning on and off are compared on the same items with a 95% interval; one cell per model is run twice.
- **Re-run on a gated night.** The main sweeps were repeated with an idle-card gate before every cell (utilization ≤ 2% and ≤ 45 W over 10 s), a speed sentinel per container and a single-stream health probe around every cell, and judged by the original runs' own analysis functions (`results/p80_rerun/`).
- **The hash chain.** `python ../tools/bound_files.py --history` lists every recorded SHA-256 and verifies the file it binds.

## Measurement conditions and what is not explained

Stated plainly, because a reader who reruns this will meet the same things. Details are in [`BASELINE.md`](BASELINE.md) §C, §H, §I, §J and [`results/p80_rerun/README.md`](results/p80_rerun/README.md).

- **The card also drives the Windows desktop.** Most cells of the first runs cannot be shown to have ended on an idle card: of 211 cells, 12 match an idle fingerprint at their end, 176 do not, 23 have no record (`results/p78_audit/`). The main concurrency sweeps were therefore repeated behind an idle-card gate; both values are published side by side.
- **A desktop application can push part of the container out of GPU memory.** With a NIM container at its default budget, under 1 GiB of the card stays free (`results/p80_rerun/events.jsonl`, `container_start` → `state_after`: 30.8–31.0 GiB in use of 31.84). In a harness test on 30 September another program took a little more GPU memory while a container was serving, and Windows moved part of the container's allocation to system memory. Single-request speed stayed normal; high-concurrency throughput collapsed, with the GPU showing 100% utilization at low power. That test's records are kept on the machine and are not published. The published runs record the same Windows GPU counters every 10 s (`results/p80_rerun/windows_gpu_memory_public.jsonl`).
- **One whole run was 6–20× slow and its cause is unexplained.** The first attempt at the re-run, on the morning of 30 September with nobody at the machine, showed that same shape (utilization near 100% at 140–180 W). The same configuration measured before and after a reboot was normal in 18 of 18 cells (`results/p79_host_state/`). The slow run is not published.
- **Two consecutive containers can differ.** On the gated night one container ran 8–27% below its first-night values at every level and the next one, from the same image with the same settings, did not; on identical probes they were 12–16% apart. The memory the container held in system RAM at READY does not separate them. The latency limits were the same.
- **Session to session, absolute rates move.** The 9B v2's single-stream rate ran up to about 20% above earlier runs in one later session (`BASELINE.md` §D), and containers of one configuration differed by up to 31% at 64 concurrent requests in the sequence-cap runs (§C).
- **Nemotron 3 Nano needs a warm-up after READY.** In some containers its first requests run at roughly half the steady rate; where the slow phase ended it had lasted at most 7 requests and 33 s, and nothing in the container log coincides with it (`results/p55_a2_slow_phase/`).
- **One second-night sweep is void by its own rule.** The RAG-shaped sweep had one failed request of 2,579 at 512 concurrent requests, far above its limit of 8; the rule "no failed request at any live level" makes its conclusion null.
- **The 9B v2 engine exits under concurrent load.** Over two nights all eight of its containers ended with the same error: twice at 16 concurrent requests, five times at 32, once at 64. Its container also slowed down over four hours of continuous load (a GSM8K cell took 7.6 s per item at the start and 29.6 s later, accuracy unchanged), so its timing figures from that night are not quoted.
- **Nemotron 3 Nano does not repeat its own text at temperature 0** (20 of 1,319 answers identical between two runs of one cell), while its accuracy repeats (95.68% and 95.60%). Byte-identity between NIM and upstream vLLM could therefore not be tested on this model.
- **Two predictions about the reasoning switch failed.** The MMLU gain from reasoning (9–12 points) is larger than predicted, and answers with reasoning off are 31–39% as long as with it on, not under 25%.

## Evidence index

The rest of this file is the index: which file belongs to which experiment, where its measurement boundary is recorded, and how data points are counted. Full tables, failed predictions and voided runs are in [`BASELINE.md`](BASELINE.md), [`FOOTPRINT.md`](FOOTPRINT.md) and each result directory's README. Run identifiers (P50, P53, P55, P78, P79, P80, E7, E9, S6) name one measurement request each and appear in directory, script and pre-registration names; they carry no other meaning.

> **The March 2026 Vol.1 lives in [`../benchmark/`](../benchmark/)** (question sets, harness, results). It is published evidence and is not modified here.

---

## Layout

```
vol2-nemotron/
├── README.md
├── data/README.md          # pointer only — question sets are Vol.1's, not copied
├── scripts/
│   ├── e7/                 # E7 arms (P / A1 / A2) + C (co-residence test)
│   ├── e9/                 # E9 runner + analyzer
│   ├── guardrails_nothink/ # E9 rail config (self-check prompts with /no_think system message)
│   ├── bench_reranker.py   # E8 harness (public BEIR datasets only)
│   ├── nim_ttft.py         # shared measurement helpers (GPU context, kernel-path check)
│   ├── run_e3_guardrails_vol2.py  # E9 harness — fork of ../benchmark/run_e3_guardrails.py (lineage in file header)
│   ├── scan_self_check_facts.py   # S6
│   ├── p50_footprint.py · p50_footprint_analyze.py · p50_footprint_gen_prediction.py · run_p50_footprint.sh   # footprint sweep (A1, A2, A2 FP8)
│   ├── p50_footprint_addendum.py · …_gen_prediction.py · run_p50_footprint_addendum.sh    # A2 with NIM_MAX_BATCH_SIZE=32 (no effect)
│   ├── p50_footprint_addendum2.py · …_gen_prediction.py · run_p50_footprint_addendum2.sh  # A2 with --max-num-seqs 32 via NIM_PASSTHROUGH_ARGS
│   ├── p50_speed.py · p50_speed_analyze.py · p50_speed_gen_prediction.py · run_p50_speed.sh   # A1 vs A2 speed, alternating blocks
│   ├── p50_bytes_per_token.py     # bytes a decode step reads, from safetensors headers (MoE split)
│   ├── p53_answer.py · p53_answer_analyze.py · p53_answer_gen_prediction.py · run_p53_answer.sh                 # time to a complete answer, max_tokens 4096
│   ├── p53_concurrency.py · p53_concurrency_analyze.py · p53_concurrency_gen_prediction.py · run_p53_concurrency.sh   # closed-loop concurrency (AIPerf) with calibration — first run, conclusions null under its own gate
│   ├── p53_concurrency_v2.py · p53_concurrency_v2_analyze.py · p53_concurrency_v2_gen_prediction.py · run_p53_concurrency_v2.sh   # second run: warm-up level before calibration, profile-matched calibration prompt, engine death as ceiling
│   ├── p53_longctx.py · p53_longctx_analyze.py · p53_longctx_gen_prediction.py · run_p53_longctx.sh             # prompt-depth sweep, one container per depth
│   ├── p53_longctx_addendum.py · p53_longctx_addendum_analyze.py · p53_longctx_addendum_gen_prediction.py · run_p53_longctx_addendum.sh   # the same on A2 (and A1 at 16k) with a 90 s warm-up phase
│   ├── p53_guardrails.py · p53_guardrails_analyze.py · p53_guardrails_gen_prediction.py · run_p53_guardrails.sh   # NeMo Guardrails 0.23.0 on both arms (drives the Vol.3 bridge harness)
│   ├── p53_guardrails_analyze_digest.py   # corrected guardrails analysis (block labels from response digests; written after the run, see its README)
│   ├── p55_concurrency_a2.py · p55_concurrency_a2_analyze.py · p55_concurrency_a2_gen_prediction.py · run_p55_concurrency_a2.sh   # A2 concurrency at max_num_seqs 64 / 128 / 256 (imports the second concurrency run's harness)
│   ├── p55_capture_control.py · p55_capture_control_analyze.py · p55_capture_control_gen_prediction.py · run_p55_capture_control.sh   # A2 at cap 256 with only the CUDA-graph capture size lowered
│   ├── p55_judge_thinking.py · p55_judge_thinking_analyze.py · p55_judge_thinking_gen_prediction.py · run_p55_judge_thinking.sh   # Nemotron 3 Nano judge with enable_thinking false: direct, then through Guardrails
│   ├── p55_depth.py · p55_depth_analyze.py · p55_depth_gen_prediction.py · run_p55_depth.sh   # A1 CUDA-graph control and ~120k-token depth on both arms
│   ├── p55_a2_slow_phase.py   # A2's slow first phase after READY, from records on disk (no GPU)
│   ├── p78_quality.py · p78_lmeval_chunk.py · p78_scorer.py · p78_engines.py · p78_gen_prediction.py · p78_analyze.py · run_p78.sh   # P78: answer quality with reasoning on / off (lm-eval), engine launchers, the analysis of all P78 stages
│   ├── p78_nim_vs_vllm.py     # P78: Nemotron 3 Nano on NIM 2.0.12 against upstream vLLM 0.27.1 on the same files
│   ├── p78_clean_rerun.py · p78_n2_upstream.py   # P78: the sweep definitions that P80 runs (six concurrency sweeps; the 9B v2 weights on upstream vLLM)
│   ├── p78_mock_openai.py     # the mock server used for the harness tests
│   ├── p79_host_state.py · p79_judge.py · p79_gen_prediction.py   # P79: the same configuration before and after a reboot, with the Windows GPU counters
│   ├── p80_rerun.py · p80_judge.py · p80_gen_prediction.py   # P80: the sweeps above with a sentinel per container and arm health around every cell; per-cell verdicts
│   ├── p80_slo.py             # P80: the re-run sweeps judged by the original runs' analysis functions (written after the run)
│   └── p80_postrun.py         # public event files and recompute checks for the P78 / P79 results
└── results/
    ├── e7/                 # E7 arm results + pre-registrations (+ c/ for C)
    ├── e8/                 # E8 reranker result
    ├── e9/                 # E9 raw 270-point result + analysis
    ├── s6/                 # S6 summary (its pre-registration is held out, see below)
    ├── p50_availability/   # image tags, NIM versions, executable profiles, weight bytes, DGX Spark specs (no GPU run)
    ├── p50_footprint/      # minimum engine budget per model, by sweeping NIM_KVCACHE_PERCENT (+ p50_footprint_addendum/, p50_footprint_addendum2/)
    ├── p50_speed/          # A1 vs A2 generation rate with the arm-health gate
    ├── p53_answer/         # the same 50 questions at max_tokens 4096: time and tokens to a complete answer
    ├── p53_concurrency/    # first concurrency run: level tables valid, conclusions null (instrument gate failed by design); A1 engine crash at c=32
    ├── p53_concurrency_v2/ # second concurrency run with the repaired gate: largest closed-loop concurrency inside the MLPerf Server / Interactive SLOs, two ISL/OSL profiles
    ├── p53_longctx/        # TTFT, generation rate and memory at READY at ~1k / 4k / 16k / 64k prompt tokens
    ├── p53_longctx_addendum/  # A2 re-measured at all depths after a warm-up phase (its first minute after READY is not steady state); A1 at 16k again
    ├── p53_guardrails/     # end-to-end overhead and rail cost of NeMo Guardrails 0.23.0 on both arms, E3 question set
    ├── p55_concurrency_a2_256/ · _128/ · _064/   # A2 concurrency with the sequence cap raised: SLO ceilings, which pool binds, fresh-container repeats
    ├── p55_capture_control/   # A2: the CUDA-graph capture size, not the cap, sets the rate at a fixed concurrency
    ├── p55_judge_thinking/ # Nemotron 3 Nano as the self-check judge with reasoning switched off (two layers: direct, through Guardrails)
    ├── p55_a1_capture/     # A1's rate step past 8k tokens: CUDA graphs off at ~4k and ~14k (attribution measured)
    ├── p55_longctx_120k/   # both arms at ~120k prompt tokens
    ├── p55_a2_slow_phase/  # A2's slow first phase after READY: what the records can and cannot say (no GPU)
    ├── p78_quality/        # GSM8K and an MMLU sample, both models, reasoning on and off: per-item scores, analysis
    ├── p78_nim_vs_vllm/    # Nemotron 3 Nano: NIM 2.0.12 vs upstream vLLM 0.27.1 (bare, and with NIM's arguments)
    ├── p78_audit/          # the end-of-cell GPU record of every P50 / P53 / P55 cell against one idle-card fingerprint (no GPU run)
    ├── p78_clean_rerun/ · p78_n2_upstream/   # pre-registrations only: the runs themselves are in p80_rerun/
    ├── p79_host_state/     # the same configuration before and after a host reboot (T1, T2): 18 cells, Windows GPU memory counters, 500 ms nvidia-smi logs
    ├── p80_rerun/          # six concurrency sweeps repeated on a gated night, and the 9B v2 weights on upstream vLLM 0.30.0
    └── logs/               # pre-launch GPU context lines + NIM startup logs
```

Per-request raw rows (`*.rows.jsonl`) are not included. P78, P79 and P80 (2026-09-29 to 2026-10-01) were added on 2026-10-01 and are in the `vol2-nemotron-published` tag.

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

| **Availability** (no GPU) | Which NIM images, versions, executable profiles and weight sizes exist for Nemotron Nano 9B v2 and Nemotron 3 Nano on this card; DGX Spark specifications from two sources; NeMo Retriever image reachability | `results/p50_availability/README.md` · `availability.json` · `raw/` | — (a query, not a measurement) |
| **Footprint** | Smallest engine memory budget (`NIM_KVCACHE_PERCENT`) at which each model starts and serves at 4,096 context; whether the Nemotron 3 Nano FP8 profile starts at all | `results/p50_footprint/README.md` · `configs.jsonl` · `analysis.json`; two addenda on the sequence limit in `results/p50_footprint_addendum/` and `…_addendum2/` (each with its own README) | `results/p50_footprint/prediction_p50_footprint.json` (+ `.sha256`); `…_addendum/prediction_p50_footprint_addendum.json`; `…_addendum2/prediction_p50_footprint_addendum2.json` (each + `.sha256`) |
| **Speed** | Nemotron Nano 9B v2 (bf16, NIM 1.12.2) vs Nemotron 3 Nano (NVFP4, NIM 2.0.12), alternating blocks on the same 50 questions, engine token usage recorded, arm-health gate before any ratio | `results/p50_speed/README.md` · `requests.jsonl` · `events.jsonl` · `analysis.json` | `results/p50_speed/prediction_p50_speed.json` (+ `.sha256`) |
| **Answer** | The speed run's design at `max_tokens` 4096 (containers at `NIM_MAX_MODEL_LEN` 8192): total time and tokens to a complete answer, truncation rate, whether a reasoning channel is exposed | `results/p53_answer/README.md` · `requests.jsonl` · `events.jsonl` · `analysis.json` | `results/p53_answer/prediction_p53_answer.json` (+ `.sha256`) |
| **Concurrency, first run** | Closed-loop concurrency 1–64 per arm on two synthetic ISL/OSL profiles (AIPerf 0.11.0, `ignore_eos`), both arms at `max_num_seqs` 32; instrument calibrated against the harness's own client; fresh-container repeat of the top levels. **Conclusions null under its own rules** (the calibration ran during A2's warm-up and with one prompt length for both profiles; A1's engine died at c=32); level tables published | `results/p53_concurrency/README.md` · `levels.jsonl` · `events.jsonl` · `analysis.json` · per-level AIPerf summaries | `results/p53_concurrency/prediction_p53_concurrency.json` (+ `.sha256`) |
| **Concurrency, second run** | The same sweeps with the gate repaired: a discarded 60 s warm-up level before the calibration, calibration prompt of the profile's length, engine death pre-registered as the ceiling, container logs saved | `results/p53_concurrency_v2/README.md` · `levels.jsonl` · `events.jsonl` · `analysis.json` · per-level AIPerf summaries | `results/p53_concurrency_v2/prediction_p53_concurrency_v2.json` (+ `.sha256`) |
| **Long context** | Prompt depth ~1k / 4k / 16k / 64k tokens per arm, each depth in a container sized for it; TTFT, generation rate, memory at READY | `results/p53_longctx/README.md` · `requests.jsonl` · `events.jsonl` · `analysis.json` | `results/p53_longctx/prediction_p53_longctx.json` (+ `.sha256`) |
| **Long context, addendum** | A2 at the four depths and A1 at 16k with discarded warm-up requests (≥ 90 s, ≥ 6) before the five measured ones; warm-up rows kept and marked | `results/p53_longctx_addendum/README.md` · `requests.jsonl` · `events.jsonl` · `analysis.json` | `results/p53_longctx_addendum/prediction_p53_longctx_addendum.json` (+ `.sha256`) |
| **Guardrails** | NeMo Guardrails 0.23.0 on each arm: nim-only vs Vol.1's rail config vs the same config with a `/no_think` judge message, E3 question set, 3 rounds; end-to-end overhead and rail cost kept apart | `results/p53_guardrails/README.md` · `rows_public.jsonl` (no model text; judge replies as digests) · `events.jsonl` · `analysis.json` (frozen analyser; its block counts are wrong, see README) · `analysis_digest.json` (corrected) · `gr_config_*/` | `results/p53_guardrails/prediction_p53_guardrails.json` (+ `.sha256`) |
| **Concurrency, cap raised** (P55) | A2 alone at `max_num_seqs` 64, 128 and 256 (the image default), same harness, profiles, SLOs and rules as the second run; levels to twice the cap; per-level vLLM gauges read to name the pool that binds | `results/p55_concurrency_a2_{256,128,064}/README.md` · `levels.jsonl` · `events.jsonl` · `analysis.json` · per-level AIPerf summaries and gauges | `results/p55_concurrency_a2_{256,128,064}/prediction_*.json` (+ `.sha256`) |
| **CUDA-graph capture control** (P55, added) | A2 at cap 256, default capture size vs capture size 64, one session, profile C at c=1 / 16 / 32 | `results/p55_capture_control/README.md` · `levels.jsonl` · `events.jsonl` · `analysis.json` | `results/p55_capture_control/prediction_p55_capture_control.json` (+ `.sha256`) |
| **Judge with reasoning off** (P55) | Nemotron 3 Nano judging Vol.1's self-check prompts with `chat_template_kwargs.enable_thinking = false`: straight to the NIM, then through Guardrails 0.23.0 (task-typed judge models) | `results/p55_judge_thinking/README.md` · `l1_calls.jsonl` · `rows_public.jsonl` (no model text) · `events.jsonl` · `analysis.json` · `gr_config_a2_j/` | `results/p55_judge_thinking/prediction_p55_judge_thinking.json` (+ `.sha256`) |
| **A1 CUDA-graph control** (P55) | A1 at ~4k and ~14k tokens with CUDA graphs switched off (`NIM_DISABLE_CUDA_GRAPH`), and the capture-limit setting the image does not deliver | `results/p55_a1_capture/README.md` · `requests.jsonl` · `events.jsonl` · `analysis.json` | `results/p55_a1_capture/prediction_p55_a1_capture.json` (+ `.sha256`) |
| **Long context, ~120k** (P55) | Both arms at ~120k prompt tokens (`NIM_MAX_MODEL_LEN` 131072) | `results/p55_longctx_120k/README.md` · `requests.jsonl` · `events.jsonl` · `analysis.json` · `analysis_ref_order_addendum_first.json` | `results/p55_longctx_120k/prediction_p55_longctx_120k.json` (+ `.sha256`) |
| **A2 slow first phase** (P55, no GPU) | Request records and saved container logs of earlier runs read for a mechanism and a warm-up count | `results/p55_a2_slow_phase/README.md` · `slow_phase.json` | — (analysis of existing records) |
| **Answer quality, reasoning on / off** (P78) | GSM8K (1,319 items) and an MMLU sample (2,850 items) through lm-eval 0.4.13 at temperature 0, each model with reasoning on and off; one repeated cell per model; one cell at client concurrency 1 | `results/p78_quality/items.jsonl` (one row per item: score, tokens, cap, no text) · `analysis.json` · `durations.json` · `events_public.jsonl` · `recompute_check.txt` | `results/p78_quality/prediction_p78_quality.json` + `.sha256` |
| **NIM vs upstream vLLM on Nemotron 3 Nano** (P78) | NIM 2.0.12 against `vllm/vllm-openai:v0.27.1` bare and with NIM's argument list: 50 single requests, chat profile at c = 1 / 8 / 32 / 64 / 128, GSM8K with reasoning off | `results/p78_nim_vs_vllm/requests.jsonl` (response digests, no text) · `levels.jsonl` · `analysis.json` · `events_public.jsonl` | `results/p78_nim_vs_vllm/prediction_p78_nim_vs_vllm.json` + `.sha256` |
| **End-of-cell GPU state** (P78, no GPU) | One idle-card fingerprint applied to the end-of-cell GPU record of every P50 / P53 / P55 cell, and which written number each cell feeds | `results/p78_audit/z3_audit.md` · `z3_audit.json` · `z3_audit.py` | — (reads the committed tree) |
| **Host state** (P79) | The cap-256 configuration in fresh containers before (T1) and after (T2) a host reboot: R c=1, C c=1, C c=128 per container, with Windows GPU memory counters and 500 ms `nvidia-smi` logs | `results/p79_host_state/T1/` · `T2/` (`levels.jsonl` · `judge.json` · `events_public.jsonl` · `windows_gpu_memory_public.jsonl`) · `sentinel_replay.json` | `results/p79_host_state/prediction_p79_host_state.json` + `.sha256` |
| **Concurrency re-run on a gated night** (P80) | The main sweeps of the second concurrency run and of the cap-256 run again, with an idle-card gate, a speed sentinel per container and arm health around every cell; the 9B v2 weights on upstream vLLM 0.30.0 at c = 16 / 32 / 64 | `results/p80_rerun/README.md` · `levels.jsonl` · `events.jsonl` · `judge.json` · `slo_ceilings.json` · `engine_log_excerpts.json` · `recompute_check.txt` | `results/p80_rerun/prediction_p80_gates.json` + `.sha256` (gates) · `results/p78_clean_rerun/prediction_p78_clean_rerun.json` · `results/p78_n2_upstream/prediction_p78_n2_upstream.json` (the sweeps) |

The Guardrails, E9, S6 and judge-with-reasoning-off rows are measurements of Nemotron on NIM and stay here; the judge topic itself is the subject of Vol.3 ([`../vol3-judges/`](../vol3-judges/README.md)).

**The speed table is not a single-variable comparison either.** A1 and A2 differ in architecture (dense / MoE), precision (bf16 / NVFP4 — the only precision each image can run on this card) and NIM version (1.12.2 / 2.0.12 — no common version exists, see `results/p50_availability/`). It compares two deployment options, each in its own best configuration on this card.

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
| **Single-request latency points (E7, E9)** | **1,170** | |
| Speed — 50 questions × 2 arms (`p50_speed`) | 100 | ✅ single-request |
| Answer — 50 questions × 2 arms at `max_tokens` 4096 (`p53_answer`) | 100 | ✅ single-request |
| Long context — 5 requests × 4 depths × 2 arms (`p53_longctx`) | 40 | ✅ single-request |
| Long context addendum — 5 measured requests × 5 (arm, depth) cells (`p53_longctx_addendum`; 68 warm-up rows recorded, not counted) | 25 | ✅ single-request |
| Guardrails — 45 questions × 3 rounds × 3 request arms × 2 container arms (`p53_guardrails`) | 810 | ✅ (270 nim-only single-request rows + 540 rail rows) |
| **Single-request latency points, Vol.2 P50/P53** | **1,075** | |
| Concurrency, first run — AIPerf closed-loop requests completed over 36 levels (`p53_concurrency`) | 4,995 | ❌ different unit (closed-loop levels; conclusions null) |
| Concurrency, second run — completed over 33 levels (+ 576 in discarded warm-up levels) (`p53_concurrency_v2`) | 5,145 | ❌ different unit (closed-loop levels) |
| Footprint — container starts (`p50_footprint` 15, addenda 6 + 8) | 29 | ❌ different unit |
| Answer quality — scored items over 13 cells (`p78_quality/items.jsonl`) | 22,152 | ❌ different unit (accuracy items, not latency points) |
| NIM vs upstream vLLM — 60 single requests × 3 arms (50 questions + 10 self-repeats) (`p78_nim_vs_vllm/requests.jsonl`) | 180 | ❌ not added to the totals above |
| NIM vs upstream vLLM — completed over 15 levels (+ 540 in discarded warm-up levels) | 8,917 | ❌ different unit (closed-loop levels) |
| Host state — completed over 18 levels, T1 3,522 + T2 3,593 (+ 390 in warm-up levels) (`p79_host_state`) | 7,115 | ❌ different unit (closed-loop levels) |
| Concurrency re-run — completed over 49 measured level rows (+ 1,843 in 14 sentinel probes, 619 in warm-up levels) (`p80_rerun`) | 18,717 | ❌ different unit (closed-loop levels) |
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

Identifiers beginning with `D` or `S` (e.g. `D25`, `D26`, `S0`, `S6`), and `P` followed by two digits (e.g. `P07`, `P50`), are internal work-order and step codes,
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

Scripts resolve paths relative to `vol2-nemotron/` and read question sets from `../benchmark/`. Machine-specific locations come from environment variables:

| Variable | Used by | Meaning |
|---|---|---|
| `NGC_ENV_FILE` | `scripts/e7/run_arm.sh` | path to an env-file passed to `docker run --env-file` |
| `NIM_CACHE_DIR` | `scripts/e7/run_arm.sh` | local directory mounted as the NIM cache |
| `GR0230_PY` | `scripts/e9/run_e9.sh` | python of an isolated venv with `nemoguardrails==0.23.0` |
| `NGC_ENV_FILE` · `NIM_CACHE_DIR` | `scripts/run_p50_*.sh` · `scripts/run_p53_*.sh` | as above (the P50/P53 harnesses start their own containers) |
| `AIPERF` · `TOKENIZER_ROOT` | `scripts/run_p53_concurrency.sh` · `scripts/run_p53_concurrency_v2.sh` | the `aiperf` executable (0.11.0) and a directory holding each model's tokenizer files under `a1/` and `a2/` |
| `GR023_PY` | `scripts/run_p53_guardrails.sh` | python of an isolated venv with `nemoguardrails==0.23.0` (the Vol.3 worker) |

See [`../DEPLOYMENT_NOTES.md`](../DEPLOYMENT_NOTES.md) for RTX 5090 deployment notes.

## Scripts and pre-registration hashes

Where a pre-registration file records a script's SHA-256, that script is published exactly as registered. The E9 and E7 per-arm
pre-registrations recorded thresholds and inputs but did not record the harness SHA-256. That link cannot be added retroactively.
Results from those runs are reproducible from the scripts as published, but the "script-as-registered" guarantee that later volumes
carry does not apply to them. **The same applies to S6, and more strongly: its pre-registration records no digest of anything, and no
`.sha256` sidecar was ever written for it, so that run has no hash chain at all.** For B′, the verdict script as registered is kept in `results/e7/b_prime/verdict_patch/` next to the
patched version that produced the final verdict (see `PATCH_NOTE.md` there). One entry cannot be verified at all: the first P07 attempt's pre-registration (`results/p07_toolcall/attempt1_20260913_probe_stop/prediction_p07.json`) records a single digest computed over two scripts combined (`harness_sha256_of_toolcall_eval_py+tools_py`), and the published files do not record how the two were combined, so that digest cannot be recomputed on a clone. Every other binding in this repository can be.
