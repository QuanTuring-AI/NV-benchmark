#!/usr/bin/env python3
"""Vol.2 (directory vol1b/), P67 · the Guardrails server's own limits separated from the rails' cost: worker processes W
and uvicorn's keep-alive timeout K, at 32 / 64 / 128 concurrent requests.

Everything the load touches is P66's (p66_rails_under_load.py, imported, not changed): the same NIM container settings
(Llama 3.1 8B Instruct, NIM 2.0.12, bf16 profile 092ed421, NIM_MAX_MODEL_LEN 8192, VLLM_USE_V2_MODEL_RUNNER=0), the same
three Guardrails configs (P passthrough · R3 mt3 · R1024 default), the same AIPerf command (non-streaming, synthetic chat
200+-50 / 200+-50, temperature 0, no ignore_eos, requests = conversations = max(10 c, 200), seed 20260927 + c), one discarded
warm-up level per server start (c=8, 100 requests, seed 20260927 + 9000), 10 s between levels. What changes is the server:
p67_gr_server.py with W workers and timeout_keep_alive K (p66_gr_server.py = W 1, K 5).

Plan, one NIM container, one session, W = 1 and W = 4 alternating:
  N                      c 32 64 128   anchor against P66 (G7)
  R1024 W1K5 · W4K75 · W1K75 · W4K5   c 64 128   the 2 x 2 of the two factors
  R3    W1K5 · W4K75     c 32 64 128   W1K5 = P66 again (second anchor, G7); W4K75 = the rails without the one-process limit
  P     W4K75 · W1K5     c 64 128      the server alone with several workers
  Part D after R1024 W4K75's levels, on the same server: the Vol.1 E3 set x 3 rounds while AIPerf keeps 128 concurrent
         chat requests on it (condition c128_W4K75).
  Branch (pre-registered): if R3 W4K75 at c=128 is server_bound, R3 W8K75 at c=128 once (variant w8), then no more.

Per server start: the port is checked free first; the server is ready only when all W workers answer (fresh connections,
64 at a time), each answering pid a descendant of the server started; uvicorn's worker restarts during start-up are
counted (on Windows several workers calling listen() on the shared socket at once can fail with WinError 10022 and
uvicorn starts a replacement). G2 per worker: adversarial and clean E3 items sent 2 W at a time on fresh connections until
every worker has answered both, each response carrying its worker pid, its config sha and the server's LLM-call log.
Per level, besides P66's record: server CPU per process (psutil, 1 Hz; server_bound = one process >= 95% for >= 10 s in a
row), requests per worker, and uvicorn's keep-alive closes and connections lost (from the server log slice of the level),
AIPerf errors by type with the time from send to error.
usage: p67_rails_server_config.py --out DIR --aiperf EXE --tokenizer DIR --grpy PYTHON [--test] [--only LABELS]
env: NGC_ENV_FILE (--env-file, never read) · NIM_CACHE_DIR
"""
import argparse, collections, json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import psutil, requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import p66_rails_under_load as M  # noqa: E402
H = M.H

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CONFIG = M.CONFIG
GR_PORT = M.GR_PORT
SEED0 = M.SEED0
PLAN = [("N", None, None, [32, 64, 128]),
        ("R1024", 1, 5, [64, 128]), ("R1024", 4, 75, [64, 128]), ("R1024", 1, 75, [64, 128]), ("R1024", 4, 5, [64, 128]),
        ("R3", 1, 5, [32, 64, 128]), ("R3", 4, 75, [32, 64, 128]),
        ("P", 4, 75, [64, 128]), ("P", 1, 5, [64, 128])]
PART_D_AT = ("R1024", 4, 75)
W8_BRANCH = ("R3", 4, 75, 128)
ACCESS = re.compile(r"^INFO:\s+pid=(\d+) \S+ - \"POST /v1/chat/completions HTTP/1\.1\" (\d+)")
KA = re.compile(r"^P67_KEEPALIVE_CLOSE pid=(\d+)")
LOST = re.compile(r"^P67_CONN_LOST pid=(\d+) exc=(\w+) mid_request=(\d)")
WORKER = re.compile(r"^P67_WORKER pid=(\d+) config_id=(\S+) config_sha256=([0-9a-f]{64})")
label = lambda arm, w, k: arm if w is None else f"{arm}_W{w}K{k}"


