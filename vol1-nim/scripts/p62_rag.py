#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q3 · the RAG profile (R: 3,500+-300 input / 500+-50 output tokens) for the two NIM arms, with the
calibration gate repaired.

P59 reused prompts nowhere by design (nonce-led calibration prompts, a warm-up level on its own seed) and checked for
prefix-cache reuse through time to first token only. Here the check reads the server: vLLM's Prometheus counters
`vllm:prefix_cache_queries` and `vllm:prefix_cache_hits` (tokens) on /metrics, read before and after each request.
  positive control  one ~3,500-token prompt sent twice: the second request's hits must be >= 50% of its queried tokens
                    (the detector fires); if it does not, the detector is not working and the container stops (null)
  negative form     two calibration-form prompts (each led by its own nonce): hits of the second <= HIT_SHARE of its
                    queried tokens (the chat template's fixed preamble is shared by every request and is allowed for)
  calibration       the harness's 20 calibration requests (P59's form: nonce first, then filler, fresh connection each),
                    each with its own counter delta; any request whose hits exceed HIT_SHARE of its queried tokens
                    rejects the calibration (null), whatever its timing
  levels            each AIPerf level's counter delta over the level (warm-up included in the level's own window is
                    not possible to separate, so the delta is read around the whole AIPerf call) -> hit share per level
  server-side readings (reported, not a gate) the server's own TTFT / prefill / queue time counters for each of the
                    harness's calibration requests, and AIPerf's server-metrics export for each level: they show
                    whether a gap between AIPerf and the harness's own client is in the client or in the server
