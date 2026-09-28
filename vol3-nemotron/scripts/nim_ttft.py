#!/usr/bin/env python3
"""NIM TTFT / throughput harness —— 換模型不換 harness。

區段頭尾各取一次 measurement_context；
        前後差 > 500 MiB 或 util > 20% ⇒ 標 context_unstable，數字仍記但不進對外素材。
A2 必須另外驗 kernel 路徑（見 --kernel-log），Marlin fallback 要標明。
紅線：任何離開本 repo 的數字必須帶量測邊界 ⇒ 程式生成 measurement_label，不手寫。
"""
import argparse, json, subprocess, sys, time, urllib.request, io, re

sys.stdout.reconfigure(encoding="utf-8")   # cp950 會把成功變成 exit 1（8/19 踩過）

SMI = ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,"
       "temperature.gpu,power.draw", "--format=csv,noheader"]

def ctx():
    out = subprocess.run(SMI, capture_output=True, text=True).stdout.strip()
    m = re.findall(r"[\d.]+", out)
    return {"raw": out,
            "memory_used_MiB": int(float(m[0])) if m else None,
            "utilization_pct": int(float(m[2])) if len(m) > 2 else None}

def stream_once(url, model, prompt, max_tokens):
    body = json.dumps({"model": model, "max_tokens": max_tokens, "stream": True,
                       "temperature": 0.0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter(); ttft = None; ntok = 0
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                break
            try:
                d = json.loads(payload)
            except Exception:
                continue
            delta = (d.get("choices") or [{}])[0].get("delta", {}).get("content")
            if delta:
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
                ntok += 1
    total = (time.perf_counter() - t0) * 1000
    return {"ttft_ms": None if ttft is None else round(ttft, 1),
            "total_ms": round(total, 1), "tokens": ntok,
            "tok_per_s": round(ntok / (total / 1000), 2) if total else None}

def kernel_path(container):
    """確認 kernel 路徑，不要只確認它起得來。"""
    log = subprocess.run(["docker", "logs", container], capture_output=True).stdout \
            .decode("utf-8", "replace")
    pat = re.compile(r"marlin|native support for FP4|quant_algo|W4A16|"
                     r"Selected .*Kernel|backend", re.I)
    hits = [l.strip() for l in log.splitlines() if pat.search(l)]
    marlin = any("marlin" in h.lower() or "native support for FP4" in h for h in hits)
    vllm = re.search(r"vllm[ =-]*v?(\d+\.\d+\.\d+[^\s,)]*)", log, re.I)
    blocks = re.search(r"num_gpu_blocks_override['\"]?[:=]\s*(\d+)", log)
    conc = re.search(r"Maximum concurrency for \d+ tokens per request: ([\d.]+x)", log)
    return {"matched_lines": hits[:40],
            "marlin_fallback_detected": marlin,
            "kernel_path": "Marlin W4A16 fallback（非原生 FP4）" if marlin else "未偵測到 fallback 警告",
            "vllm_version_from_log": vllm.group(1) if vllm else None,
            "num_gpu_blocks_override": int(blocks.group(1)) if blocks else None,
            "max_concurrency": conc.group(1) if conc else None}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--container", required=True)
    p.add_argument("--label", required=True, help="這組配置的識別名，進 measurement_label")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--max-tokens", type=int, default=64)
    p.add_argument("--prompt", required=True, help="prompt text; recorded implicitly via config label — no default in this repo")
    p.add_argument("--out", required=True)
    a = p.parse_args()

    models = json.load(urllib.request.urlopen(a.base + "/v1/models", timeout=30))
    model = models["data"][0]["id"]
    mmlen = models["data"][0].get("max_model_len")

    before = ctx()
    stream_once(a.base + "/v1/chat/completions", model, a.prompt, a.max_tokens)  # warmup, 不計
    runs = [stream_once(a.base + "/v1/chat/completions", model, a.prompt, a.max_tokens)
            for _ in range(a.runs)]
    # 沉降 3 秒再取 after —— 量測剛結束時 GPU 本來就在忙，直接取樣會把
    # 「量測自身的負載」當成「背景負載漂移」，於是每次成功量測都被標 unstable。
    # （2026-09-04 自陳缺陷：A2 attempt1 delta=0 MiB 卻判 unstable）
    time.sleep(3)
    after = ctx()

    ttfts = sorted(r["ttft_ms"] for r in runs if r["ttft_ms"] is not None)
    tps = sorted(r["tok_per_s"] for r in runs if r["tok_per_s"] is not None)
    med = lambda v: v[len(v) // 2] if v else None

    # 🔴 穩定性判定 —— 不穩不代表數字不記，代表不得進對外素材
    dmem = abs((after["memory_used_MiB"] or 0) - (before["memory_used_MiB"] or 0))
    _bu = before["utilization_pct"] or 0
    _au = after["utilization_pct"] or 0
    # 抓的是背景負載漂移，不是量測自身的負載
    unstable = dmem > 500 or _bu > 20 or _au > 20
    kp = kernel_path(a.container)

    res = {
        "config_label": a.label, "model": model, "max_model_len": mmlen,
        "runs": runs,
        "ttft_ms_p50": med(ttfts), "ttft_ms_min": ttfts[0] if ttfts else None,
        "ttft_ms_max": ttfts[-1] if ttfts else None,
        "ttft_ms_p95": (sorted(ttfts)[min(len(ttfts)-1, int(round(0.95*(len(ttfts)-1))))] if ttfts else None),  # p95 is reported alongside avg
        "tok_per_s_p50": med(tps), "tok_per_s_min": tps[0] if tps else None,
        "tok_per_s_max": tps[-1] if tps else None,
        "measurement_context": {"before": before, "after": after,
                                "delta_memory_MiB": dmem},
        "context_unstable": unstable,
        "kernel_verification": kp,
        "n": a.runs, "max_tokens": a.max_tokens, "warmup_discarded": 1,
        "clean_window": ((before["memory_used_MiB"] or 0) < 1500 and (before["utilization_pct"] or 0) < 5),  # clean-window criterion of that run
    }
    res["measurement_label"] = (
        f"{model} · config={a.label} · max_model_len={mmlen} · "
        f"num_gpu_blocks_override={kp['num_gpu_blocks_override']} · "
        f"max_concurrency={kp['max_concurrency']} · kernel_path={kp['kernel_path']} · "
        f"streaming · max_tokens={a.max_tokens} · warmup 1 不計 · n={a.runs} · "
        f"TTFT p50 {res['ttft_ms_p50']} ms (p95 {res['ttft_ms_p95']}) · {res['tok_per_s_p50']} tok/s · "
        f"context_unstable={unstable} · 非乾淨窗口"
    )
    # 引用閘：不穩 或 偵測到 Marlin fallback ⇒ 不可對外
    res["citable_external"] = False   # 非乾淨窗口，本階段一律 False
    res["citable_internal"] = not unstable

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(res["measurement_label"])
    print(f"context_unstable={unstable} (delta {dmem} MiB) · marlin_fallback="
          f"{kp['marlin_fallback_detected']} · out={a.out}")

if __name__ == "__main__":
    main()
