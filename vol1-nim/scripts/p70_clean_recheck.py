#!/usr/bin/env python3
"""Vol.1 (renewed), P70 · the 128-request headline re-checked in a window with no other load on the GPU.

P59 (the source of the Vol.1 headline: profile C, 128 concurrent requests, NIM bf16 5,458 tok/s against the 4-bit Ollama
build's 741, 7.4x) ran from 2026-09-25 02:32 to 06:44 with other load on the desktop GPU: every level ended at 3-23%
utilization (median 5) where a clean window ends at 0 (tools/g8_gate.py). This run repeats the C profile at 1, 32 and 128
concurrent requests on P59's four configurations, with the GPU checked idle before every cell.

Everything is P59's harness (p59_nim_value.py in this directory, imported unchanged): images, NIM profiles, the Ollama slot
counts P59 found (O-Q4 16, O-FP16 8), context 8,192, the isolation check, the prefix-cache detector, the discarded 120 s
warm-up level on its own seed, the harness's own calibration (20 requests), the AIPerf command (streaming, C profile,
--use-legacy-max-tokens, client token counts), 60 s per level, seed 20260925 + c.
Order: one container per configuration, N-BF16 -> O-Q4 -> N-FP8 -> O-FP16, each running c = 1, 32, 128 in turn (four
container starts instead of twelve; every cell is still gated by G8, which is what an interleaved order would protect).
Gates added here: G8 (tools/g8_gate.py) before every measured cell, with a positive control once (sampled while the first
NIM container is decoding); the no-overwrite gate (tools/overwrite_gate.py) after every cell: tracked files unchanged and
new files only under this run's directory, else the run stops (exit 4) and the cell is void.
Paths are derived from this file's location; no volume directory name is written here.
usage: p70_clean_recheck.py --aiperf EXE --tokenizer DIR --store DIR [--out DIR] [--arms a,b] [--test]
env: NGC_ENV_FILE (NIM arms, --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, sys, threading, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))
import p59_nim_value as H  # noqa: E402
import g8_gate as G  # noqa: E402
import overwrite_gate as O  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_OUT = os.path.join(HERE, "..", "results", "p70_clean_recheck")
ORDER = ["N-BF16", "O-Q4", "N-FP8", "O-FP16"]
SLOTS = {"O-Q4": 16, "O-FP16": 8}
LEVELS = [1, 32, 128]
SEED0 = 20260925


def g8_positive_control(kind, model, tok):
    """G8 sampled while the engine decodes a stream of requests: it must not pass."""
    stop = threading.Event()

    def load():
        while not stop.is_set():
            H.stream_once(kind, model, H.nonce_prompt("C"), 400, tok)
    ts = [threading.Thread(target=load, daemon=True) for _ in range(4)]
    for t in ts:
        t.start()
    time.sleep(3)
    s = G.sample()
    stop.set()
    for t in ts:
        t.join(120)
    return {"what": "G8 sampled while 4 streams decode on the engine", "sample": s, "gate_passed": s["pass"], "control_fired": not s["pass"]}


def run_arm(a, arm, tok, log, ev, logdir, snap, state):
    kind = H.ARMS[arm]["kind"]
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": H.now()}, ensure_ascii=False) + "\n"), ev.flush())
    name = f"p70-{arm.lower()}"
    if kind == "ollama":
        st_ = H.start_ollama(name, a.store, SLOTS[arm], logdir)
        load = H.ollama_load(name, H.ARMS[arm]["model"]) if st_["ready"] else None
        if not (load and load["full_gpu"]):
            event(kind="container_failed", arm=arm, start=st_, load=load); H.save_logs(name, logdir); H.stop(name); return True
        model = H.ARMS[arm]["model"]
        extra = {"image": H.OLLAMA_IMAGE, "ollama_version": st_.get("version"), "env": st_["env"], "load": load}
    else:
        st_ = H.start_nim(arm, name, logdir)
        if not st_["ready"]:
            event(kind="container_failed", arm=arm, reason=st_.get("reason"), first_error_line=st_.get("first_error_line")); H.save_logs(name, logdir); H.stop(name); return True
        time.sleep(5)
        model = requests.get(H.BASE["nim"] + "/v1/models", timeout=30).json()["data"][0]["id"]
        extra = {"image": H.NIM_IMAGE, "env": st_["env"], "seconds_to_ready": st_["seconds_to_verdict"], "readback": H.nim_profile_readback(logdir, name),
                 "captured_graph_sizes": st_.get("captured_graph_sizes")}
    iso = H.isolation(kind); det = H.prefix_detector(kind, model, tok)
    event(kind="container_start", arm=arm, container="main", name=name, model=model, isolation=iso, prefix_detector=det, gpu_ready=H.gpu(), **extra)
    print(f"  {arm}: isolation={iso['pass']} detector={det['pass']} (control fired={det['positive_control_same_prompt_twice']['fired']})", flush=True)
    ok = True
    if iso["pass"] and det["pass"]:
        warm = H.run_level(a, arm, kind, model, "C", 1, 20 if a.test else 120, os.path.join(a.out, f"{arm}_C_main", "warmup", "c0001"), "main", log, SEED0 + 9000, {"warmup": True})
        cal = H.calibrate(kind, model, "C", tok)
        event(kind="profile_start", arm=arm, profile="C", container="main", calibration=cal, warmup_level={k: warm.get(k) for k in ("rc", "completed", "engine_dead")})
        if kind == "nim" and not state.get("g8_control"):
            pc = g8_positive_control(kind, model, tok); state["g8_control"] = pc
            event(kind="g8_positive_control", arm=arm, **pc)
            print(f"  G8 positive control: fired={pc['control_fired']} util={pc['sample']['util_pct_p50']} power={pc['sample']['power_w_p50']}", flush=True)
        for n in ([1] if a.test else LEVELS):
            g8 = G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S)
            event(kind="g8", arm=arm, concurrency=n, **g8)
            print(f"  {arm} c={n} G8 pass={g8['pass']} waited={g8['waited_s']} s last util={g8['attempts'][-1]['util_pct_p50']} power={g8['attempts'][-1]['power_w_p50']}", flush=True)
            if not g8["pass"]:
                event(kind="cell_null", arm=arm, concurrency=n, reason="G8 did not pass within the wait limit"); continue
            art = os.path.join(a.out, f"{arm}_C_main", f"c{n:04d}")
            rec = H.run_level(a, arm, kind, model, "C", n, 20 if a.test else 60, art, "main", log, SEED0 + n, {"g8_pass": True, "g8_waited_s": g8["waited_s"]})
            ov = O.check(snap)
            event(kind="overwrite_check", arm=arm, concurrency=n, **ov)
            if not ov["pass"]:
                print(f"  NO-OVERWRITE GATE FAILED after {arm} c={n}: {ov['violations'][:3]}", flush=True)
                ok = False; break
            if rec["engine_dead"]:
                break
    else:
        event(kind="container_refused", arm=arm, reason="isolation or prefix-cache detector failed")
    H.save_logs(name, logdir); H.stop(name)
    event(kind="container_end", arm=arm, container="main", gpu_after_stop=H.gpu())
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--store", required=True); ap.add_argument("--arms", default=",".join(ORDER)); ap.add_argument("--test", action="store_true")
    a = ap.parse_args(); a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    snap = O.snapshot(REPO, [os.path.relpath(os.path.abspath(os.path.join(HERE, "..", "results", "p70_clean_recheck")), REPO).replace(os.sep, "/")])
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    ev.write(json.dumps({"kind": "overwrite_snapshot", "allowed": snap["allowed"], "tracked_differing": len(snap["modified"]), "watched": len(snap["others"]), "at": H.now()}) + "\n"); ev.flush()
    if H.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    tok = H.tokenizer(a.tokenizer); state = {}
    for arm in a.arms.split(","):
        print(f"##### arm {arm} {H.now()}", flush=True)
        if not run_arm(a, arm, tok, log, ev, logdir, snap, state):
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