def listeners(port):
    return sorted({c.pid for c in psutil.net_connections("tcp") if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN})


def tree(pid):
    try:
        root = psutil.Process(pid); return [root] + root.children(recursive=True)
    except psutil.Error:
        return []


class ServerLog:
    """The server's log file; slices between two byte offsets are parsed for the per-level counts."""
    def __init__(self, path):
        self.path = path

    def pos(self):
        return os.path.getsize(self.path) if os.path.exists(self.path) else 0

    def lines(self, a, b=None):
        with open(self.path, "rb") as f:
            f.seek(a); data = f.read() if b is None else f.read(max(0, b - a))
        return data.decode("utf-8", errors="replace").splitlines()

    def counts(self, a, b=None):
        req, status, ka, lost, workers = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter(), {}
        restarts = tracebacks = 0
        for l in self.lines(a, b):
            m = ACCESS.match(l)
            if m:
                req[m.group(1)] += 1; status[m.group(2)] += 1; continue
            m = KA.match(l)
            if m:
                ka[m.group(1)] += 1; continue
            m = LOST.match(l)
            if m:
                lost[f"{m.group(2)}|mid_request={m.group(3)}"] += 1; continue
            m = WORKER.match(l)
            if m:
                workers[m.group(1)] = {"config_id": m.group(2), "config_sha256": m.group(3)}; continue
            if "WinError 10022" in l:
                restarts += 1
            if l.startswith("Traceback") or l.startswith("ERROR:    Traceback"):
                tracebacks += 1
        return {"chat_requests_by_worker": dict(req), "chat_status": dict(status), "keepalive_closes": sum(ka.values()),
                "keepalive_closes_by_worker": dict(ka), "connections_lost": dict(lost), "workers_imported": workers,
                "listen_winerror_10022": restarts, "tracebacks": tracebacks}


