# Vol.3 · The Safety Guard verdicts on two servers: a second, separately pre-registered look

*Working data, 2026-10-08, 11:24 to 11:41 (+0800). One RTX 5090 (32 GB), Windows 11 with Docker Desktop (WSL2), graphics driver 610.88; one model on the card at a time; the idle-card gate passed before every container and every cell; no game launcher was running. Aegis 2.0 test split and XSTest; the model card's prompt, `max_tokens` 100, temperature 0.0, context 8,192; one run per cell.*

**Why a second look.** The first ([`../model_free_nim/`](../model_free_nim/README.md)) asked that four rates of the generic NIM differ from the upstream server's by at most 0.5 points, and one of them came to 0.51: that criterion did not pass, and it is reported as not passed wherever this cell is reported. The repository already held three runs of the upstream server alone, and between two of them the same rate differs by more than that limit. This cell asks the question again with an allowance taken from that movement, a paired test of direction, and the upstream server measured twice in the session, before and after the NIM. The first look's files are unchanged.

Pre-registration: [`prediction_safety_guard_recheck.json`](prediction_safety_guard_recheck.json), frozen 2026-10-08T11:23:04+0800, SHA-256 `e633b4c05b9552e8463f15ad05214619e561f971e281de9a23911872b3d12116`; the first container started at 2026-10-08T03:24:19Z, after it.

## The three arms

| Arm | Served by | Engine version the server reports | NIM version · profile | Ready after | Card once ready |
|---|---|---|---|---|---|
| U1 | `vllm/vllm-openai:v0.20.2` | 0.20.2 | — | 160 s | 31,440 MiB |
| M | `nvcr.io/nim/nvidia/model-free-nim:2.0.12` | 0.27.1 | 2.0.12 · `d655bc3a760b0d20b2ce2e638bb8212015e1a564bdcdc6f1642fdc4d9619f000` (vllm-tp1-pp1) | 182 s | 30,526 MiB |
| U2 | `vllm/vllm-openai:v0.20.2` | 0.20.2 | — | 139 s | 31,441 MiB |

