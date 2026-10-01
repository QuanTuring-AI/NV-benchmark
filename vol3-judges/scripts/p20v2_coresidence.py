#!/usr/bin/env python3
"""P20 v2 · co-residence of NIM and Ollama on one GPU, with the Ollama-alone arm measured through both addresses.

Arms (P37 section 2)
  S-N    NIM alone          NIM up, Ollama model unloaded AND GPU memory back at the NIM-alone level; NIM via localhost
  S-OL   Ollama alone       NIM container stopped; Ollama via 127.0.0.1 (the engine without the client delay)
  S-OH   Ollama alone       NIM container stopped; Ollama via localhost (the client path Vol.1's harness used, verbatim)
  C      co-resident        NIM up and Ollama loaded; one NIM request (localhost), 2 s, one Ollama request (127.0.0.1), 2 s

Change from v1 (P20 v1 BASELINE section 10 post-hoc): in v1 half of the S-N requests came right after the Ollama model had
been unloaded, while part of NIM's memory was still outside the GPU, so S-N was not clean. Here, after every unload,
unmeasured NIM warm-up requests are sent until GPU memory in use is back within RECOVERY_TOLERANCE_MIB of the NIM-alone
level taken at the start of the NIM phase (before any Ollama load), or until RECOVERY_MAX tries; each S-N row records the
level it was sent at, and the analysis refuses the run if any S-N request was sent below it.

Phases (run_p20v2.sh)
  --phase so --half A|B   S-OL and S-OH on half of the run order, both arms on each question, order alternating by position
  --phase nim             S-N and C interleaved question by question (even positions S-N then C, odd C then S-N)

Timing and the throughput formula are Vol.1's; explicit temperature 0.0 / top_p 0.9; NIM include_usage; Ollama final-chunk
counts; timeout 300 s. No response text is stored.
usage: p20v2_coresidence.py --phase so --half A|B --out DIR [--test] | --phase nim --out DIR [--test]
"""
import argparse, hashlib, json, os, subprocess, sys, time

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
QFILE = os.path.join(REPO, "benchmark", "questions.json")
SAMPLE = os.path.join(REPO, "vol1b", "results", "p20_coresidence", "sample.json")
NIM_LOCALHOST = "http://localhost:8000"
OLL_LOOPBACK = "http://127.0.0.1:11434"
OLL_LOCALHOST = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1:8b"
MAX_TOKENS, COOLDOWN, TEMPERATURE, TOP_P, TIMEOUT = 500, 2, 0.0, 0.9, 300
RECOVERY_TOLERANCE_MIB, RECOVERY_MAX = 1000, 10


def now():
    return subprocess.run(["date", "+%FT%T%z"], capture_output=True, text=True).stdout.strip()


def gpu():
    r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw",
                        "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
    u, f, ut, t, p = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
    return {"used_mib": int(u), "free_mib": int(f), "util_pct": int(ut), "temp_c": int(t), "power_w": float(p)}


def docker_ps():
    r = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=30)
    return [x for x in r.stdout.split() if x]


def ollama_ps():
    try:
        ms = requests.get(OLL_LOOPBACK + "/api/ps", timeout=15).json().get("models", [])
        return [{"name": m.get("name"), "size": m.get("size"), "size_vram": m.get("size_vram")} for m in ms]
    except Exception as e:
        return [{"error": str(e)}]


def connect_probe(port, path, n=3):
    out = {}
    for host in ("localhost", "127.0.0.1"):
        ms = []
        for _ in range(n):
            t = time.perf_counter()
            try:
                requests.get(f"http://{host}:{port}{path}", timeout=15)
                ms.append(round((time.perf_counter() - t) * 1000, 1))
            except Exception as e:
                ms.append(f"error {type(e).__name__}")
        out[host] = ms
    return out


def ollama_unload():
    requests.post(OLL_LOOPBACK + "/api/generate", json={"model": OLLAMA_MODEL, "keep_alive": 0}, timeout=120)
    for _ in range(60):
        if not [m for m in ollama_ps() if m.get("name")]:
            return True
        time.sleep(0.5)
    return False


