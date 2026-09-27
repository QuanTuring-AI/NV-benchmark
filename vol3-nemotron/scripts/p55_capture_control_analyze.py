#!/usr/bin/env python3
"""Vol.2 · A2 capture-size control (p55_capture_control.py) · analysis. Rules frozen in prediction_p55_capture_control.json.

Preconditions per condition (a failed one -> that condition's verdict inputs are null):
  P1 every measured level rc 0, 0 errors, engine alive
  P2 AIPerf c=1 against the harness's own calibration: TTFT within max(20 ms, 20%), ITL within 20% (p53_concurrency_v2's rule)
  P3 the capture setting reached the engine: the startup log's mixed prefill-decode (PIECEWISE) capture count equals the
     count the setting implies (default at cap 256 -> 51 sizes; capture size 64 -> 11)
Verdict, both conditions from this run: r = s256_cg064 / s256_default, output tok/s at c=32 (r16 at c=16 reported beside it)
  "measured"  r <= 0.85: at cap 256, lowering only the capture size to cap-32's slows c=32 by 15% or more
  "withdrawn" r >= 0.95: it does not -> the capture size does not explain why rates rise with the cap
  "partial"   otherwise; "unverified" if either condition fails a precondition
  The reverse direction (cap 32 with the cap-256 capture size) is not run here.
usage: p55_capture_control_analyze.py <run_dir> | --self-test
"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
EXPECT_PIECEWISE = {"s256_default": 51, "s256_cg064": 11}
CAL_TOL, CAL_FLOOR = 0.20, 20.0
PW = "mixed prefill-decode, PIECEWISE"


def pct(s, k, p):
    return ((s or {}).get(k) or {}).get(p)


def analyse(levels, events):
    starts = {e["container"]: e for e in events if e.get("kind") == "container_start"}
    out = {"conditions": {}}
    for cond, exp in EXPECT_PIECEWISE.items():
        ev = starts.get(cond) or {}
        rows = sorted((r for r in levels if r.get("container") == cond and not r.get("warmup") and "concurrency" in r), key=lambda r: r["concurrency"])
        p1 = bool(rows) and all(r.get("rc") == 0 and r.get("summary") and not r.get("engine_dead")
                                and not ((r["summary"].get("error_request_count") or {}).get("avg") or 0) for r in rows)
        cal, c1 = ev.get("calibration") or {}, next((r for r in rows if r["concurrency"] == 1), None)
        p2 = False; det = None
        if cal.get("ttft_ms_p50") and cal.get("itl_ms_p50") and c1 and c1.get("summary"):
            at, ai = pct(c1["summary"], "time_to_first_token", "p50"), pct(c1["summary"], "inter_token_latency", "p50")
            dt = abs(at - cal["ttft_ms_p50"]); di = abs(ai - cal["itl_ms_p50"]) / cal["itl_ms_p50"]
            p2 = (dt <= CAL_FLOOR or dt / cal["ttft_ms_p50"] <= CAL_TOL) and di <= CAL_TOL
            det = {"aiperf_ttft": at, "own_ttft": cal["ttft_ms_p50"], "aiperf_itl": ai, "own_itl": cal["itl_ms_p50"]}
        got = (ev.get("captured_graph_sizes") or {}).get(PW)
        p3 = got == exp
        tps = {r["concurrency"]: pct(r["summary"], "output_token_throughput", "avg") for r in rows if r.get("summary")}
        itl = {r["concurrency"]: pct(r["summary"], "inter_token_latency", "p50") for r in rows if r.get("summary")}
        out["conditions"][cond] = {"preconditions": {"P1_levels_clean": p1, "P2_calibrated": {"pass": p2, "detail": det},
                                                     "P3_capture_applied": {"expected_piecewise_sizes": exp, "logged": got, "all_logged": ev.get("captured_graph_sizes"), "pass": p3}},
                                   "pass": p1 and p2 and p3, "output_tps": tps, "itl_p50_ms": itl}
    c = out["conditions"]
    if all(v["pass"] for v in c.values()) and all(32 in v["output_tps"] for v in c.values()):
        r = c["s256_cg064"]["output_tps"][32] / c["s256_default"]["output_tps"][32]
        d16, l16 = c["s256_default"]["output_tps"].get(16), c["s256_cg064"]["output_tps"].get(16)
        verdict = "measured" if r <= 0.85 else ("withdrawn" if r >= 0.95 else "partial")
        out["verdict"] = {"r": round(r, 4), "r16": round(l16 / d16, 4) if d16 and l16 else None, "attribution": verdict}
    else:
        out["verdict"] = {"r": None, "r16": None, "attribution": "unverified"}
    return out


def self_test():
    def lv(cond, n, tps, ttft=40.0, itl=3.2, rc=0, err=0):
        return {"container": cond, "concurrency": n, "rc": rc, "engine_dead": False,
                "summary": {"output_token_throughput": {"avg": tps}, "time_to_first_token": {"p50": ttft}, "inter_token_latency": {"p50": itl}, "error_request_count": {"avg": err}}}

    def ev(cond, pw):
        return {"kind": "container_start", "container": cond, "calibration": {"ttft_ms_p50": 45.0, "itl_ms_p50": 3.2}, "captured_graph_sizes": {PW: pw, "decode, FULL": 7}}
    base_ev = [ev("s256_default", 51), ev("s256_cg064", 11)]

    def lvs(hi, lo):
        return [lv("s256_default", 1, 300), lv("s256_default", 16, 1500), lv("s256_default", 32, hi), lv("s256_cg064", 1, 300), lv("s256_cg064", 16, 1100), lv("s256_cg064", 32, lo)]
    cases = [("measured (0.70)", analyse(lvs(2200, 1550), base_ev)["verdict"]["attribution"] == "measured"),
             ("withdrawn (0.98)", analyse(lvs(2200, 2150), base_ev)["verdict"]["attribution"] == "withdrawn"),
             ("partial (0.91)", analyse(lvs(2200, 2000), base_ev)["verdict"]["attribution"] == "partial"),
             ("boundary 0.85 is measured", analyse(lvs(2000, 1700), base_ev)["verdict"]["attribution"] == "measured"),
             ("capture not applied -> unverified", analyse(lvs(2200, 1550), [ev("s256_default", 51), ev("s256_cg064", 51)])["verdict"]["attribution"] == "unverified"),
             ("errors -> unverified", analyse(lvs(2200, 1550)[:-1] + [lv("s256_cg064", 32, 1550, err=3)], base_ev)["verdict"]["attribution"] == "unverified"),
             ("calibration off by 30 ms and 30% -> unverified", analyse([dict(r, summary=dict(r["summary"], time_to_first_token={"p50": 75.0})) if r["concurrency"] == 1 and r["container"] == "s256_cg064" else r for r in lvs(2200, 1550)], base_ev)["verdict"]["attribution"] == "unverified"),
             ("calibration within the 20 ms floor passes", analyse([dict(r, summary=dict(r["summary"], time_to_first_token={"p50": 28.0})) if r["concurrency"] == 1 else r for r in lvs(2200, 1550)], base_ev)["verdict"]["attribution"] == "measured")]
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    levels = [json.loads(l) for l in open(os.path.join(d, "levels.jsonl"), encoding="utf-8")]
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf-8")]
    a = analyse(levels, events)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps(a["verdict"]), {k: (v["pass"], v["output_tps"]) for k, v in a["conditions"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
