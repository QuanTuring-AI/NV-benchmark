#!/usr/bin/env python3
"""Vol.3 · arm J6G: the Safety Guard 8B v3 NIM asked through the NeMo Guardrails content-safety rail, configured as the
library documents it for this model. Against the server on 127.0.0.1:8000; the study's Guardrails worker
(p93_gr_worker.py) is used as it is.

Configuration (written to results/safety_guard_nim/J6G/gr_config/, with the SHA-256 of each file in the record):
  config.yml    the tutorial "Check Harmful Content with Nemotron Content Safety NIM" of the library at tag v0.24.1,
                section "Deploy ... NIM locally": engine `nim`, model type `content_safety`, the two content-safety
                flows. Three changes, each recorded: the base URL is this server's; the model name is given once (the
                tutorial gives it in `model` and again in `parameters.model_name`, and the library at the same tag
                refuses a configuration that names the model in two places); the main model points at the same server
                (no answer is generated in this study, so the main model is never called).
  prompts.yml   examples/configs/content_safety_multilingual/prompts.yml of the library at tag v0.24.1, byte for byte
                (kept in scripts/guardrails_safety_guard/prompts.yml; its SHA-256 is checked before use): the prompt
                with the 23 categories, max_tokens 50, parsers nemoguard_parse_prompt_safety / _response_safety.

Two things are recorded per item and kept apart, as in the study:
  rail      what the library's action decided: allow / block, or raise:<exception>
  verdict   what the study's parser (p93_parse.py, JSON shape) reads from the same completion
The worker reads verdicts in the line shape of another model; here the verdict is read again in the JSON shape from the
stored completion, after its SHA-256 is compared with the one in the worker's line.
`same_call` classifies each item by its own rail decision and its own verdict (one arm, one call; no other arm is read).

  precheck   two synthetic controls of the study's pre-registration through the rail: the violating one must be blocked
             and the harmless one allowed. rc 3 if not.
  cell       the study's subset for the Guardrails path (100 items per track), one call at a time.
Result lines carry no text; completions go to the folder outside the repository.

usage: safety_guard_nim_rail.py precheck|cell --track input|output --prediction FILE --gr-py PY
"""
import argparse, json, os, subprocess, sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from p93_common import BASE, RESULTS as P93_RESULTS, VOL, BUCKET as P93_BUCKET, gpu, now, read_jsonl, sha256_file, sha256_text  # noqa: E402
from p93_parse import read_verdict  # noqa: E402

RESULTS = os.environ.get("SG_NIM_RESULTS") or os.path.join(VOL, "results", "safety_guard_nim")
BUCKET = os.environ.get("SG_NIM_BUCKET") or os.path.join(os.path.dirname(VOL), "_internal", "safety_guard_nim_bucket")
ARM = "J6G"
PROMPTS = os.path.join(HERE, "guardrails_safety_guard", "prompts.yml")
SOURCE = {"tutorial": "docs/getting-started/tutorials/nemotron-safety-guard-deployment.mdx", "prompts": "examples/configs/content_safety_multilingual/prompts.yml",
          "repository": "https://github.com/NVIDIA/NeMo-Guardrails", "tag": "v0.24.1"}


def served_model():
    return requests.get(BASE + "/v1/models", timeout=60).json()["data"][0]["id"]


def write_config(model, out_dir, pred):
    want = pred["guardrails"]["prompts_sha256"]
    if sha256_file(PROMPTS) != want:
        sys.exit("refused: scripts/guardrails_safety_guard/prompts.yml is not the library's file the pre-registration names")
    config = f"""models:
  - type: main
    engine: nim
    model: {model}
    parameters:
      base_url: "{BASE}/v1"

  - type: content_safety
    engine: nim
    model: {model}
    parameters:
      base_url: "{BASE}/v1"

rails:
  input:
    flows:
      - content safety check input $model=content_safety
  output:
    flows:
      - content safety check output $model=content_safety
"""
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "config.yml"), "w", encoding="utf-8", newline="\n").write(config)
    open(os.path.join(out_dir, "prompts.yml"), "wb").write(open(PROMPTS, "rb").read())
    return {"source": SOURCE, "model": model, "engine": "nim", "files": {"config.yml": sha256_text(config), "prompts.yml": sha256_file(os.path.join(out_dir, "prompts.yml"))},
            "changes_from_the_tutorial": ["base_url is this server's", "the model name is given once (model), not also in parameters.model_name", "the main model points at the same server and is never called"],
            "max_tokens_in_prompts": 50, "kind": "content_safety"}


