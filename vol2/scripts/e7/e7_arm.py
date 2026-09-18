#!/usr/bin/env python3
"""E7 · 一臂 ＝ 100Q × 3 輪。

🔴 `benchmark_nim` 逐字沿用 Vol.1 `NV-benchmark/benchmark/run_benchmark.py`（唯讀複製，未改一行邏輯）：
   - token_count = Σ len(delta.split())  ⇒ 逐 delta 取 split ⇒ 「非空白串流片段/秒」≈ token/秒（2026-09-13 更正：先前誤寫為單字/秒）；改了就與 73.8 不可比
   - TTFT = 第一個 SSE data 行（即使只含 role）
   - max_tokens=500 · stream=true · ⛔ 不設 temperature · COOLDOWN 2s · 每題後取 VRAM
新增（不改上述量法）：usage.completion_tokens 併記，供「真 token/s」另算；avg ＋ p50 ＋ p95；per-category。
"""
import argparse, json, os, statistics as st, subprocess, sys, time, datetime
import requests
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from nim_ttft import ctx

MAX_TOKENS, ROUNDS, COOLDOWN = 500, 3, 2


def get_vram_mb():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return -1


def benchmark_nim(url, model, question):
    payload = {"model": model, "messages": [{"role": "user", "content": question}], "max_tokens": MAX_TOKENS, "stream": True,
               "stream_options": {"include_usage": True}}  # 🔴 唯一偏離 Vol.1 payload：多要 usage chunk 以取得真 token/s；TTFT 與片段計數不受影響，total_latency 多一個 SSE frame（<1 ms / 4.3 s）
    get_vram_mb()
    start = time.perf_counter(); first_token_time = None; full_response = ""; token_count = 0; usage = None; reasoning_chars = 0
    try:
        response = requests.post(url, json=payload, stream=True, timeout=90)
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: ") and line != "data: [DONE]":
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    try:
                        chunk = json.loads(line[6:])
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                        ch = chunk.get("choices") or [{}]
                        delta = ch[0].get("delta", {}).get("content", "") if ch else ""
                        rdelta = (ch[0].get("delta", {}).get("reasoning_content") or ch[0].get("delta", {}).get("reasoning") or "") if ch else ""
                        reasoning_chars += len(rdelta)  # 僅記錄（推理模型臂用）· 不進 tps／TTFT 任何計算
                        if delta:
                            full_response += delta
                            token_count += len(delta.split())
                    except json.JSONDecodeError:
                        pass
        end = time.perf_counter()
    except Exception as e:
        return {"error": str(e)}
    total_sec = end - start
    return {"ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
            "total_latency_ms": round(total_sec * 1000, 1), "tokens": token_count,
            "tps": round(token_count / total_sec, 1) if total_sec > 0 else 0,
            "completion_tokens": (usage or {}).get("completion_tokens"),
            "true_tps": round((usage or {}).get("completion_tokens", 0) / total_sec, 1) if usage and total_sec > 0 else None,
            "vram_mb": get_vram_mb(), "response_preview": full_response[:150], "content_chars": len(full_response), "reasoning_chars": reasoning_chars}


