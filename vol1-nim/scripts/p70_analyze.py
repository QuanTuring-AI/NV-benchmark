#!/usr/bin/env python3
"""Vol.1 (renewed), P70 · analysis. Rules frozen in prediction_p70.json.

P59's analysis program (p59_analyze.py in this directory, imported unchanged) runs on this run's levels.jsonl and
events.jsonl: residency and health gates per arm (decode rate at c=1 x bytes per token / 1,792 GB/s >= 0.40), container
checks (isolation, prefix-cache detector), calibration, per-cell usability. A cell here is usable only if, in addition:
  its G8 check passed before it (events `g8`), and the no-overwrite check after it passed (events `overwrite_check`).
Ratios at 128 on total output tok/s: N-BF16 / O-Q4 (the headline), N-FP8 / O-Q4, N-BF16 / O-FP16; each beside P59's value
for the same pair (P59's analysis.json, read from the results directory next to this run's) and this / P59.
At 1: N-BF16 / O-Q4 (P59 0.505). Per cell: total tok/s beside P59's same cell (this / P59), reported, not interpreted.
Predictions:
  R1  N-BF16 / O-Q4 at 128 within 6.7-8.1
  R2  N-FP8 / O-Q4 and N-BF16 / O-FP16 at 128 each within P59's value x (0.9, 1.1)
  R3  at 1, O-Q4's total tok/s above N-BF16's
usage: p70_analyze.py <run_dir> | --self-test
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p59_analyze as A  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P59_ANALYSIS = os.path.join(HERE, "..", "results", "p59_nim_value", "analysis.json")
PAIRS_128 = [("N-BF16", "O-Q4"), ("N-FP8", "O-Q4"), ("N-BF16", "O-FP16")]
R1_BAND, R2_TOL = (6.7, 8.1), 0.10
LEVELS = [1, 32, 128]


def analyse(levels, events, p59):
    base = A.analyse(levels, events)
    g8 = {(e["arm"], e["concurrency"]): e.get("pass") for e in events if e.get("kind") == "g8"}
    ov = {(e["arm"], e["concurrency"]): e.get("pass") for e in events if e.get("kind") == "overwrite_check"}
    nulls = {(e["arm"], e["concurrency"]): e.get("reason") for e in events if e.get("kind") == "cell_null"}
    pc = next((e for e in events if e.get("kind") == "g8_positive_control"), None)
    p59l = p59.get("levels") or {}
    cells = {}
    for arm in ("N-BF16", "O-Q4", "N-FP8", "O-FP16"):
        ag = (base["arms"].get(arm) or {})
        t = (base["levels"].get(f"{arm}|C|main") or {})
        for n in LEVELS:
            c = t.get(n) or t.get(str(n)) or {}
            reasons = []
            if (arm, n) in nulls:
                reasons.append(nulls[(arm, n)])
            if not c:
                reasons.append("not run") if (arm, n) not in nulls else None
            if c and not c.get("usable"):
                reasons.append("P59 cell checks failed: " + ", ".join(c.get("flags") or []) or "P59 cell checks failed")
            if not ag.get("usable"):
                reasons.append("arm gate failed (residency or health)")
            if c and g8.get((arm, n)) is not True:
                reasons.append("G8 did not pass")
            if c and ov.get((arm, n)) is not True:
                reasons.append("no-overwrite check did not pass")
            p = (p59l.get(f"{arm}|C|main") or {}).get(str(n)) or {}
            tps = c.get("total_tps") if c else None
            cells[f"{arm}|{n}"] = {"usable": not reasons, "reasons": reasons, "total_tps": tps, "per_user_tps": c.get("per_user_tps") if c else None,
                                   "ttft_p99_ms": c.get("ttft_p99_ms") if c else None, "tpot_p99_ms": c.get("tpot_p99_ms") if c else None,
                                   "in_server_slo": c.get("in_server_slo") if c else None, "p59_total_tps": p.get("total_tps"),
                                   "this_over_p59": round(tps / p["total_tps"], 3) if tps and p.get("total_tps") else None}
    def ratio(b, a, n):
        cb, ca = cells[f"{b}|{n}"], cells[f"{a}|{n}"]
        return round(cb["total_tps"] / ca["total_tps"], 3) if cb["usable"] and ca["usable"] and cb["total_tps"] and ca["total_tps"] else None
    def p59ratio(b, a, n):
        pb, pa = (p59l.get(f"{b}|C|main") or {}).get(str(n)) or {}, (p59l.get(f"{a}|C|main") or {}).get(str(n)) or {}
        return round(pb["total_tps"] / pa["total_tps"], 3) if pb.get("total_tps") and pa.get("total_tps") else None
    r128 = {}
    for b, a in PAIRS_128:
        v, pv = ratio(b, a, 128), p59ratio(b, a, 128)
        r128[f"{b}/{a}"] = {"this_run": v, "p59": pv, "this_over_p59": round(v / pv, 3) if v and pv else None}
    r1 = {"this_run": ratio("N-BF16", "O-Q4", 1), "p59": p59ratio("N-BF16", "O-Q4", 1)}
    h = r128["N-BF16/O-Q4"]["this_run"]
    pred = {"R1": {"pass": h is not None and R1_BAND[0] <= h <= R1_BAND[1], "value": h, "band": R1_BAND},
            "R2": {"pass": all(r128[k]["this_run"] is not None and r128[k]["p59"] and abs(r128[k]["this_run"] / r128[k]["p59"] - 1) <= R2_TOL for k in ("N-FP8/O-Q4", "N-BF16/O-FP16")),
                   "values": {k: r128[k] for k in ("N-FP8/O-Q4", "N-BF16/O-FP16")}, "tolerance": R2_TOL},
            "R3": {"pass": r1["this_run"] is not None and r1["this_run"] < 1.0, "N-BF16/O-Q4_at_1": r1["this_run"]}}
    return {"arms": base["arms"], "cells": cells, "ratios_128": r128, "ratio_at_1": r1, "predictions": pred,
            "g8_positive_control": pc and {"fired": pc.get("control_fired"), "util_pct_p50": (pc.get("sample") or {}).get("util_pct_p50"), "power_w_p50": (pc.get("sample") or {}).get("power_w_p50")},
            "g8_by_cell": {f"{a}|{n}": v for (a, n), v in g8.items()}, "overwrite_by_cell": {f"{a}|{n}": v for (a, n), v in ov.items()}}


def self_test():
    T = {"N-BF16": {1: 87, 32: 2262, 128: 5458}, "O-Q4": {1: 172, 32: 755, 128: 741}, "N-FP8": {1: 151, 32: 3817, 128: 8713}, "O-FP16": {1: 79, 32: 390, 128: 402}}
    B = {"N-BF16": 16060522496, "O-Q4": 4920738944, "N-FP8": 9081280648, "O-FP16": 16068895872}
    ITL = {arm: 1000.0 * B[arm] / 1792e9 / 0.6 for arm in T}     # health 0.6
    def lv(arm, n, tps):
        return {"arm": arm, "profile": "C", "container": "main", "concurrency": n, "rc": 0, "completed": 100,
                "summary": {"output_token_throughput": {"avg": tps}, "inter_token_latency": {"p50": ITL[arm], "p99": 50}, "time_to_first_token": {"p50": 30, "p99": 500},
                            "error_request_count": {"avg": 0}}, "checks": {"truncated_requests": 0, "completion_below_90pct_of_target": False}}
    def ev(g8fail=(), ovfail=()):
        e = []
        for arm in T:
            st = {"kind": "container_start", "arm": arm, "container": "main", "isolation": {"pass": True}, "prefix_detector": {"pass": True}}
            st.update({"load": {"full_gpu": True}} if arm.startswith("O-") else {"captured_graph_sizes": {"x": 1}})
            e.append(st)
            e.append({"kind": "profile_start", "arm": arm, "profile": "C", "container": "main", "calibration": {"ttft_ms_p50": 30, "itl_ms_p50": ITL[arm]}})
            for n in LEVELS:
                e.append({"kind": "g8", "arm": arm, "concurrency": n, "pass": (arm, n) not in g8fail})
                e.append({"kind": "overwrite_check", "arm": arm, "concurrency": n, "pass": (arm, n) not in ovfail})
        return e
    p59 = {"levels": {f"{a}|C|main": {str(n): {"total_tps": v} for n, v in d.items()} for a, d in T.items()}}
    L = [lv(a, n, v) for a, d in T.items() for n, v in d.items()]
    x = analyse(L, ev(), p59)
    cases = [("baseline: headline 5458/741 = 7.366, R1-R3 pass", x["ratios_128"]["N-BF16/O-Q4"]["this_run"] == round(5458 / 741, 3) and all(v["pass"] for v in x["predictions"].values())),
             ("this / P59 = 1.0 on every cell", all(c["this_over_p59"] == 1.0 for c in x["cells"].values()))]
    L2 = [lv("O-Q4", 128, 900) if (r["arm"], r["concurrency"]) == ("O-Q4", 128) else r for r in L]
    y = analyse(L2, ev(), p59)
    cases.append(("O-Q4 at 128 900 -> 6.064, R1 fails; R2 N-FP8/O-Q4 fails", not y["predictions"]["R1"]["pass"] and y["ratios_128"]["N-BF16/O-Q4"]["this_run"] == round(5458 / 900, 3) and not y["predictions"]["R2"]["pass"]))
    z = analyse(L, ev(g8fail={("N-BF16", 128)}), p59)
    cases.append(("G8 failed before N-BF16 128 -> cell null, headline null, R1 fails", z["cells"]["N-BF16|128"]["usable"] is False and z["ratios_128"]["N-BF16/O-Q4"]["this_run"] is None and not z["predictions"]["R1"]["pass"]))
    w = analyse(L, ev(ovfail={("O-FP16", 128)}), p59)
    cases.append(("overwrite check failed -> that cell null", w["cells"]["O-FP16|128"]["usable"] is False and w["cells"]["O-FP16|32"]["usable"]))
    L3 = [lv("O-Q4", 1, 80) if (r["arm"], r["concurrency"]) == ("O-Q4", 1) else r for r in L]
    cases.append(("O-Q4 slower than N-BF16 at 1 -> R3 fails", not analyse(L3, ev(), p59)["predictions"]["R3"]["pass"]))
    L4 = [dict(r, summary=dict(r["summary"], inter_token_latency={"p50": ITL["O-FP16"] * 2, "p99": 50})) if (r["arm"], r["concurrency"]) == ("O-FP16", 1) else r for r in L]
    v = analyse(L4, ev(), p59)
    cases.append(("O-FP16 health 0.30 < 0.40 -> its cells null, N-BF16/O-FP16 null, R2 fails", v["cells"]["O-FP16|128"]["usable"] is False and v["ratios_128"]["N-BF16/O-FP16"]["this_run"] is None and not v["predictions"]["R2"]["pass"]))
    slow = {"O-FP16": ITL["O-FP16"] * 2}
    L6 = [dict(r, summary=dict(r["summary"], inter_token_latency={"p50": slow["O-FP16"], "p99": 50})) if r["arm"] == "O-FP16" else r for r in L]
    e6 = [dict(e, calibration={"ttft_ms_p50": 30, "itl_ms_p50": slow["O-FP16"]}) if e.get("kind") == "profile_start" and e["arm"] == "O-FP16" else e for e in ev()]
    u = analyse(L6, e6, p59)
    cases.append(("health 0.30 with calibration consistent -> only the arm gate nulls O-FP16", u["cells"]["O-FP16|32"]["usable"] is False
                  and u["cells"]["O-FP16|32"]["reasons"] == ["arm gate failed (residency or health)"]))
    L7 = [dict(r, checks={"truncated_requests": 3, "completion_below_90pct_of_target": False}) if (r["arm"], r["concurrency"]) == ("N-FP8", 32) else r for r in L]
    t = analyse(L7, ev(), p59)
    cases.append(("truncated prompts in N-FP8 32 -> P59's cell check nulls that cell only", t["cells"]["N-FP8|32"]["usable"] is False and t["cells"]["N-FP8|128"]["usable"]))
    L5 = [lv("N-FP8", 128, 8713 * 1.12) if (r["arm"], r["concurrency"]) == ("N-FP8", 128) else r for r in L]
    cases.append(("N-FP8 12% above P59 at 128 -> R2 fails (tolerance 10%)", not analyse(L5, ev(), p59)["predictions"]["R2"]["pass"]))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    rd = lambda f: [json.loads(l) for l in open(os.path.join(d, f), encoding="utf-8")] if os.path.exists(os.path.join(d, f)) else []
    ev_file = "events_public.jsonl" if os.path.exists(os.path.join(d, "events_public.jsonl")) else "events.jsonl"
    p59 = json.load(open(P59_ANALYSIS, encoding="utf-8"))
    a = analyse(rd("levels.jsonl"), rd(ev_file), p59)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False, sort_keys=True)
    for k, c in a["cells"].items():
        print(k, c["usable"], c["total_tps"] and round(c["total_tps"]), c["p59_total_tps"] and round(c["p59_total_tps"]), c["this_over_p59"], c["reasons"])
    print(json.dumps(a["ratios_128"]), json.dumps(a["ratio_at_1"]))
    print(json.dumps({k: v["pass"] for k, v in a["predictions"].items()}), a["g8_positive_control"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
