#!/usr/bin/env python3
"""Vol.5 · a smoke test of the object-detection NIM 2.0 (one image serves page elements or table structure, chosen by
NIM_ENGINE_MODEL_NAME): each image is sent twice to the endpoint of the model the container serves, and what came
back is counted. A smoke test, not a measurement.

The request is the one NeMo Retriever Library 26.8.2 sends (nemo_retriever/models/nim/nim.py, lines 314 to 324):
    POST /v1/page-elements | /v1/table-structure      {"input": [{"type": "image_url", "url": "data:image/png;base64,..."}]}
Recorded per request: HTTP status, seconds, the shape of the answer (key names and counts, no string values), and,
when the answer has the form data[i].bounding_boxes.<label> = [boxes], the number of boxes per label and each box's
coordinates and confidence. No image and no recognised text is stored. For an error the first 600 characters of the
server's answer are kept: that text is the result.

usage: object_detection_smoke.py --url http://127.0.0.1:8000 --endpoint page-elements|table-structure --out FILE.json
                                 --image FILE [--image FILE ...] [--label NAME ...] [--timeout 300]
       --label: a name to store for each image in place of its file name (the same number of times as --image)
"""
import argparse, base64, hashlib, json, os, sys, time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extraction_smoke import shape  # noqa: E402


def boxes_of(d):
    """-> per image: {label: [{"box": [x_min, y_min, x_max, y_max], "confidence": c}, ...]} or None if the form is another one."""
    try:
        out = []
        for item in d["data"]:
            bb = item["bounding_boxes"]; per = {}
            for label, boxes in bb.items():
                per[label] = [{"box": [b.get("x_min"), b.get("y_min"), b.get("x_max"), b.get("y_max")], "confidence": b.get("confidence")} for b in boxes]
            out.append(per)
        return out
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--endpoint", choices=["page-elements", "table-structure"], required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--image", action="append", required=True); ap.add_argument("--label", action="append"); ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    if a.label and len(a.label) != len(a.image):
        raise SystemExit("refused: give --label as often as --image, or not at all")
    path = "/v1/" + a.endpoint; base = a.url.rstrip("/")
    out = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "url": a.url, "path": path, "request": {"input": "one image as a data URL, type image_url"}, "gets": [], "images": []}
    for p in ("/v1/health/ready", "/v1/metadata", "/v1/models"):
        try:
            r = requests.get(base + p, timeout=30); out["gets"].append({"get": p, "status": r.status_code, "body": r.text[:400]})
        except Exception as e:
            out["gets"].append({"get": p, "error": f"{type(e).__name__}: {e}"[:200]})
    for i, image in enumerate(a.image):
        raw = open(image, "rb").read(); kind = "png" if image.lower().endswith(".png") else "jpeg"
        body = {"input": [{"type": "image_url", "url": f"data:image/{kind};base64," + base64.b64encode(raw).decode()}]}
        rec = {"image": a.label[i] if a.label else os.path.basename(image), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "requests": []}
        for n in (1, 2):                               # twice: the first request of a server is often not like the second
            t = time.perf_counter()
            try:
                r = requests.post(base + path, json=body, timeout=a.timeout)
                q = {"n": n, "status": r.status_code, "seconds": round(time.perf_counter() - t, 3)}
                if r.status_code == 200:
                    d = r.json(); q["answer_shape"] = shape(d); b = boxes_of(d)
                    if b is not None:
                        q["boxes_per_label"] = {k: len(v) for k, v in b[0].items()} if b else {}; q["boxes"] = b[0] if b else {}
                else:
                    q["body"] = r.text[:600]
            except Exception as e:
                q = {"n": n, "error": f"{type(e).__name__}: {e}"[:300], "seconds": round(time.perf_counter() - t, 3)}
            rec["requests"].append(q)
        out["images"].append(rec)
    out["program_sha256"] = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps([{"image": im["image"], "requests": [{k: q.get(k) for k in ("status", "seconds", "boxes_per_label", "error") if q.get(k) is not None} for q in im["requests"]]} for im in out["images"]]))
    ok = all(q.get("status") == 200 for im in out["images"] for q in im["requests"])
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
