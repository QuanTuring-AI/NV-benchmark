#!/usr/bin/env python3
"""P102 · follow-up cells to the judge study (P93), against the server on 127.0.0.1:8000. The P93 harness files are
used as they are (imported, not edited): the item tables, the subsets, the answer parser, the Guardrails worker.

  passthrough   Nemotron 3 Nano on NIM, with or without a server-side reasoning parser (the runner sets the container).
                (b) three harmless requests with enable_thinking true: is there a reasoning_content (or reasoning) field,
                    does the content still carry </think>, does it carry <think>;
                (c) the 100 input items of the gr_path subset through the Guardrails self-check rail with the J2 config,
                    one call at a time: what the rail decided, what the answer reads as.
  lg3           Llama Guard 3 8B on upstream vLLM, a reference arm (not a NIM). The turns are sent as chat messages; the
                model's own chat template builds the prompt. Its native answer is `safe`, or `unsafe` and a line of
                category codes: the first non-empty line is the verdict, anything else is no verdict.
  n2            optional: Nemotron Nano 9B v2 on NIM through the Guardrails self-check rail with the `/no_think` judge
                config of Vol.2 (scripts/guardrails_nothink), one call at a time only.
Modes for lg3 / n2: precheck (two synthetic controls; for n2 also ten harmless prompts that must show no reasoning),
c1 (the 200-item subset of the track; for n2 the whole track, since it has no c=16 cell), c16 (lg3 only, whole track).
Result lines carry no text; raw answers go to the process bucket, as in P93.

usage: p102_cells.py passthrough --label on|off --prediction FILE --gr-py PY
       p102_cells.py lg3 --mode precheck|c1|c16 --track input|output --prediction FILE
       p102_cells.py n2  --mode precheck|c1 --track input|output --prediction FILE --gr-py PY
       p102_cells.py self_test
"""
import argparse, collections, concurrent.futures as cf, json, os, queue, re, subprocess, sys, threading, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from p93_common import BASE, BUCKET, RESULTS as P93, TEMPERATURE, VOL, gpu, now, read_jsonl, sha256_file, sha256_text  # noqa: E402
from p93_configs import write_config  # noqa: E402
from p93_parse import split_reasoning  # noqa: E402

RESULTS = os.environ.get("P102_RESULTS") or os.path.join(VOL, "results", "p102_followup")
NOTHINK_CONFIG = os.path.join(os.path.dirname(VOL), "vol2-nemotron", "scripts", "guardrails_nothink", "config.yml")
LG3_MAX_TOKENS = 100
WARM_UP = ("Hello.", "Hi there.")


def parse_native(content):
    """Llama Guard's own answer format: first non-empty line `safe` or `unsafe`."""
    lines = [l.strip() for l in (content or "").strip().splitlines() if l.strip()]
    first = lines[0].lower() if lines else ""
    return first if first in ("safe", "unsafe") else None


def served_model():
    return requests.get(BASE + "/v1/models", timeout=60).json()["data"][0]["id"]


def load_prediction(path):
    pred = json.load(open(path, encoding="utf-8"))
    side = os.path.splitext(path)[0] + ".sha256"
    if not os.path.isfile(side) or open(side, encoding="utf-8").read().split()[0] != sha256_file(path):
        sys.exit("the pre-registration does not match its .sha256 file")
    return pred


def texts_and_items():
    items = read_jsonl(os.path.join(P93, "items.jsonl")); subsets = json.load(open(os.path.join(P93, "subsets.json"), encoding="utf-8"))
    tpath = os.path.join(BUCKET, "items_text.jsonl"); texts = {r["item_id"]: r for r in read_jsonl(tpath)}
    return items, subsets, texts, tpath


def check_texts(ids, track, items, texts):
    by = {it["item_id"]: it for it in items}
    for i in ids:
        if sha256_text(texts[i]["prompt"]) != by[i]["prompt_sha256"] or (track == "output" and sha256_text(texts[i]["response"]) != by[i]["response_sha256"]):
            sys.exit(f"{i}: the text in the bucket does not match the item table")


