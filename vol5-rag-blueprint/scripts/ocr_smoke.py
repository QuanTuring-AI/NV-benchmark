#!/usr/bin/env python3
"""Vol.5 preparation: one request to a running OCR NIM, and what came back. A smoke test, not a measurement.

The request is the one the RAG Blueprint's ingestion sends to this service (POST /v1/infer, deploy/compose of the
Blueprint): one image as a data URL. The image is a public one given on the command line. The HTTP status, the keys
of the answer and the number of text items are recorded; the recognised text is not.

Written after the pre-registration of the session was frozen, as that file says.
usage: ocr_smoke.py --url http://127.0.0.1:8000 --image FILE --out FILE.json
"""
import argparse, base64, hashlib, json, os, sys, time

import requests

ap = argparse.ArgumentParser(); ap.add_argument("--url", required=True); ap.add_argument("--image", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()
raw = open(a.image, "rb").read()
kind = "png" if a.image.lower().endswith(".png") else "jpeg"
body = {"input": [{"type": "image_url", "url": f"data:image/{kind};base64," + base64.b64encode(raw).decode()}]}
out = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "url": a.url, "image": {"name": os.path.basename(a.image), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}, "requests": []}
for path in ("/v1/health/ready", "/v1/metadata"):
    try:
        r = requests.get(a.url.rstrip("/") + path, timeout=30)
        out["requests"].append({"get": path, "status": r.status_code, "body": r.text[:300]})
    except Exception as e:
        out["requests"].append({"get": path, "error": f"{type(e).__name__}: {e}"[:200]})
for n in (1, 2):                                   # twice: the first request of a server is often not like the second
    t = time.perf_counter()
    try:
        r = requests.post(a.url.rstrip("/") + "/v1/infer", json=body, timeout=300)
        rec = {"post": "/v1/infer", "n": n, "status": r.status_code, "seconds": round(time.perf_counter() - t, 3)}
        if r.status_code == 200:
            d = r.json(); data = d.get("data") or []
            items = sum(len(x.get("text_detections") or []) for x in data if isinstance(x, dict))
            rec.update({"answer_keys": sorted(d.keys()), "data_items": len(data), "text_items": items, "first_item_keys": sorted(data[0].keys()) if data and isinstance(data[0], dict) else None})
        else:
            rec["body"] = r.text[:600]
    except Exception as e:
        rec = {"post": "/v1/infer", "n": n, "error": f"{type(e).__name__}: {e}"[:300], "seconds": round(time.perf_counter() - t, 3)}
    out["requests"].append(rec)
out["program_sha256"] = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
print(json.dumps([{k: r.get(k) for k in ("post", "get", "status", "seconds", "text_items", "error") if r.get(k) is not None} for r in out["requests"]]))
