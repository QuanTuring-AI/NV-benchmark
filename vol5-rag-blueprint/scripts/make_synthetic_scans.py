#!/usr/bin/env python3
"""Vol.5 · stand-ins for scanned documents. A corpus in which every PDF has a text layer has no file of category 1
("the text cannot be taken from the file"). This program makes such files from text-layer PDFs: every page is rendered
to an image at a fixed resolution and the images are written as a new PDF that has no text layer. The text layer of
the source stays where it is and is the reference for what an OCR path should find.

Written next to the PDFs (outside the repository): <out-dir>/synthetic_scan_<id>.pdf and, per file, the reference
text of each page (<out-dir>/reference/<id>.txt, pages separated by a form feed). Written to --record: ids, page
counts, pixel sizes, SHA-256 values and the character counts of the reference: no text, no image.

usage: make_synthetic_scans.py --list LIST.json --corpus DIR --ids ID[,ID...] --out-dir DIR --record FILE.json [--dpi 150]
"""
import argparse, hashlib, json, os, sys, time

import pypdfium2 as pdfium


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True); ap.add_argument("--corpus", required=True); ap.add_argument("--ids", required=True); ap.add_argument("--out-dir", required=True)
    ap.add_argument("--record", required=True); ap.add_argument("--dpi", type=int, default=150)
    a = ap.parse_args()
    files = {f["id"]: f for f in json.load(open(a.list, encoding="utf-8"))["files"]}
    os.makedirs(os.path.join(a.out_dir, "reference"), exist_ok=True); recs = []
    for fid in a.ids.split(","):
        f = files[fid]; src = os.path.join(a.corpus, f["file"])
        if f["format"] != "pdf" or sha256_file(src) != f["sha256"]:
            sys.exit(f"refused: {fid} is not a PDF of the list with its recorded SHA-256")
        doc = pdfium.PdfDocument(src); images, texts, sizes = [], [], []
        for i in range(len(doc)):
            page = doc[i]; tp = page.get_textpage(); texts.append(tp.get_text_range()); tp.close()
            img = page.render(scale=a.dpi / 72).to_pil().convert("RGB"); images.append(img); sizes.append(list(img.size)); page.close()
        doc.close()
        out = os.path.join(a.out_dir, f"synthetic_scan_{fid}.pdf")
        images[0].save(out, "PDF", resolution=float(a.dpi), save_all=True, append_images=images[1:])
        ref = os.path.join(a.out_dir, "reference", f"{fid}.txt"); open(ref, "w", encoding="utf-8", newline="\n").write("\f".join(texts))
        check = pdfium.PdfDocument(out); left = 0
        for i in range(len(check)):
            page = check[i]; tp = page.get_textpage(); left += sum(1 for c in tp.get_text_range() if not c.isspace()); tp.close(); page.close()
        pages_out = len(check); check.close()
        recs.append({"id": "synthetic_scan_" + fid, "made_from": fid, "source_sha256": f["sha256"], "pages": len(images), "pages_in_the_new_file": pages_out, "dpi": a.dpi, "page_pixels": sizes,
                     "sha256": sha256_file(out), "bytes": os.path.getsize(out), "text_layer_characters_left_in_the_new_file": left,
                     "reference": {"characters_without_white_space_per_page": [sum(1 for c in t if not c.isspace()) for t in texts], "sha256": sha256_file(ref)}})
    rec = {"what": "PDFs without a text layer, made by rendering text-layer PDFs of the list; stand-ins for scanned documents", "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "library": {"pypdfium2": pdfium.PYPDFIUM_INFO.version, "pdfium": str(pdfium.PDFIUM_INFO.version)}, "list_sha256": sha256_file(a.list), "files": recs}
    os.makedirs(os.path.dirname(os.path.abspath(a.record)), exist_ok=True)
    json.dump(rec, open(a.record, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps([{k: r[k] for k in ("id", "pages", "bytes", "text_layer_characters_left_in_the_new_file")} for r in recs]))
    return 0 if all(r["text_layer_characters_left_in_the_new_file"] == 0 and r["pages"] == r["pages_in_the_new_file"] for r in recs) else 4


if __name__ == "__main__":
    sys.exit(main())
