#!/usr/bin/env python3
"""Vol.1-A revisit, P59: what NIM is worth on this card once several people use it at the same time.

Llama 3.1 8B Instruct on one RTX 5090, five configurations, one engine on the card at a time, in this order:
  O-Q4      Ollama (Docker image), llama3.1:8b (the 4-bit default), OLLAMA_NUM_PARALLEL = the largest that loads 100% on GPU
  N-BF16    NIM 2.0.12, profile 092ed421 (bf16), as P54's arm N
  O-FP16    Ollama, llama3.1:8b-instruct-fp16, OLLAMA_NUM_PARALLEL = the largest that loads 100% on GPU
  N-FP8     NIM 2.0.12, profile c4789f7a (fp8, the profile NIM selects on this card when nothing is set)
  O-Q4-def  as O-Q4 with OLLAMA_NUM_PARALLEL not set (the value Ollama chooses is read from its log)
Every arm: context 8,192 set explicitly (Ollama OLLAMA_CONTEXT_LENGTH; NIM NIM_MAX_MODEL_LEN), endpoints on 127.0.0.1.

Per container, before any measured level:
  isolation   no other compute process on the GPU, port 8000 / 11434 held only by this arm, no Windows-native Ollama running
  residency   Ollama: `ollama ps` PROCESSOR = "100% GPU"; NIM: the startup log (profile, CUDA graph sizes captured)
  prefix-cache detector (P58 section 3-2): a positive control sends one ~3,500-token prompt twice (the second TTFT must
              drop if the engine reuses a cached prefix: the detector can fire), then two prompts of the calibration form,
              which differ from their first token on (the second must NOT drop). A drop there means the calibration
              would measure cache hits -> the arm stops, null.
  warm-up     a discarded 120 s AIPerf level at c=1 on its own seed (not the c=1 level's: P54's RAG profile hit the cache
              because the two shared a seed)
  calibration the harness's own client, 20 requests + 1 discarded, each prompt with its own leading nonce and a length at the
              profile's mean, new connection per request, tokens counted with the Llama 3.1 tokenizer from the streamed text
Levels 1, 8, 16, 32, 64, 128, 60 s each, AIPerf 0.11.0 closed loop, profiles C (200/200) and R (3,500/500) as
p53_concurrency, token counts from the client tokenizer (no --use-server-token-count: the Ollama and NIM usage fields are
not comparable), and the output cap sent as `max_tokens` on every arm (--use-legacy-max-tokens: Ollama 0.34.4 ignores the
`max_completion_tokens` field AIPerf sends by default, so without it the Ollama arms would generate to end-of-sequence). Per level, from AIPerf's per-request export (not kept): prompt tokens sent (client) against prompt tokens
the server reports it consumed (a server count below 98% of the client count on any request = silent truncation), and the
median completion tokens against the profile's target. A fresh container repeats the two highest levels of both profiles.
usage: p59_nim_value.py --out DIR --aiperf EXE --tokenizer DIR --store DIR [--arms a,b] [--test]
env: NGC_ENV_FILE (passed to --env-file of the NIM arms, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, re, statistics as st, subprocess, sys, time, uuid

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "vol2", "scripts"))
from p53_concurrency import PROFILE_ARGS, SUMMARY_KEYS  # noqa: E402

NIM_IMAGE = "nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12"
OLLAMA_IMAGE = "ollama/ollama:latest"
BASE = {"nim": "http://127.0.0.1:8000", "ollama": "http://127.0.0.1:11434"}
PORT = {"nim": 8000, "ollama": 11434}
CONTEXT = 8192
LEVELS = [1, 8, 16, 32, 64, 128]
PARALLEL_LADDER = [64, 32, 16, 8, 4, 2, 1]
NIM_ENV = {"NIM_MAX_MODEL_LEN": str(CONTEXT), "VLLM_USE_V2_MODEL_RUNNER": "0"}
ARMS = {
    "O-Q4":     {"kind": "ollama", "model": "llama3.1:8b", "parallel": "max"},
    "N-BF16":   {"kind": "nim", "profile": "092ed4213624e774d24cdaf84e3b6222839bab2008a21d3c214ab46626366f90"},
    "O-FP16":   {"kind": "ollama", "model": "llama3.1:8b-instruct-fp16", "parallel": "max"},
    "N-FP8":    {"kind": "nim", "profile": "c4789f7af56c770c1c88b73da666886365534d6980b6b922b41fd97036c77d73"},
    "O-Q4-def": {"kind": "ollama", "model": "llama3.1:8b", "parallel": None},
}
ORDER = ["O-Q4", "N-BF16", "O-FP16", "N-FP8", "O-Q4-def"]
OSL_TARGET = {"C": 200, "R": 500}
FILLER = "The quick brown fox jumps over the lazy dog."
CAL = {"C": {"reps": 18, "osl": 200}, "R": {"reps": 348, "osl": 500}}   # ~10.06 Llama tokens per repeat (harness test: 19 -> 211, 328 -> 3,301): ~200 and ~3,500, the profiles' means
CAL_N = 20   # measured calibration requests (+1 discarded): Ollama's TTFT is bimodal at c=1, 10 left its median unstable in the harness test
DROP = 0.70          # second/first TTFT below this = a cached prefix was reused
TRUNC = 0.98         # server prompt tokens below this share of the client count = truncated
SERVED = {"nim": "meta/llama-3.1-8b-instruct"}


def now():
    return subprocess.run(["date", "+%FT%T%z"], capture_output=True, text=True).stdout.strip()


def sh(args, timeout=120):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def gpu():
    r = sh(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits"], 30)
    u, ut, tp, p = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
    return {"used_mib": int(u), "util_pct": int(ut), "temp_c": int(tp), "power_w": float(p)}


def isolation(kind):
    apps = sh(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"], 30).stdout.strip()
    net = sh(["netstat", "-ano"], 60).stdout
    listen = sorted({l.split()[1] for l in net.splitlines() if "LISTEN" in l and re.search(r":(8000|11434)\s", l)})
    tl = sh(["tasklist"], 60).stdout
    native = sorted({l.split()[0] for l in tl.splitlines() if l.lower().startswith("ollama")})
    ps = sh(["docker", "ps", "--format", "{{.Names}}"], 30).stdout.split()
    return {"at": now(), "gpu_compute_apps": apps or "(none listed)", "listening_8000_11434": listen, "windows_native_ollama": native,
            "containers": ps, "pass": not native and len(ps) <= 1}


def tokenizer(path):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(path)


# ---------------------------------------------------------------- containers
def docker_logs(name):
    r = sh(["docker", "logs", name], 120)
    return r.stdout + r.stderr


def save_logs(name, logdir):
    L = docker_logs(name)
    lines = [l for l in L.splitlines() if "nvapi" not in l.lower()]
    open(os.path.join(logdir, f"{name}.log.txt"), "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    return len(lines)


def stop(name):
    sh(["docker", "rm", "-f", name], 120); time.sleep(5)


def start_ollama(name, store, parallel, logdir):
    env = {"OLLAMA_CONTEXT_LENGTH": str(CONTEXT)}
    if parallel is not None:
        env["OLLAMA_NUM_PARALLEL"] = str(parallel)
    cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "127.0.0.1:11434:11434", "-v", f"{store}:/root/.ollama"]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += [OLLAMA_IMAGE]
    t0 = time.time(); r = sh(cmd, 120)
    if r.returncode != 0:
        return {"ready": False, "env": env, "reason": r.stderr.strip()[:400], "seconds": round(time.time() - t0, 1)}
    while time.time() - t0 < 120:
        try:
            if requests.get(BASE["ollama"] + "/api/version", timeout=5).status_code == 200:
                return {"ready": True, "env": env, "version": requests.get(BASE["ollama"] + "/api/version", timeout=5).json().get("version"),
                        "seconds": round(time.time() - t0, 1)}
        except Exception:
            pass
        time.sleep(2)
    return {"ready": False, "env": env, "reason": "no /api/version within 120 s", "seconds": round(time.time() - t0, 1)}


def ollama_load(name, model):
    """Load the model (an empty generate request), then read `ollama ps` and the server log's view of the runner."""
    t0 = time.time()
    try:
        r = requests.post(BASE["ollama"] + "/api/generate", json={"model": model, "prompt": "", "stream": False}, timeout=900)
        status, body = r.status_code, r.text[:300]
    except Exception as e:
        status, body = None, str(e)[:300]
    ps = sh(["docker", "exec", name, "ollama", "ps"], 60).stdout
    row = next((l for l in ps.splitlines()[1:] if l.strip()), "")
    proc = re.search(r"(\d+%\s*GPU|\d+%/\d+%\s*CPU/GPU|\d+%\s*CPU)", row)
    L = docker_logs(name)
    par = [int(x) for x in re.findall(r"--parallel (\d+)", L)] + [int(x) for x in re.findall(r"n_seq_max\s*=\s*(\d+)", L)]
    ctx = [int(x) for x in re.findall(r"--ctx-size (\d+)", L)] + [int(x) for x in re.findall(r"llama_context: n_ctx\s*=\s*(\d+)", L)]
    err = next((l.strip()[:300] for l in L.splitlines() if re.search(r"error|out of memory|failed", l, re.I) and "level=INFO" not in l), None)
    return {"http_status": status, "body_head": body if status != 200 else None, "seconds": round(time.time() - t0, 1),
            "ollama_ps": row.strip(), "processor": proc.group(1) if proc else None,
            "full_gpu": bool(proc and re.fullmatch(r"100%\s*GPU", proc.group(1))),
            "runner_parallel_from_log": par[-1] if par else None, "runner_ctx_from_log": ctx[-1] if ctx else None,
            "first_error_line": err}


