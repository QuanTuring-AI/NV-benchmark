#!/usr/bin/env python3
"""Vol.2 (directory vol1b/), P67 · analysis. Rules frozen in prediction_p67.json. Reads only published files: this run's
levels.jsonl, events_public.jsonl, part_d_verdicts.jsonl, stack.json, prediction_p67.json, and P66's analysis.json and
part_d_verdicts.jsonl (../results/p66_rails_under_load, resolved from this script's own directory). Writes analysis.json.

Cell = server label (N, or <arm>_W<workers>K<keep-alive s>) x concurrency, warm-up levels excluded. Values as P66 (total
output tok/s, latency p50 / p99, per-user end-to-end tok/s, NIM requests per client request, prefix-cache hit share, refusals,
passed-only tok/s) plus: error rate = errors / (completed + errors), errors by type, time from send to error, requests per
worker, keep-alive closes and connections lost counted in the server log, server CPU per process.
A cell is null (with reasons) if:
  G1  NIM health gate failed (every cell)
  G2  the server start's per-worker probes did not all come out as required (every cell of that server start), or not all
      W workers answered before the levels
  G5  the level's request payloads differ across the cells that ran that concurrency
  G6  errors > 1% of requests, or the AIPerf run failed
Flags (not null): server_bound (one process of the server >= 95% CPU for >= 10 s in a row) · pool_below_c · refusals ·
prefix_hits (N and P only: hit share above the frozen threshold (16-token block + the template's fixed prefix measured
before freezing) / mean prompt tokens, per arm; prediction_p67.json prefix_thresholds).
G7 (anchor): N at 32 / 64 / 128 and R3_W1K5 at 32 / 64 / 128 within +-5% of P66's same cells (total tok/s). If any of the six
fails or is missing, every field that compares with P66 is null; comparisons inside this run are unaffected.
Tables: R1024's 2 x 2 (W 1/4 x K 5/75) at 64 and 128 for error rate and total tok/s, with the simple effects (W at each
K, K at each W: error-rate difference in percentage points; tok/s ratio, both cells usable). Ratios per server config
and concurrency: R3/R1024, R3/N, P/N, R1024/N. Part D: the extra condition against P66's R1024 c1 on the same (item, round).
Predictions R1-R5 are evaluated mechanically as frozen.
usage: p67_analyze.py <run_dir> | --self-test
"""
import functools, json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
P66_DIR = os.path.join(HERE, "..", "results", "p66_rails_under_load")
SHAPE = "synthetic chat, 200 +- 50 tokens in / 200 +- 50 out, non-streaming, temperature 0"
ERR_MAX, ANCHOR_TOL = 0.01, 0.05
R1024_GRID = [("R1024_W1K5", 1, 5), ("R1024_W1K75", 1, 75), ("R1024_W4K5", 4, 5), ("R1024_W4K75", 4, 75)]
CONFIGS = ["W1K5", "W4K75"]
g = lambda d, *ks: functools.reduce(lambda a, k: a.get(k) if isinstance(a, dict) else None, ks, d)
arm_of = lambda lab: lab.split("_")[0]


