#!/usr/bin/env python3
"""Vol.2 long-context · analysis. Rules frozen in prediction_p53_longctx.json.

Preconditions per (arm, depth) that reached READY: P1 every request HTTP 200 with usage and no error; P2 the measured
prompt_tokens median is within 25% of the target depth (the filler is sized by characters); P3 exactly one container
up at every request. A depth whose container did not start is reported as that arm's ceiling, not as a failure.
Per (arm, depth): prompt_tokens, TTFT, generation rate (median over the requests), memory at READY and KV tokens from
the start event. Per arm: the TTFT and generation-rate ratios of each depth to the 1k depth (the decay shape) and the
memory added per doubling of NIM_MAX_MODEL_LEN.
usage: p53_longctx_analyze.py <run_dir> | --self-test
"""
import json, os, statistics as st, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEPTH_TOL = 0.25


def med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(st.median(xs), 2) if xs else None


def analyse(rows, events):
    by = {}
    for r in rows:
        by.setdefault((r["arm"], r["depth_target"]), []).append(r)
    starts = {(e["arm"], e["depth"]): e for e in events if e.get("kind") == "depth_start"}
    fails = {(e["arm"], e["depth"]): e for e in events if e.get("kind") == "depth_failed"}
    out = {"per_arm": {}, "all_preconditions_pass": True}
    for arm in sorted({k[0] for k in list(by) + list(fails)}):
        depths = {}
        for (a_, d), v in sorted(by.items()):
            if a_ != arm:
                continue
            bad1 = [r for r in v if r.get("error") or r.get("http_status") != 200 or not r.get("usage_present")]
            pt = med(r.get("prompt_tokens") for r in v)
            bad2 = pt is None or abs(pt - d) / d > DEPTH_TOL
            bad3 = [r for r in v if len(r.get("docker_ps_before") or []) != 1]
            pre = {"P1": {"violations": len(bad1), "pass": not bad1}, "P2_depth_within_25pct": {"prompt_tokens_p50": pt, "target": d, "pass": not bad2},
                   "P3_one_container": {"violations": len(bad3), "pass": not bad3}}
            ok = all(x["pass"] for x in pre.values()); out["all_preconditions_pass"] = out["all_preconditions_pass"] and ok
            ev = starts.get((arm, d)) or {}
            depths[d] = {"preconditions": pre, "preconditions_pass": ok, "n": len(v), "max_model_len": v[0].get("max_model_len"),
                         "prompt_tokens_p50": pt, "ttft_ms_p50": med(r.get("ttft_ms") for r in v) if ok else None,
                         "generation_tps_p50": med(r.get("generation_tps") for r in v) if ok else None,
                         "completion_tokens_p50": med(r.get("completion_tokens") for r in v),
                         "finish_reason": {k: sum(1 for r in v if r.get("finish_reason") == k) for k in sorted({r.get("finish_reason") for r in v})},
                         "gpu_ready_mib": (ev.get("gpu_ready") or {}).get("used_mib"), "gpu_before_launch_mib": (ev.get("gpu_before_launch") or {}).get("used_mib"),
                         "kv_tokens": (ev.get("cache_config") or {}).get("kv_tokens"), "seconds_to_ready": ev.get("seconds_to_ready")}
        for (a_, d), e in fails.items():
            if a_ == arm:
                depths[d] = {"preconditions_pass": None, "container_failed": e.get("reason"), "max_model_len": e.get("max_model_len"), "log_lines": e.get("log_lines")}
        base = depths.get(min(k for k in depths if depths[k].get("preconditions_pass"))) if any(depths[k].get("preconditions_pass") for k in depths) else None
        shape = {}
        if base and base.get("ttft_ms_p50") and base.get("generation_tps_p50"):
            for d, x in sorted(depths.items()):
                if x.get("preconditions_pass"):
                    shape[d] = {"ttft_x_of_shallowest": round(x["ttft_ms_p50"] / base["ttft_ms_p50"], 3),
                                "generation_x_of_shallowest": round(x["generation_tps_p50"] / base["generation_tps_p50"], 3)}
        ceiling = [d for d, x in depths.items() if x.get("container_failed")]
        out["per_arm"][arm] = {"depths": {str(k): v for k, v in sorted(depths.items())}, "decay_shape": {str(k): v for k, v in shape.items()},
                               "context_ceiling": ("container failed at depth %d (NIM_MAX_MODEL_LEN %s)" % (min(ceiling), depths[min(ceiling)]["max_model_len"])) if ceiling else "no failure within the depths tried"}
    return out


def mk(arm, d, pt, ttft, gen, i=0, status=200, docker=None):
    return {"arm": arm, "depth_target": d, "max_model_len": 8192, "i": i, "prompt_tokens": pt, "ttft_ms": ttft, "generation_tps": gen,
            "completion_tokens": 256, "finish_reason": "length", "http_status": status, "usage_present": status == 200, "error": None,
            "docker_ps_before": docker if docker is not None else ["c"]}


def self_test():
    rows = []; ev = []
    for d, ttft, gen in ((1024, 100, 80), (4096, 300, 78), (16384, 1200, 70)):
        rows += [mk("A1", d, int(d * 0.95), ttft * (1 + 0.05 * i), gen, i) for i in range(3)]
        ev.append({"kind": "depth_start", "arm": "A1", "depth": d, "gpu_ready": {"used_mib": 20000 + d // 4}, "gpu_before_launch": {"used_mib": 500}, "cache_config": {"kv_tokens": 100000}, "seconds_to_ready": 200})
    ev.append({"kind": "depth_failed", "arm": "A1", "depth": 65536, "max_model_len": 131072, "reason": "engine refused"})
    a = analyse(rows, ev); p = a["per_arm"]["A1"]
    cases = [("clean run passes", a["all_preconditions_pass"]),
             ("ttft shape 16k = 12x", p["decay_shape"]["16384"]["ttft_x_of_shallowest"] == 12.0),
             ("generation 16k = 0.875x", p["decay_shape"]["16384"]["generation_x_of_shallowest"] == 0.875),
             ("ceiling reported at 65536", p["context_ceiling"].startswith("container failed at depth 65536"))]
    rows2 = [dict(r) for r in rows]; rows2[0]["prompt_tokens"] = 400   # median of (400, 973, 973) still 973 -> pass; make all three short
    rows3 = [dict(r, prompt_tokens=400) for r in rows]
    cases.append(("prompt tokens far from target -> that depth null", analyse(rows3, ev)["per_arm"]["A1"]["depths"]["1024"]["ttft_ms_p50"] is None))
    rows4 = [dict(r) for r in rows]; rows4[0]["http_status"] = 500; rows4[0]["usage_present"] = False
    cases.append(("HTTP 500 -> all_preconditions false", analyse(rows4, ev)["all_preconditions_pass"] is False))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{sum(ok for _, ok in cases)}/{len(cases)} pass")
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    rows = [json.loads(l) for l in open(os.path.join(d, "requests.jsonl"), encoding="utf-8")]
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf-8")]
    a = analyse(rows, events)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    for arm, p in a["per_arm"].items():
        print(arm, {k: (v.get("ttft_ms_p50"), v.get("generation_tps_p50"), v.get("gpu_ready_mib")) for k, v in p["depths"].items()}, p["context_ceiling"])
    return 0 if a["all_preconditions_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
