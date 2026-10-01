#!/usr/bin/env python3
"""Vol.2 · P78 G2 / G3 (and G4's quality arms) · answer quality of the two Nemotron models with reasoning on and off.

Tasks and harness: lm-evaluation-harness 0.4.13 (pinned venv), `local-chat-completions`, gsm8k_cot_llama (all 1,319
test items, 8-shot, multi-turn chat) and mmlu_llama restricted to P62's pre-registered 50 x 57 sample (2,850 items),
--apply_chat_template, --fewshot_as_multiturn, temperature 0, the task's own prompts. lm-eval runs in chunks, each in its
own process (p78_lmeval_chunk.py), so a chunk that hangs can be stopped from outside, an engine that exits costs one
chunk, and results land on disk chunk by chunk.

The logging proxy between lm-eval and the engine applies the same, pre-registered request changes to every arm, because
the two task configurations were written for a model that answers at once:
  - `stop` removed (gsm8k_cot_llama stops at "Q:", which a reasoning model can write inside its reasoning);
  - mmlu_llama's trailing assistant message "The best answer is" removed, with continue_final_message and
    add_generation_prompt (a model that continues that prefix answers without reasoning; the prompt itself asks for
    "The best answer is [letter]");
  - max_tokens set to 8,192 with reasoning on and 1,024 with reasoning off (the task's own 256 / 10 would cut a
    reasoning model off before its answer; too small a cap returns content null without an error);
  - reasoning off: Nemotron 3 Nano and the upstream arms on its weights get chat_template_kwargs {"enable_thinking": false};
    Nemotron Nano 9B v2 gets a system message "/no_think" (the switch each model card documents; P55).
The proxy records per request the sha256 of the messages lm-eval sent (the join key), of the body sent upstream, the
changes applied, the server's token counts, finish_reason, whether content was null (then "" is passed to lm-eval), and
the output (content and any reasoning channel) with its sha256. The output text goes to the process bucket outside the
repository; the repository gets per-item fields only. Items are scored by p78_scorer.py on the whole output (reasoning
channel, then content): the last answer in the task's format wins. lm-eval's own metrics are kept for reference.

Cells: one container per arm; each cell = one task x reasoning mode x run. Before every cell G8 (tools/g8_gate.py) must
pass; per cell the host record (tools/host_gate.py); after every cell the no-overwrite check (tools/overwrite_gate.py).
A cell with any HTTP 400 from the engine (a prompt that did not fit) is void. If the engine exits, its log tail is kept,
the container is started again and the cell resumes at the chunk that failed; a second exit in the same cell makes the
cell null. A chunk that exceeds its timeout is stopped and retried once. Paths come from this file's location.
usage: p78_quality.py --arms N3,N2 --lmpy PY --raw DIR [--out DIR] [--deadline HH:MM] [--test N] [--mock]
env: NGC_ENV_FILE (NIM, --env-file, never read) · NIM_CACHE_DIR · V_CACHE_DIR
"""
import argparse, datetime, hashlib, http.client, http.server, json, os, socketserver, statistics as st, subprocess, sys, threading, time, urllib.parse

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))
import p78_engines as E  # noqa: E402
import p78_scorer as SC  # noqa: E402
import g8_gate as G  # noqa: E402
import host_gate as HG  # noqa: E402
import overwrite_gate as O  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
O.SCOPES = O.SCOPES + sorted(d for d in os.listdir(REPO) if d.startswith("vol") and d not in O.SCOPES)   # the gate file is bound; its list is extended here
RESULTS = os.path.join(HERE, "..", "results")
DEFAULT_OUT = os.path.join(RESULTS, "p78_quality")
MMLU_IDS = next(os.path.join(REPO, d, "results", "p62_quality", "mmlu_sample_ids.json") for d in sorted(os.listdir(REPO))
                if os.path.exists(os.path.join(REPO, d, "results", "p62_quality", "mmlu_sample_ids.json")))