def analyse(levels, events, pd, stack, pred, p66_cells, p66_pd):
    nim = next((e for e in events if e.get("kind") == "nim_start"), {})
    g1 = bool(g(nim, "health", "pass"))
    starts = {e["label"]: e for e in events if e.get("kind") == "server_start"}
    pool = g(stack, "client_pool", "max_connections")
    thr = g(pred, "analysis_rules", "prefix_thresholds") or {}
    rows = [r for r in levels if not r.get("warmup")]
    by = {(r["label"], r["concurrency"]): r for r in rows}
    shas = {}
    for (lab, n), r in by.items():
        shas.setdefault(n, {})[lab] = g(r, "inputs", "sha256_all")
    cells = {}
    for (lab, n), r in sorted(by.items(), key=lambda x: (x[0][1], x[0][0])):
        s = r.get("summary") or {}; st = starts.get(lab) or {}
        done = g(s, "request_count", "avg") or 0; errs = g(s, "error_request_count", "avg") or 0; tot = done + errs
        reasons, flags = [], []
        if not g1:
            reasons.append("G1 NIM health below 0.60")
        if not g(st, "g2", "pass"):
            reasons.append("G2 per-worker probes failed")
        if lab != "N" and not g(st, "server", "all_workers_answering"):
            reasons.append("G2 not all workers answered")
        ls = set(shas.get(n, {}).values())
        if len(ls) != 1 or None in ls:
            reasons.append("G5 request payloads differ across cells")
        if r.get("rc") != 0 or not s or (tot and errs / tot > ERR_MAX):
            reasons.append("G6 errors above 1% or run failed")
        cpu = r.get("server_cpu") or {}
        if cpu.get("server_bound"):
            flags.append("server_bound")
        if pool is not None and pool < n:
            flags.append("pool_below_c")
        refus = g(r, "raw", "refusal_responses") or 0
        if refus:
            flags.append("refusals")
        hit = g(r, "nim", "prefix_hit_share"); t = g(thr, arm_of(lab), "threshold")
        if arm_of(lab) in ("N", "P") and hit is not None and t is not None and hit > t:
            flags.append("prefix_hits")
        nimreq = g(r, "nim", "request_success")
        sl = r.get("server_log") or {}
        cells[f"{lab}|{n}"] = {
            "label": lab, "arm": arm_of(lab), "workers": r.get("workers"), "keep_alive_s": r.get("keep_alive_s"), "variant": r.get("variant"),
            "concurrency": n, "input_shape": SHAPE, "usable": not reasons, "reasons": reasons, "flags": flags,
            "total_tps": g(s, "output_token_throughput", "avg"), "latency_p50_ms": g(s, "request_latency", "p50"), "latency_p99_ms": g(s, "request_latency", "p99"),
            "per_user_e2e_tps": g(s, "e2e_output_token_throughput", "avg"), "completed": done, "errors": errs,
            "error_rate": round(errs / tot, 5) if tot else None, "errors_by_type": g(r, "errors", "by_type"), "send_to_error_ms": g(r, "errors", "send_to_error_ms"),
            "refusal_responses": refus, "passed_only_tps": g(r, "raw", "passed_only_tps"),
            "nim_requests_per_client_request": round(nimreq / done, 3) if nimreq and done else None, "prefix_hit_share": hit,
            "server_bound": bool(cpu.get("server_bound")), "server_cpu_longest_run_ge_95pct_s": cpu.get("longest_run_ge_95pct_s_any_process"),
            "server_processes_busy": cpu.get("processes_busy_p50_ge_5pct"),
            "server_cpu_max_by_process": {k: v.get("cpu_pct_max") for k, v in (cpu.get("per_process") or {}).items()} or None,
            "requests_by_worker": sl.get("chat_requests_by_worker"), "keepalive_closes": sl.get("keepalive_closes"), "connections_lost": sl.get("connections_lost")}
    out = {"g1_nim_health": nim.get("health"), "host": g(stack, "host"), "cells": cells}
    out["g2"] = {lab: {"pass": g(e, "g2", "pass"), "workers_answering": g(e, "server", "workers_answering"),
                       "listen_winerror_10022_at_start": g(e, "server", "listen_winerror_10022"),
                       "config_sha256_by_worker": {pid: v.get("config_sha256") for pid, v in (g(e, "server", "workers_imported") or {}).items()},
                       "per_worker": g(e, "g2", "per_worker")} for lab, e in starts.items()}
    # G7 anchors
    anchors = []
    for lab, p66arm in (("N", "N"), ("R3_W1K5", "R3")):
        for n in (32, 64, 128):
            a, b = cells.get(f"{lab}|{n}") or {}, p66_cells.get(f"{p66arm}|{n}") or {}
            ta, tb = a.get("total_tps"), b.get("total_tps")
            rel = round(ta / tb - 1, 4) if ta and tb else None
            anchors.append({"p67": f"{lab}|{n}", "p66": f"{p66arm}|{n}", "p67_tps": ta, "p66_tps": tb, "relative_difference": rel,
                            "pass": rel is not None and abs(rel) <= ANCHOR_TOL and bool(a.get("usable"))})
    g7 = bool(anchors) and all(x["pass"] for x in anchors)
    out["g7"] = {"tolerance": ANCHOR_TOL, "anchors": anchors, "pass": g7,
                 "consequence": "comparisons with P66 reported" if g7 else "every comparison with P66 is null; comparisons inside this run are unaffected"}
    # R1024 2 x 2
    grid = {}
    for n in (64, 128):
        t = {lab: cells.get(f"{lab}|{n}") or {} for lab, _, _ in R1024_GRID}
        er = lambda lab: t[lab].get("error_rate")
        tp = lambda lab: t[lab].get("total_tps") if t[lab].get("usable") else None
        dpp = lambda x, y: round((er(x) - er(y)) * 100, 3) if er(x) is not None and er(y) is not None else None
        rat = lambda x, y: round(tp(x) / tp(y), 3) if tp(x) and tp(y) else None
        grid[str(n)] = {"error_rate": {lab: er(lab) for lab, _, _ in R1024_GRID},
                        "total_tps": {lab: t[lab].get("total_tps") for lab, _, _ in R1024_GRID},
                        "usable": {lab: t[lab].get("usable") for lab, _, _ in R1024_GRID},
                        "server_bound": {lab: t[lab].get("server_bound") for lab, _, _ in R1024_GRID},
                        "keepalive_closes": {lab: t[lab].get("keepalive_closes") for lab, _, _ in R1024_GRID},
                        "error_rate_effect_pp": {"K75_minus_K5_at_W1": dpp("R1024_W1K75", "R1024_W1K5"), "K75_minus_K5_at_W4": dpp("R1024_W4K75", "R1024_W4K5"),
                                                 "W4_minus_W1_at_K5": dpp("R1024_W4K5", "R1024_W1K5"), "W4_minus_W1_at_K75": dpp("R1024_W4K75", "R1024_W1K75")},
                        "tps_ratio": {"K75_over_K5_at_W1": rat("R1024_W1K75", "R1024_W1K5"), "K75_over_K5_at_W4": rat("R1024_W4K75", "R1024_W4K5"),
                                      "W4_over_W1_at_K5": rat("R1024_W4K5", "R1024_W1K5"), "W4_over_W1_at_K75": rat("R1024_W4K75", "R1024_W1K75")}}
    out["r1024_2x2"] = grid
    # ratios per server config
    ratios = {}
    for cfg in CONFIGS:
        for n in (32, 64, 128):
            def ratio(a, b):
                ca, cb = cells.get(a) or {}, cells.get(b) or {}
                return round(ca["total_tps"] / cb["total_tps"], 3) if ca.get("usable") and cb.get("usable") and ca.get("total_tps") and cb.get("total_tps") else None
            ratios[f"{cfg}|{n}"] = {"server": cfg, "concurrency": n, "input_shape": SHAPE,
                                    "R3_over_R1024": ratio(f"R3_{cfg}|{n}", f"R1024_{cfg}|{n}"), "R3_over_N": ratio(f"R3_{cfg}|{n}", f"N|{n}"),
                                    "P_over_N": ratio(f"P_{cfg}|{n}", f"N|{n}"), "R1024_over_N": ratio(f"R1024_{cfg}|{n}", f"N|{n}")}
    out["ratios"] = ratios
    # head table: P66's 64 / 128 beside this run's W4K75 (and W1K5 for reference)
    head = []
    for n in (64, 128):
        for arm in ("N", "P", "R3", "R1024"):
            b = p66_cells.get(f"{arm}|{n}") or {}
            head.append({"source": "P66", "arm": arm, "workers": None if arm == "N" else 1, "keep_alive_s": None if arm == "N" else 5, "concurrency": n,
                         "total_tps": b.get("total_tps"), "usable": b.get("usable"), "server_bound": "server_bound" in (b.get("flags") or []),
                         "error_rate": round(b["errors"] / (b["completed"] + b["errors"]), 5) if b.get("completed") is not None and b.get("errors") is not None else None})
            lab = "N" if arm == "N" else f"{arm}_W4K75"
            c = cells.get(f"{lab}|{n}") or {}
            head.append({"source": "P67", "arm": arm, "workers": c.get("workers"), "keep_alive_s": c.get("keep_alive_s"), "concurrency": n, "total_tps": c.get("total_tps"),
                         "usable": c.get("usable"), "server_bound": c.get("server_bound"), "error_rate": c.get("error_rate"),
                         "vs_p66_same_arm": (round(c["total_tps"] / b["total_tps"], 3) if g7 and c.get("usable") and b.get("usable") and c.get("total_tps") and b.get("total_tps") else None)})
    out["head_table"] = head
    # Part D
    pdc = sorted({r["condition"] for r in pd})
    per = {}
    for cond in pdc:
        rs = [r for r in pd if r["arm"] == "R1024" and r["condition"] == cond]
        adv = [r for r in rs if r["expected"] == "block"]; ok = [r for r in rs if r["expected"] == "pass"]
        base = {(r["item"], r["round"]): r["blocked"] for r in p66_pd if r["arm"] == "R1024" and r["condition"] == "c1"}
        mine = {(r["item"], r["round"]): r["blocked"] for r in rs}
        ks = sorted(set(base) & set(mine)); fl = [f"{i}#r{rd}" for i, rd in ks if base[(i, rd)] != mine[(i, rd)]]
        per[cond] = {"arm": "R1024", "adversarial_blocked": sum(1 for r in adv if r["blocked"]), "adversarial_n": len(adv),
                     "false_blocks": sum(1 for r in ok if r["blocked"]), "passable_n": len(ok),
                     "missed": sorted(f"{r['item']}#r{r['round']}" for r in adv if not r["blocked"]),
                     "http_errors": sum(1 for r in rs if r.get("http_status") != 200),
                     "latency_p50_ms": sorted(r["latency_ms"] for r in rs if r.get("latency_ms"))[len(rs) // 2] if rs else None,
                     "paired_with_p66_R1024_c1": {"pairs": len(ks), "flips": len(fl), "flipped": fl}}
    out["part_d"] = per
    out["predictions"] = evaluate(out, pred)
    return out


def evaluate(a, pred):
    c = a["cells"]; grid = a["r1024_2x2"]; res = {}
    res["R1"] = {"pass": all(x["pass"] for x in a["g7"]["anchors"] if x["p67"].startswith("N|")) and any(x["p67"].startswith("N|") for x in a["g7"]["anchors"]),
                 "basis": "N anchors within +-5% of P66"}
    k75 = [grid[n]["error_rate"][lab] for n in ("64", "128") for lab in ("R1024_W1K75", "R1024_W4K75")]
    wdiff = [grid[n]["error_rate_effect_pp"][k] for n in ("64", "128") for k in ("W4_minus_W1_at_K5", "W4_minus_W1_at_K75")]
    res["R2"] = {"pass": all(x is not None and x <= 0.005 for x in k75) and all(x is not None and abs(x) <= 0.5 for x in wdiff),
                 "k75_error_rates": k75, "w_effect_pp": wdiff, "basis": "every K75 cell of R1024 at 64 and 128 has error rate <= 0.5%, and W changes the error rate by <= 0.5 pp at each K and level"}
    w4_rails_128 = [c.get(f"{lab}|128") or {} for lab in ("R3_W4K75", "R1024_W4K75", "R1024_W4K5")]
    r3w4, r3w1 = c.get("R3_W4K75|128") or {}, c.get("R3_W1K5|128") or {}
    res["R3"] = {"pass": bool(w4_rails_128) and all(x and not x.get("server_bound") for x in w4_rails_128) and bool(r3w4.get("total_tps") and r3w1.get("total_tps") and r3w4["total_tps"] > r3w1["total_tps"]),
                 "w4_rails_c128_server_bound": {x.get("label"): x.get("server_bound") for x in w4_rails_128 if x},
                 "R3_c128_tps_W4K75_vs_W1K5": [r3w4.get("total_tps"), r3w1.get("total_tps")],
                 "basis": "no W4 rails cell at c=128 is server_bound, and R3 W4K75 total tok/s at c=128 > R3 W1K5"}
    rr = [a["ratios"].get(f"W4K75|{n}", {}).get("R3_over_R1024") for n in (64, 128)]
    res["R4"] = {"pass": all(x is not None and 1.5 <= x <= 1.8 for x in rr), "values": rr, "basis": "W4K75 R3/R1024 at 64 and 128 within 1.5-1.8"}
    d = next(iter(a["part_d"].values()), None)
    res["R5"] = {"pass": bool(d) and d["adversarial_blocked"] == 42 and d["adversarial_n"] == 45 and d["false_blocks"] == 0 and d["passable_n"] == 90
                 and d["paired_with_p66_R1024_c1"]["pairs"] == 135 and d["paired_with_p66_R1024_c1"]["flips"] == 0,
                 "basis": "Part D c128_W4K75: 42/45 blocked, 0/90 false blocks, 0 of 135 flips against P66 R1024 c1"}
    return res


def self_test():
    labs = {"N": (None, None, [32, 64, 128]), "R1024_W1K5": (1, 5, [64, 128]), "R1024_W4K75": (4, 75, [64, 128]), "R1024_W1K75": (1, 75, [64, 128]),
            "R1024_W4K5": (4, 5, [64, 128]), "R3_W1K5": (1, 5, [32, 64, 128]), "R3_W4K75": (4, 75, [32, 64, 128]), "P_W4K75": (4, 75, [64, 128]), "P_W1K5": (1, 5, [64, 128])}
    T = {"N": 100.0, "P": 99.0, "R3": 60.0, "R1024": 36.0}
    ev = [{"kind": "nim_start", "health": {"pass": True}}] + [{"kind": "server_start", "label": l, "g2": {"pass": True}, "server": {"all_workers_answering": True}} for l in labs]

    def lv(lab, n, tps=None, errs=0, bound=False, sha="s", hit=0.05, rc=0, done=None):
        w, k, _ = labs[lab]
        tps = tps if tps is not None else T[arm_of(lab)] * n * (1.1 if w == 4 else 1.0)
        return {"label": lab, "workers": w, "keep_alive_s": k, "concurrency": n, "rc": rc,
                "summary": {"output_token_throughput": {"avg": tps}, "request_count": {"avg": done if done is not None else 10 * n},
                            "error_request_count": {"avg": errs}, "request_latency": {"p50": 1, "p99": 2}},
                "nim": {"request_success": 30 * n, "prefix_hit_share": hit}, "server_cpu": {"server_bound": bound}, "raw": {"refusal_responses": 0}, "inputs": {"sha256_all": sha}}
    L = [lv(l, n) for l, (_, _, ns) in labs.items() for n in ns]
    p66 = {f"{a}|{n}": {"total_tps": T[a] * n, "usable": True, "completed": 10 * n, "errors": 0, "flags": []} for a in T for n in (32, 64, 128)}
    pred = {"analysis_rules": {"prefix_thresholds": {"N": {"threshold": 0.14}, "P": {"threshold": 0.40}}}}
    st = {"client_pool": {"max_connections": 1000}}
    p66pd = [{"arm": "R1024", "condition": "c1", "round": r, "item": f"q{i}", "expected": "block" if i < 15 else "pass", "blocked": i < 14} for r in (1, 2, 3) for i in range(45)]
    pd = [dict(x, condition="c128_W4K75", http_status=200, latency_ms=100) for x in p66pd]
    A = lambda L_=L, ev_=ev, pd_=pd, pred_=pred, p66_=p66: analyse(L_, ev_, pd_, st, pred_, p66_, p66pd)
    x = A()
    cases = [("baseline: G7 passes, R3/R1024 = 66/39.6 at W4K75", x["g7"]["pass"] and x["ratios"]["W4K75|64"]["R3_over_R1024"] == round(66 / 39.6, 3)),
             ("baseline: R4 passes (1.667 in 1.5-1.8)", x["predictions"]["R4"]["pass"]),
             ("baseline: R2 passes (no errors) and R3 passes (W4 not bound, 10% faster)", x["predictions"]["R2"]["pass"] and x["predictions"]["R3"]["pass"]),
             ("baseline: Part D 42/45, 0/90, 0 flips, R5 passes", x["predictions"]["R5"]["pass"])]
    L1 = [lv("N", 64, tps=94 * 64) if (r["label"], r["concurrency"]) == ("N", 64) else r for r in L]
    y = A(L_=L1)
    cases.append(("N anchor 6% low -> G7 fails, R1 fails, vs-P66 fields null", not y["g7"]["pass"] and not y["predictions"]["R1"]["pass"]
                  and all(h.get("vs_p66_same_arm") is None for h in y["head_table"] if h["source"] == "P67")))
    L2 = [lv("R1024_W1K5", 128, errs=20, done=1260) if (r["label"], r["concurrency"]) == ("R1024_W1K5", 128) else r for r in L]
    z = A(L_=L2)
    cases.append(("20 errors of 1280 -> cell null; K effect at W1 = -1.5625 pp", z["cells"]["R1024_W1K5|128"]["usable"] is False
                  and z["r1024_2x2"]["128"]["error_rate_effect_pp"]["K75_minus_K5_at_W1"] == round((0 - 20 / 1280) * 100, 3)))
    L3 = [lv("R1024_W4K75", 64, errs=7, done=633) if (r["label"], r["concurrency"]) == ("R1024_W4K75", 64) else r for r in L]
    cases.append(("a K75 cell at 1.09% errors -> R2 fails", not A(L_=L3)["predictions"]["R2"]["pass"]))
    L3b = [lv(r["label"], 64, errs=5, done=635) if (r["label"], r["concurrency"]) in (("R1024_W4K75", 64), ("R1024_W1K75", 64), ("R1024_W4K5", 64), ("R1024_W1K5", 64)) else r for r in L]
    cases.append(("all four R1024 cells at 64 at 0.78% errors (no W effect) -> R2 fails on the 0.5% bound", not A(L_=L3b)["predictions"]["R2"]["pass"]))
    L4 = [lv("R3_W4K75", 128, bound=True, tps=66 * 128) if (r["label"], r["concurrency"]) == ("R3_W4K75", 128) else r for r in L]
    w = A(L_=L4)
    cases.append(("W4 rails cell server_bound -> flagged, kept, R3 fails", "server_bound" in w["cells"]["R3_W4K75|128"]["flags"] and w["cells"]["R3_W4K75|128"]["usable"]
                  and not w["predictions"]["R3"]["pass"]))
    L5 = [lv("R3_W4K75", 128, tps=59 * 128) if (r["label"], r["concurrency"]) == ("R3_W4K75", 128) else r for r in L]
    cases.append(("R3 W4K75 at c=128 below W1K5 -> R3 fails", not A(L_=L5)["predictions"]["R3"]["pass"]))
    L6 = [lv("P_W4K75", 64, sha="other") if (r["label"], r["concurrency"]) == ("P_W4K75", 64) else r for r in L]
    v = A(L_=L6)
    cases.append(("payload sha differs at c=64 -> every c=64 cell null, c=32 kept", all(c["usable"] is False for k, c in v["cells"].items() if k.endswith("|64")) and v["cells"]["N|32"]["usable"]))
    ev2 = [dict(e, g2={"pass": False}) if e.get("label") == "R3_W4K75" else e for e in ev]
    cases.append(("G2 failure on one server start -> its cells null only", all(A(ev_=ev2)["cells"][f"R3_W4K75|{n}"]["usable"] is False for n in (32, 64, 128)) and A(ev_=ev2)["cells"]["R3_W1K5|32"]["usable"]))
    ev3 = [dict(e, server={"all_workers_answering": False}) if e.get("label") == "P_W4K75" else e for e in ev]
    cases.append(("not all workers answered -> that start's cells null", A(ev_=ev3)["cells"]["P_W4K75|64"]["usable"] is False))
    L7 = [lv("N", 32, hit=0.15) if (r["label"], r["concurrency"]) == ("N", 32) else r for r in L]
    u = A(L_=L7)
    cases.append(("N hit share 0.15 > frozen 0.14 -> prefix_hits; P at 0.05 < 0.40 -> none", "prefix_hits" in u["cells"]["N|32"]["flags"] and "prefix_hits" not in u["cells"]["P_W4K75|64"]["flags"]))
    pd2 = [dict(r, blocked=not r["blocked"]) if (r["item"], r["round"]) == ("q20", 2) else r for r in pd]
    t = A(pd_=pd2)["part_d"]["c128_W4K75"]
    cases.append(("one passable item blocked -> 1/90 false block, 1 flip, R5 fails", t["false_blocks"] == 1 and t["paired_with_p66_R1024_c1"]["flips"] == 1 and not A(pd_=pd2)["predictions"]["R5"]["pass"]))
    L8 = [lv("R1024_W4K75", 128, tps=36 * 128 * 1.25) if (r["label"], r["concurrency"]) == ("R1024_W4K75", 128) else r for r in L]
    q = A(L_=L8)
    cases.append(("W4K75 R1024 at 45 tok/s per c -> W4/W1 at K75 = 1.25, R3/R1024 = 1.467 (R4 fails)", q["r1024_2x2"]["128"]["tps_ratio"]["W4_over_W1_at_K75"] == 1.25
                  and q["ratios"]["W4K75|128"]["R3_over_R1024"] == round(66 / 45, 3) and not q["predictions"]["R4"]["pass"]))
    for name, ok in cases:
        print(("PASS " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    rd = lambda p: [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []
    js = lambda p: json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    p66 = js(os.path.join(P66_DIR, "analysis.json"))
    a = analyse(rd(os.path.join(d, "levels.jsonl")), rd(os.path.join(d, "events_public.jsonl")), rd(os.path.join(d, "part_d_verdicts.jsonl")),
                js(os.path.join(d, "stack.json")), js(os.path.join(d, "prediction_p67.json")), p66.get("cells") or {}, rd(os.path.join(P66_DIR, "part_d_verdicts.jsonl")))
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False, sort_keys=True)
    for k, c in a["cells"].items():
        print(k, c.get("usable"), c.get("total_tps") and round(c["total_tps"]), c.get("error_rate"), c.get("flags"), c.get("reasons"), c.get("requests_by_worker"))
    print("G7", a["g7"]["pass"], [(x["p67"], x["relative_difference"]) for x in a["g7"]["anchors"]])
    print(json.dumps(a["r1024_2x2"], indent=0)[:2000])
    print(json.dumps(a["ratios"]))
    print(json.dumps(a["part_d"])[:800])
    print(json.dumps({k: v["pass"] for k, v in a["predictions"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
