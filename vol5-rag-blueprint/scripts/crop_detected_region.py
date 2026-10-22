#!/usr/bin/env python3
"""Vol.5 · cuts one detected region out of a page image, the way NeMo Retriever Library 26.8.2 hands a chart region
to OCR: the box the page-elements model returned (coordinates as fractions of the page) is cropped from the page.

Reads the answer file of object_detection_smoke.py, takes the image entry named --image-label and its second request,
and crops the box with the highest confidence among the labels given, in the order given (the first label that has a
box wins). The crop is written to --out-image, which must lie outside the repository; --record gets the label, the
box, the pixel size and the SHA-256 of the crop, and the number of boxes per label on the page: no image, no text.
Exit code 3 when the page has no box with any of the labels (the record says so).

usage: crop_detected_region.py --answer FILE.json --image-label NAME --page-image FILE.png --labels chart,infographic
                               --out-image FILE.png --record FILE.json
"""
import argparse, hashlib, json, os, sys, time

from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answer", required=True); ap.add_argument("--image-label", required=True); ap.add_argument("--page-image", required=True); ap.add_argument("--labels", required=True)
    ap.add_argument("--out-image", required=True); ap.add_argument("--record", required=True)
    a = ap.parse_args()
    ans = json.load(open(a.answer, encoding="utf-8")); entry = next(im for im in ans["images"] if im["image"] == a.image_label)
    if hashlib.sha256(open(a.page_image, "rb").read()).hexdigest() != entry["sha256"]:
        sys.exit("refused: the page image is not the one that was sent")
    boxes = entry["requests"][-1].get("boxes") or {}
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "page_image": a.image_label, "page_image_sha256": entry["sha256"], "boxes_per_label": {k: len(v) for k, v in boxes.items()}, "labels_asked_in_order": a.labels.split(","),
           "cropped": None}
    for label in a.labels.split(","):
        cand = [b for b in boxes.get(label, []) if None not in b["box"]]
        if cand:
            b = max(cand, key=lambda x: x.get("confidence") or 0.0); img = Image.open(a.page_image); w, h = img.size; x0, y0, x1, y1 = b["box"]
            if max(x0, y0, x1, y1) <= 1.5:                       # fractions of the page
                x0, x1, y0, y1 = x0 * w, x1 * w, y0 * h, y1 * h
            crop = img.crop((max(0, int(x0)), max(0, int(y0)), min(w, int(round(x1))), min(h, int(round(y1)))))
            os.makedirs(os.path.dirname(os.path.abspath(a.out_image)), exist_ok=True); crop.save(a.out_image)
            rec["cropped"] = {"label": label, "box_as_returned": b["box"], "confidence": b.get("confidence"), "pixels": list(crop.size), "share_of_the_page": round(crop.size[0] * crop.size[1] / (w * h), 4),
                              "sha256": hashlib.sha256(open(a.out_image, "rb").read()).hexdigest()}
            break
    os.makedirs(os.path.dirname(os.path.abspath(a.record)), exist_ok=True)
    json.dump(rec, open(a.record, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"boxes_per_label": rec["boxes_per_label"], "cropped": rec["cropped"] and {k: rec["cropped"][k] for k in ("label", "pixels", "confidence")}}))
    return 0 if rec["cropped"] else 3


if __name__ == "__main__":
    sys.exit(main())