def fit_ollama(arm, store, logdir, events, ctx_note=""):
    """Walk the pre-registered NUM_PARALLEL ladder until a start loads 100% on GPU; return (name, parallel, load) of the
    passing container, left running, or (None, None, None)."""
    a = ARMS[arm]
    ladder = PARALLEL_LADDER if a["parallel"] == "max" else [None]
    for k, par in enumerate(ladder):
        name = f"p59-{arm.lower()}-p{par if par is not None else 'def'}{ctx_note}"
        st_ = start_ollama(name, store, par, logdir)
        load = ollama_load(name, a["model"]) if st_["ready"] else None
        ok = bool(st_["ready"] and load and load["http_status"] == 200 and load["full_gpu"])
        events.write(json.dumps({"kind": "ollama_fit", "arm": arm, "step": k, "at": now(), "num_parallel_set": par, "context": CONTEXT,
                                 "start": st_, "load": load, "pass": ok}, ensure_ascii=False) + "\n"); events.flush()
        print(f"  {arm} NUM_PARALLEL {par}: ready={st_['ready']} load={load and load['http_status']} {load and load['processor']} -> {'PASS' if ok else 'fail'}", flush=True)
        if ok:
            return name, par, load, st_
        save_logs(name, logdir); stop(name)
    return None, None, None, None