def stats(v):
    if not v:
        return None
    s = sorted(v)
    p = lambda q: round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 1)
    return {"avg": round(st.mean(v), 1), "p50": p(0.50), "p95": p(0.95), "min": round(min(v), 1), "max": round(max(v), 1), "n": len(v)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["P", "A1", "A2"])
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--questions", default=os.path.join(ROOT, "..", "benchmark", "questions.json"))  # Vol.1 題庫原位（sha256 見 results/e7/questions_source_sha256.txt）
    ap.add_argument("--prelaunch-ctx", required=True, help="啟動前桌面基線檔")
    ap.add_argument("--image", required=True)
    ap.add_argument("--index-digest", required=True)
    ap.add_argument("--manifest-digest", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--extra-env", default="")
    a = ap.parse_args()
    import urllib.request
    model = json.load(urllib.request.urlopen(a.base + "/v1/models", timeout=30))["data"][0]["id"]
    qs = json.load(open(a.questions, encoding="utf-8"))
    pre = open(a.prelaunch_ctx, encoding="utf-8").read().strip()
    mem = int(pre.split("|")[-1].split("MiB")[0].strip()) if "MiB" in pre else -1
    clean = mem >= 0 and mem < 1500
    started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    before = ctx(); rows = []
    url = a.base + "/v1/chat/completions"
    for rnd in range(1, ROUNDS + 1):
        for i, q in enumerate(qs):
            r = benchmark_nim(url, model, q["text"])
            r.update({"question_id": q["id"], "category": q["category"], "round": rnd})
            rows.append(r)
            time.sleep(COOLDOWN)
        done = [x for x in rows if "error" not in x]
        print(f"  round {rnd}/{ROUNDS} done · n={len(done)} · avg tps so far {st.mean([x['tps'] for x in done]):.1f}", flush=True)
    after = ctx()
    ok = [r for r in rows if "error" not in r]
    cats = sorted({q["category"] for q in qs})
    res = {"arm": a.arm, "model": model, "image": a.image, "image_index_digest": a.index_digest, "manifest_digest_amd64": a.manifest_digest,
           "profile": a.profile, "extra_env": a.extra_env, "n_requests": len(rows), "n_ok": len(ok), "n_error": len(rows) - len(ok),
           "harness": "逐字沿用 Vol.1 run_benchmark.py::benchmark_nim（tps=非空白片段/秒 ≈ token/秒）· max_tokens=500 · stream · 無 temperature · COOLDOWN 2s · 3 輪",
           "tps_words_per_s": stats([r["tps"] for r in ok]),
           "ttft_ms": stats([r["ttft_ms"] for r in ok if r["ttft_ms"] is not None]),
           "total_latency_ms": stats([r["total_latency_ms"] for r in ok]),
           "true_tps_tokens_per_s": stats([r["true_tps"] for r in ok if r.get("true_tps")]),
           "completion_tokens": stats([r["completion_tokens"] for r in ok if r.get("completion_tokens")]),
           "vram_mb_max": max((r["vram_mb"] for r in ok), default=None),
           "output_split": {"n_with_reasoning_field": sum(1 for r in ok if r.get("reasoning_chars")),
                            "content_chars": stats([r.get("content_chars", 0) for r in ok]),
                            "reasoning_chars": stats([r.get("reasoning_chars", 0) for r in ok]),
                            "n_content_has_think_tag": sum(1 for r in ok if "<think>" in r.get("response_preview", ""))},
           "per_category": {c: {"tps_avg": round(st.mean([r["tps"] for r in ok if r["category"] == c]), 1),
                                "ttft_avg_ms": round(st.mean([r["ttft_ms"] for r in ok if r["category"] == c and r["ttft_ms"] is not None]), 1),
                                "latency_avg_ms": round(st.mean([r["total_latency_ms"] for r in ok if r["category"] == c]), 1),
                                "n": sum(1 for r in ok if r["category"] == c)} for c in cats},
           "measurement_context": {"prelaunch": pre, "before": before, "after": after}, "clean_window_prelaunch": clean,
           "started": started, "finished": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    res["measurement_label"] = (f"{model} · {a.image} · index {a.index_digest[:19]}… · profile {a.profile[:12]}… · {a.extra_env} · "
                                f"RTX 5090 · driver 591.86 / CUDA 13.1 · Win11 + Docker Desktop(WSL2) · "
                                f"100Q × 3 輪 = {len(rows)} 請求 · max_tokens=500 · streaming · 無 temperature · COOLDOWN 2s · "
                                f"tps=非空白片段/秒（Vol.1 同式 · ≈token/秒）avg {res['tps_words_per_s']['avg']} (p50 {res['tps_words_per_s']['p50']}) · "
                                f"TTFT avg {res['ttft_ms']['avg']} ms (p50 {res['ttft_ms']['p50']}) · "
                                f"latency avg {res['total_latency_ms']['avg']} ms · VRAM max {res['vram_mb_max']} MB · "
                                f"clean_window_prelaunch={clean}")
    os.makedirs(os.path.join(ROOT, "results", "e7"), exist_ok=True)
    json.dump(res, open(os.path.join(ROOT, "results", "e7", f"e7_arm_{a.arm.lower()}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(os.path.join(ROOT, "results", "e7", f"e7_arm_{a.arm.lower()}.rows.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(res["measurement_label"])


if __name__ == "__main__":
    main()
