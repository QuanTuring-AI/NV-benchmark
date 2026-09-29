#!/usr/bin/env python3
"""Vol.2 speed table: Nemotron Nano 9B v2 (A1) and Nemotron 3 Nano (A2), each in its own NIM image, alternated on one GPU.

The two images cannot share the card (17.8 + 19.3 GB of weights on a 32.6 GB card), so "interleaved in one session"
means alternating containers: four blocks A1, A2, A1, A2 on the same 50 questions in a fixed order (the Vol.1-B
co-residence sample), the first two blocks on positions 0-24 and the last two on 25-49. Each arm therefore sees every
question once, and any drift across the session falls on both arms.
Per block: start the container as the footprint run's default configuration, discard one request, then one request
per question with 2 s between requests. Payload as Vol.1 run_benchmark.py plus temperature 0.0, top_p 0.9,
stream with usage. No system prompt: both models reason by default and that is what a Vol.1-style request receives.
Rows record client timings, Vol.1 word count, engine token usage, finish_reason, and GPU state; no response text.
usage: p50_speed.py --out DIR [--test]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, hashlib, json, os, subprocess, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
QFILE = os.path.join(REPO, "benchmark", "questions.json")
SAMPLE = os.path.join(REPO, "vol1b", "results", "p20_coresidence", "sample.json")
MAX_TOKENS, COOLDOWN, TEMPERATURE, TOP_P, TIMEOUT = 500, 2, 0.0, 0.9, 300
BLOCKS = [("A1", 0), ("A2", 0), ("A1", 1), ("A2", 1)]   # (arm, half)


def request(model, text, max_tokens=MAX_TOKENS):
    payload = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens,
               "temperature": TEMPERATURE, "top_p": TOP_P, "stream": True, "stream_options": {"include_usage": True}}
    t0 = time.perf_counter(); first = None; full = ""; words = 0; usage = None; finish = None; status = None
    try:
        r = requests.post(BASE + "/v1/chat/completions", json=payload, stream=True, timeout=TIMEOUT)
        status = r.status_code
        for line in r.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.startswith("data: ") and line != "data: [DONE]":
                if first is None:
                    first = time.perf_counter()
                try:
                    c = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if c.get("usage"):
                    usage = c["usage"]
                for ch in c.get("choices") or []:
                    d = (ch.get("delta") or {}).get("content") or ""
                    if d:
                        full += d; words += len(d.split())
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
        t1 = time.perf_counter()
    except Exception as e:
        return {"error": str(e), "http_status": status}
    total = t1 - t0
    return {"ttft_ms": round((first - t0) * 1000, 1) if first else None, "total_latency_ms": round(total * 1000, 1),
            "tokens": words, "tps": round(words / total, 1) if total else 0,
            "completion_tokens": (usage or {}).get("completion_tokens"), "prompt_tokens": (usage or {}).get("prompt_tokens"),
            "usage_present": usage is not None, "finish_reason": finish, "http_status": status,
            "response_sha256": hashlib.sha256(full.encode("utf-8")).hexdigest(), "response_chars": len(full)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    req_f = open(os.path.join(a.out, "requests.jsonl"), "a", encoding="utf-8", newline="\n")
    ev_f = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")

    def event(**kw):
        kw["at"] = now(); ev_f.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev_f.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "block", "ready", "at")}, flush=True)

    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    s = json.load(open(SAMPLE, encoding="utf-8"))
    bank = {q["id"]: q for q in json.load(open(QFILE, encoding="utf-8"))}
    ids = [x["id"] for x in (s["harness_test_questions"] if a.test else s["run_order"])]
    order = [(i, bank[x]) for i, x in enumerate(ids)]
    half = (len(order) + 1) // 2
    for b, (arm, h) in enumerate(BLOCKS):
        part = order[:half] if h == 0 else order[half:]
        name = f"p50-speed-{arm.lower()}-b{b}"
        before = gpu()
        st = start(arm, name, None, logdir)
        model = None
        if st["ready"]:
            time.sleep(5)
            try:
                model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
            except Exception as e:
                event(kind="models_error", arm=arm, block=b, error=str(e))
            cc = metrics_cache_config()
            if cc.get("kv_tokens") is None and st.get("kv_tokens_from_log"):
                cc["kv_tokens"] = st["kv_tokens_from_log"]; cc["kv_tokens_source"] = "log"
            w = request(model or "", "Hello", 16)
            event(kind="block_start", arm=arm, block=b, half=h, image=ARMS[arm]["image"], profile=ARMS[arm]["profile"],
                  env=st["env"], gpu_before_launch=before, gpu_ready=gpu(), seconds_to_ready=st["seconds_to_ready"],
                  log_lines=st["log_lines"], cache_config=cc, served_model=model, first_request_discarded=w)
            time.sleep(COOLDOWN)
            for pos, q in part:
                gb = gpu(); at = now()
                r = request(model, q["text"])
                r.update({"arm": arm, "block": b, "pos": pos, "question_id": q["id"], "category": q["category"], "at": at,
                          "served_model": model, "gpu_before": gb, "gpu_after": gpu(),
                          "docker_ps_before": sh(["docker", "ps", "--format", "{{.Names}}"], timeout=30).stdout.split()})
                req_f.write(json.dumps(r, ensure_ascii=False) + "\n"); req_f.flush()
                print(f"  {arm} b{b} {q['id']} ttft {r.get('ttft_ms')} tps {r.get('tps')} ct {r.get('completion_tokens')} "
                      f"{r.get('finish_reason')} {r.get('error', '')}", flush=True)
                time.sleep(COOLDOWN)
        else:
            event(kind="block_failed", arm=arm, block=b, reason=st.get("reason"), log_lines=st.get("log_lines"))
        stop(name)
        event(kind="block_end", arm=arm, block=b, gpu_after_stop=gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
