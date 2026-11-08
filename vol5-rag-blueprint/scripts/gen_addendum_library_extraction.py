#!/usr/bin/env python3
"""Vol.5 · writes the addendum to prediction_visual_path.json for the library's whole extraction (cell V3) and the
memory budget of the extraction side (cell V4), with its .sha256 file. Run once, before the first container of V3.
usage: gen_addendum_library_extraction.py --nrl-digest sha256:... [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = os.path.join(VOL, "results", "visual_path"); OUT = os.path.join(RES, "addendum_library_extraction.json"); DRAFT = "--draft" in sys.argv
NRL = sys.argv[sys.argv.index("--nrl-digest") + 1]
if not (NRL.startswith("sha256:") and len(NRL) == 71):
    sys.exit("give --nrl-digest as sha256:<64 hex>")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load(name):
    return json.load(open(os.path.join(RES, name), encoding="utf-8"))


cat = load("category_by_file.json"); pe = load("od_page_elements.json"); ts = load("od_table_structure.json"); fig = load("figure_page_elements.json"); crop = load("figure_region_crop.json"); ocr = load("figure_region_ocr.json")
ready = [json.loads(l) for l in open(os.path.join(RES, "events.jsonl"), encoding="utf-8") if '"kind": "ready"' in l]
seen = {
 "containers_ready": [{"name": e["name"], "seconds": e["seconds_to_verdict"], "card_memory_added_mib": e["card_memory_added_mib"]} for e in ready],
 "page_elements": {im["image"]: im["requests"][-1].get("boxes_per_label") for im in pe["images"]}, "table_structure": {im["image"]: im["requests"][-1].get("boxes_per_label") for im in ts["images"]},
 "figure_page": {"boxes_per_label": fig["images"][0]["requests"][-1].get("boxes_per_label"), "cropped_label": (crop.get("cropped") or {}).get("label"),
                 "ocr_of_the_crop": {k: r.get(k) for r in ocr["requests"] if r.get("post") for k in ("status", "text_items", "characters_returned")}},
 "files": {"V1 and V2 result files": {n: sha(os.path.join(RES, n)) for n in ("od_page_elements.json", "od_table_structure.json", "figure_page_elements.json", "figure_region_crop.json", "figure_region_ocr.json", "category_by_file.json", "synthetic_scans.json")}}}
BOUND = ["nrl_extraction_summary.py", "ocr_text_smoke.py", "smoke_step.py"]
A = {
 "what": "Addendum to prediction_visual_path.json: the library's extraction over every PDF of the list and the three stand-in scans (V3), and the card memory of the extraction side (V4)",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"file": "prediction_visual_path.json", "sha256": sha(os.path.join(RES, "prediction_visual_path.json"))},
 "seen_in_V1_and_V2": seen,
 "what_V1_and_V2_change": "the page-elements model labelled the picture of the figure page `infographic`, not `chart`. The library extracts charts by default and infographics only on request "
                          "(extract_charts true, extract_infographics false: nemo_retriever/src/nemo_retriever/common/params/models.py lines 510 to 539 at tag 26.8.2). V3 therefore has two arms.",
 "V3": {
  "inputs": {"files": sorted(f["id"] for f in cat["files"] if f["format"] == "pdf"), "categories": cat["counts"], "category_file_sha256": sha(os.path.join(RES, "category_by_file.json")),
             "not_an_input": "Markdown files (the library reads them as text: no layout model, no OCR), and any file outside the list"},
  "services": {"page elements and table structure": "nemotron-object-detection 2.0.1, one container per model", "OCR": "nemotron-ocr-v2 2.0.1, NIM_ENGINE_MODEL_VARIANT=multilingual",
               "environment": "as the library's Compose file sets it for the three (nemo_retriever/dev/compose/service-mode.compose.yaml lines 105 to 170); all three on the card at once, on one Docker network"},
  "library": {"image": "nvcr.io/nvidia/nemo-microservices/nrl-service:26.8.2", "image_digest": NRL, "started_without": "--gpus (it calls the three services over HTTP)",
              "call": "retriever ingest /in/<id>.pdf --page-elements-invoke-url http://<page-elements>:8000/v1/page-elements --table-structure-invoke-url http://<table-structure>:8000/v1/table-structure "
                      "--ocr-invoke-url http://<ocr>:8000/v1/ocr --index-mode sparse --lancedb-uri /out/<arm>/lancedb --table-name <id>",
              "one_call_per_file": "so that every file has its own duration and its own exit code",
              "what_is_not_a_default": "--index-mode sparse: the rows are stored without vectors, so no embedding model is on the card. Everything about extraction is left as the command resolves it: "
                                       "method pdfium_hybrid, tables and charts on, infographics off, page images on, 200 dpi, no text chunking, no caption stage."},
  "arms": {"defaults": "the call above", "infographics_on": "the call above with --extract-infographics"},
  "recorded": "per call: exit code, seconds, rows reported. Per file from the stored rows: rows by type and fidelity, pages with a row, characters by type, per row page / type / characters / digest / box. "
              "For the stand-in scans: characters of the reference text found, per page and in total, as returned and with both sides in Simplified forms. For rows of a figure type: page, kind, caption, box. "
              "The rows themselves (text) stay outside the repository.",
  "limits_s": {"ready": 660, "one call": 600, "export of the rows": 600},
  "program": "nrl_extraction_summary.py"},
 "V4": "card memory read with the three NIMs ready and after each arm (the events file); whether the generation side fits beside them is measured with the ingestion and generation cells, which get their own pre-registration",
 "expectations": {
  "calls": "all 36 calls end with exit code 0",
  "category 2 (13 files)": "one text row per page with fidelity verbatim; the nine one-page annex tables each give at least one table row whose text came from OCR, so the table's characters are there twice (page text and table row)",
  "category 3 (2 files)": "arm defaults: no row of type infographic and none of type image (images become rows only with a caption stage); arm infographics_on: at least one infographic row for the file whose figure page was sent in V2. "
                          "Every figure row says its page and its kind and has a box; none carries a caption",
  "category 1 (3 stand-ins)": "every page gets at least one row whose text came from OCR; of the reference's CJK characters at least 80% are found as returned and more with both sides Simplified "
                              "(an earlier check of this OCR model on 129 pages of Traditional Chinese found about 87%)",
  "V4": "the three NIMs together add less than 6 GiB to the card (1,155 + 1,155 + 3,040 MiB when started alone)",
  "confidence": "moderate for the calls and the scans; low for the row types (the library has not been run on this host)"},
 "branches_decided_in_advance": {"a call fails": "its last lines are the result for that file; the other files stand", "figure rows carry no caption": "written as: the library's default path does not attach a figure's printed caption",
                                 "the library needs a setting changed to run here": "the setting and the reason are recorded in the events file before the rerun; a changed extraction default is a separate arm, never a silent replacement"},
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in BOUND},
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen addendum exists")
json.dump(A, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + A["written_at"], sha(OUT))