def start_nim(arm, name, logdir):
    sys.path.insert(0, os.path.join(REPO, "vol2", "scripts"))
    import p54_engine as E
    env = {"NIM_MODEL_PROFILE": ARMS[arm]["profile"], **NIM_ENV}
    st_ = E.launch("N", name, env, [], logdir)
    return st_


def nim_profile_readback(logdir, name):
    p = os.path.join(logdir, f"{name}.startup.log.txt")
    L = open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else ""
    prof = re.findall(r"[0-9a-f]{64}", L)
    cap = {k: int(n) for k, n, _ in re.findall(r"Capturing CUDA graphs \(([^)]*)\):\s*100%\S*\s*(\d+)/(\d+)", L)}
    return {"profile_ids_in_log": sorted(set(prof))[:4], "captured_graph_sizes": cap}


# ---------------------------------------------------------------- client measurements (own client, fresh connection)
def stream_once(kind, model, text, max_tokens, tok):
    import http.client, socket, urllib.parse
    u = urllib.parse.urlparse(BASE[kind])
    payload = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens, "temperature": 0.0,
               "stream": True, "stream_options": {"include_usage": True}}
    body = json.dumps(payload).encode("utf-8")
    t0 = time.perf_counter(); first = None; out = ""; usage = None; status = None; err = None; buf = b""; conn = None
    try:
        conn = http.client.HTTPConnection(u.hostname, u.port, timeout=900); conn.connect()
        conn.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.request("POST", "/v1/chat/completions", body=body, headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
        resp = conn.getresponse(); status = resp.status
        while True:
            data = resp.read1(65536)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1); line = line.strip()
                if line.startswith(b"data: ") and line != b"data: [DONE]":
                    try:
                        c = json.loads(line[6:].decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if c.get("usage"):
                        usage = c["usage"]
                    for ch in c.get("choices") or []:
                        d = (ch.get("delta") or {}).get("content") or ""
                        if d:
                            if first is None:
                                first = time.perf_counter()
                            out += d
    except Exception as e:
        err = str(e)[:300]
    finally:
        if conn is not None:
            conn.close()
    t1 = time.perf_counter()
    ct = len(tok.encode(out, add_special_tokens=False)) if out else 0
    pt = len(tok.encode(text, add_special_tokens=False))
    return {"http_status": status, "error": err, "ttft_ms": round((first - t0) * 1000, 2) if first else None, "e2e_ms": round((t1 - t0) * 1000, 2),
            "client_prompt_tokens": pt, "client_completion_tokens": ct, "server_prompt_tokens": (usage or {}).get("prompt_tokens"),
            "server_completion_tokens": (usage or {}).get("completion_tokens"),
            "itl_ms": round(((t1 - first) * 1000) / (ct - 1), 3) if first and ct > 1 else None}


def nonce_prompt(prof):
    return f"Session {uuid.uuid4().hex}. " + " ".join([FILLER] * CAL[prof]["reps"])


def prefix_detector(kind, model, tok):
    stream_once(kind, model, nonce_prompt("R"), 16, tok)   # discarded: the first long prefill after load is slow for other reasons
    same = nonce_prompt("R")
    a1 = stream_once(kind, model, same, 16, tok); a2 = stream_once(kind, model, same, 16, tok)
    b1 = stream_once(kind, model, nonce_prompt("R"), 16, tok); b2 = stream_once(kind, model, nonce_prompt("R"), 16, tok)
    r_ctl = (a2["ttft_ms"] / a1["ttft_ms"]) if a1["ttft_ms"] and a2["ttft_ms"] else None
    r_cal = (b2["ttft_ms"] / b1["ttft_ms"]) if b1["ttft_ms"] and b2["ttft_ms"] else None
    return {"positive_control_same_prompt_twice": {"ttft_ms": [a1["ttft_ms"], a2["ttft_ms"]], "ratio": r_ctl, "fired": r_ctl is not None and r_ctl < DROP},
            "calibration_form_two_prompts": {"ttft_ms": [b1["ttft_ms"], b2["ttft_ms"]], "ratio": r_cal},
            "pass": r_cal is not None and r_cal >= DROP}


def calibrate(kind, model, prof, tok):
    rows = [dict(stream_once(kind, model, nonce_prompt(prof), CAL[prof]["osl"], tok), i=i, warmup=(i == 0)) for i in range(CAL_N + 1)]
    ok = [r for r in rows if not r["warmup"] and r["ttft_ms"] and r["itl_ms"]]
    return {"profile": prof, "rows": rows, "n_ok": len(ok),
            "ttft_ms_p50": round(st.median(r["ttft_ms"] for r in ok), 2) if ok else None,
            "itl_ms_p50": round(st.median(r["itl_ms"] for r in ok), 3) if ok else None,
            "client_prompt_tokens_p50": st.median(r["client_prompt_tokens"] for r in ok) if ok else None}


def engine_alive(kind, model):
    try:
        r = requests.post(BASE[kind] + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1, "stream": False}, timeout=180)
        return {"alive": r.status_code == 200, "http_status": r.status_code, "body_head": r.text[:200]}
    except Exception as e:
        return {"alive": False, "http_status": None, "body_head": str(e)[:200]}