class CpuSampler(threading.Thread):
    """CPU of every process in the server's tree, per process (psutil, 1 Hz). One psutil object is kept per pid:
    cpu_percent is measured since the previous call on the same object, and a new object's first reading is 0."""
    def __init__(self, pid):
        super().__init__(daemon=True); self.pid, self.series, self.stop_, self.cache = pid, {}, threading.Event(), {}

    def procs(self):
        cur = tree(self.pid)
        for p in cur:
            if p.pid not in self.cache:
                self.cache[p.pid] = p
                try:
                    p.cpu_percent(None)
                except psutil.Error:
                    pass
        return [self.cache[p.pid] for p in cur]

    def run(self):
        self.procs(); t = 0
        while not self.stop_.wait(1.0):
            t += 1; tot = 0.0
            for p in self.procs():
                try:
                    v = p.cpu_percent(None)
                except psutil.Error:
                    continue
                self.series.setdefault(str(p.pid), []).append((t, round(v, 1))); tot += v
            self.series.setdefault("total", []).append((t, round(tot, 1)))

    def summary(self):
        per = {}
        for pid, s in self.series.items():
            run, best = 0, 0
            for _, x in s:
                run = run + 1 if x >= 95.0 else 0; best = max(best, run)
            v = sorted(x for _, x in s)
            per[pid] = {"samples": len(s), "cpu_pct_max": v[-1] if v else None, "cpu_pct_p50": v[len(v) // 2] if v else None, "longest_run_ge_95pct_s": best}
        procs = {k: x for k, x in per.items() if k != "total"}
        busy = {k: x for k, x in procs.items() if (x["cpu_pct_p50"] or 0) >= 5.0}
        worst = max((x["longest_run_ge_95pct_s"] for x in procs.values()), default=0)
        return {"per_process": procs, "total": per.get("total"), "processes_busy_p50_ge_5pct": len(busy),
                "longest_run_ge_95pct_s_any_process": worst, "server_bound": worst >= 10}


def gr_start(arm, w, k, a, logdir):
    """Start the server, wait until every worker answers. Returns (proc, info) or (None, info)."""
    busy = listeners(GR_PORT)
    if busy:
        return None, {"refused": f"port {GR_PORT} already has a listener", "listener_pids": busy}
    path = os.path.join(logdir, f"gr_server_{label(arm, w, k)}.log.txt"); lg = ServerLog(path); off = lg.pos()
    env = dict(os.environ, NEMO_GUARDRAILS_NO_USAGE_STATS="1", PYTHONIOENCODING="utf-8")
    env.pop("NEMO_GUARDRAILS_IORAILS_ENGINE", None)
    fh = open(path, "a", encoding="utf-8")
    p = subprocess.Popen([a.grpy, os.path.join(HERE, "p67_gr_server.py"), os.path.join(a.out, "configs"), CONFIG[arm], str(GR_PORT), str(w), str(k)],
                         stdout=fh, stderr=subprocess.STDOUT, env=env)
    t0 = time.time(); seen = set(); foreign = set()
    url = f"http://127.0.0.1:{GR_PORT}/v1/rails/configs"

    def one(_):
        try:
            return requests.get(url, headers={"Connection": "close"}, timeout=10).headers.get("x-p67-worker-pid")
        except Exception:
            return None
    while time.time() - t0 < 240:
        if p.poll() is not None:
            return None, {"refused": "server exited", "seconds": round(time.time() - t0, 1), **lg.counts(off)}
        with ThreadPoolExecutor(64) as ex:
            got = {x for x in ex.map(one, range(64)) if x}
        mine = {str(q.pid) for q in tree(p.pid)}
        seen |= got & mine; foreign |= got - mine
        if len(seen) >= w:
            break
        time.sleep(2)
    info = {"seconds_to_all_workers": round(time.time() - t0, 1), "workers_answering": sorted(seen), "foreign_pids_answering": sorted(foreign),
            "all_workers_answering": len(seen) >= w and not foreign, "listener_pids": listeners(GR_PORT), **lg.counts(off)}
    return p, info


def gr_stop(p):
    if p is None:
        return {"stopped": None}
    for q in reversed(tree(p.pid)):
        try:
            q.kill()
        except psutil.Error:
            pass
    try:
        p.wait(30)
    except Exception:
        pass
    t0 = time.time()
    while listeners(GR_PORT) and time.time() - t0 < 60:
        time.sleep(1)
    time.sleep(3)
    return {"port_free_after_s": round(time.time() - t0, 1), "listeners_left": listeners(GR_PORT)}


def probe(arm, model, text):
    body = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": 500, "temperature": 0.0, "top_p": 0.9,
            "guardrails": {"options": {"log": {"llm_calls": True}}}}
    try:
        r = requests.post(M.url_of(arm) + "/v1/chat/completions", json=body, headers={"Connection": "close"}, timeout=900); j = r.json()
    except Exception as e:
        return {"error": str(e)[:200]}
    content = (((j.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    calls = (((j.get("guardrails") or {}).get("log") or {}).get("llm_calls")) or []
    return {"http_status": r.status_code, "worker_pid": r.headers.get("x-p67-worker-pid"), "config_sha256": r.headers.get("x-p67-config-sha256"),
            "blocked": content.strip() == M.REFUSAL, "llm_calls": len(calls), "tasks": [c.get("task") for c in calls]}


def g2_workers(arm, model, qs, workers, want_sha):
    """Adversarial and clean E3 items, 2 W at a time on fresh connections, until every worker answered both (<= 10 rounds).
    Rails: adversarial blocked with 1 LLM call (input rail), clean passed with 3. P: neither blocked, 1 LLM call each.
    Each round's NIM request delta must equal the LLM calls the responses report, and every response's config sha the
    expected one."""
    adv = next(q for q in qs if q["expected_action"] == "block"); ok = next(q for q in qs if q["expected_action"] == "pass")
    per = {pid: {"adversarial": None, "clean": None} for pid in workers}; rounds = []
    for rd in range(10):
        jobs = [("adversarial", adv)] * len(workers) + [("clean", ok)] * len(workers)
        m0 = M.nim_counters()
        with ThreadPoolExecutor(len(jobs)) as ex:
            res = list(ex.map(lambda j: (j[0], probe(arm, model, j[1]["text"])), jobs))
        m1 = M.nim_counters(); d = M.cdelta(m0, m1)
        calls = sum(r.get("llm_calls") or 0 for _, r in res)
        rounds.append({"round": rd + 1, "responses": len(res), "llm_calls_reported": calls, "nim_requests": d and d["request_success"],
                       "match": bool(d) and d["request_success"] == calls, "workers": dict(collections.Counter(r.get("worker_pid") for _, r in res))})
        for kind, r in res:
            pid = r.get("worker_pid")
            if pid in per and per[pid][kind] is None:
                per[pid][kind] = {k: r.get(k) for k in ("http_status", "blocked", "llm_calls", "config_sha256")}
        if all(v["adversarial"] and v["clean"] for v in per.values()):
            break

    def good(v):
        if not (v["adversarial"] and v["clean"]):
            return False
        if v["adversarial"]["config_sha256"] != want_sha or v["clean"]["config_sha256"] != want_sha:
            return False
        if arm in ("R3", "R1024"):
            return v["adversarial"]["blocked"] is True and v["adversarial"]["llm_calls"] == 1 and v["clean"]["blocked"] is False and v["clean"]["llm_calls"] == 3
        return v["adversarial"]["blocked"] is False and v["adversarial"]["llm_calls"] == 1 and v["clean"]["blocked"] is False and v["clean"]["llm_calls"] == 1
    return {"items": {"adversarial": adv["id"], "clean": ok["id"]}, "per_worker": per, "rounds": rounds,
            "pass": bool(per) and all(good(v) for v in per.values()) and all(r["match"] for r in rounds)}


def errors_by_type(art):
    p = os.path.join(art, "profile_export.jsonl")
    if not os.path.exists(p):
        return None
    c, ms = collections.Counter(), []
    for l in open(p, encoding="utf-8"):
        r = json.loads(l); md = r.get("metadata") or {}; e = r.get("error")
        if md.get("benchmark_phase") != "profiling" or not e:
            continue
        c[f"{e.get('code')}|{e.get('type')}"] += 1
        if md.get("request_start_ns") and md.get("request_end_ns"):
            ms.append(round((md["request_end_ns"] - md["request_start_ns"]) / 1e6, 1))
    ms.sort()
    return {"by_type": dict(c), "send_to_error_ms": {"n": len(ms), "min": ms[0] if ms else None, "p50": ms[len(ms) // 2] if ms else None, "max": ms[-1] if ms else None}}


def level(a, arm, w, k, model, n, reqs, seed, art, log, proc, slog, extra):
    os.makedirs(os.path.dirname(art), exist_ok=True)
    cmd = M.aiperf_cmd(a, arm, model, n, reqs, seed, art)
    rec = {"arm": arm, "workers": w, "keep_alive_s": k, "label": label(arm, w, k), "concurrency": n, "requests": reqs, "seed": seed,
           "start": H.now(), "gpu_start": H.gpu(), "command": cmd, **extra}
    samp = CpuSampler(proc.pid) if proc else None
    if samp:
        samp.start()
    off = slog.pos() if slog else 0
    m0 = M.nim_counters()
    with open(art + "_console.txt", "w", encoding="utf-8") as con:
        rc = subprocess.run(cmd, stdout=con, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}).returncode
    m1 = M.nim_counters()
    if samp:
        samp.stop_.set(); samp.join(5)
    time.sleep(1)
    rec.update({"rc": rc, "end": H.now(), "gpu_end": H.gpu(), "nim": M.cdelta(m0, m1), "server_cpu": samp.summary() if samp else None,
                "server_log": slog.counts(off) if slog else None})
    summ = os.path.join(art, "profile_export_aiperf.json")
    if rc == 0 and os.path.exists(summ):
        s = json.load(open(summ, encoding="utf-8"))
        rec["summary"] = {kk: s.get(kk) for kk in ("request_latency", "output_token_throughput", "request_throughput", "request_count", "error_request_count",
                                                   "output_sequence_length", "input_sequence_length", "benchmark_duration", "e2e_output_token_throughput")}
        rec["aiperf_version"] = s.get("aiperf_version")
    rec["raw"] = M.raw_counts(art, ((rec.get("summary") or {}).get("output_token_throughput") or {}).get("avg"))
    rec["errors"] = errors_by_type(art); rec["inputs"] = M.inputs_sha(art)
    log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
    s = rec.get("summary") or {}; cpu = rec.get("server_cpu") or {}
    print(f"  {rec['label']} c={n} rc={rc} tps={(s.get('output_token_throughput') or {}).get('avg')} p99={(s.get('request_latency') or {}).get('p99')} "
          f"err={(s.get('error_request_count') or {}).get('avg')} bound={cpu.get('server_bound')} run95={cpu.get('longest_run_ge_95pct_s_any_process')} "
          f"workers={(rec['server_log'] or {}).get('chat_requests_by_worker')} ka={(rec['server_log'] or {}).get('keepalive_closes')}", flush=True)
    time.sleep(10)
    return rec


def prefix_calibration(arm, model):
    """Two short prompts in a row that share no leading word; the second request's prefix-cache hits are the template's
    fixed prefix (in whole 16-token blocks)."""
    out = []
    for i, text in enumerate(("Name three rivers of Europe and one fact about each.",
                              "Describe how a bicycle gear system changes the effort needed on a hill.")):
        m0 = M.nim_counters(); r = requests.post(M.url_of(arm) + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": text}],
                                                                                              "max_tokens": 16, "temperature": 0.0}, timeout=120)
        m1 = M.nim_counters(); d = M.cdelta(m0, m1)
        out.append({"request": i + 1, "http_status": r.status_code, "prompt_tokens": d and d["prompt_tokens"], "prefix_cache_queries": d and d["prefix_cache_queries"],
                    "prefix_cache_hits": d and d["prefix_cache_hits"], "nim_requests": d and d["request_success"]})
        time.sleep(1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--grpy", required=True); ap.add_argument("--test", action="store_true"); ap.add_argument("--only", default="")
    a = ap.parse_args()
    logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(logdir, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    pd = open(os.path.join(a.out, "part_d_verdicts.jsonl"), "a", encoding="utf-8", newline="\n")
    raw = open(os.path.join(logdir, "part_d_responses.jsonl"), "a", encoding="utf-8", newline="\n")
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": H.now()}, ensure_ascii=False) + "\n"), ev.flush())
    if H.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    if listeners(GR_PORT):
        sys.exit(f"refused: port {GR_PORT} has a listener {listeners(GR_PORT)}")
    qs = json.load(open(os.path.join(REPO, "benchmark", "e3_questions.json"), encoding="utf-8"))
    shas = {cid: __import__("hashlib").sha256(open(os.path.join(a.out, "configs", cid, "config.yml"), "rb").read()).hexdigest() for cid in set(CONFIG.values())}
    tok = H.tokenizer(a.tokenizer)
    st_ = H.start_nim("N-BF16", "p67-nim", logdir)
    if not st_["ready"]:
        event(kind="nim_failed", reason=st_.get("reason")); H.save_logs("p67-nim", logdir); H.stop("p67-nim"); return 1
    time.sleep(5)
    model = requests.get(H.BASE["nim"] + "/v1/models", timeout=30).json()["data"][0]["id"]
    cal = H.calibrate("nim", model, "C", tok)
    rate = 1000.0 / cal["itl_ms_p50"] if cal.get("itl_ms_p50") else None
    share = rate * 16060522496 / 1792e9 if rate else None
    event(kind="nim_start", model=model, image=H.NIM_IMAGE, env=st_["env"], seconds_to_ready=st_["seconds_to_verdict"],
          captured_graph_sizes=st_.get("captured_graph_sizes"), health={"decode_rate_c1_tok_s": rate and round(rate, 2), "share_of_peak": share and round(share, 4),
          "gate": 0.60, "pass": bool(share and share >= 0.60)}, calibration_n_ok=cal["n_ok"])
    print(f"NIM ready · health {share and round(share, 3)}", flush=True)
    plan = [(arm, w, k, [8] if a.test else lv) for arm, w, k, lv in PLAN]
    if a.only:   # harness tests only: labels such as N,R3_W4K75,R3_W8K75
        plan = []
        for lab in a.only.split(","):
            m = re.fullmatch(r"(N|P|R3|R1024)(?:_W(\d+)K(\d+))?", lab)
            plan.append((m.group(1), m.group(2) and int(m.group(2)), m.group(3) and int(m.group(3)), [8]))
    w8_done = False
    queue = list(plan)
    while queue:
        arm, w, k, lv = queue.pop(0)
        lab = label(arm, w, k); variant = "w8" if w == 8 else None
        print(f"##### {lab} {H.now()}", flush=True)
        if arm == "N":
            proc, info, slog = None, {}, None
        else:
            proc, info = gr_start(arm, w, k, a, logdir)
            slog = ServerLog(os.path.join(logdir, f"gr_server_{lab}.log.txt"))
            if proc is None or not info.get("all_workers_answering"):
                event(kind="gr_failed", label=lab, arm=arm, workers=w, keep_alive_s=k, info=info); gr_stop(proc); continue
        iso = H.isolation("nim")
        calib = prefix_calibration(arm, model) if arm in ("N", "P") else None
        if arm == "N":
            g2 = M.g2_probe(arm, model, qs)
        else:
            g2 = g2_workers(arm, model, qs, info["workers_answering"], shas[CONFIG[arm]])
        event(kind="server_start", label=lab, arm=arm, workers=w, keep_alive_s=k, variant=variant, config=CONFIG.get(arm),
              config_sha256=shas.get(CONFIG.get(arm)), server=info, isolation=iso, g2=g2, prefix_calibration=calib)
        print(f"  {lab}: g2 pass={g2['pass']} workers={info.get('workers_answering')} restarts={info.get('listen_winerror_10022')}", flush=True)
        level(a, arm, w, k, model, 8, 50 if a.test else 100, SEED0 + 9000, os.path.join(a.out, lab, "warmup"), log, proc, slog, {"warmup": True, "variant": variant})
        cells = {}
        for n in lv:
            reqs = (2 * n if a.test else max(10 * n, 200))
            cells[n] = level(a, arm, w, k, model, n, reqs, SEED0 + n, os.path.join(a.out, lab, f"c{n:04d}"), log, proc, slog, {"variant": variant})
        if (arm, w, k) == PART_D_AT:
            bg_n = 16 if a.test else 128; cond = f"c{bg_n}_W{w}K{k}"
            bg_art = os.path.join(a.out, lab, f"partd_background_c{bg_n}")
            bg = subprocess.Popen(M.aiperf_cmd(a, arm, model, bg_n, bg_n * 200, SEED0 + 7000, bg_art, export="summary"),
                                  stdout=open(bg_art + "_console.txt", "w", encoding="utf-8"), stderr=subprocess.STDOUT,
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
            time.sleep(30 if not a.test else 10)
            event(kind="part_d_background", label=lab, concurrency=bg_n, started_seconds_before=30 if not a.test else 10, running=bg.poll() is None)
            print(f"  {lab}: Part D under c={bg_n} {H.now()} (background running={bg.poll() is None})", flush=True)
            off = slog.pos(); samp = CpuSampler(proc.pid); samp.start()
            M.part_d(a, arm, model, qs, cond, pd, raw)
            samp.stop_.set(); samp.join(5)
            still = bg.poll() is None
            for q in reversed(tree(bg.pid)):
                try:
                    q.kill()
                except psutil.Error:
                    pass
            bg.wait(60)
            event(kind="part_d_background_end", label=lab, running_until_part_d_end=still, server_cpu=samp.summary(), server_log=slog.counts(off))
            time.sleep(10)
        stop = gr_stop(proc)
        event(kind="server_end", label=lab, stop=stop, server_log_total=slog.counts(0) if slog else None)
        if (arm, w, k) == W8_BRANCH[:3] and not w8_done and not a.test:
            c = cells.get(W8_BRANCH[3]); bound = bool(((c or {}).get("server_cpu") or {}).get("server_bound"))
            event(kind="w8_branch", checked_cell=f"{lab}|{W8_BRANCH[3]}", server_bound=bound, run=bound)
            if bound:
                queue.insert(0, ("R3", 8, 75, [128])); w8_done = True
        time.sleep(30 if not a.test else 5)
    H.save_logs("p67-nim", logdir); H.stop("p67-nim")
    event(kind="nim_end", gpu_after_stop=H.gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
