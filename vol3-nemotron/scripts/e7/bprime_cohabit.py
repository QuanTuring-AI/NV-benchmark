#!/usr/bin/env python3
"""B′ · one run · co-residence with Ollama's GPU layers limited by a VRAM ledger (num_gpu fixed before the run).

Question: with Ollama's GPU share reduced to the size implied by Vol.1's VRAM record, does NIM TTFT come back
to Vol.1's order of magnitude, and if TTFT rises, is it compute contention or memory pressure?

Cells (same NIM container throughout, same 30 questions, same order — identical to C):
  A1  NIM alone
  B′  Ollama llama3.1:8b resident with options.num_gpu = N, alternating per question: NIM → 2 s → Ollama → 2 s
  A2  Ollama unloaded (keep_alive 0, verified with `ollama ps`), NIM alone

Request payloads are Vol.1 E2 verbatim (benchmark/run_benchmark.py:50-139). The ONLY addition to any payload is
options.num_gpu = N on Ollama requests (the variable under test). Timing logic is Vol.1's, unchanged.
Recorded in addition, without touching payloads or timing:
  - NIM: finish_reason from the stream   - Ollama: done_reason, eval_count, eval_duration, prompt_eval_count, load_duration
  - per-cell Windows GPU counter snapshots (per-process dedicated / shared GPU memory) via gpu_counters.ps1
  - `ollama ps` text at cell start / end (and after warm-up)

Pre-registered gate: if A1 NIM TTFT avg is outside [30, 80] ms, stop before loading Ollama.
Checkpoints: bprime_cohabit.partial.json is rewritten after every cell and after the warm-up.
"""
import json, os, statistics as st, subprocess, sys, time, urllib.request
import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))      # vol2/
OUT = os.environ.get("BPRIME_OUT") or os.path.join(ROOT, "results", "e7", "b_prime")
NIM_BASE = os.environ.get("BPRIME_NIM_BASE", "http://localhost:8000")
OLLAMA_BASE = os.environ.get("BPRIME_OLLAMA_BASE", "http://localhost:11434")
NIM_URL = NIM_BASE + "/v1/chat/completions"
OLLAMA_URL = OLLAMA_BASE + "/api/chat"
OLLAMA_MODEL = "llama3.1:8b"
MAX_TOKENS, COOLDOWN = 500, 2
COUNTERS_PS1 = os.path.join(ROOT, "scripts", "e7", "gpu_counters.ps1")
SKIP_COUNTERS = os.environ.get("BPRIME_SKIP_COUNTERS") == "1"          # mock tests only


def now():
    return subprocess.run(["date", "+%FT%T%z"], capture_output=True, text=True).stdout.strip()


def winpath(p):
    try:
        return subprocess.run(["cygpath", "-w", p], capture_output=True, text=True).stdout.strip() or p
    except Exception:
        return p


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


def snapshot(tag, pidfile):
    path = os.path.join(OUT, "counters", f"snap_{tag}.json")
    if SKIP_COUNTERS:
        return {"skipped": True}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    args = ["powershell.exe", "-NoProfile", "-File", winpath(COUNTERS_PS1), "-Mode", "snapshot", "-Out", winpath(path)]
    if pidfile and os.path.exists(pidfile):
        args += ["-PidFile", winpath(pidfile)]
    subprocess.run(args, capture_output=True, text=True, timeout=60)
    try:
        return json.load(open(path, encoding="utf-8-sig"))
    except Exception as e:
        return {"error": str(e)}


def identify(before, after, total_mib, names=None, exclude_pids=()):
    """Process whose dedicated GPU memory grew most between two snapshots. Values above the adapter total are
    counter artefacts and are ignored (one overlay process reports >1 TB on this machine).
    names: optional set of lower-case process names to restrict to. Ollama's GPU memory is held by its runner
    process `llama-server`, not by `ollama` (verified in results/e7/b_prime/precheck/)."""
    if not before or not after or "processes" not in before or "processes" not in after:
        return None
    b = {p["pid"]: p for p in before["processes"]}
    best = None
    for p in after["processes"]:
        if p["dedicated_mib"] > total_mib or p["pid"] in exclude_pids:
            continue
        if names and str(p.get("name") or "").lower() not in names:
            continue
        grow = p["dedicated_mib"] - (b.get(p["pid"], {}).get("dedicated_mib", 0.0) if b.get(p["pid"], {}).get("dedicated_mib", 0.0) <= total_mib else 0.0)
        if best is None or grow > best["growth_mib"]:
            best = {"pid": p["pid"], "name": p.get("name"), "growth_mib": round(grow, 1), "dedicated_mib": p["dedicated_mib"], "shared_mib": p["shared_mib"]}
    return best