def ollama_load():
    requests.post(OLL_LOOPBACK + "/api/generate", json={"model": OLLAMA_MODEL, "keep_alive": "60m"}, timeout=300)
    return any((m.get("name") or "").startswith(OLLAMA_MODEL) for m in ollama_ps())


def nim_request(base, model, text, max_tokens=MAX_TOKENS):
    payload = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens,
               "temperature": TEMPERATURE, "top_p": TOP_P, "stream": True, "stream_options": {"include_usage": True}}
    start = time.perf_counter(); first = None; full = ""; words = 0; usage = None; finish = None; status = None
    try:
        resp = requests.post(base + "/v1/chat/completions", json=payload, stream=True, timeout=TIMEOUT)
        status = resp.status_code
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.startswith("data: ") and line != "data: [DONE]":
                if first is None:
                    first = time.perf_counter()
                try:
                    chunk = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for ch in chunk.get("choices") or []:
                    delta = (ch.get("delta") or {}).get("content") or ""
                    if delta:
                        full += delta; words += len(delta.split())
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
        end = time.perf_counter()
    except Exception as e:
        return {"engine": "nim", "base": base, "error": str(e), "http_status": status}
    total = end - start
    return {"engine": "nim", "base": base, "ttft_ms": round((first - start) * 1000, 1) if first else None,
            "total_latency_ms": round(total * 1000, 1), "tokens": words, "tps": round(words / total, 1) if total else 0,
            "completion_tokens": (usage or {}).get("completion_tokens"), "prompt_tokens": (usage or {}).get("prompt_tokens"),
            "finish_reason": finish, "http_status": status,
            "response_sha256": hashlib.sha256(full.encode("utf-8")).hexdigest(), "response_chars": len(full)}


def ollama_request(base, text, max_tokens=MAX_TOKENS):
    payload = {"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": text}], "stream": True,
               "options": {"num_predict": max_tokens, "temperature": TEMPERATURE, "top_p": TOP_P}}
    start = time.perf_counter(); first = None; full = ""; words = 0; final = {}; status = None
    try:
        resp = requests.post(base + "/api/chat", json=payload, stream=True, timeout=TIMEOUT)
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
        return {"engine": "ollama", "base": base, "error": str(e), "http_status": status}
    total = end - start
    ns = lambda k: round(final[k] / 1e6, 1) if isinstance(final.get(k), (int, float)) else None
    return {"engine": "ollama", "base": base, "ttft_ms": round((first - start) * 1000, 1) if first else None,
            "total_latency_ms": round(total * 1000, 1), "tokens": words, "tps": round(words / total, 1) if total else 0,
            "completion_tokens": final.get("eval_count"), "prompt_tokens": final.get("prompt_eval_count"),
            "finish_reason": final.get("done_reason"), "http_status": status,
            "load_duration_ms": ns("load_duration"), "prompt_eval_duration_ms": ns("prompt_eval_duration"),
            "eval_duration_ms": ns("eval_duration"),
            "response_sha256": hashlib.sha256(full.encode("utf-8")).hexdigest(), "response_chars": len(full)}


class Log:
    def __init__(self, out):
        os.makedirs(out, exist_ok=True)
        self.req = open(os.path.join(out, "requests.jsonl"), "a", encoding="utf-8", newline="\n")
        self.ev = open(os.path.join(out, "events.jsonl"), "a", encoding="utf-8", newline="\n")

    def event(self, **kw):
        kw["at"] = now(); self.ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); self.ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "ok", "tries", "at")}, flush=True)

    def row(self, arm, pos, q, r, before, **extra):
        r.update({"arm": arm, "pos": pos, "question_id": q["id"], "category": q["category"], "at": before["at"],
                  "gpu_before": before["gpu"], "ollama_ps_before": before["ollama_ps"],
                  "docker_ps_before": before["docker_ps"], "gpu_after": gpu()}, **extra)
        self.req.write(json.dumps(r, ensure_ascii=False) + "\n"); self.req.flush()
        print(f"  {arm:4s} {q['id']:5s} {r.get('engine')} ttft {r.get('ttft_ms')} tps {r.get('tps')} "
              f"tok {r.get('completion_tokens')} {r.get('error', '')}", flush=True)


