# Footprint addendum · Nemotron 3 Nano (NVFP4) with `NIM_MAX_BATCH_SIZE=32` (run 2026-09-21)

**Why.** In the main run (`../p50_footprint/`) A2's floor was set by the Mamba state cache for the engine's default 256 sequences ("max_num_seqs (256) exceeds available Mamba cache blocks"), not by the KV cache. A single-user deployment does not reserve state for 256 sequences, so this addendum repeated the same sweep with `NIM_MAX_BATCH_SIZE=32`, the NIM 2.0.12 variable named for the batch limit. Pre-registration `prediction_p50_footprint_addendum.json`, frozen before the run.

**Result: the variable had no effect on this profile.** Every start reproduced the main run to within the desktop's memory noise, and the two refusals name the same limit:

| Budget (share · MiB) | READY? | Probe | Memory at READY (MiB) | KV tokens | Failure text |
|---|---|---|---|---|---|
| default (0.92 · 29,998) | yes | stop ×3 | 31,688 | 3,002,368 | |
| 0.85 · 27,716 | yes | stop ×3 | 29,386 | 2,236,416 | |
| 0.80 · 26,086 | yes | stop ×3 | 27,830 | 1,691,648 | |
| **0.75 · 24,455** | **yes** | **stop ×3** | **26,166** | **1,146,880** | |
| 0.725 · 23,640 | no | — | — | — | `max_num_seqs (256) exceeds available Mamba cache blocks (213)` |
| 0.70 · 22,825 | no | — | — | — | `max_num_seqs (256) exceeds available Mamba cache blocks (146)` |

The engine still resolved `max_num_seqs` to 256; the startup log contains no line acknowledging `NIM_MAX_BATCH_SIZE`. The image's code reads the variable (`nimlib/env.py`) and warns, for profiles that do not support it, that the profile is skipped — this profile was not skipped and the value was not applied. Which variable sets `max_num_seqs` in NIM 2.0.12 for this profile is recorded in the main README once established; until then, **A2's 24.5 GB floor is the floor of a server sized for 256 sequences**, and the single-user floor is not measured.

Pre-registered: **R1** floor at most 0.70 — **failed** (0.75). **R2** first failure below the floor is a KV-block refusal — **failed** (Mamba-block refusal, as before). Both failures are the same fact: the setting did not reach the engine. Analysis in `analysis.json` (rows carry `arm_as_run = A2B32`, analysed under the A2 label).

Mamba cache blocks scale with the budget: 146 at 0.70, 213 at 0.725; by that slope the default 256 sequences need about 0.74 of the card — consistent with 0.75 passing.