def proc_mem(snap, pid):
    for p in (snap or {}).get("processes", []):
        if p["pid"] == pid:
            return {"dedicated_mib": p["dedicated_mib"], "shared_mib": p["shared_mib"]}
    return None


def benchmark_nim(model, question):
    payload = {"model": model, "messages": [{"role": "user", "content": question}], "max_tokens": MAX_TOKENS, "stream": True}
    get_vram_mb()
    start = time.perf_counter(); first_token_time = None; full_response = ""; token_count = 0; finish_reason = None
    try:
        response = requests.post(NIM_URL, json=payload, stream=True, timeout=90)
        status = response.status_code
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: ") and line != "data: [DONE]":
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    try:
                        chunk = json.loads(line[6:])
                        ch0 = chunk.get("choices", [{}])[0]
                        delta = ch0.get("delta", {}).get("content", "")
                        if ch0.get("finish_reason"):
                            finish_reason = ch0["finish_reason"]
                        if delta:
                            full_response += delta
                            token_count += len(delta.split())
                    except (json.JSONDecodeError, IndexError):
                        pass
        end = time.perf_counter()
    except Exception as e:
        return {"provider": "nim", "error": str(e), "t_start": time.time()}
    total_sec = end - start
    return {"provider": "nim", "ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
            "total_latency_ms": round(total_sec * 1000, 1), "tokens": token_count,
            "tps": round(token_count / total_sec, 1) if total_sec > 0 else 0, "vram_mb": get_vram_mb(),
            "finish_reason": finish_reason, "http_status": status, "t_end_epoch": time.time(), "t_start_epoch": time.time() - total_sec}


def benchmark_ollama(question, num_gpu):
    payload = {"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": question}], "stream": True,
               "options": {"num_predict": MAX_TOKENS, "num_gpu": num_gpu}}
    get_vram_mb()
    start = time.perf_counter(); first_token_time = None; full_response = ""; token_count = 0; done = {}
    try:
        response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=90)
        status = response.status_code
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
                        done = {k: chunk.get(k) for k in ("done_reason", "eval_count", "eval_duration", "prompt_eval_count", "prompt_eval_duration", "load_duration", "total_duration")}
                        break
                except json.JSONDecodeError:
                    pass
        end = time.perf_counter()
    except Exception as e:
        return {"provider": "ollama", "error": str(e)}
    total_sec = end - start
    return {"provider": "ollama", "ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
            "total_latency_ms": round(total_sec * 1000, 1), "tokens": token_count,
            "tps": round(token_count / total_sec, 1) if total_sec > 0 else 0, "vram_mb": get_vram_mb(),
            "http_status": status, **done, "t_end_epoch": time.time(), "t_start_epoch": time.time() - total_sec}


def stats(v):
    if not v:
        return None
    s = sorted(v); p = lambda q: round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 1)
    return {"avg": round(st.mean(v), 1), "p50": p(0.5), "p95": p(0.95), "min": min(v), "max": max(v), "n": len(v)}


def write_text(name, text):
    with open(os.path.join(OUT, name), "a", encoding="utf-8") as f:
        f.write(f"--- {now()}\n{text}\n")


