#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q2 + Q4 · the chat profile at low concurrency, and O-Q4's step between 8 and 16 requests.

Q2: P59 placed the NIM-vs-Ollama total-throughput crossing between 1 and 8 concurrent requests. This run measures c=2 and
c=4 on all five P59 configurations, with c=1 and c=8 in the same session as anchors, so the crossing is read from one
session. Q4: P59's O-Q4 (Ollama 4-bit, 16 slots) served no more at c=8 than at c=1, then jumped at c=16; its per-request
timestamps show 8 requests decoding at once for most of the c=8 level, each at about an eighth of the single-stream rate.
O-Q4 therefore also runs c=9, 12 and 16 in the same container, with `ollama ps` sampled every second during its levels.
Everything is P59's harness (vol1a-revisit/scripts/p59_nim_value.py, imported unchanged): images, models, the slot counts
P59 found (O-Q4 16, O-FP16 8, O-Q4-def Ollama's choice), context 8,192, the isolation check, the prefix-cache detector,
the discarded 120 s warm-up level on its own seed, the harness's own calibration (20 requests), AIPerf flags
(--use-legacy-max-tokens, client token counts), 60 s per level. Profile C only; main containers only.
Per level, from AIPerf's per-request export (not kept), the share of the level's time with k requests decoding at once
(first token to last) is written to concurrency.jsonl.
usage: p62_levels.py --out DIR --aiperf EXE --tokenizer DIR --store DIR [--arms a,b] [--test]
env: NGC_ENV_FILE (NIM arms, --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, subprocess, sys, threading, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p59_nim_value as H  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ORDER = ["O-Q4", "N-BF16", "O-FP16", "N-FP8", "O-Q4-def"]
SLOTS = {"O-Q4": 16, "O-FP16": 8, "O-Q4-def": None}     # P59: the largest that loaded 100% on GPU at 8,192 / not set
LEVELS = [1, 2, 4, 8]
Q4_EXTRA = {"O-Q4": [9, 12, 16]}
SEED0 = 20260926


def decoding_share(art):
    p = os.path.join(art, "profile_export.jsonl")
    if not os.path.exists(p):
        return None
    ev = []
    for l in open(p, encoding="utf-8"):
        r = json.loads(l); md = r.get("metadata") or {}; m = r.get("metrics") or {}
        if md.get("benchmark_phase") != "profiling" or r.get("error"):
            continue
        ttft = (m.get("time_to_first_token") or {}).get("value")
        if ttft:
            ev += [(md["request_start_ns"] + ttft * 1e6, 1), (md["request_end_ns"], -1)]
    ev.sort(); cur = 0; last = None; dist = {}; tot = 0; mx = 0
    for t, d in ev:
        if last is not None:
            dist[cur] = dist.get(cur, 0) + (t - last); tot += t - last
        cur += d; mx = max(mx, cur); last = t
    return {"max_decoding_at_once": mx, "time_share_by_decoding": {str(k): round(v / tot, 4) for k, v in sorted(dist.items())} if tot else None}


class PsSampler(threading.Thread):
    def __init__(self, name, path):
        super().__init__(daemon=True); self.name_, self.f = name, open(path, "a", encoding="utf-8", newline="\n"); self.stop_ = threading.Event()

    def run(self):
        while not self.stop_.is_set():
            ps = H.sh(["docker", "exec", self.name_, "ollama", "ps"], 30).stdout
            row = next((l.strip() for l in ps.splitlines()[1:] if l.strip()), "")
            self.f.write(json.dumps({"t": time.time(), "ollama_ps": row}) + "\n"); self.f.flush()
            self.stop_.wait(1.0)


def run_arm(a, arm, tok, log, ev, conc, logdir):
    kind = H.ARMS[arm]["kind"]
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": H.now()}, ensure_ascii=False) + "\n"), ev.flush())
    name = f"p62-{arm.lower()}"
    if kind == "ollama":
        st_ = H.start_ollama(name, a.store, SLOTS[arm], logdir)
        load = H.ollama_load(name, H.ARMS[arm]["model"]) if st_["ready"] else None
        if not (load and load["full_gpu"]):
            event(kind="container_failed", arm=arm, start=st_, load=load); H.save_logs(name, logdir); H.stop(name); return
        model = H.ARMS[arm]["model"]
        extra = {"image": H.OLLAMA_IMAGE, "ollama_version": st_.get("version"), "env": st_["env"], "load": load}
    else:
        st_ = H.start_nim(arm, name, logdir)
        if not st_["ready"]:
            event(kind="container_failed", arm=arm, reason=st_.get("reason"), first_error_line=st_.get("first_error_line")); H.save_logs(name, logdir); H.stop(name); return
        time.sleep(5)
        model = requests.get(H.BASE["nim"] + "/v1/models", timeout=30).json()["data"][0]["id"]
        extra = {"image": H.NIM_IMAGE, "env": st_["env"], "seconds_to_ready": st_["seconds_to_verdict"], "captured_graph_sizes": st_.get("captured_graph_sizes")}
    iso = H.isolation(kind); det = H.prefix_detector(kind, model, tok)
    event(kind="container_start", arm=arm, container="main", name=name, model=model, isolation=iso, prefix_detector=det, gpu_ready=H.gpu(), **extra)
    print(f"  {arm}: isolation={iso['pass']} detector={det['pass']} (control fired={det['positive_control_same_prompt_twice']['fired']})", flush=True)
    if iso["pass"] and det["pass"]:
        warm = H.run_level(a, arm, kind, model, "C", 1, 20 if a.test else 120, os.path.join(a.out, f"{arm}_C_main", "warmup", "c0001"), "main", log, SEED0 + 9000, {"warmup": True})
        cal = H.calibrate(kind, model, "C", tok)
        event(kind="profile_start", arm=arm, profile="C", container="main", calibration=cal, warmup_level={k: warm.get(k) for k in ("rc", "completed", "engine_dead")})
        sampler = PsSampler(name, os.path.join(a.out, f"ollama_ps_{arm}.jsonl")) if kind == "ollama" and arm in Q4_EXTRA else None
        if sampler:
            sampler.start()
        for n in (LEVELS + Q4_EXTRA.get(arm, [])) if not a.test else [1, 2]:
            art = os.path.join(a.out, f"{arm}_C_main", f"c{n:04d}")
            rec = H.run_level(a, arm, kind, model, "C", n, 20 if a.test else 60, art, "main", log, SEED0 + n, {})
            conc.write(json.dumps({"arm": arm, "profile": "C", "concurrency": n, **(decoding_share(art) or {})}) + "\n"); conc.flush()
            if rec["engine_dead"]:
                break
        if sampler:
            sampler.stop_.set(); sampler.join(5)
    else:
        event(kind="container_refused", arm=arm, reason="isolation or prefix-cache detector failed")
    H.save_logs(name, logdir); H.stop(name)
    event(kind="container_end", arm=arm, container="main", gpu_after_stop=H.gpu())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--store", required=True); ap.add_argument("--arms", default=",".join(ORDER)); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    conc = open(os.path.join(a.out, "concurrency.jsonl"), "a", encoding="utf-8", newline="\n")
    if H.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    tok = H.tokenizer(a.tokenizer)
    for arm in a.arms.split(","):
        print(f"##### arm {arm} {H.now()}", flush=True)
        run_arm(a, arm, tok, log, ev, conc, logdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