GSM_N = 1319
CAP = {"on": 8192, "off": 1024}
MAX_MODEL_LEN = "16384"
PROXY_PORT = 18081
CHUNK_GSM, CHUNK_MMLU_SUBJ = 110, 5
PEAK, HEALTH_MIN = 1792e9, 0.10
PLAN = {
    "N3": [("on_gsm8k_1", "gsm8k", "on", 16, None), ("on_mmlu", "mmlu", "on", 16, None), ("off_gsm8k", "gsm8k", "off", 16, None),
           ("off_mmlu", "mmlu", "off", 16, None), ("on_gsm8k_2", "gsm8k", "on", 16, None), ("off_gsm8k_c1_first200", "gsm8k", "off", 1, 200)],
    "N2": [("on_gsm8k_1", "gsm8k", "on", 16, None), ("on_mmlu", "mmlu", "on", 16, None), ("off_gsm8k", "gsm8k", "off", 16, None),
           ("off_mmlu", "mmlu", "off", 16, None), ("on_gsm8k_2", "gsm8k", "on", 16, None)],
    "V3B1": [("off_gsm8k", "gsm8k", "off", 16, None)],
    "V3B2": [("off_gsm8k", "gsm8k", "off", 16, None)],
}
FAMILY = {"N3": "n3", "V3B1": "n3", "V3B2": "n3", "N2": "n2", "V2N": "n2"}
canon = lambda o: json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
sha = lambda b: hashlib.sha256(b).hexdigest()
now = lambda: datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- request changes (pre-registered)
def transform(req, family, mode):
    ch = []
    if "stop" in req:
        req.pop("stop"); ch.append("stop_removed")
    msgs = list(req.get("messages") or [])
    if msgs and msgs[-1].get("role") == "assistant" and (msgs[-1].get("content") or "").strip() == "The best answer is":
        msgs.pop(); ch.append("mmlu_prefill_removed")
    for k in ("continue_final_message", "add_generation_prompt", "max_completion_tokens"):
        if k in req:
            req.pop(k); ch.append(f"{k}_removed")
    req["max_tokens"] = CAP[mode]; ch.append(f"max_tokens={CAP[mode]}")
    if mode == "off":
        if family == "n3":
            req["chat_template_kwargs"] = {"enable_thinking": False}; ch.append("enable_thinking=false")
        else:
            msgs = [{"role": "system", "content": "/no_think"}] + msgs; ch.append("system=/no_think")
    req["messages"] = msgs
    return req, ch


