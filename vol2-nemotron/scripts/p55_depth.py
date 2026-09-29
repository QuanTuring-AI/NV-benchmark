#!/usr/bin/env python3
"""Vol.2 · depth probes after P53: one container per condition, adaptive warm-up at the measured depth, then five
measured requests. The request, the prompt builder and the warm-up rule are p53_longctx_addendum's; what varies per
condition is the container environment and the prompt's character budget.

Conditions (--conditions, comma-separated names from CONDITIONS):
  A1's generation rate steps from 72 to 45 tok/s between 4k and 16k prompt tokens; its engine config dump reads
  "max_seq_len_to_capture": 8192, and decode past that length runs without CUDA graphs. Two tests of that attribution:
  a1_16k_capture   forward: NIM_PASSTHROUGH_ARGS "--max-seq-len-to-capture 32768" at ~14k. NIM 1.12.2 builds its engine
                   arguments itself (--async-engine-args JSON) and reads a fixed set of NIM_* variables; the harness test
                   showed the config dump still at 8192. Kept so the non-delivery is recorded in the published run.
  a1_4k_default / a1_4k_eager / a1_16k_default / a1_16k_eager
                   reverse, one variable: NIM_DISABLE_CUDA_GRAPH=1 (the image maps it to enforce_eager,
                   nim_llm_sdk/entrypoints/args.py:53) at ~3.8k tokens (NIM_MAX_MODEL_LEN 8192), where the default uses
                   graphs, and at ~14k (32768), where neither does. The engine config dump is read back for each.
  a1_120k, a2_120k ~120k prompt tokens at NIM_MAX_MODEL_LEN 131072 (the main run reached 57k: its character budget, not a
                   limit); max_num_seqs 32 on both arms
The character budget is chosen from the measured ratio at 64k (56,730 prompt tokens for a 65,536-token budget: 0.866), so
depth 138,620 targets ~120,000 tokens; the target recorded for the analysis is the token count aimed at.
Warm-up: discarded requests at the measured depth (offsets 1000+) until >= 60 s and >= 6 requests and, on A2, the last three
generation rates agree within 5% and are all at or above A2's fast threshold (220 tok/s; at 120k 180 tok/s, below every steady rate A2 showed at any depth and above its slow-phase rates at 1k-4k), or 25 requests / 600 s. A1 has shown no slow phase in any container, so
its warm-up is the minimum only (its rate varies +/-15% at 120k, and a 5% rule would only run it to the cap). A condition whose container does not start is recorded with the engine's refusal (a context ceiling).
usage: p55_depth.py --out DIR --conditions a,b [--test]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, re, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import ARMS, BASE, docker_logs, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
from p53_longctx import COOLDOWN, QFILE, build_prompt, request  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
A1_SEQS = {"NIM_MAX_NUM_SEQS": "32"}
A2_SEQS = {"NIM_PASSTHROUGH_ARGS": "--max-num-seqs 32"}
CONDITIONS = {
    "a1_4k_default": {"arm": "A1", "env": {"NIM_MAX_MODEL_LEN": "8192", **A1_SEQS}, "target": 4096, "char_depth": 4096, "fast": 0.0, "expect_eager": False},
    "a1_4k_eager": {"arm": "A1", "env": {"NIM_MAX_MODEL_LEN": "8192", **A1_SEQS, "NIM_DISABLE_CUDA_GRAPH": "1"}, "target": 4096, "char_depth": 4096, "fast": 0.0, "expect_eager": True},
    "a1_16k_default": {"arm": "A1", "env": {"NIM_MAX_MODEL_LEN": "32768", **A1_SEQS}, "target": 16384, "char_depth": 16384, "fast": 0.0, "expect_eager": False},
    "a1_16k_eager": {"arm": "A1", "env": {"NIM_MAX_MODEL_LEN": "32768", **A1_SEQS, "NIM_DISABLE_CUDA_GRAPH": "1"}, "target": 16384, "char_depth": 16384, "fast": 0.0, "expect_eager": True},
    "a1_16k_capture": {"arm": "A1", "env": {"NIM_MAX_MODEL_LEN": "32768", **A1_SEQS, "NIM_PASSTHROUGH_ARGS": "--max-seq-len-to-capture 32768"},
                       "target": 16384, "char_depth": 16384, "fast": 0.0, "expect_capture": 32768},
    "a1_120k": {"arm": "A1", "env": {"NIM_MAX_MODEL_LEN": "131072", **A1_SEQS}, "target": 120000, "char_depth": 138620, "fast": 0.0},
    "a2_120k": {"arm": "A2", "env": {"NIM_MAX_MODEL_LEN": "131072", **A2_SEQS}, "target": 120000, "char_depth": 138620, "fast": 180.0},
}
WARM = {"min_s": 60, "min_n": 6, "tol": 0.05, "max_n": 25, "max_s": 600}
N_REQ = 5


def capture_from_log(logdir, name):
    p = os.path.join(logdir, f"{name}.startup.log.txt")
    if not os.path.exists(p):
        return None
    t = open(p, encoding="utf-8", errors="replace").read()
    m = re.findall(r'"?max_seq_len_to_capture"?\s*[:=]\s*(\d+)', t)
    # the engine's config values only: vLLM's hint text "set 'enforce_eager=True'" is quoted and excluded by the look-behind
    e = re.findall(r"(?<!')\benforce_eager\"?\s*[:=]\s*(true|false|True|False)", t)
    unk = re.findall(r"(unrecognized arguments[^\n]{0,200}|error: argument[^\n]{0,200})", t)
    return {"max_seq_len_to_capture": [int(x) for x in m], "enforce_eager": [x.lower() == "true" for x in e], "argument_errors": unk[:3]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--conditions", required=True); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    nreq = 2 if a.test else N_REQ
    wmin_s, wmin_n, wmax_n, wmax_s = (10, 2, 4, 120) if a.test else (WARM["min_s"], WARM["min_n"], WARM["max_n"], WARM["max_s"])
    req_f = open(os.path.join(a.out, "requests.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    bank = json.load(open(QFILE, encoding="utf-8"))

    def event(**kw):
        kw["at"] = now(); ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "condition", "at")}, flush=True)

    def row(r, cond, c, i, model, warmup, at, gb):
        r.update({"condition": cond, "arm": c["arm"], "depth_target": c["target"], "char_depth": c["char_depth"], "max_model_len": int(c["env"]["NIM_MAX_MODEL_LEN"]),
                  "i": i, "warmup": warmup, "at": at, "served_model": model, "gpu_before": gb, "gpu_after": gpu(),
                  "docker_ps_before": sh(["docker", "ps", "--format", "{{.Names}}"], timeout=30).stdout.split()})
        req_f.write(json.dumps(r, ensure_ascii=False) + "\n"); req_f.flush()
        print(f"  {cond} {'warm' if warmup else 'i'}={i} pt={r.get('prompt_tokens')} ttft={r.get('ttft_ms')} gen={r.get('generation_tps')} {r.get('finish_reason')} {r.get('error', '')}", flush=True)

    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")
    for cond in a.conditions.split(","):
        c = CONDITIONS[cond]; arm = c["arm"]
        ARMS[arm] = dict(ARMS[arm], env=dict(c["env"]))
        name = f"p55-depth-{cond.replace('_', '-')}"
        before = gpu()
        st_ = start(arm, name, None, logdir)
        cap = capture_from_log(logdir, name)
        if not st_["ready"]:
            L = docker_logs(name)
            open(os.path.join(logdir, f"{name}.container.log.txt"), "w", encoding="utf-8", newline="\n", errors="replace").write("\n".join(l for l in L.splitlines() if "nvapi" not in l.lower()) + "\n")
            event(kind="condition_failed", condition=cond, arm=arm, env=c["env"], reason=st_.get("reason"), log_lines=st_.get("log_lines"), capture=cap, gpu_before=before,
                  log_tail=[l for l in L.splitlines() if "nvapi" not in l.lower()][-25:])
            stop(name); continue
        time.sleep(5)
        model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
        cc = metrics_cache_config()
        if cc.get("kv_tokens") is None and st_.get("kv_tokens_from_log"):
            cc["kv_tokens"] = st_["kv_tokens_from_log"]; cc["kv_tokens_source"] = "log"
        event(kind="condition_start", condition=cond, arm=arm, env=c["env"], target=c["target"], char_depth=c["char_depth"], image=ARMS[arm]["image"], profile=ARMS[arm]["profile"],
              gpu_before_launch=before, gpu_ready=gpu(), seconds_to_ready=st_["seconds_to_ready"], cache_config=cc, log_lines=st_["log_lines"], served_model=model,
              engine_config_from_log=cap, expect_capture=c.get("expect_capture"), expect_eager=c.get("expect_eager"))
        t_w = time.time(); k = 0; rates = []; stable = False
        while True:
            gb = gpu(); at = now()
            r = request(model, build_prompt(bank, c["char_depth"], 1000 + 7 * k))
            row(r, cond, c, k, model, True, at, gb)
            rates.append(r.get("generation_tps")); k += 1
            el = time.time() - t_w
            last3 = [x for x in rates[-3:] if isinstance(x, (int, float))]
            if c["arm"] == "A1":   # A1 showed no slow phase in any container: minimum warm-up only (its rate varies +/-15% at 120k, so a 5% rule would only run it to the cap)
                stable = True
            else:
                stable = len(last3) == 3 and (max(last3) - min(last3)) / max(last3) <= WARM["tol"] and min(last3) >= c["fast"]
            if (el >= wmin_s and k >= wmin_n and stable) or k >= wmax_n or el >= wmax_s:
                break
            time.sleep(COOLDOWN)
        time.sleep(COOLDOWN)
        event(kind="warmup_end", condition=cond, warmup_requests=k, warmup_seconds=round(time.time() - t_w, 1), stabilized=stable, rates=rates)
        for i in range(nreq):
            gb = gpu(); at = now()
            row(request(model, build_prompt(bank, c["char_depth"], i * 13)), cond, c, i, model, False, at, gb)
            time.sleep(COOLDOWN)
        L = docker_logs(name)
        open(os.path.join(logdir, f"{name}.container.log.txt"), "w", encoding="utf-8", newline="\n", errors="replace").write("\n".join(l for l in L.splitlines() if "nvapi" not in l.lower()) + "\n")
        stop(name)
        event(kind="condition_end", condition=cond, gpu_after_stop=gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
