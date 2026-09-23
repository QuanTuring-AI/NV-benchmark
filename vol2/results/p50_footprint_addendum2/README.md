# Footprint addendum 2 · Nemotron 3 Nano (NVFP4) with vLLM `max_num_seqs 32` via `NIM_PASSTHROUGH_ARGS` (run 2026-09-21)

**Why.** The main run's A2 floor (`../p50_footprint/`) was set by the Mamba state cache for the engine's default 256 sequences; addendum 1 showed `NIM_MAX_BATCH_SIZE` does not change that number in NIM 2.0.12. In this image `max_num_seqs` is a per-profile engine argument and `NIM_PASSTHROUGH_ARGS` is the path for user engine arguments (`nim_llm/config/system_config.py`, parsed with `shlex` at PASSTHROUGH priority). This run repeated the sweep with `NIM_PASSTHROUGH_ARGS="--max-num-seqs 32"`, the same limit A1 ran with (`NIM_MAX_NUM_SEQS=32`). Pre-registration `prediction_p50_footprint_addendum2.json`, frozen before the run.

| Budget (share · MiB) | READY? | Probe | Memory at READY (MiB) | Added over pre-launch | KV tokens | KV tokens in the main run at the same budget | Failure text |
|---|---|---|---|---|---|---|---|
| default (0.92 · 29,998) | yes | stop ×3 | 29,850 | 29,511 | 3,067,904 | 3,002,368 | |
| 0.85 · 27,716 | yes | stop ×3 | 28,400 | 28,052 | 2,347,008 | 2,236,416 | |
| 0.80 · 26,086 | yes | stop ×3 | 26,766 | 26,413 | 1,802,240 | 1,691,648 | |
| 0.75 · 24,455 | yes | stop ×3 | 25,134 | 24,784 | 1,257,472 | 1,146,880 | |
| 0.70 · 22,825 | yes | stop ×3 | 23,520 | 23,170 | 667,648 | refused (Mamba blocks 146) | |
| **0.65 · 21,195** | **yes** | **stop ×3** | **21,872** | **21,519** | **163,840** | — | |
| 0.625 · 20,379 | no | — | — | — | — | — | `No available memory for the cache blocks` |
| 0.60 · 19,564 | no | — | — | — | — | — | same |

**The setting reached the engine.** Two independent signs: at every budget the KV cache grew by about 65,000–110,000 tokens over the main run (the Mamba state for 224 fewer sequences was released to it), and the refusal below the floor changed from a Mamba-block refusal to a KV-block refusal. The startup log does not print the resolved `max_num_seqs` (`resolved_max_num_seqs.txt` is empty for every start), so the value is inferred from those two effects, not read.

Pre-registered: **R1** the resolved `max_num_seqs` is visible in the log — **failed** (not printed). **R2** floor at most 0.70 — held (0.65). **R3** first refusal below the floor is a KV-block refusal — held.

**Floor at 32 sequences: 0.65 of the card = 21,195 MiB budget, 21,872 MiB in use at READY, with 163,840 KV tokens (40 × 4,096).** Against the main run's 0.75 at 256 sequences, the per-sequence Mamba state of this model accounts for about 3,260 MiB of budget for 224 sequences, roughly 14.6 MiB per sequence. Analysis in `analysis.json` (rows carry `arm_as_run = A2S32`, analysed under the A2 label).