def snapshot():
    return {"at": now(), "gpu": gpu(), "ollama_ps": ollama_ps(), "docker_ps": docker_ps()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["so", "nim"], required=True)
    ap.add_argument("--half", choices=["A", "B"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    s = json.load(open(SAMPLE, encoding="utf-8"))
    bank = {q["id"]: q for q in json.load(open(QFILE, encoding="utf-8"))}
    ids = [x["id"] for x in (s["harness_test_questions"] if a.test else s["run_order"])]
    order = [(i, bank[x]) for i, x in enumerate(ids)]
    log = Log(a.out)

    if a.phase == "so":
        if docker_ps():
            sys.exit(f"S-O refused: containers running {docker_ps()}")
        part = [p for p in order if p[0] % 2 == (0 if a.half == "A" else 1)]
        log.event(kind="connect_probe", half=a.half, ollama=connect_probe(11434, "/api/version"))
        ok = ollama_load()
        log.event(kind="so_load", half=a.half, ok=ok, ollama_ps=ollama_ps(), gpu=gpu())
        for base in (OLL_LOOPBACK, OLL_LOCALHOST):
            w = ollama_request(base, "Hello", 16)
            log.event(kind="so_warmup_discarded", half=a.half, base=base, ok="error" not in w, result=w)
            time.sleep(COOLDOWN)
        for pos, q in part:
            arms = [("S-OL", OLL_LOOPBACK), ("S-OH", OLL_LOCALHOST)]
            if pos % 4 in (2, 3):
                arms.reverse()
            for arm, base in arms:
                before = snapshot()
                log.row(arm, pos, q, ollama_request(base, q["text"]), before)
                time.sleep(COOLDOWN)
        return 0

    model = requests.get(NIM_LOCALHOST + "/v1/models", timeout=30).json()["data"][0]["id"]
    time.sleep(10)
    baseline = gpu()["used_mib"]
    log.event(kind="nim_phase_start", served_model=model, nim_alone_used_mib=baseline, gpu=gpu(), docker_ps=docker_ps())
    log.event(kind="connect_probe", nim=connect_probe(8000, "/v1/models"), ollama=connect_probe(11434, "/api/version"))
    floor = baseline - RECOVERY_TOLERANCE_MIB
    loaded = None
    c_warm = False
    for pos, q in order:
        seq = ["S-N", "C"] if pos % 2 == 0 else ["C", "S-N"]
        for arm in seq:
            if arm == "S-N":
                if loaded is not False:
                    ok = ollama_unload(); loaded = False
                    log.event(kind="unload", pos=pos, ok=ok, ollama_ps=ollama_ps(), gpu=gpu())
                    tries = 0
                    while gpu()["used_mib"] < floor and tries < RECOVERY_MAX:
                        nim_request(NIM_LOCALHOST, model, "Hello", 16); tries += 1
                        time.sleep(1)
                    log.event(kind="recovery", pos=pos, tries=tries, used_mib=gpu()["used_mib"], floor_mib=floor,
                              ok=gpu()["used_mib"] >= floor)
                    time.sleep(COOLDOWN)
                before = snapshot()
                log.row("S-N", pos, q, nim_request(NIM_LOCALHOST, model, q["text"]), before,
                        nim_alone_used_mib=baseline, recovery_floor_mib=floor)
                time.sleep(COOLDOWN)
            else:
                if loaded is not True:
                    ok = ollama_load(); loaded = True
                    log.event(kind="load", pos=pos, ok=ok, ollama_ps=ollama_ps(), gpu=gpu())
                    if not c_warm:
                        w = ollama_request(OLL_LOOPBACK, "Hello", 16)
                        log.event(kind="c_warmup_discarded", pos=pos, ok="error" not in w, result=w)
                        c_warm = True
                        time.sleep(COOLDOWN)
                before = snapshot()
                log.row("C", pos, q, nim_request(NIM_LOCALHOST, model, q["text"]), before)
                time.sleep(COOLDOWN)
                before = snapshot()
                log.row("C", pos, q, ollama_request(OLL_LOOPBACK, q["text"]), before)
                time.sleep(COOLDOWN)
    ok = ollama_unload()
    log.event(kind="nim_phase_end", ok=ok, gpu=gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
