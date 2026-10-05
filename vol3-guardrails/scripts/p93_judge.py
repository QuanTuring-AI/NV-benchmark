#!/usr/bin/env python3
"""P93 · one cell of the judge study: one arm, one track, one mode, against the server on 127.0.0.1:8000.

  mode c1         the 200-item subset of the track, one call at a time: per-call duration (p50 / p99 come from here)
  mode c16        every item of the track, 16 calls in flight (closed loop): verdicts for the quality figures, wall time
  mode stability  the stability subset judged again at 16 in flight: does the arm repeat its own verdicts
  mode gr_path    J4G / J5G only: the gr_path subset through Guardrails' content-safety rail, one call at a time
  precheck        before an arm's cells, per track: two synthetic controls (one clearly violating, one harmless) must be
                  read as unsafe and safe, and the reasoning switch must have taken effect (see below). rc 3 if not.

How an arm is asked (p93_common.ARMS):
  guardrails_self_check / guardrails_content_safety   through p93_gr_worker.py in the Guardrails environment (--gr-py)
  direct_lines   Nemotron 3.5 Content Safety: the turns as chat messages; the model's own chat template supplies the
                 instructions and the taxonomy. chat_template_kwargs: enable_thinking per arm, request_categories "/categories"
  direct_json    Safety Guard 8B: the prompt template of its model card, read from the model snapshot at run time
                 (--sg8-template, the card's inference_script.py), sent as one user message
Sampling is greedy everywhere (temperature 0.0).

Reasoning switch check (precheck): ten short harmless prompts from the pre-registration are judged.
  arm with thinking on   reasoning must be present in at least 9 of the 10 answers
  arm with thinking off  reasoning must be present in none
  arm without a switch   not checked
What a result line holds: item id, verdict, status, finish_reason, token counts, duration, SHA-256 and sizes of the
answer. Never text. Raw answers and reasoning go to the bucket (raw/<arm>/...).
A cell refuses to start if its result file exists. Every finished call is written and flushed at once.
Every cell starts with one discarded call on a fixed harmless text (the first call of a new client is not a steady one).
Connections: a direct arm opens a new connection for every call; the precheck of a direct arm times ten harmless calls
both ways (new per call, one reused) and records the two medians. An arm through Guardrails uses the library's own
client, which keeps connections open; that is part of what that path costs and is not changed here.

usage: p93_judge.py cell --arm J4 --track input --mode c16 --prediction FILE [--gr-py PY] [--sg8-template FILE] [--limit N]
       p93_judge.py precheck --arm J4 --track input --prediction FILE [--gr-py PY] [--sg8-template FILE] [--tag stability]
"""
import argparse, concurrent.futures as cf, json, os, queue, re, subprocess, sys, threading, time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p93_common import ARMS, BASE, BUCKET, C1, C16, RESULTS, TEMPERATURE, gpu, now, read_jsonl, sha256_file, sha256_text  # noqa: E402
from p93_configs import write_config  # noqa: E402
from p93_parse import read_verdict  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TOGGLE_MIN_ON = 9
WARM_UP = ("Hello.", "Hi there.")   # the discarded first call of every cell
CONC = {"c1": C1, "c16": C16, "stability": C16, "gr_path": C1}


def served_model():
    return requests.get(BASE + "/v1/models", timeout=60).json()["data"][0]["id"]


def load_prediction(path):
    pred = json.load(open(path, encoding="utf-8"))
    side = os.path.splitext(path)[0] + ".sha256"
    if not os.path.isfile(side) or open(side, encoding="utf-8").read().split()[0] != sha256_file(path):
        sys.exit("the pre-registration does not match its .sha256 file")
    for name, c in pred["controls"].items():
        for part in ("prompt", "response"):
            if part in c and sha256_text(c[part]) != c[part + "_sha256"]:
                sys.exit(f"control {name}: the {part} does not match its SHA-256")
    return pred