def run_worker(gr_py, cfg_dir, track, texts_path, ids, out_path, raw_path, work):
    ids_path = os.path.join(work, f"ids_{ARM}_{track}_{os.getpid()}.json")
    json.dump(ids, open(ids_path, "w", encoding="utf-8"))
    cmd = [gr_py, os.path.join(HERE, "p93_gr_worker.py"), "--config", cfg_dir, "--kind", "content_safety", "--track", track, "--texts", texts_path, "--ids", ids_path,
           "--concurrency", "1", "--out", out_path, "--raw", raw_path]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", NEMO_GUARDRAILS_NO_USAGE_STATS="1")
    env.setdefault("NVIDIA_API_KEY", "not-used-by-a-local-server")   # the engine's client wants a value; the local NIM does not check it
    with open(os.path.join(work, f"gr_worker_{ARM}_{track}_{os.getpid()}.log"), "w", encoding="utf-8") as log:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8", env=env)
    os.remove(ids_path)
    lines = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
    ready = next((l for l in lines if "ready" in l), {}); done = next((l for l in lines if "done" in l), {})
    return p.returncode, ready, done


def same_call(rail, verdict, status):
    """One item's rail decision beside the verdict read from the same completion."""
    r = "block" if str(rail).startswith("block") else "allow" if str(rail).startswith("allow") else "raise" if str(rail).startswith("raise") else "other"
    if verdict in ("safe", "unsafe"):
        agree = (r == "block") == (verdict == "unsafe") and r in ("block", "allow")
        return ("agree" if agree else f"{r}_but_verdict_{verdict}")
    return f"{r}_and_no_verdict_{status}"


def reread(rows_path, raw_path, track):
    """The worker's lines with the verdict read in the JSON shape from the stored completion."""
    raw = {r["item_id"]: r for r in read_jsonl(raw_path)} if os.path.isfile(raw_path) else {}
    out = []
    for r in read_jsonl(rows_path):
        c = raw.get(r["item_id"])
        if c is None or r.get("completion_sha256") is None:
            r.update({"verdict": None, "status": r.get("status") if r.get("status") == "error" else "error", "verdict_read_as": None})
        else:
            if sha256_text(c["content"]) != r["completion_sha256"]:
                sys.exit(f"{r['item_id']}: the stored completion is not the one the worker hashed")
            r.update(read_verdict("json", track, c["content"], c.get("reasoning") or "", r.get("finish_reason")))
            r["verdict_read_as"] = "json"
        r["same_call"] = same_call(r.get("rail"), r.get("verdict"), r.get("status"))
        out.append(r)
    return out


def setup(a):
    pred = json.load(open(a.prediction, encoding="utf-8"))
    side = os.path.splitext(a.prediction)[0] + ".sha256"
    if not os.path.isfile(side) or open(side, encoding="utf-8").read().split()[0] != sha256_file(a.prediction):
        sys.exit("the pre-registration does not match its .sha256 file")
    p93 = json.load(open(os.path.join(P93_RESULTS, "prediction_p93.json"), encoding="utf-8"))
    arm_dir = os.path.join(RESULTS, ARM); raw_dir = os.path.join(BUCKET, "bucket_" + ARM, "raw"); work = os.path.join(BUCKET, "bucket_" + ARM, "work")
    for d in (arm_dir, raw_dir, work):
        os.makedirs(d, exist_ok=True)
    model = served_model()
    cfg = os.path.join(arm_dir, "gr_config")
    return {"pred": pred, "p93": p93, "arm_dir": arm_dir, "raw_dir": raw_dir, "work": work, "model": model, "cfg": cfg, "config": write_config(model, cfg, pred)}