# ---------------------------------------------------------------- logging proxy
class Proxy:
    def __init__(self, upstream, family, mode):
        self.up = urllib.parse.urlparse(upstream); self.family, self.mode = family, mode
        self.lock = threading.Lock(); self.tl = threading.local(); self.rows = []; self.raw = None
        proxy = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                rec = {"t_start": time.time()}; text = {"content": None, "reasoning": None}
                try:
                    req = json.loads(body.decode("utf-8"))
                    rec["messages_sha"] = sha(canon(req.get("messages")))
                    req, ch = transform(req, proxy.family, proxy.mode)
                    rec["changes"] = ch; rec["sent_request_sha"] = sha(canon({k: v for k, v in req.items() if k != "model"}))
                    body = json.dumps(req, ensure_ascii=False).encode("utf-8")
                except Exception as e:
                    rec["request_error"] = str(e)[:200]
                status, data = 502, b'{"error":"proxy: upstream unreachable"}'
                for attempt in (1, 2):
                    try:
                        c = getattr(proxy.tl, "conn", None)
                        if c is None:
                            c = proxy.tl.conn = http.client.HTTPConnection(proxy.up.hostname, proxy.up.port, timeout=3600)
                        c.request("POST", self.path, body=body, headers={"Content-Type": "application/json", "Connection": "keep-alive"})
                        r = c.getresponse(); status, data = r.status, r.read(); rec.pop("upstream_error", None); break
                    except Exception as e:
                        rec["upstream_error"] = f"attempt {attempt}: {str(e)[:200]}"
                        try:
                            proxy.tl.conn.close()
                        except Exception:
                            pass
                        proxy.tl.conn = None
                rec.update({"t_end": time.time(), "status": status})
                if status == 200:
                    try:
                        out = json.loads(data.decode("utf-8")); chh = (out.get("choices") or [{}])[0]; msg = chh.get("message") or {}
                        text = {"content": msg.get("content"), "reasoning": msg.get("reasoning_content") or msg.get("reasoning")}
                        rec.update({"finish_reason": chh.get("finish_reason"), "usage": out.get("usage"), "content_null": msg.get("content") is None,
                                    "reasoning_channel": bool(text["reasoning"]), "content_chars": len(text["content"] or ""),
                                    "reasoning_chars": len(text["reasoning"] or ""),
                                    "output_sha": sha(SC.full_text(text["content"], text["reasoning"]).encode("utf-8"))})
                        if msg.get("content") is None:      # lm-eval cannot take a null; it gets "" and the record says so
                            msg["content"] = ""; data = json.dumps(out, ensure_ascii=False).encode("utf-8")
                    except Exception as e:
                        rec["response_parse_error"] = str(e)[:200]
                else:
                    rec["error_head"] = data[:300].decode("utf-8", "replace")
                with proxy.lock:
                    proxy.rows.append((rec, text))
                    if proxy.raw:
                        proxy.raw.write(json.dumps({**rec, **text}, ensure_ascii=False) + "\n"); proxy.raw.flush()
                try:
                    self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data)))
                    self.end_headers(); self.wfile.write(data)
                except (ConnectionError, OSError):    # lm-eval closed its end first (its retries after an engine exit); the record is kept
                    pass

        class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

            def handle_error(self, request, client_address):     # a client that reset its connection (lm-eval retrying after an engine exit)
                proxy.dropped = getattr(proxy, "dropped", 0) + 1
        self.srv = Server(("127.0.0.1", PROXY_PORT), Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def take(self):
        with self.lock:
            rows, self.rows = self.rows, []
        return rows

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


# ---------------------------------------------------------------- chunks
def chunks_for(task, limit, test):
    if task == "gsm8k":
        ids = list(range(GSM_N))[: (test or limit or GSM_N)]
        step = min(CHUNK_GSM, max(1, len(ids) // 2)) if test else CHUNK_GSM
        return [("gsm8k_cot_llama", {"gsm8k_cot_llama": ids[i:i + step]}) for i in range(0, len(ids), step)]
    ids = json.load(open(MMLU_IDS, encoding="utf-8"))["ids"]
    subj = sorted(ids)
    if test:
        subj = subj[:2]; ids = {s: ids[s][:max(1, test // 2)] for s in subj}
    return [(",".join(g), {s: ids[s] for s in g}) for g in (subj[i:i + CHUNK_MMLU_SUBJ] for i in range(0, len(subj), CHUNK_MMLU_SUBJ))]


def kill_tree(pid):
    try:
        import psutil
        p = psutil.Process(pid)
        for k in p.children(recursive=True):
            k.kill()
        p.kill()
    except Exception:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def run_chunk(a, model, tasks, ids, conc, mode, cdir, timeout_s):
    os.makedirs(cdir, exist_ok=True)
    idf = os.path.join(cdir, "ids.json"); json.dump(ids, open(idf, "w", encoding="utf-8"))
    cmd = [a.lmpy, os.path.join(HERE, "p78_lmeval_chunk.py"), "--tasks", tasks, "--ids", idf, "--model", model,
           "--base", f"http://127.0.0.1:{PROXY_PORT}/v1/chat/completions", "--conc", str(conc), "--max-gen", str(CAP[mode]), "--out", cdir]
    env = {**os.environ, "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1"}
    t0 = time.time()
    with open(os.path.join(cdir, "chunk.stdout.txt"), "w", encoding="utf-8") as so, open(os.path.join(cdir, "chunk.stderr.txt"), "w", encoding="utf-8") as se:
        p = subprocess.Popen(cmd, stdout=so, stderr=se, env=env)
        try:
            rc = p.wait(timeout=timeout_s); hung = False
        except subprocess.TimeoutExpired:
            kill_tree(p.pid); rc = None; hung = True
    return {"rc": rc, "hung": hung, "seconds": round(time.time() - t0, 1), "timeout_s": timeout_s}


def join_and_score(task_kind, cdir, rows):
    """docs.jsonl (lm-eval's documents with the sha of the messages it sent and the gold answer) x the proxy's records."""
    docs = [json.loads(l) for l in open(os.path.join(cdir, "docs.jsonl"), encoding="utf-8")] if os.path.exists(os.path.join(cdir, "docs.jsonl")) else []
    by_sha = {}
    for rec, text in sorted(rows, key=lambda x: x[0]["t_start"]):
        if rec.get("status") == 200 and "messages_sha" in rec:
            by_sha.setdefault(rec["messages_sha"], []).append((rec, text))
    items, unjoined = [], 0
    for d in docs:
        cands = by_sha.get(d["messages_sha"]) or []
        if not cands:
            unjoined += 1; continue
        rec, text = cands.pop(0)
        s = SC.score("gsm8k" if task_kind == "gsm8k" else "mmlu", text["content"], text["reasoning"], d["gold"])
        u = rec.get("usage") or {}
        items.append({"task": d["task"], "doc_id": d["doc_id"], "messages_sha": d["messages_sha"], "sent_request_sha": rec.get("sent_request_sha"),
                      "output_sha": rec.get("output_sha"), "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                      "finish_reason": rec.get("finish_reason"), "hit_cap": rec.get("finish_reason") == "length", "content_null": rec.get("content_null"),
                      "reasoning_channel": rec.get("reasoning_channel"), "content_chars": rec.get("content_chars"), "reasoning_chars": rec.get("reasoning_chars"),
                      "seconds": round(rec["t_end"] - rec["t_start"], 3), "t_start": rec["t_start"], "t_end": rec["t_end"],
                      "extracted": s["extracted"], "gold": d["gold"], "correct": s["correct"], "no_answer": s["no_answer"]})
    return items, {"docs": len(docs), "items": len(items), "unjoined": unjoined,
                   "non_200": sum(1 for r, _ in rows if r.get("status") != 200), "http_400": sum(1 for r, _ in rows if r.get("status") == 400),
                   "changes_seen": sorted({",".join(r.get("changes") or []) for r, _ in rows})[:4]}


# ---------------------------------------------------------------- engine lifecycle
class Engine:
    def __init__(self, a, arm, logdir, ev, extra_args=None):
        self.a, self.arm, self.logdir, self.ev = a, arm, logdir, ev
        self.name = f"p78q-{arm.lower()}"; self.starts = 0; self.extra_args = extra_args or []

    def start(self):
        self.starts += 1
        name = self.cur = f"{self.name}-{self.starts}"
        if self.a.mock:        # harness test: the stand-in server; the first start exits after --mock-die-after requests
            port = urllib.parse.urlparse(self.a.mock_base).port
            cmd = [sys.executable, os.path.join(HERE, "p78_mock_openai.py"), "--port", str(port), "--log", os.path.join(self.logdir, "mock_requests.jsonl")]
            if self.starts == 1 and self.a.mock_die_after:
                cmd += ["--die-after", str(self.a.mock_die_after)]
            self.mock_proc = subprocess.Popen(cmd); time.sleep(1.5)
            return {"ready": True, "mock": True, "die_after": self.a.mock_die_after if self.starts == 1 else 0}
        env = {"NIM_MAX_MODEL_LEN": MAX_MODEL_LEN} if self.arm in ("N3", "N2") else {}
        args = [] if self.arm == "V3B1" else (self.extra_args if self.arm in ("V3B2", "V2N") else [])
        st_ = E.launch(self.arm, name, self.logdir, env=env, args=args)
        self.cur = name
        return st_

    def stop(self):
        if self.a.mock:
            if getattr(self, "mock_proc", None) and self.mock_proc.poll() is None:
                self.mock_proc.kill(); self.mock_proc.wait(10)
            return
        E.save_logs(self.cur, self.logdir); E.stop(self.cur)

    def alive(self, model):
        return E.alive(model)


def stream_rate(model, fam, max_tokens=400):
    """One streamed request; generation rate = completion tokens after the first / (end - first token)."""
    body = {"model": model, "messages": [{"role": "user", "content": "Write a detailed explanation of how a refrigerator moves heat, in about 350 words."}],
            "max_tokens": max_tokens, "temperature": 0, "stream": True, "stream_options": {"include_usage": True}}
    if fam == "n3":
        body["chat_template_kwargs"] = {"enable_thinking": False}
    else:
        body["messages"] = [{"role": "system", "content": "/no_think"}] + body["messages"]
    t0 = time.perf_counter(); first = None; usage = None
    with requests.post(E.BASE + "/v1/chat/completions", json=body, stream=True, timeout=600) as r:
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: ") or line.endswith("[DONE]"):
                continue
            j = json.loads(line[6:])
            if j.get("usage"):
                usage = j["usage"]
            for c in j.get("choices") or []:
                d = c.get("delta") or {}
                if (d.get("content") or d.get("reasoning_content") or d.get("reasoning")) and first is None:
                    first = time.perf_counter()
    t1 = time.perf_counter(); n = (usage or {}).get("completion_tokens")
    return (n - 1) / (t1 - first) if (n and first and t1 > first and n > 1) else None


def warm_and_health(arm, model):
    fam = FAMILY[arm]; rates = []; t0 = time.time()
    warm = []
    while time.time() - t0 < 300:                        # A2 serves at half speed for 10-50 s after READY (P55); warm until stable
        r = stream_rate(model, fam, 200); warm.append(r and round(r, 1))
        if len(warm) >= 3 and r and (fam == "n2" or r >= 220):
            break
    for _ in range(5):
        r = stream_rate(model, fam); rates.append(r)
    ok = [x for x in rates if x]
    rate = st.median(ok) if ok else None
    share = rate * E.IMAGES[arm]["bytes_per_token"] / PEAK if rate else None
    return {"warmup_rates": warm, "rates": [x and round(x, 2) for x in rates], "rate_median": rate and round(rate, 2),
            "bytes_per_token": E.IMAGES[arm]["bytes_per_token"], "share_of_peak": share and round(share, 4), "pass": bool(share and share >= HEALTH_MIN)}


def run_cell(a, arm, eng, model, cell, ev, items_f, raw_dir, state):
    cid, task, mode, conc, limit = cell
    event = lambda **kw: (ev.write(json.dumps({**kw, "arm": arm, "cell": cid, "at": now()}, ensure_ascii=False) + "\n"), ev.flush())
    fam = FAMILY[arm]
    chunks = chunks_for(task, limit, a.test)
    proxy = Proxy(E.BASE, fam, mode)
    exits, done, per_item_s, summary = 0, [], [], {"chunks": len(chunks), "http_400": 0, "items": 0, "unjoined": 0, "hung_chunks": 0, "failed_chunks": 0}
    os.makedirs(raw_dir, exist_ok=True)
    proxy.raw = open(os.path.join(raw_dir, f"{arm}__{cid}.proxy.jsonl"), "a", encoding="utf-8", newline="\n")
    k = 0; retried = set(); null_reason = None
    while k < len(chunks):
        tasks, ids = chunks[k]; n_items = sum(len(v) for v in ids.values())
        if per_item_s:
            timeout_s = max(600, int(3 * st.mean(per_item_s) * n_items))
        else:   # first chunk: every item at the cap, at the single-stream rate, per stream (an upper bound, not x3)
            timeout_s = max(600, int(n_items * CAP[mode] / (conc * max(20.0, state.get("rate") or 20.0))))
        cdir = os.path.join(raw_dir, f"{arm}__{cid}", f"chunk{k:02d}")
        r = run_chunk(a, model, tasks, ids, conc, mode, cdir, timeout_s)
        rows = proxy.take()
        items, j = join_and_score(task, cdir, rows)
        summary["http_400"] += j["http_400"]
        event(kind="chunk", chunk=k, tasks=tasks, n_items=n_items, run=r, join=j)
        print(f"    {arm} {cid} chunk {k}: rc={r['rc']} hung={r['hung']} {r['seconds']} s items {j['items']}/{j['docs']} non200={j['non_200']}", flush=True)
        if j["http_400"]:
            null_reason = "an HTTP 400 from the engine (a prompt that did not fit): the measurement is broken"; break
        if r["rc"] == 0 and j["items"] == j["docs"] == n_items:
            with open(items_f, "a", encoding="utf-8", newline="\n") as f:
                for it in items:
                    f.write(json.dumps({"arm": arm, "cell": cid, "chunk": k, **it}, ensure_ascii=False, sort_keys=True) + "\n")
            summary["items"] += len(items)
            per_item_s.append(r["seconds"] / max(1, n_items))
            k += 1; continue
        # the chunk did not complete: engine exit, hang or lm-eval error
        dead = not (a.mock or E.container_running(eng.cur)) or not eng.alive(model)
        if r["hung"]:
            summary["hung_chunks"] += 1
        if dead:
            exits += 1
            tail = "" if a.mock else E.save_logs(eng.cur, eng.logdir)[-4000:]
            event(kind="engine_exit", chunk=k, exits_in_cell=exits, log_tail=tail[-1500:])
            if exits >= 2:
                null_reason = "the engine exited twice in this cell"; break
            eng.stop(); st_ = eng.start()
            event(kind="engine_restart", chunk=k, start=st_)
            if not st_.get("ready"):
                null_reason = "the engine did not start again"; break
            continue                                   # resume at the same chunk
        if k in retried:
            summary["failed_chunks"] += 1; k += 1; continue
        retried.add(k)
    proxy.raw.close(); proxy.close()
    summary["engine_exits"] = exits; summary["null_reason"] = null_reason
    return summary


def run_arm(a, arm, ev, items_f, logdir, snap, state):
    event = lambda **kw: (ev.write(json.dumps({**kw, "arm": arm, "at": now()}, ensure_ascii=False) + "\n"), ev.flush())
    extra = []
    if arm in ("V3B2",) and not a.mock:
        d = E.dryrun("N3", {"NIM_MAX_MODEL_LEN": MAX_MODEL_LEN}, os.path.join(logdir, "dryrun_N3.txt"))
        extra, edits = E.upstream_args_from(d["backend_args"] or [], E.IMAGES["V3B2"]["snapshot"])
        event(kind="dryrun", selected_profile=d.get("selected_profile"), backend_args=d.get("backend_args"), upstream_args=extra, edits=edits, rc=d.get("rc"))
        if not d.get("backend_args"):
            event(kind="arm_null", reason="the NIM dry-run gave no argument list"); return True
    eng = Engine(a, arm, logdir, ev, extra)
    st_ = eng.start()
    event(kind="engine_start", start=st_)
    if not st_.get("ready"):
        event(kind="arm_null", reason="the engine did not start", start=st_); eng.stop(); return True
    model = "mock" if a.mock else E.served_model()
    health = {"pass": True, "mock": True} if a.mock else warm_and_health(arm, model)
    state["rate"] = health.get("rate_median")
    event(kind="health", **health)
    print(f"  {arm}: model={model} health={health.get('share_of_peak')} pass={health['pass']}", flush=True)
    if not health["pass"]:
        event(kind="arm_null", reason="arm health below 10% of peak bandwidth"); eng.stop(); return True
    ok = True
    for cell in PLAN[arm]:
        if a.deadline and datetime.datetime.now().strftime("%H:%M") >= a.deadline and datetime.datetime.now().hour < 12:
            event(kind="cell_not_started", cell=cell[0], reason=f"deadline {a.deadline} reached"); continue
        g8 = {"pass": True, "mock": True} if a.mock else G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S)
        event(kind="g8", cell=cell[0], **g8)
        if not g8["pass"]:
            event(kind="cell_null", cell=cell[0], reason="G8 did not pass within the wait limit"); continue
        hg = HG.cell_start()
        t0 = now()
        summ = run_cell(a, arm, eng, model, cell, ev, items_f, os.path.join(a.raw, arm), state)
        event(kind="cell_end", cell=cell[0], task=cell[1], mode=cell[2], concurrency=cell[3], limit=cell[4], start=t0, end=now(), summary=summ, host=HG.cell_end(hg))
        print(f"  {arm} {cell[0]}: {summ}", flush=True)
        ov = O.check(snap)
        event(kind="overwrite_check", cell=cell[0], **ov)
        if not ov["pass"]:
            print(f"  NO-OVERWRITE GATE FAILED after {arm} {cell[0]}: {ov['violations'][:3]}", flush=True); ok = False; break
    eng.stop()
    event(kind="engine_end", gpu_after_stop=None if a.mock else E.gpu())
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", required=True); ap.add_argument("--lmpy", required=True)
    ap.add_argument("--out", default=DEFAULT_OUT); ap.add_argument("--raw", required=True)   # the process bucket, outside the repository
    ap.add_argument("--deadline"); ap.add_argument("--test", type=int, default=0)
    ap.add_argument("--mock", action="store_true"); ap.add_argument("--mock-base", default="http://127.0.0.1:18090"); ap.add_argument("--mock-die-after", type=int, default=0)
    a = ap.parse_args(); a.out = os.path.abspath(a.out); a.raw = os.path.abspath(a.raw)
    if a.mock:
        E.BASE = a.mock_base
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    snap = O.snapshot(REPO, [os.path.relpath(a.out.split(os.sep + "harness_test")[0], REPO).replace(os.sep, "/")])   # the stage's results directory (its logs/ and harness_test/ included)
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    ev.write(json.dumps({"kind": "run_start", "arms": a.arms, "test": a.test, "mock": a.mock, "caps": CAP, "max_model_len": MAX_MODEL_LEN, "plan": PLAN,
                         "overwrite_snapshot": {"allowed": snap["allowed"], "watched": len(snap["others"])}, "host_calibration": HG.calibrate(),
                         "scorer_self_test_fails": SC.self_test(quiet=True), "at": now()}, ensure_ascii=False) + "\n"); ev.flush()
    if not a.mock and E.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    items_f = os.path.join(a.out, "items.jsonl"); state = {}
    for arm in a.arms.split(","):
        print(f"##### arm {arm} {now()}", flush=True)
        if not run_arm(a, arm, ev, items_f, logdir, snap, state):
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
