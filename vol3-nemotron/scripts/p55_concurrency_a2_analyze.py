#!/usr/bin/env python3
"""Vol.2 concurrency, A2 with the sequence cap raised (p55_concurrency_a2.py) · analysis. Rules frozen in each run's
prediction_p55_concurrency_a2_<N>.json.

The rules are p53_concurrency_v2_analyze.py's, word for word, with one change and one addition:
  P3 (changed) the container ran at the intended sequence cap N: env as intended (N = 256: no max-num-seqs override at
     all; N = 64 / 128: NIM_PASSTHROUGH_ARGS "--max-num-seqs N"), AND the engine's own gauge agrees: the maximum of
     vllm:num_requests_running recorded by AIPerf never exceeds N at any level, and it was recorded at >= 1 level.
  pools (added) per level, from the vLLM gauges AIPerf records in server_metrics_export.json: running max / p50, waiting
     max, kv_cache_usage_perc max, preemptions; and a pre-registered reading of what bound admission at that level:
       "sequence cap"      running max >= N and waiting max > 0
       "KV blocks"         running max < N, waiting max > 0 and (kv usage max >= 0.90 or preemptions > 0)
       "all admitted"      waiting max == 0
       "other (scheduler)" waiting max > 0 with free sequence slots and KV usage < 0.90 (e.g. the prefill token budget)
     The Mamba state pool cannot bind at run time: the engine refuses to start unless N states fit (footprint run).
usage: p55_concurrency_a2_analyze.py <run_dir> --seqs N | --self-test
"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SLO = {"server": {"ttft_p99_ms": 2000.0, "itl_p99_ms": 100.0}, "interactive": {"ttft_p99_ms": 500.0, "itl_p99_ms": 30.0}}
CAL_TOL = 0.20
CAL_TTFT_FLOOR_MS = 20.0
IMAGE_DEFAULT_SEQS = 256
KV_BIND = 0.90


def pct(s, key, p):
    v = (s or {}).get(key) or {}
    return v.get(p)


def gauges(run_dir, arm, prof, cont, n):
    """Per-level vLLM gauges from AIPerf's server_metrics_export.json; None if the file is absent."""
    p = os.path.join(run_dir, f"{arm}_{prof}_{cont}", f"c{n:04d}", "server_metrics_export.json")
    if not run_dir or not os.path.exists(p):
        return None
    m = json.load(open(p, encoding="utf-8")).get("metrics") or {}

    def st(name, label=None):
        for s in (m.get(name) or {}).get("series") or []:
            if label is None or all((s.get("labels") or {}).get(k) == v for k, v in label.items()):
                return s.get("stats") or {}
        return {}
    wr = {}
    for s in (m.get("vllm:num_requests_waiting_by_reason") or {}).get("series") or []:
        wr[(s.get("labels") or {}).get("reason")] = (s.get("stats") or {}).get("max")
    return {"running_max": st("vllm:num_requests_running").get("max"), "running_p50": st("vllm:num_requests_running").get("p50"),
            "waiting_max": st("vllm:num_requests_waiting").get("max"), "waiting_max_by_reason": wr,
            "kv_usage_max": st("vllm:kv_cache_usage_perc").get("max"), "kv_usage_p50": st("vllm:kv_cache_usage_perc").get("p50"),
            "preemptions": st("vllm:num_preemptions").get("total")}


def binding(g, seqs):
    if not g or g.get("running_max") is None or g.get("waiting_max") is None:
        return "no gauge"
    if (g["waiting_max"] or 0) <= 0:
        return "all admitted"
    if g["running_max"] >= seqs:
        return "sequence cap"
    if (g.get("kv_usage_max") or 0) >= KV_BIND or (g.get("preemptions") or 0) > 0:
        return "KV blocks"
    return "other (scheduler)"


def env_ok(env, seqs):
    pa = env.get("NIM_PASSTHROUGH_ARGS") or ""
    if seqs == IMAGE_DEFAULT_SEQS:
        return "max-num-seqs" not in pa and "NIM_MAX_NUM_SEQS" not in env
    return f"--max-num-seqs {seqs}" in pa


