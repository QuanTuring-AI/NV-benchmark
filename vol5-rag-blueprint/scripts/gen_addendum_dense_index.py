#!/usr/bin/env python3
"""Vol.5 · writes the second addendum to prediction_visual_path.json, with its .sha256 file: the library's extraction
once more with its default index mode (dense), after the first run with `--index-mode sparse` stored page rows only.
Run once, before the first container of the dense run. usage: gen_addendum_dense_index.py --embed-digest sha256:... [--draft]
"""
import collections, hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = os.path.join(VOL, "results", "visual_path"); OUT = os.path.join(RES, "addendum_dense_index.json"); DRAFT = "--draft" in sys.argv
EMB = sys.argv[sys.argv.index("--embed-digest") + 1]
if not (EMB.startswith("sha256:") and len(EMB) == 71):
    sys.exit("give --embed-digest as sha256:<64 hex>")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


first = json.load(open(os.path.join(RES, "library_extraction.json"), encoding="utf-8"))
runs = [json.loads(l) for l in open(os.path.join(RES, "library_extraction_runs.jsonl"), encoding="utf-8")]
keys = sorted({k for arm in first["arms"].values() for f in arm for ks in (f.get("metadata_keys_by_type") or {}).values() for k in ks})
notes = [json.loads(l) for l in open(os.path.join(RES, "events.jsonl"), encoding="utf-8") if '"label": "V3' in l]
A = {
 "what": "Second addendum to prediction_visual_path.json: cell V3 again with the library's default index mode, because the first run's `--index-mode sparse` changed what the library stores",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"file": "prediction_visual_path.json", "sha256": sha(os.path.join(RES, "prediction_visual_path.json"))},
 "after": {"file": "addendum_library_extraction.json", "sha256": sha(os.path.join(RES, "addendum_library_extraction.json"))},
 "first_run": {
  "calls": dict(collections.Counter(f"{r['arm']} · exit code {r['rc']}" for r in runs)), "seconds_of_all_calls": sum(r["seconds"] for r in runs),
  "rows": first["per_arm"], "metadata_keys_of_the_rows": keys, "card_notes": [{"label": n["label"], "text": n["text"]} for n in notes],
  "files": {n: sha(os.path.join(RES, n)) for n in ("library_extraction.json", "library_extraction_runs.jsonl")},
  "what_happened": "all 36 calls ended with exit code 0 and both arms stored the same rows: one row per page, without a type, with the page's detection counts in its metadata. No row for a table, a chart or an infographic exists.",
  "cause": "the library turns the tables, charts and infographics of a page into rows of their own in its embedding stage (explode_content_to_rows, called only inside the embed stage: nemo_retriever/src/nemo_retriever/graph/ingestor_runtime.py lines 570 to 593 at tag 26.8.2). "
           "`--index-mode sparse` leaves that stage out, and with it the rows. The first addendum called that option the one thing that was not a default and said it left extraction as it is; that was wrong for the stored rows.",
  "error_of_the_plan": "the option was chosen to keep an embedding model off the card, without tracing where the library builds its rows. Cost: about four minutes of the card.",
  "kept": "the first run's files stay as they are: the calls, the page rows, and the detection counts per page (which the dense run should show again as rows). The expectations of the first addendum about row types were not tested by it.",
  "repair_of_a_file": "the driver wrote library_extraction_runs.jsonl in the console's code page; it was converted to UTF-8 once after the run (content unchanged), before the summary read it"},
 "second_run": {
  "what_changes": "the call no longer has `--index-mode sparse` and has `--embed-invoke-url http://<embedding>:8000/v1/embeddings`; the library's default embedding model name is left as it is (nvidia/llama-nemotron-embed-vl-1b-v2)",
  "embedding_service": {"image": "nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:2.3.0", "image_digest": EMB,
                        "why_this_tag": "the tag of the library's Helm values and documentation at 26.8.2 (its development Compose file names 1.12.0); 2.3.0 is the tag Vol.4 measured on this host"},
  "arms": {"dense_defaults": "everything else as the command resolves it", "dense_infographics_on": "the same with --extract-infographics"},
  "inputs_and_other_services": "as in the first addendum: the 15 PDFs of the list and the 3 stand-in scans, one call per file; page elements, table structure and OCR as before",
  "recorded": "as in the first addendum (nrl_extraction_summary.py, unchanged), in library_extraction_dense.json; card memory with the four NIMs ready and after each arm",
  "limits_s": {"ready of the embedding NIM": 900, "one call": 600}},
 "expectations": {"calls": "all 36 end with exit code 0", "rows": "rows now carry a type. The expectations of the first addendum about categories 1, 2 and 3 apply to this run unchanged.",
                  "card": "the four NIMs together add less than 10 GiB to the card (the three extraction NIMs added 5,355 MiB)", "confidence": "low for the row types: the first run showed that the stored shape depends on stages this plan had not traced"},
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in ("nrl_extraction_summary.py", "ocr_text_smoke.py", "smoke_step.py", "session_step.py") if os.path.isfile(os.path.join(HERE, f))},
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen addendum exists")
json.dump(A, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + A["written_at"], sha(OUT))
