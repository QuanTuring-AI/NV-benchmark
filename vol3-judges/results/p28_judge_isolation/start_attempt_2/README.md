# P28 start attempt 2 — container exited before the judge ran

> **Correction (2026-09-17): the explanation below is wrong and is kept only as the record of what was believed at the time.** The cause of every failed start was the profile value passed to NIM: the v1 pre-registration stored the profile id followed by the display suffix that `list-model-profiles` prints, and NIM matched neither the id nor the description. Free GPU memory played no part. With the bare 64-hex id (v2) the container started on the first attempt. See `PREDICTION_V1_SUPERSEDED.md`.

- 2026-09-16 21:12:09 start gate PASS (free samples 30123 / 30102 / 30118 MiB; `start_gate.txt`).
- 21:12:37 NIM: `Model download failed: Environment variable NIM_MODEL_PROFILE is set to 092ed421… (vllm-bf16-tp1-pp1), but no matching profile_id or profile description is found in manifest.` Container exited 21:12:44; the harness never started, `judgements.jsonl` was not created. Logs: `logs/p28_20260916T211210/`.
- Diagnostics afterwards, same image, same pinned profile, same `NIM_MAX_MODEL_LEN` and `VLLM_USE_V2_MODEL_RUNNER`, same cache mount, no harness:
  - 21:16 with `NIM_LOG_LEVEL=DEBUG` (no `-d`, no `-p`): the env profile selector matched the pinned profile and loading began (log kept locally, outside version control); stopped by hand.
  - 21:20 identical to `run_p28.sh` except the container name: passed profile selection (log kept locally, outside version control); removed by hand.
  - Host free memory at both diagnostics: 30,126 MiB.
- NIM's own free-memory reading inside the container equals the host figure (29.42 GiB = 30,126 MiB), so the host figure is the quantity NIM uses.
- What this does to the afternoon's explanation: a free-memory boundary between 29,916 and 29,846 MiB is **not supported**. 12:53 started at 30,070, 21:12 failed at 30,102, 21:16 and 21:20 passed at 30,126. Either the boundary is narrower than the resolution of these observations and moves, or the failure is intermittent. The cause is not established.