def ask_lg3(model, track, text, t0):
    messages = [{"role": "user", "content": text["prompt"]}]
    if track == "output":
        messages.append({"role": "assistant", "content": text.get("response") or ""})
    body = {"model": model, "messages": messages, "max_tokens": LG3_MAX_TOKENS, "temperature": TEMPERATURE}
    start = time.perf_counter(); row = {"item_id": text["item_id"]}; raw = None
    try:
        r = requests.post(BASE + "/v1/chat/completions", json=body, timeout=900); end = time.perf_counter()
        if r.status_code != 200:
            row.update({"verdict": None, "status": "error", "error": f"HTTP {r.status_code}", "error_sha256": sha256_text(r.text)})
        else:
            d = r.json(); ch = d["choices"][0]; content = (ch.get("message") or {}).get("content") or ""; u = d.get("usage") or {}
            v = parse_native(content)
            row.update({"verdict": v, "status": "ok" if v else ("truncated" if ch.get("finish_reason") == "length" else "unreadable"), "has_reasoning": False, "reasoning_chars": 0,
                        "answer_chars": len(content.strip()), "finish_reason": ch.get("finish_reason"), "completion_tokens": u.get("completion_tokens"), "prompt_tokens": u.get("prompt_tokens"),
                        "completion_sha256": sha256_text(content)})
            raw = {"item_id": text["item_id"], "content": content, "reasoning": ""}
    except Exception as e:
        end = time.perf_counter(); row.update({"verdict": None, "status": "error", "error": type(e).__name__})
    row.update({"latency_ms": round((end - start) * 1000, 1), "t_start_s": round(start - t0, 3), "t_end_s": round(end - t0, 3)})
    return row, raw


def run_lg3(model, track, texts, ids, conc, out_path, raw_path):
    q = queue.Queue()
    for i in ids:
        q.put(i)
    lock = threading.Lock(); counts = collections.Counter()
    out = open(out_path, "a", encoding="utf-8", newline="\n"); raw = open(raw_path, "a", encoding="utf-8", newline="\n")
    warm_ms = ask_lg3(model, track, {"item_id": "warm_up", "prompt": WARM_UP[0], "response": WARM_UP[1]}, time.perf_counter())[0]["latency_ms"]
    t0 = time.perf_counter()

    def worker():
        while True:
            try:
                i = q.get_nowait()
            except queue.Empty:
                return
            row, r = ask_lg3(model, track, texts[i], t0)
            with lock:
                counts[row["status"]] += 1
                out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
                if r:
                    raw.write(json.dumps(r, ensure_ascii=False) + "\n"); raw.flush()
    with cf.ThreadPoolExecutor(conc) as ex:
        for f in [ex.submit(worker) for _ in range(conc)]:
            f.result()
    wall = time.perf_counter() - t0; out.close(); raw.close()
    return {"wall_s": round(wall, 3), "status_counts": {k: counts.get(k, 0) for k in ("ok", "truncated", "unreadable", "error")}, "discarded_warm_up_ms": warm_ms, "connection": "new per call"}


def run_worker(gr_py, cfg_dir, track, texts_path, ids, conc, out_path, raw_path, work, tag):
    ids_path = os.path.join(work, f"ids_{tag}_{os.getpid()}.json"); json.dump(ids, open(ids_path, "w", encoding="utf-8"))
    cmd = [gr_py, os.path.join(HERE, "p93_gr_worker.py"), "--config", cfg_dir, "--kind", "self_check", "--track", track, "--texts", texts_path, "--ids", ids_path,
           "--concurrency", str(conc), "--out", out_path, "--raw", raw_path]
    log_path = os.path.join(work, f"gr_worker_{tag}_{os.getpid()}.log")
    with open(log_path, "w", encoding="utf-8") as log:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8", NEMO_GUARDRAILS_NO_USAGE_STATS="1"))
    os.remove(ids_path)
    lines = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
    ready = next((l for l in lines if "ready" in l), {}); done = next((l for l in lines if "done" in l), {})
    malformed = sum(1 for l in open(log_path, encoding="utf-8", errors="replace") if "Malformed <think>" in l)
    return {"worker_rc": p.returncode, "worker": ready, "wall_s": done.get("wall_s"), "status_counts": done.get("status_counts"), "discarded_warm_up_ms": done.get("warm_up_ms"),
            "malformed_think_log_lines": malformed, "ok": p.returncode == 0 and bool(done.get("done"))}


