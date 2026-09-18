#!/usr/bin/env python3
"""P19 · fifth cell · one NIM container (cell 4 stack), three arms rotated per question:
  arm A   nim-only (Vol.1 E3 payload + top_p + stream_options.include_usage, as in the 2x2 bridge)
  arm C   NIM + NeMo Guardrails 0.23.0, rail config as in cell 4 (no max_tokens on the self-check prompts -> library default 1024)
  arm Cp  NIM + NeMo Guardrails 0.23.0, the same config with ONE change: `max_tokens: 3` on the self_check_input and
          self_check_output prompt entries (the 0.21.0 library default)
Both Guardrails arms run in the same venv (GR023_PY) in two worker processes; only the config directory differs.
Everything else (questions, rounds, cooldown, warm-up, checkpointing) is bridge_2x2.py, imported, not copied."""
import argparse, json, os, re, subprocess, sys, time
import requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from bridge_2x2 import nim_only, sha, now, QUESTIONS, QUESTIONS_SHA, RAIL_CONFIG, MAX_TOKENS, ROUNDS, COOLDOWN, TOP_P

SELF_CHECK_MAX_TOKENS = 3


class Worker:
    def __init__(self, name, python, config_dir, log_path):
        env = dict(os.environ, GR_CONFIG_DIR=config_dir, PYTHONIOENCODING="utf-8")
        self.name = name; self.log = open(log_path, "w", encoding="utf-8")
        self.p = subprocess.Popen([python, os.path.join(HERE, "gr_worker_p19.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=self.log, env=env, text=True, encoding="utf-8", bufsize=1)
        hello = self._read()
        if not hello or not hello.get("ready"):
            raise RuntimeError(f"worker {name} not ready: {hello}")
        self.versions = hello["versions"]; self.config_dir = hello.get("config_dir")

    def _read(self):
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


def derive_configs(out, model):
    """cell-4 derivation (model name substitution if needed, top_p added) -> gr_config_default/; plus max_tokens -> gr_config_mt3/"""
    src = open(RAIL_CONFIG, encoding="utf-8").read()
    m = re.search(r"^(\s*model:\s*)(\S+)\s*$", src, flags=re.M)
    substituted = None
    if m and m.group(2) != model:
        substituted = {"from": m.group(2), "to": model}; src = src[:m.start(2)] + model + src[m.end(2):]
    t = re.search(r"^(\s*)temperature:\s*0\.0\s*$", src, flags=re.M)
    if not t or "top_p:" in src or "max_tokens: 3" in src:
        sys.exit("rail config: expected one 'temperature: 0.0' line, no top_p, no self-check max_tokens")
    default = src[:t.end()] + f"\n{t.group(1)}top_p: {TOP_P}" + src[t.end():]
    mt3, n = re.subn(r"^(\s*)- task: (self_check_input|self_check_output)\s*$",
                     lambda mm: f"{mm.group(0)}\n{mm.group(1)}  max_tokens: {SELF_CHECK_MAX_TOKENS}", default, flags=re.M)
    if n != 2:
        sys.exit(f"rail config: expected exactly 2 self-check prompt entries, found {n}")
    dirs = {}
    for name, text in (("gr_config_default", default), ("gr_config_mt3", mt3)):
        d = os.path.join(out, name); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "config.yml"), "w", encoding="utf-8", newline="").write(text); dirs[name] = d
    return dirs, substituted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--container", required=True)
    ap.add_argument("--image", required=True); ap.add_argument("--index-digest", required=True); ap.add_argument("--manifest-digest", required=True)
    ap.add_argument("--profile", required=True); ap.add_argument("--extra-env", required=True)
    ap.add_argument("--prediction", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--gr023-py", required=True)
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
    dirs, substituted = derive_configs(a.out, model)

    def smi():
        return subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version", "--format=csv,noheader"],
                              capture_output=True, text=True).stdout.strip()
    nim_ver = subprocess.run(["docker", "inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", a.container], capture_output=True, text=True).stdout
    nim_ver = next((l.split("=", 1)[1] for l in nim_ver.splitlines() if l.startswith("INFERENCE_MICROSERVICE_LLM_NIM_VERSION=")), None)
    meta = {"experiment": "P19 fifth cell: cell 4 + self-check max_tokens 3", "cells": {"C": "4", "Cp": "5"}, "model_served": model,
            "image": a.image, "image_index_digest": a.index_digest, "manifest_digest_amd64": a.manifest_digest, "profile": a.profile,
            "extra_env": a.extra_env, "nim_version_from_container_env": nim_ver, "prediction_file": os.path.basename(a.prediction),
            "prediction_sha256": sha(a.prediction), "questions": {"file": "benchmark/e3_questions.json", "sha256": QUESTIONS_SHA, "n": len(qs)},
            "rounds": a.rounds, "order": "per question A -> C -> Cp, 2 s cooldown after every request", "max_tokens": MAX_TOKENS,
            "rail_config": {"source": "benchmark/guardrails/config.yml", "source_sha256": sha(RAIL_CONFIG),
                            "C_used_sha256": sha(os.path.join(dirs["gr_config_default"], "config.yml")),
                            "Cp_used_sha256": sha(os.path.join(dirs["gr_config_mt3"], "config.yml")),
                            "model_name_substitution": substituted, "added_both": f"top_p: {TOP_P} under the main model parameters",
                            "added_Cp_only": f"max_tokens: {SELF_CHECK_MAX_TOKENS} on the self_check_input and self_check_output prompt entries"},
            "nim_only_payload": f"Vol.1 E3 (model, messages, max_tokens 500, temperature 0.0, stream) + top_p {TOP_P} + stream_options.include_usage",
            "started": now(), "ctx_start": smi()}
    wC = Worker("C", a.gr023_py, dirs["gr_config_default"], os.path.join(a.out, "worker_C_gr023_default.stderr.txt"))
    wCp = Worker("Cp", a.gr023_py, dirs["gr_config_mt3"], os.path.join(a.out, "worker_Cp_gr023_mt3.stderr.txt"))
    meta["worker_versions"] = {"C": wC.versions, "Cp": wCp.versions}; meta["worker_config_dirs"] = {"C": wC.config_dir, "Cp": wCp.config_dir}
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    rows_f = open(os.path.join(a.out, "rows.jsonl"), "w", encoding="utf-8")

    def one(arm, q, rnd, warmup=False):
        if arm == "A":
            r = nim_only(a.base, model, q["text"])
        else:
            r = (wC if arm == "C" else wCp).ask(f"{q['id']}#{rnd}", q["text"])
        r.pop("key", None)
        r.update({"arm": arm, "question_id": q["id"], "category": q["category"], "expected_action": q["expected_action"],
                  "round": rnd, "warmup": warmup, "t": now()})
        rows_f.write(json.dumps(r, ensure_ascii=False) + "\n"); rows_f.flush()
        time.sleep(COOLDOWN)
        return r

    for arm in ("A", "C", "Cp"):
        one(arm, qs[0], 0, warmup=True)
    print(f"warm-up done {now()}", flush=True)
    done = 0
    for rnd in range(1, a.rounds + 1):
        for q in qs:
            for arm in ("A", "C", "Cp"):
                r = one(arm, q, rnd); done += 1
                if "error" in r:
                    print(f"ERROR arm {arm} {q['id']} r{rnd}: {r['error'][:160]}", flush=True)
            if done % 45 == 0:
                print(f"  {done}/{len(qs) * a.rounds * 3} · {now()} · {smi()}", flush=True)
    rows_f.close(); wC.close(); wCp.close()
    meta.update({"finished": now(), "ctx_end": smi()})
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"done {meta['finished']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
