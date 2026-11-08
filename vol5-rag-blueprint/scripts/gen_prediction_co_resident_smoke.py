#!/usr/bin/env python3
"""Vol.5 · writes what is expected of the smoke tests that share the card with a running encoding job (the night of
2026-10-04), and its .sha256 file. Run once, before the first container of these smoke tests. Never changed afterwards.
usage: gen_prediction_co_resident_smoke.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
OUT = os.path.join(VOL, "results", "co_resident_smoke", "prediction_co_resident_smoke.json")
DRAFT = "--draft" in sys.argv


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def digest(image):
    r = subprocess.run(["docker", "image", "inspect", image, "--format", "{{index .RepoDigests 0}}"], capture_output=True, text=True)
    return r.stdout.strip() or None


PROGRAMS = ["scripts/smoke_step.py", "scripts/ocr_text_smoke.py", "scripts/ingest_text_only_smoke.py", "scripts/make_zh_test_image.py",
            "compose_text_only/text_only.env", "compose_text_only/override.yaml", "compose_text_only/override_milvus_cpu.yaml", "compose_text_only/up.sh",
            "compose_text_only/prompt_overrides_none.yaml", "test_images/zh_statute_text.png", "test_images/zh_statute_text.txt"]
pred = {
 "what": "Expectations for three smoke tests of Vol.5 that run while another container of this repository's work (a whole-corpus encoding) uses the card",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "conditions": {"card": "one RTX 5090 (32 GB), Windows 11 + Docker Desktop (WSL2); shared with the embedding NIM of the encoding job for the whole time",
                "no_timing": "nothing here is a speed figure: seconds are recorded as what happened on a shared card and every record carries gpu_contended",
                "before_a_start": "free card memory must be at least what the container is expected to need plus 4,096 MiB; otherwise the start is refused and recorded",
                "the_encoding_job": "its pieces of 100,000 passages took 430 to 459 s before these tests; if pieces that overlap a test take more than 20% longer (above about 534 s), the test is stopped and that is recorded",
                "limits": "every command runs under `timeout`: start 660 to 780 s, a request program 700 s, the ingestion pass 2,100 s, docker compose up 900 s",
                "test_data": "the Blueprint's own example image and sample PDFs, and a test image made here from public statute text (scripts/make_zh_test_image.py); no other document"},
 "ocr_v2": {"image": "nvcr.io/nim/nvidia/nemotron-ocr-v2:2.0.1", "image_digest": digest("nvcr.io/nim/nvidia/nemotron-ocr-v2:2.0.1"),
            "known_before": "its documentation describes a new runtime that is not Triton, with the endpoint /v1/ocr, a multilingual variant as the default and a download-only mode; its support matrix lists no GeForce card. The weights are fetched beforehand in that download-only mode.",
            "requests": "POST /v1/ocr with merge_levels word: the Blueprint's example image, then the Chinese test image (and once more with merge_levels paragraph); each twice",
            "expectation": "the container reports ready and answers 200; on the Chinese test image at least 90% of the expected CJK characters are in the answer. Confidence: medium (the embedding NIM of the same runtime family runs on this card; nothing is known about this image on it).",
            "both_outcomes_are_results": "ready and Chinese text returned: a candidate OCR service for the volume on this host setup. Not ready or an error: the error text is the result."},
 "paddleocr_zh": {"image": "nvcr.io/nim/baidu/paddleocr:1.5.0", "image_digest": digest("nvcr.io/nim/baidu/paddleocr:1.5.0"),
                  "known_before": "the profile that fits this card builds its recognizer with language en; neither the image's files nor its documentation name a language setting, so there is nothing to switch",
                  "requests": "POST /v1/infer: the Chinese test image, twice",
                  "expectation": "200; fewer than 20% of the expected CJK characters are in the answer"},
 "text_only_ingestion": {"recipe": "compose_text_only/ (this repository's variables and two override files on top of the Blueprint's compose files at v2.6.2; no answer model, no reranker, Milvus CPU image)",
                         "documents": ["data/multimodal/woods_frost.pdf", "data/multimodal/functional_validation.pdf (both from the Blueprint repository)"],
                         "recorded": "per service whether and when it answered its health endpoint, the card's memory, the status codes of collection creation, upload, task status and document listing, the number of chunks in Milvus",
                         "expectation": "all three services answer their health endpoints, the task finishes, both documents are listed and Milvus holds more than 0 rows. The step judged most likely to fail: the ingestion runtime's start (it asks for 40 GB of shared memory and 16 worker processes).",
                         "both_outcomes_are_results": "it runs through: the text-only path is a working baseline for the volume on this host setup. A service fails: its error text is the result."},
 "embedding_nim_nvfp4_probe": {
  "image": "nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2", "image_digest": digest("nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2"),
  "known_before": "earlier this evening the container refused NIM_ENGINE_PRECISION=fp8 and =nvfp4 with the weights of its default download-only run mounted (the only compatible pipeline it named was padded-naive-fp16). The download-only run was repeated with a precision pinned: with fp8 it wrote the same 14 files, byte for byte; with nvfp4 it wrote another set (18 files, 997 MiB, a quantised checkpoint with its own manifest).",
  "what": "one start with NIM_ENGINE_PRECISION=nvfp4 and the nvfp4 files mounted; if it reports ready: the smoke step and the probe of vol4-retriever/scripts/embed_cell.py on miracl-hn-zh (8 queries and 8 passages against the reference arm's vectors of the same texts). No timing.",
  "fp8": "no start: the fp8-pinned download gave nothing the earlier start did not have, so the earlier refusal stands as the result",
  "expectation": "a guess with low confidence: it reports ready; the cosine of each of the 16 vectors with the reference arm's is above 0.95",
  "both_outcomes_are_results": "ready: a timed nvfp4 cell is planned for a later session. Not ready: the last log lines are the result."},
 "files_sha256": {f: sha(os.path.join(VOL, f)) for f in PROGRAMS},
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen file exists")
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
