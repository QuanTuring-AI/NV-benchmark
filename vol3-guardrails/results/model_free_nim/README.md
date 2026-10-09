# Vol.3 · The Safety Guard 8B v3 weights in the generic NIM container, with three partners the same night

*Working data, 2026-10-08, 03:10 to 03:56 (+0800). One RTX 5090 (32 GB), Windows 11 with Docker Desktop (WSL2), graphics driver 610.88; one model on the card at a time; the idle-card gate passed before every container and every cell. Aegis 2.0 test split (1,928 prompts, 813 prompt and response pairs) and XSTest (450 prompts); the model card's prompt, `max_tokens` 100, temperature 0.0, context 8192; one run per cell.*

**The question.** The model's own NIM (1.14.0) gave about a fifth fewer verdicts per second than upstream vLLM 0.20.2 on this card ([`../safety_guard_nim/`](../safety_guard_nim/README.md)), and upstream vLLM 0.10.0 came within 4% of that NIM ([`../parser_and_engine_version/`](../parser_and_engine_version/README.md)). Does the same weight directory, served by the generic NIM container of the 2.x line, give upstream's rate and the same verdicts?

| Set beforehand | File | Frozen | SHA-256 |
|---|---|---|---|
| pre-registration: four criteria and the branches tied to them | [`prediction_model_free_nim.json`](prediction_model_free_nim.json) | 2026-10-07T23:10:07+0800 | `2953204441cfd056aada6dda1ac22393c7abe8de691e9ef89729631c1eafa2ec` |
| addendum: one more arm, two more criteria, and their disposition | [`addendum_same_engine_arm.json`](addendum_same_engine_arm.json) | 2026-10-08T03:08:33+0800 | `e7f4e2395554f3f2cc87a898d175deeccf7594c3674c809195f3243bb62db68f` |

The first serving container started at 2026-10-07T19:11:49Z, which is 03:11:49 (+0800), after both files. Read beforehand ([`before_the_run/`](before_the_run/facts_read_before_the_run.json)): the generic image `nvcr.io/nim/nvidia/model-free-nim:2.0.12` ships vLLM 0.27.1, newer than the upstream arm of this volume (0.20.2). The addendum exists because of that: the registered speed criterion is two-sided, and it would have failed for an arm that is faster.

## The four arms

| Arm | Served by | Engine version the server reports | Profile | Start setting that ran | Ready after | Card once ready |
|---|---|---|---|---|---|---|
| J6-tonight | `vllm/vllm-openai:v0.20.2` | 0.20.2 | — | upstream vLLM | 166 s | 31,893 MiB |
| J6-v0271 | `vllm/vllm-openai:v0.27.1` | 0.27.1 | — | with_the_v1_model_runner | 192 s | 30,786 MiB |
| J6M | `nvcr.io/nim/nvidia/model-free-nim:2.0.12` | 0.27.1 | `d655bc3a760b0d20b2ce2e638bb8212015e1a564bdcdc6f1642fdc4d9619f000` (vllm-tp1-pp1), chosen by the image | with_the_v1_model_runner | 208 s | 30,433 MiB |
| J6N-tonight | `nvcr.io/nim/nvidia/llama-3.1-nemotron-safety-guard-8b-v3:1.14.0` | not reported by this server (its start log of 2026-10-06 names vLLM 0.10.0: [`../safety_guard_nim/`](../safety_guard_nim/README.md)) | `47804570e8db67fdc60d9cb518b0f60316ac4eb0f3a55af81aafefe124505a8f`, pinned | generic profile of the model's NIM | 182 s | 31,808 MiB |

The engine version and the profile are what each server answered on `/version` and `/v1/metadata` after it was ready (kept in `events.jsonl`, kind `warm_up`); the arm labels inside the `summary.json` files leave two of their fields empty for that reason: the start logs do not print the version in the form the label looks for, and the 2.x NIM names its profile under another key than the 1.x one.

Cells per arm: on each track a precheck, one request at a time on the 200-item subset, 16 concurrent requests on the whole track. J6M also ran the content-safety rail cell (100 items per track) and, in a new container, the stability subset.