def cmd_precheck(a):
    ctx = setup(a); c = ctx["p93"]["controls"]; track = a.track
    for name, x in c.items():
        for part in ("prompt", "response"):
            if part in x and sha256_text(x[part]) != x[part + "_sha256"]:
                sys.exit(f"control {name}: the {part} does not match its SHA-256")
    items = [{"item_id": f"control_{track}_violating", **{k: c[f"{track}_violating"].get(k, "") for k in ("prompt", "response")}},
             {"item_id": f"control_{track}_benign", **{k: c[f"{track}_benign"].get(k, "") for k in ("prompt", "response")}}]
    tpath = os.path.join(ctx["work"], f"precheck_texts_{track}.jsonl")
    with open(tpath, "w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    rows_path = os.path.join(ctx["work"], f"precheck_rows_{track}.jsonl"); raw_path = os.path.join(ctx["raw_dir"], f"precheck_{track}.jsonl")
    for p in (rows_path, raw_path):
        if os.path.exists(p):
            os.remove(p)
    rc, ready, done = run_worker(a.gr_py, ctx["cfg"], track, tpath, [it["item_id"] for it in items], rows_path, raw_path, ctx["work"])
    rows = {r["item_id"]: r for r in reread(rows_path, raw_path, track)} if os.path.isfile(rows_path) else {}
    v = rows.get(f"control_{track}_violating", {}); b = rows.get(f"control_{track}_benign", {})
    ok = str(v.get("rail", "")).startswith("block") and str(b.get("rail", "")).startswith("allow")
    keep = ("rail", "verdict", "status", "finish_reason", "completion_tokens", "latency_ms", "same_call", "error", "rail_error")
    rec = {"arm": ARM, "track": track, "at": now(), "model": ctx["model"], "prediction_sha256": sha256_file(a.prediction), "worker_rc": rc, "worker": ready,
           "control_violating": {k: v.get(k) for k in keep}, "control_benign": {k: b.get(k) for k in keep},
           "rule": "the rail blocks the violating control and allows the harmless one", "config": ctx["config"], "pass": bool(ok)}
    json.dump(rec, open(os.path.join(ctx["arm_dir"], f"precheck_{track}.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    os.remove(tpath)
    if os.path.isfile(rows_path):
        os.remove(rows_path)
    print(json.dumps({"arm": ARM, "track": track, "pass": rec["pass"], "violating": v.get("rail"), "benign": b.get("rail"), "worker_rc": rc}))
    return 0 if rec["pass"] else 3


def cmd_cell(a):
    ctx = setup(a); track = a.track
    items = read_jsonl(os.path.join(P93_RESULTS, "items.jsonl")); subsets = json.load(open(os.path.join(P93_RESULTS, "subsets.json"), encoding="utf-8"))
    ids = subsets["gr_path"][track]
    texts_path = os.path.join(P93_BUCKET, "items_text.jsonl"); texts = {r["item_id"]: r for r in read_jsonl(texts_path)}; by = {it["item_id"]: it for it in items}
    for i in ids:
        if sha256_text(texts[i]["prompt"]) != by[i]["prompt_sha256"] or (track == "output" and sha256_text(texts[i]["response"]) != by[i]["response_sha256"]):
            sys.exit(f"{i}: the text in the bucket does not match the item table")
    out_path = os.path.join(ctx["arm_dir"], f"{track}_rail.jsonl"); raw_path = os.path.join(ctx["raw_dir"], f"{track}_rail.jsonl"); tmp = os.path.join(ctx["work"], f"{track}_rail_worker_rows.jsonl")
    if os.path.exists(out_path):
        sys.exit(f"refused: {out_path} exists")
    for p in (tmp, raw_path):
        if os.path.exists(p):
            os.remove(p)
    rec = {"arm": ARM, "track": track, "mode": "rail", "n": len(ids), "concurrency": 1, "model": ctx["model"], "prediction_sha256": sha256_file(a.prediction),
           "harness_sha256": {f: sha256_file(os.path.join(HERE, f)) for f in ("safety_guard_nim_rail.py", "p93_gr_worker.py", "p93_parse.py", "p93_common.py")},
           "request": {"through": "NeMo Guardrails action", "config": ctx["config"]}, "start": now(), "gpu_start": gpu()}
    rc, ready, done = run_worker(a.gr_py, ctx["cfg"], track, texts_path, ids, tmp, raw_path, ctx["work"])
    rows = reread(tmp, raw_path, track) if os.path.isfile(tmp) else []
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    counts = {}
    for r in rows:
        counts[r["same_call"]] = counts.get(r["same_call"], 0) + 1
    status = {k: sum(r.get("status") == k for r in rows) for k in ("ok", "truncated", "unreadable", "error")}
    rec.update({"end": now(), "gpu_end": gpu(), "worker_rc": rc, "worker": ready, "wall_s": done.get("wall_s"), "discarded_warm_up_ms": done.get("warm_up_ms"), "status_counts": status,
                "rail_beside_verdict_of_the_same_call": counts, "rows_written": len(rows), "complete": len(rows) == len(ids) and {r["item_id"] for r in rows} == set(ids) and rc == 0,
                "result_file": os.path.basename(out_path), "result_sha256": sha256_file(out_path) if rows else None})
    with open(os.path.join(ctx["arm_dir"], "cells.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if os.path.isfile(tmp):
        os.remove(tmp)
    print(json.dumps({k: rec.get(k) for k in ("arm", "track", "mode", "n", "wall_s", "status_counts", "rail_beside_verdict_of_the_same_call", "complete")}))
    return 0 if rec["complete"] else 4


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["precheck", "cell"])
    ap.add_argument("--track", required=True, choices=["input", "output"]); ap.add_argument("--prediction", required=True); ap.add_argument("--gr-py", required=True)
    a = ap.parse_args()
    return cmd_precheck(a) if a.cmd == "precheck" else cmd_cell(a)


if __name__ == "__main__":
    sys.exit(main())