def checkpoint(res):
    with open(os.path.join(OUT, "bprime_cohabit.partial.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)


def cell(name, model, qs, with_ollama, num_gpu, pidfile, total_mib):
    ps_start = ollama_ps(); write_text(f"ollama_ps_{name}.txt", "cell start\n" + ps_start)
    ev = {"cell": name, "start": now(), "vram_start": get_vram_mb(), "ollama_ps_start": ps_start, "counters_start": snapshot(f"{name}_start", pidfile)}
    nim_rows, oll_rows = [], []
    for q in qs:
        r = benchmark_nim(model, q["text"]); r.update(question_id=q["id"], category=q["category"]); nim_rows.append(r)
        time.sleep(COOLDOWN)
        if with_ollama:
            o = benchmark_ollama(q["text"], num_gpu); o.update(question_id=q["id"], category=q["category"]); oll_rows.append(o)
            time.sleep(COOLDOWN)
    ok = [r for r in nim_rows if "error" not in r]
    ps_end = ollama_ps(); write_text(f"ollama_ps_{name}.txt", "cell end\n" + ps_end)
    ev.update({"end": now(), "vram_end": get_vram_mb(), "ollama_ps_end": ps_end, "counters_end": snapshot(f"{name}_end", pidfile),
               "nim": {"n_ok": len(ok), "n_error": len(nim_rows) - len(ok), "ttft_ms": stats([r["ttft_ms"] for r in ok if r["ttft_ms"] is not None]),
                       "tps_fragments": stats([r["tps"] for r in ok]), "latency_ms": stats([r["total_latency_ms"] for r in ok]),
                       "vram_mb": stats([r["vram_mb"] for r in ok]),
                       "finish_reason_counts": {k: sum(1 for r in ok if r.get("finish_reason") == k) for k in {r.get("finish_reason") for r in ok}}},
               "rows_nim": nim_rows})
    for k in ("vram_start", "vram_end"):
        ev[k + "_pct_of_reported_total"] = round(100 * ev[k] / total_mib, 2) if ev[k] > 0 else None
        ev[k + "_pct_of_32768"] = round(100 * ev[k] / 32768, 2) if ev[k] > 0 else None
    if with_ollama:
        ook = [r for r in oll_rows if "error" not in r]
        ec = [(r["tokens"], r["eval_count"]) for r in ook if r.get("eval_count")]
        ev["ollama"] = {"n_ok": len(ook), "n_error": len(oll_rows) - len(ook), "ttft_ms": stats([r["ttft_ms"] for r in ook if r["ttft_ms"] is not None]),
                        "tps_fragments": stats([r["tps"] for r in ook]), "vram_mb": stats([r["vram_mb"] for r in ook]),
                        "eval_count": stats([r["eval_count"] for r in ook if r.get("eval_count")]),
                        "fragments_over_eval_count": round(sum(a for a, _ in ec) / sum(b for _, b in ec), 4) if ec else None,
                        "tokens_per_s_from_eval": stats([r["eval_count"] / (r["eval_duration"] / 1e9) for r in ook if r.get("eval_count") and r.get("eval_duration")]),
                        "done_reason_counts": {k: sum(1 for r in ook if r.get("done_reason") == k) for k in {r.get("done_reason") for r in ook}}}
        ev["rows_ollama"] = oll_rows
    t = ev["nim"]["ttft_ms"] or {}
    print(f"[{name}] {ev['start']}→{ev['end']} · NIM TTFT avg {t.get('avg')} (p50 {t.get('p50')}) · VRAM {ev['vram_start']}→{ev['vram_end']}"
          + (f" · Ollama tps {ev['ollama']['tps_fragments'] and ev['ollama']['tps_fragments']['avg']}" if with_ollama else ""), flush=True)
    return ev


def main():
    pred = json.load(open(os.path.join(OUT, "prediction_bprime.json"), encoding="utf-8"))
    N = int(pred["design"]["num_gpu"])
    ids = json.load(open(os.path.join(ROOT, "results", "e7", "c", "prediction_c.json"), encoding="utf-8"))["design"]["subset_ids"]
    allq = {q["id"]: q for q in json.load(open(os.path.join(ROOT, "..", "benchmark", "questions.json"), encoding="utf-8"))}
    qs = [allq[i] for i in ids]
    pidfile = os.path.join(OUT, "counters", "pids.txt")
    idle = json.load(open(os.environ["BPRIME_IDLE_SNAPSHOT"], encoding="utf-8-sig")) if os.environ.get("BPRIME_IDLE_SNAPSHOT") else None
    model = json.load(urllib.request.urlopen(NIM_BASE + "/v1/models", timeout=30))["data"][0]["id"]
    smi = subprocess.run(["nvidia-smi", "--query-gpu=memory.total,driver_version", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip().split(",")
    total_mib, driver = int(smi[0]), smi[1].strip()
    ov = subprocess.run(["ollama", "--version"], capture_output=True, text=True).stdout.strip()
    res = {"experiment": "B′ · co-residence with Ollama num_gpu from VRAM ledger", "run_tag": os.environ.get("RUN_TAG"),
           "prediction_file": "results/e7/b_prime/prediction_bprime.json", "prediction_written_at": pred["written_at"],
           "num_gpu": N, "model": model, "ollama_model": OLLAMA_MODEL, "ollama_version": ov, "driver": driver,
           "gpu_memory_total_mib_reported": total_mib, "questions": {"file": "benchmark/questions.json", "ids": ids},
           "payload_note": "Vol.1 E2 verbatim; only addition options.num_gpu on Ollama requests", "started": now(), "cells": []}
    ready = snapshot("ready", None)
    nim_proc = identify(idle, ready, total_mib)
    res["process_identification"] = {"idle_snapshot": bool(idle), "nim": nim_proc,
                                     "rule": "largest dedicated growth idle→ready, values above adapter total ignored; valid only if growth ≥ 20000 MiB"}
    res["process_identification"]["nim_valid"] = bool(nim_proc and nim_proc["growth_mib"] >= 20000)
    if res["process_identification"]["nim_valid"]:
        os.makedirs(os.path.dirname(pidfile), exist_ok=True)
        open(pidfile, "w").write(f"{nim_proc['pid']}\n")
    checkpoint(res)

    a1 = cell("A1", model, qs, False, N, pidfile, total_mib); res["cells"].append(a1); checkpoint(res)
    t = (a1["nim"]["ttft_ms"] or {}).get("avg")
    res["gate_A1"] = {"rule": "A1 NIM TTFT avg in [30, 80] ms", "value": t, "pass": t is not None and 30 <= t <= 80}
    if not res["gate_A1"]["pass"]:
        res["stopped"] = "A1 gate failed — Ollama not loaded"; res["finished"] = now(); checkpoint(res)
        json.dump(res, open(os.path.join(OUT, "bprime_cohabit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("A1 gate failed ⇒ stop", flush=True); return 7

    warm = benchmark_ollama("Hello.", N); time.sleep(COOLDOWN)
    ps_w = ollama_ps(); write_text("ollama_ps_B.txt", "after warm-up\n" + ps_w)
    snap_w = snapshot("B_after_warmup", pidfile)
    oll_proc = identify(a1.get("counters_end"), snap_w, total_mib, names={"llama-server"},
                        exclude_pids={nim_proc["pid"]} if nim_proc else ())
    res["B_warmup"] = {"result": warm, "ollama_ps": ps_w, "vram": get_vram_mb(), "at": now(), "counters": snap_w, "ollama_process": oll_proc}
    if oll_proc and os.path.exists(pidfile):
        open(pidfile, "a").write(f"{oll_proc['pid']}\n")
    print(f"[B warm-up] {ps_w.splitlines()[-1] if ps_w else ''} · VRAM {res['B_warmup']['vram']} · ollama proc {oll_proc}", flush=True)
    checkpoint(res)

    b = cell("B", model, qs, True, N, pidfile, total_mib); res["cells"].append(b); checkpoint(res)

    try:
        requests.post(OLLAMA_BASE + "/api/generate", json={"model": OLLAMA_MODEL, "keep_alive": 0}, timeout=60)
    except Exception as e:
        res["unload_error"] = str(e)
    for _ in range(30):
        if OLLAMA_MODEL not in ollama_ps():
            break
        time.sleep(2)
    time.sleep(5)
    res["A2_unload_check"] = {"ollama_ps": ollama_ps(), "vram": get_vram_mb(), "at": now(), "counters": snapshot("A2_after_unload", pidfile)}
    checkpoint(res)

    a2 = cell("A2", model, qs, False, N, pidfile, total_mib); res["cells"].append(a2)
    res["finished"] = now()
    checkpoint(res)
    json.dump(res, open(os.path.join(OUT, "bprime_cohabit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("saved results/e7/b_prime/bprime_cohabit.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