# ---------------------------------------------------------------- AIPerf levels
def aiperf_cmd(a, kind, model, prof, n, dur, art, seed):
    return [a.aiperf, "profile", "-m", model, "--endpoint-type", "chat", "--streaming", "-u", BASE[kind], "--tokenizer", a.tokenizer,
            *PROFILE_ARGS[prof], "--extra-inputs", "temperature:0", "--use-legacy-max-tokens", "--concurrency", str(n), "--warmup-request-count", str(n),
            "--benchmark-duration", str(dur), "--benchmark-grace-period", "0", "--no-gpu-telemetry", "--ui-type", "none",
            "--random-seed", str(seed), "--artifact-dir", art]


def per_request_checks(art, prof):
    """From AIPerf's per-request export: client vs server prompt tokens (truncation) and completion tokens."""
    p = os.path.join(art, "profile_export.jsonl")
    if not os.path.exists(p):
        return None
    ratios, osl, n, no_usage = [], [], 0, 0
    for l in open(p, encoding="utf-8"):
        r = json.loads(l); m = r.get("metrics") or {}
        if (r.get("metadata") or {}).get("benchmark_phase") != "profiling" or r.get("error"):
            continue
        n += 1
        isl = (m.get("input_sequence_length") or {}).get("value"); up = (m.get("usage_prompt_tokens") or {}).get("value")
        o = (m.get("output_sequence_length") or {}).get("value")
        if o is not None:
            osl.append(o)
        if isl and up:
            ratios.append(up / isl)
        else:
            no_usage += 1
    return {"requests": n, "server_over_client_prompt_min": round(min(ratios), 4) if ratios else None,
            "server_over_client_prompt_p50": round(st.median(ratios), 4) if ratios else None,
            "requests_without_server_prompt_count": no_usage,
            "truncated_requests": sum(1 for x in ratios if x < TRUNC),
            "completion_tokens_p50": st.median(osl) if osl else None, "completion_target": OSL_TARGET[prof],
            "completion_below_90pct_of_target": (st.median(osl) < 0.9 * OSL_TARGET[prof]) if osl else None}


