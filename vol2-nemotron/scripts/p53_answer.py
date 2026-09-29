#!/usr/bin/env python3
"""Vol.2 answer-completion run: the speed table's two arms and 50 questions at max_tokens 4096.

The speed run (p50_speed, max_tokens 500) measures generation rate; 79 of its 100 completions hit the cap, so it
cannot say how long a question takes to answer or how many tokens the model spends before the answer. This run keeps
everything else identical (same arms, containers, sample, order of blocks, payload) and raises max_tokens to 4096.
The stream is parsed for a reasoning channel: OpenAI-style deltas may carry `reasoning_content` beside `content`,
and the text may carry <think>...</think> markers. Both are counted separately when present, and the row records
which one, if any, the image exposed. No response text is stored.
usage: p53_answer.py --out DIR [--test]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, hashlib, json, os, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
from p50_speed import BLOCKS, COOLDOWN, QFILE, SAMPLE, TEMPERATURE, TOP_P  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
MAX_TOKENS, TIMEOUT = 4096, 900
THINK_OPEN, THINK_CLOSE = "<think>", "</think>"
# Deviation from p50_speed, forced by the request shape: at NIM_MAX_MODEL_LEN 4096 a 4096-token completion budget
# cannot fit beside any prompt (the speed run's containers rejected every request with HTTP 400 in the harness test),
# so both containers run at NIM_MAX_MODEL_LEN 8192. Everything else (image, profile, A1 NIM_MAX_NUM_SEQS 32, A2 default)
# is the speed run's configuration.
ANSWER_ENV = {"A1": {"NIM_MAX_MODEL_LEN": "8192", "NIM_MAX_NUM_SEQS": "32"}, "A2": {"NIM_MAX_MODEL_LEN": "8192"}}
for _arm, _env in ANSWER_ENV.items():
    ARMS[_arm] = dict(ARMS[_arm], env=_env)


def request(model, text, max_tokens=MAX_TOKENS):
    payload = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens,
               "temperature": TEMPERATURE, "top_p": TOP_P, "stream": True, "stream_options": {"include_usage": True}}
    t0 = time.perf_counter(); first = None; first_content_after_reasoning = None
    content = ""; reasoning = ""; words = 0; usage = None; finish = None; status = None; reasoning_field = False
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
                    d = ch.get("delta") or {}
                    rc = d.get("reasoning_content") or d.get("reasoning")
                    if rc:
                        reasoning += rc; reasoning_field = True
                    dc = d.get("content") or ""
                    if dc:
                        if reasoning and first_content_after_reasoning is None:
                            first_content_after_reasoning = time.perf_counter()
                        content += dc; words += len(dc.split())
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
        t1 = time.perf_counter()
    except Exception as e:
        return {"error": str(e), "http_status": status}
    # <think> markers inside content (when the image streams reasoning as plain text)
    think_marked = THINK_OPEN in content
    think_chars = 0; answer_text = content
    if think_marked:
        a, b = content.find(THINK_OPEN), content.find(THINK_CLOSE)
        if b > a >= 0:
            think_chars = b - a - len(THINK_OPEN); answer_text = content[b + len(THINK_CLOSE):]
        else:
            think_chars = len(content) - a - len(THINK_OPEN); answer_text = ""
    total = t1 - t0
    return {"ttft_ms": round((first - t0) * 1000, 1) if first else None, "total_latency_ms": round(total * 1000, 1),
            "time_to_first_answer_ms": round((first_content_after_reasoning - t0) * 1000, 1) if first_content_after_reasoning else None,
            "tokens": words, "tps": round(words / total, 1) if total else 0,
            "completion_tokens": (usage or {}).get("completion_tokens"), "prompt_tokens": (usage or {}).get("prompt_tokens"),
            "usage_present": usage is not None, "finish_reason": finish, "http_status": status,
            "reasoning_channel": "reasoning_content field" if reasoning_field else ("<think> markers" if think_marked else "none"),
            "reasoning_chars": len(reasoning) if reasoning_field else think_chars,
            "answer_chars": len(answer_text) if (reasoning_field or think_marked) else len(content),
            "answer_empty": (len(answer_text.strip()) == 0) if (reasoning_field or think_marked) else (len(content.strip()) == 0),
            "response_sha256": hashlib.sha256((reasoning + content).encode("utf-8")).hexdigest(),
            "response_chars": len(reasoning) + len(content)}


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
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "block", "at")}, flush=True)

    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    s = json.load(open(SAMPLE, encoding="utf-8"))
    bank = {q["id"]: q for q in json.load(open(QFILE, encoding="utf-8"))}
    ids = [x["id"] for x in (s["harness_test_questions"] if a.test else s["run_order"])]
    order = [(i, bank[x]) for i, x in enumerate(ids)]
    half = (len(order) + 1) // 2
    for b, (arm, h) in enumerate(BLOCKS):
        part = order[:half] if h == 0 else order[half:]
        name = f"p53-answer-{arm.lower()}-b{b}"
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
                  env=st["env"], max_tokens=MAX_TOKENS, gpu_before_launch=before, gpu_ready=gpu(), seconds_to_ready=st["seconds_to_ready"],
                  log_lines=st["log_lines"], cache_config=cc, served_model=model, first_request_discarded=w)
            time.sleep(COOLDOWN)
            for pos, q in part:
                gb = gpu(); at = now()
                r = request(model, q["text"])
                r.update({"arm": arm, "block": b, "pos": pos, "question_id": q["id"], "category": q["category"], "at": at,
                          "served_model": model, "max_tokens": MAX_TOKENS, "gpu_before": gb, "gpu_after": gpu(),
                          "docker_ps_before": sh(["docker", "ps", "--format", "{{.Names}}"], timeout=30).stdout.split()})
                req_f.write(json.dumps(r, ensure_ascii=False) + "\n"); req_f.flush()
                print(f"  {arm} b{b} {q['id']} ttft {r.get('ttft_ms')} total {r.get('total_latency_ms')} ct {r.get('completion_tokens')} "
                      f"{r.get('finish_reason')} reasoning={r.get('reasoning_channel')} rc={r.get('reasoning_chars')} ac={r.get('answer_chars')} {r.get('error', '')}", flush=True)
                time.sleep(COOLDOWN)
        else:
            event(kind="block_failed", arm=arm, block=b, reason=st.get("reason"), log_lines=st.get("log_lines"))
        stop(name)
        event(kind="block_end", arm=arm, block=b, gpu_after_stop=gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
