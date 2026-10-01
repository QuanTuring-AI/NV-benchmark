#!/usr/bin/env python3
"""Vol.2 · P80 · judge every cell of the P80 night (G6 sweeps and G5), and the P78 predictions those runs answer.

Per measured cell (levels.jsonl rows that are not warm-up or sentinel probes; for a cell run twice, the second run):
  speed_ratio   total tok/s / the original main sweep's value at the same level (p55_concurrency_a2_256 for s256_*,
                p53_concurrency_v2 for v2_*; the values p80_rerun.py wrote into its 'originals' event)
  verdict       abnormal if speed_ratio <= 0.5 (P80 section 2); normal if speed_ratio >= 0.8; grey between;
                "no original" when the sweep has no original value at that level (G5, levels past an original crash)
  shape         the morning shape of 2026-09-30 (P80 section 2): utilization median >= 95% and power median <= 200 W over
                the cell's nvidia-smi rows, and speed_ratio <= 0.5; needs the 500 ms log, so None when it is missing
  arm_health    from cell_end: after / before ratio, marked (< 0.8, rerun) and null (< 0.8 twice)
Per group: sentinel pass / fail / not judged (G5). P78 predictions: s256_C P1 (the largest level inside the MLPerf
server SLO -- p99 TTFT <= 2,000 ms and p99 ITL <= 100 ms -- is 128), s256_C P2 (every level >= 0.95 x the original);
G5 P1 (a ladder step <= 2 starts and serves), P2 (no engine exit at 16, 32 or 64), P3 (generation rate at ~16k tokens >=
80% of ~4k). Positive control (P80 acceptance 7): this morning's s256_R c=1 (tok/s 99.8 vs 273.5) and s256_C c=128
(543.3 vs 3,902.1), vol2-nemotron/results/p78_clean_rerun/levels.jsonl lines 13 and 9, must be abnormal.
usage: p80_judge.py <run_dir> | self_test       -> writes <run_dir>/judge.json
"""
import csv, datetime as dt, glob, json, os, statistics as st, sys

ABNORMAL, NORMAL = 0.5, 0.8
SHAPE_UTIL, SHAPE_POWER = 95.0, 200.0


def verdict(ratio, abnormal=ABNORMAL, normal=NORMAL):
    if ratio is None:
        return "no original"
    if ratio <= abnormal:
        return "abnormal"
    if ratio >= normal:
        return "normal"
    return "grey"


def shape(util_med, power_med, ratio):
    if util_med is None or power_med is None or ratio is None:
        return None
    return util_med >= SHAPE_UTIL and power_med <= SHAPE_POWER and ratio <= ABNORMAL


def inside_slo(rec):
    s = rec.get("summary") or {}
    t = (s.get("time_to_first_token") or {}).get("p99"); i = (s.get("inter_token_latency") or {}).get("p99")
    return t is not None and i is not None and t <= 2000 and i <= 100


def smi_window(run, start, end):
    ts = lambda s: dt.datetime.fromisoformat(s[:19])  # noqa: E731
    rows = []
    for f in glob.glob(os.path.join(run, "smi_*.csv")):
        for r in csv.reader(open(f, encoding="utf-8")):
            try:
                t = dt.datetime.strptime(r[0].strip()[:19], "%Y/%m/%d %H:%M:%S")
            except Exception:  # noqa: BLE001
                continue
            if ts(start) <= t <= ts(end):
                try:
                    rows.append((float(r[4].split()[0]), float(r[5].split()[0])))
                except Exception:  # noqa: BLE001
                    pass
    if not rows:
        return None, None, 0
    return st.median(u for _, u in rows), st.median(p for p, _ in rows), len(rows)


