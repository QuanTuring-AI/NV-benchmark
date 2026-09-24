#!/usr/bin/env python3
"""Vol.2 concurrency: closed-loop sweeps with AIPerf against each Nemotron NIM, two ISL/OSL profiles, both arms at
max_num_seqs 32, with an instrument calibration at concurrency 1 before every sweep.

Per (arm, profile): start the container (NIM_MAX_MODEL_LEN 8192 so the RAG profile's ISL+OSL fits; A1 NIM_MAX_NUM_SEQS=32,
A2 NIM_PASSTHROUGH_ARGS "--max-num-seqs 32"), discard one request, run the calibration (10 streamed requests through
this script's own client at concurrency 1, new connection per request, fixed synthetic prompt, ignore_eos), then one `aiperf profile` process per
level 1, 2, 4, 8, 16, 32, 64 (closed loop: a new request is issued as soon as one completes; warm-up = N requests
excluded by AIPerf; benchmark duration as vol1b/scripts/p17_sweep.py). Then a fresh container repeats the two highest
levels, so the state dependence seen in D25 is visible rather than averaged away.
Profiles (after the NVIDIA NIM LLM Benchmarking Guide's ISL/OSL categories, short chat vs summarization/RAG): C = 200±50 / 200±50, R = 3500±300 / 500±50, synthetic, ignore_eos,
temperature 0. AIPerf artifacts are written per level before the next level starts.
usage: p53_concurrency.py --out DIR --aiperf EXE --tokenizer-root DIR [--levels 1,2,4,8,16,32,64] [--test]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, statistics as st, subprocess, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PROFILE_ARGS = {
    "C": ["--isl", "200", "--isl-stddev", "50", "--osl", "200", "--osl-stddev", "50", "--extra-inputs", "ignore_eos:true"],
    "R": ["--isl", "3500", "--isl-stddev", "300", "--osl", "500", "--osl-stddev", "50", "--extra-inputs", "ignore_eos:true"],
}
SUMMARY_KEYS = ["time_to_first_token", "inter_token_latency", "request_latency", "output_token_throughput",
                "output_token_throughput_per_user", "request_throughput", "request_count", "error_request_count",
                "input_sequence_length", "output_sequence_length", "benchmark_duration"]
CONC_ENV = {"A1": {"NIM_MAX_MODEL_LEN": "8192", "NIM_MAX_NUM_SEQS": "32"},
            "A2": {"NIM_MAX_MODEL_LEN": "8192", "NIM_PASSTHROUGH_ARGS": "--max-num-seqs 32"}}
CAL_N, CAL_OSL = 10, 200
CAL_PROMPT = " ".join(["The quick brown fox jumps over the lazy dog."] * 22)   # about 200 tokens of filler


def calibrate(model):
    """One discarded warm-up request, then ten streamed requests at concurrency 1 through this script's own client, each
    on a new TCP connection: TTFT and inter-token latency as GenAI-Perf defines them (ITL = (e2e - TTFT) /
    (output_tokens - 1)). Compared with AIPerf's c=1 level in analysis (medians of both)."""
    rows = []
    # Why a new connection per request: in the calibration diagnosis of 2026-09-23 (A1, this prompt, same server) the
    # first request on a fresh connection reached its first chunk in 43-54 ms, the same as AIPerf's 46-57 ms, while
    # every later request on the same kept-alive connection took 83-99 ms with ITL unchanged. The earlier calibration
    # attempts (a requests.Session, then one http.client connection with TCP_NODELAY) all reused the connection and
    # all measured 85-96 ms; curl's time to the response headers on the same server was 6-8 ms, so the request path
    # itself is not the cause. The mechanism (on the Docker Desktop port proxy or in the container) was not identified;
    # the harness avoids the condition and records it here rather than explaining it.
    # The client reads the socket chunk by chunk (http.client read1: one underlying read per call), so the first SSE
    # event is timed when it arrives; the requests library's iter_lines() first fills a 512-byte buffer, which on this
    # server means two or three tokens (see the side measurement below).
    import http.client, socket, urllib.parse
    u = urllib.parse.urlparse(BASE)

    def connect():
        c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=300)
        c.connect()
        c.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return c

    for i in range(CAL_N + 1):
        payload = {"model": model, "messages": [{"role": "user", "content": CAL_PROMPT + f" ({i})"}], "max_tokens": CAL_OSL,
                   "temperature": 0.0, "stream": True, "ignore_eos": True, "stream_options": {"include_usage": True}}
        body = json.dumps(payload).encode("utf-8")
        t0 = time.perf_counter(); first = None; usage = None; status = None; err = None; buf = b""
        conn = None
        try:
            conn = connect()
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
                     "e2e_ms": round((t1 - t0) * 1000, 2), "completion_tokens": ct,
                     "itl_ms": round(((t1 - first) * 1000) / (ct - 1), 3) if first and ct and ct > 1 else None})
        time.sleep(1)
    ok = [r for r in rows if r["ttft_ms"] and r["itl_ms"] and not r["warmup"]]
    # Side measurement, not part of the gate: the same requests through the `requests` client that the speed,
    # answer and long-context harnesses use (headers and body in separate writes, Nagle's algorithm on), so the
    # client-side TTFT offset those tables carry is quantified against the same server in the same session.
    req_rows = []
    for i in range(5):
        payload = {"model": model, "messages": [{"role": "user", "content": CAL_PROMPT + f" (r{i})"}], "max_tokens": CAL_OSL,
                   "temperature": 0.0, "stream": True, "ignore_eos": True, "stream_options": {"include_usage": True}}
        t0 = time.perf_counter(); first = None; usage = None
        try:
            r = requests.post(BASE + "/v1/chat/completions", json=payload, stream=True, timeout=300)
            for line in r.iter_lines():
                if line and line.startswith(b"data: ") and line != b"data: [DONE]":
                    if first is None:
                        first = time.perf_counter()
                    try:
                        c = json.loads(line[6:].decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if c.get("usage"):
                        usage = c["usage"]
            t1 = time.perf_counter(); ct = (usage or {}).get("completion_tokens")
            req_rows.append({"ttft_ms": round((first - t0) * 1000, 2) if first else None,
                             "itl_ms": round(((t1 - first) * 1000) / (ct - 1), 3) if first and ct and ct > 1 else None})
        except Exception as e:
            req_rows.append({"error": str(e)})
        time.sleep(1)
    rq = [r for r in req_rows if r.get("ttft_ms") and r.get("itl_ms")]
    return {"rows": rows, "ttft_ms_avg": round(st.mean(r["ttft_ms"] for r in ok), 2) if ok else None,
            "ttft_ms_p50": round(st.median(r["ttft_ms"] for r in ok), 2) if ok else None,
            "itl_ms_avg": round(st.mean(r["itl_ms"] for r in ok), 3) if ok else None,
            "itl_ms_p50": round(st.median(r["itl_ms"] for r in ok), 3) if ok else None, "n_ok": len(ok),
            "requests_client": {"rows": req_rows, "ttft_ms_avg": round(st.mean(r["ttft_ms"] for r in rq), 2) if rq else None,
                                "ttft_ms_p50": round(st.median(r["ttft_ms"] for r in rq), 2) if rq else None,
                                "itl_ms_avg": round(st.mean(r["itl_ms"] for r in rq), 3) if rq else None, "n_ok": len(rq)}}


def sweep(a, arm, prof, model, levels, tag, log, first_duration):
    prev = None
    for n in levels:
        dur = first_duration if prev is None else int(min(600, max(60, 4 * (prev["request_latency_p99_ms"] / 1000 * n / prev["concurrency"]))))
        art = os.path.join(a.out, f"{arm}_{prof}_{tag}", f"c{n:04d}")
        os.makedirs(os.path.dirname(art), exist_ok=True)
        cmd = [a.aiperf, "profile", "-m", model, "--endpoint-type", "chat", "--streaming", "-u", BASE,
               "--tokenizer", os.path.join(a.tokenizer_root, arm.lower()), *PROFILE_ARGS[prof], "--extra-inputs", "temperature:0",
               "--concurrency", str(n), "--warmup-request-count", str(n), "--benchmark-duration", str(dur),
               "--benchmark-grace-period", "0", "--use-server-token-count", "--no-gpu-telemetry", "--ui-type", "none",
               "--random-seed", str(20260921 + n), "--artifact-dir", art]
        rec = {"arm": arm, "profile": prof, "container": tag, "concurrency": n, "duration_s": dur, "start": now(), "gpu_start": gpu(), "command": cmd}
        print(f"  {arm} {prof} {tag} c={n} D={dur}s", flush=True)
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
        log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
        print(f"     rc={rc} completed={rec.get('completed')} ttft_p99={(rec.get('summary') or {}).get('time_to_first_token', {}).get('p99') if rec.get('summary') else None}", flush=True)
        prev = rec if rec.get("request_latency_p99_ms") else prev
        time.sleep(10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer-root", required=True)
    ap.add_argument("--levels", default="1,2,4,8,16,32,64"); ap.add_argument("--test", action="store_true")
    ap.add_argument("--arms", default="A1,A2"); ap.add_argument("--profiles", default="C,R")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    levels = [int(x) for x in a.levels.split(",")]
    first_duration = 20 if a.test else 60
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
                name = f"p53-conc-{arm.lower()}-{prof.lower()}-{tag}"
                st_ = start(arm, name, None, logdir)
                if not st_["ready"]:
                    event(kind="container_failed", arm=arm, profile=prof, container=tag, reason=st_.get("reason"), log_lines=st_.get("log_lines"))
                    stop(name); continue
                time.sleep(5)
                model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
                cc = metrics_cache_config()
                if cc.get("kv_tokens") is None and st_.get("kv_tokens_from_log"):
                    cc["kv_tokens"] = st_["kv_tokens_from_log"]; cc["kv_tokens_source"] = "log"
                requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 16, "stream": False}, timeout=120)
                cal = calibrate(model) if tag == "main" else None
                event(kind="container_start", arm=arm, profile=prof, container=tag, image=ARMS[arm]["image"], profile_id=ARMS[arm]["profile"],
                      env=st_["env"], seconds_to_ready=st_["seconds_to_ready"], gpu_ready=gpu(), cache_config=cc, log_lines=st_["log_lines"],
                      served_model=model, calibration=cal)
                sweep(a, arm, prof, model, lv, tag, log, first_duration)
                stop(name)
                event(kind="container_end", arm=arm, profile=prof, container=tag, gpu_after_stop=gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
