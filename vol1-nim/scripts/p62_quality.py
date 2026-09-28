#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q1 · answer quality of the four P59 configurations on three public task sets.

lm-evaluation-harness (pinned, run from this process through its Python API) with the `local-chat-completions` backend,
the same task configuration for every arm, each arm's own /v1/chat/completions. A logging proxy on 127.0.0.1 sits
between lm-eval and the server and records, per request: the sha256 of the request body without its "model" field (the
field that differs by arm), the sha256 of its messages, the server's prompt and completion token counts, finish_reason,
and the output text (process bucket only) with its sha256 and length.

Arms (images, profiles, slot counts as P59): O-Q4 (Ollama 4-bit, NUM_PARALLEL 16) · N-BF16 · O-FP16 (NUM_PARALLEL 8) ·
N-FP8; context 8,192 on every arm. Per arm, before any task: isolation, residency (Ollama `ollama ps` 100% GPU; NIM CUDA
graphs captured), P59's health gate (decode rate at c=1 from the harness's own 20 calibration requests x bytes per
token / 1,792 GB/s >= 0.40), `ollama show` (quantization as the model reports it) and a template probe (prompt tokens the
server counts for a one-word message).
Tasks: gsm8k_cot_llama (8-shot, multi-turn chat), ifeval, mmlu_llama restricted to the pre-registered 50 x 57 sample
(mmlu_sample_ids.json); --apply_chat_template, --fewshot_as_multiturn, concurrency 8, temperature 0, each task's own
generation settings. mmlu_llama ends every prompt with an assistant message holding the start of the answer ("The best
answer is"); the request carries continue_final_message=true and add_generation_prompt=false on every arm so that an
engine continues that message instead of opening a new turn (Ollama continues a trailing assistant message by itself;
the fields are sent to it too, so the request bodies stay identical).
Extra runs: N-BF16 repeats all three tasks (noise floor); N-FP8 runs GSM8K again at concurrency 1 and 32.
usage: p62_quality.py --out DIR --tokenizer DIR --store DIR [--arms a,b] [--test N]
env: NGC_ENV_FILE (NIM arms, --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, hashlib, http.client, http.server, json, os, socketserver, sys, threading, time, urllib.parse

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p59_nim_value as H  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ORDER = ["O-Q4", "N-BF16", "O-FP16", "N-FP8"]
SLOTS = {"O-Q4": 16, "O-FP16": 8}
TASKS = {"gsm8k": "gsm8k_cot_llama", "ifeval": "ifeval", "mmlu": "mmlu_llama"}
RUNS = {"O-Q4": [(t, 8, "main") for t in TASKS], "O-FP16": [(t, 8, "main") for t in TASKS],
        "N-BF16": [(t, 8, "main") for t in TASKS] + [(t, 8, "repeat") for t in TASKS],
        "N-FP8": [(t, 8, "main") for t in TASKS] + [("gsm8k", 1, "c1"), ("gsm8k", 32, "c32")]}
MMLU_EXTRA = {"continue_final_message": True, "add_generation_prompt": False}
PROXY_PORT = 18080
IDS = os.path.join(HERE, "..", "results", "p62_quality", "mmlu_sample_ids.json")
PEAK, HEALTH = 1792e9, 0.40
BYTES = {"O-Q4": 4920738944, "O-FP16": 16068895872, "N-BF16": 16060522496, "N-FP8": 9081280648}   # P59's table
canon = lambda o: json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
sha = lambda b: hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- logging proxy
class Proxy:
    def __init__(self, upstream, log_path):
        self.up = urllib.parse.urlparse(upstream); self.lock = threading.Lock()
        self.f = open(log_path, "a", encoding="utf-8", newline="\n"); self.n = 0; self.tl = threading.local()
        proxy = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                t0 = time.time(); rec = {"t_start": t0, "path": self.path}
                try:
                    req = json.loads(body.decode("utf-8"))
                    rec["request_sha"] = sha(canon({k: v for k, v in req.items() if k != "model"}))
                    rec["messages_sha"] = sha(canon(req.get("messages")))
                    rec["request_keys"] = sorted(req.keys())
                    rec["gen"] = {k: v for k, v in req.items() if k not in ("messages", "model")}
                except Exception as e:
                    rec["request_parse_error"] = str(e)[:200]
                status, data, ctype = 502, b"", "application/json"
                for attempt in (1, 2):   # one kept-alive upstream connection per handler thread (a new one per request exhausts local ports)
                    try:
                        c = getattr(proxy.tl, "conn", None)
                        if c is None:
                            c = proxy.tl.conn = http.client.HTTPConnection(proxy.up.hostname, proxy.up.port, timeout=1800)
                        c.request("POST", self.path, body=body, headers={"Content-Type": "application/json", "Connection": "keep-alive"})
                        r = c.getresponse(); status, data, ctype = r.status, r.read(), r.getheader("Content-Type", "application/json")
                        rec.pop("upstream_error", None); break
                    except Exception as e:
                        rec["upstream_error"] = f"attempt {attempt}: {str(e)[:300]}"
                        try:
                            proxy.tl.conn.close()
                        except Exception:
                            pass
                        proxy.tl.conn = None
                rec.update({"t_end": time.time(), "status": status})
                try:
                    out = json.loads(data.decode("utf-8")); ch = (out.get("choices") or [{}])[0]
                    text = ((ch.get("message") or {}).get("content")) or ""
                    rec.update({"finish_reason": ch.get("finish_reason"), "usage": out.get("usage"), "output": text,
                                "output_sha": sha(text.encode("utf-8")), "output_chars": len(text)})
                except Exception:
                    rec["response_head"] = data[:300].decode("utf-8", "replace")
                with proxy.lock:
                    proxy.f.write(json.dumps(rec, ensure_ascii=False) + "\n"); proxy.f.flush(); proxy.n += 1
                self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
                self.end_headers(); self.wfile.write(data)

        class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True
        self.srv = Server(("127.0.0.1", PROXY_PORT), Handler)
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True); self.th.start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close(); self.f.close()


# ---------------------------------------------------------------- per-item public fields
def letter(x):
    s = (x or "").strip().rstrip(".").strip()
    return s if s in ("A", "B", "C", "D") else "[other]"


def public_items(task_key, samples_by_task, proxy_rows):
    """Join lm-eval's logged samples to the proxy log by the sha of the messages; keep machine fields only."""
    by_msg = {}
    for r in proxy_rows:
        if r.get("status") == 200 and "messages_sha" in r:
            by_msg.setdefault(r["messages_sha"], []).append(r)
    items, unjoined, ambiguous, text_mismatch = [], 0, 0, 0
    for sub, rows in sorted(samples_by_task.items()):
        per_doc = {}
        for s in rows:
            per_doc.setdefault(s["doc_id"], {})[s.get("filter")] = s
        for doc_id, fs in sorted(per_doc.items()):
            s0 = next(iter(fs.values()))
            ctx = s0["arguments"]["gen_args_0"]["arg_0"] if isinstance(s0["arguments"], dict) else s0["arguments"][0][0]
            while isinstance(ctx, (list, tuple)) and ctx and not isinstance(ctx[0], dict):   # [[ctx], gen_kwargs] -> [ctx] -> ctx
                ctx = ctx[0]
            msgs = json.loads(ctx) if isinstance(ctx, str) else ctx
            msha = sha(canon(msgs)); hits = by_msg.get(msha, [])
            if not hits:
                unjoined += 1; p = {}
            else:
                if len({h["output_sha"] for h in hits}) > 1:
                    ambiguous += 1
                p = hits[-1]
            resp = s0["resps"][0][0] if s0.get("resps") else ""
            if p and sha(resp.encode("utf-8")) != p.get("output_sha"):
                text_mismatch += 1
            it = {"task": sub, "doc_id": doc_id, "request_sha": p.get("request_sha"), "messages_sha": msha,
                  "output_sha": p.get("output_sha"), "output_chars": p.get("output_chars"),
                  "prompt_tokens": (p.get("usage") or {}).get("prompt_tokens"), "completion_tokens": (p.get("usage") or {}).get("completion_tokens"),
                  "finish_reason": p.get("finish_reason"), "requests_seen": len(hits)}
            if task_key == "gsm8k":
                st_, fl = fs.get("strict-match") or {}, fs.get("flexible-extract") or {}
                it.update({"correct": int(st_.get("exact_match", 0) == 1), "correct_flexible": int(fl.get("exact_match", 0) == 1),
                           "extracted": (st_.get("filtered_resps") or [None])[0], "extracted_flexible": (fl.get("filtered_resps") or [None])[0]})
            elif task_key == "mmlu":
                st_ = fs.get("strict_match") or s0
                it.update({"correct": int(st_.get("exact_match", 0) == 1), "extracted": letter((st_.get("filtered_resps") or [None])[0])})
            else:
                it.update({"correct": int(bool(s0.get("prompt_level_strict_acc"))), "prompt_level_loose": int(bool(s0.get("prompt_level_loose_acc"))),
                           "inst_strict": [int(bool(x)) for x in (s0.get("inst_level_strict_acc") or [])],
                           "inst_loose": [int(bool(x)) for x in (s0.get("inst_level_loose_acc") or [])]})
            items.append(it)
    return items, {"items": len(items), "unjoined": unjoined, "ambiguous_outputs": ambiguous, "resp_vs_proxy_text_mismatch": text_mismatch}


# ---------------------------------------------------------------- one lm-eval run
def run_task(a, arm, model, kind, task_key, conc, tag, ev):
    import lm_eval
    raw = os.path.join(a.out, "raw", arm, f"{task_key}_{tag}"); os.makedirs(raw, exist_ok=True)
    proxy = Proxy(H.BASE[kind], os.path.join(raw, "proxy.jsonl"))
    samples = None
    if task_key == "mmlu":
        samples = json.load(open(IDS, encoding="utf-8"))["ids"]
        if a.test:
            samples = {k: v[:1] for k, v in samples.items()}   # every subject must be listed: lm-eval runs a missing subject in full
    elif a.test:
        samples = {TASKS[task_key]: list(range(a.test))}
    margs = {"model": model, "base_url": f"http://127.0.0.1:{PROXY_PORT}/v1/chat/completions", "num_concurrent": conc, "max_retries": 3,
             "timeout": 1800, "tokenized_requests": False, "tokenizer_backend": None}
    gk = dict(MMLU_EXTRA) if task_key == "mmlu" else None
    t0 = H.now(); print(f"  {arm} {task_key} {tag} c={conc} start {t0}", flush=True)
    err = None
    try:
        res = lm_eval.simple_evaluate(model="local-chat-completions", model_args=margs, tasks=[TASKS[task_key]], apply_chat_template=True,
                                      fewshot_as_multiturn=True, log_samples=True, samples=samples, gen_kwargs=gk, bootstrap_iters=0)
    except Exception as e:
        res, err = None, repr(e)[:500]
    proxy.close()
    t1 = H.now()
    rows = [json.loads(l) for l in open(os.path.join(raw, "proxy.jsonl"), encoding="utf-8")]
    rec = {"kind": "task_run", "arm": arm, "task": task_key, "lm_eval_task": TASKS[task_key], "run": tag, "concurrency": conc, "start": t0, "end": t1,
           "error": err, "proxy_requests": len(rows), "proxy_non_200": sum(1 for r in rows if r.get("status") != 200),
           "gen_settings_seen": sorted({json.dumps(r.get("gen"), sort_keys=True) for r in rows})[:3], "model_args": {k: v for k, v in margs.items()}, "gen_kwargs": gk}
    if res:
        json.dump(res.get("samples"), open(os.path.join(raw, "samples.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, default=str)
        items, join = public_items(task_key, res["samples"], rows)
        pub = os.path.join(a.out, "items", f"{arm}__{task_key}__{tag}.jsonl"); os.makedirs(os.path.dirname(pub), exist_ok=True)
        with open(pub, "w", encoding="utf-8", newline="\n") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n")
        rec.update({"join": join, "lm_eval_results": {k: {m: v for m, v in d.items() if isinstance(v, (int, float, str))} for k, d in (res.get("results") or {}).items()},
                    "lm_eval_version": getattr(lm_eval, "__version__", None), "configs_sha": sha(canon(res.get("configs"), )) if res.get("configs") else None})
        json.dump(res.get("configs"), open(os.path.join(raw, "configs.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, default=str, indent=1)
    ev.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n"); ev.flush()
    print(f"     end {t1} err={err} requests={len(rows)} join={rec.get('join')}", flush=True)


def probe(kind, model):
    out = {}
    for name, msgs in (("user_one_word", [{"role": "user", "content": "Hello"}]),
                       ("assistant_prefill", [{"role": "user", "content": "Say A."}, {"role": "assistant", "content": "The best answer is"}])):
        body = {"model": model, "messages": msgs, "max_tokens": 5, "temperature": 0}
        if name == "assistant_prefill":
            body.update(MMLU_EXTRA)
        try:
            r = requests.post(H.BASE[kind] + "/v1/chat/completions", json=body, timeout=120); j = r.json()
            out[name] = {"http_status": r.status_code, "prompt_tokens": (j.get("usage") or {}).get("prompt_tokens"),
                         "finish_reason": ((j.get("choices") or [{}])[0]).get("finish_reason"),
                         "output_chars": len((((j.get("choices") or [{}])[0]).get("message") or {}).get("content") or "")}
        except Exception as e:
            out[name] = {"error": str(e)[:200]}
    return out


def run_arm(a, arm, tok, ev, logdir):
    kind = H.ARMS[arm]["kind"]; name = f"p62q-{arm.lower()}"
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": H.now()}, ensure_ascii=False) + "\n"), ev.flush())
    if kind == "ollama":
        st_ = H.start_ollama(name, a.store, SLOTS[arm], logdir)
        load = H.ollama_load(name, H.ARMS[arm]["model"]) if st_["ready"] else None
        model = H.ARMS[arm]["model"]
        show = H.sh(["docker", "exec", name, "ollama", "show", model], 60).stdout
        quant = next((l.split()[-1] for l in show.splitlines() if l.strip().lower().startswith("quantization")), None)
        extra = {"image": H.OLLAMA_IMAGE, "ollama_version": st_.get("version"), "env": st_.get("env"), "load": load,
                 "ollama_show_quantization": quant, "ollama_show": [l.strip() for l in show.splitlines() if l.strip()][:20]}
        resident = bool(load and load.get("full_gpu"))
    else:
        st_ = H.start_nim(arm, name, logdir)
        model = requests.get(H.BASE["nim"] + "/v1/models", timeout=30).json()["data"][0]["id"] if st_["ready"] else None
        extra = {"image": H.NIM_IMAGE, "env": st_.get("env"), "seconds_to_ready": st_.get("seconds_to_verdict"), "captured_graph_sizes": st_.get("captured_graph_sizes")}
        resident = bool(st_["ready"] and st_.get("captured_graph_sizes"))
    iso = H.isolation(kind)
    if not (iso["pass"] and resident):
        event(kind="arm_refused", arm=arm, isolation=iso, resident=resident, **extra); H.save_logs(name, logdir); H.stop(name); return
    cal = H.calibrate(kind, model, "C", tok)
    rate = 1000.0 / cal["itl_ms_p50"] if cal.get("itl_ms_p50") else None
    share = rate * BYTES[arm] / PEAK if rate else None
    event(kind="arm_start", arm=arm, model=model, isolation=iso, resident=resident, health={"decode_rate_c1_tok_s": rate and round(rate, 2), "bytes_per_token": BYTES[arm],
          "share_of_peak": share and round(share, 4), "pass": bool(share and share >= HEALTH)}, calibration_n_ok=cal["n_ok"], probe=probe(kind, model), gpu_ready=H.gpu(), **extra)
    print(f"  {arm}: resident={resident} health={share and round(share, 3)}", flush=True)
    for task_key, conc, tag in RUNS[arm]:
        if a.test and tag not in ("main", "c1"):
            continue
        run_task(a, arm, model, kind, task_key, conc, tag, ev)
    H.save_logs(name, logdir); H.stop(name)
    event(kind="arm_end", arm=arm, gpu_after_stop=H.gpu())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--tokenizer", required=True); ap.add_argument("--store", required=True)
    ap.add_argument("--arms", default=",".join(ORDER)); ap.add_argument("--test", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    if H.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    tok = H.tokenizer(a.tokenizer)
    for arm in a.arms.split(","):
        print(f"##### arm {arm} {H.now()}", flush=True)
        run_arm(a, arm, tok, ev, logdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
