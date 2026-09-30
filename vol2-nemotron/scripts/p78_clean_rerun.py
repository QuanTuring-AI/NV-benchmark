#!/usr/bin/env python3
"""Vol.2 · P78 G6 · the concurrency sweeps whose levels ended with other GPU load (Z3 audit) and that feed a Vol.2 number,
measured again with the GPU checked idle before every level.

Z3 read every level's end-of-level GPU record (gpu_end: utilization and power as the level finished) and classified it
against the clean-window fingerprint (utilization 0%, 26-42 W; P69 / P70). Sweeps with dirty levels that feed a number in
the Vol.2 write-up are repeated here, in the priority order below, with everything else unchanged: the image, profile and
environment of the original run, p53_concurrency_v2's calibration and level runner imported unchanged (AIPerf 0.11.0
flags, the discarded 120 s warm-up level, engine-death detection, level durations: 60 s first, then
min(600, max(60, 4 x the previous level's p99 latency x N / N_prev))). Added: G8 (tools/g8_gate.py) before every
level, the host record (tools/host_gate.py) per level, the no-overwrite check after every level. The original results are
not changed; each sweep here writes under its own directory.
Priority (stop between sweeps at the deadline):
  1. s256_C  Nemotron 3 Nano, image default cap (256), profile C, main container, levels 1..512   (the "128 inside the server SLO" row)
  2. s256_R  the same, profile R                                                            (the R column of that row)
  3. v2_A2_C p53_concurrency_v2's A2 at cap 32, profile C, main, levels 1..64
  4. v2_A2_R the same, profile R
  5. v2_A1_C p53_concurrency_v2's A1 (Nemotron Nano 9B v2, cap 32), profile C, main, levels 1..64 (its engine exits at 32: the exit is the ceiling)
  6. v2_A1_R the same, profile R
usage: p78_clean_rerun.py --aiperf EXE --tokenizer-root DIR [--out DIR] [--sweeps s256_C,...] [--deadline HH:MM] [--test]
env: NGC_ENV_FILE (--env-file, never read) · NIM_CACHE_DIR
"""
import argparse, datetime, json, os, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
import p53_concurrency_v2 as C2  # noqa: E402
from p53_concurrency import CONC_ENV  # noqa: E402
import g8_gate as G  # noqa: E402
import host_gate as HG  # noqa: E402
import overwrite_gate as O  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_OUT = os.path.join(HERE, "..", "results", "p78_clean_rerun")
SWEEPS = {
    "s256_C": {"arm": "A2", "env": {"NIM_MAX_MODEL_LEN": "8192"}, "profile": "C", "levels": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512], "source": "p55_concurrency_a2_256 C main"},
    "s256_R": {"arm": "A2", "env": {"NIM_MAX_MODEL_LEN": "8192"}, "profile": "R", "levels": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512], "source": "p55_concurrency_a2_256 R main"},
    "v2_A2_C": {"arm": "A2", "env": CONC_ENV["A2"], "profile": "C", "levels": [1, 2, 4, 8, 16, 32, 64], "source": "p53_concurrency_v2 A2 C main"},
    "v2_A2_R": {"arm": "A2", "env": CONC_ENV["A2"], "profile": "R", "levels": [1, 2, 4, 8, 16, 32, 64], "source": "p53_concurrency_v2 A2 R main"},
    "v2_A1_C": {"arm": "A1", "env": CONC_ENV["A1"], "profile": "C", "levels": [1, 2, 4, 8, 16, 32, 64], "source": "p53_concurrency_v2 A1 C main"},
    "v2_A1_R": {"arm": "A1", "env": CONC_ENV["A1"], "profile": "R", "levels": [1, 2, 4, 8, 16, 32, 64], "source": "p53_concurrency_v2 A1 R main"},
}


