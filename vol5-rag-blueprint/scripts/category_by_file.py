#!/usr/bin/env python3
"""Vol.5 · sorts every file of a corpus list into one of three categories by a mechanical rule, before any extraction
is run. The unit of the decision is the whole file.

  1  the file's text cannot be taken from the file itself  -> every page goes through OCR
  2  the text can be taken, and the file has no figure      -> no OCR
  3  the text can be taken, and the file has figures        -> text as in 2; every figure separately

What is counted, per page of a PDF, with pdfium (the library NV-Ingest itself reads PDFs with):
  text-layer characters   non-white-space characters of the page's text layer
  image objects           each with the share of the page its box covers (form objects are entered, up to 4 levels)
  drawing objects         path and shading objects (lines, rules, filled shapes: tables, charts, decoration alike)

The rule (thresholds are arguments; the values used are written into the output and into the pre-registration):
  a page "has text"       when it has at least --min-chars text-layer characters
  a page is "empty"       when it has no object at all
  category 1              when fewer than --min-text-share of the non-empty pages have text
  a "figure"              an image object covering at least --figure-min-share and less than --full-page-share of the
                          page, and at least --figure-min-px wide and high as stored
  a "full-page image"     an image object covering --full-page-share of the page or more (a scan, or a slide
                          background): counted, never a figure
  category 3              not 1, and at least one figure
  category 2              not 1, no figure
  a Markdown or text file category 2 (it is its own text; this program does not look for image links in it)

What the rule cannot see is written next to the result, not hidden: a chart drawn with vector lines is not an image
object (the count of drawing objects per page is reported so that such pages can be found; it does not decide the
category, because the rules of a table are drawing objects too); and a figure stored as many small tiles is counted
tile by tile. The output holds ids, counts and digests only: no text and no image of any file.

usage: category_by_file.py --list LIST.json --corpus DIR --out OUT.json [--extra-dir DIR] [thresholds]
       LIST.json: {"files": [{"id", "file", "format", "sha256"}, ...]}; --extra-dir: PDFs outside the list (id = stem)
"""
import argparse, hashlib, json, os, statistics, sys, time

import pypdfium2 as pdfium
import pypdfium2.raw as raw

KIND = {raw.FPDF_PAGEOBJ_TEXT: "text", raw.FPDF_PAGEOBJ_PATH: "path", raw.FPDF_PAGEOBJ_IMAGE: "image", raw.FPDF_PAGEOBJ_SHADING: "shading", raw.FPDF_PAGEOBJ_FORM: "form"}


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def page_counts(page, a):
    w, h = page.get_size(); area = max(w * h, 1e-9)
    tp = page.get_textpage(); chars = sum(1 for c in tp.get_text_range() if not c.isspace()); tp.close()
    n = {"text": 0, "path": 0, "image": 0, "shading": 0, "form": 0, "other": 0}; figures = full = small = 0; shares = []
    for obj in page.get_objects(max_depth=4):
        k = KIND.get(obj.type, "other"); n[k] += 1
        if k != "image":
            continue
        l, b, r, t = obj.get_bounds(); share = max(0.0, min(r, w) - max(l, 0)) * max(0.0, min(t, h) - max(b, 0)) / area
        try:
            px = obj.get_px_size()
        except Exception:
            px = (0, 0)
        shares.append(round(share, 4))
        if share >= a.full_page_share:
            full += 1
        elif share >= a.figure_min_share and min(px) >= a.figure_min_px:
            figures += 1
        else:
            small += 1
    return {"chars": chars, "objects": sum(n.values()), "text_objects": n["text"], "image_objects": n["image"], "drawing_objects": n["path"] + n["shading"],
            "figures": figures, "full_page_images": full, "small_images": small, "largest_image_share": max(shares) if shares else 0.0}


def classify(pages, a):
    non_empty = [p for p in pages if p["objects"] > 0]
    with_text = [p for p in non_empty if p["chars"] >= a.min_chars]
    share = (len(with_text) / len(non_empty)) if non_empty else 0.0
    figures = sum(p["figures"] for p in pages)
    cat = 1 if share < a.min_text_share else (3 if figures >= 1 else 2)
    return cat, {"pages": len(pages), "non_empty_pages": len(non_empty), "pages_with_text": len(with_text), "share_of_non_empty_pages_with_text": round(share, 4), "figures": figures}