def judge(run):
    ev = [json.loads(l) for l in open(os.path.join(run, "events.jsonl"), encoding="utf-8") if l.strip()]
    lv = [json.loads(l) for l in open(os.path.join(run, "levels.jsonl"), encoding="utf-8") if l.strip()]
    orig = next((e["tok_s"] for e in ev if e["kind"] == "originals"), {})
    ends = {}
    for e in ev:
        if e["kind"] == "cell_end":
            ends[(e["group"], e["concurrency"])] = e
    last = {}
    for r in lv:
        if r.get("warmup") or r.get("sentinel") or "concurrency" not in r or "group" not in r:
            continue
        last[(r["group"], r["concurrency"])] = r
    cells = []
    for (g, n), r in sorted(last.items(), key=lambda x: (x[0][0], x[0][1])):
        s = r.get("summary") or {}
        tps = (s.get("output_token_throughput") or {}).get("avg")
        o = orig.get(f"{g}|{n}")
        ratio = round(tps / o, 3) if tps and o else None
        u, p, nrows = smi_window(run, r["start"], r["end"])
        ce = ends.get((g, n), {})
        cells.append({"group": g, "concurrency": n, "tok_s": round(tps, 1) if tps else None, "original_tok_s": o, "speed_ratio": ratio,
                      "verdict": verdict(ratio), "engine_dead": r.get("engine_dead"), "inside_server_slo": inside_slo(r),
                      "smi_rows": nrows, "util_median": u, "power_median": p, "shape": shape(u, p, ratio),
                      "arm_health_ratio": ce.get("health_ratio"), "cell_attempt": r.get("cell_attempt", 1)})
    marked = [(e["group"], e["concurrency"]) for e in ev if e["kind"] == "cell_marked"]
    nulls = [(e.get("group"), e.get("concurrency"), e.get("reason")) for e in ev if e["kind"] == "level_null"]
    sent = {e["group"]: {"pass": e.get("pass"), "judged": e.get("judged")} for e in ev if e["kind"] == "sentinel"}
    gnull = [e["group"] for e in ev if e["kind"] == "group_null"]
    s256c = [c for c in cells if c["group"] == "s256_C"]
    inside = [c["concurrency"] for c in s256c if c["inside_server_slo"]]
    largest = None
    for c in sorted(s256c, key=lambda c: c["concurrency"]):
        if c["inside_server_slo"]:
            largest = c["concurrency"]
        else:
            break
    g5_attempt = [e for e in ev if e["kind"] == "attempt"]
    g5_served = next((e["step"] for e in g5_attempt if e.get("ready") and (e.get("probe") or {}).get("http_status") == 200), None)
    g5_exit = any(e["kind"] == "engine_exit" and e.get("group") == "G5" for e in ev)
    ctx = {e["depth"]: st.median([r["gen_rate"] for r in e["rows"] if r.get("gen_rate")]) for e in ev if e["kind"] == "context" and any(r.get("gen_rate") for r in e["rows"])}
    g5_levels = [c["concurrency"] for c in cells if c["group"] == "G5"]
    preds = {
        "s256_C_P1": {"largest_inside_server_slo": largest, "levels_inside": inside, "verdict": None if not s256c else ("pass" if largest == 128 else "fail")},
        "s256_C_P2": {"ratios": {c["concurrency"]: c["speed_ratio"] for c in s256c},
                      "verdict": None if not s256c else ("pass" if all(c["speed_ratio"] is not None and c["speed_ratio"] >= 0.95 for c in s256c) else "fail")},
        "G5_P1": {"served_at_step": g5_served, "verdict": None if not g5_attempt else ("pass" if g5_served is not None and g5_served <= 2 else "fail")},
        "G5_P2": {"levels_run": g5_levels, "engine_exit": g5_exit, "verdict": None if not g5_levels else ("pass" if not g5_exit and sorted(g5_levels) == [16, 32, 64] else ("fail" if g5_exit else "incomplete"))},
        "G5_P3": {"rates": ctx, "verdict": None if not {"4k", "16k"} <= set(ctx) else ("pass" if ctx["16k"] >= 0.8 * ctx["4k"] else "fail")},
    }
    out = {"cells": cells, "cells_marked_arm_health": marked, "level_nulls": nulls, "sentinel": sent, "groups_null": gnull, "p78_predictions": preds,
           "counts": {v: sum(1 for c in cells if c["verdict"] == v) for v in ("normal", "grey", "abnormal", "no original")},
           "shape_seen": [(c["group"], c["concurrency"]) for c in cells if c["shape"]]}
    json.dump(out, open(os.path.join(run, "judge.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return out


def self_test():
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want; ok &= good
        print(f"  {'PASS' if good else 'FAIL'} {name}: {got} (want {want})")
    # positive control: this morning (p78_clean_rerun levels.jsonl lines 13 and 9)
    check("positive control: s256_R c=1 99.8 / 273.54 -> abnormal", verdict(round(99.8 / 273.54, 3)), "abnormal")
    check("positive control: s256_C c=128 543.3 / 3902.07 -> abnormal", verdict(round(543.3 / 3902.07, 3)), "abnormal")
    check("P79 T1 container 1 c=128 3572 / 3902.07 -> normal", verdict(round(3572 / 3902.07, 3)), "normal")
    check("grey 0.6", verdict(0.6), "grey")
    check("no original", verdict(None), "no original")
    check("shape: 100% at 150 W at 0.14x -> shape", shape(100.0, 150.0, 0.14), True)
    check("shape: 95% at 380 W (a loaded card) -> not the shape", shape(95.0, 380.0, 0.95), False)
    check("shape: no smi rows -> None", shape(None, None, 0.14), None)
    check("SLO: p99 TTFT 1,188.8 / ITL 35.8 inside", inside_slo({"summary": {"time_to_first_token": {"p99": 1188.8}, "inter_token_latency": {"p99": 35.8}}}), True)
    check("SLO: p99 TTFT 33,917 outside", inside_slo({"summary": {"time_to_first_token": {"p99": 33917}, "inter_token_latency": {"p99": 258.8}}}), False)
    # mutations: a broken rule must let this morning's cells through
    check("mutation: abnormal line 0.1 -> this morning's s256_R c=1 no longer abnormal", verdict(round(99.8 / 273.54, 3), abnormal=0.1) != "abnormal", True)
    check("mutation: normal line 0.3 -> this morning's s256_R c=1 reads normal", verdict(round(99.8 / 273.54, 3), abnormal=0.2, normal=0.3), "normal")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "self_test":
        raise SystemExit(self_test())
    j = judge(sys.argv[1])
    print(json.dumps({k: j[k] for k in ("counts", "sentinel", "groups_null", "cells_marked_arm_health", "level_nulls", "shape_seen", "p78_predictions")}, indent=1, ensure_ascii=False))