def nothink_config(model, out_dir):
    src = open(NOTHINK_CONFIG, encoding="utf-8").read()
    m = re.search(r"^(\s*model:\s*)(\S+)\s*$", src, flags=re.M); b = re.search(r"^(\s*base_url:\s*)(\S+)\s*$", src, flags=re.M)
    if not m or not b:
        sys.exit("the no-think rail config has no model or base_url line")
    src = src[:m.start(2)] + model + src[m.end(2):]
    b = re.search(r"^(\s*base_url:\s*)(\S+)\s*$", src, flags=re.M)
    src = src[:b.start(2)] + BASE + "/v1" + src[b.end(2):]
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "config.yml"), "w", encoding="utf-8", newline="\n").write(src)
    return {"source": "vol2-nemotron/scripts/guardrails_nothink/config.yml", "source_sha256": sha256_file(NOTHINK_CONFIG), "model": model, "files": {"config.yml": sha256_text(src)}}


def control_items(pred, track):
    c = pred["controls"]
    return [{"item_id": f"control_{track}_violating", "prompt": c[f"{track}_violating"]["prompt"], "response": c[f"{track}_violating"].get("response", "")},
            {"item_id": f"control_{track}_benign", "prompt": c[f"{track}_benign"]["prompt"], "response": c[f"{track}_benign"].get("response", "")}]


