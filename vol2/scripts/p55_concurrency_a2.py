#!/usr/bin/env python3
"""Vol.2 concurrency, A2 only, with the sequence cap raised: the p53_concurrency_v2 sweep of Nemotron 3 Nano repeated at
max_num_seqs N = 256 (the image default: no override at all), and at N = 64 and 128 (intermediate states, set with
NIM_PASSTHROUGH_ARGS "--max-num-seqs N" as in v2). In v2 both arms ran at 32 so that A1 and A2 shared one configuration;
32 is therefore a lower bound on A2's concurrency, not A2's own ceiling. A1 is not re-run (its engine dies at 32).

Everything that is not the sequence cap and the level ladder is p53_concurrency_v2's, imported unchanged: the profiles,
NIM_MAX_MODEL_LEN 8192, AIPerf 0.11.0 flags, the discarded 120 s warm-up level, the back-to-back calibration on the
profile's own prompt length, engine-death detection, level durations, fresh-container repeat of the two highest levels,
container logs saved before removal. Levels: 1, 2, 4, ... N, 2N (one level beyond the cap, so queueing is visible).
usage: p55_concurrency_a2.py --out DIR --aiperf EXE --tokenizer-root DIR --seqs {64,128,256} [--profiles C,R] [--levels ...] [--test]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
from p53_concurrency_v2 import calibrate, run_level, save_logs, sweep  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
IMAGE_DEFAULT_SEQS = 256   # the engine's own default for this image (footprint run: "max_num_seqs (256) exceeds available Mamba cache blocks")


def env_for(seqs):
    env = {"NIM_MAX_MODEL_LEN": "8192"}
    if seqs != IMAGE_DEFAULT_SEQS:
        env["NIM_PASSTHROUGH_ARGS"] = f"--max-num-seqs {seqs}"
    return env


def ladder(seqs):
    lv, n = [], 1
    while n <= 2 * seqs:
        lv.append(n); n *= 2
    return lv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer-root", required=True)
    ap.add_argument("--seqs", type=int, required=True, choices=(64, 128, 256)); ap.add_argument("--profiles", default="C,R")
    ap.add_argument("--levels", default=""); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    levels = [int(x) for x in a.levels.split(",")] if a.levels else ladder(a.seqs)
    first_duration = 20 if a.test else 60
    warm_duration = 20 if a.test else 120
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")

    def event(**kw):
        kw["at"] = now(); ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "profile", "container", "at")}, flush=True)

    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    arm = "A2"
    ARMS[arm] = dict(ARMS[arm], env=env_for(a.seqs))
    for prof in a.profiles.split(","):
        for tag, lv in (("main", levels), ("fresh", levels[-2:] if len(levels) >= 2 else levels)):
            if a.test and tag == "fresh":
                continue
            name = f"p55-conc-a2-s{a.seqs}-{prof.lower()}-{tag}"
            st_ = start(arm, name, None, logdir)
            if not st_["ready"]:
                event(kind="container_failed", arm=arm, profile=prof, container=tag, seqs=a.seqs, reason=st_.get("reason"), log_lines=st_.get("log_lines"))
                save_logs(name, logdir); stop(name); continue
            time.sleep(5)
            model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
            cc = metrics_cache_config()
            requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 16, "stream": False}, timeout=120)
            warm = run_level(a, model, arm, prof, 1, warm_duration, os.path.join(a.out, f"{arm}_{prof}_{tag}", "warmup", "c0001"), tag, log, {"warmup": True})
            cal = calibrate(model, prof) if (tag == "main" and not warm["engine_dead"]) else None
            event(kind="container_start", arm=arm, profile=prof, container=tag, seqs=a.seqs, levels=lv, image=ARMS[arm]["image"], profile_id=ARMS[arm]["profile"],
                  env=st_["env"], seconds_to_ready=st_["seconds_to_ready"], gpu_ready=gpu(), cache_config=cc, log_lines=st_["log_lines"],
                  served_model=model, warmup_level={k: warm.get(k) for k in ("rc", "completed", "engine_dead", "summary")}, calibration=cal)
            if not warm["engine_dead"]:
                sweep(a, arm, prof, model, lv, tag, log, first_duration)
            saved = save_logs(name, logdir)
            stop(name)
            event(kind="container_end", arm=arm, profile=prof, container=tag, gpu_after_stop=gpu(), container_log=saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
