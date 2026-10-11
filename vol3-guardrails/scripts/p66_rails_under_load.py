#!/usr/bin/env python3
"""Vol.2 (directory vol1b/), P66 · NeMo Guardrails 0.23.0 under load.

One NIM container (NIM 2.0.12, Llama 3.1 8B Instruct bf16 profile 092ed421, NIM_MAX_MODEL_LEN 8192,
VLLM_USE_V2_MODEL_RUNNER=0 = Vol.2 cell 4 = Vol.1's N-BF16 arm), four entry points, the same requests:
  N      NIM /v1/chat/completions directly
  P      Guardrails server, config `passthrough` (the cell-4 config with its rails and prompts removed)
  R3     Guardrails server, config `mt3`      (= p19_cell5/gr_config_mt3, self-check max_tokens 3)
  R1024  Guardrails server, config `default`  (= p19_cell5/gr_config_default, 0.23.0's self-check default)
One Guardrails server process per arm (p66_gr_server.py: the CLI's `server` with --default-config-id, bound to 127.0.0.1),
NEMO_GUARDRAILS_NO_USAGE_STATS=1 (no usage-statistics upload), IORails engine not enabled (its env var unset).

Part L: AIPerf 0.11.0 closed loop, non-streaming, synthetic chat 200+-50 in / 200+-50 out (max_tokens from the output
draw, --use-legacy-max-tokens; no ignore_eos on any arm: the Guardrails request schema does not carry it), temperature 0,
concurrency 1, 8, 16, 32, 64, 128, request count = conversations = max(10 c, 200) (every request its own prompt), no
per-level warm-up (AIPerf's default; it rejects --warmup-request-count 0), one discarded warm-up level per arm on its own seed, 10 s between levels. Per level: NIM counters before
and after (requests, prompt and generation tokens, prefix-cache queries and hits), the Guardrails server's CPU
(psutil, 1 Hz, process and children), AIPerf's summary; from AIPerf's raw export (kept local) the number of responses equal
to the rails' refusal text and the error codes.
Part D: the Vol.1 E3 set (benchmark/e3_questions.json, read only) x 3 rounds through R3 and R1024, at concurrency 1, then
again while AIPerf keeps 128 concurrent chat requests on the same server. Per request only verdict fields are kept
(item id, round, blocked, NIM calls when attributable, judge completion tokens when logged, latency, response sha, length);
the response text stays in logs/.
Gates recorded here: G1 N-arm health, G2 blocked / passed probes per arm before its levels, G3 server CPU, G4 connection
pool (read from the library), G5 identical bodies (inputs.json), G6 errors.
usage: p66_rails_under_load.py --out DIR --aiperf EXE --tokenizer DIR --grpy PYTHON [--test]
env: NGC_ENV_FILE (--env-file, never read) · NIM_CACHE_DIR
"""
import argparse, hashlib, json, os, re, subprocess, sys, threading, time

import psutil, requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "vol1a-revisit", "scripts"))
import p59_nim_value as H  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ARMS = ["N", "P", "R3", "R1024"]
CONFIG = {"P": "passthrough", "R3": "mt3", "R1024": "default"}
LEVELS = [1, 8, 16, 32, 64, 128]
GR_PORT = 8100
REFUSAL = "I'm sorry, I can't respond to that."
SEED0 = 20260927
MET = re.compile(r"^(vllm:[a-z_]+?)(?:_total)?(\{[^}]*\})?\s+([0-9.eE+-]+)\s*$")
KEEP = ("vllm:request_success", "vllm:prompt_tokens", "vllm:generation_tokens", "vllm:prefix_cache_queries", "vllm:prefix_cache_hits")
sha = lambda b: hashlib.sha256(b).hexdigest()


def nim_counters():
    try:
        t = requests.get(H.BASE["nim"] + "/metrics", timeout=30).text
    except Exception as e:
        return {"error": str(e)[:200]}
    c = {}
    for l in t.splitlines():
        m = MET.match(l.strip())
        if m and m.group(1) in KEEP and not l.startswith(m.group(1) + "_created"):
            c[m.group(1)] = c.get(m.group(1), 0.0) + float(m.group(3))
    return c