def analyse(levels, events, seqs, run_dir=None, gauge_fn=None):
    gauge_fn = gauge_fn or (lambda arm, prof, cont, n: gauges(run_dir, arm, prof, cont, n))
    sweeps, skipped = {}, {}
    for r in levels:
        key = (r["arm"], r["profile"], r["container"])
        if "skipped_levels" in r:
            skipped[key] = r; continue
        if r.get("warmup"):
            continue
        sweeps.setdefault(key, []).append(r)
    starts = {(e["arm"], e["profile"], e["container"]): e for e in events if e.get("kind") == "container_start"}
    out = {"seqs": seqs, "sweeps": {}, "all_preconditions_pass": True}
    for key, rows in sorted(sweeps.items()):
        rows = sorted(rows, key=lambda r: r["concurrency"])
        arm, prof, cont = key
        ev = starts.get(key) or {}
        crash = next((r["concurrency"] for r in rows if r.get("engine_dead")), None)
        live = [r for r in rows if crash is None or r["concurrency"] < crash]
        p1_bad = [r["concurrency"] for r in live if r.get("rc") != 0 or not r.get("summary") or ((r["summary"].get("error_request_count") or {}).get("avg") or 0) > 0]
        after = [r["concurrency"] for r in rows if crash is not None and r["concurrency"] > crash]
        p1_ok = not p1_bad and bool(live) and not after
        cal = ev.get("calibration") if cont == "main" else (starts.get((arm, prof, "main")) or {}).get("calibration")
        c1 = next((r for r in live if r["concurrency"] == 1), None) or next((r for r in (sweeps.get((arm, prof, "main")) or []) if r["concurrency"] == 1 and not r.get("engine_dead")), None)
        cal_ok = None; cal_detail = None
        if cal and c1 and c1.get("summary"):
            at, ai = pct(c1["summary"], "time_to_first_token", "p50"), pct(c1["summary"], "inter_token_latency", "p50")
            if at and ai and cal.get("ttft_ms_p50") and cal.get("itl_ms_p50"):
                dt, di = abs(at - cal["ttft_ms_p50"]) / cal["ttft_ms_p50"], abs(ai - cal["itl_ms_p50"]) / cal["itl_ms_p50"]
                cal_ok = (dt <= CAL_TOL or abs(at - cal["ttft_ms_p50"]) <= CAL_TTFT_FLOOR_MS) and di <= CAL_TOL
                cal_detail = {"aiperf_c1_ttft_p50_ms": at, "own_ttft_p50_ms": cal["ttft_ms_p50"], "ttft_rel_diff": round(dt, 3),
                              "aiperf_c1_itl_p50_ms": ai, "own_itl_p50_ms": cal["itl_ms_p50"], "itl_rel_diff": round(di, 3),
                              "own_n": cal.get("n_ok"), "own_prompt_tokens_p50": cal.get("prompt_tokens_p50"), "aiperf_c1_isl_avg": pct(c1["summary"], "input_sequence_length", "avg")}
        env = ev.get("env") or {}
        g_by_n = {r["concurrency"]: gauge_fn(arm, prof, cont, r["concurrency"]) for r in live}
        run_max = [g["running_max"] for g in g_by_n.values() if g and g.get("running_max") is not None]
        p3_env = env_ok(env, seqs)
        p3_gauge = bool(run_max) and max(run_max) <= seqs
        pre = {"P1_levels_clean_below_ceiling": {"bad_levels": p1_bad, "levels_after_crash": after, "live_levels": [r["concurrency"] for r in live], "engine_crash_at": crash, "pass": p1_ok},
               "P2_instrument_calibrated": {"pass": cal_ok is True, "detail": cal_detail},
               "P3_sequence_cap": {"intended": seqs, "env": env, "env_as_intended": p3_env, "levels_with_gauge": len(run_max),
                                   "running_max_over_levels": max(run_max) if run_max else None, "pass": p3_env and p3_gauge}}
        ok = all(v["pass"] for v in pre.values())
        table = []
        for r in rows:
            s = r.get("summary") or {}
            g = g_by_n.get(r["concurrency"])
            table.append({"concurrency": r["concurrency"], "duration_s": r.get("duration_s"), "completed": r.get("completed"), "completed_ge_3N": r.get("completed_ge_3N"),
                          "ttft_ms": {p: pct(s, "time_to_first_token", p) for p in ("p50", "p90", "p99")},
                          "itl_ms": {p: pct(s, "inter_token_latency", p) for p in ("p50", "p90", "p99")},
                          "output_tps": pct(s, "output_token_throughput", "avg"), "tps_per_user": pct(s, "output_token_throughput_per_user", "avg"),
                          "isl_avg": pct(s, "input_sequence_length", "avg"), "osl_avg": pct(s, "output_sequence_length", "avg"),
                          "errors": (s.get("error_request_count") or {}).get("avg"), "engine_dead": bool(r.get("engine_dead")),
                          "first_error": (r.get("first_error") or {}).get("message"), "pools": g, "binding": binding(g, seqs)})
        con = None
        if ok:
            lt = [t for t in table if not t["engine_dead"]]

            def within(t, slo):
                return (t["ttft_ms"]["p99"] is not None and t["itl_ms"]["p99"] is not None
                        and t["ttft_ms"]["p99"] <= slo["ttft_p99_ms"] and t["itl_ms"]["p99"] <= slo["itl_p99_ms"])
            ns = [t["concurrency"] for t in lt if within(t, SLO["server"])]
            ni = [t["concurrency"] for t in lt if within(t, SLO["interactive"])]
            sat = None
            for i in range(1, len(lt)):
                a, b = lt[i - 1]["output_tps"], lt[i]["output_tps"]
                if a and b and b < a * 1.05:
                    sat = lt[i - 1]["concurrency"]; break
            fails_server = [t["concurrency"] for t in lt if not within(t, SLO["server"])]
            fails_inter = [t["concurrency"] for t in lt if not within(t, SLO["interactive"])]
            if crash is not None:
                ceiling = "engine crash at c=%d" % crash + ((" (Server SLO already failed at c=%d)" % min(fails_server)) if fails_server else "")
            elif fails_server:
                ceiling = "reached at c=%d" % min(fails_server)
            else:
                ceiling = "not reached within the range"

            def which(t):
                if t is None:
                    return None
                f = []
                if t["ttft_ms"]["p99"] is not None and t["ttft_ms"]["p99"] > SLO["server"]["ttft_p99_ms"]: f.append("TTFT")
                if t["itl_ms"]["p99"] is not None and t["itl_ms"]["p99"] > SLO["server"]["itl_p99_ms"]: f.append("TPOT")
                return f
            first_fail = next((t for t in lt if t["concurrency"] == min(fails_server)), None) if fails_server else None
            first_fail_i = next((t for t in lt if t["concurrency"] == min(fails_inter)), None) if fails_inter else None
            con = {"max_concurrency_within_server_slo": max(ns) if ns else 0, "max_concurrency_within_interactive_slo": max(ni) if ni else 0,
                   "throughput_saturation_level": sat, "throughput_at_saturation": next((t["output_tps"] for t in lt if t["concurrency"] == sat), None),
                   "throughput_max": max((t["output_tps"] or 0) for t in lt),
                   "ceiling": ceiling, "server_slo_failed_on": which(first_fail),
                   "interactive_slo_failed_on": [x for x, lim in (("TTFT", 500.0), ("TPOT", 30.0)) if first_fail_i and ((first_fail_i["ttft_ms"]["p99"] or 0) > lim if x == "TTFT" else (first_fail_i["itl_ms"]["p99"] or 0) > lim)] if first_fail_i else None,
                   "binding_at_server_ceiling": first_fail["binding"] if first_fail else None,
                   "binding_at_top_level": lt[-1]["binding"],
                   "engine_crash_at": crash, "range": [lt[0]["concurrency"], lt[-1]["concurrency"]], "max_num_seqs": seqs,
                   "skipped_after_crash": (skipped.get(key) or {}).get("skipped_levels"),
                   "slo_source": "MLPerf Inference v5.1 Llama 3.1-8B server (p99 TTFT 2,000 ms, p99 TPOT 100 ms) and interactive (500 ms, 30 ms)"}
        out["sweeps"]["|".join(key)] = {"arm": arm, "profile": prof, "container": cont, "preconditions": pre, "preconditions_pass": ok, "levels": table, "conclusions": con}
        out["all_preconditions_pass"] = out["all_preconditions_pass"] and ok
    return out


