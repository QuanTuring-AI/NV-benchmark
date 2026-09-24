#!/usr/bin/env python3
"""Vol.2 · NeMo Guardrails 0.23.0 on the two Nemotron NIMs: per arm one container, two request arms rotated per
question — nim-only (Vol.1 E3 payload) and NIM + Guardrails 0.23.0 (worker process in its own venv) — over the
Vol.1-A E3 question set (45 questions × 3 rounds), 2 s between requests, warm-up request per request arm excluded.

Everything about the timed regions, the rail config handling (Vol.1's config.yml with the model name substituted and
top_p added) and the worker protocol is the Vol.1-B bridge harness, imported from vol1b/scripts (bridge_2x2.py,
gr_worker.py); this file only drives it over the two Nemotron containers. Containers: the footprint configuration
plus NIM_MAX_MODEL_LEN 8192 (the Vol.1-B value; the self-check prompts wrap the question) and max_num_seqs 32.
Both models reason by default; what the rail's judge does with that is recorded per LLM call by rails.explain().
usage: p53_guardrails.py --out DIR --gr023-py PYTHON [--rounds 3] [--question-limit 0] [--arms A1,A2]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, re, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
from bridge_2x2 import COOLDOWN, MAX_TOKENS, QUESTIONS, QUESTIONS_SHA, RAIL_CONFIG, TOP_P, Worker, nim_only, sha  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
GR_ENV = {"A1": {"NIM_MAX_MODEL_LEN": "8192", "NIM_MAX_NUM_SEQS": "32"},
          "A2": {"NIM_MAX_MODEL_LEN": "8192", "NIM_PASSTHROUGH_ARGS": "--max-num-seqs 32"}}


NOTHINK_CONFIG = os.path.join(HERE, "guardrails_nothink", "config.yml")   # E9's variant: the same prompts, sent with a /no_think system message


def rail_config_for(model, out_dir, source=RAIL_CONFIG):
    src = open(source, encoding="utf-8").read()
    m = re.search(r"^(\s*model:\s*)(\S+)\s*$", src, flags=re.M)
    substituted = None
    if m and m.group(2) != model:
        substituted = {"from": m.group(2), "to": model}
        src = src[:m.start(2)] + model + src[m.end(2):]
    t = re.search(r"^(\s*)temperature:\s*0\.0\s*$", src, flags=re.M)
    if not t or "top_p:" in src:
        sys.exit("rail config: expected one 'temperature: 0.0' line and no top_p")
    src = src[:t.end()] + f"\n{t.group(1)}top_p: {TOP_P}" + src[t.end():]
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "config.yml")
    open(p, "w", encoding="utf-8", newline="").write(src)
    return p, substituted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--gr023-py", required=True)
    ap.add_argument("--rounds", type=int, default=3); ap.add_argument("--question-limit", type=int, default=0)
    ap.add_argument("--arms", default="A1,A2")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    if sha(QUESTIONS) != QUESTIONS_SHA:
        sys.exit("e3_questions.json sha256 mismatch")
    qs = json.load(open(QUESTIONS, encoding="utf-8"))
    if a.question_limit:
        qs = qs[:a.question_limit]
    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    rows_f = open(os.path.join(a.out, "rows.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")

    def event(**kw):
        kw["at"] = now(); ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "at")}, flush=True)

    for arm in a.arms.split(","):
        ARMS[arm] = dict(ARMS[arm], env=GR_ENV[arm])
        name = f"p53-gr-{arm.lower()}"
        before = gpu()
        st_ = start(arm, name, None, logdir)
        if not st_["ready"]:
            event(kind="container_failed", arm=arm, reason=st_.get("reason"), log_lines=st_.get("log_lines")); stop(name); continue
        time.sleep(5)
        model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
        cc = metrics_cache_config()
        if cc.get("kv_tokens") is None and st_.get("kv_tokens_from_log"):
            cc["kv_tokens"] = st_["kv_tokens_from_log"]; cc["kv_tokens_source"] = "log"
        # two judge configurations: G = Vol.1's rail config verbatim (judge prompts as plain content); H = E9's variant of
        # the same prompts sent with a "/no_think" system message. In the harness test G's judge answered the clean
        # questions with about 200 tokens of reasoning and the rail treated every one of them as a block.
        workers, cfg_meta = {}, {}
        for label, source in (("G", RAIL_CONFIG), ("H", NOTHINK_CONFIG)):
            cfg_dir = os.path.join(a.out, f"gr_config_{arm.lower()}_{label.lower()}")
            cfg_path, substituted = rail_config_for(model, cfg_dir, source)
            cfg_meta[label] = {"source": os.path.relpath(source, os.path.join(HERE, "..", "..")).replace(os.sep, "/"), "source_sha256": sha(source),
                               "used_sha256": sha(cfg_path), "model_name_substitution": substituted, "added": f"top_p: {TOP_P}"}
            try:
                workers[label] = Worker(label, a.gr023_py, cfg_dir, os.path.join(logdir, f"worker_{arm.lower()}_{label.lower()}_gr023.stderr.txt"))
            except Exception as e:
                workers[label] = None; cfg_meta[label]["worker_error"] = str(e)[:800]
        event(kind="arm_start", arm=arm, image=ARMS[arm]["image"], profile=ARMS[arm]["profile"], env=st_["env"], served_model=model,
              gpu_before_launch=before, gpu_ready=gpu(), seconds_to_ready=st_["seconds_to_ready"], cache_config=cc, log_lines=st_["log_lines"],
              rail_configs=cfg_meta, worker_versions={k: getattr(w, "versions", None) for k, w in workers.items()}, max_tokens=MAX_TOKENS,
              questions={"file": "benchmark/e3_questions.json", "sha256": QUESTIONS_SHA, "n": len(qs)}, rounds=a.rounds)

        def one(req_arm, q, rnd, warmup=False):
            if req_arm == "N":
                r = nim_only(BASE, model, q["text"])
            elif workers.get(req_arm) is None:
                r = {"error": "guardrails worker unavailable: " + str(cfg_meta[req_arm].get("worker_error", "?"))}
            else:
                r = workers[req_arm].ask(f"{q['id']}#{rnd}", q["text"])
            r.pop("key", None)
            full = r.pop("response_full", None)
            r["response_sha256"] = __import__("hashlib").sha256((full or "").encode("utf-8")).hexdigest() if full is not None else None
            r["response_chars"] = len(full) if full is not None else None
            r.update({"arm": arm, "request_arm": req_arm, "question_id": q["id"], "category": q["category"],
                      "expected_action": q["expected_action"], "round": rnd, "warmup": warmup, "t": now(),
                      "docker_ps_before": sh(["docker", "ps", "--format", "{{.Names}}"], timeout=30).stdout.split()})
            rows_f.write(json.dumps(r, ensure_ascii=False) + "\n"); rows_f.flush()
            time.sleep(COOLDOWN)
            return r

        for req_arm in ("N", "G", "H"):
            one(req_arm, qs[0], 0, warmup=True)
        done = 0
        for rnd in range(1, a.rounds + 1):
            for q in qs:
                for req_arm in ("N", "G", "H"):
                    r = one(req_arm, q, rnd); done += 1
                    if "error" in r:
                        print(f"  ERROR {arm} {req_arm} {q['id']} r{rnd}: {str(r['error'])[:140]}", flush=True)
                if done % 45 == 0:
                    print(f"  {arm} {done}/{len(qs) * a.rounds * 3} · {now()} · gpu {gpu()['used_mib']} MiB", flush=True)
        for w in workers.values():
            if w is not None:
                w.close()
        stop(name)
        event(kind="arm_end", arm=arm, gpu_after_stop=gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
