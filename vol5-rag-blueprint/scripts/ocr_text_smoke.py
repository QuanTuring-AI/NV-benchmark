#!/usr/bin/env python3
"""Vol.5 · one image sent to a running OCR service, and how much of a known text came back. A smoke test, not a
measurement of accuracy: one image, sent twice.

Two request forms:
  ocr     POST /v1/ocr    {"input": [{"type": "image_url", "url": <data URL>}], "merge_levels": [<level>]}
          — the form documented for the nemotron-ocr-v2 NIM (release 2.0; getting-started page of its documentation)
  infer   POST /v1/infer  {"input": [{"type": "image_url", "url": <data URL>}]}
          — the form of the 1.x OCR services (nemotron-ocr-v1, PaddleOCR)
Both answer with data[].text_detections[].text_prediction.text.

Recorded: the HTTP status, the seconds, how many text items came back and how many characters. With --expected (the
text that was rendered into the image): how many of its characters are in the answer, counted with multiplicity and
without white space, for all characters and for the CJK ones alone; and how many returned characters are not in the
expected text. Of the recognised text itself only the first 50 characters are kept. For an error, the first 600
characters of the server's answer are kept.

usage: ocr_text_smoke.py --form ocr|infer --url http://127.0.0.1:8010 --image FILE.png --out FILE.json
                         [--expected FILE.txt] [--merge-level word] [--timeout 300]
"""
import argparse, base64, collections, hashlib, json, os, sys, time

import requests


def cjk(c):
    return "一" <= c <= "鿿"


def overlap(expected, got):
    e = collections.Counter(c for c in expected if not c.isspace()); g = collections.Counter(c for c in got if not c.isspace())
    hit = sum((e & g).values())
    e_cjk = collections.Counter({c: n for c, n in e.items() if cjk(c)}); g_cjk = collections.Counter({c: n for c, n in g.items() if cjk(c)})
    return {"expected_characters": sum(e.values()), "found": hit, "share_found": round(hit / max(1, sum(e.values())), 4),
            "expected_cjk_characters": sum(e_cjk.values()), "cjk_found": sum((e_cjk & g_cjk).values()),
            "share_of_cjk_found": round(sum((e_cjk & g_cjk).values()) / max(1, sum(e_cjk.values())), 4),
            "returned_characters": sum(g.values()), "returned_cjk_characters": sum(g_cjk.values()),
            "returned_not_in_expected": sum((g - e).values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--form", choices=["ocr", "infer"], required=True); ap.add_argument("--url", required=True); ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--expected"); ap.add_argument("--merge-level", default="word"); ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    raw = open(a.image, "rb").read()
    kind = "png" if a.image.lower().endswith(".png") else "jpeg"
    body = {"input": [{"type": "image_url", "url": f"data:image/{kind};base64," + base64.b64encode(raw).decode()}]}
    path = "/v1/infer"
    if a.form == "ocr":
        path = "/v1/ocr"; body["merge_levels"] = [a.merge_level]
    expected = open(a.expected, encoding="utf-8").read() if a.expected else None
    out = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "form": a.form, "url": a.url, "path": path, "merge_level": a.merge_level if a.form == "ocr" else None,
           "image": {"name": os.path.basename(a.image), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
           "expected": ({"name": os.path.basename(a.expected), "sha256": hashlib.sha256(expected.encode("utf-8")).hexdigest()} if expected else None), "requests": []}
    for p in ("/v1/health/ready", "/v1/metadata", "/v1/models"):
        try:
            r = requests.get(a.url.rstrip("/") + p, timeout=30)
            out["requests"].append({"get": p, "status": r.status_code, "body": r.text[:300]})
        except Exception as e:
            out["requests"].append({"get": p, "error": f"{type(e).__name__}: {e}"[:200]})
    for n in (1, 2):                                   # twice: the first request of a server is often not like the second
        t = time.perf_counter()
        try:
            r = requests.post(a.url.rstrip("/") + path, json=body, timeout=a.timeout)
            rec = {"post": path, "n": n, "status": r.status_code, "seconds": round(time.perf_counter() - t, 3)}
            if r.status_code == 200:
                d = r.json(); items = []
                for x in d.get("data") or []:
                    for det in (x.get("text_detections") or []) if isinstance(x, dict) else []:
                        items.append(((det.get("text_prediction") or {}).get("text") or ""))
                text = "".join(items)
                rec.update({"answer_keys": sorted(d.keys()), "model": d.get("model"), "data_items": len(d.get("data") or []), "text_items": len(items),
                            "characters_returned": len(text), "first_50_characters": text[:50]})
                if expected is not None:
                    rec["against_the_expected_text"] = overlap(expected, text)
            else:
                rec["body"] = r.text[:600]
        except Exception as e:
            rec = {"post": path, "n": n, "error": f"{type(e).__name__}: {e}"[:300], "seconds": round(time.perf_counter() - t, 3)}
        out["requests"].append(rec)
    out["program_sha256"] = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps([{k: r.get(k) for k in ("post", "get", "status", "seconds", "text_items", "characters_returned", "error") if r.get(k) is not None} for r in out["requests"]]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