P59's health gate (decode rate at c=1 on profile C x bytes per token / 1,792 GB/s >= 0.40) needs a profile-C c=1 level:
the main container runs one (60 s, after a discarded 60 s C warm-up) before profile R; no other C level is run.
Everything else is P59's harness imported unchanged (images, profiles c4789f7a / 092ed421, NIM_MAX_MODEL_LEN 8192,
VLLM_USE_V2_MODEL_RUNNER=0, isolation check, TTFT detector, discarded 120 s warm-up level on its own seed, levels
1, 8, 16, 32, 64, 128 at 60 s, then a fresh container for 64 and 128, --use-legacy-max-tokens).
usage: p62_rag.py --out DIR --aiperf EXE --tokenizer DIR [--arms a,b] [--test]
env: NGC_ENV_FILE (--env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, re, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p59_nim_value as H  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ORDER = ["N-BF16", "N-FP8"]
LEVELS = [1, 8, 16, 32, 64, 128]
FRESH = [64, 128]
SEED0 = 20260927
HIT_SHARE = 0.02      # hits / queried tokens above this on one request = a reused prefix beyond the template preamble
FIRE = 0.50           # the positive control must reach this share
MET = re.compile(r"^vllm:prefix_cache_(queries|hits)(?:_total)?(?:\{[^}]*\})?\s+([0-9.eE+-]+)\s*$")
SRV = re.compile(r"^vllm:(time_to_first_token_seconds|request_prefill_time_seconds|request_queue_time_seconds)_(sum|count)(?:\{[^}]*\})?\s+([0-9.eE+-]+)\s*$")
SRV_KEYS = ("vllm:time_to_first_token_seconds", "vllm:request_prefill_time_seconds", "vllm:request_queue_time_seconds", "vllm:request_prompt_tokens")


def counters():
    try:
        t = requests.get(H.BASE["nim"] + "/metrics", timeout=30).text
    except Exception as e:
        return {"error": str(e)[:200]}
    c = {"queries": 0.0, "hits": 0.0, "lines": 0}
    for l in t.splitlines():
        m = MET.match(l.strip())
        if m:
            c[m.group(1)] += float(m.group(2)); c["lines"] += 1
        m = SRV.match(l.strip())
        if m:
            c[f"{m.group(1)}_{m.group(2)}"] = c.get(f"{m.group(1)}_{m.group(2)}", 0.0) + float(m.group(3))
    return c


def delta(a, b):
    if "error" in a or "error" in b or not a.get("lines") or not b.get("lines"):
        return None
    q, h = b["queries"] - a["queries"], b["hits"] - a["hits"]
    srv = {}
    for k in ("time_to_first_token_seconds", "request_prefill_time_seconds", "request_queue_time_seconds"):
        n = b.get(k + "_count", 0) - a.get(k + "_count", 0); t = b.get(k + "_sum", 0) - a.get(k + "_sum", 0)
        srv[k.replace("_seconds", "_ms_mean")] = round(1000 * t / n, 2) if n else None
    return {"queried_tokens": q, "hit_tokens": h, "hit_share": round(h / q, 5) if q else None, "server": srv}


def one(model, text, osl, tok):
    a = counters(); r = H.stream_once("nim", model, text, osl, tok); b = counters()
    r["prefix_cache"] = delta(a, b); return r


def detector(model, tok):
    one(model, H.nonce_prompt("R"), 16, tok)   # discarded: first long prefill after load
    same = H.nonce_prompt("R")
    a1, a2 = one(model, same, 16, tok), one(model, same, 16, tok)
    b1, b2 = one(model, H.nonce_prompt("R"), 16, tok), one(model, H.nonce_prompt("R"), 16, tok)
    pc = a2["prefix_cache"]; ng = b2["prefix_cache"]
    fired = bool(pc and pc["hit_share"] is not None and pc["hit_share"] >= FIRE)
    neg_ok = bool(ng and ng["hit_share"] is not None and ng["hit_share"] <= HIT_SHARE)
    return {"metrics_available": pc is not None, "positive_control_same_prompt_twice": {"first": a1["prefix_cache"], "second": pc, "fired": fired,
            "ttft_ms": [a1["ttft_ms"], a2["ttft_ms"]]},
            "negative_form_two_prompts": {"first": b1["prefix_cache"], "second": ng, "ttft_ms": [b1["ttft_ms"], b2["ttft_ms"]], "pass": neg_ok},
            "pass": fired and neg_ok}


def calibrate(model, tok):
    import statistics as st
    rows = [dict(one(model, H.nonce_prompt("R"), H.CAL["R"]["osl"], tok), i=i, warmup=(i == 0)) for i in range(H.CAL_N + 1)]
    ok = [r for r in rows if not r["warmup"] and r["ttft_ms"] and r["itl_ms"]]
    hit = [r["i"] for r in rows if not r["warmup"] and (r["prefix_cache"] is None or (r["prefix_cache"]["hit_share"] or 0) > HIT_SHARE)]
    return {"profile": "R", "rows": rows, "n_ok": len(ok), "requests_with_hits_or_no_counter": hit, "rejected_for_hits": bool(hit),
            "ttft_ms_p50": round(st.median(r["ttft_ms"] for r in ok), 2) if ok and not hit else None,
            "itl_ms_p50": round(st.median(r["itl_ms"] for r in ok), 3) if ok and not hit else None,
            "ttft_ms_p50_measured": round(st.median(r["ttft_ms"] for r in ok), 2) if ok else None,
            "itl_ms_p50_measured": round(st.median(r["itl_ms"] for r in ok), 3) if ok else None,
            "client_prompt_tokens_p50": st.median(r["client_prompt_tokens"] for r in ok) if ok else None,
            "server_ttft_ms_p50": round(st.median(r["prefix_cache"]["server"]["time_to_first_token_ms_mean"] for r in ok if (r.get("prefix_cache") or {}).get("server", {}).get("time_to_first_token_ms_mean")), 2) if ok else None,
            "server_prefill_ms_p50": round(st.median(r["prefix_cache"]["server"]["request_prefill_time_ms_mean"] for r in ok if (r.get("prefix_cache") or {}).get("server", {}).get("request_prefill_time_ms_mean")), 2) if ok else None}


def server_export(art):
    """AIPerf's own server-metrics export for the level (its profiling window): the server's TTFT, prefill, queue and
    prompt-token histograms, mean and p50 estimate."""
    p = os.path.join(art, "server_metrics_export.json")
    if not os.path.exists(p):
        return None
    m = json.load(open(p, encoding="utf-8")).get("metrics") or {}
    out = {}
    for k in SRV_KEYS:
        stt = ((m.get(k) or {}).get("series") or [{}])[0].get("stats") or {}
        out[k.split(":")[1]] = {"count": stt.get("count"), "avg": stt.get("avg"), "p50_estimate": stt.get("p50_estimate")}
    return out


def level(a, arm, model, n, dur, art, tag, log, seed, extra):
    c0 = counters(); rec = H.run_level(a, arm, "nim", model, "R", n, dur, art, tag, log, seed, extra); c1 = counters()
    d = delta(c0, c1)
    if d is not None:
        d["aiperf_server_metrics"] = server_export(art)
    return rec, d


def run_arm(a, arm, tok, log, ev, pcl, logdir):
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": H.now()}, ensure_ascii=False) + "\n"), ev.flush())
    for tag in (("main",) if a.test else ("main", "fresh")):
        name = f"p62r-{arm.lower()}-{tag}"
        st_ = H.start_nim(arm, name, logdir)
        if not st_["ready"]:
            event(kind="container_failed", arm=arm, container=tag, reason=st_.get("reason")); H.save_logs(name, logdir); H.stop(name); continue
        time.sleep(5)
        model = requests.get(H.BASE["nim"] + "/v1/models", timeout=30).json()["data"][0]["id"]
        iso = H.isolation("nim"); det = detector(model, tok)
        event(kind="container_start", arm=arm, container=tag, name=name, model=model, isolation=iso, prefix_detector=det, gpu_ready=H.gpu(),
              image=H.NIM_IMAGE, env=st_["env"], seconds_to_ready=st_["seconds_to_verdict"], captured_graph_sizes=st_.get("captured_graph_sizes"))
        print(f"  {arm} {tag}: isolation={iso['pass']} detector={det['pass']} fired={det['positive_control_same_prompt_twice']['fired']} "
              f"pos={det['positive_control_same_prompt_twice']['second']} neg={det['negative_form_two_prompts']['second']}", flush=True)
        if iso["pass"] and det["pass"]:
            if tag == "main":   # P59's health gate reads the profile-C c=1 level: a discarded 60 s C warm-up, then that level
                H.run_level(a, arm, "nim", model, "C", 1, 20 if a.test else 60, os.path.join(a.out, f"{arm}_C_{tag}", "warmup", "c0001"), tag, log, SEED0 + 9001, {"warmup": True})
                H.run_level(a, arm, "nim", model, "C", 1, 20 if a.test else 60, os.path.join(a.out, f"{arm}_C_{tag}", "c0001"), tag, log, SEED0 + 1001, {"for_health_gate": True})
            wrec, wd = level(a, arm, model, 1, 20 if a.test else 120, os.path.join(a.out, f"{arm}_R_{tag}", "warmup", "c0001"), tag, log, SEED0 + 9000, {"warmup": True})
            pcl.write(json.dumps({"arm": arm, "container": tag, "concurrency": 1, "warmup": True, "prefix_cache": wd}) + "\n"); pcl.flush()
            cal = calibrate(model, tok) if tag == "main" else None
            event(kind="profile_start", arm=arm, profile="R", container=tag, calibration=cal, warmup_level={k: wrec.get(k) for k in ("rc", "completed", "engine_dead")})
            for n in ([1, 8] if a.test else (LEVELS if tag == "main" else FRESH)):
                rec, d = level(a, arm, model, n, 20 if a.test else 60, os.path.join(a.out, f"{arm}_R_{tag}", f"c{n:04d}"), tag, log, SEED0 + n, {})
                pcl.write(json.dumps({"arm": arm, "container": tag, "concurrency": n, "prefix_cache": d}) + "\n"); pcl.flush()
                if rec["engine_dead"]:
                    break
        else:
            event(kind="container_refused", arm=arm, container=tag, reason="isolation or prefix-cache detector failed")
        H.save_logs(name, logdir); H.stop(name)
        event(kind="container_end", arm=arm, container=tag, gpu_after_stop=H.gpu())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--arms", default=",".join(ORDER)); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    pcl = open(os.path.join(a.out, "prefix_cache_levels.jsonl"), "a", encoding="utf-8", newline="\n")
    if H.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    tok = H.tokenizer(a.tokenizer)
    for arm in a.arms.split(","):
        print(f"##### arm {arm} {H.now()}", flush=True)
        run_arm(a, arm, tok, log, ev, pcl, logdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
