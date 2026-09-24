#!/usr/bin/env python3
"""Vol.2 long context · addendum: the same depth measurement as p53_longctx.py, with a timed warm-up phase before the
measured requests, because the main run showed that one discarded request is not enough on A2.

In the main run every A2 container's first requests were slow and got faster request by request (1k depth: 122, 119,
128, 171, 280 tok/s for the five measured requests; 4k: 140, 190, 295, 315, 315), so the 1k and 4k medians describe
the engine's first minute, not its steady state. A1 showed no such drift. This addendum keeps everything of the main
run (prompts, offsets, max_tokens, model-length rule, max_num_seqs 32, one container per depth) and adds a warm-up
phase: discarded requests at the same depth (offsets that the measured requests do not use) until at least WARM_S
seconds and WARM_N requests have passed AND the last three generation rates agree within WARM_TOL AND all three are
at or above WARM_FAST_TPS for the arm, or WARM_MAX_N requests / WARM_MAX_S seconds have been spent (then the depth is
marked not stabilized and measured anyway). The length of A2's slow phase is not fixed: a diagnosis on 2026-09-23
(harness_test/a2_warm_diag_*) saw it end after 3 requests (~16 s, mid-request), two harness tests saw 6-7 requests
(43-50 s) still slow and, in the second, the last three slow rates already agreed within 5% (160-167 tok/s) -- so
stability alone does not mean the slow phase is over. The rate threshold separates the two states at every depth
observed (slow 119-175 tok/s at 1k-4k; steady 256-319 at 1k-64k); A1 has no slow phase and its threshold is 0. Once
ended the slow phase did not return after 20-30 s idle. In the diagnosis the SM clock was already 2.9 GHz during the
slow requests at 130-230 W and 100% utilisation: an engine-side condition, not a clock ramp; the container log says
nothing about it. The warm-up rows are recorded with warmup=true so the transient itself is documented; the analysis uses
only the measured rows. Startup logs are saved by start(); the container's log is also
saved before removal.
usage: p53_longctx_addendum.py --out DIR [--depths 1024,4096,16384,65536] [--arms A2] [--test]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import ARMS, BASE, docker_logs, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
from p53_longctx import COOLDOWN, N_REQ, QFILE, build_prompt, model_len_for, request  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
WARM_S, WARM_N, WARM_TOL, WARM_MAX_N, WARM_MAX_S = 60, 6, 0.05, 25, 300
WARM_FAST_TPS = {"A1": 0.0, "A2": 220.0}   # a default: below every steady rate seen on A2 (256-319 tok/s, 1k-64k) and above every slow-phase rate (119-175)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--depths", default="1024,4096,16384,65536")
    ap.add_argument("--arms", default="A2"); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    depths = [int(x) for x in a.depths.split(",")]
    nreq = 2 if a.test else N_REQ
    warm_s, warm_n, warm_max_n, warm_max_s = (20, 2, 6, 60) if a.test else (WARM_S, WARM_N, WARM_MAX_N, WARM_MAX_S)
    req_f = open(os.path.join(a.out, "requests.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    bank = json.load(open(QFILE, encoding="utf-8"))

    def event(**kw):
        kw["at"] = now(); ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "depth", "at")}, flush=True)

    def row(r, arm, depth, ml, i, model, warmup, at, gb):
        r.update({"arm": arm, "depth_target": depth, "max_model_len": ml, "i": i, "warmup": warmup, "at": at, "served_model": model,
                  "gpu_before": gb, "gpu_after": gpu(), "docker_ps_before": sh(["docker", "ps", "--format", "{{.Names}}"], timeout=30).stdout.split()})
        req_f.write(json.dumps(r, ensure_ascii=False) + "\n"); req_f.flush()
        print(f"  {arm} d={depth} {'warm' if warmup else 'i'}={i} pt={r.get('prompt_tokens')} ttft={r.get('ttft_ms')} gen={r.get('generation_tps')} {r.get('finish_reason')} {r.get('error', '')}", flush=True)

    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    for arm in a.arms.split(","):
        for depth in depths:
            ml = model_len_for(depth)
            env = {"NIM_MAX_MODEL_LEN": str(ml)}
            env.update({"NIM_MAX_NUM_SEQS": "32"} if arm == "A1" else {"NIM_PASSTHROUGH_ARGS": "--max-num-seqs 32"})
            ARMS[arm] = dict(ARMS[arm], env=env)
            name = f"p53-ctxadd-{arm.lower()}-{depth}"
            before = gpu()
            st_ = start(arm, name, None, logdir)
            if not st_["ready"]:
                event(kind="depth_failed", arm=arm, depth=depth, max_model_len=ml, env=env, reason=st_.get("reason"), log_lines=st_.get("log_lines"), gpu_before=before)
                stop(name); continue
            time.sleep(5)
            model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
            cc = metrics_cache_config()
            if cc.get("kv_tokens") is None and st_.get("kv_tokens_from_log"):
                cc["kv_tokens"] = st_["kv_tokens_from_log"]; cc["kv_tokens_source"] = "log"
            event(kind="depth_start", arm=arm, depth=depth, max_model_len=ml, env=env, image=ARMS[arm]["image"], profile=ARMS[arm]["profile"],
                  gpu_before_launch=before, gpu_ready=gpu(), seconds_to_ready=st_["seconds_to_ready"], cache_config=cc,
                  log_lines=st_["log_lines"], served_model=model, warmup={"min_seconds": warm_s, "min_requests": warm_n, "stable_tolerance": WARM_TOL, "fast_tps_threshold": WARM_FAST_TPS[arm], "max_requests": warm_max_n, "max_seconds": warm_max_s})
            # warm-up: discarded requests at this depth, offsets 1000+ (the measured requests use 0, 13, 26, 39, 52), until the
            # minimum is met and the last three generation rates agree within WARM_TOL, or the cap is hit
            t_w = time.time(); k = 0; rates = []
            while True:
                gb = gpu(); at = now()
                r = request(model, build_prompt(bank, depth, 1000 + 7 * k))
                row(r, arm, depth, ml, k, model, True, at, gb)
                rates.append(r.get("generation_tps")); k += 1
                el = time.time() - t_w
                last3 = [x for x in rates[-3:] if isinstance(x, (int, float))]
                stable = len(last3) == 3 and (max(last3) - min(last3)) / max(last3) <= WARM_TOL and min(last3) >= WARM_FAST_TPS[arm]
                if (el >= warm_s and k >= warm_n and stable) or k >= warm_max_n or el >= warm_max_s:
                    break
                time.sleep(COOLDOWN)
            time.sleep(COOLDOWN)
            event(kind="warmup_end", arm=arm, depth=depth, warmup_requests=k, warmup_seconds=round(time.time() - t_w, 1), stabilized=stable, last_three_rates=last3, rates=rates)
            for i in range(nreq):
                gb = gpu(); at = now()
                row(request(model, build_prompt(bank, depth, i * 13)), arm, depth, ml, i, model, False, at, gb)
                time.sleep(COOLDOWN)
            L = docker_logs(name)
            open(os.path.join(logdir, f"{name}.container.log.txt"), "w", encoding="utf-8", newline="\n", errors="replace").write("\n".join(l for l in L.splitlines() if "nvapi" not in l.lower()) + "\n")
            stop(name)
            event(kind="depth_end", arm=arm, depth=depth, gpu_after_stop=gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
