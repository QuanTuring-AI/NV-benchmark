#!/usr/bin/env python3
"""E6 · concurrency on the Vol.1 stack (Llama 3.1 8B Instruct on NIM 1.13.1).

Vol.1 listed "E6 · concurrency stress test (1–50 concurrent users)" as planned.
This harness runs exactly that on Vol.1's own stack, with Vol.1's question set and request settings.

Per-request measurement = Vol.1 E2 `benchmark_nim` (benchmark/run_benchmark.py:50-93), same logic:
  - payload {model, messages, max_tokens=500, stream=True}  (no temperature, no stream_options)
  - TTFT   = time to the first SSE `data:` line (may carry only the role)
  - tokens = Σ len(delta.split()) over content deltas  => non-whitespace streamed fragments (≈ tokens)
  - tps    = tokens / total request time
Changes made so it can run concurrently; none of them is inside the per-request timed region:
  1. no nvidia-smi call per request (Vol.1 calls it before and after each request). With c threads that
     spawns c subprocesses right before the wave and staggers request start. VRAM is sampled once per wave.
  2. HTTP status code recorded; a non-200 response counts as a failure (Vol.1 does not check it, so an
     error response would appear as a request with 0 tokens).
  3. all c requests of a wave are released together by a threading.Barrier.
  4. requests timeout 90 s kept from Vol.1; a timeout is a failure.

Wave design (fixed before the run, see prediction_e6.json):
  - questions: ../../benchmark/questions.json, fixed order, cycled. Each level restarts at q001.
  - per level: 1 warmup wave (not counted), then max(3, ceil(100 / c)) measured waves,
    so every level's measured set covers the full 100-question set at least once
    (the output-length mix is then comparable across levels).
  - a wave = c requests with the next c questions in the cycle; the next wave starts when all c return.
  - any failure at a level => record it and stop scanning upward (the failing level is itself a result).
Stopping rule wording: if no level fails, the result is "no ceiling reached within 1–50",
never "the limit is 50".
"""
import argparse, datetime, json, math, os, statistics as st, subprocess, sys, threading, time
import requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))                       # roadmap-e456/
QUESTIONS = os.path.join(ROOT, "..", "benchmark", "questions.json")
QUESTIONS_SHA256 = "262f2339d55ec6b855f7b0180704bd225fdbc561ea37f902b99e1ab405add1f9"
MAX_TOKENS = 500


def now():
    return subprocess.run(["date", "+%FT%T%z"], capture_output=True, text=True).stdout.strip()


