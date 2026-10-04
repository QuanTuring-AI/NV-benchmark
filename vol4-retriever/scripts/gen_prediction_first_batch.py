#!/usr/bin/env python3
"""Vol.4 / Vol.5 · writes the pre-registration of the first GPU session (2026-10-04) and its .sha256 file.
Run once, before the first GPU step. The file is never changed afterwards.
env: VOL4_HOLD (folder outside the repository with the weights) · usage: gen_prediction_first_batch.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE); REPO = os.path.dirname(VOL)
OUT = os.path.join(VOL, "results", "first_batch", "prediction_first_batch.json")
DRAFT = "--draft" in sys.argv


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def digest(image):
    r = subprocess.run(["docker", "image", "inspect", image, "--format", "{{index .RepoDigests 0}}"], capture_output=True, text=True)
    return r.stdout.strip() or None


def counts(name):
    p = os.path.join(VOL, "results", "first_batch", "token_counts", name + ".json")
    if not os.path.isfile(p):
        return None
    d = json.load(open(p, encoding="utf-8"))
    return {"file_sha256": sha(p), "queries_longer_than_4096": d["queries"]["longer_than_limit"], "passages_longer_than_4096": d["passages"]["longer_than_limit"],
            "passages": d["passages"]["count"], "longest_passage_tokens": d["passages"]["max"], "passage_tokens_total": d["passages"]["total"]}


hold = os.environ["VOL4_HOLD"]
IMAGES = {"nemotron-3-embed-1b": "nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2", "llama-nemotron-embed-1b-v2": "nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2:1.13.0",
          "llama-nemotron-embed-300m-v2": "nvcr.io/nim/nvidia/llama-nemotron-embed-300m-v2:1.13.0", "llama-nemotron-embed-vl-1b-v2": "nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:2.3.0",
          "llama-nemotron-rerank-1b-v2": "nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0", "llama-nemotron-rerank-500m-v2": "nvcr.io/nim/nvidia/llama-nemotron-rerank-500m-v2:1.10.0",
          "nemotron-3-nano": "nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12", "nemotron-ocr-v1": "nvcr.io/nim/nvidia/nemotron-ocr-v1:1.3.0", "client": "vol4-client:py312"}
HARNESS = ["scripts/embed_cell.py", "scripts/score_run.py", "scripts/rerank_cell.py", "scripts/run_step.py", "scripts/retrieval_datasets.py", "scripts/retrieval_metrics.py",
           "scripts/nim_retrieval_clients.py", "client/Dockerfile"]
ref = os.path.join(hold, "weights", "nemotron-3-embed-1b-bf16-open-weights")
pred = {
 "what": "Pre-registration of the first GPU session of Vol.4 (NeMo Retriever on one RTX 5090) with two preparatory cells of Vol.5",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "session": {"card": "one RTX 5090 (32 GB), Windows 11 + Docker Desktop (WSL2)", "window": "2026-10-04, from the freeze of this file to 17:30 local time at the latest",
             "order": "P1, P2, P3, P4 as listed below; a cell that has not started by 17:30 is not run and is reported as not run with its reason",
             "no_positive_control_is_skipped_to_save_time": True},
 "rules": {
  "timed_and_untimed": "A cell has a timed part (a throughput figure) and an untimed part (encoding or reranking the whole data set for the quality figures). A timed part is one blocking call during which nothing else is started on the host from this session; the idle-card gate runs right before it. Wall times of untimed parts are recorded and are not reported as speeds.",
  "gate": "tools/g8_gate.py (utilization p50 <= 2 % and power p50 <= 45 W over 10 s) before every container start and every timed part. Each gate also records the memory the desktop holds on the card (when no container of the session is running) or the growth since the container reported ready, the number of game-launcher processes and the containers that are running. 512 MiB more desktop memory than at the first gate of the session is flagged in the record; it is not a stop.",
  "start_conditions_of_a_timed_part": "the gate passes, no container of another session is running, no game-launcher process is running",
  "stop": "if a game process or another session's container appears, the running cell finishes and no new cell starts",
  "one_variable": "two cells that are compared differ in one thing; whatever else had to change is listed with the cell and is not absorbed",
  "raw_output": "vectors, run files and container logs are kept outside the repository; the repository gets the metrics, the per-query values, the timings and the records"},
 "method_from_this_volume_on": {
  "client": "the timing client runs in a container on the same Docker network as the NIM (image vol4-client:py312, built from client/Dockerfile), so that no host port forwarding is in the path; one kept connection; the batch size is fixed per cell",
  "server_side": "where a NIM has a Prometheus endpoint (/v1/metrics) it is read before and after a timed part and kept beside the client's figure",
  "why": "on this host a new connection to a published container port costs about 3 ms or about 19 ms (two clusters), in shares that drift between sessions; found in the judge study of Vol.3"},
 "data": {
  "miracl-hn-zh / miracl-hn-ja": {"source": "mteb/MIRACLRetrievalHardNegatives @ d7d94fa4b946cec4a27c84653aa0cf6b33f74a3c, dev (the non-v2 task of MTEB)", "counts": "81,309 passages / 393 queries; 185,319 / 860; checked by retrieval_datasets.check_published_counts before every cell"},
  "beir-scifact": {"source": "the BEIR zip, MD5 5f7d1de60b170fc8027bb7898e2efca1, test", "counts": "5,183 passages / 300 queries"},
  "not_in_this_session": "HotpotQA and the full MIRACL corpus (millions of passages)",
  "token_counts_known_before_the_run": {n: counts(n) for n in ("miracl-hn-zh", "miracl-hn-ja", "beir-scifact")}},
 "metrics": {"quality": "nDCG@10 and Recall@100 by scripts/retrieval_metrics.py (pytrec_eval), after an exact cosine search over the whole corpus that keeps 1,000 per query (scripts/score_run.py); the same program for every cell",
             "speed": "passages per second: the first 4,096 passages of the corpus in file order, 64 per request, one discarded pass over the first 4 batches, then 3 timed passes; the median of the three is the figure and all three are kept"},
 "P1_reference_arm": {
  "what": "the open weights on the reduced MIRACL task, through this repository's own programs (not through MTEB), with the conditions of the published result as listed in MTEB_REFERENCE.md",
  "weights": {"repo": "nvidia/Nemotron-3-Embed-1B-BF16", "revision": "f880174635613cff04033875fc6a69296cb72006", "model_safetensors_sha256": sha(os.path.join(ref, "model.safetensors"))},
  "environment": {"python": "3.11.13", "torch": "2.11.0+cu130", "sentence-transformers": "5.4.1", "transformers": "5.5.0",
                  "why_these": "the versions the model repository records it was saved with (config_sentence_transformers.json); the versions of the published MTEB result are not recorded anywhere"},
  "conditions": {"loader": "SentenceTransformer(path, device='cuda', processor_kwargs={'model_max_length': 4096})", "prefixes": {"query": "query: ", "passage": "passage: "},
                 "passage_text": "title + ' ' + text, stripped", "pooling_and_normalisation": "the model's own modules (mean pooling including the prompt, Normalize)", "precision": "as stored (bfloat16)",
                 "batch": 16, "batch_note": "the batch size of the published result is not recorded; 16 is what the same results folder records for most other tasks",
                 "search": "exact cosine, 1,000 per query"},
  "seen_before_the_freeze_on_the_cpu": "the loader gives max_seq_length 4096, bfloat16 parameters and the two prefixes; transformers prints 'Unrecognized keys in rope_parameters for rope_type=yarn: {apply_yarn_scaling}' while loading, so one configuration key of the model is not used by this transformers version",
  "target": {"zh_ndcg_at_10": 0.64244, "ja_ndcg_at_10": 0.74194, "source": "MTEB results repository, commit 4abe26c645a2adec358ce761c1dded42a5b6e6fa"},
  "branches_decided_in_advance": {
   "a": "both languages within 0.005 of the target: this repository's path is accepted and the NIM cells on this task are a comparison against a reproduced reference",
   "b": "a difference above 0.005 in either language: MTEB 2.14.3 itself is run once on zh with the same weights and conditions. MTEB reproduces and this path does not: this path is wrong, the NIM comparison on this task is stopped and that is reported. Neither reproduces: the environment differs in a condition that is not recorded; the difference is reported as measured, the NIM cells run and are labelled 'control not reproduced'. No parameter is tuned until the figure fits."},
  "expectation": "branch a. The risk that is known: the unrecorded conditions, and the configuration key this transformers version does not use."},
 "P1_nim_same_task": {
  "image": IMAGES["nemotron-3-embed-1b"], "image_digest": digest(IMAGES["nemotron-3-embed-1b"]), "weights": "fetched earlier by the NIM's own download-only mode; model.safetensors byte-identical to the open weights",
  "profiles": "the documentation of 2.x says there is no list-model-profiles step: kernels are picked at start-up and the precision can be set with NIM_ENGINE_PRECISION (fp16, fp8, nvfp4). The command is tried once and its answer is recorded.",
  "cell_A": "the NIM as it starts with nothing set: the precision and engine it reports are recorded from its log",
  "cell_B": "a precision equal to the reference arm's (bf16) if the NIM offers one. The documented values do not include bf16; if cell A did not run in fp16, one cell pinned to fp16 (the documented 16-bit value) is run and is labelled as fp16, not as bf16. If cell A already ran in fp16, there is no cell B.",
  "request": {"input_type": "query / passage on every request", "truncate": "END", "batch": 64, "text": "as in the reference arm but without a prefix written by the client"},
  "variables_of_the_serving_path_checked_one_by_one": {
   "input_type_and_prefix": "eight queries and eight passages: the NIM's vector with input_type against the reference arm's vector of the same text; the same text sent with the other input_type; the prefix written by the client in addition to input_type (is it applied twice)",
   "truncation": "the number of passages and queries above 4,096 tokens is counted beforehand (above); one over-long input is sent with truncate END and with NONE and the answers are recorded",
   "vector_size": "expected 2,048; a request with dimensions=1024 is sent once"},
  "controls": {"positive": "the smoke step before a cell: finite vectors of unit length and expected size; a passage is nearest to itself when sent in another batch size",
               "negative": "a query sent with input_type passage must not give the query-mode vector (cosine below 0.999 for at least one of eight); if it does, input_type has no effect and the cell is reported as such"},
  "branch_decided_in_advance": "the image does not start on this card (its support matrix does not list the RTX 50 series): the error text is the result of the cell and the session goes on",
  "expectation": "it starts and runs in a 16-bit precision; nDCG@10 within 0.01 of the reference arm in both languages. Speed: recorded, no expectation."},
 "P2_method_cell": {"what": "the same NIM, the same requests (the timed part on miracl-hn-zh), once with the client in the container on the Docker network and once with the client on the host through the published port (a new connection per request, and one kept connection)",
                    "reported": "passages per second and the per-request durations of each of the three ways, side by side",
                    "expectation": "per-request durations through the host port with a new connection per request fall into two groups about 16 ms apart; in the container they do not"},
 "P2_other_embedding_nims": {
  "images": {k: {"image": IMAGES[k], "image_digest": digest(IMAGES[k])} for k in ("llama-nemotron-embed-1b-v2", "llama-nemotron-embed-300m-v2", "llama-nemotron-embed-vl-1b-v2")},
  "data": ["beir-scifact", "miracl-hn-zh", "miracl-hn-ja"], "request": "input_type on every request, truncate END, 64 per request",
  "recorded_per_nim": "version, digest, the profile or precision it selects, seconds to ready, what it downloads at its first start, the card's memory once ready, the three figures per data set",
  "targets": "none: no published per-data-set value exists for these models on these data sets (MODEL_CARD_CLAIMS.json). The figures are reported as measured; nothing is called a reproduction.",
  "branch_decided_in_advance": "an image that does not start: its error text is recorded and the session goes on"},
 "P3_reranking": {
  "images": {k: {"image": IMAGES[k], "image_digest": digest(IMAGES[k])} for k in ("llama-nemotron-rerank-1b-v2", "llama-nemotron-rerank-500m-v2")},
  "input": "the first 100 results per query of the P1 NIM (cell A) on beir-scifact, miracl-hn-zh and miracl-hn-ja", "request": "one call per query with its 100 passages, truncate END",
  "rule": "at most 512 passages per call; scores of separate calls are never combined", "reported": "nDCG@10 before and after reranking, side by side; passage-query pairs per second (first 40 queries, 3 timed passes)",
  "if_the_P1_NIM_did_not_run": "the first-stage ranking is the reference arm's, and that is stated with the figures"},
 "P4_vol5_preparation": {
  "nano_context": {"image": IMAGES["nemotron-3-nano"], "image_digest": digest(IMAGES["nemotron-3-nano"]), "what": "the smallest memory budget with which Nemotron 3 Nano starts and answers, at 8,192 and at 16,384 tokens of context",
                   "method": "the method of Vol.2's footprint addendum (vol2-nemotron/results/p50_footprint_addendum2): same precision and same max_num_seqs, only the context changes. The program is that harness if it takes the context as an argument; otherwise a program written after this freeze from the same method, whose SHA-256 is written to the events file before its first container."},
  "ocr_smoke": {"image": IMAGES["nemotron-ocr-v1"], "image_digest": digest(IMAGES["nemotron-ocr-v1"]), "what": "start the container, send one request with a public example image, record the HTTP status",
                "why": "a forum report (topic 351835) says version 1.1.0 answers 500 on an RTX 5090 under WSL2", "both_outcomes_are_results": True},
  "if_time_runs_out": "P4 is dropped as a whole and reported as not run"},
 "not_in_this_session": ["HotpotQA and the full MIRACL corpus", "the RAG Blueprint as a whole", "a reference arm with the NVFP4 open weights", "any further measurement for Vol.3"],
 "client_image": {"image": IMAGES["client"], "id": subprocess.run(["docker", "image", "inspect", IMAGES["client"], "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip() or None},
 "harness_sha256": {f: sha(os.path.join(VOL, f)) for f in HARNESS} | {"tools/g8_gate.py": sha(os.path.join(REPO, "tools", "g8_gate.py"))},
 "programs_written_after_the_freeze": "only the P4 programs, as stated there; each records its SHA-256 in the events file before its first use",
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT), "| token counts present:", {k: bool(v) for k, v in pred["data"]["token_counts_known_before_the_run"].items()})
