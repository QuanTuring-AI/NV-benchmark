"""P17 §1 instrument check: send the same prompts AIPerf is given, one at a time, with `requests`, and compute
TTFT and ITL with AIPerf's definitions (ITL = (e2e - TTFT) / (output_tokens - 1), first token excluded).
usage: p17_calibrate_client.py --input prompts.jsonl --model ID --osl N --out result.json [--url http://localhost:8000]
Input: one {"text": "..."} per line (the same file passed to AIPerf as a single_turn dataset)."""
import argparse, json, statistics, time
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)
ap.add_argument("--model", required=True)
ap.add_argument("--osl", type=int, required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--url", default="http://localhost:8000")
ap.add_argument("--session", action="store_true", help="reuse one connection (requests.Session) instead of a new connection per request")
a = ap.parse_args()
http = requests.Session() if a.session else requests

prompts = [json.loads(l)["text"] for l in open(a.input, encoding="utf-8") if l.strip()]
rows = []
for i, text in enumerate(prompts):
    payload = {"model": a.model, "messages": [{"role": "user", "content": text}], "max_tokens": a.osl,
               "min_tokens": a.osl, "ignore_eos": True, "temperature": 0.0, "stream": True,
               "stream_options": {"include_usage": True}}
    t0 = time.perf_counter(); first = last = None; usage = None; finish = None; err = None
    try:
        with http.post(f"{a.url}/v1/chat/completions", json=payload, stream=True, timeout=300) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith(b"data: "):
                    continue
                data = line[6:]
                if data == b"[DONE]":
                    break
                ch = json.loads(data)
                if ch.get("usage"):
                    usage = ch["usage"]
                for c in ch.get("choices") or []:
                    if (c.get("delta") or {}).get("content"):
                        now = time.perf_counter(); first = first or now; last = now
                    finish = c.get("finish_reason") or finish
    except Exception as e:  # recorded, not retried
        err = repr(e)
    e2e = (time.perf_counter() - t0) * 1000
    out_tok = (usage or {}).get("completion_tokens")
    ttft = (first - t0) * 1000 if first else None
    itl = (e2e - ttft) / (out_tok - 1) if ttft is not None and out_tok and out_tok > 1 else None
    rows.append({"i": i, "ttft_ms": ttft, "itl_ms": itl, "e2e_ms": e2e, "output_tokens": out_tok,
                 "input_tokens": (usage or {}).get("prompt_tokens"), "finish_reason": finish, "error": err})
    print(json.dumps(rows[-1]), flush=True)

ok = [r for r in rows if r["error"] is None and r["ttft_ms"] is not None]
summ = lambda k: {"avg": round(statistics.mean(r[k] for r in ok), 2), "p50": round(statistics.median(r[k] for r in ok), 2), "n": len(ok)} if ok else None
json.dump({"tool": "requests " + requests.__version__, "url": a.url, "connection": "session (reused)" if a.session else "new per request","definitions": "TTFT = first content chunk; ITL = (e2e - TTFT)/(output_tokens - 1)",
           "rows": rows, "ttft_ms": summ("ttft_ms"), "itl_ms": summ("itl_ms"), "e2e_ms": summ("e2e_ms"),
           "errors": sum(1 for r in rows if r["error"])}, open(a.out, "w", encoding="utf-8"), indent=1)
