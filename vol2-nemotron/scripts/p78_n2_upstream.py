#!/usr/bin/env python3
"""Vol.2 · P78 G5 · Nemotron Nano 9B v2 on the newest stable upstream vLLM image, as another deployment option.

On NIM 1.12.2 (the newest image for this model; Z2 found no newer tag) the engine exits when concurrency reaches its
sequence cap (P53), and generation slows by 38% past about 8k tokens of context (P53 long context). This asks whether the
upstream engine of today (vllm/vllm-openai v0.30.0) behaves the same on the same bf16 files. It is recorded as another
deployment option; the NIM 1.12.2 results are not changed.
Start: P54's ladder, from zero flags, one step added only after a failed start:
  0  model path only   1  + --trust-remote-code   2  + --max-model-len 16384   3  + --max-num-seqs 64
Measured configuration: the first step that starts and serves. Then, each after G8:
  single   10 questions of the co-residence sample, system "/no_think", max_tokens 500, streamed: generation rate
  conc     AIPerf 0.11.0, profile C, a discarded 120 s level at c=1, then 16, 32, 64 at 60 s (does the engine exit?)
  context  prompts of about 4k and 16k tokens (filler, the server's prompt_tokens recorded), each starting with its own tag
           so that no prefix is reused, "/no_think", about 200 words asked, max_tokens 256, three requests per depth after
           one discarded: time to first token and generation rate
usage: p78_n2_upstream.py --aiperf EXE --tokenizer DIR [--out DIR] [--test]
env: NIM_CACHE_DIR · V_CACHE_DIR
"""
import argparse, json, os, statistics as st, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))
import p78_engines as E  # noqa: E402
import p78_quality as Q  # noqa: E402
import p78_nim_vs_vllm as G4  # noqa: E402
import p53_concurrency_v2 as C2  # noqa: E402
import g8_gate as G  # noqa: E402
import host_gate as HG  # noqa: E402
import overwrite_gate as O  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_OUT = os.path.join(HERE, "..", "results", "p78_n2_upstream")
LADDER = [[], ["--trust-remote-code"], ["--trust-remote-code", "--max-model-len", "16384"],
          ["--trust-remote-code", "--max-model-len", "16384", "--max-num-seqs", "64"]]
LEVELS = [16, 32, 64]
DEPTHS = {"4k": 4000, "16k": 16000}
FILLER = "The quick brown fox jumps over the lazy dog."      # about 10.7 tokens per repeat (p53_concurrency_v2)
now = Q.now


