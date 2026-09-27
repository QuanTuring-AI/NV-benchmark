#!/usr/bin/env python3
"""Vol.2 concurrency, second run (v2): the v1 sweeps with the instrument gate repaired. v1 (p53_concurrency.py, results in
results/p53_concurrency/) is kept byte for byte and its conclusions are null under its own frozen rules; this file is a
separate harness so that v1's pre-registration still describes the file it hashed.

What v2 changes, and why (each from a v1 observation, see results/p53_concurrency/README.md):
  1. Calibration after a warm-up level. In v1 the calibration ran first after READY and, on A2, per-token time fell
     from 5.2 to 4.3 ms over its ten requests while AIPerf's c=1 level a minute later measured 3.7 ms: the NVFP4 MoE
     engine is still tuning kernels for the first minute of traffic. v2 runs a discarded 120 s AIPerf level at c=1
     first (artifact kept under warmup/; 120 s because the slow phase lasted more than 45 s in two long-context
     harness tests the same morning), then the calibration, then the sweep.
  2. Calibration prompt matched to the profile. v1 calibrated with a ~200-token prompt on both profiles and compared
     it with AIPerf's c=1 TTFT on the R profile's 3,500-token prompts (339 vs 57 ms: a comparison of two prompt
     lengths, not two instruments). v2 builds the calibration prompt from the profile's ISL and uses the profile's OSL.
  3. Engine death is a ceiling, not a broken level. In v1 A1's engine died at c=32 (IndexError in the Mamba constant-
     size cache) and every later level of that sweep measured a dead server. v2 checks the server after any level with
     errors; if the engine is dead the level is marked engine_dead, the remaining levels are skipped, and the analysis
     treats the crash level as the ceiling with the levels below it intact.
  4. Container logs are saved before the container is removed (v1's stop() lost the crash traceback of the first
     container that died; the traceback quoted in the v1 README was captured by hand from a later container).
Everything else -- images, profiles, env, levels, durations, AIPerf flags, fresh-container repeat -- is v1's, imported.
usage: p53_concurrency_v2.py --out DIR --aiperf EXE --tokenizer-root DIR [--levels 1,2,4,8,16,32,64] [--test] [--arms A1,A2] [--profiles C,R]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, re, statistics as st, subprocess, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
from p53_concurrency import CONC_ENV, PROFILE_ARGS, SUMMARY_KEYS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CAL_N = 10
FILLER = "The quick brown fox jumps over the lazy dog."      # about 10 tokens on both tokenizers
CAL = {"C": {"reps": 19, "osl": 200}, "R": {"reps": 328, "osl": 500}}   # 10.7 tokens per repeat measured in the harness test (22 repeats -> 235 prompt tokens): 19 -> ~203, 328 -> ~3,500; OSL = the profile's OSL mean
CAL_PROMPT = {p: " ".join([FILLER] * v["reps"]) for p, v in CAL.items()}


def engine_alive(model):
    """A one-token non-streamed request: 200 means the engine serves; the v1 crash answered 500 with 'Engine loop is not running'."""
    try:
        r = requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1, "stream": False}, timeout=120)
        return {"alive": r.status_code == 200, "http_status": r.status_code, "body_head": r.text[:300]}
    except Exception as e:
        return {"alive": False, "http_status": None, "body_head": str(e)[:300]}


def save_logs(name, logdir):
    """docker logs of the container, trimmed: first 400 lines, 120 lines around the first Traceback, last 400 lines."""
    p = sh(["docker", "logs", name], timeout=300)
    lines = (p.stdout + p.stderr).splitlines()
    keep = lines[:400]
    tb = next((i for i, l in enumerate(lines) if "Traceback" in l or "Engine loop is not running" in l), None)
    if tb is not None and tb > 400:
        keep += ["", f"... {tb - 400} lines omitted ...", ""] + lines[max(400, tb - 20):tb + 100]
    if len(lines) > 800:
        keep += ["", f"... total {len(lines)} lines; last 400 follow ...", ""] + lines[-400:]
    txt = "\n".join(l for l in keep if "nvapi" not in l.lower())
    open(os.path.join(logdir, f"{name}.container.log.txt"), "w", encoding="utf-8", newline="\n", errors="replace").write(txt + "\n")
    return {"lines_total": len(lines), "first_traceback_line": tb}


def calibrate(model, prof):
    """One discarded warm-up request, then CAL_N streamed requests at concurrency 1 through this script's own client,
    each on a new TCP connection, prompt of about the profile's ISL, max_tokens = the profile's OSL, ignore_eos.
    TTFT = arrival of the first streamed chunk carrying a choice; ITL = (e2e - TTFT) / (completion_tokens - 1).
    A new connection per request because on this host a reused connection adds ~45 ms to the first chunk (v1 README).
    Requests are back to back (closed loop at concurrency 1, AIPerf's load pattern): on A2, requests 2 s apart ran 5-8%
    slower than back-to-back ones (150-185 W against 340-355 W at the same SM clock; clock diagnosis of 2026-09-23)."""
    import http.client, socket, urllib.parse
    u = urllib.parse.urlparse(BASE)
    rows = []
    for i in range(CAL_N + 1):
        payload = {"model": model, "messages": [{"role": "user", "content": CAL_PROMPT[prof] + f" ({i})"}], "max_tokens": CAL[prof]["osl"],
                   "temperature": 0.0, "stream": True, "ignore_eos": True, "stream_options": {"include_usage": True}}
        body = json.dumps(payload).encode("utf-8")
        t0 = time.perf_counter(); first = None; usage = None; status = None; err = None; buf = b""; conn = None
        try:
            conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=600); conn.connect()
            conn.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.request("POST", "/v1/chat/completions", body=body, headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
            resp = conn.getresponse(); status = resp.status
            while True:
                data = resp.read1(65536)
                if not data:
                    break
                if first is None and b'"choices"' in data:
                    first = time.perf_counter()
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if line.startswith(b"data: ") and line != b"data: [DONE]":
                        try:
                            c = json.loads(line[6:].decode("utf-8"))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                        if c.get("usage"):
                            usage = c["usage"]
        except Exception as e:
            err = str(e)
        finally:
            if conn is not None:
                conn.close()
        t1 = time.perf_counter()
        ct = (usage or {}).get("completion_tokens")
        rows.append({"i": i, "warmup": i == 0, "http_status": status, "error": err, "ttft_ms": round((first - t0) * 1000, 2) if first else None,
                     "e2e_ms": round((t1 - t0) * 1000, 2), "prompt_tokens": (usage or {}).get("prompt_tokens"), "completion_tokens": ct,
                     "itl_ms": round(((t1 - first) * 1000) / (ct - 1), 3) if first and ct and ct > 1 else None})
    ok = [r for r in rows if r["ttft_ms"] and r["itl_ms"] and not r["warmup"]]
    return {"profile": prof, "prompt_reps": CAL[prof]["reps"], "max_tokens": CAL[prof]["osl"], "rows": rows, "n_ok": len(ok),
            "prompt_tokens_p50": st.median(r["prompt_tokens"] for r in ok) if ok and all(r["prompt_tokens"] for r in ok) else None,
            "ttft_ms_avg": round(st.mean(r["ttft_ms"] for r in ok), 2) if ok else None, "ttft_ms_p50": round(st.median(r["ttft_ms"] for r in ok), 2) if ok else None,
            "itl_ms_avg": round(st.mean(r["itl_ms"] for r in ok), 3) if ok else None, "itl_ms_p50": round(st.median(r["itl_ms"] for r in ok), 3) if ok else None}


def aiperf_cmd(a, model, arm, prof, n, dur, art):
    return [a.aiperf, "profile", "-m", model, "--endpoint-type", "chat", "--streaming", "-u", BASE,
            "--tokenizer", os.path.join(a.tokenizer_root, arm.lower()), *PROFILE_ARGS[prof], "--extra-inputs", "temperature:0",
            "--concurrency", str(n), "--warmup-request-count", str(n), "--benchmark-duration", str(dur),
            "--benchmark-grace-period", "0", "--use-server-token-count", "--no-gpu-telemetry", "--ui-type", "none",
            "--random-seed", str(20260921 + n), "--artifact-dir", art]


def run_level(a, model, arm, prof, n, dur, art, tag, log, extra):
    os.makedirs(os.path.dirname(art), exist_ok=True)
    cmd = aiperf_cmd(a, model, arm, prof, n, dur, art)
    rec = {"arm": arm, "profile": prof, "container": tag, "concurrency": n, "duration_s": dur, "start": now(), "gpu_start": gpu(), "command": cmd, **extra}
    print(f"  {arm} {prof} {tag} c={n} D={dur}s{' (warm-up, discarded)' if extra.get('warmup') else ''}", flush=True)
    with open(art + "_console.txt", "w", encoding="utf-8") as con:
        rc = subprocess.run(cmd, stdout=con, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}).returncode
    rec.update({"rc": rc, "end": now(), "gpu_end": gpu()})
    summ = os.path.join(art, "profile_export_aiperf.json")
    if rc == 0 and os.path.exists(summ):
        s = json.load(open(summ, encoding="utf-8"))
        rec["summary"] = {k: s.get(k) for k in SUMMARY_KEYS}
        rec["error_summary"] = s.get("error_summary"); rec["was_cancelled"] = s.get("was_cancelled"); rec["aiperf_version"] = s.get("aiperf_version")
        cnt = (s.get("request_count") or {}).get("avg") or 0
        rec["completed"] = cnt; rec["completed_ge_3N"] = cnt >= 3 * n
        rec["request_latency_p99_ms"] = (s.get("request_latency") or {}).get("p99")
    else:
        # the first recorded per-request error, verbatim head, so a dead engine is identifiable from the level record
        exp = os.path.join(art, "profile_export.jsonl")
        if os.path.exists(exp):
            for l in open(exp, encoding="utf-8"):
                r = json.loads(l)
                if r.get("error"):
                    rec["first_error"] = {k: (str(v)[:300] if k == "message" else v) for k, v in r["error"].items()}; break
    rec["engine_after"] = engine_alive(model) if (rc != 0 or rec.get("summary") is None or ((rec.get("summary") or {}).get("error_request_count") or {}).get("avg")) else {"alive": True, "checked": False}
    rec["engine_dead"] = not rec["engine_after"]["alive"]
    log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
    print(f"     rc={rc} completed={rec.get('completed')} ttft_p99={(rec.get('summary') or {}).get('time_to_first_token', {}).get('p99') if rec.get('summary') else None} engine_dead={rec['engine_dead']}", flush=True)
    time.sleep(10)
    return rec


def sweep(a, arm, prof, model, levels, tag, log, first_duration):
    prev = None
    for n in levels:
        dur = first_duration if prev is None else int(min(600, max(60, 4 * (prev["request_latency_p99_ms"] / 1000 * n / prev["concurrency"]))))
        art = os.path.join(a.out, f"{arm}_{prof}_{tag}", f"c{n:04d}")
        rec = run_level(a, model, arm, prof, n, dur, art, tag, log, {})
        if rec["engine_dead"]:
            print(f"  {arm} {prof} {tag}: engine dead after c={n}; remaining levels {levels[levels.index(n) + 1:]} skipped", flush=True)
            log.write(json.dumps({"arm": arm, "profile": prof, "container": tag, "skipped_levels": levels[levels.index(n) + 1:], "reason": f"engine dead after c={n}", "at": now()}, ensure_ascii=False) + "\n"); log.flush()
            return
        prev = rec if rec.get("request_latency_p99_ms") else prev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer-root", required=True)
    ap.add_argument("--levels", default="1,2,4,8,16,32,64"); ap.add_argument("--test", action="store_true")
    ap.add_argument("--arms", default="A1,A2"); ap.add_argument("--profiles", default="C,R")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    levels = [int(x) for x in a.levels.split(",")]
    first_duration = 20 if a.test else 60
    warm_duration = 20 if a.test else 120   # 120 s: A2's slow phase after READY lasted more than 45 s in two long-context harness tests
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")

    def event(**kw):
        kw["at"] = now(); ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "profile", "container", "at")}, flush=True)

    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    for arm in a.arms.split(","):
        ARMS[arm] = dict(ARMS[arm], env=CONC_ENV[arm])
        for prof in a.profiles.split(","):
            for tag, lv in (("main", levels), ("fresh", levels[-2:] if len(levels) >= 2 else levels)):
                if a.test and tag == "fresh":
                    continue
                name = f"p53v2-conc-{arm.lower()}-{prof.lower()}-{tag}"
                st_ = start(arm, name, None, logdir)
                if not st_["ready"]:
                    event(kind="container_failed", arm=arm, profile=prof, container=tag, reason=st_.get("reason"), log_lines=st_.get("log_lines"))
                    save_logs(name, logdir); stop(name); continue
                time.sleep(5)
                model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
                cc = metrics_cache_config()
                if cc.get("kv_tokens") is None and st_.get("kv_tokens_from_log"):
                    cc["kv_tokens"] = st_["kv_tokens_from_log"]; cc["kv_tokens_source"] = "log"
                requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 16, "stream": False}, timeout=120)
                # warm-up level (discarded): the engine's first minute of traffic is not the steady state on A2
                warm = run_level(a, model, arm, prof, 1, warm_duration, os.path.join(a.out, f"{arm}_{prof}_{tag}", "warmup", "c0001"), tag, log, {"warmup": True})
                cal = calibrate(model, prof) if (tag == "main" and not warm["engine_dead"]) else None
                event(kind="container_start", arm=arm, profile=prof, container=tag, image=ARMS[arm]["image"], profile_id=ARMS[arm]["profile"],
                      env=st_["env"], seconds_to_ready=st_["seconds_to_ready"], gpu_ready=gpu(), cache_config=cc, log_lines=st_["log_lines"],
                      served_model=model, warmup_level={k: warm.get(k) for k in ("rc", "completed", "engine_dead", "summary")}, calibration=cal)
                if not warm["engine_dead"]:
                    sweep(a, arm, prof, model, lv, tag, log, first_duration)
                saved = save_logs(name, logdir)
                stop(name)
                event(kind="container_end", arm=arm, profile=prof, container=tag, gpu_after_stop=gpu(), container_log=saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