def gpu_ctx():
    q = "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw"
    try:
        return subprocess.run(["nvidia-smi", q, "--format=csv,noheader"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as e:
        return f"ERR {e}"


def vram_mb(ctx_line):
    try:
        return int(ctx_line.split(",")[0].strip().split()[0])
    except Exception:
        return -1


def benchmark_nim(url, model, question, barrier):
    """Vol.1 E2 benchmark_nim timing logic, unchanged (see module docstring for the 4 changes)."""
    payload = {"model": model, "messages": [{"role": "user", "content": question}], "max_tokens": MAX_TOKENS, "stream": True}
    try:
        barrier.wait(timeout=60)
    except threading.BrokenBarrierError as e:
        return {"error": f"barrier: {e}", "http_status": None}
    start = time.perf_counter()
    first_token_time = None
    full_response = ""
    token_count = 0
    status = None
    try:
        response = requests.post(url, json=payload, stream=True, timeout=90)
        status = response.status_code
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
        return {"error": f"{type(e).__name__}: {e}", "http_status": status}
    total_sec = end - start
    r = {"ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
         "total_latency_ms": round(total_sec * 1000, 1), "tokens": token_count,
         "tps": round(token_count / total_sec, 1) if total_sec > 0 else 0,
         "http_status": status, "response_chars": len(full_response)}
    if status != 200:
        r["error"] = f"HTTP {status}"
    return r


def stats(v):
    if not v:
        return None
    s = sorted(v)

    def p(q):
        k = (len(s) - 1) * q
        f, c = math.floor(k), math.ceil(k)
        return round(s[f] + (s[c] - s[f]) * (k - f), 1)
    return {"avg": round(st.mean(v), 1), "p50": p(0.5), "p95": p(0.95), "min": round(s[0], 1), "max": round(s[-1], 1), "n": len(v)}


def run_wave(url, model, qs, start_idx, c):
    picked = [qs[(start_idx + k) % len(qs)] for k in range(c)]
    barrier = threading.Barrier(c)
    out = [None] * c

    def work(i):
        out[i] = benchmark_nim(url, model, picked[i]["text"], barrier)
        out[i].update(question_id=picked[i]["id"], category=picked[i]["category"])

    th = [threading.Thread(target=work, args=(i,)) for i in range(c)]
    t0 = time.perf_counter()
    for t in th:
        t.start()
    for t in th:
        t.join()
    wall = time.perf_counter() - t0
    ctx_after = gpu_ctx()
    ok = [r for r in out if "error" not in r]
    toks = sum(r["tokens"] for r in ok)
    return {"wall_s": round(wall, 3), "fragments": toks, "aggregate_fragments_per_s": round(toks / wall, 2) if wall > 0 else None,
            "failures": c - len(ok), "vram_mb_after_wave": vram_mb(ctx_after), "requests": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--levels", required=True)
    ap.add_argument("--prelaunch-ctx", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--index-digest", required=True)
    ap.add_argument("--manifest-digest", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--extra-env", required=True)
    ap.add_argument("--prediction", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import hashlib
    raw = open(QUESTIONS, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != QUESTIONS_SHA256:
        sys.exit(f"questions.json sha256 mismatch: {sha}")
    qs = json.loads(raw.decode("utf-8"))
    pred = json.load(open(a.prediction, encoding="utf-8"))
    model = requests.get(a.base + "/v1/models", timeout=30).json()["data"][0]["id"]
    url = a.base + "/v1/chat/completions"
    pre = open(a.prelaunch_ctx, encoding="utf-8").read().strip()
    started = now()

    levels, stopped_at = [], None
    for c in [int(x) for x in a.levels.split(",")]:
        waves_n = max(3, math.ceil(len(qs) / c))
        lvl_ctx_before = gpu_ctx()
        warm = run_wave(url, model, qs, 0, c)
        waves = [run_wave(url, model, qs, w * c, c) for w in range(waves_n)]
        reqs = [r for w in waves for r in w["requests"]]
        ok = [r for r in reqs if "error" not in r]
        agg = [w["aggregate_fragments_per_s"] for w in waves if w["aggregate_fragments_per_s"] is not None]
        fails = sum(w["failures"] for w in waves) + warm["failures"]
        cv = round(st.pstdev(agg) / st.mean(agg), 4) if len(agg) > 1 and st.mean(agg) > 0 else None
        lvl = {"concurrency": c, "ctx_before_level": lvl_ctx_before, "warmup": {k: warm[k] for k in ("wall_s", "failures")},
               "waves_measured": waves_n, "requests_measured": len(reqs), "failures_including_warmup": fails,
               "questions_covered": len({r["question_id"] for r in reqs}),
               "aggregate_fragments_per_s": {"per_wave": agg, "mean": round(st.mean(agg), 2) if agg else None,
                                             "min": min(agg) if agg else None, "max": max(agg) if agg else None, "cv": cv},
               "ttft_ms": stats([r["ttft_ms"] for r in ok if r["ttft_ms"] is not None]),
               "total_latency_ms": stats([r["total_latency_ms"] for r in ok]),
               "per_request_tps": stats([r["tps"] for r in ok]),
               "fragments_per_request": stats([r["tokens"] for r in ok]),
               "vram_mb_max_after_wave": max(w["vram_mb_after_wave"] for w in waves),
               "errors_sample": [r["error"] for r in reqs if "error" in r][:5] + ([r["error"] for r in warm["requests"] if "error" in r][:3]),
               "waves": waves}
        levels.append(lvl)
        # checkpoint after every level: a failure at the final write must not lose measured levels
        with open(a.out + ".partial.json", "w", encoding="utf-8") as fh:
            json.dump({"checkpoint_after_level": c, "started": started, "model": model, "levels": levels}, fh, ensure_ascii=False)
        t = lvl["ttft_ms"] or {}
        print(f"c={c:>3} waves={waves_n} req={len(reqs)} fail={fails} agg mean={lvl['aggregate_fragments_per_s']['mean']} (cv {cv}) "
              f"TTFT avg={t.get('avg')} p50={t.get('p50')} p95={t.get('p95')} ms · {now()}", flush=True)
        if fails:
            stopped_at = c
            print(f"  c={c}: {fails} failed request(s) => stop scanning upward", flush=True)
            break

    finished = now()
    tested = [l["concurrency"] for l in levels]
    res = {"experiment": "E6 · concurrency on the Vol.1 stack",
           "prediction_file": os.path.basename(a.prediction), "prediction_written_at": pred.get("written_at"),
           "model": model, "image": a.image, "image_index_digest": a.index_digest, "manifest_digest_amd64": a.manifest_digest,
           "profile": a.profile, "extra_env": a.extra_env,
           "questions": {"file": "benchmark/questions.json", "sha256": sha, "order": "fixed, cycled, restart at q001 per level"},
           "request_settings": {"max_tokens": MAX_TOKENS, "stream": True, "temperature": "not set (Vol.1 E2)", "timeout_s": 90},
           "levels_requested": a.levels, "levels_tested": tested, "stopped_at_concurrency": stopped_at,
           "ceiling_statement": (f"failures at c={stopped_at}" if stopped_at else
                                 f"no failures at any tested level ⇒ no ceiling reached within {tested[0]}–{tested[-1]}; this is NOT a measured limit"),
           "not_comparable_with": ("Nemotron concurrency curves measured with max_tokens=64 and a different per-request harness "
                                   "(temperature 0, TTFT at first content delta). Output length differs (500 vs 64) ⇒ do not plot side by side."),
           "units": {"aggregate_fragments_per_s": "Σ non-whitespace streamed fragments in a wave ÷ wave wall time (≈ tokens/s, Vol.1 formula)",
                     "per_request_tps": "Vol.1 E2 formula, per request"},
           "measurement_context": {"prelaunch": pre, "run_started": started, "run_finished": finished},
           "levels": levels}
    top = levels[-1]
    res["measurement_label"] = (
        f"{model} · {a.image} · index {a.index_digest[:19]}… · manifest {a.manifest_digest[:19]}… · profile {a.profile[:12]}… · {a.extra_env} · "
        f"RTX 5090 · Win11 + Docker Desktop(WSL2) · Vol.1 questions.json (sha256 {sha[:12]}…) fixed-order cycle · "
        f"max_tokens=500 · streaming · temperature not set · levels tested {tested} · warmup 1 wave per level not counted · "
        f"≥max(3, ceil(100/c)) measured waves · stopped_at={stopped_at} · "
        f"top level c={top['concurrency']}: aggregate {top['aggregate_fragments_per_s']['mean']} fragments/s (avg of waves), "
        f"TTFT avg {(top['ttft_ms'] or {}).get('avg')} ms (p50 {(top['ttft_ms'] or {}).get('p50')}) · window {started} → {finished}")
    if os.path.dirname(a.out):
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(res["measurement_label"])
    print(res["ceiling_statement"])


if __name__ == "__main__":
    main()
