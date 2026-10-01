#!/usr/bin/env python3
"""Vol.2 long-context behaviour: TTFT, generation rate and memory at READY at prompt depths of about 1k, 4k, 16k
and 64k tokens, each arm, each depth in its own container sized for that depth.

Per (arm, depth): NIM_MAX_MODEL_LEN is set to the smallest of 4096, 8192, 32768, 131072 that holds depth + 512; both
arms run at max_num_seqs 32 (A1 NIM_MAX_NUM_SEQS, A2 NIM_PASSTHROUGH_ARGS). After READY the memory level and KV tokens
are recorded (this depth's own footprint), one request is discarded, then five requests are sent: prompts built by
concatenating questions from benchmark/questions.json (public, Vol.1's set) until a character budget of 3.6 x depth
is reached, each of the five starting at a different offset so the texts differ; the request asks for a one-line
summary, max_tokens 256, temperature 0. The engine's prompt_tokens is the depth actually measured. A start that fails
is recorded as that arm's context ceiling. No response text is stored.
usage: p53_longctx.py --out DIR [--depths 1024,4096,16384,65536] [--test]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, hashlib, json, os, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
QFILE = os.path.join(REPO, "benchmark", "questions.json")
MAX_TOKENS, N_REQ, CHARS_PER_TOKEN, COOLDOWN = 256, 5, 3.6, 2
INSTRUCTION = "\n\nThe text above is a list of questions. In one line, say how many questions it contains and what topic most of them share."


def model_len_for(depth):
    for m in (4096, 8192, 32768, 131072):
        if depth + 512 <= m:
            return m
    return 131072


def build_prompt(bank, depth, offset):
    budget = int(depth * CHARS_PER_TOKEN); parts = []; n = 0; i = offset
    while n < budget:
        t = bank[i % len(bank)]["text"]; parts.append(t); n += len(t) + 1; i += 1
    return "\n".join(parts) + INSTRUCTION


def request(model, text):
    payload = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": MAX_TOKENS, "temperature": 0.0,
               "top_p": 0.9, "stream": True, "stream_options": {"include_usage": True}}
    t0 = time.perf_counter(); first = None; full = ""; usage = None; finish = None; status = None
    try:
        r = requests.post(BASE + "/v1/chat/completions", json=payload, stream=True, timeout=900)
        status = r.status_code
        for line in r.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    c = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if c.get("usage"):
                    usage = c["usage"]
                for ch in c.get("choices") or []:
                    d = (ch.get("delta") or {}).get("content") or (ch.get("delta") or {}).get("reasoning_content") or ""
                    if d and first is None:
                        first = time.perf_counter()
                    full += d
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
        t1 = time.perf_counter()
    except Exception as e:
        return {"error": str(e), "http_status": status}
    ct = (usage or {}).get("completion_tokens")
    return {"ttft_ms": round((first - t0) * 1000, 1) if first else None, "total_latency_ms": round((t1 - t0) * 1000, 1),
            "prompt_tokens": (usage or {}).get("prompt_tokens"), "completion_tokens": ct, "usage_present": usage is not None,
            "generation_tps": round(ct / (t1 - first), 2) if first and ct and t1 > first else None,
            "finish_reason": finish, "http_status": status, "response_chars": len(full),
            "response_sha256": hashlib.sha256(full.encode("utf-8")).hexdigest()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--depths", default="1024,4096,16384,65536")
    ap.add_argument("--arms", default="A1,A2"); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    depths = [int(x) for x in a.depths.split(",")]
    nreq = 2 if a.test else N_REQ
    req_f = open(os.path.join(a.out, "requests.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    bank = json.load(open(QFILE, encoding="utf-8"))

    def event(**kw):
        kw["at"] = now(); ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "depth", "ready", "at")}, flush=True)

    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    for arm in a.arms.split(","):
        for depth in depths:
            ml = model_len_for(depth)
            env = {"NIM_MAX_MODEL_LEN": str(ml)}
            env.update({"NIM_MAX_NUM_SEQS": "32"} if arm == "A1" else {"NIM_PASSTHROUGH_ARGS": "--max-num-seqs 32"})
            ARMS[arm] = dict(ARMS[arm], env=env)
            name = f"p53-ctx-{arm.lower()}-{depth}"
            before = gpu()
            st_ = start(arm, name, None, logdir)
            if not st_["ready"]:
                event(kind="depth_failed", arm=arm, depth=depth, max_model_len=ml, env=env, reason=st_.get("reason"), log_lines=st_.get("log_lines"), gpu_before=before)
                stop(name); continue
            time.sleep(5)
            model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
            cc = metrics_cache_config()
            if cc.get("kv_tokens") is None and st_.get("kv_tokens_from_log"):
                cc["kv_tokens"] = st_["kv_tokens_from_log"]; cc["kv_tokens_source"] = "log"
            w = request(model, build_prompt(bank, min(depth, 1024), 97))
            event(kind="depth_start", arm=arm, depth=depth, max_model_len=ml, env=env, image=ARMS[arm]["image"], profile=ARMS[arm]["profile"],
                  gpu_before_launch=before, gpu_ready=gpu(), seconds_to_ready=st_["seconds_to_ready"], cache_config=cc,
                  log_lines=st_["log_lines"], served_model=model, first_request_discarded=w)
            time.sleep(COOLDOWN)
            for i in range(nreq):
                gb = gpu(); at = now()
                r = request(model, build_prompt(bank, depth, i * 13))
                r.update({"arm": arm, "depth_target": depth, "max_model_len": ml, "i": i, "at": at, "served_model": model,
                          "gpu_before": gb, "gpu_after": gpu(), "docker_ps_before": sh(["docker", "ps", "--format", "{{.Names}}"], timeout=30).stdout.split()})
                req_f.write(json.dumps(r, ensure_ascii=False) + "\n"); req_f.flush()
                print(f"  {arm} d={depth} i={i} pt={r.get('prompt_tokens')} ttft={r.get('ttft_ms')} gen={r.get('generation_tps')} {r.get('finish_reason')} {r.get('error', '')}", flush=True)
                time.sleep(COOLDOWN)
            stop(name)
            event(kind="depth_end", arm=arm, depth=depth, gpu_after_stop=gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