| Arm | Track | Harmful flagged | Harmless flagged | Median ms, one at a time | Verdicts per second at 16 | p99 ms at 16 | Rate against J6-tonight | against J6-v0271 |
|---|---|---|---|---|---|---|---|---|
| J6-tonight | prompts | 87.5% (909/1039) | 15.5% (138/889) | 202.5 | **46.8** | 730.0 | +0.0% | -0.7% |
| J6-tonight | responses | 87.6% (345/394) | 13.6% (57/419) | 294.2 | **29.7** | 850.3 | +0.0% | -1.0% |
| J6-v0271 | prompts | 87.9% (913/1039) | 15.6% (139/889) | 198.8 | **47.1** | 727.2 | +0.8% | +0.0% |
| J6-v0271 | responses | 87.6% (345/394) | 14.6% (61/419) | 297.1 | **30.0** | 844.2 | +1.0% | +0.0% |
| J6M | prompts | 87.7% (911/1039) | 15.6% (139/889) | 206.5 | **46.8** | 724.5 | +0.2% | -0.6% |
| J6M | responses | 88.1% (347/394) | 14.1% (59/419) | 296.8 | **30.1** | 824.2 | +1.4% | +0.4% |
| J6N-tonight | prompts | 87.7% (911/1039) | 15.6% (139/889) | 221.9 | **38.9** | 882.9 | -16.9% | -17.5% |
| J6N-tonight | responses | 87.6% (345/394) | 14.3% (60/419) | 329.1 | **24.6** | 1065.1 | -17.1% | -17.9% |

- **J6M runs at upstream's rate.** Against upstream vLLM 0.20.2 the same night: +0.2% on prompts, +1.4% on responses. Against upstream vLLM 0.27.1, the engine version it ships: -0.6% and +0.4%.
- **The model's own NIM 1.14.0 is where the fifth goes.** J6N-tonight against J6-tonight: -16.9% and -17.1%; against its own figures of 2026-10-06 it moved by less than 1%.
- The two upstream versions give the same rate on this model: J6-v0271 against J6-tonight +0.8% and +1.0%.

## The criteria, as registered

| Criterion | Measured | Result |
|---|---|---|
| Speed: J6M within 5% of J6-tonight on both tracks | +0.18% · +1.40% (J6M is above on both) | **passes** |
| Verdicts, first half: the same verdict on at least 99% of the items of each track | 2,414 of 2,423 (99.63%) · 809 of 813 (99.51%) | within the limit |
| Verdicts, second half: Aegis 2.0 detection and false-alarm rates differ by at most 0.5 points | prompts 0.19 and 0.11 · responses **0.51** and 0.48 | one of the four is above the limit |
| Verdicts, both halves together | | **does not pass** |
| Rail: decision and verdict of the same call agree on at least 199 of 200 calls | 200 of 200 | **passes** |
| Validity of the night: J6-tonight within 5% of J6-today (2026-10-06) | -1.57% · -2.46% | **passes** |
| Addendum: J6M at least 95% of J6-tonight's rate on both tracks | 100.2% · 101.4% | **passes** |
| Addendum: J6M within 5% of J6-v0271 on both tracks | -0.57% · +0.40% | **passes** |

**Branch B, by the registered rule and by the addendum's table alike** (`criteria.json`, `criteria_addendum.json`). The verdicts criterion does not pass, by one of its four rate differences: on the responses J6M flagged 347 of the 394 harmful items and J6-tonight 345, a difference of 0.51 points against a limit of 0.5. One item of that set is 0.25 points, so the limit allows a difference of one item and two were measured. Every other figure of the cell is inside its limit.

**The arm is kept in the article despite this; the deviation and its reason are stated there.** By the registered branch the NIM arm would have left the figures of this volume. The people who write the article decided on 2026-10-08 to keep it, as arm J6M, and to say so: the criterion is reported as not passed, here and there, and nothing in the pre-registration, the addendum or `criteria.json` was changed. A second, separately pre-registered look at the same question, with an allowance taken from the measured movement and a paired test, is in [`../safety_guard_recheck/`](../safety_guard_recheck/README.md).

