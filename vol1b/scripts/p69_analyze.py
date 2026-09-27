#!/usr/bin/env python3
"""Vol.2, P69 · analysis. Rules frozen in prediction_p69.json. Reads only published files: this run's levels.jsonl,
events_public.jsonl and contamination_marks.jsonl, and P66's and P67's published files (resolved from this file's
location). P66's and P67's analysis programs are imported unchanged and run on two assembled views:
  P66 clean view: P66's levels with every re-run cell replaced by its clean re-run, and R1024 at 1, 8, 16, 32 replaced by
    the re-runs made alternately with R3 (so R3 / R1024 at 1-32 has both terms from one window); G1 from this run's NIM
    health; G2 per arm = every server start of that arm in this run passed. Part D and R1024 at 64 / 128 stay P66's.
  P67 clean view: P67's levels with every re-run cell replaced; G2 for a replaced server label from this run; anchors (G7)
    against the P66 clean view.
Also: every re-run cell beside its contaminated original (total tok/s, ratio), marked descriptive only; G8 per cell.
Predictions:
  R1  the G8 positive control does not pass, and G8 passes before every re-run level
  R2  P67's N anchors (clean) within +-5% of P66's N (clean) at 32, 64, 128
  R3  R3 / R1024 at 1, 8, 16, 32 (same window) within 1.5-1.8
  R4  contaminated vs clean: reported only
A level that timed out (events `cell_hung`) is listed under `hung`; its record has no AIPerf summary, so P66's and P67's
programs make its cell null (G6: run failed). If its retry completed, the retry's record is the one used.
usage: p69_analyze.py <run_dir> | --self-test
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.path.abspath(os.path.join(HERE, "..", "results"))
sys.path.insert(0, HERE)
import p66_analyze as A66  # noqa: E402
import p67_analyze as A67  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BAND = (1.5, 1.8)
SAME_WINDOW = [1, 8, 16, 32]


def p66_view(l66, e66, l69, e69):
    mine = [r for r in l69 if r.get("source_run") == "P66"]
    key = lambda r: (r["arm"], r["concurrency"], bool(r.get("warmup")))
    rep = {key(r): r for r in mine}
    levels = [rep.get(key(r), r) for r in l66] + [r for r in mine if key(r) not in {key(x) for x in l66}]
    nim69 = next((e for e in e69 if e.get("kind") == "nim_start"), None)
    events = [e for e in e66 if e.get("kind") not in ("nim_start", "arm_start")] + ([nim69] if nim69 else [])
    for arm in ("N", "P", "R3", "R1024"):
        starts = [e for e in e69 if e.get("kind") == "arm_start" and e.get("run") == "P66" and e.get("arm") == arm]
        if starts:
            events.append({"kind": "arm_start", "arm": arm, "g2": {"pass": all((s.get("g2") or {}).get("pass") for s in starts), "server_starts": len(starts)}})
        else:
            events += [e for e in e66 if e.get("kind") == "arm_start" and e.get("arm") == arm]
    return levels, events


def p67_view(l67, e67, l69, e69):
    mine = [r for r in l69 if r.get("source_run") == "P67"]
    key = lambda r: (r.get("label") or r["arm"], r["concurrency"], bool(r.get("warmup")))
    rep = {key(r): r for r in mine}
    levels = [rep.get(key(r), r) for r in l67]
    labs = {r.get("label") for r in mine}
    starts = [e for e in e69 if e.get("kind") == "server_start" and e.get("run") == "P67"]
    events = [e for e in e67 if not (e.get("kind") == "server_start" and e.get("label") in labs)] + starts
    return levels, events


def analyse(l69, e69, marks, p66, p67):
    l66v, e66v = p66_view(p66["levels"], p66["events"], l69, e69)
    a66 = A66.analyse(l66v, e66v, p66["part_d"], p66["stack"])
    l67v, e67v = p67_view(p67["levels"], p67["events"], l69, e69)
    a67 = A67.analyse(l67v, e67v, p67["part_d"], p67["stack"], p67["prediction"], a66["cells"], p66["part_d"])
    g8 = [e for e in e69 if e.get("kind") == "g8"]
    pc = next((e for e in e69 if e.get("kind") == "g8_positive_control"), None)
    nulls = [e for e in e69 if e.get("kind") == "cell_null"]
    hung = [{k: e.get(k) for k in ("run", "label", "concurrency", "warmup", "attempt", "final", "in_flight")} | {"elapsed_s": (e.get("timeout") or {}).get("elapsed_s")}
            for e in e69 if e.get("kind") == "cell_hung"]
    orig = {("P66", r["arm"], r["concurrency"], bool(r.get("warmup"))): r for r in p66["levels"]}
    orig.update({("P67", r.get("label") or r["arm"], r["concurrency"], bool(r.get("warmup"))): r for r in p67["levels"]})
    tps = lambda r: ((r.get("summary") or {}).get("output_token_throughput") or {}).get("avg")
    pairs = []
    for m in marks:
        o = orig.get((m["run"], m["label"], m["concurrency"], bool(m["warmup"])))
        c = next((r for r in l69 if r.get("source_run") == m["run"] and (r.get("label") or r["arm"]) == m["label"] and r["concurrency"] == m["concurrency"]
                  and bool(r.get("warmup")) == bool(m["warmup"])), None)
        to, tc = o and tps(o), c and tps(c)
        pairs.append({"run": m["run"], "label": m["label"], "concurrency": m["concurrency"], "warmup": m["warmup"], "contaminated_tps": to, "clean_tps": tc,
                      "clean_over_contaminated": round(tc / to, 3) if to and tc else None, "clean_errors": c and ((c.get("summary") or {}).get("error_request_count") or {}).get("avg")})
    sw = {}
    for n in SAME_WINDOW:
        a, b = a66["cells"].get(f"R3|{n}") or {}, a66["cells"].get(f"R1024|{n}") or {}
        sw[str(n)] = {"R3_tps": a.get("total_tps"), "R1024_tps": b.get("total_tps"), "R3_over_R1024": (a66["ratios"].get(str(n)) or {}).get("R3_over_R1024"),
                      "both_usable": bool(a.get("usable") and b.get("usable"))}
    n_anchor = [x for x in a67["g7"]["anchors"] if x["p67"].startswith("N|")]
    pred = {"R1": {"pass": bool(pc) and pc.get("control_fired") is True and bool(g8) and all(e.get("pass") for e in g8) and not nulls,
                   "positive_control_fired": pc and pc.get("control_fired"), "g8_checks": len(g8), "g8_passed": sum(1 for e in g8 if e.get("pass")), "cells_null": len(nulls)},
            "R2": {"pass": bool(n_anchor) and all(x["pass"] for x in n_anchor), "anchors": n_anchor},
            "R3": {"pass": all(v["R3_over_R1024"] is not None and BAND[0] <= v["R3_over_R1024"] <= BAND[1] for v in sw.values()), "values": {k: v["R3_over_R1024"] for k, v in sw.items()}, "band": BAND},
            "R4": {"reported_only": True}}
    return {"p66_clean_view": {"cells": a66["cells"], "ratios": a66["ratios"], "g1_nim_health": a66["g1_nim_health"], "g2": a66["g2"]},
            "p67_clean_view": {k: a67[k] for k in ("cells", "g7", "r1024_2x2", "ratios", "head_table", "predictions")},
            "same_window_R3_over_R1024": sw, "g7_clean": a67["g7"],
            "contaminated_vs_clean": {"note": "descriptive only: what the other load was doing is not known", "rows": pairs},
            "g8": {"positive_control": pc and {k: pc.get(k) for k in ("control_fired", "gate_passed")} | {"sample": (pc.get("sample") or {})},
                   "checks": len(g8), "passed": sum(1 for e in g8 if e.get("pass")), "cells_null": nulls,
                   "by_cell": [{k: e.get(k) for k in ("run", "label", "concurrency", "warmup", "pass", "waited_s")} | {"last_samples": e["attempts"][-1]["samples"]} for e in g8]},
            "hung": {"rule": "timeout = max(3 x the original level's duration, 300 s), at most 900 s; one retry after the server is restarted",
                     "events": hung, "final": [f"{h['run']}|{h['label']}|{h['concurrency']}{'|warm-up' if h['warmup'] else ''}" for h in hung if h.get("final")]},
            "predictions": pred}


def self_test():
    ARMS = ["N", "P", "R3", "R1024"]; LV = [1, 8, 16, 32, 64, 128]
    T = {"N": 100.0, "P": 99.0, "R3": 60.0, "R1024": 36.0}
    def lv(arm, n, tps, warm=False, src=None, lab=None):
        r = {"arm": arm, "concurrency": n, "rc": 0, "summary": {"output_token_throughput": {"avg": tps}, "request_count": {"avg": 10 * n}, "error_request_count": {"avg": 0},
             "request_latency": {"p50": 1, "p99": 2}}, "nim": {"request_success": 10 * n, "prefix_hit_share": 0.05}, "server_cpu": {"server_bound": False},
             "raw": {"refusal_responses": 0}, "inputs": {"sha256_all": "s"}}
        if warm: r["warmup"] = True
        if src: r["source_run"] = src
        if lab: r["label"] = lab
        return r
    l66 = [lv(a, n, T[a] * n * (0.9 if a != "R1024" else 1.0)) for a in ARMS for n in LV]      # contaminated: 10% slower
    e66 = [{"kind": "nim_start", "health": {"pass": True}}] + [{"kind": "arm_start", "arm": a, "g2": {"pass": True}} for a in ARMS]
    labs67 = {"N": [32, 64, 128], "R3_W1K5": [32, 64, 128]}
    l67 = [lv(lab.split("_")[0], n, T[lab.split("_")[0]] * n * 0.9, lab=lab) for lab, ns in labs67.items() for n in ns]
    for r in l67:
        r.update(workers=None if r["label"] == "N" else 1, keep_alive_s=None if r["label"] == "N" else 5)
    e67 = [{"kind": "nim_start", "health": {"pass": True}}] + [{"kind": "server_start", "label": l, "g2": {"pass": True}, "server": {"all_workers_answering": True}} for l in labs67]
    l69 = [lv(a, n, T[a] * n, src="P66", lab=a) for a in ("N", "P", "R3") for n in LV] + [lv("R1024", n, T["R1024"] * n, src="P66", lab="R1024") for n in SAME_WINDOW] \
        + [lv("N", n, T["N"] * n, src="P67", lab="N") for n in (32, 64, 128)]
    e69 = [{"kind": "nim_start", "health": {"pass": True}}, {"kind": "g8_positive_control", "control_fired": True, "gate_passed": False, "sample": {}}] \
        + [{"kind": "arm_start", "run": "P66", "arm": a, "g2": {"pass": True}} for a in ARMS] + [{"kind": "server_start", "run": "P67", "label": "N", "g2": {"pass": True}, "server": {}}] \
        + [{"kind": "g8", "run": "P66", "label": "x", "concurrency": 1, "warmup": False, "pass": True, "waited_s": 10, "attempts": [{"samples": []}]}]
    marks = [{"run": "P66", "label": a, "concurrency": n, "warmup": False} for a in ("N", "P", "R3") for n in LV] + [{"run": "P67", "label": "N", "concurrency": n, "warmup": False} for n in (32, 64, 128)]
    p66 = {"levels": l66, "events": e66, "part_d": [], "stack": {"client_pool": {"max_connections": 1000}}}
    p67 = {"levels": l67, "events": e67, "part_d": [], "stack": {"client_pool": {"max_connections": 1000}}, "prediction": {}}
    x = analyse(l69, e69, marks, p66, p67)
    cases = [("same-window R3/R1024 = 60/36 = 1.667 at 1-32, R3 passes", all(v["R3_over_R1024"] == round(60 / 36, 3) for v in x["same_window_R3_over_R1024"].values()) and x["predictions"]["R3"]["pass"]),
             ("clean N (P67) vs clean N (P66) equal -> R2 passes", x["predictions"]["R2"]["pass"]),
             ("contaminated vs clean = 1/0.9 = 1.111 for P66 N 128", next(p for p in x["contaminated_vs_clean"]["rows"] if (p["run"], p["label"], p["concurrency"]) == ("P66", "N", 128))["clean_over_contaminated"] == round(1 / 0.9, 3)),
             ("R1 passes (control fired, all G8 passed)", x["predictions"]["R1"]["pass"])]
    e69b = [dict(e, control_fired=False) if e.get("kind") == "g8_positive_control" else e for e in e69]
    cases.append(("positive control did not fire -> R1 fails", not analyse(l69, e69b, marks, p66, p67)["predictions"]["R1"]["pass"]))
    e69c = e69 + [{"kind": "g8", "run": "P66", "label": "y", "concurrency": 8, "warmup": False, "pass": False, "waited_s": 900, "attempts": [{"samples": []}]}]
    cases.append(("one G8 failure -> R1 fails", not analyse(l69, e69c, marks, p66, p67)["predictions"]["R1"]["pass"]))
    l69d = [lv("N", n, T["N"] * n * 1.06, src="P67", lab="N") if (r.get("source_run"), r["arm"], r["concurrency"]) == ("P67", "N", 64) else r for r in l69 for n in [r["concurrency"]]]
    cases.append(("clean P67 N 64 6% above clean P66 N 64 -> R2 fails", not analyse(l69d, e69, marks, p66, p67)["predictions"]["R2"]["pass"]))
    l69e = [lv("R1024", 8, T["R3"] * 8 / 1.4, src="P66", lab="R1024") if (r.get("source_run"), r["arm"], r["concurrency"]) == ("P66", "R1024", 8) else r for r in l69]
    y = analyse(l69e, e69, marks, p66, p67)
    cases.append(("R1024 at 8 made so that R3/R1024 = 1.4 -> R3 fails, value 1.4", not y["predictions"]["R3"]["pass"] and y["same_window_R3_over_R1024"]["8"]["R3_over_R1024"] == 1.4))
    e69f = [dict(e, g2={"pass": False}) if e.get("kind") == "arm_start" and e.get("arm") == "R3" else e for e in e69]
    z = analyse(l69, e69f, marks, p66, p67)
    cases.append(("a failed G2 on an R3 server start -> R3 cells null, same-window ratios null", z["p66_clean_view"]["cells"]["R3|8"]["usable"] is False and z["same_window_R3_over_R1024"]["8"]["R3_over_R1024"] is None))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    rd = lambda p: [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []
    js = lambda p: json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    D66, D67 = os.path.join(RES, "p66_rails_under_load"), os.path.join(RES, "p67_rails_server_config")
    p66 = {"levels": rd(os.path.join(D66, "levels.jsonl")), "events": rd(os.path.join(D66, "events_public.jsonl")), "part_d": rd(os.path.join(D66, "part_d_verdicts.jsonl")),
           "stack": js(os.path.join(D66, "stack.json"))}
    p67 = {"levels": rd(os.path.join(D67, "levels.jsonl")), "events": rd(os.path.join(D67, "events_public.jsonl")), "part_d": rd(os.path.join(D67, "part_d_verdicts.jsonl")),
           "stack": js(os.path.join(D67, "stack.json")), "prediction": js(os.path.join(D67, "prediction_p67.json"))}
    a = analyse(rd(os.path.join(d, "levels.jsonl")), rd(os.path.join(d, "events_public.jsonl")), rd(os.path.join(d, "contamination_marks.jsonl")), p66, p67)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False, sort_keys=True)
    print(json.dumps(a["same_window_R3_over_R1024"])); print("G7", a["g7_clean"]["pass"], [(x["p67"], x["relative_difference"]) for x in a["g7_clean"]["anchors"]])
    print(json.dumps({k: v.get("pass") for k, v in a["predictions"].items()}))
    for p in a["contaminated_vs_clean"]["rows"]:
        print(p["run"], p["label"], p["concurrency"], "w" if p["warmup"] else "", p["contaminated_tps"] and round(p["contaminated_tps"]), p["clean_tps"] and round(p["clean_tps"]), p["clean_over_contaminated"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
