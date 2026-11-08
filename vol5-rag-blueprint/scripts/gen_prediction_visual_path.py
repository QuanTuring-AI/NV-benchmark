#!/usr/bin/env python3
"""Vol.5 · writes the pre-registration of the first cells on the visual path of ingestion (the object-detection NIM
2.0 and the path a chart takes in NeMo Retriever Library 26.8.2), with the rule that sorts files into three
categories, and its .sha256 file. Run once, before the first container of these cells.
usage: gen_prediction_visual_path.py --od-digest sha256:... --ocr-digest sha256:... [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = os.path.join(VOL, "results", "visual_path"); OUT = os.path.join(RES, "prediction_visual_path.json"); DRAFT = "--draft" in sys.argv


def arg(name):
    v = sys.argv[sys.argv.index(name) + 1]
    if not (v.startswith("sha256:") and len(v) == 71):
        sys.exit(f"give {name} as sha256:<64 hex>, copied from `docker image inspect`")
    return v


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


OD, OCR = arg("--od-digest"), arg("--ocr-digest")
BOUND = ["object_detection_smoke.py", "crop_detected_region.py", "category_by_file.py", "make_synthetic_scans.py", "smoke_step.py", "ocr_text_smoke.py", "extraction_smoke.py"]
pred = {
 "what": "Pre-registration: the three-category rule for files, the object-detection NIM 2.0 on this host (page elements, table structure), and the path of a chart region to OCR",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "host": "one RTX 5090 (32 GB), Windows 11 + Docker Desktop (WSL2), graphics driver 610.88",
 "background": {
  "found_on_2026-10-04": "the Triton-based extraction NIMs of the RAG Blueprint v2.6.2 (page elements, graphic elements, table structure 1.8.0; OCR 1.3.0) do not become ready on this host: their Python backends share GPU tensors "
                         "between processes, which Docker Desktop's WSL2 does not provide. EXTRACTION_NIMS_ON_WSL2.md has the evidence.",
  "what_is_new": "NeMo Retriever Library 26.8.2 names one image for page elements and table structure, nemotron-object-detection 2.0.x, whose runtime is not Triton, and reads charts by cropping the region the page-elements model "
                 "labels `chart` and sending it to OCR (no graphic-elements model). The OCR NIM of the same runtime family (nemotron-ocr-v2 2.0.1) runs on this host (results/co_resident_smoke, results/ocr_client_check).",
  "sources": "the library's repository at tag 26.8.2 (commit 6bb5a7bbd19062cdaf4882a329a685db7d77a27f): nemo_retriever/dev/compose/service-mode.compose.yaml lines 103 to 170; docs/docs/extraction/multimodal-extraction.md lines 50 and 63"},
 "three_categories": {
  "categories_as_given": ["1 the text of the file cannot be taken from the file: the whole file goes through OCR, chunks per page",
                               "2 the text can be taken and the file has text and tables, no figures: no OCR",
                               "3 the text can be taken and the file has figures: text and tables as in 2; every figure separately through OCR, and its source must say which page, what kind of figure, and what its caption says"],
  "program": "category_by_file.py (the unit is the whole file; counts per page with pdfium)",
  "thresholds": {"min_chars": 20, "min_text_share": 0.9, "figure_min_share": 0.02, "full_page_share": 0.9, "figure_min_px": 64, "drawing_report_line": 300},
  "said_before_the_freeze": "the thresholds were written into the program before its first run. One draft run over the 15 PDFs of the list was made before this file was frozen (13 files category 2, 2 files category 3); "
                            "no threshold was changed after it. What that run showed about the rule's limits: an image of about 2.3% of the page that repeats on most pages of two slide decks (a logo) counts as a figure, "
                            "and it is the only reason one of the two files is category 3. The rule is kept as written; the count is reported.",
  "markdown_files": "category 2 by rule",
  "stand_ins_for_category_1": {"why": "every PDF of the list has a text layer", "program": "make_synthetic_scans.py --dpi 150",
                               "which": "the three PDFs of the list with the most text-layer characters among those with at most 25 pages", "names": "synthetic_scan_<id>.pdf, kept outside the repository"}},
 "cells": {
  "V1": {"what": "the object-detection NIM 2.0.1, started once per model (two containers, one after the other)",
         "image": "nvcr.io/nim/nvidia/nemotron-object-detection:2.0.1", "image_digest": OD,
         "models": {"page-elements": "NIM_ENGINE_MODEL_NAME=nvidia/nemotron-page-elements-v3, NIM_ENGINE_MODEL_PATH=/model/page-elements, POST /v1/page-elements",
                    "table-structure": "NIM_ENGINE_MODEL_NAME=nvidia/nemotron-table-structure-v1, NIM_ENGINE_MODEL_PATH=/model/table-structure, POST /v1/table-structure"},
         "environment": "as the library's Compose file sets it: NIM_ENGINE_MODEL_DOWNLOAD_PROVIDER=ngc, NIM_PERFORMANCE_MODE=0, NIM_SERVER_MODE=latency, NIM_SERVER_MAX_WAIT_MS=0, NIM_ENGINE_COUNT=1, NIM_PIPELINE_MAX_BATCH_SIZE=1; "
                        "the model files were fetched before with the image's download-only mode and are mounted at /model",
         "images_sent": ["the RAG Blueprint's example image (docs/assets/arch_diagram.png of the Blueprint repository at v2.6.2)", "one page of a PDF of the list that is a table, rendered at 150 dpi"],
         "program": "object_detection_smoke.py (each image twice)", "recorded": "seconds to ready, card memory added, HTTP status, boxes per label with coordinates and confidence; no image, no text",
         "limits_s": {"ready": 660, "requests": 300},
         "reading": {"status 200 and at least one box on the table page, for both models": "the layout and table blockage on this host is lifted for this image; the table of 2026-10-04 gets a new row",
                     "a container does not become ready": "the last lines of its log are the result",
                     "ready but an error status": "the first 600 characters of the answer are the result"}},
  "V2": {"what": "the path of a figure in 26.8.2, by hand on one page: the page-elements model on a page with a figure; the first region it labels chart or infographic (or, if it labels none, the fact) is cropped and sent to the OCR NIM",
         "page": "of the file of the list with figures, the page whose largest image object covers the largest share of the page, rendered at 150 dpi",
         "containers": "the page-elements container of V1 and nemotron-ocr-v2 2.0.1 (" + OCR + "), both on the card",
         "programs": "object_detection_smoke.py, crop_detected_region.py (the crop stays outside the repository), ocr_text_smoke.py --form ocr",
         "recorded": "the labels and boxes on the page, which region was cropped, the number of characters OCR returned for it; whether anything in either answer is a caption or a figure type beyond the label",
         "not_run": {"graphic-elements": "not part of 26.8.2 (its controls were removed; nemo_retriever/tests/test_params_models.py lines 125 to 127); the 1.8.0 image is the one that does not become ready here",
                     "caption model": "26.8.2 names nemotron-3-nano-omni-30b-a3b-reasoning (optional, off by default); its documentation gives about 80 GB of disk for the NIM and lists a 32 GB Blackwell card as not supported; not downloaded"},
         "limits_s": {"ready": 660, "requests": 300}}},
 "expectations": {
  "V1": "both models become ready and answer 200. The page-elements model returns at least one box labelled table on the table page; the table-structure model returns cell, row or column boxes on it. "
        "Card memory added per container below 4 GiB. Confidence: moderate (the OCR NIM of the same runtime family runs here; this image has not been started on this host).",
  "V2": "the page-elements model labels at least one region of the figure page chart or infographic; OCR returns text for the crop (labels and numbers of the figure). Neither answer carries the figure's own caption as a field. "
        "Confidence: low for the label (a slide's picture may be labelled as text or not at all)."},
 "not_in_this_file": ["the library's whole extraction over the list and the stand-ins, and the memory budget: an addendum before their first container", "ingestion into a vector store, generation",
                      "any text or image of a file: results hold ids, counts, boxes and digests"],
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in BOUND},
}
os.makedirs(RES, exist_ok=True)
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