def gated_sweep(a, label, arm, prof, model, levels, log, ev, snap):
    event = lambda **kw: (ev.write(json.dumps({**kw, "sweep": label, "at": now()}, ensure_ascii=False) + "\n"), ev.flush())
    prev = None
    for n in levels:
        dur = (20 if a.test else 60) if prev is None else int(min(600, max(60, 4 * (prev["request_latency_p99_ms"] / 1000 * n / prev["concurrency"]))))
        g8 = G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S); event(kind="g8", concurrency=n, **g8)
        if not g8["pass"]:
            event(kind="level_null", concurrency=n, reason="G8 did not pass within the wait limit"); continue
        hg = HG.cell_start()
        art = os.path.join(a.out, label, f"{arm}_{prof}_main", f"c{n:04d}")
        rec = C2.run_level(a, model, arm, prof, n, dur, art, "main", log, {"sweep": label, "g8_waited_s": g8["waited_s"]})
        event(kind="host_level", concurrency=n, **HG.cell_end(hg))
        ov = O.check(snap); event(kind="overwrite_check", concurrency=n, **ov)
        if not ov["pass"]:
            return False
        if rec["engine_dead"]:
            log.write(json.dumps({"sweep": label, "arm": arm, "profile": prof, "skipped_levels": levels[levels.index(n) + 1:], "reason": f"engine dead after c={n}", "at": now()}) + "\n"); log.flush()
            break
        prev = rec if rec.get("request_latency_p99_ms") else prev
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer-root", required=True); ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--sweeps", default=",".join(SWEEPS)); ap.add_argument("--deadline"); ap.add_argument("--test", action="store_true")
    a = ap.parse_args(); a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    O.SCOPES = O.SCOPES + sorted(d for d in os.listdir(REPO) if d.startswith("vol") and d not in O.SCOPES)
    snap = O.snapshot(REPO, [os.path.relpath(a.out.split(os.sep + "harness_test")[0], REPO).replace(os.sep, "/")])   # the stage's results directory (its logs/ and harness_test/ included)
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    ev.write(json.dumps({"kind": "run_start", "sweeps": a.sweeps, "test": a.test, "host_calibration": HG.calibrate(), "at": now()}) + "\n"); ev.flush()
    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    for label in a.sweeps.split(","):
        if a.deadline and datetime.datetime.now().strftime("%H:%M") >= a.deadline and datetime.datetime.now().hour < 12:
            ev.write(json.dumps({"kind": "sweep_not_started", "sweep": label, "reason": f"deadline {a.deadline} reached", "at": now()}) + "\n"); ev.flush(); continue
        s = SWEEPS[label]; arm, prof = s["arm"], s["profile"]
        levels = s["levels"][:1] if a.test else s["levels"]
        ARMS[arm] = dict(ARMS[arm], env=s["env"])
        name = f"p78-rerun-{label.lower().replace('_', '-')}"
        st_ = start(arm, name, None, logdir)
        if not st_["ready"]:
            ev.write(json.dumps({"kind": "container_failed", "sweep": label, "reason": st_.get("reason"), "at": now()}) + "\n"); ev.flush()
            C2.save_logs(name, logdir); stop(name); continue
        time.sleep(5)
        model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
        requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 16, "stream": False}, timeout=120)
        warm = C2.run_level(a, model, arm, prof, 1, 20 if a.test else 120, os.path.join(a.out, label, f"{arm}_{prof}_main", "warmup", "c0001"), "main", log, {"warmup": True, "sweep": label})
        cal = C2.calibrate(model, prof) if not warm["engine_dead"] else None
        ev.write(json.dumps({"kind": "container_start", "sweep": label, "source": s["source"], "arm": arm, "profile": prof, "env": st_["env"], "levels": levels,
                             "image": ARMS[arm]["image"], "profile_id": ARMS[arm]["profile"], "cache_config": metrics_cache_config(), "calibration": cal,
                             "warmup_level": {k: warm.get(k) for k in ("rc", "completed", "engine_dead")}, "gpu_ready": gpu(), "at": now()}, ensure_ascii=False) + "\n"); ev.flush()
        ok = True
        if not warm["engine_dead"]:
            ok = gated_sweep(a, label, arm, prof, model, levels, log, ev, snap)
        C2.save_logs(name, logdir); stop(name)
        ev.write(json.dumps({"kind": "container_end", "sweep": label, "gpu_after_stop": gpu(), "at": now()}) + "\n"); ev.flush()
        if not ok:
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