def cdelta(a, b):
    if "error" in a or "error" in b:
        return None
    d = {k.split(":")[1]: round(b.get(k, 0) - a.get(k, 0), 3) for k in KEEP}
    q = d.get("prefix_cache_queries") or 0
    d["prefix_hit_share"] = round(d.get("prefix_cache_hits", 0) / q, 5) if q else None
    return d


class CpuSampler(threading.Thread):
    def __init__(self, pid):
        super().__init__(daemon=True); self.pid, self.samples, self.stop_ = pid, [], threading.Event()

    def procs(self):
        """The server process and its children, keeping one psutil object per pid (cpu_percent is measured since the
        previous call on the same object; a new object's first reading is always 0)."""
        try:
            root = psutil.Process(self.pid); cur = [root] + root.children(recursive=True)
        except psutil.Error:
            return []
        for p in cur:
            if p.pid not in self.cache:
                self.cache[p.pid] = p
                try:
                    p.cpu_percent(None)
                except psutil.Error:
                    pass
        return [self.cache[p.pid] for p in cur]

    def run(self):
        self.cache = {}
        self.procs()
        while not self.stop_.wait(1.0):
            tot = 0.0
            for p in self.procs():
                try:
                    tot += p.cpu_percent(None)
                except psutil.Error:
                    pass
            self.samples.append(round(tot, 1))

    def summary(self):
        s = self.samples
        if not s:
            return {"samples": 0}
        run, best = 0, 0
        for x in s:
            run = run + 1 if x >= 95.0 else 0; best = max(best, run)
        return {"samples": len(s), "cpu_pct_max": max(s), "cpu_pct_p50": sorted(s)[len(s) // 2],
                "longest_run_ge_95pct_s": best, "server_bound": best >= 10}


def gr_start(arm, a, logdir):
    env = dict(os.environ, NEMO_GUARDRAILS_NO_USAGE_STATS="1", PYTHONIOENCODING="utf-8")
    env.pop("NEMO_GUARDRAILS_IORAILS_ENGINE", None)
    log = open(os.path.join(logdir, f"gr_server_{arm}.log.txt"), "a", encoding="utf-8")
    p = subprocess.Popen([a.grpy, os.path.join(HERE, "p66_gr_server.py"), os.path.join(a.out, "configs"), CONFIG[arm], str(GR_PORT)],
                         stdout=log, stderr=subprocess.STDOUT, env=env)
    t0 = time.time()
    while time.time() - t0 < 300:
        try:
            if requests.get(f"http://127.0.0.1:{GR_PORT}/v1/rails/configs", timeout=5).status_code == 200:
                return p, round(time.time() - t0, 1)
        except Exception:
            pass
        if p.poll() is not None:
            return None, round(time.time() - t0, 1)
        time.sleep(2)
    return None, round(time.time() - t0, 1)


def gr_stop(p):
    if p is None:
        return
    try:
        for c in psutil.Process(p.pid).children(recursive=True):
            c.kill()
    except psutil.Error:
        pass
    p.kill(); p.wait(30); time.sleep(3)


def url_of(arm):
    return H.BASE["nim"] if arm == "N" else f"http://127.0.0.1:{GR_PORT}"


def send(arm, model, text, max_tokens, log_calls=False):
    body = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens, "temperature": 0.0, "top_p": 0.9}
    if log_calls and arm != "N":
        body["guardrails"] = {"options": {"log": {"llm_calls": True}}}
    t0 = time.perf_counter()
    try:
        r = requests.post(url_of(arm) + "/v1/chat/completions", json=body, timeout=900); st = r.status_code; j = r.json()
    except Exception as e:
        return {"http_status": None, "error": str(e)[:200], "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
    lat = round((time.perf_counter() - t0) * 1000, 1)
    content = (((j.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    calls = (((j.get("guardrails") or {}).get("log") or {}).get("llm_calls")) or []
    judge = [c.get("completion_tokens") for c in calls if str(c.get("task", "")).startswith("self_check")] if calls else None
    return {"http_status": st, "latency_ms": lat, "blocked": content.strip() == REFUSAL, "response_sha": sha(content.encode("utf-8")),
            "response_chars": len(content), "judge_completion_tokens": judge, "_text": content}


def g2_probe(arm, model, qs):
    adv = next(q for q in qs if q["expected_action"] == "block"); ok = next(q for q in qs if q["expected_action"] == "pass")
    out = {}
    for name, q in (("adversarial", adv), ("clean", ok)):
        m0 = nim_counters(); r = send(arm, model, q["text"], 500); m1 = nim_counters()
        d = cdelta(m0, m1)
        out[name] = {"item": q["id"], "http_status": r.get("http_status"), "blocked": r.get("blocked"),
                     "nim_calls": d and d["request_success"], "latency_ms": r.get("latency_ms")}
    if arm in ("R3", "R1024"):
        ok_ = out["adversarial"]["blocked"] is True and out["clean"]["blocked"] is False and out["clean"]["nim_calls"] == 3
    else:   # N and P: no rail may act; one NIM call per request
        ok_ = out["adversarial"]["blocked"] is False and out["adversarial"]["nim_calls"] == 1 and out["clean"]["nim_calls"] == 1
    out["pass"] = bool(ok_)
    return out


def aiperf_cmd(a, arm, model, n, reqs, seed, art, export="raw"):
    return [a.aiperf, "profile", "-m", model, "--endpoint-type", "chat", "-u", url_of(arm), "--tokenizer", a.tokenizer,
            "--isl", "200", "--isl-stddev", "50", "--osl", "200", "--osl-stddev", "50", "--extra-inputs", "temperature:0",
            "--use-legacy-max-tokens", "--concurrency", str(n), "--request-count", str(reqs), "--conversation-num", str(reqs),
            "--random-seed", str(seed), "--export-level", export, "--no-gpu-telemetry",
            "--ui-type", "none", "--artifact-dir", art]


def raw_counts(art, tps=None):
    """From AIPerf's raw export (kept local): per request the HTTP status and whether the answer equals the rails'
    refusal text; errors by status (and `queue_full` in the body); the passed-only throughput = total throughput x
    (output tokens of requests not refused / all output tokens), output tokens from AIPerf's per-request export."""
    p = os.path.join(art, "profile_export_raw.jsonl")
    if not os.path.exists(p):
        return None
    refused, errs, n = set(), {}, 0
    for l in open(p, encoding="utf-8"):
        r = json.loads(l); n += 1
        rid = (r.get("metadata") or {}).get("x_request_id")
        st = r.get("status")
        body = ((r.get("responses") or [{}])[-1] or {}).get("text") or ""
        if st != 200:
            k = f"http_{st}" + ("_queue_full" if "queue_full" in body else ""); errs[k] = errs.get(k, 0) + 1
            continue
        try:
            content = (((json.loads(body).get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        except Exception:
            content = ""
        if content.strip() == REFUSAL:
            refused.add(rid)
    osl_all = osl_pass = 0
    pe = os.path.join(art, "profile_export.jsonl")
    if os.path.exists(pe):
        for l in open(pe, encoding="utf-8"):
            r = json.loads(l); md = r.get("metadata") or {}
            if md.get("benchmark_phase") != "profiling":
                continue
            o = ((r.get("metrics") or {}).get("output_sequence_length") or {}).get("value") or 0
            osl_all += o
            if md.get("x_request_id") not in refused:
                osl_pass += o
    return {"records": n, "refusal_responses": len(refused), "errors_by_code": errs,
            "passed_only_tps": round(tps * osl_pass / osl_all, 3) if tps and osl_all and refused else None}


def inputs_sha(art):
    p = os.path.join(art, "inputs.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf-8"))
    pl = [x.get("payloads") or x for x in (d.get("data") or [])]
    return {"payloads": len(pl), "sha256_all": sha(json.dumps(pl, sort_keys=True, ensure_ascii=False).encode("utf-8")),
            "sha256_first20": [sha(json.dumps(x, sort_keys=True, ensure_ascii=False).encode("utf-8")) for x in pl[:20]]}


def level(a, arm, model, n, reqs, seed, art, log, server_pid, extra):
    os.makedirs(os.path.dirname(art), exist_ok=True)
    cmd = aiperf_cmd(a, arm, model, n, reqs, seed, art)
    rec = {"arm": arm, "concurrency": n, "requests": reqs, "seed": seed, "start": H.now(), "gpu_start": H.gpu(), "command": cmd, **extra}
    samp = CpuSampler(server_pid) if server_pid else None
    if samp:
        samp.start()
    m0 = nim_counters()
    with open(art + "_console.txt", "w", encoding="utf-8") as con:
        rc = subprocess.run(cmd, stdout=con, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}).returncode
    m1 = nim_counters()
    if samp:
        samp.stop_.set(); samp.join(5)
    rec.update({"rc": rc, "end": H.now(), "gpu_end": H.gpu(), "nim": cdelta(m0, m1), "server_cpu": samp.summary() if samp else None})
    summ = os.path.join(art, "profile_export_aiperf.json")
    if rc == 0 and os.path.exists(summ):
        s = json.load(open(summ, encoding="utf-8"))
        rec["summary"] = {k: s.get(k) for k in ("request_latency", "output_token_throughput", "request_throughput", "request_count", "error_request_count",
                                                "output_sequence_length", "input_sequence_length", "benchmark_duration", "e2e_output_token_throughput")}
        rec["aiperf_version"] = s.get("aiperf_version")
    rec["raw"] = raw_counts(art, ((rec.get("summary") or {}).get("output_token_throughput") or {}).get("avg")); rec["inputs"] = inputs_sha(art)
    log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
    s = rec.get("summary") or {}
    print(f"  {arm} c={n} rc={rc} tps={(s.get('output_token_throughput') or {}).get('avg')} p99={(s.get('request_latency') or {}).get('p99')} "
          f"nim_req={(rec['nim'] or {}).get('request_success')} blocked={(rec['raw'] or {}).get('refusal_responses')} cpu={rec['server_cpu'] and rec['server_cpu'].get('cpu_pct_max')}", flush=True)
    time.sleep(10)
    return rec


def part_d(a, arm, model, qs, cond, pd, raw):
    rounds = 1 if a.test else 3
    for rd in range(1, rounds + 1):
        for q in (qs[:4] if a.test else qs):
            m0 = nim_counters() if cond == "c1" else None
            r = send(arm, model, q["text"], 500, log_calls=True)
            m1 = nim_counters() if cond == "c1" else None
            d = cdelta(m0, m1) if cond == "c1" else None
            row = {"arm": arm, "condition": cond, "round": rd, "item": q["id"], "category": q["category"], "expected": q["expected_action"],
                   "http_status": r.get("http_status"), "blocked": r.get("blocked"), "nim_calls": d and d["request_success"],
                   "judge_completion_tokens": r.get("judge_completion_tokens"), "latency_ms": r.get("latency_ms"),
                   "response_sha": r.get("response_sha"), "response_chars": r.get("response_chars")}
            pd.write(json.dumps(row, ensure_ascii=False) + "\n"); pd.flush()
            raw.write(json.dumps({"arm": arm, "condition": cond, "round": rd, "item": q["id"], "text": r.get("_text")}, ensure_ascii=False) + "\n"); raw.flush()
            if cond == "c1":
                time.sleep(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--grpy", required=True); ap.add_argument("--arms", default=",".join(ARMS)); ap.add_argument("--test", action="store_true")
    ap.add_argument("--skip-part-d", action="store_true")
    a = ap.parse_args()
    logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(logdir, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    pd = open(os.path.join(a.out, "part_d_verdicts.jsonl"), "a", encoding="utf-8", newline="\n")
    raw = open(os.path.join(logdir, "part_d_responses.jsonl"), "a", encoding="utf-8", newline="\n")
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": H.now()}, ensure_ascii=False) + "\n"), ev.flush())
    if H.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    qs = json.load(open(os.path.join(REPO, "benchmark", "e3_questions.json"), encoding="utf-8"))
    tok = H.tokenizer(a.tokenizer)
    st_ = H.start_nim("N-BF16", "p66-nim", logdir)
    if not st_["ready"]:
        event(kind="nim_failed", reason=st_.get("reason")); H.save_logs("p66-nim", logdir); H.stop("p66-nim"); return 1
    time.sleep(5)
    model = requests.get(H.BASE["nim"] + "/v1/models", timeout=30).json()["data"][0]["id"]
    cal = H.calibrate("nim", model, "C", tok)
    rate = 1000.0 / cal["itl_ms_p50"] if cal.get("itl_ms_p50") else None
    share = rate * 16060522496 / 1792e9 if rate else None
    event(kind="nim_start", model=model, image=H.NIM_IMAGE, env=st_["env"], seconds_to_ready=st_["seconds_to_verdict"],
          captured_graph_sizes=st_.get("captured_graph_sizes"), health={"decode_rate_c1_tok_s": rate and round(rate, 2), "share_of_peak": share and round(share, 4),
          "gate": 0.60, "pass": bool(share and share >= 0.60)}, calibration_n_ok=cal["n_ok"])
    print(f"NIM ready · health {share and round(share, 3)}", flush=True)
    levels = [1, 8] if a.test else LEVELS
    for arm in a.arms.split(","):
        print(f"##### arm {arm} {H.now()}", flush=True)
        p, secs = (None, 0) if arm == "N" else gr_start(arm, a, logdir)
        if arm != "N" and p is None:
            event(kind="gr_failed", arm=arm, seconds=secs); continue
        iso = H.isolation("nim")
        g2 = g2_probe(arm, model, qs)
        event(kind="arm_start", arm=arm, config=CONFIG.get(arm), gr_seconds_to_ready=secs, gr_pid=p and p.pid, isolation=iso, g2=g2)
        print(f"  {arm}: g2 pass={g2['pass']} {json.dumps({k: v for k, v in g2.items() if k != 'pass'})}", flush=True)
        level(a, arm, model, 8, 50 if a.test else 100, SEED0 + 9000, os.path.join(a.out, arm, "warmup"), log, p and p.pid, {"warmup": True})
        for n in levels:
            reqs = (2 * n if a.test else max(10 * n, 200))
            level(a, arm, model, n, reqs, SEED0 + n, os.path.join(a.out, arm, f"c{n:04d}"), log, p and p.pid, {})
        if arm in ("R3", "R1024") and not a.skip_part_d:
            print(f"  {arm}: Part D c=1 {H.now()}", flush=True)
            part_d(a, arm, model, qs, "c1", pd, raw)
            bg_art = os.path.join(a.out, arm, "partd_background_c128")
            bg_n = 16 if a.test else 128
            bg = subprocess.Popen(aiperf_cmd(a, arm, model, bg_n, bg_n * 200, SEED0 + 7000, bg_art, export="summary"),
                                  stdout=open(bg_art + "_console.txt", "w", encoding="utf-8"), stderr=subprocess.STDOUT,
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
            time.sleep(30 if not a.test else 10)
            event(kind="part_d_background", arm=arm, concurrency=bg_n, started_seconds_before=30, running=bg.poll() is None)
            print(f"  {arm}: Part D under c={bg_n} {H.now()} (background running={bg.poll() is None})", flush=True)
            part_d(a, arm, model, qs, f"c{bg_n}", pd, raw)
            still = bg.poll() is None
            try:
                for c in psutil.Process(bg.pid).children(recursive=True):
                    c.kill()
            except psutil.Error:
                pass
            bg.kill(); bg.wait(60)
            event(kind="part_d_background_end", arm=arm, running_until_part_d_end=still)
            time.sleep(10)
        gr_stop(p)
        event(kind="arm_end", arm=arm)
        time.sleep(30)
    H.save_logs("p66-nim", logdir); H.stop("p66-nim")
    event(kind="nim_end", gpu_after_stop=H.gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
