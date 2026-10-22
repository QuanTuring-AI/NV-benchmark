#!/usr/bin/env python3
"""Vol.5 · what NeMo Retriever Library's extraction returned for each file, counted. Reads the rows the library wrote
(exported to JSON lines outside the repository, one file per arm and input file: {"text", "metadata", "source"} as
stored, metadata and source being JSON strings), the category file, and for the stand-in scans the reference text of
each page. Writes one JSON: counts, page numbers, types, lengths, digests, boxes. No text of any file is written.

Per input file and arm:
  rows by type and by fidelity (the library's own labels in the row's metadata), pages that have a row, characters by type,
  the metadata keys seen per type, and per row: page, type, fidelity, characters, SHA-256 of the text, the box if any
For a stand-in scan (category 1): per page and in total, how many characters of the reference the rows of that page
  contain (multiset of characters, white space ignored; CJK characters also on their own), as returned and with both
  sides converted to Simplified forms (the OCR model mixes Simplified forms into Traditional text)
For rows of a figure type (chart, infographic, image): does the row say which page, what kind of figure, and does it
  carry a caption (a non-empty `caption` in its metadata, or a row of a *_caption type for the same box)

usage: nrl_extraction_summary.py --rows-dir DIR --runs RUNS.jsonl --categories FILE.json --references DIR --out OUT.json
       DIR/<arm>/<file id>.jsonl; RUNS.jsonl: one line per library call {"arm", "id", "rc", "seconds", ...}
"""
import argparse, collections, hashlib, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ocr_text_smoke import overlap  # noqa: E402

FIGURE_TYPES = ("chart", "infographic", "image")


def simplified(text):
    try:
        import opencc
        return opencc.OpenCC("t2s").convert(text)
    except Exception:
        return None


def load_rows(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line); m = r.get("metadata"); m = json.loads(m) if isinstance(m, str) and m else (m or {})
            rows.append({"text": r.get("text") or "", "meta": m})
    return rows


def row_type(m):
    return str(m.get("type") or "text")


