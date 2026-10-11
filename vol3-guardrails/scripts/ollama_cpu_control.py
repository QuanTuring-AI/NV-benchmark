#!/usr/bin/env python3
"""Ollama CPU control · the final Ollama measurement in this repository.

The same Ollama, model, questions and run order as P20 v2, sent through 127.0.0.1 only, with the model placed in two
ways within one run:
  G    default placement (the whole model in GPU memory); the first three questions of the run order
  CPU  options.num_gpu = 0 (no layer on the GPU); all 50 questions
Placement is read from Ollama /api/ps before and after every request (size and size_vram). If the CPU warm-up does not
leave size_vram at 0, or the G warm-up does not leave size_vram equal to size, the run stops before any measured
request of that arm and exits 3. NIM is not started; the run refuses to start if any container is running.
Payload: Vol.1 run_benchmark.py payload plus temperature 0.0 and top_p 0.9, max 500 tokens, keep_alive 60m; 2 s between
requests; timeout 900 s. No response text is stored (SHA-256 and length only).
usage: ollama_cpu_control.py --out DIR [--test]
"""
import argparse, hashlib, json, os, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p20v2_coresidence import QFILE, SAMPLE, OLL_LOOPBACK, OLLAMA_MODEL, docker_ps, gpu, now, ollama_ps, ollama_unload

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
MAX_TOKENS, COOLDOWN, TEMPERATURE, TOP_P, TIMEOUT, KEEP = 500, 2, 0.0, 0.9, 900, "60m"
N_G = 3
ARMS = {"G": {}, "CPU": {"num_gpu": 0}}


def request(text, extra, max_tokens=MAX_TOKENS):
    payload = {"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": text}], "stream": True, "keep_alive": KEEP,
               "options": {"num_predict": max_tokens, "temperature": TEMPERATURE, "top_p": TOP_P, **extra}}
    start = time.perf_counter(); first = None; full = ""; words = 0; final = {}; status = None
    try:
        resp = requests.post(OLL_LOOPBACK + "/api/chat", json=payload, stream=True, timeout=TIMEOUT)
        status = resp.status_code
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = (chunk.get("message") or {}).get("content", "")
            if content:
                if first is None:
                    first = time.perf_counter()
                full += content; words += len(content.split())
            if chunk.get("done"):
                final = chunk
                break
        end = time.perf_counter()
    except Exception as e:
        return {"error": str(e), "http_status": status}
    total = end - start
    ns = lambda k: round(final[k] / 1e6, 1) if isinstance(final.get(k), (int, float)) else None
    return {"ttft_ms": round((first - start) * 1000, 1) if first else None, "total_latency_ms": round(total * 1000, 1),
            "tokens": words, "tps": round(words / total, 1) if total else 0,
            "completion_tokens": final.get("eval_count"), "prompt_tokens": final.get("prompt_eval_count"),
            "finish_reason": final.get("done_reason"), "http_status": status,
            "load_duration_ms": ns("load_duration"), "prompt_eval_duration_ms": ns("prompt_eval_duration"),
            "eval_duration_ms": ns("eval_duration"),
            "response_sha256": hashlib.sha256(full.encode("utf-8")).hexdigest(), "response_chars": len(full)}


def placement(ps):
    m = [x for x in ps if (x.get("name") or "").startswith(OLLAMA_MODEL)]
    if len(m) != 1 or not isinstance(m[0].get("size"), int) or not isinstance(m[0].get("size_vram"), int):
        return None
    return round(m[0]["size_vram"] / m[0]["size"], 4)


def expected(arm, share):
    return share == (0.0 if arm == "CPU" else 1.0)


class Log:
    def __init__(self, out):
        os.makedirs(out, exist_ok=True)
        self.req = open(os.path.join(out, "requests.jsonl"), "a", encoding="utf-8", newline="\n")
        self.ev = open(os.path.join(out, "events.jsonl"), "a", encoding="utf-8", newline="\n")

    def event(self, **kw):
        kw["at"] = now(); self.ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); self.ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "ok", "share", "at")}, flush=True)

    def row(self, r):
        self.req.write(json.dumps(r, ensure_ascii=False) + "\n"); self.req.flush()
        print(f"  {r['arm']:3s} {r['question_id']:5s} share {r['vram_share_after']} ttft {r.get('ttft_ms')} "
              f"tok {r.get('completion_tokens')} eval_ms {r.get('eval_duration_ms')} {r.get('error', '')}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if docker_ps():
        sys.exit(f"refused: containers running {docker_ps()}")
    s = json.load(open(SAMPLE, encoding="utf-8"))
    bank = {q["id"]: q for q in json.load(open(QFILE, encoding="utf-8"))}
    ids = [x["id"] for x in (s["harness_test_questions"] if a.test else s["run_order"])]
    plan = {"G": ids[:N_G] if not a.test else ids[:1], "CPU": ids}
    log = Log(a.out)
    for arm in ("G", "CPU"):
        ok = ollama_unload()
        log.event(kind="unload", arm=arm, ok=ok, ollama_ps=ollama_ps(), gpu=gpu())
        w = request("Hello", ARMS[arm], 16)
        ps = ollama_ps(); share = placement(ps)
        log.event(kind="warmup_discarded", arm=arm, ok="error" not in w, share=share, ollama_ps=ps, gpu=gpu(), result=w)
        if not expected(arm, share):
            log.event(kind="placement_refused", arm=arm, share=share)
            print(f"PLACEMENT-NOT-AS-REQUIRED arm={arm} share={share}", flush=True)
            return 3
        time.sleep(COOLDOWN)
        for pos, qid in enumerate(plan[arm]):
            q = bank[qid]
            before = {"at": now(), "gpu": gpu(), "ps": ollama_ps(), "docker": docker_ps()}
            r = request(q["text"], ARMS[arm])
            after = ollama_ps()
            r.update({"arm": arm, "pos": pos, "question_id": qid, "category": q["category"], "at": before["at"],
                      "options_extra": ARMS[arm], "gpu_before": before["gpu"], "gpu_after": gpu(),
                      "docker_ps_before": before["docker"], "ollama_ps_before": before["ps"],
                      "ollama_ps_after": after, "vram_share_before": placement(before["ps"]),
                      "vram_share_after": placement(after)})
            log.row(r)
            if not (expected(arm, r["vram_share_before"]) and expected(arm, r["vram_share_after"])):
                log.event(kind="placement_changed", arm=arm, pos=pos, share=r["vram_share_after"])
                print("PLACEMENT-CHANGED", flush=True)
                return 3
            time.sleep(COOLDOWN)
    ok = ollama_unload()
    log.event(kind="end", ok=ok, ollama_ps=ollama_ps(), gpu=gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
