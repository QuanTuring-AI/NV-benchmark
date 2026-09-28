# Vol.1 (renewed) · P62 Q3 · the RAG profile for the two NIM arms, with prefix-cache reuse read from the server (run 2026-09-26, 16:52–17:58)

**Why.** P54's RAG profile is null: its warm-up level and its c=1 level shared a seed, so the same prompts were served twice and the engine reused their cached prefixes. P59 removed every shared prompt by design, but it checked reuse through time to first token only. Its N-FP8 RAG calibration then failed (AIPerf p50 TTFT 208 ms against the harness's own 156 ms), and P59 had no way to tell whether a cached prefix was involved.

This run counts reuse on the server, with vLLM's `vllm:prefix_cache_queries` and `vllm:prefix_cache_hits` counters. They are read before and after every calibration request and around every level. P54's RAG result stays null and was not re-run. P59's three Ollama arms passed their RAG calibration and were not re-run.

**Pre-registration and harness.**
- The pre-registration is `prediction_p62_rag.json`, frozen 2026-09-26T16:39:13+0800 after two harness tests, which are disclosed in `harness_test_record.json` and in its `harness_test` field. It was scanned before its sidecar was written (`prediction_scan.txt`, with a planted-control rescan). The first container started at 16:52:58.
- The harness is `vol1-nim/scripts/p62_rag.py`, which imports P59's harness unchanged and adds the counter reads.
- The analysis is `vol1-nim/scripts/p62_rag_analyze.py`: P59's frozen analysis program plus the counter rules.
- **Profile R:** 3,500 ± 300 input tokens, 500 ± 50 output tokens. AIPerf 0.11.0 closed loop, levels 1, 8, 16, 32, 64, 128 at 60 s each, then a fresh container for 64 and 128.
- **Arms:** N-BF16 (profile `092ed421…`) and N-FP8 (profile `c4789f7a…`), both NIM 2.0.12 with `NIM_MAX_MODEL_LEN` 8192.

## The detector works, and nothing was reused

All sources below are in `events_public.jsonl` (`container_start.prefix_detector`, `profile_start.calibration`) or `analysis.json` (`levels.*.prefix_cache`).

| Check | N-BF16 main / fresh | N-FP8 main / fresh |
|---|---|---|
| **Positive control:** the same ~3,500-token prompt twice; share of the second request's tokens served from cache | 99.5% / 99.9% | 99.6% / 99.7% |
| **Negative form:** two prompts, each led by its own nonce | 0.5% / 0.9% | 0.9% / 0.9% |
| Largest share on any of the 20 calibration requests | 0.9% | 0.9% |
| Share per level (main, c=1 → 128) | 0.45–0.73% | 0.44–0.59%; **c=128: 4.0%** |

About 0.9% (32 tokens, two 16-token blocks) is the chat template's preamble, which every request shares. The rule allows 2%.

N-FP8's c=128 main level showed 4.0% and is therefore excluded ("prefix-cache hits"). Its cause was not examined. This run cannot say whether AIPerf repeated prompts at that level.

## N-BF16 · RAG conclusion

Calibration passed: AIPerf p50 TTFT 306 ms against 320 ms, and inter-token latency 11.5 against 11.6 ms (`arms.N-BF16.calibration.R`). Health was 80.3% of peak bandwidth.

Each cell gives total tok/s · per-user tok/s (1 / inter-token latency) · p99 TTFT (ms). Source: `rag.N-BF16.conclusion.levels.<c>`.

| c | 1 | 8 | 16 | 32 | 64 | 128 |
|---|---|---|---|---|---|---|
| main | 83 · 87 · 353 | 380 · 54 · 2,229 | 535 · 39 · 4,728 | 539 · 32 · 18,540 | 529 · 32 · 38,804 | 558 · 33 · 40,843 |

- The largest level inside the MLPerf server SLO (p99 TTFT ≤ 2 s, p99 TPOT ≤ 100 ms) **is 1**, and the same holds for the interactive SLO. At 8 the p99 first token is 2.2 s (`largest_level_in_server_slo`).
- The fresh container at 64 and 128 gave 534 and 551 tok/s.
- Anchors against P59 range from 0.930 to 1.019 (`anchors_vs_p59`).

## N-FP8 · RAG conclusion: **null** (calibration failed, with no prefix-cache hits)