U1 and U2 are two containers of one image and one command (the study's arm J6); M ran between them with the command that ran as arm J6M in the first look. Per arm and track: the precheck, then the whole track at 16 concurrent requests.

| Arm | Track | Harmful flagged | Harmless flagged | Verdicts per second at 16 | Against the upstream arm of 2026-10-08 |
|---|---|---|---|---|---|
| U1 | prompts | 87.7% (911/1039) | 15.7% (140/889) | 46.9 | +0.4% |
| U1 | responses | 87.8% (346/394) | 14.3% (60/419) | 29.2 | -1.9% |
| M | prompts | 87.2% (906/1039) | 15.5% (138/889) | 47.6 | +1.7% |
| M | responses | 88.1% (347/394) | 14.1% (59/419) | 29.2 | -1.7% |
| U2 | prompts | 87.6% (910/1039) | 15.6% (139/889) | 47.0 | +0.5% |
| U2 | responses | 87.3% (344/394) | 13.8% (58/419) | 29.2 | -1.7% |

## The criteria

**Outcome: C1 or C2 does not pass.** C1 **does not pass**, C2 **passes**, C3 **passes**; the session is valid and the two upstream containers pass the sanity check.

| Check | Measured | Result |
|---|---|---|
| Validity: U1 and U2 each within 5% of the upstream arm's rate of 2026-10-08 | U1 +0.4% · -1.9%; U2 +0.5% · -1.7% | **passes** |
| Sanity: U1 against U2, the test of C2 and the share of C3 | prompts: 4 to 2 of the differing Aegis items, p = 0.688, same verdict on 99.67%; responses: 6 to 2 of the differing Aegis items, p = 0.289, same verdict on 99.02% | **passes** |
| C1 · prompts · harmful flagged: M within T of the mean of U1 and U2 | U1 87.68% · M 87.20% · U2 87.58%; M is 0.43 points below the mean; T = 0.29 (D_hist) | **outside** |
| C1 · prompts · harmless flagged: M within T of the mean of U1 and U2 | U1 15.75% · M 15.52% · U2 15.64%; M is 0.17 points below the mean; T = 0.22 (D_hist) | within |
| C1 · responses · harmful flagged: M within T of the mean of U1 and U2 | U1 87.82% · M 88.07% · U2 87.31%; M is 0.51 points above the mean; T = 0.76 (D_hist) | within |
| C1 · responses · harmless flagged: M within T of the mean of U1 and U2 | U1 14.32% · M 14.08% · U2 13.84%; M is 0.00 points above the mean; T = 0.48 (D_hist) | within |
| C1, the four together | | **does not pass** |
| C2 · M against U1, prompts (Aegis items) | of 1,928 items the verdicts differ on 11: unsafe only on M 2, only on U1 9; p = 0.065 | at least 0.0125 |
| C2 · M against U1, responses (Aegis items) | of 813 items the verdicts differ on 6: unsafe only on M 3, only on U1 3; p = 1.000 | at least 0.0125 |
| C2 · M against U2, prompts (Aegis items) | of 1,928 items the verdicts differ on 9: unsafe only on M 2, only on U2 7; p = 0.180 | at least 0.0125 |
| C2 · M against U2, responses (Aegis items) | of 813 items the verdicts differ on 6: unsafe only on M 5, only on U2 1; p = 0.219 | at least 0.0125 |
| C2, the four together | | **passes** |
| C3 · the same verdict on at least 99% of each track's items | M and U1, prompts: 2,411 of 2,423 (99.50%); M and U1, responses: 807 of 813 (99.26%); M and U2, prompts: 2,413 of 2,423 (99.59%); M and U2, responses: 807 of 813 (99.26%) | **passes** |
| XSTest, reported and not judged | M against U1: unsafe only on M 1, only on U1 0, p = 1.000; M against U2: unsafe only on M 0, only on U2 1, p = 1.000 | — |

**What the pre-registration ties to this outcome:** the NIM 2.0.12 row stays (its rate is a separate finding); every statement that the verdicts are the same is removed from the article and replaced by what was measured: how large the difference is and in which direction

## The allowance, and what was known about the criteria before the freeze

`T = max(D_hist, |U1 - U2|)` per rate. `D_hist` is the largest difference between any two of the three earlier runs of the upstream arm, computed and written into the pre-registration before the freeze:

| Rate | 2 October · 6 October · 8 October (flagged of) | Largest difference between two of them, points |
|---|---|---|
| prompts · harmful flagged | 912 · 911 · 909 of 1,039 | 0.29 |
| prompts · harmless flagged | 137 · 136 · 138 of 889 | 0.22 |
| responses · harmful flagged | 347 · 344 · 345 of 394 | 0.76 |
| responses · harmless flagged | 58 · 59 · 57 of 419 | 0.48 |

**The allowance is not a bound on the next difference.** Before the freeze the criteria were run on 20,000 simulated sessions in which M is nothing but one more run of the upstream server ([`before_the_run/null_simulation.json`](before_the_run/null_simulation.json); the model and its one input from data are stated in [`../../scripts/safety_guard_recheck_null_simulation.py`](../../scripts/safety_guard_recheck_null_simulation.py)): C1 fails in 28% of them, C2 in 0.8%. The allowance was kept as set; the pre-registration says how a failure of C1 alone is to be read. C2 is the check whose error rate is the one it states.

**Checks that had to fail, and did** ([`before_the_run/positive_controls.json`](before_the_run/positive_controls.json)): an existing file with 10 verdicts turned one way gives p = 0.0020 in C2 on each track; with 8 harmful responses turned it differs by 2.03 points against an allowance of 0.76 in C1. On two real upstream arms of the first look (vLLM 0.20.2 and 0.27.1) the test of C2 gives p = 0.180 and 0.219.

## Files

| File | What it is |
|---|---|
| `prediction_safety_guard_recheck.json` (with its `.sha256`) | the allowance, the criteria, the expectations and the disposition, set beforehand |
| `before_the_run/positive_controls.json` · `before_the_run/null_simulation.json` | the checks on existing files and the simulated sessions, both before the freeze |
| `events.jsonl` | every step as it happened |
| `U1/` · `M/` · `U2/` | per arm: `cells.jsonl`, per-item verdict files without text, `summary.json` with the arm's label |
| `criteria.json` · `table.json` · `table.md` | every check with its numbers; the three arms side by side |

Programs: [`../../scripts/safety_guard_recheck_run.py`](../../scripts/safety_guard_recheck_run.py), [`safety_guard_recheck_summary.py`](../../scripts/safety_guard_recheck_summary.py); every cell is the study's unchanged `p93_judge.py --arm J6`, every container is started by the first look's frozen functions.

## What this does not show

- One session, one container of the NIM, two of the upstream server. The per-item verdicts of two arms are set side by side here for one model on two servers, and for the two upstream containers; nowhere else in this volume.
- The allowance comes from three earlier runs and one pair of this session: four differences per rate.
- Nothing about the model's own NIM 1.14.0, about upstream vLLM 0.27.1, about the rail, or about one request at a time: the first look has those.