def mk(n, ttft99, itl99, tps, errors=0, rc=0, dead=False, cont="main", prof="C"):
    r = {"arm": "A2", "profile": prof, "container": cont, "concurrency": n, "duration_s": 60, "rc": rc, "completed": 5 * n, "completed_ge_3N": True, "engine_dead": dead,
         "summary": {"time_to_first_token": {"avg": ttft99 * 0.5, "p50": ttft99 * 0.5, "p90": ttft99 * 0.8, "p99": ttft99},
                     "inter_token_latency": {"avg": itl99 * 0.8, "p50": itl99 * 0.8, "p90": itl99 * 0.9, "p99": itl99},
                     "output_token_throughput": {"avg": tps}, "output_token_throughput_per_user": {"avg": tps / n},
                     "input_sequence_length": {"avg": 200}, "output_sequence_length": {"avg": 200}, "error_request_count": {"avg": errors}}}
    if rc != 0:
        r["summary"] = None; r["completed"] = None; r["first_error"] = {"code": 500, "message": "Engine loop is not running"}
    return r


def self_test():
    ev = [{"kind": "container_start", "arm": "A2", "profile": "C", "container": "main", "env": {"NIM_MAX_MODEL_LEN": "8192"},
           "calibration": {"ttft_ms_p50": 50.0, "itl_ms_p50": 12.0, "n_ok": 10}}]
    lv = [mk(1, 100, 15, 80), mk(4, 200, 20, 300), mk(16, 400, 28, 900), mk(64, 1500, 40, 1800), mk(256, 1900, 90, 2500), mk(512, 9000, 92, 2550)]

    def G(seqs_cap, kv=0.3, pre=0):
        return lambda arm, prof, cont, n: {"running_max": min(n, seqs_cap), "running_p50": min(n, seqs_cap), "waiting_max": max(0, n - seqs_cap),
                                           "waiting_max_by_reason": {"capacity": max(0, n - seqs_cap)}, "kv_usage_max": kv, "kv_usage_p50": kv, "preemptions": pre}
    a = analyse(lv, ev, 256, gauge_fn=G(256)); s = a["sweeps"]["A2|C|main"]; c = s["conclusions"]
    cases = [("clean sweep at 256 passes", s["preconditions_pass"]),
             ("server SLO max = 256", c["max_concurrency_within_server_slo"] == 256),
             ("interactive SLO max = 16 (c=64 ITL 40 > 30)", c["max_concurrency_within_interactive_slo"] == 16),
             ("interactive failed on TTFT and TPOT (c=64: 1,500 ms, 40 ms)", c["interactive_slo_failed_on"] == ["TTFT", "TPOT"]),
             ("saturation at 256 (512 adds < 5%)", c["throughput_saturation_level"] == 256),
             ("server ceiling at 512 on TTFT", c["ceiling"] == "reached at c=512" and c["server_slo_failed_on"] == ["TTFT"]),
             ("binding at 512 = sequence cap", c["binding_at_top_level"] == "sequence cap"),
             ("binding at 64 = all admitted", s["levels"][3]["binding"] == "all admitted")]
    # P3: env override present when 256 was intended -> null (mutation of env_ok's default branch)
    ev_bad = [dict(ev[0], env={"NIM_MAX_MODEL_LEN": "8192", "NIM_PASSTHROUGH_ARGS": "--max-num-seqs 32"})]
    cases.append(("256 intended but override present -> null", analyse(lv, ev_bad, 256, gauge_fn=G(256))["sweeps"]["A2|C|main"]["conclusions"] is None))
    # P3: gauge exceeds the cap -> null
    cases.append(("running gauge above cap -> null", analyse(lv, ev, 128, gauge_fn=G(256))["sweeps"]["A2|C|main"]["conclusions"] is None))
    # P3: 128 with the right override and gauge -> passes; binding at 256 = sequence cap
    ev128 = [dict(ev[0], env={"NIM_MAX_MODEL_LEN": "8192", "NIM_PASSTHROUGH_ARGS": "--max-num-seqs 128"})]
    a128 = analyse(lv, ev128, 128, gauge_fn=G(128))["sweeps"]["A2|C|main"]
    cases.append(("128 with override passes", a128["preconditions_pass"]))
    # P3: no gauge recorded anywhere -> null
    cases.append(("no gauge at any level -> null", analyse(lv, ev, 256, gauge_fn=lambda *x: None)["sweeps"]["A2|C|main"]["conclusions"] is None))
    # binding: KV blocks when running below cap, waiting, kv >= 0.90
    kvG = lambda arm, prof, cont, n: {"running_max": min(n, 100), "running_p50": 90, "waiting_max": max(0, n - 100), "waiting_max_by_reason": {}, "kv_usage_max": 0.97, "kv_usage_p50": 0.9, "preemptions": 3}
    a_kv = analyse(lv, ev, 256, gauge_fn=kvG)["sweeps"]["A2|C|main"]
    cases.append(("binding = KV blocks when kv >= 0.90 below the cap", a_kv["levels"][4]["binding"] == "KV blocks"))
    kv95 = lambda arm, prof, cont, n: {"running_max": min(n, 100), "running_p50": 90, "waiting_max": max(0, n - 100), "waiting_max_by_reason": {}, "kv_usage_max": 0.95, "kv_usage_p50": 0.9, "preemptions": 0}
    cases.append(("binding = KV blocks on kv 0.95 alone (no preemptions)", analyse(lv, ev, 256, gauge_fn=kv95)["sweeps"]["A2|C|main"]["levels"][4]["binding"] == "KV blocks"))
    otherG = lambda arm, prof, cont, n: {"running_max": min(n, 100), "running_p50": 90, "waiting_max": max(0, n - 100), "waiting_max_by_reason": {}, "kv_usage_max": 0.4, "kv_usage_p50": 0.3, "preemptions": 0}
    cases.append(("binding = other when slots and KV are free", analyse(lv, ev, 256, gauge_fn=otherG)["sweeps"]["A2|C|main"]["levels"][4]["binding"] == "other (scheduler)"))
    # v2 rules carried over: calibration off -> null; errors on live engine -> null; engine death -> ceiling
    ev_cal = [dict(ev[0], calibration={"ttft_ms_p50": 25.0, "itl_ms_p50": 12.0, "n_ok": 10})]
    cases.append(("calibration TTFT 100% / 25 ms off -> null", analyse(lv, ev_cal, 256, gauge_fn=G(256))["sweeps"]["A2|C|main"]["conclusions"] is None))
    lv_err = [dict(r) for r in lv]; lv_err[2] = mk(16, 400, 28, 900, errors=2)
    cases.append(("errors on a live engine -> null", analyse(lv_err, ev, 256, gauge_fn=G(256))["sweeps"]["A2|C|main"]["conclusions"] is None))
    lv_dead = lv[:4] + [mk(256, 0, 0, 0, rc=1, dead=True), {"arm": "A2", "profile": "C", "container": "main", "skipped_levels": [512]}]
    cd = analyse(lv_dead, ev, 256, gauge_fn=G(256))["sweeps"]["A2|C|main"]["conclusions"]
    cases.append(("engine death at 256 -> ceiling, levels below stand", cd["ceiling"] == "engine crash at c=256" and cd["max_concurrency_within_server_slo"] == 64))
    lvw = lv + [dict(mk(1, 5000, 500, 1), warmup=True)]
    cases.append(("warm-up level excluded", analyse(lvw, ev, 256, gauge_fn=G(256))["sweeps"]["A2|C|main"]["conclusions"]["max_concurrency_within_server_slo"] == 256))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{sum(ok for _, ok in cases)}/{len(cases)} pass")
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    seqs = int(sys.argv[sys.argv.index("--seqs") + 1])
    levels = [json.loads(l) for l in open(os.path.join(d, "levels.jsonl"), encoding="utf-8")]
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf-8")]
    a = analyse(levels, events, seqs, run_dir=d)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    for k, s in a["sweeps"].items():
        print(k, "pre", s["preconditions_pass"], json.dumps(s["conclusions"], ensure_ascii=False)[:400] if s["conclusions"] else "conclusions null",
              json.dumps({n: v["pass"] for n, v in s["preconditions"].items()}))
    return 0 if a["all_preconditions_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