def run_level(a, arm, kind, model, prof, n, dur, art, tag, log, seed, extra):
    os.makedirs(os.path.dirname(art), exist_ok=True)
    cmd = aiperf_cmd(a, kind, model, prof, n, dur, art, seed)
    rec = {"arm": arm, "profile": prof, "container": tag, "concurrency": n, "duration_s": dur, "seed": seed, "start": now(), "gpu_start": gpu(), "command": cmd, **extra}
    print(f"  {arm} {prof} {tag} c={n}{' (warm-up, discarded)' if extra.get('warmup') else ''}", flush=True)
    with open(art + "_console.txt", "w", encoding="utf-8") as con:
        rc = subprocess.run(cmd, stdout=con, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}).returncode
    rec.update({"rc": rc, "end": now(), "gpu_end": gpu()})
    summ = os.path.join(art, "profile_export_aiperf.json")
    if rc == 0 and os.path.exists(summ):
        s = json.load(open(summ, encoding="utf-8"))
        rec["summary"] = {k: s.get(k) for k in SUMMARY_KEYS}
        rec["error_summary"] = s.get("error_summary"); rec["aiperf_version"] = s.get("aiperf_version")
        rec["completed"] = (s.get("request_count") or {}).get("avg")
    rec["checks"] = per_request_checks(art, prof)
    errs = ((rec.get("summary") or {}).get("error_request_count") or {}).get("avg")
    rec["engine_after"] = engine_alive(kind, model) if (rc != 0 or not rec.get("summary") or errs) else {"alive": True, "checked": False}
    rec["engine_dead"] = not rec["engine_after"]["alive"]
    log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
    s = rec.get("summary") or {}
    print(f"     rc={rc} completed={rec.get('completed')} tps={(s.get('output_token_throughput') or {}).get('avg')} "
          f"ttft_p99={(s.get('time_to_first_token') or {}).get('p99')} checks={rec['checks'] and {k: rec['checks'][k] for k in ('truncated_requests', 'completion_tokens_p50')}} dead={rec['engine_dead']}", flush=True)
    time.sleep(5)
    return rec


def sweep(a, arm, kind, model, prof, levels, tag, log, out, dur):
    for n in levels:
        rec = run_level(a, arm, kind, model, prof, n, dur, os.path.join(out, f"{arm}_{prof}_{tag}", f"c{n:04d}"), tag, log, 20260925 + n, {})
        if rec["engine_dead"]:
            log.write(json.dumps({"arm": arm, "profile": prof, "container": tag, "skipped_levels": levels[levels.index(n) + 1:], "reason": f"engine dead after c={n}", "at": now()}) + "\n"); log.flush()
            return False
    return True


