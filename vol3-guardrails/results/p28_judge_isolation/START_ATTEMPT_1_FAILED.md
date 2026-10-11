# P28 · start attempt 1 failed — the container did not start, no judgement was made

> **Correction (2026-09-17): the explanation below is wrong and is kept only as the record of what was believed at the time.** The cause of every failed start was the profile value passed to NIM: the v1 pre-registration stored the profile id followed by the display suffix that `list-model-profiles` prints, and NIM matched neither the id nor the description. Free GPU memory played no part. With the bare 64-hex id (v2) the container started on the first attempt. See `PREDICTION_V1_SUPERSEDED.md`.

2026-09-16 16:22:25 → 16:22:59. `judgements.jsonl` was never created; the measurement did not begin. The frozen
prediction (`prediction_p28.json`, sha256 `0fe2786e…`) and corpus (`corpus.sha256`) are unchanged.

NIM refused the pinned profile:

```
ERROR actions.py:120] Model download failed: Environment variable NIM_MODEL_PROFILE is set to
092ed4213624e774d24cdaf84e3b6222839bab2008a21d3c214ab46626366f90 (vllm-bf16-tp1-pp1), but no matching
profile_id or profile description is found in manifest.
```

`list-model-profiles` on the same image, minutes later (`list_model_profiles_at_failure.txt`):

```
- Free GPUs: <None>
- Compatible with system and runnable: <None>
- Compatible with system but low memory:
    - 092ed421… (vllm-bf16-tp1-pp1-33.0) [requires >=33 GB/gpu, try --max-model-len=84992 to reduce to >=28 GB/gpu]
    …
```

The profile is present in the manifest; NIM classified it as not runnable because of free GPU memory, and the pinned
profile then resolves to nothing. Today's starts of the same image, same profile, same env:

| start | desktop GPU memory in use | free | result |
|---|---|---|---|
| 12:53 (P19) | 2,537 MiB | 30,070 MiB | READY |
| 15:51 (P28 plumbing test) | 2,691 MiB | 29,916 MiB | READY |
| **16:22 (this attempt)** | **2,761 MiB** | **29,846 MiB** | **profile not runnable** |

The threshold lies between 29,916 and 29,846 MiB free. Desktop use rose from 2,537 to 2,836 MiB over three and a half
hours (Explorer, Search, Start menu, the NVIDIA App overlay), so whether this container starts is decided by the
desktop, not by the measurement. This is the same shape as the E6 window threshold, on NIM's side of the line.

Nothing was changed to work around it: lowering `--max-model-len`, unpinning the profile or choosing an FP8/NVFP4
profile would each alter the stack that cell ④, P19 and this run are supposed to share.

---

The context files of this attempt (`idle_baseline.txt`, `ctx_before.txt`, `ctx_after.txt`, `console.txt`, `list_model_profiles_at_failure.txt`) were moved into `start_attempt_1/` on 2026-09-16 before the second start, because `run_p28.sh` appends to `idle_baseline.txt` and the two attempts would otherwise share one file. The log directory `logs/p28_20260916T162225/` is already named by run and was not moved.
