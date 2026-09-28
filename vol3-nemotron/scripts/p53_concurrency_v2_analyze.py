#!/usr/bin/env python3
"""Vol.2 concurrency v2 · analysis. Rules frozen in prediction_p53_concurrency_v2.json.

Input: levels.jsonl (one AIPerf summary per level; warm-up levels carry warmup=true and are excluded; a level after
which the engine was found dead carries engine_dead=true; a skipped_levels record notes what was not run) and
events.jsonl (container starts with the calibration).
Preconditions per (arm, profile, container):
  P1 every level before the first engine-death level has rc 0, a summary and error_request_count 0, and at least one such
     level exists; a level with errors on a live engine fails P1. The engine-death level is not an error of the
     instrument: it is recorded as the sweep's ceiling ("engine crash at c=N") and the levels below it stand.
  P2 the calibration exists and AIPerf's c=1 TTFT and ITL medians are within 20% of this script's own client's medians
     (TTFT alternatively within 20 ms), both measured on the profile's own prompt length after the warm-up level.
     Fresh-container sweeps use the main sweep's calibration.
  P3 max_num_seqs is 32 on both arms (from the container env recorded at start).
Per level: p50/p90/p99 TTFT and ITL (AIPerf: ITL = (e2e - TTFT)/(tokens - 1)), output token throughput, completed
requests, whether completed >= 3N. Conclusions per sweep: the largest concurrency whose p99 TTFT and p99 ITL both
sit inside the Server SLO (2,000 ms / 100 ms) and the Interactive SLO (500 ms / 30 ms) -- MLPerf Inference v5.1
Llama 3.1-8B limits -- the throughput saturation level (first level after which throughput rises by less than 5%), and
the ceiling: "engine crash at c=N", "reached at c=N" (first level failing the Server SLO), or "not reached within the range".
usage: p53_concurrency_v2_analyze.py <run_dir> | --self-test
"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SLO = {"server": {"ttft_p99_ms": 2000.0, "itl_p99_ms": 100.0}, "interactive": {"ttft_p99_ms": 500.0, "itl_p99_ms": 30.0}}
CAL_TOL = 0.20
CAL_TTFT_FLOOR_MS = 20.0   # v1 used 15 ms; the own client's first-chunk median sat 9.5, 12.3 and 15.05 ms above AIPerf's in three C-profile calibrations with ITL agreeing within 2%: a stack difference, not an instrument error (an instrument error of the kind the gate exists for was 115 ms)


def pct(s, key, p):
    v = (s or {}).get(key) or {}
    return v.get(p)


def analyse(levels, events):
    sweeps, skipped = {}, {}
    for r in levels:
        key = (r["arm"], r["profile"], r["container"])
        if "skipped_levels" in r:
            skipped[key] = r; continue
        if r.get("warmup"):
            continue
        sweeps.setdefault(key, []).append(r)
    starts = {(e["arm"], e["profile"], e["container"]): e for e in events if e.get("kind") == "container_start"}
    out = {"sweeps": {}, "all_preconditions_pass": True}
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
        seqs32 = env.get("NIM_MAX_NUM_SEQS") == "32" or "--max-num-seqs 32" in (env.get("NIM_PASSTHROUGH_ARGS") or "")
        pre = {"P1_levels_clean_below_ceiling": {"bad_levels": p1_bad, "levels_after_crash": after, "live_levels": [r["concurrency"] for r in live], "engine_crash_at": crash, "pass": p1_ok},
               "P2_instrument_calibrated": {"pass": cal_ok is True, "detail": cal_detail},
               "P3_max_num_seqs_32": {"env": env, "pass": seqs32}}
        ok = all(v["pass"] for v in pre.values())
        table = []
        for r in rows:
            s = r.get("summary") or {}
            table.append({"concurrency": r["concurrency"], "duration_s": r.get("duration_s"), "completed": r.get("completed"), "completed_ge_3N": r.get("completed_ge_3N"),
                          "ttft_ms": {p: pct(s, "time_to_first_token", p) for p in ("p50", "p90", "p99")},
                          "itl_ms": {p: pct(s, "inter_token_latency", p) for p in ("p50", "p90", "p99")},
                          "output_tps": pct(s, "output_token_throughput", "avg"), "tps_per_user": pct(s, "output_token_throughput_per_user", "avg"),
                          "isl_avg": pct(s, "input_sequence_length", "avg"), "osl_avg": pct(s, "output_sequence_length", "avg"),
                          "errors": (s.get("error_request_count") or {}).get("avg"), "engine_dead": bool(r.get("engine_dead")),
                          "first_error": (r.get("first_error") or {}).get("message")})
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
            if crash is not None:
                ceiling = "engine crash at c=%d" % crash + ((" (Server SLO already failed at c=%d)" % min(fails_server)) if fails_server else "")
            elif fails_server:
                ceiling = "reached at c=%d" % min(fails_server)
            else:
                ceiling = "not reached within the range"
            con = {"max_concurrency_within_server_slo": max(ns) if ns else 0, "max_concurrency_within_interactive_slo": max(ni) if ni else 0,
                   "throughput_saturation_level": sat, "ceiling": ceiling, "engine_crash_at": crash,
                   "range": [lt[0]["concurrency"], lt[-1]["concurrency"]], "max_num_seqs": 32,
                   "skipped_after_crash": (skipped.get(key) or {}).get("skipped_levels"),
                   "slo_source": "MLPerf Inference v5.1 Llama 3.1-8B server (p99 TTFT 2,000 ms, p99 TPOT 100 ms) and interactive (500 ms, 30 ms)"}
        out["sweeps"]["|".join(key)] = {"arm": arm, "profile": prof, "container": cont, "preconditions": pre, "preconditions_pass": ok, "levels": table, "conclusions": con}
        out["all_preconditions_pass"] = out["all_preconditions_pass"] and ok
    return out


def mk(arm, prof, cont, n, ttft99, itl99, tps, errors=0, rc=0, dead=False):
    r = {"arm": arm, "profile": prof, "container": cont, "concurrency": n, "duration_s": 60, "rc": rc, "completed": 5 * n, "completed_ge_3N": True, "engine_dead": dead,
         "summary": {"time_to_first_token": {"avg": ttft99 * 0.5, "p50": ttft99 * 0.5, "p90": ttft99 * 0.8, "p99": ttft99},
                     "inter_token_latency": {"avg": itl99 * 0.8, "p50": itl99 * 0.8, "p90": itl99 * 0.9, "p99": itl99},
                     "output_token_throughput": {"avg": tps}, "output_token_throughput_per_user": {"avg": tps / n},
                     "input_sequence_length": {"avg": 200}, "output_sequence_length": {"avg": 200}, "error_request_count": {"avg": errors}}}
    if rc != 0:
        r["summary"] = None; r["completed"] = None; r["first_error"] = {"code": 500, "message": "Engine loop is not running"}
    return r


def self_test():
    ev = [{"kind": "container_start", "arm": "A1", "profile": "C", "container": "main", "env": {"NIM_MAX_NUM_SEQS": "32"},
           "calibration": {"ttft_ms_p50": 50.0, "itl_ms_p50": 12.0, "n_ok": 10, "prompt_tokens_p50": 205}}]
    lv = [mk("A1", "C", "main", 1, 100, 15, 80), mk("A1", "C", "main", 4, 200, 20, 300), mk("A1", "C", "main", 16, 600, 40, 900),
          mk("A1", "C", "main", 32, 1500, 90, 1500), mk("A1", "C", "main", 64, 3000, 120, 1550)]
    a = analyse(lv, ev); s = a["sweeps"]["A1|C|main"]; c = s["conclusions"]
    cases = [("clean sweep passes", s["preconditions_pass"]),
             ("server SLO max = 32", c["max_concurrency_within_server_slo"] == 32),
             ("interactive SLO max = 4", c["max_concurrency_within_interactive_slo"] == 4),
             ("saturation at 32", c["throughput_saturation_level"] == 32),
             ("ceiling reached at 64", c["ceiling"] == "reached at c=64")]
    lv2 = lv[:-1]; c2 = analyse(lv2, ev)["sweeps"]["A1|C|main"]["conclusions"]
    cases.append(("no failing level -> not reached", c2["ceiling"] == "not reached within the range"))
    # engine death at 32: levels below stand, ceiling names the crash, level 64 skipped
    lv3 = lv[:3] + [mk("A1", "C", "main", 32, 0, 0, 0, rc=1, dead=True), {"arm": "A1", "profile": "C", "container": "main", "skipped_levels": [64], "reason": "engine dead after c=32"}]
    s3 = analyse(lv3, ev)["sweeps"]["A1|C|main"]
    cases.append(("engine death: preconditions pass", s3["preconditions_pass"]))
    cases.append(("engine death: ceiling = crash at 32", s3["conclusions"]["ceiling"] == "engine crash at c=32"))
    cases.append(("engine death: server SLO max from live levels = 16", s3["conclusions"]["max_concurrency_within_server_slo"] == 16))
    cases.append(("engine death: skipped levels recorded", s3["conclusions"]["skipped_after_crash"] == [64]))
    # a level after the crash was run anyway -> P1 fails
    lv4 = lv[:3] + [mk("A1", "C", "main", 32, 0, 0, 0, rc=1, dead=True), mk("A1", "C", "main", 64, 0, 0, 0, rc=1, dead=True)]
    cases.append(("level after crash -> null", analyse(lv4, ev)["sweeps"]["A1|C|main"]["conclusions"] is None))
    # errors on a live engine -> P1 fails
    lv5 = [dict(r) for r in lv]; lv5[2] = mk("A1", "C", "main", 16, 600, 40, 900, errors=2)
    cases.append(("errors on a live engine -> null", analyse(lv5, ev)["sweeps"]["A1|C|main"]["conclusions"] is None))
    ev_bad = [dict(ev[0], calibration={"ttft_ms_p50": 25.0, "itl_ms_p50": 12.0, "n_ok": 10})]   # aiperf 50 vs own 25: 100% and 25 ms off
    cases.append(("calibration TTFT off by 100% / 25 ms -> null", analyse(lv, ev_bad)["sweeps"]["A1|C|main"]["conclusions"] is None))
    ev_itl = [dict(ev[0], calibration={"ttft_ms_p50": 50.0, "itl_ms_p50": 9.0, "n_ok": 10})]
    cases.append(("calibration ITL off by 33% -> null", analyse(lv, ev_itl)["sweeps"]["A1|C|main"]["conclusions"] is None))
    ev_seq = [dict(ev[0], env={"NIM_MAX_NUM_SEQS": "256"})]
    cases.append(("max_num_seqs not 32 -> null", analyse(lv, ev_seq)["sweeps"]["A1|C|main"]["conclusions"] is None))
    lvw = lv + [dict(mk("A1", "C", "main", 1, 5000, 500, 1), warmup=True)]
    cases.append(("warm-up level excluded", analyse(lvw, ev)["sweeps"]["A1|C|main"]["conclusions"]["max_concurrency_within_server_slo"] == 32))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{sum(ok for _, ok in cases)}/{len(cases)} pass")
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    levels = [json.loads(l) for l in open(os.path.join(d, "levels.jsonl"), encoding="utf-8")]
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf-8")]
    a = analyse(levels, events)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    for k, s in a["sweeps"].items():
        print(k, "pre", s["preconditions_pass"], json.dumps(s["conclusions"], ensure_ascii=False)[:300] if s["conclusions"] else "conclusions null",
              json.dumps({n: v["pass"] for n, v in s["preconditions"].items()}))
    return 0 if a["all_preconditions_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