AIPerf p50 TTFT was 224 ms against the harness's own 163 ms; inter-token latency agreed (7.11 against 7.19 ms). Every calibration request showed at most 0.9% hits. **So the gap P59 saw is not a cached prefix.**

**Where the gap sits** (`server_side_reading.arms`, reported and not a gate). The server's own TTFT histogram was read for both sets of requests:

| | N-BF16 | N-FP8 |
|---|---|---|
| harness's prompts (nonce, then one sentence repeated; 3,501 client tokens) · client p50 TTFT | 320 ms | 163 ms |
| same requests · **server's own** TTFT (median of per-request means) | 309 ms | **138 ms** |
| AIPerf's c=1 prompts (synthetic text, 3,500 ± 300 tokens) · AIPerf p50 / mean TTFT | 306 / 304 ms | 224 / 224 ms |
| same requests · **server's own** mean TTFT | 302 ms | **220 ms** |

AIPerf agrees with the server on both arms: within 2 ms on N-BF16 and 5 ms on N-FP8. On N-BF16 the two prompt sets take the same time on the server. On N-FP8 the server takes 138 ms for the harness's prompts and 220 ms for AIPerf's, at about the same length. **The gap is in the server, not in either client, and it depends on the prompt content on the FP8 arm only.** Why it depends on content cannot be determined from this run.

The pre-registered rule (P59's calibration) makes N-FP8's RAG conclusion null, and it stays null.

**Secondary table, not the conclusion** (`rag.N-FP8.secondary_not_the_conclusion`). It is listed because AIPerf agrees with the server (pre-registered). The format is the same as above, and c=128 is excluded for the hits.

| c | 1 | 8 | 16 | 32 | 64 |
|---|---|---|---|---|---|
| main | 132 · 141 · 250 | 600 · 83 · 968 | 800 · 57 · 2,194 | 942 · 35 · 4,450 | 895 · 31 · 20,314 |

In this table the largest level inside the server SLO is 8, and inside the interactive SLO it is 1. The fresh container gave 893 and 904 tok/s at 64 and 128.

**What this means for P59's RAG calibrations.** P59's calibration compared AIPerf's synthetic prompts with the harness's repeated-sentence prompts. On the N-FP8 arm those two do not cost the server the same, so the comparison mixed prompt content with instrument error. The other P59 arms passed that comparison. This run does not re-examine them.

## Predictions (`prediction_p62_rag.json` → `predictions`)

| # | Prediction | Result |
|---|---|---|
| Q3-1 | positive control fires on every container | ✅ 4 / 4 (99.5–99.9%) |
| Q3-2 | every calibration request and every level ≤ 2% hits | ❌ N-FP8 c=128 main 4.0%; everything else ≤ 0.9% |
| Q3-3 | N-BF16 calibration passes | ✅ |
| Q3-4 | N-FP8 calibration fails again, no hits (already seen in the harness tests) | ✅ |
| Q3-4b | N-FP8: AIPerf agrees with the server; the server is faster on the harness's prompts | ✅ 224 / 220 ms; 138 against 220 ms |
| Q3-5 | largest server-SLO level: N-BF16 1, N-FP8 8 | ✅ N-BF16 1; N-FP8 8 in the secondary table only (its conclusion is null) |
| Q3-6 | N-FP8 ahead of N-BF16 on R total throughput at every level | not evaluable: N-FP8's conclusion is null (in the secondary table it is ahead at every level) |
| Q3-7 | N-BF16 anchors within 0.85–1.15 of P59 | ✅ 0.930–1.019 |

## Files

| File | What |
|---|---|
| `prediction_p62_rag.json` · `.sha256` · `prediction_scan.txt` · `harness_test_record.json` | pre-registration and its records |
| `levels.jsonl` · `prefix_cache_levels.jsonl` | per level: AIPerf summary; counter deltas and AIPerf's server-metrics reading |
| `events_public.jsonl` | detector, calibration (per request, with counters and the server's own TTFT), gates. The raw desktop-process list is replaced by counts; `analysis.json` recomputes byte for byte from it. |
| `analysis.json` · `e2e_per_user.json` | analysis; end-to-end per-user speed |
| `<arm>_<profile>_<container>/c<nnnn>/profile_export_aiperf.json`, `server_metrics_export.json` | AIPerf's per-level summary and server-metrics export. The local home prefix is replaced by `<HOME>` (`deidentification_ledger.json`); the analysis is identical on the originals. |