def sg8_template(path):
    """The Safety Guard 8B prompt template, taken from the model card's inference_script.py in the model snapshot."""
    import jinja2
    src = open(path, encoding="utf-8").read()
    m = re.search(r'Template\("""(.*?)"""\)', src, re.S)
    if not m:
        sys.exit("the Safety Guard prompt template was not found in the model snapshot")
    return jinja2.Template(m.group(1)), sha256_text(m.group(1))


def body_for(arm, model, track, prompt, response, template):
    A = ARMS[arm]
    if A["path"] == "direct_lines":
        messages = [{"role": "user", "content": prompt}]
        if track == "output":
            messages.append({"role": "assistant", "content": response})
        return {"model": model, "messages": messages, "max_tokens": A["max_tokens"], "temperature": TEMPERATURE,
                "chat_template_kwargs": {"enable_thinking": bool(A["thinking"]), "request_categories": "/categories"}}
    content = template.render(query=prompt, response=response if track == "output" else None)
    return {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": A["max_tokens"], "temperature": TEMPERATURE}


def ask_direct(session, arm, model, track, text, template, t0):
    shape = "lines" if ARMS[arm]["path"] == "direct_lines" else "json"
    body = body_for(arm, model, track, text["prompt"], text.get("response") or "", template)
    start = time.perf_counter(); row = {"item_id": text["item_id"]}; raw = None
    try:
        r = (session or requests).post(BASE + "/v1/chat/completions", json=body, timeout=900)   # session None: a new connection for this call
        end = time.perf_counter()
        if r.status_code != 200:
            row.update({"verdict": None, "status": "error", "error": f"HTTP {r.status_code}", "error_sha256": sha256_text(r.text)})
        else:
            d = r.json(); ch = d["choices"][0]; msg = ch.get("message") or {}; u = d.get("usage") or {}
            content = msg.get("content") or ""; reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
            row.update(read_verdict(shape, track, content, reasoning, ch.get("finish_reason")))
            det = u.get("completion_tokens_details") or {}
            row.update({"finish_reason": ch.get("finish_reason"), "completion_tokens": u.get("completion_tokens"), "prompt_tokens": u.get("prompt_tokens"),
                        "reasoning_tokens_reported": det.get("reasoning_tokens"), "completion_sha256": sha256_text(content),
                        "reasoning_sha256": sha256_text(reasoning) if reasoning else None})
            raw = {"item_id": text["item_id"], "content": content, "reasoning": reasoning}
    except Exception as e:
        end = time.perf_counter()
        row.update({"verdict": None, "status": "error", "error": type(e).__name__})
    row.update({"latency_ms": round((end - start) * 1000, 1), "t_start_s": round(start - t0, 3), "t_end_s": round(end - t0, 3)})
    return row, raw


def run_direct(arm, model, track, texts, ids, conc, out_path, raw_path, template):
    """Closed loop: `conc` workers, each takes the next item as soon as its call returns."""
    q = queue.Queue()
    for i in ids:
        q.put(i)
    lock = threading.Lock(); counts = {"ok": 0, "truncated": 0, "unreadable": 0, "error": 0}
    out = open(out_path, "a", encoding="utf-8", newline="\n"); raw = open(raw_path, "a", encoding="utf-8", newline="\n")
    t0 = time.perf_counter()

    warm = {"item_id": "warm_up", "prompt": WARM_UP[0], "response": WARM_UP[1]}
    warm_ms = ask_direct(None, arm, model, track, warm, template, t0)[0]["latency_ms"]   # one discarded call before the cell
    t0 = time.perf_counter()

    def worker():
        s = None   # every call opens its own connection (a reused one adds a fixed offset on this host; measured in the precheck)
        while True:
            try:
                i = q.get_nowait()
            except queue.Empty:
                return
            row, r = ask_direct(s, arm, model, track, texts[i], template, t0)
            with lock:
                counts[row["status"]] += 1
                out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
                if r:
                    raw.write(json.dumps(r, ensure_ascii=False) + "\n"); raw.flush()
    with cf.ThreadPoolExecutor(conc) as ex:
        for f in [ex.submit(worker) for _ in range(conc)]:
            f.result()
    wall = time.perf_counter() - t0
    out.close(); raw.close()
    return {"wall_s": round(wall, 3), "status_counts": counts, "client": {"requests": requests.__version__, "connection": "new per call"}, "discarded_warm_up_ms": warm_ms}


def run_guardrails(arm, track, texts_path, ids, conc, out_path, raw_path, gr_py, cfg_dir, kind, work):
    ids_path = os.path.join(work, f"ids_{arm}_{track}_{os.getpid()}.json")
    json.dump(ids, open(ids_path, "w", encoding="utf-8"))
    cmd = [gr_py, os.path.join(HERE, "p93_gr_worker.py"), "--config", cfg_dir, "--kind", kind, "--track", track, "--texts", texts_path, "--ids", ids_path,
           "--concurrency", str(conc), "--out", out_path, "--raw", raw_path]
    log = open(os.path.join(work, f"gr_worker_{arm}_{track}_{os.getpid()}.log"), "w", encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", NEMO_GUARDRAILS_NO_USAGE_STATS="1")
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8", env=env)
    log.close(); os.remove(ids_path)
    lines = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
    ready = next((l for l in lines if "ready" in l), {}); done = next((l for l in lines if "done" in l), {})
    if p.returncode != 0 or not done.get("done"):
        return {"wall_s": None, "status_counts": None, "worker_rc": p.returncode, "worker_ready": ready, "worker_failed": True}
    return {"wall_s": done["wall_s"], "status_counts": done["status_counts"], "worker": ready, "discarded_warm_up_ms": done.get("warm_up_ms")}


def connection_check(model, n=10):
    """The same minimal request (one user turn, max_tokens 1) n times on new connections and n times on one reused
    connection. It measures what the transport on this host adds, apart from any arm's request shape."""
    import statistics
    body = {"model": model, "messages": [{"role": "user", "content": "What is 2 + 2?"}], "max_tokens": 1, "temperature": TEMPERATURE}

    def once(s):
        t = time.perf_counter()
        try:
            ok = (s or requests).post(BASE + "/v1/chat/completions", json=body, timeout=300).status_code == 200
        except Exception:
            ok = False
        return (time.perf_counter() - t) * 1000 if ok else None
    once(None)
    fresh = [once(None) for _ in range(n)]; s = requests.Session(); once(s); reused = [once(s) for _ in range(n)]
    med = lambda xs: round(statistics.median([x for x in xs if x is not None]), 1) if any(x is not None for x in xs) else None  # noqa: E731
    return {"request": "one user turn, max_tokens 1", "n": n, "new_per_call_ms_median": med(fresh), "reused_ms_median": med(reused),
            "failed": sum(x is None for x in fresh + reused), "direct_cells_use": "new per call", "guardrails_cells_use": "the library's client (connections kept open)"}


def setup(a):
    A = ARMS[a.arm]; pred = load_prediction(a.prediction); model = served_model()
    arm_dir = os.path.join(RESULTS, a.arm); os.makedirs(arm_dir, exist_ok=True)
    raw_dir = os.path.join(BUCKET, "raw", a.arm); os.makedirs(raw_dir, exist_ok=True)
    work = os.path.join(BUCKET, "work"); os.makedirs(work, exist_ok=True)
    ctx = {"A": A, "pred": pred, "model": model, "arm_dir": arm_dir, "raw_dir": raw_dir, "work": work, "template": None, "template_sha256": None, "config": None}
    if A["path"].startswith("guardrails"):
        if not a.gr_py:
            sys.exit("--gr-py is required for an arm that goes through Guardrails")
        cfg = os.path.join(arm_dir, "gr_config")
        ctx["config"] = write_config(a.arm, model, cfg); ctx["cfg_dir"] = cfg
    if A["path"] == "direct_json":
        if not a.sg8_template:
            sys.exit("--sg8-template is required for the Safety Guard arm")
        ctx["template"], ctx["template_sha256"] = sg8_template(a.sg8_template)
    return ctx


def run(a, ctx, track, texts, texts_path, ids, conc, out_path, raw_path):
    A = ctx["A"]
    if A["path"].startswith("guardrails"):
        return run_guardrails(a.arm, track, texts_path, ids, conc, out_path, raw_path, a.gr_py, ctx["cfg_dir"], ctx["config"]["kind"], ctx["work"])
    return run_direct(a.arm, ctx["model"], track, texts, ids, conc, out_path, raw_path, ctx["template"])


def request_shape(a, ctx, track):
    A = ctx["A"]
    if A["path"].startswith("guardrails"):
        return {"through": "NeMo Guardrails action", "config": ctx["config"]}
    b = body_for(a.arm, ctx["model"], track, "<prompt>", "<response>", ctx["template"]) if A["path"] == "direct_lines" else {"model": ctx["model"], "messages": "[one user message: the model card's template with the turns filled in]", "max_tokens": A["max_tokens"], "temperature": TEMPERATURE}
    return {"through": "direct request", "body": b, "sg8_template_sha256": ctx["template_sha256"]}


def cmd_precheck(a):
    ctx = setup(a); pred = ctx["pred"]; track = a.track
    c = pred["controls"]
    items = [{"item_id": f"control_{track}_violating", **{k: c[f"{track}_violating"].get(k, "") for k in ("prompt", "response")}},
             {"item_id": f"control_{track}_benign", **{k: c[f"{track}_benign"].get(k, "") for k in ("prompt", "response")}}]
    items += [{"item_id": f"toggle_{i:02d}", "prompt": p, "response": pred["toggle_response"] if track == "output" else ""} for i, p in enumerate(pred["toggle_prompts"], 1)]
    texts = {it["item_id"]: it for it in items}
    tpath = os.path.join(ctx["work"], f"precheck_texts_{a.arm}_{track}.jsonl")
    with open(tpath, "w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    out_path = os.path.join(ctx["work"], f"precheck_rows_{a.arm}_{track}.jsonl"); raw_path = os.path.join(ctx["raw_dir"], f"precheck_{track}.jsonl")
    for p in (out_path, raw_path):
        if os.path.exists(p):
            os.remove(p)
    res = run(a, ctx, track, texts, tpath, [it["item_id"] for it in items], 1, out_path, raw_path)
    rows = {r["item_id"]: r for r in read_jsonl(out_path)} if os.path.isfile(out_path) else {}
    v = rows.get(f"control_{track}_violating", {}); b = rows.get(f"control_{track}_benign", {})
    tog = [rows.get(f"toggle_{i:02d}", {}) for i in range(1, len(pred["toggle_prompts"]) + 1)]
    with_reasoning = sum(bool(r.get("has_reasoning")) for r in tog); think = ctx["A"]["thinking"]
    controls_ok = v.get("verdict") == "unsafe" and b.get("verdict") == "safe"
    toggle_ok = True if think is None else (with_reasoning >= TOGGLE_MIN_ON if think else with_reasoning == 0)
    keep = ("verdict", "status", "rail", "finish_reason", "completion_tokens", "has_reasoning", "reasoning_chars", "latency_ms", "error")
    connection = connection_check(ctx["model"])
    rec = {"arm": a.arm, "track": track, "at": now(), "model": ctx["model"], "prediction_sha256": sha256_file(a.prediction),
           "control_violating": {k: v.get(k) for k in keep}, "control_benign": {k: b.get(k) for k in keep}, "controls_pass": controls_ok,
           "reasoning_switch": {"arm_setting": think, "answers_with_reasoning": with_reasoning, "of": len(tog), "rule": f"on: >= {TOGGLE_MIN_ON} of {len(tog)}; off: 0; no switch: not checked", "pass": toggle_ok},
           "toggle_rows": [{k: r.get(k) for k in keep} for r in tog], "connection_check": connection, "run": res, "request": request_shape(a, ctx, track), "pass": bool(controls_ok and toggle_ok)}
    json.dump(rec, open(os.path.join(ctx["arm_dir"], f"precheck_{track}{'_' + a.tag if a.tag else ''}.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    os.remove(tpath); os.remove(out_path)
    print(json.dumps({k: rec[k] for k in ("arm", "track", "controls_pass", "pass")} | {"with_reasoning": f"{with_reasoning}/{len(tog)}", "violating": v.get("verdict"), "benign": b.get("verdict")}))
    return 0 if rec["pass"] else 3


def cmd_cell(a):
    ctx = setup(a); track = a.track
    if a.mode == "gr_path" and ctx["A"]["path"] != "guardrails_content_safety":
        sys.exit("mode gr_path is for J4G / J5G")
    items = read_jsonl(os.path.join(RESULTS, "items.jsonl")); subsets = json.load(open(os.path.join(RESULTS, "subsets.json"), encoding="utf-8"))
    if a.mode == "c1":
        ids = subsets[f"c1_{track}"]["items"]
    elif a.mode == "c16":
        ids = [it["item_id"] for it in items if track in it["tracks"]]
    else:
        ids = subsets[a.mode][track]
    if a.limit:
        ids = ids[: a.limit]
    texts_path = os.path.join(BUCKET, "items_text.jsonl")
    texts = {r["item_id"]: r for r in read_jsonl(texts_path)}
    by_id = {it["item_id"]: it for it in items}
    for i in ids:   # the text in the bucket must be the text the item table was built from
        t = texts[i]
        if sha256_text(t["prompt"]) != by_id[i]["prompt_sha256"] or (track == "output" and sha256_text(t["response"]) != by_id[i]["response_sha256"]):
            sys.exit(f"{i}: the text in the bucket does not match the item table")
    name = f"{track}_{a.mode}" + (f"_limit{a.limit}" if a.limit else "")
    out_path = os.path.join(ctx["arm_dir"], name + ".jsonl"); raw_path = os.path.join(ctx["raw_dir"], name + ".jsonl")
    if os.path.exists(out_path):
        sys.exit(f"refused: {out_path} exists")
    conc = CONC[a.mode]
    rec = {"arm": a.arm, "judge": ctx["A"]["judge"], "track": track, "mode": a.mode, "n": len(ids), "concurrency": conc, "model": ctx["model"], "limit": a.limit or None,
           "prediction_sha256": sha256_file(a.prediction), "harness_sha256": {f: sha256_file(os.path.join(HERE, f)) for f in ("p93_judge.py", "p93_gr_worker.py", "p93_parse.py", "p93_configs.py", "p93_common.py")},
           "request": request_shape(a, ctx, track), "start": now(), "gpu_start": gpu()}
    res = run(a, ctx, track, texts, texts_path, ids, conc, out_path, raw_path)
    rows = read_jsonl(out_path) if os.path.isfile(out_path) else []
    rec.update({"end": now(), "gpu_end": gpu(), **res, "rows_written": len(rows), "complete": len(rows) == len(ids) and {r["item_id"] for r in rows} == set(ids),
                "result_file": os.path.basename(out_path), "result_sha256": sha256_file(out_path) if rows else None})
    with open(os.path.join(ctx["arm_dir"], "cells.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({k: rec.get(k) for k in ("arm", "track", "mode", "n", "concurrency", "wall_s", "status_counts", "complete")}))
    return 0 if rec["complete"] else 4


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("cell", "precheck"):
        p = sub.add_parser(name)
        p.add_argument("--arm", required=True, choices=sorted(ARMS)); p.add_argument("--track", required=True, choices=["input", "output"])
        p.add_argument("--prediction", required=True); p.add_argument("--gr-py"); p.add_argument("--sg8-template")
        if name == "cell":
            p.add_argument("--mode", required=True, choices=sorted(CONC)); p.add_argument("--limit", type=int, default=0)
        else:
            p.add_argument("--tag", default="", help="suffix of the precheck file, for a precheck that is repeated in a later container")
    a = ap.parse_args()
    return cmd_cell(a) if a.cmd == "cell" else cmd_precheck(a)


if __name__ == "__main__":
    sys.exit(main())
