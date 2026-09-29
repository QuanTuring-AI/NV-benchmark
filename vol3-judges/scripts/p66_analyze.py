#!/usr/bin/env python3
"""Vol.2 (directory vol1b/), P66 · analysis. Rules frozen in prediction_p66.json. Reads only published files:
levels.jsonl, events_public.jsonl, part_d_verdicts.jsonl, stack.json. Writes analysis.json.

Part L cell (arm x concurrency, warm-up excluded): total output tok/s (AIPerf output_token_throughput avg, final-answer
tokens counted on the client), request latency p50 / p99 (non-streaming: end to end), per-user end-to-end tok/s (AIPerf
e2e_output_token_throughput avg), NIM requests per client request (NIM counter delta / completed), NIM prefix-cache hit
share, the Guardrails server's CPU, refusal responses and errors. A cell is null (with reasons) if:
  G1  the NIM arm-health gate failed (decode rate at c=1 x 16.06 GB / 1,792 GB/s < 0.60): every cell
  G2  the arm's blocked / passed probes before its levels did not come out as required: every cell of that arm
  G5  the level's request payloads (AIPerf inputs.json, sha256 over all payloads) are not identical across the arms that ran it
  G6  errors > 1% of requests (errors by code listed; 503 / queue_full counted)
Flags (not null): server_bound (server CPU >= 95% for >= 10 s in a row, G3) · pool_below_c (client pool max_connections
< concurrency, G4) · refusals (responses equal to the rails' refusal text > 0; the passed-only throughput is then
reported beside the total) · prefix_hits (N or P arm with hit share > 2%; the rails arms' self-check template is shared by
design and only reported).
Ratios (per concurrency, total output tok/s, both cells usable): R3 / R1024 (what the one line takes back), R3 / N (what
the rails cost under load), P / N (the server alone); each row carries its concurrency and the input shape.
Part D: per arm x condition (c1, c128): adversarial blocked / 45, clean + edge blocked / 90, the set of adversarial items
missed (item x round), and paired flips between c1 and c128 on the same (item, round).
usage: p66_analyze.py <run_dir> | --self-test
"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ARMS = ["N", "P", "R3", "R1024"]
LEVELS = [1, 8, 16, 32, 64, 128]
SHAPE = "synthetic chat, 200 +- 50 tokens in / 200 +- 50 out, non-streaming, temperature 0"
ERR_MAX, HIT_MAX = 0.01, 0.02
g = lambda d, *ks: (lambda x: x)(__import__("functools").reduce(lambda a, k: (a or {}).get(k) if isinstance(a, dict) else None, ks, d))


def analyse(levels, events, pd, stack):
    nim = next((e for e in events if e.get("kind") == "nim_start"), {})
    g1 = bool(g(nim, "health", "pass"))
    starts = {e["arm"]: e for e in events if e.get("kind") == "arm_start"}
    pool = g(stack, "client_pool", "max_connections")
    rows = [r for r in levels if not r.get("warmup")]
    by = {(r["arm"], r["concurrency"]): r for r in rows}
    shas = {}
    for (arm, n), r in by.items():
        shas.setdefault(n, {})[arm] = g(r, "inputs", "sha256_all")
    out = {"g1_nim_health": nim.get("health"), "g2": {a: g(starts.get(a), "g2") for a in ARMS}, "stack": stack, "cells": {}, "ratios": {}, "part_d": {}}
    cells = {}
    for arm in ARMS:
        for n in LEVELS:
            r = by.get((arm, n)); key = f"{arm}|{n}"
            if not r:
                cells[key] = {"usable": False, "reasons": ["not run"]}; continue
            s = r.get("summary") or {}
            done = g(s, "request_count", "avg") or 0
            errs = g(s, "error_request_count", "avg") or 0
            reasons, flags = [], []
            if not g1:
                reasons.append("G1 NIM health below 0.60")
            if not g(starts.get(arm), "g2", "pass"):
                reasons.append("G2 probes failed")
            ls = {v for v in shas.get(n, {}).values()}
            if len(ls) != 1 or None in ls:
                reasons.append("G5 request payloads differ across arms")
            tot = done + errs
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
            hit = g(r, "nim", "prefix_hit_share")
            if arm in ("N", "P") and hit is not None and hit > HIT_MAX:
                flags.append("prefix_hits")
            nimreq = g(r, "nim", "request_success")
            tps = g(s, "output_token_throughput", "avg")
            cells[key] = {"usable": not reasons, "reasons": reasons, "flags": flags, "concurrency": n, "input_shape": SHAPE,
                          "total_tps": tps, "latency_p50_ms": g(s, "request_latency", "p50"), "latency_p99_ms": g(s, "request_latency", "p99"),
                          "per_user_e2e_tps": g(s, "e2e_output_token_throughput", "avg"), "completed": done, "errors": errs,
                          "errors_by_code": g(r, "raw", "errors_by_code"), "refusal_responses": refus,
                          "passed_only_tps": g(r, "raw", "passed_only_tps"),
                          "nim_requests": nimreq, "nim_requests_per_client_request": round(nimreq / done, 3) if nimreq and done else None,
                          "prefix_hit_share": hit, "server_cpu": cpu or None}
    out["cells"] = cells
    for n in LEVELS:
        def ratio(a, b):
            ca, cb = cells.get(f"{a}|{n}") or {}, cells.get(f"{b}|{n}") or {}
            if ca.get("usable") and cb.get("usable") and ca.get("total_tps") and cb.get("total_tps"):
                return round(ca["total_tps"] / cb["total_tps"], 3)
            return None
        out["ratios"][str(n)] = {"concurrency": n, "input_shape": SHAPE, "R3_over_R1024": ratio("R3", "R1024"),
                                 "R3_over_N": ratio("R3", "N"), "P_over_N": ratio("P", "N"), "R1024_over_N": ratio("R1024", "N")}
    conds = sorted({r["condition"] for r in pd})
    for arm in ("R3", "R1024"):
        per = {}
        for cond in conds:
            rs = [r for r in pd if r["arm"] == arm and r["condition"] == cond]
            if not rs:
                continue
            adv = [r for r in rs if r["expected"] == "block"]; ok = [r for r in rs if r["expected"] == "pass"]
            per[cond] = {"adversarial_blocked": sum(1 for r in adv if r["blocked"]), "adversarial_n": len(adv),
                         "false_blocks": sum(1 for r in ok if r["blocked"]), "passable_n": len(ok),
                         "missed": sorted(f"{r['item']}#r{r['round']}" for r in adv if not r["blocked"]),
                         "http_errors": sum(1 for r in rs if r.get("http_status") != 200),
                         "latency_p50_ms": sorted(r["latency_ms"] for r in rs if r.get("latency_ms"))[len(rs) // 2] if rs else None}
        flips = None
        if len(conds) >= 2:
            a_, b_ = conds[0], conds[1]
            ma = {(r["item"], r["round"]): r["blocked"] for r in pd if r["arm"] == arm and r["condition"] == a_}
            mb = {(r["item"], r["round"]): r["blocked"] for r in pd if r["arm"] == arm and r["condition"] == b_}
            ks = sorted(set(ma) & set(mb))
            fl = [f"{i}#r{rd}" for i, rd in ks if ma[(i, rd)] != mb[(i, rd)]]
            flips = {"pairs": len(ks), "flips": len(fl), "flipped": fl, "conditions": [a_, b_]}
        out["part_d"][arm] = {"by_condition": per, "paired_flips": flips}
    return out


def self_test():
    ok_ev = [{"kind": "nim_start", "health": {"pass": True}}] + [{"kind": "arm_start", "arm": a, "g2": {"pass": True}} for a in ARMS]
    def lv(arm, n, tps, errs=0, cpu=None, sha="s", refus=0, hit=0.001, rc=0):
        return {"arm": arm, "concurrency": n, "rc": rc, "summary": {"output_token_throughput": {"avg": tps}, "request_count": {"avg": 200}, "error_request_count": {"avg": errs},
                "request_latency": {"p50": 1000, "p99": 2000}}, "nim": {"request_success": 600 if arm.startswith("R") else 200, "prefix_hit_share": hit},
                "server_cpu": cpu, "raw": {"refusal_responses": refus}, "inputs": {"sha256_all": sha}}
    T = {"N": 100.0, "P": 90.0, "R3": 60.0, "R1024": 30.0}
    L = [lv(a, n, T[a] * n) for a in ARMS for n in LEVELS]
    st = {"client_pool": {"max_connections": 1000}}
    pd = [{"arm": a, "condition": c, "round": r, "item": f"q{i}", "expected": "block" if i < 15 else "pass", "blocked": (i < 14) if not (c == "c128" and i == 3 and r == 1) else False,
           "http_status": 200, "latency_ms": 100} for a in ("R3", "R1024") for c in ("c1", "c128") for r in (1, 2, 3) for i in range(45)]
    x = analyse(L, ok_ev, pd, st)
    cases = [("R3/R1024 = 2.0 at every level", all(x["ratios"][str(n)]["R3_over_R1024"] == 2.0 for n in LEVELS)),
             ("P/N = 0.9", x["ratios"]["128"]["P_over_N"] == 0.9),
             ("Part D c1: 42/45 blocked, 0/90 false blocks", x["part_d"]["R3"]["by_condition"]["c1"]["adversarial_blocked"] == 42 and x["part_d"]["R3"]["by_condition"]["c1"]["false_blocks"] == 0),
             ("one flip c1 -> c128", x["part_d"]["R3"]["paired_flips"]["flips"] == 1 and x["part_d"]["R3"]["paired_flips"]["flipped"] == ["q3#r1"])]
    L2 = [dict(r, summary=dict(r["summary"], error_request_count={"avg": 5})) if (r["arm"], r["concurrency"]) == ("R1024", 128) else r for r in L]
    y = analyse(L2, ok_ev, pd, st)
    cases.append(("errors 5/205 > 1% -> cell null, ratio null", y["cells"]["R1024|128"]["usable"] is False and y["ratios"]["128"]["R3_over_R1024"] is None))
    L3 = [dict(r, inputs={"sha256_all": "other"}) if (r["arm"], r["concurrency"]) == ("P", 16) else r for r in L]
    z = analyse(L3, ok_ev, pd, st)
    cases.append(("payload sha differs at c=16 -> every c=16 cell null", all(z["cells"][f"{a}|16"]["usable"] is False for a in ARMS) and z["cells"]["P|8"]["usable"]))
    ev2 = [dict(e, g2={"pass": False}) if e.get("arm") == "R3" else e for e in ok_ev]
    cases.append(("G2 failure -> arm null", all(analyse(L, ev2, pd, st)["cells"][f"R3|{n}"]["usable"] is False for n in LEVELS)))
    L4 = [dict(r, server_cpu={"server_bound": True}) if (r["arm"], r["concurrency"]) == ("P", 64) else r for r in L]
    w = analyse(L4, ok_ev, pd, st)
    cases.append(("server_bound flagged, cell kept", "server_bound" in w["cells"]["P|64"]["flags"] and w["cells"]["P|64"]["usable"]))
    cases.append(("pool below c flagged", "pool_below_c" in analyse(L, ok_ev, pd, {"client_pool": {"max_connections": 100}})["cells"]["N|128"]["flags"]))
    cases.append(("G1 failure -> all null", not any(c["usable"] for c in analyse(L, [dict(ok_ev[0], health={"pass": False})] + ok_ev[1:], pd, st)["cells"].values())))
    L5 = [dict(r, nim=dict(r["nim"], prefix_hit_share=0.05)) if (r["arm"], r["concurrency"]) == ("N", 8) else r for r in L]
    cases.append(("N prefix hits > 2% flagged", "prefix_hits" in analyse(L5, ok_ev, pd, st)["cells"]["N|8"]["flags"]))
    pd2 = [dict(r, blocked=True) if (r["arm"], r["condition"], r["round"], r["item"]) == ("R1024", "c128", 2, "q20") else r for r in pd]
    v = analyse(L, ok_ev, pd2, st)["part_d"]["R1024"]["by_condition"]["c128"]
    cases.append(("one passable item blocked -> 1 false block of 90", v["false_blocks"] == 1 and v["passable_n"] == 90))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    rd = lambda f: [json.loads(l) for l in open(os.path.join(d, f), encoding="utf-8")] if os.path.exists(os.path.join(d, f)) else []
    st = json.load(open(os.path.join(d, "stack.json"), encoding="utf-8")) if os.path.exists(os.path.join(d, "stack.json")) else {}
    a = analyse(rd("levels.jsonl"), rd("events_public.jsonl"), rd("part_d_verdicts.jsonl"), st)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False, sort_keys=True)
    for k, c in a["cells"].items():
        print(k, c.get("usable"), c.get("total_tps") and round(c["total_tps"]), c.get("latency_p50_ms") and round(c["latency_p50_ms"]), c.get("latency_p99_ms") and round(c["latency_p99_ms"]), c.get("flags"), c.get("reasons"))
    print(json.dumps(a["ratios"]))
    print(json.dumps(a["part_d"])[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
