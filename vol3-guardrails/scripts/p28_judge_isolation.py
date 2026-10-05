#!/usr/bin/env python3
"""P28 · judge isolation: the same answer text is judged by two output judges that differ only in the self-check
`max_tokens` of the rail config. No generation happens here — every text comes from the corpus file (built from the
P19 run) or from the two synthetic control segments carried in the prediction file.

  J1024  rail config as cell 4 / P19 arm C  (self-check prompts carry no max_tokens -> library default 1024)
  J3     the same config plus `max_tokens: 3` on the two self-check prompt entries (identical to P19 arm Cp)

Each text is judged REPS times by each judge. Per call: the raw completion's first word, its completion tokens, its
duration, the action's own return (is_safe), and the first 200 characters of the completion. The rail config's
self_check_output template references only `bot_response`, so the rendered prompt depends on the answer text alone.

Controls (P29 section 2), judged in the same batch and tagged `control_*`:
  control_violating  a synthetic, non-code policy violation -> both judges must answer Yes (mechanism check)
  control_benign     a synthetic harmless paragraph         -> both judges must answer No  (mechanism check)
Both texts live in the prediction file and are covered by its SHA-256.

usage: p28_judge_isolation.py --corpus corpus.json --out DIR --prediction pred.json --gr023-py PY --container NAME \
                             --image I --index-digest D --manifest-digest D --profile P --extra-env E [--reps 3] [--limit N]
Each text's result is appended to judgements.jsonl as it completes."""
import argparse, json, os, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from bridge_2x2 import sha, now, RAIL_CONFIG, TOP_P
from bridge_p19 import derive_configs, SELF_CHECK_MAX_TOKENS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prediction", required=True)
    ap.add_argument("--gr023-py", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--image", required=True); ap.add_argument("--index-digest", required=True); ap.add_argument("--manifest-digest", required=True)
    ap.add_argument("--profile", required=True); ap.add_argument("--extra-env", required=True)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="harness tests only; 0 = whole corpus")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    import requests
    model = requests.get(a.base + "/v1/models", timeout=30).json()["data"][0]["id"]
    dirs, substituted = derive_configs(a.out, model)
    judges = {"J1024": dirs["gr_config_default"], "J3": dirs["gr_config_mt3"]}

    pred = json.load(open(a.prediction, encoding="utf-8"))
    ctrl = pred["controls"]
    corpus = json.load(open(a.corpus, encoding="utf-8"))
    if a.limit:
        corpus = corpus[:a.limit]
    items = ([{"id": "control_violating", "kind": "control_violating", "sha256": ctrl["violating"]["sha256"],
               "text": ctrl["violating"]["text"], "sources": ["prediction:controls.violating"]},
              {"id": "control_benign", "kind": "control_benign", "sha256": ctrl["benign"]["sha256"],
               "text": ctrl["benign"]["text"], "sources": ["prediction:controls.benign"]}]
             + [dict(x, id=x["sha256"], kind="corpus") for x in corpus])
    for c in ("violating", "benign"):
        import hashlib
        if hashlib.sha256(ctrl[c]["text"].encode("utf-8")).hexdigest() != ctrl[c]["sha256"]:
            sys.exit(f"control {c}: text does not match the sha256 recorded in the prediction")

    def smi():
        return subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version",
                               "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()

    nim_ver = subprocess.run(["docker", "inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", a.container],
                             capture_output=True, text=True).stdout
    nim_ver = next((l.split("=", 1)[1] for l in nim_ver.splitlines() if l.startswith("INFERENCE_MICROSERVICE_LLM_NIM_VERSION=")), None)
    meta = {"experiment": "P28 judge isolation: one answer text, two output judges differing only in self-check max_tokens",
            "judges": {"J1024": "rail config as cell 4 / P19 arm C (no max_tokens on the self-check prompts)",
                       "J3": f"same config + max_tokens: {SELF_CHECK_MAX_TOKENS} on both self-check prompt entries (identical to P19 arm Cp)"},
            "model_served": model, "image": a.image, "image_index_digest": a.index_digest, "manifest_digest_amd64": a.manifest_digest,
            "profile": a.profile, "extra_env": a.extra_env, "nim_version_from_container_env": nim_ver,
            "prediction_file": os.path.basename(a.prediction), "prediction_sha256": sha(a.prediction),
            "corpus": {"file": os.path.basename(a.corpus), "sha256": sha(a.corpus), "texts": len(corpus)},
            "controls": {"violating_sha256": ctrl["violating"]["sha256"], "benign_sha256": ctrl["benign"]["sha256"],
                         "source": "carried in the prediction file, covered by its sha256"},
            "reps_per_text_per_judge": a.reps, "generation": "none - no answer is generated in this run",
            "rail_config": {"source": "benchmark/guardrails/config.yml", "source_sha256": sha(RAIL_CONFIG),
                            "J1024_used_sha256": sha(os.path.join(dirs["gr_config_default"], "config.yml")),
                            "J3_used_sha256": sha(os.path.join(dirs["gr_config_mt3"], "config.yml")),
                            "model_name_substitution": substituted, "added_both": f"top_p: {TOP_P} under the main model parameters"},
            "call": "nemoguardrails.library.self_check.output_check.actions.self_check_output, called directly with "
                    "context={'bot_message': text}; llm_task_manager, llm and config come from LLMRails(config_dir)",
            "started": now(), "ctx_start": smi()}
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    workers = {}
    for name, cfg in judges.items():
        env = dict(os.environ, GR_CONFIG_DIR=cfg, PYTHONIOENCODING="utf-8")
        p = subprocess.Popen([a.gr023_py, os.path.join(HERE, "p28_judge_worker.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=open(os.path.join(a.out, f"worker_{name}.stderr.txt"), "w", encoding="utf-8"),
                             env=env, text=True, encoding="utf-8", bufsize=1)
        hello = json.loads(p.stdout.readline())
        if not hello.get("ready"):
            raise RuntimeError(f"judge {name} not ready: {hello}")
        workers[name] = p
        meta.setdefault("worker_hello", {})[name] = hello
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def ask(name, text):
        p = workers[name]
        p.stdin.write(json.dumps({"text": text}) + "\n"); p.stdin.flush()
        line = p.stdout.readline()
        return json.loads(line) if line else {"error": "worker returned no line (crashed?)"}

    out_f = open(os.path.join(a.out, "judgements.jsonl"), "w", encoding="utf-8")
    for i, item in enumerate(items, 1):
        rec = {"id": item["id"], "kind": item["kind"], "sha256": item["sha256"], "len": len(item["text"]),
               "sources": item["sources"], "text_head": item["text"][:200], "judges": {}}
        for name in ("J1024", "J3"):
            rec["judges"][name] = [ask(name, item["text"]) for _ in range(a.reps)]
        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n"); out_f.flush()
        if i % 10 == 0 or i == len(items):
            print(f"  {i}/{len(items)} · {now()} · {smi()}", flush=True)
    out_f.close()
    for p in workers.values():
        try:
            p.stdin.write(json.dumps({"stop": True}) + "\n"); p.stdin.flush(); p.wait(timeout=30)
        except Exception:
            p.kill()
    meta.update({"finished": now(), "ctx_end": smi()})
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"done {meta['finished']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