def write_cell(arm_dir, rec):
    with open(os.path.join(arm_dir, "cells.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cmd_arm(a, arm):
    pred = load_prediction(a.prediction); model = served_model(); track = a.track
    arm_dir = os.path.join(RESULTS, arm); os.makedirs(arm_dir, exist_ok=True)
    raw_dir = os.path.join(BUCKET, "raw", "p102_" + arm); os.makedirs(raw_dir, exist_ok=True); work = os.path.join(BUCKET, "work"); os.makedirs(work, exist_ok=True)
    items, subsets, texts, tpath = texts_and_items()
    cfg = None
    if arm == "N2R":
        cfg_dir = os.path.join(arm_dir, "gr_config"); cfg = nothink_config(model, cfg_dir)
    if a.mode == "precheck":
        its = control_items(pred, track)
        if arm == "N2R":
            its += [{"item_id": f"toggle_{i:02d}", "prompt": p, "response": pred["toggle_response"] if track == "output" else ""} for i, p in enumerate(pred["toggle_prompts"], 1)]
        tp = os.path.join(work, f"p102_precheck_texts_{arm}_{track}.jsonl")
        with open(tp, "w", encoding="utf-8", newline="\n") as f:
            for it in its:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        outp = os.path.join(work, f"p102_precheck_rows_{arm}_{track}.jsonl"); rawp = os.path.join(raw_dir, f"precheck_{track}.jsonl")
        for p in (outp, rawp):
            if os.path.exists(p):
                os.remove(p)
        if arm == "LG3":
            res = run_lg3(model, track, {it["item_id"]: it for it in its}, [it["item_id"] for it in its], 1, outp, rawp)
        else:
            res = run_worker(a.gr_py, cfg_dir, track, tp, [it["item_id"] for it in its], 1, outp, rawp, work, f"{arm}_pre_{track}")
        rows = {r["item_id"]: r for r in read_jsonl(outp)} if os.path.isfile(outp) else {}
        v = rows.get(f"control_{track}_violating", {}); b = rows.get(f"control_{track}_benign", {})
        tog = [rows.get(f"toggle_{i:02d}", {}) for i in range(1, len(pred["toggle_prompts"]) + 1)] if arm == "N2R" else []
        with_r = sum(bool(r.get("has_reasoning")) for r in tog)
        ok = v.get("verdict") == "unsafe" and b.get("verdict") == "safe" and (arm != "N2R" or with_r == 0)
        keep = ("verdict", "status", "rail", "finish_reason", "completion_tokens", "has_reasoning", "latency_ms", "error")
        rec = {"arm": arm, "track": track, "at": now(), "model": model, "prediction_sha256": sha256_file(a.prediction), "control_violating": {k: v.get(k) for k in keep},
               "control_benign": {k: b.get(k) for k in keep}, "reasoning_switch": None if arm != "N2R" else {"arm_setting": False, "answers_with_reasoning": with_r, "of": len(tog)},
               "run": res, "config": cfg, "pass": bool(ok)}
        json.dump(rec, open(os.path.join(arm_dir, f"precheck_{track}.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
        os.remove(tp); os.remove(outp)
        print(json.dumps({"arm": arm, "track": track, "pass": rec["pass"], "violating": v.get("verdict"), "benign": b.get("verdict"), "with_reasoning": f"{with_r}/{len(tog)}"}))
        return 0 if ok else 3
    if a.mode == "c1":
        ids = subsets[f"c1_{track}"]["items"] if arm == "LG3" else [it["item_id"] for it in items if track in it["tracks"]]
    else:
        ids = [it["item_id"] for it in items if track in it["tracks"]]
    check_texts(ids, track, items, texts)
    name = f"{track}_{a.mode}"; outp = os.path.join(arm_dir, name + ".jsonl"); rawp = os.path.join(raw_dir, name + ".jsonl")
    if os.path.exists(outp):
        sys.exit(f"refused: {outp} exists")
    conc = 16 if a.mode == "c16" else 1
    rec = {"arm": arm, "track": track, "mode": a.mode, "n": len(ids), "concurrency": conc, "model": model, "prediction_sha256": sha256_file(a.prediction),
           "request": ({"through": "direct request", "body": {"model": model, "messages": "[the turns as chat messages]", "max_tokens": LG3_MAX_TOKENS, "temperature": TEMPERATURE}} if arm == "LG3"
                       else {"through": "NeMo Guardrails action", "config": cfg}), "start": now(), "gpu_start": gpu()}
    res = run_lg3(model, track, texts, ids, conc, outp, rawp) if arm == "LG3" else run_worker(a.gr_py, cfg_dir, track, tpath, ids, conc, outp, rawp, work, f"{arm}_{name}")
    rows = read_jsonl(outp) if os.path.isfile(outp) else []
    rec.update({"end": now(), "gpu_end": gpu(), **res, "rows_written": len(rows), "complete": len(rows) == len(ids) and {r["item_id"] for r in rows} == set(ids),
                "result_file": os.path.basename(outp), "result_sha256": sha256_file(outp) if rows else None})
    write_cell(arm_dir, rec)
    print(json.dumps({k: rec.get(k) for k in ("arm", "track", "mode", "n", "concurrency", "wall_s", "status_counts", "complete")}))
    return 0 if rec["complete"] else 4


def cmd_passthrough(a):
    pred = load_prediction(a.prediction); model = served_model(); label = a.label
    out_dir = os.path.join(RESULTS, "passthrough", label); os.makedirs(out_dir, exist_ok=True)
    raw_dir = os.path.join(BUCKET, "raw", "p102_passthrough_" + label); os.makedirs(raw_dir, exist_ok=True); work = os.path.join(BUCKET, "work"); os.makedirs(work, exist_ok=True)
    shapes = []
    for prompt in pred["toggle_prompts"][:3]:
        r = requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 512, "temperature": TEMPERATURE,
                                                              "chat_template_kwargs": {"enable_thinking": True}}, timeout=600)
        d = r.json() if r.status_code == 200 else {}
        ch = (d.get("choices") or [{}])[0]; msg = ch.get("message") or {}; content = msg.get("content") or ""; rc = msg.get("reasoning_content"); rs = msg.get("reasoning")
        shapes.append({"http": r.status_code, "message_keys": sorted(msg.keys()), "reasoning_content_present": bool(rc), "reasoning_content_chars": len(rc or ""),
                       "reasoning_field_present": bool(rs), "reasoning_field_chars": len(rs or ""), "content_chars": len(content),
                       "content_has_closing_think": "</think>" in content, "content_has_opening_think": "<think>" in content, "finish_reason": ch.get("finish_reason"),
                       "completion_tokens": (d.get("usage") or {}).get("completion_tokens")})
    items, subsets, texts, tpath = texts_and_items()
    ids = subsets["gr_path"]["input"]; check_texts(ids, "input", items, texts)
    cfg_dir = os.path.join(out_dir, "gr_config"); cfg = write_config("J2", model, cfg_dir)
    outp = os.path.join(out_dir, "input_gr100.jsonl"); rawp = os.path.join(raw_dir, "input_gr100.jsonl")
    if os.path.exists(outp):
        sys.exit(f"refused: {outp} exists")
    start = now(); res = run_worker(a.gr_py, cfg_dir, "input", tpath, ids, 1, outp, rawp, work, f"passthrough_{label}")
    rows = read_jsonl(outp) if os.path.isfile(outp) else []
    raw = read_jsonl(rawp) if os.path.isfile(rawp) else []
    rec = {"label": label, "model": model, "prediction_sha256": sha256_file(a.prediction), "start": start, "end": now(), "request_shapes": shapes, "config": cfg, "n": len(ids), "run": res,
           "rail": dict(collections.Counter(str(r.get("rail")) for r in rows)), "verdict": dict(collections.Counter(str(r.get("verdict")) for r in rows)),
           "answers_with_reasoning": sum(bool(r.get("has_reasoning")) for r in rows),
           "answers_whose_content_still_carries_closing_think": sum("</think>" in (r.get("content") or "") for r in raw),
           "answers_with_reasoning_moved_out_of_the_content": sum(bool(r.get("reasoning")) for r in raw),
           "complete": len(rows) == len(ids), "result_file": os.path.basename(outp), "result_sha256": sha256_file(outp) if rows else None}
    json.dump(rec, open(os.path.join(out_dir, "passthrough.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"label": label, "rail": rec["rail"], "verdict": rec["verdict"], "reasoning_content_present": [s["reasoning_content_present"] for s in shapes],
                      "content_has_closing_think": [s["content_has_closing_think"] for s in shapes], "complete": rec["complete"]}))
    return 0 if rec["complete"] else 4


SAMPLES = [("safe", "safe"), ("unsafe\nS1", "unsafe"), ("\n\nunsafe\nS1,S10", "unsafe"), ("Safe", "safe"), ("  unsafe", "unsafe"), ("The message is safe.", None), ("", None), ("S1", None),
           ("unsafe S1", None), ("safe\nunsafe", "safe")]


def self_test():
    ok = True
    for i, (text, want) in enumerate(SAMPLES, 1):
        got = parse_native(text); good = got == want; ok = ok and good
        print(("  PASS " if good else "  FAIL ") + f"native sample {i:02d}: {got}" + ("" if good else f" (want {want})"))
    naive = "unsafe" if "unsafe" in SAMPLES[5][0] else ("safe" if "safe" in SAMPLES[5][0] else None)
    good = naive == "safe" and parse_native(SAMPLES[5][0]) is None; ok = ok and good
    print(("  PASS " if good else "  FAIL ") + "mutation: searching the word anywhere would read a sentence as a verdict; the rule reads the first line only")
    a, r, u = split_reasoning("some reasoning</think>No"); good = (a, bool(r), u) == ("No", True, False); ok = ok and good
    print(("  PASS " if good else "  FAIL ") + "a closing tag without an opening one: the part after it is the answer")
    print("SELF-TEST " + ("PASS" if ok else "FAIL")); return ok


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 1 and sys.argv[1] == "self_test":
        return 0 if self_test() else 1
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("passthrough"); p.add_argument("--label", required=True, choices=["on", "off"]); p.add_argument("--prediction", required=True); p.add_argument("--gr-py", required=True)
    for name in ("lg3", "n2"):
        p = sub.add_parser(name); p.add_argument("--mode", required=True, choices=["precheck", "c1", "c16"] if name == "lg3" else ["precheck", "c1"])
        p.add_argument("--track", required=True, choices=["input", "output"]); p.add_argument("--prediction", required=True); p.add_argument("--gr-py")
    a = ap.parse_args()
    if a.cmd == "passthrough":
        return cmd_passthrough(a)
    return cmd_arm(a, "LG3" if a.cmd == "lg3" else "N2R")


if __name__ == "__main__":
    sys.exit(main())
