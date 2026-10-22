#!/usr/bin/env python3
"""Vol.5 preparation: one image sent twice to a running extraction NIM, and the shape of what came back. A smoke test,
not a measurement.

Two request forms:
  infer   POST /v1/infer with one image as a data URL — the form the RAG Blueprint's ingestion sends to the OCR,
          page-elements, graphic-elements and table-structure services.
  parse   POST /v1/chat/completions with one image and one tool name — the documented form of the Nemotron Parse NIM
          (https://docs.nvidia.com/nim/vision-language-models/1.5.0/examples/nemotron-parse/api.html).

Recorded: the HTTP status, the seconds, the keys of the answer, and counts (how many items, how many per class or per
element type, how many characters of text in total). Text that the service recognised is not recorded. For an error,
the first 600 characters of the server's answer are kept: that text is the result.

usage: extraction_smoke.py --form infer|parse --url http://127.0.0.1:8000 --image FILE --out FILE.json
                           [--model nvidia/nemotron-parse] [--tool markdown_bbox] [--timeout 300]
"""
import argparse, base64, collections, hashlib, json, os, sys, time

import requests


def shape(o, depth=0):
    """Counts and key names of an answer; no string value is kept."""
    if isinstance(o, dict):
        return {k: shape(v, depth + 1) for k, v in sorted(o.items())} if depth < 6 else "dict"
    if isinstance(o, list):
        kinds = collections.Counter(type(x).__name__ for x in o)
        out = {"list_of": dict(kinds), "length": len(o)}
        if o and isinstance(o[0], (dict, list)) and depth < 6:
            out["first"] = shape(o[0], depth + 1)
        return out
    if isinstance(o, str):
        return {"string_characters": len(o)}
    return type(o).__name__


def parse_elements(d):
    """Element counts of a Nemotron Parse answer: the tool call's arguments are a JSON list of elements."""
    out = {"choices": len(d.get("choices") or [])}
    try:
        msg = d["choices"][0]["message"]; calls = msg.get("tool_calls") or []
        out["tool_calls"] = len(calls); out["content_characters"] = len(msg.get("content") or "")
        out["finish_reason"] = d["choices"][0].get("finish_reason")
        elements, chars, types = 0, 0, collections.Counter()
        for c in calls:
            args = json.loads(c["function"]["arguments"])
            pages = args if (args and isinstance(args[0], list)) else [args]
            for page in pages:
                for e in page:
                    if isinstance(e, dict):
                        elements += 1; chars += len(e.get("text") or ""); types[str(e.get("type"))] += 1
        out.update({"elements": elements, "text_characters_total": chars, "element_types": dict(types), "usage": d.get("usage")})
    except Exception as e:   # the shape was not the documented one: keep what can be said without the text
        out["could_not_read_as_documented"] = f"{type(e).__name__}: {e}"[:200]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--form", choices=["infer", "parse"], required=True); ap.add_argument("--url", required=True); ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--model", default="nvidia/nemotron-parse"); ap.add_argument("--tool", default="markdown_bbox")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    raw = open(a.image, "rb").read()
    kind = "png" if a.image.lower().endswith(".png") else "jpeg"
    data_url = f"data:image/{kind};base64," + base64.b64encode(raw).decode()
    if a.form == "infer":
        path, body = "/v1/infer", {"input": [{"type": "image_url", "url": data_url}]}
    else:
        path = "/v1/chat/completions"
        body = {"model": a.model, "tools": [{"type": "function", "function": {"name": a.tool}}], "temperature": 0.0,
                "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": data_url}}]}]}
    out = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "form": a.form, "url": a.url, "path": path,
           "image": {"name": os.path.basename(a.image), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
           "request": {"model": a.model, "tool": a.tool} if a.form == "parse" else {"input": "one image as a data URL"}, "requests": []}
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
                d = r.json()
                rec["answer_shape"] = parse_elements(d) if a.form == "parse" else shape(d)
            else:
                rec["body"] = r.text[:600]
        except Exception as e:
            rec = {"post": path, "n": n, "error": f"{type(e).__name__}: {e}"[:300], "seconds": round(time.perf_counter() - t, 3)}
        out["requests"].append(rec)
    out["program_sha256"] = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps([{k: r.get(k) for k in ("post", "get", "status", "seconds", "error") if r.get(k) is not None} for r in out["requests"]]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