def pdf_record(path, a):
    doc = pdfium.PdfDocument(path); pages = []
    for i in range(len(doc)):
        page = doc[i]; pages.append(page_counts(page, a)); page.close()
    doc.close()
    cat, used = classify(pages, a); ch = [p["chars"] for p in pages]; dr = [p["drawing_objects"] for p in pages]
    return {"category": cat, "decided_by": used,
            "text_layer_characters": {"total": sum(ch), "per_page_min": min(ch), "per_page_median": statistics.median(ch), "per_page_max": max(ch)},
            "image_objects": {"all": sum(p["image_objects"] for p in pages), "figures": used["figures"], "full_page_images": sum(p["full_page_images"] for p in pages),
                              "small_images": sum(p["small_images"] for p in pages), "pages_with_a_figure": sum(1 for p in pages if p["figures"])},
            "drawing_objects": {"total": sum(dr), "per_page_max": max(dr), "pages_at_or_over_the_report_line": sum(1 for d in dr if d >= a.drawing_report_line)},
            "per_page": {"chars": ch, "figures": [p["figures"] for p in pages], "full_page_images": [p["full_page_images"] for p in pages], "drawing_objects": dr,
                         "largest_image_share": [p["largest_image_share"] for p in pages]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True); ap.add_argument("--corpus", required=True); ap.add_argument("--out", required=True); ap.add_argument("--extra-dir", default="")
    ap.add_argument("--min-chars", type=int, default=20); ap.add_argument("--min-text-share", type=float, default=0.9)
    ap.add_argument("--figure-min-share", type=float, default=0.02); ap.add_argument("--full-page-share", type=float, default=0.9)
    ap.add_argument("--figure-min-px", type=int, default=64); ap.add_argument("--drawing-report-line", type=int, default=300)
    a = ap.parse_args()
    L = json.load(open(a.list, encoding="utf-8")); files = []
    for f in L["files"]:
        path = os.path.join(a.corpus, f["file"])
        if sha256_file(path) != f["sha256"]:
            sys.exit(f"refused: {f['id']} does not have the SHA-256 of the list")
        if f["format"] == "pdf":
            rec = pdf_record(path, a)
        else:
            rec = {"category": 2, "decided_by": {"rule": "a Markdown or text file is category 2"}}
        files.append({"id": f["id"], "sha256": f["sha256"], "format": f["format"], "in_the_list": True, **rec})
    if a.extra_dir:
        for name in sorted(os.listdir(a.extra_dir)):
            if name.lower().endswith(".pdf"):
                path = os.path.join(a.extra_dir, name)
                files.append({"id": os.path.splitext(name)[0], "sha256": sha256_file(path), "format": "pdf", "in_the_list": False, **pdf_record(path, a)})
    by = {}
    for f in files:
        k = f"category {f['category']} · {f['format']}" + ("" if f["in_the_list"] else " · outside the list"); by[k] = by.get(k, 0) + 1
    out = {"what": "one record per file: the category the mechanical rule gives it and every count the rule used; ids, counts and digests only",
           "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "list": {"file": os.path.basename(a.list), "sha256": sha256_file(a.list), "files": len(L["files"])},
           "library": {"pypdfium2": pdfium.PYPDFIUM_INFO.version, "pdfium": str(pdfium.PDFIUM_INFO.version)},
           "thresholds": {"min_chars": a.min_chars, "min_text_share": a.min_text_share, "figure_min_share": a.figure_min_share, "full_page_share": a.full_page_share,
                          "figure_min_px": a.figure_min_px, "drawing_report_line": a.drawing_report_line},
           "not_seen_by_the_rule": ["a chart drawn with vector objects (reported as drawing objects per page; does not decide the category)", "a figure stored as many small tiles",
                                    "image links inside a Markdown file"],
           "counts": by, "files": files}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"files": len(files), "counts": by}, ensure_ascii=False))


if __name__ == "__main__":
    main()
