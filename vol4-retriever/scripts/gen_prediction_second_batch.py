#!/usr/bin/env python3
"""Vol.4 / Vol.5 · writes the pre-registration of the second GPU session (the night of 2026-10-04) and its .sha256 file.
It is a supplement to the pre-registration of the first session: the rules, the data, the metrics and the method of that
file stay as they are, and this file adds the cells of the second session with the limit of every measuring command.
Run once, before the first GPU container of the session. The file is never changed afterwards.
env: VOL4_HOLD (folder outside the repository with the weights) · usage: gen_prediction_second_batch.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE); REPO = os.path.dirname(VOL)
V5 = os.path.join(REPO, "vol5-rag-blueprint")
OUT = os.path.join(VOL, "results", "second_batch", "prediction_second_batch.json")
BEFORE = os.path.join(VOL, "results", "second_batch", "before_the_run")
DRAFT = "--draft" in sys.argv


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def digest(image):
    r = subprocess.run(["docker", "image", "inspect", image, "--format", "{{index .RepoDigests 0}}"], capture_output=True, text=True)
    return r.stdout.strip() or None


def before(name):
    p = os.path.join(BEFORE, name)
    return {"file": "before_the_run/" + name, "sha256": sha(p)}


I = {"n3": "nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2", "e1b": "nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2:1.13.0",
     "page": "nvcr.io/nim/nvidia/nemotron-page-elements-v3:1.8.0", "graphic": "nvcr.io/nim/nvidia/nemotron-graphic-elements-v1:1.8.0",
     "table": "nvcr.io/nim/nvidia/nemotron-table-structure-v1:1.8.0", "parse": "nvcr.io/nim/nvidia/nemotron-parse:1.5.0",
     "paddle": "nvcr.io/nim/baidu/paddleocr:1.5.0", "ocr": "nvcr.io/nim/nvidia/nemotron-ocr-v1:1.3.0", "client": "vol4-client:py312"}
first = os.path.join(VOL, "results", "first_batch", "prediction_first_batch.json")
scan = json.load(open(os.path.join(BEFORE, "transformers_rope_scan.json"), encoding="utf-8"))
r55 = json.load(open(os.path.join(BEFORE, "rope_check_transformers_5.5.0.json"), encoding="utf-8"))
r513 = json.load(open(os.path.join(BEFORE, "rope_check_transformers_5.13.0.json"), encoding="utf-8"))
NEW = ["scripts/session_step.py", "scripts/encode_corpus_resumable.py", "scripts/compare_embeddings.py", "scripts/rope_check.py", "scripts/transformers_rope_scan.py"]
OLD = ["scripts/embed_cell.py", "scripts/score_run.py", "scripts/run_step.py", "scripts/retrieval_datasets.py", "scripts/retrieval_metrics.py", "scripts/nim_retrieval_clients.py", "client/Dockerfile"]
FP16 = "2e1ac3d2b2e881b0c86959c09a6ecca58947ac174745f2113203e539ed1310d8"
pred = {
 "what": "Pre-registration of the second GPU session of Vol.4 with the extraction-service smoke tests of Vol.5; a supplement to prediction_first_batch.json",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"file": "../first_batch/prediction_first_batch.json", "sha256": sha(first),
                 "kept_from_it": "its rules (timed and untimed parts, the gate, start conditions of a timed part, one variable per comparison, raw output outside the repository), its data sets, its metrics and its method (client in a container on the NIM's Docker network, one kept connection, 64 per request, the first 4,096 passages, one discarded pass and three timed passes)"},
 "session": {"card": "one RTX 5090 (32 GB), Windows 11 + Docker Desktop (WSL2)",
             "window": "the night of 2026-10-04, from the freeze of this file; every container of the session is stopped at 08:00 local time on 2026-10-05",
             "order": "cells 1 to 6 as listed; a cell that cannot start is reported as not run with its reason, and the session goes on",
             "containers": "named p110_<tag> on the Docker network p110net (scripts/session_step.py sets this; the steps themselves are scripts/run_step.py, unchanged)"},
 "added_rule": {"every_measuring_command_has_a_limit": "each command below runs under `timeout` with the number of seconds written beside it; a command that reaches its limit is reported as 'not completed, limit reached' and is not repeated with a longer one in this session",
                "why": "in the first session one command without a limit held the card for ten minutes"},
 "disclosed_about_the_first_session": {
  "what": "another session on this host ran CPU work from 12:20 to 12:59 on 2026-10-04; the three timed passes of the NIM 2.2.2 cell (12:46:28 to 12:48:27) lie inside that window. The card was not shared.",
  "consequence": "the timed passes of that cell (fp16, miracl-hn-zh) are repeated in cell 5 of this session, next to the fp8 and nvfp4 cells, and both sets of passes are reported",
  "found_in_the_driver": "the internal driver of the first session piped each gate's output through a filter, so a refused gate would not have stopped a cell; all 34 gates of that session passed, so no cell ran against a refusal. The driver of this session sees the refusal (pipefail), and that was checked with a command that fails."},
 "cell_1_zh_version": {
  "question": "does the reference arm give another nDCG@10 on miracl-hn-zh when only the transformers version changes from 5.5.0 to the stable release of the day the published result is dated (2026-07-07): 5.13.0",
  "why_this_cell": "the published value is 0.64244 and the first session measured 0.66313; while loading, transformers prints that the rope key apply_yarn_scaling of the model is not recognised",
  "known_before_the_run_without_the_card": {
   "release_scan": dict(before("transformers_rope_scan.json"), tags=len(scan["tags"]), tags_where_the_key_name_occurs=scan["tags_where_the_key_name_occurs"],
                        reading="no release from 5.0.0 to 5.18.0 names the key: the warning cannot be made to disappear by choosing a release. The code of the YaRN function is the same from 5.0.0 to 5.14.0 and the model file is the same from 5.4.0 to 5.14.0."),
   "rope_check": {"5.5.0": before("rope_check_transformers_5.5.0.json"), "5.13.0": before("rope_check_transformers_5.13.0.json"),
                  "same_frequencies_in_both": r55["frequencies_sha256_of_float32_bytes"] == r513["frequencies_sha256_of_float32_bytes"],
                  "frequencies_changed_by_yarn": f"{r55['divided_by_the_full_factor'] + r55['in_between']} of {r55['frequencies']} in both",
                  "factor_on_cos_and_sin": [r55["factor_applied_to_cos_and_sin"], r513["factor_applied_to_cos_and_sin"]],
                  "warning_printed": [bool(r55["warning_lines_while_loading"]), bool(r513["warning_lines_while_loading"])],
                  "reading": "both releases apply the YaRN interpolation of the frequencies and no magnitude correction; the key that is not recognised has the value false in the model's configuration"},
   "model_config": "transformers_version 5.5.0; the downloaded revision is the one of the published result (f880174635613cff04033875fc6a69296cb72006)",
   "environment": {"name": "vol4-reference-tf5130", "packages": before("environment_transformers_5.13.0.txt"), "first_session_packages": before("environment_transformers_5.5.0.txt"),
                   "difference": "one line of 47: transformers 5.5.0 -> 5.13.0; torch 2.11.0+cu130, sentence-transformers 5.4.1, tokenizers 0.22.2 and every other package are the same versions"}},
  "commands": [{"what": "encode every query and passage (the first session's command, the other environment)", "program": "scripts/embed_cell.py encode --backend st --dataset miracl-hn-zh --dim 2048 --batch 16", "timeout_s": 900},
               {"what": "score", "program": "scripts/score_run.py --target-ndcg10 0.64244", "timeout_s": 300},
               {"what": "cosine of every vector with the first session's vector of the same text", "program": "scripts/compare_embeddings.py", "timeout_s": 300}],
  "branches_decided_in_advance": {
   "a": "nDCG@10 within 0.005 of 0.64244: the cause is the library version; both values are reported and the published one counts as reproduced with the release of its date",
   "b": "nDCG@10 still about 0.663: a version cause is not supported; the zh cells stay labelled 'control not reproduced, cause unknown'. No further variant is tried in this session."},
  "expectation": "branch b: nDCG@10 within 0.001 of 0.66313 and every cosine above 0.9999, because the code that computes the positions is the same in both releases",
  "not_in_this_session": "a cell that changes the model's rope settings themselves (plain RoPE, or YaRN with the magnitude correction): asked of the people who assign the work, not decided here"},
 "cell_2_three_extraction_nims": {
  "what": "start each image with the settings of the Blueprint's compose file (v2.6.2), send the Blueprint's own example image twice to /v1/infer, record seconds to ready, the HTTP status, the shape of the answer or the error text, the card's memory",
  "images": {k: {"image": I[k], "image_digest": digest(I[k]), "profile": "the one the image selects; the TensorRT fp16 engine for compute capability 12.0 was fetched beforehand in CPU-only mode"} for k in ("page", "graphic", "table")},
  "image_sent": "docs/assets/arch_diagram.png of the Blueprint repository at v2.6.2 (SHA-256 cf1bc91d…5b73 as recorded by the first session)",
  "commands_per_image": [{"what": "start and wait for ready", "program": "scripts/session_step.py nim-start --kind 1x --wait 600", "timeout_s": 720},
                         {"what": "two requests", "program": "vol5 scripts/extraction_smoke.py --form infer --timeout 300", "timeout_s": 700},
                         {"what": "stop", "program": "scripts/session_step.py nim-stop", "timeout_s": 300}],
  "both_outcomes_are_results": "HTTP 500 like the OCR NIM: the ingestion's extraction step as a whole does not run on this host setup. HTTP 200: the failure is confined to the OCR service.",
  "expectation": "a guess, with low confidence: HTTP 200 for all three (their settings name CPU threads for pre- and post-processing, which suggests those steps do not hand GPU tensors to a Python model)"},
 "cell_3_nemotron_parse": {
  "image": I["parse"], "image_digest": digest(I["parse"]),
  "known_before_the_run": "the image holds one model profile: engine tensorrt_llm, precision bf16, built on the local card at the first start; it is not a vLLM profile. Its documentation lists H100, A100, L40S and A10G. The weights (3.6 GiB) were fetched beforehand in CPU-only mode.",
  "condition_in_the_work_order": "this smoke test was planned for the case that the image serves through vLLM. It does not; the test is run nevertheless because it costs at most the limit below and its outcome is a fact either way.",
  "settings": "the Blueprint's: NIM_HTTP_API_PORT=8000, NIM_TRITON_LOG_VERBOSE=1, user root, 16 GB of shared memory",
  "request": "POST /v1/chat/completions, model nvidia/nemotron-parse, tool markdown_bbox, the same example image as a data URL, temperature 0; twice",
  "commands": [{"what": "start, engine build included, and wait for ready", "program": "scripts/session_step.py nim-start --kind 1x --wait 1500", "timeout_s": 1620},
               {"what": "two requests", "program": "vol5 scripts/extraction_smoke.py --form parse --timeout 300", "timeout_s": 700}, {"what": "stop", "timeout_s": 300}],
  "recorded": "seconds to ready, the card's memory once ready, the HTTP status, the number of elements and their types, the number of characters of text in total (not the text)",
  "expectation": "a guess, with low confidence: the engine build does not finish or fails on this card (not ready within the limit); if it becomes ready, the request answers 200"},
 "cell_4_ocr_alternatives": {
  "paddleocr": {"image": I["paddle"], "image_digest": digest(I["paddle"]),
                "known_before_the_run": "of its nine profiles only the generic ONNX one fits this card; its Python model reads its input from CPU memory and calls no other Triton model; it constructs the recognizer with language en",
                "settings": "the Blueprint's (profile paddle): OMP_NUM_THREADS=8, NIM_TRITON_RATE_LIMIT=3, NIM_TRITON_CUDA_MEMORY_POOL_MB=3072, CUDA_VISIBLE_DEVICES=0",
                "commands": [{"what": "start", "timeout_s": 720}, {"what": "two requests to /v1/infer", "timeout_s": 700}, {"what": "stop", "timeout_s": 300}],
                "expectation": "a guess: ready and HTTP 200"},
  "ocr_with_the_host_process_namespace": {
   "image": I["ocr"], "image_digest": digest(I["ocr"]),
   "what": "the OCR NIM of the first session once more, with `--pid=host` added to docker run and nothing else changed",
   "why": "the Triton issue tracker names `--pid host` as the fix for a failing cudaIpcOpenMemHandle between two containers (issue 3429) and suggests it in a WSL2 report (issue 6220)",
   "not_tried": "overriding FORCE_CPU_ONLY_INPUT_TENSORS: that parameter covers the inputs of a Python model and its default is already the CPU; in this image the GPU tensors are created inside the pipeline's own code (EXTRACTION_NIMS_ON_WSL2.md, sections 2 and 3). Changing the image's code is not done.",
   "commands": [{"what": "start", "timeout_s": 540}, {"what": "two requests to /v1/infer", "timeout_s": 700}, {"what": "stop", "timeout_s": 300}],
   "outside_the_work_order": True,
   "expectation": "HTTP 500 with the same error text as before (one container: the two processes share a namespace already)"}},
 "cell_5_one_variable_precision": {
  "rule": "two cells of one image that differ in the precision only; same data, same requests, same client; timed passes of both on the same night; speed tables of cells that differ in more than the precision are not put side by side as a comparison",
  "nemotron_3_embed_1b": {"image": I["n3"], "image_digest": digest(I["n3"]), "data": "miracl-hn-zh", "cells": ["NIM_ENGINE_PRECISION=fp16 (a repeat of the first session's cell, see above)", "NIM_ENGINE_PRECISION=fp8", "NIM_ENGINE_PRECISION=nvfp4"],
                          "branch_decided_in_advance": "a precision with which the container does not report ready: its last log lines are the result of that cell",
                          "expectation": "fp8: nDCG@10 within 0.005 of fp16 and more passages per second than fp16. nvfp4: a guess with low confidence that it starts; if it does, nDCG@10 within 0.01 of fp16."},
  "llama_nemotron_embed_1b_v2": {"image": I["e1b"], "image_digest": digest(I["e1b"]), "data": ["beir-scifact", "miracl-hn-zh", "miracl-hn-ja"],
                                 "cells": [f"NIM_MODEL_PROFILE={FP16} (TensorRT fp16, compute capability 12.0): smoke, timed passes, encode, score",
                                           "no profile set (the image selects the fp8 profile, as in the first session): smoke and timed passes only, as the same-night partner of the fp16 passes; its quality figures are the first session's"],
                                 "expectation": "fp16: nDCG@10 within 0.005 of the fp8 cell on each data set; fewer passages per second than fp8; more card memory than fp8"},
  "commands_per_cell": [{"what": "start", "program": "scripts/session_step.py nim-start --wait 900 (2.2.2) / 600 (1.13.0)", "timeout_s": "1020 / 720"},
                        {"what": "smoke", "program": "scripts/embed_cell.py smoke", "timeout_s": 300},
                        {"what": "the timed passes of one data set (gate with --timed right before)", "program": "scripts/embed_cell.py throughput --batch 64 --n 4096 --reps 3", "timeout_s": 600},
                        {"what": "encode one data set (untimed)", "program": "scripts/embed_cell.py encode --batch 64", "timeout_s": 1800},
                        {"what": "score", "program": "scripts/score_run.py", "timeout_s": 300},
                        {"what": "cosine of every vector with the other precision's vector of the same text", "program": "scripts/compare_embeddings.py", "timeout_s": 300},
                        {"what": "stop", "timeout_s": 300}],
  "reported_per_cell": "precision as the server log names it, nDCG@10, Recall@100, passages per second (median of three passes, all three kept), the card's memory once ready, and the cosine statistics against the other precision"},
 "cell_6_whole_corpus": {
  "what": "every passage of MIRACL zh (4,934,368) encoded with the NIM 2.2.2 pinned to fp16; if zh is finished before 06:00, MIRACL ja is started the same way",
  "image": I["n3"], "program": "scripts/encode_corpus_resumable.py --piece 100000 --batch 64 --stop-at 2026-10-05T08:00:00+0800",
  "not_a_speed": "no gate with --timed; the wall time of a piece is recorded and is not a throughput figure. If another program shares the card during the night, the events of this session say so and nothing else changes.",
  "checkpoint": "after every 100,000 passages: the vectors of the piece (outside the repository) and one line in results/second_batch/full_corpus/<data set>/checkpoints.jsonl (counts, seconds, SHA-256; no text). A later call goes on from the last line.",
  "check_before_the_run": "the program is new, so its first call against the real NIM encodes the first 512 passages of miracl-hn-zh in two pieces; the ids must be those of the first session in the same order and every cosine with the first session's vectors must be at least 0.9999. If not, the whole-corpus run is not started.",
  "limit": "the program stops by itself at 08:00; the driver's timeout is the seconds left until 08:00 plus 300; then the container is stopped and removed, the closing gate is run and the card's state is recorded",
  "expectation": "from the first session's rate on the reduced zh corpus (about 240 passages per second) the zh corpus needs about 5.7 hours; whether it finishes depends on the hour the cell starts. ja does not finish in this session.",
  "not_in_this_session": "any quality figure on the whole corpus"},
 "images_not_started_in_this_session": "none other than the ones named above",
 "client_image": {"image": I["client"], "id": subprocess.run(["docker", "image", "inspect", I["client"], "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip() or None},
 "harness_sha256": {f: sha(os.path.join(VOL, f)) for f in NEW + OLD} | {"tools/g8_gate.py": sha(os.path.join(REPO, "tools", "g8_gate.py")),
                                                                       "../vol5-rag-blueprint/scripts/extraction_smoke.py": sha(os.path.join(V5, "scripts", "extraction_smoke.py"))},
 "unchanged_since_the_first_session": {f: (sha(os.path.join(VOL, f)) == json.load(open(first, encoding="utf-8"))["harness_sha256"].get(f)) for f in OLD},
 "programs_written_after_the_freeze": "none planned; if one is needed, its SHA-256 is written to the events file before its first use",
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT), "| unchanged since the first session:", all(pred["unchanged_since_the_first_session"].values()))