# ---------------------------------------------------------------- one container: detector, warm-up, calibration, sweeps
def measure(a, arm, kind, model, name, tag, levels, log, ev, tok, logdir, extra_start):
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": now()}, ensure_ascii=False) + "\n"), ev.flush())
    iso = isolation(kind)
    det = prefix_detector(kind, model, tok)
    event(kind="container_start", arm=arm, container=tag, name=name, model=model, isolation=iso, prefix_detector=det, gpu_ready=gpu(), **extra_start)
    print(f"  {arm} {tag}: isolation={iso['pass']} detector pass={det['pass']} (control fired={det['positive_control_same_prompt_twice']['fired']})", flush=True)
    if not det["pass"] or not iso["pass"]:
        event(kind="container_refused", arm=arm, container=tag, reason="prefix-cache detector failed" if not det["pass"] else "isolation failed")
        return
    for prof in ("C", "R"):
        warm = run_level(a, arm, kind, model, prof, 1, 20 if a.test else 120, os.path.join(a.out, f"{arm}_{prof}_{tag}", "warmup", "c0001"), tag, log, 20260925 + 9000, {"warmup": True})
        cal = calibrate(kind, model, prof, tok) if tag == "main" else None
        event(kind="profile_start", arm=arm, profile=prof, container=tag, calibration=cal, warmup_level={k: warm.get(k) for k in ("rc", "completed", "engine_dead")})
        if warm["engine_dead"] or not sweep(a, arm, kind, model, prof, levels, tag, log, a.out, 20 if a.test else 60):
            break


def run_arm(a, arm, tok, log, ev, logdir):
    kind = ARMS[arm]["kind"]
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": now()}, ensure_ascii=False) + "\n"), ev.flush())
    levels = [1, 8] if a.test else LEVELS
    for tag in (("main",) if a.test else ("main", "fresh")):
        lv = levels if tag == "main" else levels[-2:]
        if kind == "ollama":
            if tag == "main":
                name, par, load, st_ = fit_ollama(arm, a.store, logdir, ev)
                if name is None:
                    event(kind="arm_null", arm=arm, reason="no NUM_PARALLEL on the ladder loaded 100% on GPU at context 8192"); return
                ARMS[arm]["fit_parallel"] = par
            else:
                par = ARMS[arm].get("fit_parallel")
                name = f"p59-{arm.lower()}-fresh"
                st_ = start_ollama(name, a.store, par, logdir)
                load = ollama_load(name, ARMS[arm]["model"]) if st_["ready"] else None
                if not (load and load["full_gpu"]):
                    event(kind="container_failed", arm=arm, container=tag, start=st_, load=load); save_logs(name, logdir); stop(name); continue
            model = ARMS[arm]["model"]
            extra = {"image": OLLAMA_IMAGE, "ollama_version": st_.get("version"), "env": st_["env"], "load": load}
        else:
            name = f"p59-{arm.lower()}-{tag}"
            st_ = start_nim(arm, name, logdir)
            if not st_["ready"]:
                event(kind="container_failed", arm=arm, container=tag, reason=st_.get("reason"), first_error_line=st_.get("first_error_line"))
                save_logs(name, logdir); stop(name); continue
            time.sleep(5)
            model = requests.get(BASE["nim"] + "/v1/models", timeout=30).json()["data"][0]["id"]
            extra = {"image": NIM_IMAGE, "env": st_["env"], "seconds_to_ready": st_["seconds_to_verdict"], "readback": nim_profile_readback(logdir, name),
                     "captured_graph_sizes": st_.get("captured_graph_sizes")}
        measure(a, arm, kind, model, name, tag, lv, log, ev, tok, logdir, extra)
        save_logs(name, logdir); stop(name)
        event(kind="container_end", arm=arm, container=tag, gpu_after_stop=gpu())


def fit_only_4096(a, arm, ev, logdir):
    """Section 3 branch: the largest NUM_PARALLEL that loads 100% on GPU at context 4,096 (reported beside the 8,192 value)."""
    global CONTEXT
    saved = CONTEXT; CONTEXT = 4096
    try:
        name, par, load, st_ = fit_ollama(arm, a.store, logdir, ev, ctx_note="-ctx4096")
        ev.write(json.dumps({"kind": "ollama_fit_4096_result", "arm": arm, "at": now(), "num_parallel": par, "load": load}, ensure_ascii=False) + "\n"); ev.flush()
        if name:
            save_logs(name, logdir); stop(name)
    finally:
        CONTEXT = saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--store", required=True); ap.add_argument("--arms", default=",".join(ORDER)); ap.add_argument("--test", action="store_true")
    ap.add_argument("--skip-4096", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    if sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    tok = tokenizer(a.tokenizer)
    for arm in a.arms.split(","):
        print(f"##### arm {arm} {now()}", flush=True)
        run_arm(a, arm, tok, log, ev, logdir)
        if ARMS[arm]["kind"] == "ollama" and ARMS[arm]["parallel"] == "max" and not a.test and not a.skip_4096:
            fit_only_4096(a, arm, ev, logdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
