#!/usr/bin/env python3
"""Vol.1-B · NIM × NeMo Guardrails 2×2 bridge · one NIM container, three arms rotated per question.

  arm A  nim-only            (Vol.1 E3 benchmark_nim_only payload + stream_options.include_usage)
  arm B  NIM + Guardrails 0.21.0   (worker process, venv GR021_PY)
  arm C  NIM + Guardrails 0.23.0   (worker process, venv GR023_PY)

Order per question: A → 2 s → B → 2 s → C → 2 s (Vol.1 COOLDOWN = 2 s). 45 questions × 3 rounds = 135 per arm.
Warm-up: before round 1, each arm sends questions[0] once; those three requests are recorded as warm-up and
excluded from every statistic (pre-registered — the first request after READY is systematically slow).
Rail config: Vol.1 benchmark/guardrails/config.yml copied byte-for-byte into <out>/gr_config/, with the model name
replaced only if the container serves a different model id (the replacement is recorded).
Checkpoint: every request appended to <out>/rows.jsonl as it completes.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request
import requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
QUESTIONS = os.path.join(REPO, "benchmark", "e3_questions.json")
QUESTIONS_SHA = "5d7eeeaa9408977e28366e7b31a6f01905695a0c8ce10a6c314fa40de4a1c3ea"
RAIL_CONFIG = os.path.join(REPO, "benchmark", "guardrails", "config.yml")
MAX_TOKENS, ROUNDS, COOLDOWN = 500, 3, 2
TOP_P = 0.9   # explicit in all four cells: both NIM 1.13.1 and 2.0.12 log that the model's generation config overrides
              # the engine's sampling defaults (2.0.12 prints {'temperature': 0.6, 'top_p': 0.9}); temperature stays 0.0 (Vol.1)


def now():
    return subprocess.run(["date", "+%FT%T%z"], capture_output=True, text=True).stdout.strip()


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def nim_only(base, model, question):
    """Vol.1 run_e3_guardrails.py:77-121 timing logic; payload adds stream_options.include_usage (recorded deviation)."""
    payload = {"model": model, "messages": [{"role": "user", "content": question}], "max_tokens": MAX_TOKENS,
               "temperature": 0.0, "top_p": TOP_P, "stream": True, "stream_options": {"include_usage": True}}
    start = time.perf_counter(); first_token_time = None; full_response = ""; token_count = 0
    finish_reason = None; usage = None; status = None
    try:
        response = requests.post(base + "/v1/chat/completions", json=payload, stream=True, timeout=90)
        status = response.status_code
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: ") and line != "data: [DONE]":
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    try:
                        chunk = json.loads(line[6:])
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                        ch = chunk.get("choices") or []
                        if ch:
                            if ch[0].get("finish_reason"):
                                finish_reason = ch[0]["finish_reason"]
                            delta = ch[0].get("delta", {}).get("content", "")
                            if delta:
                                full_response += delta
                                token_count += len(delta.split())
                    except json.JSONDecodeError:
                        pass
        end = time.perf_counter()
    except Exception as e:
        return {"error": str(e)[:500], "http_status": status}
    total_sec = end - start
    row = {"ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
           "total_latency_ms": round(total_sec * 1000, 1), "tokens": token_count,
           "tps": round(token_count / total_sec, 1) if total_sec > 0 else 0, "response_full": full_response,
           "was_blocked": False, "finish_reason": finish_reason, "usage": usage, "http_status": status, "t_end_epoch": time.time()}
    if status != 200:
        row["error"] = f"HTTP {status}"
    return row


class Worker:
    def __init__(self, name, python, config_dir, log_path):
        env = dict(os.environ, GR_CONFIG_DIR=config_dir, PYTHONIOENCODING="utf-8")
        self.name = name
        self.log = open(log_path, "w", encoding="utf-8")
        self.p = subprocess.Popen([python, os.path.join(HERE, "gr_worker.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=self.log, env=env, text=True, encoding="utf-8", bufsize=1)
        hello = self._read(timeout_s=300)
        if not hello or not hello.get("ready"):
            raise RuntimeError(f"worker {name} not ready: {hello}")
        self.versions = hello["versions"]

    def _read(self, timeout_s=300):
        line = self.p.stdout.readline()
        return json.loads(line) if line else None

    def ask(self, key, text):
        self.p.stdin.write(json.dumps({"key": key, "text": text}) + "\n"); self.p.stdin.flush()
        r = self._read()
        return r if r is not None else {"key": key, "error": "worker returned no line (crashed?)"}

    def close(self):
        try:
            self.p.stdin.write(json.dumps({"stop": True}) + "\n"); self.p.stdin.flush(); self.p.wait(timeout=30)
        except Exception:
            self.p.kill()
        self.log.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--container", required=True)
    ap.add_argument("--cell-labels", required=True, help="e.g. 1,2 (arm B → first, arm C → second)")
    ap.add_argument("--image", required=True); ap.add_argument("--index-digest", required=True); ap.add_argument("--manifest-digest", required=True)
    ap.add_argument("--profile", required=True); ap.add_argument("--extra-env", required=True)
    ap.add_argument("--prediction", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--gr021-py", required=True); ap.add_argument("--gr023-py", required=True)
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    ap.add_argument("--question-limit", type=int, default=0, help="mock tests only; 0 = all 45")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    if sha(QUESTIONS) != QUESTIONS_SHA:
        sys.exit("e3_questions.json sha256 mismatch")
    qs = json.load(open(QUESTIONS, encoding="utf-8"))
    if a.question_limit:
        qs = qs[:a.question_limit]
    model = requests.get(a.base + "/v1/models", timeout=30).json()["data"][0]["id"]

    cfg_dir = os.path.join(a.out, "gr_config"); os.makedirs(cfg_dir, exist_ok=True)
    src = open(RAIL_CONFIG, encoding="utf-8").read()
    m = re.search(r"^(\s*model:\s*)(\S+)\s*$", src, flags=re.M)
    substituted = None
    if m and m.group(2) != model:
        substituted = {"from": m.group(2), "to": model}
        src = src[:m.start(2)] + model + src[m.end(2):]
    t = re.search(r"^(\s*)temperature:\s*0\.0\s*$", src, flags=re.M)
    if not t or "top_p:" in src:
        sys.exit("rail config: expected one 'temperature: 0.0' line and no top_p")
    src = src[:t.end()] + f"\n{t.group(1)}top_p: {TOP_P}" + src[t.end():]
    open(os.path.join(cfg_dir, "config.yml"), "w", encoding="utf-8", newline="").write(src)

    def smi():
        return subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version", "--format=csv,noheader"],
                              capture_output=True, text=True).stdout.strip()

    nim_ver = subprocess.run(["docker", "inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", a.container], capture_output=True, text=True).stdout
    nim_ver = next((l.split("=", 1)[1] for l in nim_ver.splitlines() if l.startswith("INFERENCE_MICROSERVICE_LLM_NIM_VERSION=")), None)
    cells = a.cell_labels.split(",")
    meta = {"experiment": "Vol.1-B NIM × Guardrails 2×2 bridge", "cells": {"B": cells[0], "C": cells[1]}, "model_served": model,
            "image": a.image, "image_index_digest": a.index_digest, "manifest_digest_amd64": a.manifest_digest, "profile": a.profile,
            "extra_env": a.extra_env, "nim_version_from_container_env": nim_ver, "prediction_file": os.path.basename(a.prediction),
            "prediction_sha256": sha(a.prediction), "questions": {"file": "benchmark/e3_questions.json", "sha256": QUESTIONS_SHA, "n": len(qs)},
            "rounds": a.rounds, "order": "per question A→B→C, 2 s cooldown after every request", "max_tokens": MAX_TOKENS,
            "rail_config": {"source": "benchmark/guardrails/config.yml", "source_sha256": sha(RAIL_CONFIG),
                            "used_sha256": sha(os.path.join(cfg_dir, "config.yml")), "model_name_substitution": substituted,
                            "added": f"top_p: {TOP_P} under the main model parameters"},
            "nim_only_payload": f"Vol.1 E3 (model, messages, max_tokens 500, temperature 0.0, stream) + top_p {TOP_P} + stream_options.include_usage",
            "started": now(), "ctx_start": smi()}
    wB = Worker("B", a.gr021_py, cfg_dir, os.path.join(a.out, "worker_B_gr021.stderr.txt"))
    wC = Worker("C", a.gr023_py, cfg_dir, os.path.join(a.out, "worker_C_gr023.stderr.txt"))
    meta["worker_versions"] = {"B": wB.versions, "C": wC.versions}
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    rows_f = open(os.path.join(a.out, "rows.jsonl"), "w", encoding="utf-8")

    def record(arm, q, rnd, r, warmup=False):
        r.update({"arm": arm, "question_id": q["id"], "category": q["category"], "expected_action": q["expected_action"],
                  "round": rnd, "warmup": warmup, "t": now()})
        rows_f.write(json.dumps(r, ensure_ascii=False) + "\n"); rows_f.flush()
        return r

    def one(arm, q, rnd, warmup=False):
        if arm == "A":
            r = nim_only(a.base, model, q["text"])
        elif arm == "B":
            r = wB.ask(f"{q['id']}#{rnd}", q["text"])
        else:
            r = wC.ask(f"{q['id']}#{rnd}", q["text"])
        r.pop("key", None)
        record(arm, q, rnd, r, warmup)
        time.sleep(COOLDOWN)
        return r

    for arm in ("A", "B", "C"):
        one(arm, qs[0], 0, warmup=True)
    print(f"warm-up done {now()}", flush=True)
    done = 0
    for rnd in range(1, a.rounds + 1):
        for q in qs:
            for arm in ("A", "B", "C"):
                r = one(arm, q, rnd)
                done += 1
                if "error" in r:
                    print(f"ERROR arm {arm} {q['id']} r{rnd}: {r['error'][:160]}", flush=True)
            if done % 45 == 0:
                print(f"  {done}/{len(qs) * a.rounds * 3} · {now()} · {smi()}", flush=True)
    rows_f.close(); wB.close(); wC.close()
    meta.update({"finished": now(), "ctx_end": smi()})
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"done {meta['finished']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