### How far the same server moves between nights

The limit of 0.5 points was set without first being held against what the repository already showed. These are the same four rates between runs that differ in less than J6M and J6-tonight do; each figure is the difference of two arms' own summaries.

| Pair | What differs | Prompts: detection · false alarm | Responses: detection · false alarm | Largest |
|---|---|---|---|---|
| J6-today (6 Oct) and J6 (2 Oct) | the night and the driver; the same image and command | 0.10 · 0.11 | 0.76 · 0.24 | 0.76 (above 0.5) |
| J6-tonight (8 Oct) and J6-today (6 Oct) | the night; the same image, command and driver | 0.19 · 0.22 | 0.25 · 0.48 | 0.48 |
| J6-tonight and J6 (2 Oct) | the night and the driver | 0.29 · 0.11 | 0.51 · 0.24 | 0.51 (above 0.5) |
| J6-v0271 and J6-tonight | the upstream version, the same night | 0.38 · 0.11 | 0.00 · 0.95 | 0.95 (above 0.5) |
| J6N-tonight and J6-tonight | the model's NIM 1.14.0 for upstream, the same night | 0.19 · 0.11 | 0.00 · 0.72 | 0.72 (above 0.5) |
| **J6M and J6-tonight** | the generic NIM 2.0.12 for upstream, the same night | 0.19 · 0.11 | 0.51 · 0.48 | 0.51 (above 0.5) |
| J6M and J6-v0271 | the NIM around the same engine version, the same night | 0.19 · 0.00 | 0.51 · 0.48 | 0.51 (above 0.5) |

The upstream server compared with itself on another night is above 0.5 points in two of three pairs. The second half of the verdicts criterion therefore cannot tell a server that changes verdicts from the run-to-run movement of one server; what J6M's failure of it shows is that movement, of the size the other pairs have. The criterion stays as registered and is reported as failed. Whether the branch it selects is the one to act on is for the people who write the article; the file changes nothing about it.

## What had to be set to make each arm run

| Arm | Container command, beyond image and model | Tried first | Outcome of the first try | What ran |
|---|---|---|---|---|
| J6-tonight | `--served-model-name llama-3.1-nemotron-safety-guard-8b-v3` · `--max-model-len 8192` | upstream vLLM | ready | upstream vLLM |
| J6-v0271 | `VLLM_USE_V2_MODEL_RUNNER=0` · `--served-model-name llama-3.1-nemotron-safety-guard-8b-v3` · `--max-model-len 8192` | as_J6-tonight | not ready after 38 s: `(EngineCore pid=142) RuntimeError: UVA is not available` | with_the_v1_model_runner |
| J6M | `--shm-size=64GB` · `NIM_MODEL_PATH=/model` · `NIM_SERVED_MODEL_NAME=llama-3.1-nemotron-safety-guard-8b-v3` · `NIM_MAX_MODEL_LEN=8192` · `VLLM_USE_V2_MODEL_RUNNER=0` | as_documented | not ready after 44 s: `(EngineCore pid=182) RuntimeError: UVA is not available` | with_the_v1_model_runner |
| J6N-tonight | `--shm-size=64GB` · `NIM_MODEL_PROFILE=47804570…` · `NIM_MAX_MODEL_LEN=8192` | generic profile of the model's NIM | ready | generic profile of the model's NIM |

- **`VLLM_USE_V2_MODEL_RUNNER=0` was needed by both containers that carry vLLM 0.27.1** (J6M and J6-v0271), after the same error; the two therefore ran with the same setting, and J6M against J6-v0271 differs in the NIM around the engine and in nothing else that was set. J6-tonight (vLLM 0.20.2) ran without it: between J6M and J6-tonight the setting is a second difference beside the engine version, and it could not be made equal (0.20.2 starts without it; 0.27.1 does not start without it on this host).
- `--shm-size=64GB` is on the two NIM commands and not on the two upstream ones, as in the earlier arms of this volume. The context is 8,192 tokens in all four (`NIM_MAX_MODEL_LEN` or `--max-model-len`).
- Not changed: the model directory (no file added, no chat template written), the request parameters, the client program.

