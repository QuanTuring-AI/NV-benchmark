#!/usr/bin/env python3
"""Vol.1 · P78 G1 · NIM's own FP8 choice at 1, 32 and 128 concurrent requests, measured in a clean window.

P70 re-checked the 128-request headline with the GPU otherwise idle, but its FP8 arm was refused by P59's prefix-cache
detector: two different prompts, the second one's time to first token 0.535 of the first. The first request after a
start is slow for reasons that are not a cache (warm-up), and the detector read that as a cache hit. This run replaces
the detector and repeats the FP8 cells; P59's and P70's pre-registrations are not changed.

Everything else is P70's harness (p70_clean_recheck.py and p59_nim_value.py in this directory, imported unchanged):
NIM 2.0.12 image, FP8 profile, context 8,192, the isolation check, the discarded 120 s warm-up level, the harness's own
calibration, the AIPerf command (streaming, C profile, --use-legacy-max-tokens, client token counts), 60 s per level,
seed 20260925 + c, G8 before every cell, the no-overwrite gate after every cell.
Arms, in one clean window: N-FP8 at 1, 32, 128, then N-BF16 at 128 as the anchor (its P70 value is 6,043 tok/s). The
4-bit Ollama denominator is P70's clean O-Q4 at 128 (780 tok/s); Ollama is not run again.

The detector (new; applied to both arms):
  1. one discarded request with a fresh prompt;
  2. five pairs of two different fresh prompts; within pair k the prompt sent first alternates (x_k then y_k for even k,
     y_k then x_k for odd k); r_k = TTFT(second) / TTFT(first);
  3. positive control: one fresh prompt sent twice; r_s = TTFT(second) / TTFT(first).
  Threshold T = 0.8 x min(r_1..r_5), fixed from the five pairs measured in this container before r_s is compared.
  fired = r_s < T  (the same prompt twice is told apart from every pair of different prompts)
  pass  = fired     (no pair of different prompts behaved like the same prompt twice, by construction of T; if the
                     positive control does not fire, the detector cannot tell a hit from a miss and the arm is null)
Paths are derived from this file's location; no volume directory name is written here.
usage: p78_fp8_clean.py --aiperf EXE --tokenizer DIR --store DIR [--out DIR] [--arms a,b] [--test]
env: NGC_ENV_FILE (--env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))
# P59 (bound, unchanged) imports p53_concurrency and, through p54_engine, p50_footprint from the directory they had when it
# was frozen; after the renames that directory has another name. The directories that hold them today are found, not written.
for _mod in ("p53_concurrency.py", "p50_footprint.py"):
    for _d in sorted(os.listdir(REPO)):
        if os.path.exists(os.path.join(REPO, _d, "scripts", _mod)) and os.path.join(REPO, _d, "scripts") not in sys.path:
            sys.path.append(os.path.join(REPO, _d, "scripts"))
import p59_nim_value as H  # noqa: E402
import p70_clean_recheck as P70  # noqa: E402
import g8_gate as G  # noqa: E402
import overwrite_gate as O  # noqa: E402
import host_gate as HG  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_OUT = os.path.join(HERE, "..", "results", "p78_fp8_clean")
PLAN = [("N-FP8", [1, 32, 128]), ("N-BF16", [128])]
SEED0 = P70.SEED0
PAIRS, MARGIN = 5, 0.8


def detector(kind, model, tok, send=None):
    """The P78 prefix-cache detector. `send(text) -> ttft_ms` is injectable for the self-test."""
    send = send or (lambda text: H.stream_once(kind, model, text, 16, tok)["ttft_ms"])
    discarded = send(H.nonce_prompt("R"))
    pairs = []
    for k in range(PAIRS):
        x, y = H.nonce_prompt("R"), H.nonce_prompt("R")
        first, second = (x, y) if k % 2 == 0 else (y, x)
        t1, t2 = send(first), send(second)
        pairs.append({"k": k, "first_sent": "x" if k % 2 == 0 else "y", "ttft_ms": [t1, t2], "ratio": (t2 / t1) if t1 and t2 else None})
    rs = [p["ratio"] for p in pairs if p["ratio"] is not None]
    thr = MARGIN * min(rs) if len(rs) == PAIRS else None
    same = H.nonce_prompt("R")
    s1, s2 = send(same), send(same)
    r_s = (s2 / s1) if s1 and s2 else None
    fired = thr is not None and r_s is not None and r_s < thr
    return {"discarded_ttft_ms": discarded, "pairs": pairs, "threshold": thr, "rule": f"threshold = {MARGIN} x min(pair ratios); fired = same-prompt ratio < threshold",
            "positive_control_same_prompt_twice": {"ttft_ms": [s1, s2], "ratio": r_s, "fired": fired}, "pass": fired}


def self_test():
    """Synthetic TTFT sequences through the same function: a cache that reuses the same prompt only (must pass), no cache
    at all (the control cannot fire: must fail), a cache that also hits across different prompts (must fail), and a slow
    first request after the discarded one (P70's case: must still pass)."""
    def seq(vals):
        it = iter(vals)
        return lambda text: next(it)
    cases = {
        "same_prompt_cache_only": ([300] + [200, 205, 210, 200, 198, 202, 205, 199, 201, 200] + [200, 20], True),
        "no_cache": ([300] + [200, 205, 210, 200, 198, 202, 205, 199, 201, 200] + [200, 199], False),
        "cross_prompt_hits": ([300] + [200, 30, 210, 25, 198, 28, 205, 22, 201, 26] + [200, 20], False),
        "slow_first_pair_after_warmup": ([300] + [219, 117, 205, 199, 201, 200, 205, 199, 201, 200] + [203, 20], True),
    }
    out = {}
    for name, (vals, want) in cases.items():
        r = detector(None, None, None, send=seq(vals))
        out[name] = {"pass": r["pass"], "want": want, "ok": r["pass"] == want, "threshold": r["threshold"], "r_s": r["positive_control_same_prompt_twice"]["ratio"]}
    return out


def run_arm(a, arm, levels, tok, log, ev, logdir, snap, state):
    kind = H.ARMS[arm]["kind"]
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": H.now()}, ensure_ascii=False) + "\n"), ev.flush())
    name = f"p78-{arm.lower()}"
    st_ = H.start_nim(arm, name, logdir)
    if not st_["ready"]:
        event(kind="container_failed", arm=arm, reason=st_.get("reason"), first_error_line=st_.get("first_error_line")); H.save_logs(name, logdir); H.stop(name); return True
    time.sleep(5)
    model = requests.get(H.BASE["nim"] + "/v1/models", timeout=30).json()["data"][0]["id"]
    extra = {"image": H.NIM_IMAGE, "env": st_["env"], "seconds_to_ready": st_["seconds_to_verdict"], "readback": H.nim_profile_readback(logdir, name),
             "captured_graph_sizes": st_.get("captured_graph_sizes")}
    iso = H.isolation(kind); det = detector(kind, model, tok)
    event(kind="container_start", arm=arm, name=name, model=model, isolation=iso, prefix_detector=det, gpu_ready=H.gpu(), **extra)
    print(f"  {arm}: isolation={iso['pass']} detector pass={det['pass']} threshold={det['threshold']} r_s={det['positive_control_same_prompt_twice']['ratio']}", flush=True)
    ok = True
    if iso["pass"] and det["pass"]:
        warm = H.run_level(a, arm, kind, model, "C", 1, 20 if a.test else 120, os.path.join(a.out, f"{arm}_C_main", "warmup", "c0001"), "main", log, SEED0 + 9000, {"warmup": True})
        cal = H.calibrate(kind, model, "C", tok)
        event(kind="profile_start", arm=arm, profile="C", calibration=cal, warmup_level={k: warm.get(k) for k in ("rc", "completed", "engine_dead")})
        if not state.get("g8_control"):
            pc = P70.g8_positive_control(kind, model, tok); state["g8_control"] = pc
            event(kind="g8_positive_control", arm=arm, **pc)
        for n in ([levels[0]] if a.test else levels):
            g8 = G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S)
            hg = HG.cell_start()
            event(kind="g8", arm=arm, concurrency=n, **g8)
            if not g8["pass"]:
                event(kind="cell_null", arm=arm, concurrency=n, reason="G8 did not pass within the wait limit"); continue
            art = os.path.join(a.out, f"{arm}_C_main", f"c{n:04d}")
            rec = H.run_level(a, arm, kind, model, "C", n, 20 if a.test else 60, art, "main", log, SEED0 + n,
                              {"g8_pass": True, "g8_waited_s": g8["waited_s"]})
            event(kind="host_cell", arm=arm, concurrency=n, **HG.cell_end(hg))
            ov = O.check(snap)
            event(kind="overwrite_check", arm=arm, concurrency=n, **ov)
            if not ov["pass"]:
                print(f"  NO-OVERWRITE GATE FAILED after {arm} c={n}: {ov['violations'][:3]}", flush=True)
                ok = False; break
            if rec["engine_dead"]:
                break
    else:
        event(kind="container_refused", arm=arm, reason="isolation or the P78 prefix-cache detector failed")
    H.save_logs(name, logdir); H.stop(name)
    event(kind="container_end", arm=arm, gpu_after_stop=H.gpu())
    return ok


def main():
    if "--self-test" in sys.argv:
        r = self_test(); print(json.dumps(r, indent=1)); return 0 if all(v["ok"] for v in r.values()) else 1
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--store", required=True); ap.add_argument("--test", action="store_true")
    a = ap.parse_args(); a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    snap = O.snapshot(REPO, [os.path.relpath(os.path.abspath(os.path.join(HERE, "..", "results", "p78_fp8_clean")), REPO).replace(os.sep, "/")])
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    ev.write(json.dumps({"kind": "overwrite_snapshot", "allowed": snap["allowed"], "tracked_differing": len(snap["modified"]), "watched": len(snap["others"]), "at": H.now()}) + "\n")
    ev.write(json.dumps({"kind": "detector_self_test", "result": self_test(), "at": H.now()}) + "\n")
    ev.write(json.dumps({"kind": "host_calibration", **HG.calibrate(), "at": H.now()}) + "\n"); ev.flush()
    if H.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    tok = H.tokenizer(a.tokenizer); state = {}
    for arm, levels in PLAN:
        print(f"##### arm {arm} {H.now()}", flush=True)
        if not run_arm(a, arm, levels, tok, log, ev, logdir, snap, state):
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
