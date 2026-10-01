#!/usr/bin/env python3
"""C · 同住假說檢驗：A1（NIM 單獨）→ B（Ollama 常駐＋交替）→ A2（Ollama 卸載，NIM 單獨）。
同一 NIM 容器、同一窗口、同一 30 題、單一變因。
benchmark_nim / benchmark_ollama 逐字沿用 Vol.1 run_benchmark.py（唯讀複製，payload 未加任何欄位）。"""
import json, os, statistics as st, subprocess, sys, time, datetime, urllib.request
import requests
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "results", "e7", "c")
NIM_URL = "http://localhost:8000/v1/chat/completions"
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"
MAX_TOKENS, COOLDOWN = 500, 2


def now(): return subprocess.run(["date", "+%FT%T"], capture_output=True, text=True).stdout.strip()


def get_vram_mb():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return -1


def ollama_ps():
    try:
        return subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:
        return f"ERR {e}"


def benchmark_nim(model, question):
    payload = {"model": model, "messages": [{"role": "user", "content": question}], "max_tokens": MAX_TOKENS, "stream": True}
    get_vram_mb()
    start = time.perf_counter(); first_token_time = None; full_response = ""; token_count = 0
    try:
        response = requests.post(NIM_URL, json=payload, stream=True, timeout=90)
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: ") and line != "data: [DONE]":
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            full_response += delta
                            token_count += len(delta.split())
                    except json.JSONDecodeError:
                        pass
        end = time.perf_counter()
    except Exception as e:
        return {"provider": "nim", "error": str(e)}
    total_sec = end - start
    return {"provider": "nim", "ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
            "total_latency_ms": round(total_sec * 1000, 1), "tokens": token_count,
            "tps": round(token_count / total_sec, 1) if total_sec > 0 else 0, "vram_mb": get_vram_mb()}


def benchmark_ollama(question):
    payload = {"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": question}], "stream": True, "options": {"num_predict": MAX_TOKENS}}
    get_vram_mb()
    start = time.perf_counter(); first_token_time = None; full_response = ""; token_count = 0
    try:
        response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=90)
        for line in response.iter_lines():
            if line:
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                        full_response += content
                        token_count += len(content.split())
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    pass
        end = time.perf_counter()
    except Exception as e:
        return {"provider": "ollama", "error": str(e)}
    total_sec = end - start
    return {"provider": "ollama", "ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
            "total_latency_ms": round(total_sec * 1000, 1), "tokens": token_count,
            "tps": round(token_count / total_sec, 1) if total_sec > 0 else 0, "vram_mb": get_vram_mb()}


def stats(v):
    if not v: return None
    s = sorted(v); p = lambda q: round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 1)
    return {"avg": round(st.mean(v), 1), "p50": p(0.5), "p95": p(0.95), "min": min(v), "max": max(v), "n": len(v)}


def cell(name, model, qs, with_ollama):
    ev = {"cell": name, "start": now(), "vram_start": get_vram_mb(), "ollama_ps_start": ollama_ps()}
    nim_rows, oll_rows = [], []
    for q in qs:
        r = benchmark_nim(model, q["text"]); r.update(question_id=q["id"], category=q["category"]); nim_rows.append(r)
        time.sleep(COOLDOWN)
        if with_ollama:
            o = benchmark_ollama(q["text"]); o.update(question_id=q["id"], category=q["category"]); oll_rows.append(o)
            time.sleep(COOLDOWN)
    ok = [r for r in nim_rows if "error" not in r]
    ev.update({"end": now(), "vram_end": get_vram_mb(), "ollama_ps_end": ollama_ps(),
               "nim": {"n_ok": len(ok), "n_error": len(nim_rows) - len(ok), "ttft_ms": stats([r["ttft_ms"] for r in ok if r["ttft_ms"] is not None]),
                       "tps_words": stats([r["tps"] for r in ok]), "latency_ms": stats([r["total_latency_ms"] for r in ok]),
                       "vram_mb": stats([r["vram_mb"] for r in ok])},
               "rows_nim": nim_rows})
    if with_ollama:
        ook = [r for r in oll_rows if "error" not in r]
        ev["ollama"] = {"n_ok": len(ook), "n_error": len(oll_rows) - len(ook), "ttft_ms": stats([r["ttft_ms"] for r in ook if r["ttft_ms"] is not None]),
                        "tps_words": stats([r["tps"] for r in ook]), "vram_mb": stats([r["vram_mb"] for r in ook])}
        ev["rows_ollama"] = oll_rows
    t = ev["nim"]["ttft_ms"]
    print(f"[{name}] {ev['start']}→{ev['end']} · NIM TTFT avg {t['avg']} (p50 {t['p50']}) · tps {ev['nim']['tps_words']['avg']} · VRAM {ev['vram_start']}→{ev['vram_end']}"
          + (f" · Ollama tps {ev['ollama']['tps_words']['avg']} · Ollama TTFT {ev['ollama']['ttft_ms']['avg']}" if with_ollama else ""), flush=True)
    print(f"      ollama ps @end: {ev['ollama_ps_end'].splitlines()[-1] if ev['ollama_ps_end'] else ''}", flush=True)
    return ev


def main():
    pred = json.load(open(os.path.join(OUT, "prediction_c.json"), encoding="utf-8"))
    ids = pred["design"]["subset_ids"]
    allq = {q["id"]: q for q in json.load(open(os.path.join(ROOT, "..", "benchmark", "questions.json"), encoding="utf-8"))}
    qs = [allq[i] for i in ids]
    model = json.load(urllib.request.urlopen("http://localhost:8000/v1/models", timeout=30))["data"][0]["id"]
    res = {"prediction_file": "results/e7/c/prediction_c.json", "prediction_written_at": pred["written_at"], "model": model, "started": now(), "cells": []}
    # A1
    res["cells"].append(cell("A1", model, qs, False))
    # B：先載入 Ollama 模型（不計），確認常駐
    warm = benchmark_ollama("Hello."); time.sleep(COOLDOWN)
    res["B_warmup"] = {"result": warm, "ollama_ps": ollama_ps(), "vram": get_vram_mb(), "at": now()}
    print(f"[B warmup] ollama ps: {res['B_warmup']['ollama_ps'].splitlines()[-1] if res['B_warmup']['ollama_ps'] else ''} · VRAM {res['B_warmup']['vram']}", flush=True)
    res["cells"].append(cell("B", model, qs, True))
    # A2：卸載 Ollama 模型並驗證
    try:
        requests.post("http://localhost:11434/api/generate", json={"model": OLLAMA_MODEL, "keep_alive": 0}, timeout=60)
    except Exception as e:
        res["unload_error"] = str(e)
    for _ in range(30):
        if OLLAMA_MODEL not in ollama_ps():
            break
        time.sleep(2)
    time.sleep(5)
    res["A2_unload_check"] = {"ollama_ps": ollama_ps(), "vram": get_vram_mb(), "at": now()}
    print(f"[A2 unload] ollama ps 仍含模型? {OLLAMA_MODEL in res['A2_unload_check']['ollama_ps']} · VRAM {res['A2_unload_check']['vram']}", flush=True)
    res["cells"].append(cell("A2", model, qs, False))
    res["finished"] = now()
    json.dump(res, open(os.path.join(OUT, "c_cohabit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("saved results/e7/c/c_cohabit.json")


if __name__ == "__main__":
    main()
