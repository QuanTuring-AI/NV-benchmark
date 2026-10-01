#!/usr/bin/env python3
"""Vol.2 long context · addendum analysis. Rules frozen in prediction_p53_longctx_addendum.json.
The measured rows (warmup=false) go through the main run's analysis unchanged (p53_longctx_analyze.analyse: P1-P3 per
depth, medians, decay shape against the shallowest depth). The warm-up rows are summarised separately per (arm, depth):
their count, duration, and the generation rate of the first, the median and the last warm-up request, so the transient
that the addendum exists for is visible. Also the ratio of the measured median generation rate to the main run's.
usage: p53_longctx_addendum_analyze.py <run_dir> [--main-run DIR] | --self-test
"""
import json, os, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p53_longctx_analyze import analyse as analyse_main, self_test as self_test_main  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def analyse(rows, events, main_analysis=None):
    measured = [r for r in rows if not r.get("warmup")]
    warm = [r for r in rows if r.get("warmup")]
    a = analyse_main(measured, events)
    a["warmup"] = {}
    for key in sorted({(r["arm"], r["depth_target"]) for r in warm}):
        ws = sorted((r for r in warm if (r["arm"], r["depth_target"]) == key), key=lambda r: r["i"])
        g = [r.get("generation_tps") for r in ws if isinstance(r.get("generation_tps"), (int, float))]
        t = [r.get("ttft_ms") for r in ws if isinstance(r.get("ttft_ms"), (int, float))]
        a["warmup"]["%s|%d" % key] = {"n": len(ws), "generation_tps_first": g[0] if g else None, "generation_tps_median": round(st.median(g), 2) if g else None,
                                     "generation_tps_last": g[-1] if g else None, "ttft_ms_first": t[0] if t else None, "ttft_ms_last": t[-1] if t else None,
                                     "generation_tps_sequence": g}
    if main_analysis:
        a["vs_main_run"] = {}
        for arm, p in a["per_arm"].items():
            for d, x in p["depths"].items():
                m = ((main_analysis.get("per_arm") or {}).get(arm) or {}).get("depths", {}).get(d)
                if m and x.get("generation_tps_p50") and m.get("generation_tps_p50"):
                    a["vs_main_run"]["%s|%s" % (arm, d)] = {"generation_tps_p50_addendum": x["generation_tps_p50"], "generation_tps_p50_main": m["generation_tps_p50"],
                                                             "ratio": round(x["generation_tps_p50"] / m["generation_tps_p50"], 3),
                                                             "ttft_ms_p50_addendum": x.get("ttft_ms_p50"), "ttft_ms_p50_main": m.get("ttft_ms_p50")}
    return a


def self_test():
    rc = self_test_main()
    rows = [{"arm": "A2", "depth_target": 1024, "i": i, "warmup": True, "generation_tps": 100 + 40 * i, "ttft_ms": 300 - 50 * i} for i in range(4)]
    rows += [{"arm": "A2", "depth_target": 1024, "i": i, "warmup": False, "generation_tps": 300, "ttft_ms": 90, "http_status": 200, "usage_present": True,
              "prompt_tokens": 1100, "completion_tokens": 256, "finish_reason": "length", "docker_ps_before": ["c"]} for i in range(5)]
    ev = [{"kind": "depth_start", "arm": "A2", "depth": 1024, "max_model_len": 4096, "gpu_ready": {"used_mib": 1}, "gpu_before_launch": {"used_mib": 1}, "cache_config": {"kv_tokens": 1}, "seconds_to_ready": 1}]
    a = analyse(rows, ev, {"per_arm": {"A2": {"depths": {"1024": {"generation_tps_p50": 128.3, "ttft_ms_p50": 275.5}}}}})
    cases = [("warm-up rows excluded from the measured median", a["per_arm"]["A2"]["depths"]["1024"]["generation_tps_p50"] == 300),
             ("warm-up sequence recorded", a["warmup"]["A2|1024"]["generation_tps_sequence"] == [100, 140, 180, 220]),
             ("ratio to main run", abs(a["vs_main_run"]["A2|1024"]["ratio"] - 300 / 128.3) < 1e-3)]
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{sum(ok for _, ok in cases)}/{len(cases)} addendum cases pass (plus the main analyser's above)")
    return 0 if rc == 0 and all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    main_dir = sys.argv[sys.argv.index("--main-run") + 1] if "--main-run" in sys.argv else os.path.join(d, "..", "p53_longctx")
    rows = [json.loads(l) for l in open(os.path.join(d, "requests.jsonl"), encoding="utf-8")]
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf-8")]
    mp = os.path.join(main_dir, "analysis.json")
    ma = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else None
    a = analyse(rows, events, ma)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    for arm, p in a["per_arm"].items():
        print(arm, {k: (v.get("ttft_ms_p50"), v.get("generation_tps_p50")) for k, v in p["depths"].items()}, p["context_ceiling"])
    print("warmup", json.dumps(a["warmup"], ensure_ascii=False)[:600])
    return 0 if a["all_preconditions_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
