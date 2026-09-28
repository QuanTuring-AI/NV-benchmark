# Vol.3 · availability matrix (no GPU measurement)

What this directory answers, before any Vol.3 arm is run: which NIM images exist for the two candidate models, which NIM version each carries, which profiles this card can execute and at what precision, how large the weights are, and what the reference small system (DGX Spark) offers. Every cell names its source; raw command outputs are in `raw/`. Queried 2026-09-21 (+0800). No inference was run; `list-model-profiles` starts the container only to classify profiles.

## 1 · Images and NIM versions

| | A1 · `nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2` | A2 · `nvcr.io/nim/nvidia/nemotron-3-nano` | reference · `nvcr.io/nim/meta/llama-3.1-8b-instruct` |
|---|---|---|---|
| Version tags that resolve (`docker buildx imagetools inspect`, `raw/tag_digests.txt`) | `1.12.2` = `latest` (index `sha256:a2f4a5ae…9a406b2`). Probed and **absent**: `2`, `2.0`, `2.0.1`–`2.0.13`, `1.12.3`, `1.13.0`, `1.14`, `1.14.0` | `2.0.10` `c3b0108e…`, `2.0.11` `1eaec477…`, **`2.0.12` index `sha256:bd38d2d5…9e6f9`, amd64 manifest `sha256:ac9d1cef…2aa3`**, `2.0.13` `31e60afd…` = `latest` | `2.0.12` index `sha256:d2c94c1d…6545`; `2.0.13` `9d6faef8…` exists |
| NIM version inside the image (`docker image inspect`, `raw/inspect_*.txt`) | label `com.nvidia.nim.version=1.12.2`; env `INFERENCE_MICROSERVICE_LLM_NIM_VERSION` is empty in this image | env and label **`2.0.12`**; base `vllm/vllm-openai:v0.27.1-ubuntu2404` | env and label `2.0.12`; same vLLM base |
| Image used by the earlier E7 arm (`../e7/e7_arm_*.json`) | `:1.12.2` (same index digest) | `@sha256:ac9d1cef…` = the amd64 manifest of tag `2.0.12` (the E7 record wrote the same value in both digest fields; the index digest is `bd38d2d5…`) | `:1.13.1` (March 2026 Vol.1 stack) |

**Common NIM version across A1 and A2: none.** A1's newest image is NIM 1.12.2; every A2 image on the 2.x line is 2.0.x. A Vol.3 table that puts A1 and A2 side by side therefore carries the NIM version as a variable in its own column, per row; it is not absorbed. The Vol.2 baseline stack (NIM 2.0.12) is available for A2 and for the reference model only.

The registry's `tags/list` endpoint (`raw/tags_list.txt`, `raw/tags_summary.txt`) returned one page and omitted tags that resolve directly (A2 `2.0.10`–`2.0.13`, reference `2.0.10`–`2.0.13`), so that listing is recorded but not used as evidence of absence; absence is established only by direct resolution of the tag.

## 2 · Profiles this card can execute (`list-model-profiles`, `raw/profiles_*.txt`)

Card: NVIDIA GeForce RTX 5090, 32,607 MiB, driver 591.86. During all three listings the desktop held 2,807–2,814 MiB, so NIM 2.0.12 reported the GPU as *non-free* and classed every profile as "compatible with system but low memory"; the 1.12.2 image classed its bf16 profile as runnable under the same state. The requirement figures are the image's own.

| Model | Precision | Profile (bare 64-hex) | Image's stated requirement | Fits 32,607 MiB? |
|---|---|---|---|---|
| A1 | bf16 tp1 | `5cf34bab34141258d0cc836c66684642d3e3f32b4daaa2008e48bd289d6bc84b` | runnable (no figure printed by 1.12.2) | yes (ran in E7) |
| A1 | bf16 tp2 | `ac77e07c803a4023755b098bdcf76e17e4e94755fe7053f4c3ac95be0453d1bc` | incompatible (needs 2 GPUs) | no |
| A2 | **NVFP4 tp1** | `1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada` | ≥ 21 GB/GPU | yes (ran in E7) |
| A2 | FP8 tp1 | `8c91cce84b9b032ff4af489cb1a20395e223af35623010df9155390ab2284b7a` | ≥ 34 GB/GPU | no |
| A2 | bf16 tp1 | `352d88f8021d0ce396a61d10e929d1d4b45f75038b593595d0d92f80a398a032` | ≥ 63 GB/GPU | no |
| reference | bf16 tp1 | `092ed4213624e774d24cdaf84e3b6222839bab2008a21d3c214ab46626366f90` | ≥ 33 GB (image suggests `--max-model-len=82688` to fit ≥ 27 GB) | yes with `NIM_MAX_MODEL_LEN=8192` (Vol.2) |
| reference | FP8 tp1 | `c4789f7af56c770c1c88b73da666886365534d6980b6b922b41fd97036c77d73` | ≥ 27 GB | yes |
| reference | NVFP4 tp1 | `a28963301b18077db3454d5eb21f5678304936c5a425ddc552443de1f5449f2a` | ≥ 24 GB | yes |

