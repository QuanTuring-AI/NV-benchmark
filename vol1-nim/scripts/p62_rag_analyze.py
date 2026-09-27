#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q3 · analysis. Rules frozen in prediction_p62_rag.json.

P59's analysis program (imported unchanged) on this run's files, profile R, arms N-BF16 and N-FP8, with three additions:
  detector    the container's prefix_detector.pass is now the counter-based detector (positive control fired AND the
              negative form under HIT_SHARE); P59's program already makes a container with a failed detector unusable
  calibration a calibration with any request over HIT_SHARE (or without a counter reading) carries ttft/itl = null, so
              P59's program fails it and every main-container R level of that arm is unusable
  levels      a level whose counter delta shows hit tokens over HIT_SHARE of its queried tokens -> unusable, flag
              "prefix-cache hits"; a level without a counter delta -> unusable, flag "no counter"
Per arm: the table of usable levels (total tok/s, per-user tok/s, p99 TTFT, p99 TPOT, SLO flags), the largest level
inside the server SLO and inside the interactive SLO (among the measured levels, main container; a level outside the
SLO between two inside is reported as it is), and the crossing N-FP8 vs N-BF16 (P59's rule) recomputed after the
level flags. RAG conclusion per arm = that table, or null with the reason (arm gate, detector, calibration, all levels).
Server-side reading (reported, not a gate): the server's own TTFT and prefill time for the harness's calibration
requests and for AIPerf's c=1 level, beside the two clients' TTFT. Secondary table (never the conclusion): for an arm
whose primary calibration failed, if AIPerf's c=1 mean TTFT is within max(20 ms, 20%) of the server's own mean TTFT for
the same requests, its R levels without prefix-cache hits are listed under `rag.<arm>.secondary_not_the_conclusion`.
Anchors: each main-container level's total tok/s beside P59's value for the same cell (P59's N-FP8 R cells were
unusable there for calibration; their raw values are still listed) -- reported, not used by any rule.
usage: p62_rag_analyze.py <run_dir> [<p59_analysis.json>] | --self-test
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p59_analyze as A  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HIT_SHARE = 0.02
ARMS = ["N-BF16", "N-FP8"]


def analyse(levels, events, pcl):
    out = A.analyse(levels, events)
    hits = {(r["arm"], r["container"], r["concurrency"]): r.get("prefix_cache") for r in pcl if not r.get("warmup")}
    for key, tab in out["levels"].items():
        arm, prof, cont = key.split("|")
        for n, cell in tab.items():
            d = hits.get((arm, cont, n))
            cell["prefix_cache"] = d
            if d is None:
                cell["usable"] = False; cell["flags"].append("no counter")
            elif (d.get("hit_share") or 0) > HIT_SHARE:
                cell["usable"] = False; cell["flags"].append("prefix-cache hits")
    res = {}
    for arm in ARMS:
        v = out["arms"].get(arm) or {}
        tab = out["levels"].get(f"{arm}|R|main") or {}
        reason = None
        if not v:
            reason = "arm not run"
        elif not v.get("usable"):
            reason = "arm gate failed (residency or health)"
        elif not (v.get("isolation_and_detector", {}).get("main") or {}).get("detector"):
            reason = "prefix-cache detector failed or did not fire"
        elif not v["calibration"]["R"]["pass"]:
            reason = "calibration failed" + (" (detail: %s)" % json.dumps(v["calibration"]["R"]["detail"]) if v["calibration"]["R"]["detail"] else " (rejected for prefix-cache hits or no counter)")
        elif not any(c["usable"] for c in tab.values()):
            reason = "no usable level"
        if reason:
            res[arm] = {"conclusion": None, "reason": reason}
            continue
        use = {n: c for n, c in sorted(tab.items()) if c["usable"]}
        res[arm] = {"conclusion": {"levels": {n: {k: c[k] for k in ("total_tps", "per_user_tps", "ttft_p99_ms", "tpot_p99_ms", "in_server_slo", "in_interactive_slo", "flags")} for n, c in use.items()},
                                   "largest_level_in_server_slo": max([n for n, c in use.items() if c["in_server_slo"]], default=None),
                                   "largest_level_in_interactive_slo": max([n for n, c in use.items() if c["in_interactive_slo"]], default=None)}, "reason": None}
    cr = {}
    for metric in ("total_tps", "per_user_tps"):
        if not all(res.get(a, {}).get("conclusion") for a in ARMS):
            cr[metric] = None; continue
        tb, ta = out["levels"]["N-FP8|R|main"], out["levels"]["N-BF16|R|main"]
        pts = [(n, tb[n][metric], ta[n][metric]) for n in sorted(set(tb) & set(ta)) if tb[n]["usable"] and ta[n]["usable"] and tb[n][metric] and ta[n][metric]
               and "early stop" not in tb[n]["flags"] + ta[n]["flags"]]
        cr[metric] = A.crossing(pts, "N-FP8", "N-BF16")
    side = {}
    for arm in ARMS:
        ps = next((e for e in events if e.get("kind") == "profile_start" and e.get("arm") == arm and e.get("profile") == "R" and e.get("container") == "main"), {})
        cal = ps.get("calibration") or {}
        lv1 = next((r for r in levels if r.get("arm") == arm and r.get("profile") == "R" and r.get("container") == "main" and r.get("concurrency") == 1 and not r.get("warmup") and r.get("summary")), None)
        srv1 = ((hits.get((arm, "main", 1)) or {}).get("aiperf_server_metrics") or {}).get("time_to_first_token_seconds") or {}
        side[arm] = {"own_client_ttft_p50_ms": cal.get("ttft_ms_p50_measured"), "server_ttft_for_own_requests_p50_ms": cal.get("server_ttft_ms_p50"),
                     "server_prefill_for_own_requests_p50_ms": cal.get("server_prefill_ms_p50"), "own_client_prompt_tokens_p50": cal.get("client_prompt_tokens_p50"),
                     "aiperf_c1_ttft_p50_ms": A.pct((lv1 or {}).get("summary"), "time_to_first_token", "p50"), "aiperf_c1_ttft_avg_ms": A.pct((lv1 or {}).get("summary"), "time_to_first_token", "avg"),
                     "server_ttft_for_aiperf_c1_avg_ms": round(1000 * srv1["avg"], 2) if srv1.get("avg") else None,
                     "server_ttft_for_aiperf_c1_p50_estimate_ms": round(1000 * srv1["p50_estimate"], 2) if srv1.get("p50_estimate") else None}
    for arm in ARMS:   # secondary table: only where the primary calibration failed and the tool agrees with the server
        sd, r = side[arm], res.get(arm) or {}
        a_, s_ = sd.get("aiperf_c1_ttft_avg_ms"), sd.get("server_ttft_for_aiperf_c1_avg_ms")
        agree = bool(a_ and s_ and (abs(a_ - s_) <= 20.0 or abs(a_ - s_) / s_ <= 0.20))
        sd["aiperf_agrees_with_server_c1"] = agree if (a_ and s_) else None
        v = out["arms"].get(arm) or {}
        if r.get("conclusion") is None and (r.get("reason") or "").startswith("calibration failed") and agree and v.get("usable"):
            tab = out["levels"].get(f"{arm}|R|main") or {}
            clean = {r["concurrency"] for r in levels if r.get("arm") == arm and r.get("profile") == "R" and r.get("container") == "main" and not r.get("warmup")
                     and r.get("rc") == 0 and r.get("summary") and not ((r["summary"].get("error_request_count") or {}).get("avg")) and not r.get("engine_dead")}
            use = {n: c for n, c in sorted(tab.items()) if n in clean and set(c["flags"]) <= {"truncation unverified", "calibration failed"}
                   and c.get("prefix_cache") and (c["prefix_cache"].get("hit_share") or 0) <= HIT_SHARE and c.get("total_tps")}
            r["secondary_not_the_conclusion"] = {"rule": "primary calibration failed; AIPerf c=1 mean TTFT within max(20 ms, 20%) of the server's own mean TTFT for the same requests",
                                                 "levels": {n: {k: c[k] for k in ("total_tps", "per_user_tps", "ttft_p99_ms", "tpot_p99_ms", "in_server_slo", "in_interactive_slo")} for n, c in use.items()},
                                                 "largest_level_in_server_slo": max([n for n, c in use.items() if c["in_server_slo"]], default=None),
                                                 "largest_level_in_interactive_slo": max([n for n, c in use.items() if c["in_interactive_slo"]], default=None)}
    out["server_side_reading"] = {"note": "reported, not a gate: the server's own TTFT for the harness's calibration requests and for AIPerf's c=1 level (AIPerf's server-metrics export); where the gap sits", "arms": side}
    out["rag"] = res; out["crossing_fp8_vs_bf16_R"] = cr
    out["crossings"] = {k: v for k, v in out["crossings"].items() if "|R|" in k and k.startswith("N-FP8 vs N-BF16")}
    return out


def self_test():
    def lv(arm, n, tot, cont="main", ttft=300.0, itl=12.0):
        return {"arm": arm, "profile": "R", "container": cont, "concurrency": n, "rc": 0, "engine_dead": False,
                "summary": {"output_token_throughput": {"avg": tot}, "output_token_throughput_per_user": {"avg": tot / n},
                            "time_to_first_token": {"p50": 250.0, "p99": ttft}, "inter_token_latency": {"p50": itl, "p99": itl}, "error_request_count": {"avg": 0}},
                "checks": {"truncated_requests": 0, "server_over_client_prompt_min": None, "requests_without_server_prompt_count": 3,
                           "completion_tokens_p50": 500, "completion_below_90pct_of_target": False}}
    det = {"pass": True, "positive_control_same_prompt_twice": {"fired": True}}
    ev = [{"kind": "container_start", "arm": a, "container": "main", "captured_graph_sizes": {"x": 1}, "isolation": {"pass": True}, "prefix_detector": det} for a in ARMS]
    ev += [{"kind": "profile_start", "arm": a, "profile": "R", "container": "main", "calibration": {"ttft_ms_p50": 250.0, "itl_ms_p50": 12.0}} for a in ARMS]
    L = [lv(a, n, t * (1.6 if a == "N-FP8" else 1.0), ttft=300.0 if n == 1 else 2500.0, itl=12.0 if n == 1 else 20.0) for a in ARMS for n, t in ((1, 80), (8, 390), (16, 530))]
    # C rows so that P59's health gate (profile C, c=1) can be computed
    L += [dict(lv(a, 1, 100.0, itl=9.0 if a == "N-BF16" else 5.5), profile="C") for a in ARMS]
    ev += [{"kind": "profile_start", "arm": a, "profile": "C", "container": "main", "calibration": {"ttft_ms_p50": 250.0, "itl_ms_p50": 9.0 if a == "N-BF16" else 5.5}} for a in ARMS]
    P = [{"arm": a, "container": "main", "concurrency": n, "prefix_cache": {"queried_tokens": 1e5, "hit_tokens": 800.0, "hit_share": 0.008}} for a in ARMS for n in (1, 8, 16)]
    x = analyse(L, ev, P)
    cases = [("both conclusions present, largest server-SLO level 1", all(x["rag"][a]["conclusion"] and x["rag"][a]["conclusion"]["largest_level_in_server_slo"] == 1 for a in ARMS)),
             ("fp8 ahead throughout", x["crossing_fp8_vs_bf16_R"]["total_tps"]["crossings"] == ["N-FP8 ahead throughout 1-16"])]
    P2 = [dict(p, prefix_cache={"queried_tokens": 1e5, "hit_tokens": 9000.0, "hit_share": 0.09}) if p["arm"] == "N-BF16" and p["concurrency"] == 8 else p for p in P]
    y = analyse(L, ev, P2)
    cases.append(("level with hits unusable and flagged", y["levels"]["N-BF16|R|main"][8]["usable"] is False and "prefix-cache hits" in y["levels"]["N-BF16|R|main"][8]["flags"]))
    ev2 = [dict(e, calibration={"ttft_ms_p50": None, "itl_ms_p50": None}) if e.get("arm") == "N-FP8" and e.get("profile") == "R" else e for e in ev]
    z = analyse(L, ev2, P)
    cases.append(("calibration rejected -> N-FP8 null with reason, crossing null", z["rag"]["N-FP8"]["conclusion"] is None and "calibration" in z["rag"]["N-FP8"]["reason"] and z["crossing_fp8_vs_bf16_R"]["total_tps"] is None))
    ev3 = [dict(e, prefix_detector={"pass": False, "positive_control_same_prompt_twice": {"fired": False}}) if e.get("arm") == "N-BF16" and e["kind"] == "container_start" else e for e in ev]
    cases.append(("detector not fired -> null", analyse(L, ev3, P)["rag"]["N-BF16"]["reason"].startswith("prefix-cache detector")))
    P3 = [p for p in P if not (p["arm"] == "N-FP8" and p["concurrency"] == 16)]
    cases.append(("missing counter -> level unusable", analyse(L, ev, P3)["levels"]["N-FP8|R|main"][16]["usable"] is False))
    L5 = [dict(r, summary=dict(r["summary"], time_to_first_token={"p50": 250.0, "p99": r["summary"]["time_to_first_token"]["p99"], "avg": 251.0})) if r["arm"] == "N-FP8" and r["profile"] == "R" and r["concurrency"] == 1 else r for r in L]
    ev5 = [dict(e, calibration={"ttft_ms_p50": 150.0, "itl_ms_p50": 12.0}) if e.get("arm") == "N-FP8" and e.get("profile") == "R" else e for e in ev]
    P5 = [dict(p, prefix_cache=dict(p["prefix_cache"], aiperf_server_metrics={"time_to_first_token_seconds": {"avg": 0.248, "p50_estimate": 0.25}})) if p["arm"] == "N-FP8" and p["concurrency"] == 1 else p for p in P]
    w = analyse(L5, ev5, P5)
    cases.append(("primary calibration fails, tool agrees with server -> conclusion null, secondary table present", w["rag"]["N-FP8"]["conclusion"] is None
                  and sorted(w["rag"]["N-FP8"].get("secondary_not_the_conclusion", {}).get("levels", {})) == [1, 8, 16] and w["server_side_reading"]["arms"]["N-FP8"]["aiperf_agrees_with_server_c1"] is True))
    P6 = [dict(p, prefix_cache=dict(p["prefix_cache"], aiperf_server_metrics={"time_to_first_token_seconds": {"avg": 0.150, "p50_estimate": 0.15}})) if p["arm"] == "N-FP8" and p["concurrency"] == 1 else p for p in P]
    cases.append(("tool disagrees with server -> no secondary table", "secondary_not_the_conclusion" not in analyse(L5, ev5, P6)["rag"]["N-FP8"]))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    rd = lambda f: [json.loads(l) for l in open(os.path.join(d, f), encoding="utf-8")] if os.path.exists(os.path.join(d, f)) else []
    a = analyse(rd("levels.jsonl"), rd("events.jsonl"), rd("prefix_cache_levels.jsonl"))
    if len(sys.argv) > 2:
        p59 = json.load(open(sys.argv[2], encoding="utf-8"))["levels"]
        a["anchors_vs_p59"] = {f"{arm}|c{n}": {"this_run": c.get("total_tps"), "p59": (p59.get(f"{arm}|R|main") or {}).get(str(n), {}).get("total_tps"),
                                               "ratio": round(c["total_tps"] / p59[f"{arm}|R|main"][str(n)]["total_tps"], 3) if c.get("total_tps") and (p59.get(f"{arm}|R|main") or {}).get(str(n), {}).get("total_tps") else None}
                               for arm in ARMS for n, c in (a["levels"].get(f"{arm}|R|main") or {}).items()}
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    for arm in ARMS:
        print(arm, json.dumps(a["rag"][arm])[:600])
    print("crossing", a["crossing_fp8_vs_bf16_R"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