def summarize_file(rows, category, reference_pages):
    by_type = collections.Counter(row_type(r["meta"]) for r in rows); by_fid = collections.Counter(str(r["meta"].get("fidelity")) for r in rows)
    chars = collections.Counter(); keys = collections.defaultdict(set); pages = set(); listed = []
    for r in rows:
        m = r["meta"]; t = row_type(m); n = sum(1 for c in r["text"] if not c.isspace()); chars[t] += n; keys[t].update(m.keys())
        if m.get("page_number") is not None:
            pages.add(m["page_number"])
        listed.append({"page": m.get("page_number"), "type": t, "fidelity": m.get("fidelity"), "characters": n, "text_sha256": hashlib.sha256(r["text"].encode("utf-8")).hexdigest(),
                       "box": m.get("bbox_xyxy_norm"), "chunk": [m.get("chunk_index"), m.get("chunk_count")] if m.get("chunk_index") is not None else None})
    out = {"category": category, "rows": len(rows), "rows_by_type": dict(by_type), "rows_by_fidelity": dict(by_fid), "characters_by_type": dict(chars), "pages_with_a_row": sorted(pages),
           "metadata_keys_by_type": {t: sorted(k) for t, k in keys.items()}, "row_list": listed}
    figs = [r for r in rows if row_type(r["meta"]).replace("_caption", "") in FIGURE_TYPES]
    caption_boxes = {json.dumps(r["meta"].get("bbox_xyxy_norm")) for r in rows if row_type(r["meta"]).endswith("_caption")}
    out["figure_rows"] = [{"page": r["meta"].get("page_number"), "type": row_type(r["meta"]), "says_which_page": r["meta"].get("page_number") is not None, "says_what_kind": row_type(r["meta"]) in FIGURE_TYPES,
                           "carries_a_caption": bool(r["meta"].get("caption")) or json.dumps(r["meta"].get("bbox_xyxy_norm")) in caption_boxes, "has_a_box": r["meta"].get("bbox_xyxy_norm") is not None,
                           "characters": sum(1 for c in r["text"] if not c.isspace())} for r in figs if not row_type(r["meta"]).endswith("_caption")]
    if reference_pages is not None:
        per = []; got_all = ""; conv = simplified("") is not None
        for i, ref in enumerate(reference_pages, 1):
            got = "".join(r["text"] for r in rows if r["meta"].get("page_number") == i); got_all += got
            p = {"page": i, "rows": sum(1 for r in rows if r["meta"].get("page_number") == i), "as_returned": overlap(ref, got)}
            if conv:
                p["both_sides_simplified"] = overlap(simplified(ref), simplified(got))
            per.append(p)
        ref_all = "".join(reference_pages)
        out["against_the_reference_text"] = {"pages": len(reference_pages), "pages_with_a_row": sum(1 for p in per if p["rows"]), "as_returned": overlap(ref_all, got_all),
                                             "both_sides_simplified": overlap(simplified(ref_all), simplified(got_all)) if conv else None, "per_page": per}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows-dir", required=True); ap.add_argument("--runs", required=True); ap.add_argument("--categories", required=True); ap.add_argument("--references", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cats = {f["id"]: f for f in json.load(open(a.categories, encoding="utf-8"))["files"]}
    runs = [json.loads(l) for l in open(a.runs, encoding="utf-8") if l.strip()]
    arms = {}
    for run in runs:
        arm, fid = run["arm"], run["id"]; path = os.path.join(a.rows_dir, arm, fid + ".jsonl"); c = cats.get(fid, {})
        rec = {"id": fid, "library_call": {k: run.get(k) for k in ("rc", "seconds", "rows_reported", "at")}, "pages_of_the_file": (c.get("decided_by") or {}).get("pages")}
        if run.get("rc") == 0 and os.path.isfile(path):
            ref = None
            if fid.startswith("synthetic_scan_"):
                rp = os.path.join(a.references, fid[len("synthetic_scan_"):] + ".txt"); ref = open(rp, encoding="utf-8").read().split("\f")
            rec.update(summarize_file(load_rows(path), c.get("category"), ref)); rec["rows_file_sha256"] = hashlib.sha256(open(path, "rb").read()).hexdigest()
            if rec["pages_of_the_file"]:
                rec["seconds_per_page"] = round(run["seconds"] / rec["pages_of_the_file"], 2); rec["pages_without_a_row"] = [p for p in range(1, rec["pages_of_the_file"] + 1) if p not in rec["pages_with_a_row"]]
        else:
            rec["failed"] = True; rec["last_lines_of_the_call"] = run.get("tail")
        arms.setdefault(arm, []).append(rec)
    table = {}
    for arm, files in arms.items():
        t = collections.Counter(); fig = collections.Counter()
        for f in files:
            for k, v in (f.get("rows_by_type") or {}).items():
                t[f"category {f.get('category')} · {k}"] += v
            for r in f.get("figure_rows") or []:
                fig["figure rows"] += 1; fig["say which page"] += r["says_which_page"]; fig["say what kind"] += r["says_what_kind"]; fig["carry a caption"] += r["carries_a_caption"]; fig["have a box"] += r["has_a_box"]
        table[arm] = {"files": len(files), "failed": sum(1 for f in files if f.get("failed")), "rows_by_category_and_type": dict(sorted(t.items())), "figure_rows": dict(fig)}
    out = {"what": "rows returned by the library's extraction, per arm and input file; counts, digests and boxes only", "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "character_measure": "multiset of characters, white space ignored (ocr_text_smoke.overlap); the Simplified conversion is OpenCC t2s on both sides" + ("" if simplified("") is not None else " (not available in this environment)"),
           "per_arm": table, "arms": arms}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps(table, ensure_ascii=False))


if __name__ == "__main__":
    main()
