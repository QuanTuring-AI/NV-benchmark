#!/usr/bin/env python3
"""Vol.2 footprint decomposition: what each model needs on one GPU, measured by shrinking the engine's memory budget.

`NIM_KVCACHE_PERCENT` is the NIM environment variable that both images map to vLLM `gpu_memory_utilization`: the share
of the card the engine may use for weights, activations and KV cache. For each arm this script
  1. starts the container as the earlier E7 run did (no budget override) and records the level at READY  -> "default"
  2. then restarts it with the budget stepped down (0.85, 0.80, ... in steps of 0.05) until a start fails or the
     probe fails, then tries once at the last passing value minus 0.025.
vLLM refuses to start when the KV cache that fits inside the budget cannot hold `NIM_MAX_MODEL_LEN` tokens; that
refusal is the physical lower bound, and the probe (three short factual questions that must end with finish_reason
"stop") guards against a start that cannot serve. The smallest passing budget is the model's minimum on this card
at that context length, to the resolution of the sweep.
Every start records: memory in use before launch and at READY (nvidia-smi), the engine's own cache_config_info from
/metrics (gpu_memory_utilization, num_gpu_blocks, block_size), the startup log's memory lines (clamping, model
loading, GPU KV cache size, maximum concurrency), and the failure text when a start fails.
Rows are appended to configs.jsonl as they complete. No response text is stored.
usage: p50_footprint.py --arm A1|A2|A2FP8 --out DIR [--only-default]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, hashlib, json, os, re, subprocess, sys, time

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
QFILE = os.path.join(REPO, "benchmark", "questions.json")
BASE = "http://localhost:8000"
PROBE_IDS = ["q001", "q004", "q011"]
PROBE_MAX_TOKENS = 1024
# Both Nemotron families reason by default and do not stop within a short budget even on a one-line factual question
# (harness test 2026-09-21: A1 hit max_tokens on all three probes). The probe asks for a direct answer with the
# "/no_think" system message both families document, so that "finish_reason == stop" measures serving, not reasoning length.
PROBE_SYSTEM = "/no_think"
SWEEP = [0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40, 0.35, 0.30]
READY_TIMEOUT_S = 1200
ARMS = {
    "A1": {"image": "nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2:1.12.2",
           "index_digest": "sha256:a2f4a5aefe7dd0ff29bfd8d7081ce4977337d1b12081361af7b6283ff9a406b2",
           "profile": "5cf34bab34141258d0cc836c66684642d3e3f32b4daaa2008e48bd289d6bc84b", "precision": "bf16",
           "env": {"NIM_MAX_MODEL_LEN": "4096", "NIM_MAX_NUM_SEQS": "32"}},
    "A2": {"image": "nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12",
           "index_digest": "sha256:bd38d2d5438950b49427ee41944ee04f84cd38383265add8df2230480539e6f9",
           "profile": "1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada", "precision": "nvfp4",
           "env": {"NIM_MAX_MODEL_LEN": "4096"}},
    "A2FP8": {"image": "nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12",
              "index_digest": "sha256:bd38d2d5438950b49427ee41944ee04f84cd38383265add8df2230480539e6f9",
              "profile": "8c91cce84b9b032ff4af489cb1a20395e223af35623010df9155390ab2284b7a", "precision": "fp8",
              "env": {"NIM_MAX_MODEL_LEN": "4096"}},
}


def now():
    return subprocess.run(["date", "+%FT%T%z"], capture_output=True, text=True).stdout.strip()


def gpu():
    r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw",
                        "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
    u, t, ut, tp, p = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
    return {"used_mib": int(u), "total_mib": int(t), "util_pct": int(ut), "temp_c": int(tp), "power_w": float(p)}


def sh(args, timeout=60):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def docker_logs(name):
    return sh(["docker", "logs", name], timeout=60).stdout + sh(["docker", "logs", name], timeout=60).stderr


LOG_PATTERNS = {
    "clamp": r"clamping gpu_memory_utilization[^\n]*|gpu_memory_utilization=\d+\.\d+ \(no clamping applied\)",
    "model_loading": r"Model loading took [^\n]*|Loading model weights took [^\n]*|Loading weights took [^\n]*",
    "kv_cache_size": r"GPU KV cache size: [^\n]*",
    "max_concurrency": r"Maximum concurrency for [^\n]*",
    "kv_refusal": r"[^\n]*larger than the maximum number of tokens that can be stored in KV cache[^\n]*",
    "oom": r"[^\n]*(OutOfMemory|out of memory|No available memory)[^\n]*",
}


LOG_PATTERNS["gmu"] = r"gpu_memory_utilization[=: ]+\d+\.\d+"


def kv_tokens_from_log(text, max_model_len):
    """NIM 1.12.2 exposes no cache_config_info on /metrics; vLLM logs 'Maximum concurrency for N tokens per request: Kx',
    where K = KV tokens / N. Returns the derived KV token count, or None."""
    m = re.search(r"Maximum concurrency for (\d[\d,]*) tokens per request: ([\d.]+)x", text)
    if not m:
        return None
    return int(round(float(m.group(2)) * int(m.group(1).replace(",", ""))))


def log_lines(text):
    return {k: sorted(set(m.strip() for m in re.findall(p, text)))[:3] for k, p in LOG_PATTERNS.items()}


def metrics_cache_config():
    try:
        t = requests.get(BASE + "/metrics", timeout=20).text
    except Exception as e:
        return {"error": str(e)}
    m = re.search(r"vllm:cache_config_info\{([^}]*)\}", t)
    if not m:
        return {"present": False}
    kv = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    out = {"present": True, "gpu_memory_utilization": kv.get("gpu_memory_utilization"),
           "num_gpu_blocks": kv.get("num_gpu_blocks"), "block_size": kv.get("block_size"),
           "kv_cache_dtype": kv.get("cache_dtype"), "max_model_len": kv.get("max_model_len")}
    try:
        out["kv_tokens"] = int(kv["num_gpu_blocks"]) * int(kv["block_size"])
    except (KeyError, ValueError, TypeError):
        out["kv_tokens"] = None
    return out


def probe(model, questions):
    rows = []
    for q in questions:
        payload = {"model": model, "messages": [{"role": "system", "content": PROBE_SYSTEM}, {"role": "user", "content": q["text"]}],
                   "max_tokens": PROBE_MAX_TOKENS,
                   "temperature": 0.0, "top_p": 0.9, "stream": True, "stream_options": {"include_usage": True}}
        t0 = time.perf_counter(); first = None; full = ""; finish = None; usage = None; status = None; err = None
        try:
            r = requests.post(BASE + "/v1/chat/completions", json=payload, stream=True, timeout=300)
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
                        full += d
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
        except Exception as e:
            err = str(e)
        t1 = time.perf_counter()
        rows.append({"question_id": q["id"], "http_status": status, "error": err, "finish_reason": finish,
                     "completion_tokens": (usage or {}).get("completion_tokens"), "prompt_tokens": (usage or {}).get("prompt_tokens"),
                     "usage_present": usage is not None, "ttft_ms": round((first - t0) * 1000, 1) if first else None,
                     "total_ms": round((t1 - t0) * 1000, 1), "response_chars": len(full),
                     "response_sha256": hashlib.sha256(full.encode("utf-8")).hexdigest(),
                     "words": len(full.split())})
    viable = all(r["http_status"] == 200 and r["error"] is None and r["finish_reason"] == "stop" for r in rows)
    return rows, viable


def start(arm, name, pct, logdir):
    a = ARMS[arm]
    env = dict(a["env"])
    if pct is not None:
        env["NIM_KVCACHE_PERCENT"] = f"{pct:.3f}"
    cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "8000:8000", "--env-file", os.environ["NGC_ENV_FILE"],
           "-e", f"NIM_MODEL_PROFILE={a['profile']}"]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += ["-v", f"{os.environ['NIM_CACHE_DIR']}:/opt/nim/.cache", a["image"]]
    t_launch = time.time()
    r = sh(cmd, timeout=120)
    if r.returncode != 0:
        return {"ready": False, "reason": "docker run failed", "stderr": r.stderr[-800:], "env": env}
    ready = False; reason = None
    while time.time() - t_launch < READY_TIMEOUT_S:
        L = docker_logs(name)
        if re.search(r"Uvicorn running|Application startup complete", L):
            ready = True; break
        if re.search(LOG_PATTERNS["kv_refusal"], L):
            reason = "engine refused: KV cache within the budget cannot hold NIM_MAX_MODEL_LEN"; break
        if re.search(LOG_PATTERNS["oom"], L) or "Traceback" in L:
            reason = "startup error (see log)"
        if not sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=30).stdout.strip():
            reason = reason or "container exited"; break
        time.sleep(10)
    L = docker_logs(name)
    open(os.path.join(logdir, f"{name}.startup.log.txt"), "w", encoding="utf-8", newline="\n").write(L)
    if not ready:
        return {"ready": False, "reason": reason or f"not ready within {READY_TIMEOUT_S}s", "env": env,
                "log_lines": log_lines(L), "seconds_to_verdict": round(time.time() - t_launch, 1)}
    return {"ready": True, "env": env, "log_lines": log_lines(L), "seconds_to_ready": round(time.time() - t_launch, 1),
            "kv_tokens_from_log": kv_tokens_from_log(L, int(env.get("NIM_MAX_MODEL_LEN", "0") or 0))}


def stop(name):
    sh(["docker", "rm", "-f", name], timeout=120)
    time.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=list(ARMS), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only-default", action="store_true")
    a = ap.parse_args()
    arm = ARMS[a.arm]
    os.makedirs(a.out, exist_ok=True)
    logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    rows_f = open(os.path.join(a.out, "configs.jsonl"), "a", encoding="utf-8", newline="\n")
    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    dig = sh(["docker", "image", "inspect", arm["image"], "--format", "{{join .RepoDigests \" \"}}"], timeout=30).stdout
    if arm["index_digest"].split(":")[1] not in dig:
        sys.exit(f"INDEX-DIGEST-MISMATCH for {arm['image']}: {dig.strip()}")
    bank = {q["id"]: q for q in json.load(open(QFILE, encoding="utf-8"))}
    questions = [bank[i] for i in PROBE_IDS]

    def one(label, pct):
        name = f"p50-{a.arm.lower()}-{label}".replace(".", "p")
        before = gpu(); t_before = now()
        s = start(a.arm, name, pct, logdir)
        row = {"arm": a.arm, "image": arm["image"], "profile": arm["profile"], "precision": arm["precision"], "label": label,
               "kvcache_percent": pct, "at": t_before, "gpu_before": before, "start": s}
        if s["ready"]:
            time.sleep(5)
            row["gpu_ready"] = gpu()
            row["cache_config"] = metrics_cache_config()
            if row["cache_config"].get("kv_tokens") is None and s.get("kv_tokens_from_log"):
                row["cache_config"]["kv_tokens"] = s["kv_tokens_from_log"]
                row["cache_config"]["kv_tokens_source"] = "log: Maximum concurrency x NIM_MAX_MODEL_LEN"
            elif row["cache_config"].get("kv_tokens") is not None:
                row["cache_config"]["kv_tokens_source"] = "metrics: num_gpu_blocks x block_size"
            try:
                row["served_model"] = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
            except Exception as e:
                row["served_model"] = None; row["models_error"] = str(e)
            rows, viable = probe(row["served_model"] or "", questions)
            row["probe"] = rows; row["viable"] = viable
            row["gpu_after_probe"] = gpu()
        else:
            row["viable"] = False
        stop(name)
        row["gpu_after_stop"] = gpu()
        rows_f.write(json.dumps(row, ensure_ascii=False) + "\n"); rows_f.flush()
        print(f"  {a.arm} {label:10s} pct={pct} ready={s['ready']} viable={row['viable']} "
              f"ready_used={row.get('gpu_ready', {}).get('used_mib')} kv_tokens={row.get('cache_config', {}).get('kv_tokens')} "
              f"{s.get('reason', '')}", flush=True)
        return row

    one("default", None)
    if a.only_default:
        return 0
    last_pass = None
    for pct in SWEEP:
        r = one(f"pct{pct:.2f}", pct)
        if r["viable"]:
            last_pass = pct
        else:
            if last_pass is not None:
                one(f"pct{last_pass - 0.025:.3f}", round(last_pass - 0.025, 3))
            break
    else:
        print(f"  {a.arm}: no failure down to {SWEEP[-1]} -- lower bound not reached", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
