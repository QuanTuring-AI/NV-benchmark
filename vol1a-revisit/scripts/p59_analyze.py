#!/usr/bin/env python3
"""Vol.1-A revisit, P59 · analysis. Rules frozen in prediction_p59_nim_value.json.

Per arm (from events.jsonl and levels.jsonl):
  gate G1 residency   Ollama: the main container's load shows `ollama ps` PROCESSOR "100% GPU"; NIM: READY and CUDA
                      graph sizes captured in the startup log (the engine runs on the GPU)
  gate G2 arm health  decode rate at c=1 on profile C (1000 / AIPerf p50 inter-token latency) x bytes read per token
                      (BYTES below: the weight file sizes) / 1,792 GB/s >= 0.40; every arm's value is printed
  An arm failing G1 or G2: every comparison that involves it is null.
Per container: isolation passed and the prefix-cache detector passed (else that container's levels are not used).
Main container: calibration against AIPerf c=1 (p50 TTFT within max(20 ms, 20%), p50 ITL within 20%), per profile;
  a failed calibration makes that profile's levels of that arm unusable (null), as in p53_concurrency_v2.
Per level (usable only if rc 0, a summary, 0 request errors, the engine alive, and no level after an engine death):
  truncation  any request whose server-reported prompt tokens < 98% of the client count -> level null; no server count on
              any request -> "truncation unverified" (kept, flagged)
  early stop  median completion tokens < 90% of the profile's target -> "early stop": total throughput and per-user
              speed of that level are not compared; TTFT and TPOT are
  cells       total output tok/s (AIPerf output_token_throughput avg) · per-user tok/s (output_token_throughput_per_user avg)
              · p99 TTFT · p99 TPOT · inside the server SLO (p99 TTFT <= 2,000 ms and p99 TPOT <= 100 ms) · inside the
              interactive SLO (500 ms, 30 ms)
Crossings (pairs B vs A, per profile, per metric total and per-user, main containers, levels usable on both arms):
  the sign of B - A at each level; a change of sign between two consecutive usable levels -> "between X and Y"; no
  change -> "B ahead throughout 1-128" / "A ahead throughout" / "equal"; fewer than two usable levels -> null.
  Pairs: N-BF16 vs O-Q4, N-BF16 vs O-Q4-def, N-BF16 vs O-FP16 (engine at comparable precision), N-FP8 vs N-BF16 (the
  per-level ratio FP8/BF16 is also listed).
usage: p59_analyze.py <run_dir> | --self-test
"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PEAK = 1792e9
HEALTH = 0.40
BYTES = {"O-Q4": 4920738944, "O-Q4-def": 4920738944, "O-FP16": 16068895872, "N-BF16": 16060522496, "N-FP8": 9081280648}   # O-FP16 filled from its GGUF blob size before freezing
SLO = {"server": (2000.0, 100.0), "interactive": (500.0, 30.0)}
TARGET = {"C": 200, "R": 500}
PAIRS = [("N-BF16", "O-Q4"), ("N-BF16", "O-Q4-def"), ("N-BF16", "O-FP16"), ("N-FP8", "N-BF16")]


def pct(s, k, p):
    return ((s or {}).get(k) or {}).get(p)


def analyse(levels, events, bytes_=None):
    bytes_ = bytes_ or BYTES
    starts = {}
    for e in events:
        if e.get("kind") == "container_start":
            starts[(e["arm"], e["container"])] = e
    profs = {(e["arm"], e["profile"]): e for e in events if e.get("kind") == "profile_start" and e.get("container") == "main"}
    fits = [e for e in events if e.get("kind") == "ollama_fit"]
    fit4096 = {e["arm"]: e.get("num_parallel") for e in events if e.get("kind") == "ollama_fit_4096_result"}
    arms = sorted({r["arm"] for r in levels if "arm" in r} | {e["arm"] for e in events if "arm" in e})
    out = {"arms": {}, "crossings": {}}
    table = {}
    for arm in arms:
        main = starts.get((arm, "main")) or {}
        kind = "ollama" if arm.startswith("O-") else "nim"
        if kind == "ollama":
            g1 = bool(((main.get("load") or {}).get("full_gpu")))
        else:
            g1 = bool(main) and bool(main.get("captured_graph_sizes") or ((main.get("readback") or {}).get("captured_graph_sizes")))
        rows = [r for r in levels if r.get("arm") == arm and not r.get("warmup") and "concurrency" in r]
        c1 = next((r for r in rows if r["profile"] == "C" and r["container"] == "main" and r["concurrency"] == 1 and r.get("summary")), None)
        itl = pct((c1 or {}).get("summary"), "inter_token_latency", "p50")
        rate = 1000.0 / itl if itl else None
        b = bytes_.get(arm)
        share = rate * b / PEAK if rate and b else None
        g2 = share is not None and share >= HEALTH
        par_fit = next((f.get("num_parallel_set") for f in fits if f["arm"] == arm and f.get("pass")), None)
        par_log = ((main.get("load") or {}).get("runner_parallel_from_log"))
        cal = {}
        for prof in ("C", "R"):
            ps = profs.get((arm, prof)) or {}
            c = ps.get("calibration") or {}
            lv1 = next((r for r in rows if r["profile"] == prof and r["container"] == "main" and r["concurrency"] == 1 and r.get("summary")), None)
            ok = None; det = None
            if c.get("ttft_ms_p50") and c.get("itl_ms_p50") and lv1:
                at, ai = pct(lv1["summary"], "time_to_first_token", "p50"), pct(lv1["summary"], "inter_token_latency", "p50")
                dt, di = abs(at - c["ttft_ms_p50"]), abs(ai - c["itl_ms_p50"]) / c["itl_ms_p50"]
                ok = (dt <= 20.0 or dt / c["ttft_ms_p50"] <= 0.20) and di <= 0.20
                det = {"aiperf_ttft_p50": at, "own_ttft_p50": c["ttft_ms_p50"], "aiperf_itl_p50": ai, "own_itl_p50": c["itl_ms_p50"]}
            cal[prof] = {"pass": bool(ok), "detail": det}
        out["arms"][arm] = {"gate_residency": {"pass": g1, "ollama_ps": (main.get("load") or {}).get("ollama_ps") if kind == "ollama" else None,
                                               "captured_graph_sizes": main.get("captured_graph_sizes") if kind == "nim" else None},
                            "gate_health": {"decode_rate_c1_tok_s": round(rate, 2) if rate else None, "bytes_per_token": b,
                                            "share_of_peak": round(share, 4) if share is not None else None, "pass": g2},
                            "usable": g1 and g2,
                            "isolation_and_detector": {t: {"isolation": ((starts.get((arm, t)) or {}).get("isolation") or {}).get("pass"),
                                                           "detector": ((starts.get((arm, t)) or {}).get("prefix_detector") or {}).get("pass"),
                                                           "detector_control_fired": (((starts.get((arm, t)) or {}).get("prefix_detector") or {}).get("positive_control_same_prompt_twice") or {}).get("fired")}
                                                       for t in ("main", "fresh") if (arm, t) in starts},
                            "calibration": cal,
                            "ollama_num_parallel": {"set_at_8192": par_fit, "runner_from_log": par_log, "largest_at_4096": fit4096.get(arm)} if kind == "ollama" else None}
        for r in rows:
            key = (arm, r["profile"], r["container"])
            st_ = starts.get((arm, r["container"])) or {}
            cont_ok = bool((st_.get("isolation") or {}).get("pass") and (st_.get("prefix_detector") or {}).get("pass"))
            s = r.get("summary") or {}
            ch = r.get("checks") or {}
            errs = (s.get("error_request_count") or {}).get("avg") or 0
            flags = []
            usable = cont_ok and r.get("rc") == 0 and bool(s) and not errs and not r.get("engine_dead")
            if r["container"] == "main" and not cal[r["profile"]]["pass"]:
                usable = False; flags.append("calibration failed")
            if ch.get("truncated_requests"):
                usable = False; flags.append("truncated prompts")
            elif ch and ch.get("requests_without_server_prompt_count") and ch.get("server_over_client_prompt_min") is None:
                flags.append("truncation unverified")
            early = bool(ch.get("completion_below_90pct_of_target"))
            if early:
                flags.append("early stop")
            tt, it = pct(s, "time_to_first_token", "p99"), pct(s, "inter_token_latency", "p99")
            cell = {"usable": usable, "flags": flags, "total_tps": pct(s, "output_token_throughput", "avg"),
                    "per_user_tps": pct(s, "output_token_throughput_per_user", "avg"), "ttft_p99_ms": tt, "tpot_p99_ms": it,
                    "completed": r.get("completed"), "completion_tokens_p50": ch.get("completion_tokens_p50"),
                    "server_over_client_prompt_min": ch.get("server_over_client_prompt_min"),
                    "in_server_slo": (tt is not None and it is not None and tt <= SLO["server"][0] and it <= SLO["server"][1]),
                    "in_interactive_slo": (tt is not None and it is not None and tt <= SLO["interactive"][0] and it <= SLO["interactive"][1])}
            table.setdefault(key, {})[r["concurrency"]] = cell
    out["levels"] = {"|".join(k): v for k, v in table.items()}
    for b_arm, a_arm in PAIRS:
        for prof in ("C", "R"):
            for metric in ("total_tps", "per_user_tps"):
                key = f"{b_arm} vs {a_arm}|{prof}|{metric}"
                if not ((out["arms"].get(b_arm) or {}).get("usable") and (out["arms"].get(a_arm) or {}).get("usable")):
                    out["crossings"][key] = None; continue
                tb, ta = table.get((b_arm, prof, "main"), {}), table.get((a_arm, prof, "main"), {})
                pts = []
                for n in sorted(set(tb) & set(ta)):
                    cb, ca = tb[n], ta[n]
                    if cb["usable"] and ca["usable"] and "early stop" not in cb["flags"] + ca["flags"] and cb[metric] and ca[metric]:
                        pts.append((n, cb[metric], ca[metric]))
                out["crossings"][key] = crossing(pts, b_arm, a_arm)
    return out


def crossing(pts, b, a):
    if len(pts) < 2:
        return None
    sign = lambda x, y: (x > y) - (x < y)
    sg = [sign(x, y) for _, x, y in pts]
    res = {"levels": [n for n, _, _ in pts], "ratio_b_over_a": [round(x / y, 3) for _, x, y in pts], "crossings": []}
    for i in range(1, len(pts)):
        if sg[i] != sg[i - 1] and sg[i] != 0 and sg[i - 1] != 0:
            res["crossings"].append(f"between {pts[i - 1][0]} and {pts[i][0]}: {b if sg[i] > 0 else a} ahead from {pts[i][0]}")
    if not res["crossings"]:
        res["crossings"] = [f"{b} ahead throughout {pts[0][0]}-{pts[-1][0]}" if all(s > 0 for s in sg) else
                            f"{a} ahead throughout {pts[0][0]}-{pts[-1][0]}" if all(s < 0 for s in sg) else "no clean crossing (ties)"]
    return res


def self_test():
    def lv(arm, prof, n, tot, per, ttft=100.0, itl=10.0, cont="main", errs=0, trunc=0, osl=None, rc=0):
        return {"arm": arm, "profile": prof, "container": cont, "concurrency": n, "rc": rc, "engine_dead": False,
                "summary": {"output_token_throughput": {"avg": tot}, "output_token_throughput_per_user": {"avg": per},
                            "time_to_first_token": {"p50": 30.0, "p99": ttft}, "inter_token_latency": {"p50": itl, "p99": itl},
                            "error_request_count": {"avg": errs}},
                "checks": {"truncated_requests": trunc, "server_over_client_prompt_min": 1.02, "requests_without_server_prompt_count": 0,
                           "completion_tokens_p50": osl or TARGET[prof], "completion_below_90pct_of_target": (osl or TARGET[prof]) < 0.9 * TARGET[prof]}}
    good = {"isolation": {"pass": True}, "prefix_detector": {"pass": True, "positive_control_same_prompt_twice": {"fired": True}}}
    ev = [{"kind": "container_start", "arm": "O-Q4", "container": "main", "load": {"full_gpu": True, "ollama_ps": "100% GPU"}, **good},
          {"kind": "container_start", "arm": "N-BF16", "container": "main", "captured_graph_sizes": {"decode, FULL": 35}, **good}]
    ev += [{"kind": "profile_start", "arm": a, "profile": p, "container": "main", "calibration": {"ttft_ms_p50": 30.0, "itl_ms_p50": i}}
           for a, i in (("O-Q4", 4.3), ("N-BF16", 10.0)) for p in ("C", "R")]
    # O-Q4: 230 tok/s single stream (itl 4.35 ms), flat total above 32; N-BF16: 100 tok/s single, grows to 6,000
    L = []
    for n, oq, nb in ((1, 230, 100), (8, 900, 780), (16, 1100, 1260), (32, 1200, 2500), (64, 1150, 4200), (128, 1100, 6000)):
        for p in ("C", "R"):
            L.append(lv("O-Q4", p, n, oq, oq / n, itl=4.3 if n == 1 else 20.0))
            L.append(lv("N-BF16", p, n, nb, nb / n, itl=10.0 if n == 1 else 15.0))
    x = analyse(L, ev, dict(BYTES, **{"O-FP16": 16e9}))
    cases = []
    cases.append(("health O-Q4 = 1000/4.3 x 4.92 GB / 1792 = 0.639", abs(x["arms"]["O-Q4"]["gate_health"]["share_of_peak"] - 0.6385) < 0.002))
    cases.append(("both arms usable", x["arms"]["O-Q4"]["usable"] and x["arms"]["N-BF16"]["usable"]))
    cx = x["crossings"]["N-BF16 vs O-Q4|C|total_tps"]["crossings"]
    cases.append(("total crossing between 8 and 16", cx == ["between 8 and 16: N-BF16 ahead from 16"]))
    cp = x["crossings"]["N-BF16 vs O-Q4|C|per_user_tps"]["crossings"]
    cases.append(("per-user crossing between 8 and 16", cp == ["between 8 and 16: N-BF16 ahead from 16"]))
    cases.append(("pair with a missing arm -> null", x["crossings"]["N-BF16 vs O-FP16|C|total_tps"] is None))
    L2 = [dict(r, checks=dict(r["checks"], truncated_requests=3)) if r["arm"] == "O-Q4" and r["concurrency"] == 16 and r["profile"] == "C" else r for r in L]
    y = analyse(L2, ev)
    cases.append(("truncated level unusable and skipped in the crossing", y["levels"]["O-Q4|C|main"][16]["usable"] is False
                  and y["crossings"]["N-BF16 vs O-Q4|C|total_tps"]["crossings"] == ["between 8 and 32: N-BF16 ahead from 32"]))
    L3 = [dict(r, checks=dict(r["checks"], completion_tokens_p50=150, completion_below_90pct_of_target=True)) if r["arm"] == "O-Q4" and r["concurrency"] == 8 and r["profile"] == "C" else r for r in L]
    z = analyse(L3, ev)
    cases.append(("early stop excluded from throughput crossings", "early stop" in z["levels"]["O-Q4|C|main"][8]["flags"]
                  and 8 not in z["crossings"]["N-BF16 vs O-Q4|C|total_tps"]["levels"]))
    ev_bad = [dict(e, load={"full_gpu": False, "ollama_ps": "23%/77% CPU/GPU"}) if e.get("arm") == "O-Q4" and e["kind"] == "container_start" else e for e in ev]
    cases.append(("residency gate fails -> comparisons null", analyse(L, ev_bad)["crossings"]["N-BF16 vs O-Q4|C|total_tps"] is None))
    L4 = [dict(r, summary=dict(r["summary"], inter_token_latency={"p50": 60.0, "p99": 60.0})) if r["arm"] == "O-Q4" and r["concurrency"] == 1 and r["profile"] == "C" else r for r in L]
    w = analyse(L4, ev)   # 16.7 tok/s x 4.92 GB = 4.6% of peak: the 7.3x failure mode
    cases.append(("health gate under 40% -> arm unusable, comparisons null", w["arms"]["O-Q4"]["gate_health"]["pass"] is False and w["crossings"]["N-BF16 vs O-Q4|C|total_tps"] is None))
    ev_det = [dict(e, prefix_detector={"pass": False}) if e.get("arm") == "N-BF16" and e["kind"] == "container_start" else e for e in ev]
    cases.append(("detector failed -> that container's levels unusable", analyse(L, ev_det)["levels"]["N-BF16|C|main"][32]["usable"] is False))
    ev_cal = [dict(e, calibration={"ttft_ms_p50": 90.0, "itl_ms_p50": 10.0}) if e.get("arm") == "N-BF16" and e.get("profile") == "R" else e for e in ev]
    v = analyse(L, ev_cal)
    cases.append(("calibration off by 60 ms on R -> R levels unusable, C kept", v["levels"]["N-BF16|R|main"][32]["usable"] is False and v["levels"]["N-BF16|C|main"][32]["usable"] is True))
    cases.append(("SLO cell", x["levels"]["N-BF16|C|main"][32]["in_server_slo"] is True and x["levels"]["N-BF16|C|main"][32]["in_interactive_slo"] is True))
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
    for arm, v in a["arms"].items():
        print(arm, "usable", v["usable"], "health", v["gate_health"], "residency", v["gate_residency"]["pass"], "cal", {p: c["pass"] for p, c in v["calibration"].items()}, v["ollama_num_parallel"])
    for k, v in a["crossings"].items():
        print(k, v and v["crossings"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