def one(model, text, max_tokens):
    body = {"model": model, "messages": [{"role": "system", "content": "/no_think"}, {"role": "user", "content": text}],
            "max_tokens": max_tokens, "temperature": 0, "stream": True, "stream_options": {"include_usage": True}}
    t0 = time.perf_counter(); first = None; usage = None; status = None
    try:
        with requests.post(E.BASE + "/v1/chat/completions", json=body, stream=True, timeout=900) as r:
            status = r.status_code
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: ") or line.endswith("[DONE]"):
                    continue
                j = json.loads(line[6:])
                if j.get("usage"):
                    usage = j["usage"]
                for c in j.get("choices") or []:
                    d = c.get("delta") or {}
                    if (d.get("content") or d.get("reasoning_content")) and first is None:
                        first = time.perf_counter()
    except Exception as e:
        return {"error": str(e)[:200], "http_status": status}
    t1 = time.perf_counter(); n = (usage or {}).get("completion_tokens")
    return {"http_status": status, "ttft_ms": round((first - t0) * 1000, 1) if first else None, "prompt_tokens": (usage or {}).get("prompt_tokens"),
            "completion_tokens": n, "gen_rate": round((n - 1) / (t1 - first), 2) if (n and first and n > 1 and t1 > first) else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--out", default=DEFAULT_OUT); ap.add_argument("--test", action="store_true")
    a = ap.parse_args(); a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    O.SCOPES = O.SCOPES + sorted(d for d in os.listdir(REPO) if d.startswith("vol") and d not in O.SCOPES)
    snap = O.snapshot(REPO, [os.path.relpath(a.out.split(os.sep + "harness_test")[0], REPO).replace(os.sep, "/")])   # the stage's results directory (its logs/ and harness_test/ included)
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": now()}, ensure_ascii=False) + "\n"), ev.flush())
    lv = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    event(kind="run_start", test=a.test, image=E.IMAGES["V2N"]["image"], host_calibration=HG.calibrate(),
          image_id=E.sh(["docker", "image", "inspect", E.IMAGES["V2N"]["image"], "--format", "{{.Id}} {{json .RepoDigests}}"], 30).stdout.strip())
    if E.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    C2.aiperf_cmd = lambda a_, model, arm, prof, n, dur, art: [
        a.aiperf, "profile", "-m", model, "--endpoint-type", "chat", "--streaming", "-u", E.BASE,
        "--tokenizer", a.tokenizer, *C2.PROFILE_ARGS[prof], "--extra-inputs", "temperature:0",
        "--concurrency", str(n), "--warmup-request-count", str(n), "--benchmark-duration", str(dur),
        "--benchmark-grace-period", "0", "--use-server-token-count", "--no-gpu-telemetry", "--ui-type", "none",
        "--random-seed", str(20260921 + n), "--artifact-dir", art]
    name = None; model = None
    for k, args in enumerate(LADDER):
        name = f"p78g5-v2n-s{k}"
        st_ = E.launch("V2N", name, logdir, args=args)
        pr = None
        if st_["ready"]:
            time.sleep(5); model = E.served_model(); pr = one(model, "What is 2 + 2? Answer with one number.", 16)
        event(kind="attempt", step=k, flags=args, ready=st_["ready"], probe=pr, traps=st_.get("traps"), first_error_line=st_.get("first_error_line"),
              reason=st_.get("reason"), seconds=st_.get("seconds_to_verdict"))
        print(f"  step {k} {args}: ready={st_['ready']} probe={pr and pr.get('http_status')} {st_.get('first_error_line') or ''}", flush=True)
        if st_["ready"] and pr and pr.get("http_status") == 200:
            break
        E.save_logs(name, logdir); E.stop(name); name = None
    if not name:
        event(kind="arm_null", reason="no ladder step started and served"); return 0
    health = Q.warm_and_health("V2N", model); event(kind="health", **health)
    if health["pass"]:
        qs = G4.questions(a.test)[:10]
        g8 = G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S); event(kind="g8", cell="single", **g8)
        if g8["pass"]:
            rows = [dict(one(model, q["text"], 500), question_id=q["id"]) for q in qs]
            event(kind="single", rows=rows, gen_rate_median=st.median([r["gen_rate"] for r in rows if r.get("gen_rate")]) if any(r.get("gen_rate") for r in rows) else None)
        warm = C2.run_level(a, model, "V2N", "C", 1, 20 if a.test else 120, os.path.join(a.out, "V2N_C", "warmup", "c0001"), "main", lv, {"warmup": True})
        for n in ([16] if a.test else LEVELS):
            if warm.get("engine_dead"):
                break
            g8 = G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S); event(kind="g8", cell=f"c{n}", **g8)
            if not g8["pass"]:
                event(kind="cell_null", cell=f"c{n}", reason="G8 did not pass within the wait limit"); continue
            hg = HG.cell_start()
            rec = C2.run_level(a, model, "V2N", "C", n, 20 if a.test else 60, os.path.join(a.out, "V2N_C", f"c{n:04d}"), "main", lv, {"g8_waited_s": g8["waited_s"]})
            event(kind="host_cell", cell=f"c{n}", **HG.cell_end(hg))
            if rec["engine_dead"]:
                event(kind="engine_exit", concurrency=n, log_tail=E.save_logs(name, logdir)[-1500:]); break
        if E.alive(model):
            for label, depth in DEPTHS.items():
                g8 = G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S); event(kind="g8", cell=f"context_{label}", **g8)
                if not g8["pass"]:
                    continue
                # every request starts with its own tag, so no request reuses another's cached prefix (upstream vLLM caches
                # prefixes by default; the harness test's 16k TTFT of 114 ms was such a hit)
                body = lambda tag: f"[{tag}] " + " ".join([FILLER] * int(depth / 10.7)) + "\nDescribe this text and what a reader would notice about it, in about 200 words."
                one(model, body(f"discard-{label}"), 256)                  # discarded
                rows = [one(model, body(f"{label}-{i}"), 256) for i in range(1 if a.test else 3)]
                event(kind="context", depth=label, rows=rows)
        ov = O.check(snap); event(kind="overwrite_check", **ov)
    E.save_logs(name, logdir); E.stop(name)
    event(kind="engine_end", gpu_after_stop=E.gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
