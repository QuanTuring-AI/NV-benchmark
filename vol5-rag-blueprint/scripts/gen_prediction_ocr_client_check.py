#!/usr/bin/env python3
"""Vol.5 · writes the pre-registration of one cell and its .sha256 file: the OCR client of the ingestion library
(NV-Ingest 26.3.0) against the newer OCR NIM's /v1/ocr, from inside the library's own container. Run once, before the
OCR container of the cell starts. usage: gen_prediction_ocr_client_check.py [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
RES = os.path.join(V5, "results", "ocr_client_check"); OUT = os.path.join(RES, "prediction_ocr_client_check.json")
DRAFT = "--draft" in sys.argv


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


earlier = json.load(open(os.path.join(V5, "results", "co_resident_smoke", "ocr_v2_zh_image.json"), encoding="utf-8"))
pred = {
 "what": "Pre-registration of one cell: can the OCR client of NV-Ingest 26.3.0 talk to nemotron-ocr-v2 2.0.1 at /v1/ocr and read its answer",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "why_this_cell_and_not_the_whole_ingestion": "in NV-Ingest 26.3.0 every route to the OCR service passes the page-elements service first (EXTRACTION_NIMS_ON_WSL2.md, section 9), and that service does not become ready on this host. "
     "An ingestion with tables and charts switched on would stop one step before the OCR service. This cell leaves that step out and asks the one question that is still open: the client and the newer service, do they fit.",
 "known_before_the_run": {
  "by_reading": "over HTTP the client posts {\"input\": [image_url objects], \"merge_levels\": [...]} to the address as configured and reads data[].text_detections[] with text_prediction.text, text_prediction.confidence and bounding_box.points[].x/.y; "
                "the newer OCR NIM documents that request and those fields for /v1/ocr",
  "calling_form_check": "the program was run once in the NV-Ingest container against an address where nothing listens: the client was built and tried to post to the address as given (connection refused, as it must be). No OCR service was involved.",
  "second_backend": {"what": "the released ingestor image of the Blueprint was asked for the package of its second ingestion backend (INGESTOR_BACKEND=nrl)",
                     "image": "nvcr.io/nvidia/blueprint/ingestor-server:2.6.0", "image_digest": "sha256:5573a2ec107015daaeed6994d1f6779a1df57bd3e6f2daa904ac9ab8f0b7a557",
                     "result": "import nemo_retriever -> ModuleNotFoundError; 173 distributions installed, among them lancedb, nv-ingest-api and nv-ingest-client; ray is not installed either",
                     "consequence": "with the released image that backend cannot be selected; no cell is run for it"},
  "the_ocr_service_alone": {"file": "../co_resident_smoke/ocr_v2_zh_image.json", "sha256": sha(os.path.join(V5, "results", "co_resident_smoke", "ocr_v2_zh_image.json")),
                            "what": "the same test image sent straight to /v1/ocr on 2026-10-04", "summary_keys_of_that_file": sorted(earlier)[:12]}},
 "cell": {
  "ocr_service": {"image": "nvcr.io/nim/nvidia/nemotron-ocr-v2:2.0.1", "start": "as in the earlier smoke test (weights fetched beforehand with its download-only mode, multilingual variant by default), on a Docker network of its own",
                  "limit_s": 780},
  "client": {"image": "nvcr.io/nvidia/nemo-microservices/nv-ingest:26.3.0", "program": "scripts/ocr_client_check.py, run with the image's own Python in a container on the same network; OCR_MODEL_NAME=pipeline (the Blueprint's value)",
             "endpoint": "http://<the OCR container>:8000/v1/ocr", "images": ["test_images/zh_statute_text.png with its known text", "the Blueprint's docs/assets/arch_diagram.png"], "calls_per_image": 2, "limit_s_per_image": 900},
  "also_recorded": "from the OCR container's log, the number of lines that name a request to /v1/ocr, and the card's memory once the service is ready",
  "pass": "both calls on the Chinese test image return text pieces, and at least 100 of its 118 CJK characters are among them",
  "if_not": "the exception type and its first line are the result; nothing is patched and no other configuration is tried"},
 "expectation": "passes: the request body and the answer's fields are the ones the client writes and reads. The CJK count is near the 114 of 118 the service gave when asked directly. Confidence moderate: what the client does before its first post (a readiness or metadata call) was not read.",
 "what_a_pass_does_not_show": "that the Blueprint's ingestion runs on this host: the page-elements service is still missing in front of it",
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in ("ocr_client_check.py", "smoke_step.py")},
 "test_image_sha256": {f: sha(os.path.join(V5, "test_images", f)) for f in ("zh_statute_text.png", "zh_statute_text.txt")},
}
os.makedirs(RES, exist_ok=True)
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
