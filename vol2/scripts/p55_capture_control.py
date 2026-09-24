#!/usr/bin/env python3
"""Vol.2 · A2 concurrency: does the sequence cap change the rate at a fixed concurrency through the CUDA-graph capture
size? (added after p55_concurrency_a2_{256,128,064}; control arms, not A2's configuration)

At profile C and the same concurrency, A2 ran faster the higher its max_num_seqs (c=32: 1,540 / 1,738 / 2,238 tok/s at
caps 32 / 128 / 256; cap 64, run later, was slowest of all: 1,130). vLLM 0.27.1 sets the largest CUDA-graph capture size to min(2 x max_num_seqs, 512) tokens
(vllm/config/vllm.py, _set_cudagraph_sizes); a step larger than that runs without a graph. The startup logs agree: 11 /
35 / 51 mixed prefill-decode sizes captured at caps 32 / 128 / 256. This run changes one setting within one session:
  s256_default  max_num_seqs 256 (image default), capture size by default (512)        -- the in-run reference
  s256_cg064    max_num_seqs 256 (image default), --max-cudagraph-capture-size 64     (cap-32's capture size)
Main and fresh containers of the same configuration differed by up to 31% at c=64 in the sweeps, so the reference is
measured in this run, back to back, not taken from another run.
Everything else is p55_concurrency_a2.py's, imported unchanged: NIM_MAX_MODEL_LEN 8192, profile C, the discarded 120 s
warm-up level, calibration, AIPerf flags, engine-death detection, logs saved before removal. Levels 1, 16, 32, 60 s each.
The capture setting actually applied is read back from the startup log (the "Capturing CUDA graphs ... N/N" lines).
usage: p55_capture_control.py --out DIR --aiperf EXE --tokenizer-root DIR [--conditions a,b] [--test]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, re, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
from p53_concurrency_v2 import calibrate, run_level, save_logs, sweep  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CONDITIONS = {
    "s256_default": {"NIM_MAX_MODEL_LEN": "8192"},
    "s256_cg064": {"NIM_MAX_MODEL_LEN": "8192", "NIM_PASSTHROUGH_ARGS": "--max-cudagraph-capture-size 64"},
}
CAPTURE = re.compile(r"Capturing CUDA graphs \(([^)]*)\):\s*100%\S*\s*(\d+)/(\d+)")


def captured(path):
    """{graph kind: number of sizes captured} from a saved startup log."""
    t = open(path, encoding="utf-8", errors="replace").read()
    return {k: int(n) for k, n, _ in CAPTURE.findall(t)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer-root", required=True)
    ap.add_argument("--conditions", default="s256_default,s256_cg064"); ap.add_argument("--levels", default="1,16,32"); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    levels = [int(x) for x in a.levels.split(",")]
    warm_duration = 20 if a.test else 120
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")

    def event(**kw):
        kw["at"] = now(); ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "container", "at")}, flush=True)

    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    arm, prof = "A2", "C"
    for cond in a.conditions.split(","):
        ARMS[arm] = dict(ARMS[arm], env=CONDITIONS[cond])
        name = f"p55-cgctl-{cond.replace('_', '-')}"
        st_ = start(arm, name, None, logdir)
        if not st_["ready"]:
            event(kind="container_failed", container=cond, reason=st_.get("reason"), log_lines=st_.get("log_lines"))
            save_logs(name, logdir); stop(name); continue
        time.sleep(5)
        model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
        cc = metrics_cache_config()
        requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 16, "stream": False}, timeout=120)
        warm = run_level(a, model, arm, prof, 1, warm_duration, os.path.join(a.out, f"{arm}_{prof}_{cond}", "warmup", "c0001"), cond, log, {"warmup": True})
        cal = calibrate(model, prof) if not warm["engine_dead"] else None
        event(kind="container_start", arm=arm, profile=prof, container=cond, levels=levels, image=ARMS[arm]["image"], profile_id=ARMS[arm]["profile"],
              env=st_["env"], seconds_to_ready=st_["seconds_to_ready"], gpu_ready=gpu(), cache_config=cc, log_lines=st_["log_lines"],
              captured_graph_sizes=captured(os.path.join(logdir, f"{name}.startup.log.txt")), served_model=model,
              warmup_level={k: warm.get(k) for k in ("rc", "completed", "engine_dead", "summary")}, calibration=cal)
        if not warm["engine_dead"]:
            sweep(a, arm, prof, model, levels, cond, log, 20 if a.test else 60)
        saved = save_logs(name, logdir)
        stop(name)
        event(kind="container_end", container=cond, gpu_after_stop=gpu(), container_log=saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