**The generic NIM's own listing** for this model directory on this card ([`list_model_profiles.txt`](list_model_profiles.txt)) has no profile under "compatible and runnable"; the single-GPU profile `vllm-tp1-pp1` is under "compatible with system but low memory", with an estimate for the model's full context. With the context set to 8,192 tokens the container started that profile and used the card as the table above shows.

Start it (the model directory mounted read-only; with a local path the documentation says no credentials are needed, and none were read here: the key file is passed by path as for every NIM of this repository):

```bash
docker run -d --name mfnim_j6m_main --gpus all --shm-size=64GB -p 127.0.0.1:8000:8000 \
  --env-file $NGC_ENV_FILE \
  -e NIM_MODEL_PATH=/model \
  -e NIM_SERVED_MODEL_NAME=llama-3.1-nemotron-safety-guard-8b-v3 \
  -e NIM_MAX_MODEL_LEN=8192 \
  -e VLLM_USE_V2_MODEL_RUNNER=0 \
  -v $P93_HF_HUB/models--nvidia--Llama-3.1-Nemotron-Safety-Guard-8B-v3/snapshots/8fdc246ba3d56db9c469d534233b9f582d3afafa:/model:ro \
  -v $NIM_CACHE_DIR:/opt/nim/.cache nvcr.io/nim/nvidia/model-free-nim:2.0.12
```

## Weights, rail, stability

- **Weights.** 4 `*.safetensors` files, compared by SHA-256 between the local model directory (read by J6M, J6-tonight and J6-v0271 through one mount) and the NIM 1.14.0 cache (read by J6N-tonight): the same bytes in every file ([`weights_sha256.json`](weights_sha256.json)). The NIM cache holds its files as links written from inside a Linux container; the table says how each entry was resolved.
- **Rail.** J6M behind the NeMo Guardrails content-safety rail, configured as for arm J6G: the rail's decision and the verdict of the same call agree on 100 of 100 prompts and 100 of 100 responses ([`J6M-rail/`](J6M-rail/)).
- **Stability.** In a new container J6M gave the same outcome on 200 of 200 prompts and 98 of 100 responses.

## Files

| File | What it is |
|---|---|
| `prediction_model_free_nim.json` · `addendum_same_engine_arm.json` (each with its `.sha256`) | what was set beforehand |
| `before_the_run/facts_read_before_the_run.json` | documentation pages, registry tags and the image's own facts, read before the pre-registration |
| `events.jsonl` | every step as it happened: gates, container starts with their commands and start-log lines, prechecks, cells |
| `J6-tonight/` · `J6-v0271/` · `J6M/` · `J6N-tonight/` | per arm: `cells.jsonl`, per-item verdict files without text, `summary.json` with the arm's label |
| `J6M-rail/` | the rail cell: configuration, per-item rail decision and verdict, `summary.json` |
| `criteria.json` · `table.json` · `table.md` | the registered criteria and the branch, by the cell's own program |
| `criteria_addendum.json` · `table_addendum.json` · `table_addendum.md` | the addendum's criteria and its disposition; the four arms side by side |
| `weights_sha256.json` · `list_model_profiles.txt` | the weight comparison; the generic image's profile listing |

Programs: [`../../scripts/model_free_nim_run.py`](../../scripts/model_free_nim_run.py), [`model_free_nim_summary.py`](../../scripts/model_free_nim_summary.py), [`model_free_nim_addendum_run.py`](../../scripts/model_free_nim_addendum_run.py), [`model_free_nim_addendum_summary.py`](../../scripts/model_free_nim_addendum_summary.py); every cell is the study's unchanged `p93_judge.py --arm J6` or the unchanged rail program.

## What this does not show

- One night, one container per arm (two for J6M). The earlier parser arm of this volume showed a container that ran at half speed from its start; one container is one sample.
- 16 concurrent requests at most; one card; answers of about 20 tokens. Nothing here says how the two NIM lines compare on long answers or at higher load.
- The comparison of per-item verdicts is between J6M and J6-tonight only, as registered; no other pair's items were set side by side.
- NIM for LLMs 3.0 was not run.