`feat_lora` variants and tp2/tp4/tp8 profiles are listed in the raw files and omitted here. On this card A1 has one executable precision (bf16) and A2 has one (NVFP4); only the reference model has three.

## 3 · Weights

| Model | Architecture | Parameters | Weight bytes on disk (safetensors in the NIM cache snapshot; measured, `find -L … -printf %s`) | Model-card figures |
|---|---|---|---|---|
| A1 · NVIDIA-Nemotron-Nano-9B-v2 | hybrid Mamba-2 + MLP with four attention layers; not MoE | 9B (model card) | **17,776,492,512 B** (snapshot `v1.2.2-ga`, bf16) | native BF16; size not stated on the card |
| A2 · Nemotron-3-Nano-30B-A3B | hybrid Mamba-2 + MoE, 23 Mamba/MoE layers + 6 attention layers; 128 routed experts + 1 shared | 30B total; **3.5B active per token** (NGC container page and the NVFP4 model card; the Nemotron QAD research page says "~3B") | **19,342,796,720 B** (snapshot `hf-nvfp4-bd1ffb1`, NVFP4). bf16 and FP8 snapshots exist as refs only, no weights downloaded | NVFP4 card: attention layers and the Mamba layers feeding them kept in BF16, remaining tensors NVFP4, KV cache FP8; card lists ~18 GB of safetensors. Experts activated per token: 6 (NVFP4 card) vs "5 experts + 1 shared" (NGC page) — both recorded |
| reference · Llama 3.1 8B Instruct | dense | 8B | 16,060,556,376 B (bf16 snapshot) | — |

For the arm-health check (effective bandwidth = tok/s × bytes read per token), A2's bytes per token are **not** its 19.3 GB total: an MoE reads the shared expert, the routed experts selected for that token, and all non-expert layers. The number to use, and why, is a judgement to be written in the Vol.3 pre-registration, not here.

## 4 · Reference small system: DGX Spark

| Item | Distributor quotation held internally (dated 2026-05-26, not published) | NVIDIA product page (`nvidia.com/en-us/products/workstations/dgx-spark/`, fetched 2026-09-21) |
|---|---|---|
| Superchip / GPU | "Blackwell 架構" | NVIDIA GB10 Grace Blackwell Superchip |
| CPU | 20-core Arm: 10 Cortex-X925 + 10 Cortex-A725 | 20-core Arm: 10 Cortex-X925 + 10 Cortex-A725 |
| Memory | 128 GB LPDDR5x, unified system memory | 128 GB LPDDR5x, coherent unified system memory |
| Memory bandwidth | not stated | **273 GB/s** |
| Storage | 4 TB NVMe M.2 | 4 TB NVMe M.2, self-encrypting |
| Power | 170 W PSU | — |
| Stated AI performance | — | up to 1 PFLOP FP4 |
| Stated model size | — | inference up to 200B parameters; fine-tuning up to 70B |

The two sources agree on every item both state. 273 GB/s is 15% of the RTX 5090's 1,792 GB/s; single-stream generation rate scales with bandwidth, so no tok/s measured in this repository on the RTX 5090 transfers to DGX Spark. Whether a given model *fits* is a separate question from *how fast* it runs there, and the footprint table (next step of Vol.3) is what answers the first.

## 5 · NeMo Retriever images (Vol.4–5 pre-check)

All queried with the same credential and method as above; `raw/manifest_inspect.txt`, `raw/tags_summary.txt`.

| Image | Version tags | Resolves with the current key |
|---|---|---|
| `nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2` | `1`, `1.1`, `latest` | yes (amd64 + arm64) |
| `nvcr.io/nim/nvidia/llama-nemotron-rerank-500m-v2` | `1`, `1.1`, `latest` | yes |
| `nvcr.io/nim/nvidia/llama-3.2-nv-rerankqa-1b-v2` (previous name) | `1.3.0` … `1.8.0`, `latest` | yes |
| `nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2` | `1`, `1.13`, `1.13.0`, `latest` | yes |
| `nvcr.io/nim/nvidia/llama-3.2-nv-embedqa-1b-v2` (previous name) | `1.3.0` … `1.10.1`, `latest` | yes |

Controls: a non-existent repository (`nim/nvidia/no-such-repo-zzz`) returns HTTP 401 / "denied" — the same shape a revoked credential would produce — while the known-good reference image resolves; the positive control is what separates "does not exist" from "no access".

## Files

`raw/inspect_*.txt` image env and labels · `raw/tag_digests.txt` direct tag resolution · `raw/tags_list.txt`, `raw/tags_summary.txt` registry listing (incomplete, see §1) · `raw/manifest_inspect.txt` · `raw/profiles_*.txt` · `raw/tags_query.sh` the listing script (the credential is passed to the throwaway container by `--env-file` and is never printed) · `availability.json` the tables above as data.
