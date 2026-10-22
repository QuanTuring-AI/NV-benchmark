#!/usr/bin/env python3
"""Vol.5 · C4 configuration 5: does the Blueprint's own answer-model request fit? Sends captured request bodies of the
RAG server (byte for byte the JSON it sent, max_tokens 16256 included) to the answer model alone, reads the answer
model's max_model_len (GET /v1/models) and its cache configuration line (GET /metrics), and records per request the
HTTP status, the error text if any, the finish reason and the token usage. No answer text is kept.
usage: blueprint_request_probe.py --llm URL --request FILE [--request FILE ...] --out FILE
"""
import argparse, json, sys, time, urllib.request


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")


def send(url, body):
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    t0 = time.time(); out = {"status": None, "error": None, "finish_reason": None, "usage": None}
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            out["status"] = r.status
            for raw in r:
                l = raw.decode("utf-8").strip()
                if not l.startswith("data:") or l == "data: [DONE]":
                    continue
                d = json.loads(l[5:])
                for c in d.get("choices") or []:
                    out["finish_reason"] = c.get("finish_reason") or out["finish_reason"]
                out["usage"] = d.get("usage") or out["usage"]
    except urllib.error.HTTPError as e:
        out["status"], out["error"] = e.code, e.read().decode("utf-8")[:2000]
    out["seconds"] = round(time.time() - t0, 2)
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--llm", required=True); ap.add_argument("--request", action="append", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    models = json.loads(get(a.llm + "/v1/models"))
    info = [l for l in get(a.llm + "/metrics").splitlines() if l.startswith("vllm:cache_config_info")]
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "max_model_len": [m.get("max_model_len") for m in models.get("data", [])],
           "cache_config_info": info[0] if info else None, "requests": []}
    for f in a.request:
        cap = json.load(open(f, encoding="utf-8")); body = cap["body"]
        r = send(a.llm, body)
        rec["requests"].append({"file": f.replace("\\", "/").split("/")[-1], "max_tokens_sent": body.get("max_tokens"), **r})
    rec["all_200"] = all(r["status"] == 200 for r in rec["requests"])
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"max_model_len": rec["max_model_len"], "statuses": [r["status"] for r in rec["requests"]], "all_200": rec["all_200"]}))
    sys.exit(0 if rec["all_200"] else 7)


if __name__ == "__main__":
    main()
