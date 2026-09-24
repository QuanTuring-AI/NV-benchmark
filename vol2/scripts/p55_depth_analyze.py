#!/usr/bin/env python3
"""Vol.2 · depth probes (p55_depth.py) · analysis. Rules frozen in the run's pre-registration.
Per condition that reached READY, on the measured rows only (warm-up rows are summarised, never pooled):
  P1 every measured request HTTP 200 with usage and no error
  P2 the measured prompt_tokens median is within 25% of the condition's target
  P3 exactly one container up at every request; for a condition with an expected capture length or eager setting, the
     engine's own config dump (startup log) shows it (otherwise the change did not reach the engine)
Per condition: medians of TTFT, generation rate, prompt and completion tokens; memory at READY and KV tokens; warm-up
count, seconds, whether it stabilized, first / last warm-up rate. A condition that did not start is reported with the
engine's refusal as that arm's ceiling at that model length.
Comparisons (only between conditions whose preconditions pass):
  forward test: generation-rate ratio capture/default at 16k: >= 1.40 'measured', <= 1.10 'withdrawn', between 'partial';
    the capture condition failing P3 (the setting did not reach the engine) -> 'unverified'
  reverse test (the attribution of record when the forward test cannot run): r4 = 4k eager/default, r16 = 16k eager/default;
    r4 <= 0.75 and 0.90 <= r16 <= 1.10 -> 'measured: turning CUDA graphs off reproduces the step at 4k and changes nothing
    at 16k'; r4 >= 0.90 -> 'withdrawn: CUDA graphs do not explain the step'; otherwise 'partial'
  and and the 120k medians against reference runs given with --ref (repeatable; per arm
the reference with the most depths is used: A1 p53_longctx, A2 p53_longctx_addendum).
usage: p55_depth_analyze.py <run_dir> [--ref p53_longctx_addendum/analysis.json] | --self-test
"""
import json, os, statistics as st, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOL = 0.25


def med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(st.median(xs), 2) if xs else None


def analyse(rows, events, ref=None):
    refs = ref if isinstance(ref, list) else ([ref] if ref else [])
    starts = {e["condition"]: e for e in events if e.get("kind") == "condition_start"}
    fails = {e["condition"]: e for e in events if e.get("kind") == "condition_failed"}
    warm_end = {e["condition"]: e for e in events if e.get("kind") == "warmup_end"}
    out = {"conditions": {}, "all_preconditions_pass": True}
    for cond in sorted(set(starts) | set(fails)):
        if cond in fails and cond not in starts:
            f = fails[cond]
            out["conditions"][cond] = {"started": False, "arm": f.get("arm"), "env": f.get("env"), "reason": f.get("reason"),
                                       "log_lines": f.get("log_lines"), "engine_config_from_log": f.get("capture"), "reading": "did not start at this model length: recorded as the ceiling"}
            continue
        ev = starts[cond]
        meas = [r for r in rows if r.get("condition") == cond and not r.get("warmup")]
        warm = [r for r in rows if r.get("condition") == cond and r.get("warmup")]
        bad1 = [r.get("i") for r in meas if r.get("error") or r.get("http_status") != 200 or not r.get("usage_present")]
        pt = med([r.get("prompt_tokens") for r in meas]); tgt = ev.get("target")
        p2 = pt is not None and tgt and abs(pt - tgt) / tgt <= TOL
        one = all(len(r.get("docker_ps_before") or []) == 1 for r in meas)
        cap_expect = ev.get("expect_capture")
        cap_seen = ((ev.get("engine_config_from_log") or {}).get("max_seq_len_to_capture") or [])
        cap_ok = True if not cap_expect else (bool(cap_seen) and all(x == cap_expect for x in cap_seen))
        eager_expect = ev.get("expect_eager")
        eager_seen = ((ev.get("engine_config_from_log") or {}).get("enforce_eager") or [])
        if eager_expect is not None:
            cap_ok = cap_ok and bool(eager_seen) and all(x == eager_expect for x in eager_seen)
        pre = {"P1": {"violations": bad1, "pass": bool(meas) and not bad1},
               "P2_depth_within_25pct": {"prompt_tokens_p50": pt, "target": tgt, "pass": bool(p2)},
               "P3_one_container_and_config": {"one_container": one, "capture_expected": cap_expect, "capture_in_engine_config": cap_seen,
                                               "eager_expected": eager_expect, "eager_in_engine_config": eager_seen, "pass": one and cap_ok}}
        ok = all(v["pass"] for v in pre.values())
        out["all_preconditions_pass"] = out["all_preconditions_pass"] and ok
        we = warm_end.get(cond) or {}
        rates = we.get("rates") or []
        out["conditions"][cond] = {"started": True, "arm": ev.get("arm"), "env": ev.get("env"), "preconditions": pre, "preconditions_pass": ok, "n": len(meas),
                                   "prompt_tokens_p50": pt, "ttft_ms_p50": med([r.get("ttft_ms") for r in meas]),
                                   "generation_tps_p50": med([r.get("generation_tps") for r in meas]), "completion_tokens_p50": med([r.get("completion_tokens") for r in meas]),
                                   "finish_reason": {k: sum(1 for r in meas if r.get("finish_reason") == k) for k in sorted({str(r.get("finish_reason")) for r in meas})},
                                   "gpu_ready_mib": (ev.get("gpu_ready") or {}).get("used_mib"), "kv_tokens": (ev.get("cache_config") or {}).get("kv_tokens"),
                                   "seconds_to_ready": ev.get("seconds_to_ready"),
                                   "warmup": {"n": len(warm), "seconds": we.get("warmup_seconds"), "stabilized": we.get("stabilized"),
                                              "first_rate": rates[0] if rates else None, "last_rate": rates[-1] if rates else None,
                                              "first_ttft_ms": warm[0].get("ttft_ms") if warm else None}}
    c = out["conditions"]
    d, t = c.get("a1_16k_default"), c.get("a1_16k_capture")
    if d and t and d.get("preconditions_pass") and t.get("preconditions_pass") and d.get("generation_tps_p50") and t.get("generation_tps_p50"):
        ratio = t["generation_tps_p50"] / d["generation_tps_p50"]
        out["capture_attribution"] = {"default_tps": d["generation_tps_p50"], "capture_tps": t["generation_tps_p50"], "ratio": round(ratio, 3),
                                      "verdict": "measured: the capture limit explains the step" if ratio >= 1.40 else ("withdrawn: the capture limit does not explain it" if ratio <= 1.10 else "partial: the capture limit explains part of the step")}
    elif t is not None:
        out["capture_attribution"] = {"verdict": "unverified: " + ("the capture condition did not start" if not t.get("started") else "preconditions failed (see P3: the setting may not have reached the engine)")}
    q = [c.get(k) for k in ("a1_4k_default", "a1_4k_eager", "a1_16k_default", "a1_16k_eager")]
    if all(x is not None for x in q):
        if all(x.get("preconditions_pass") and x.get("generation_tps_p50") for x in q):
            r4 = q[1]["generation_tps_p50"] / q[0]["generation_tps_p50"]; r16 = q[3]["generation_tps_p50"] / q[2]["generation_tps_p50"]
            v = ("measured: turning CUDA graphs off reproduces the step at 4k and changes nothing at 16k" if r4 <= 0.75 and 0.90 <= r16 <= 1.10
                 else "withdrawn: CUDA graphs do not explain the step" if r4 >= 0.90 else "partial")
            out["eager_attribution"] = {"tps": {k: x["generation_tps_p50"] for k, x in zip(("4k_default", "4k_eager", "16k_default", "16k_eager"), q)},
                                        "r4_eager_over_default": round(r4, 3), "r16_eager_over_default": round(r16, 3),
                                        "eager_4k_over_default_16k": round(q[1]["generation_tps_p50"] / q[2]["generation_tps_p50"], 3), "verdict": v}
        else:
            out["eager_attribution"] = {"verdict": "unverified: a condition of the 2x2 failed its preconditions"}
    if refs:
        out["vs_reference"] = {}
        for cond, arm in (("a1_120k", "A1"), ("a2_120k", "A2")):
            x = c.get(cond)
            # per arm, the reference with the most depths for that arm (A1: the main run; A2: the addendum, whose A2 rows are warmed)
            depths = max((((r.get("per_arm") or {}).get(arm) or {}).get("depths") or {} for r in refs), key=len)
            if x and x.get("started") and depths:
                lo = min(depths, key=lambda k: int(k)); hi = max(depths, key=lambda k: int(k))
                out["vs_reference"][cond] = {"reference_shallowest": {"depth": lo, "generation_tps_p50": depths[lo].get("generation_tps_p50"), "ttft_ms_p50": depths[lo].get("ttft_ms_p50")},
                                             "reference_deepest": {"depth": hi, "generation_tps_p50": depths[hi].get("generation_tps_p50"), "ttft_ms_p50": depths[hi].get("ttft_ms_p50")},
                                             "generation_x_of_shallowest": round(x["generation_tps_p50"] / depths[lo]["generation_tps_p50"], 3) if x.get("generation_tps_p50") and depths[lo].get("generation_tps_p50") else None,
                                             "ttft_x_of_shallowest": round(x["ttft_ms_p50"] / depths[lo]["ttft_ms_p50"], 2) if x.get("ttft_ms_p50") and depths[lo].get("ttft_ms_p50") else None}
    return out


def self_test():
    def ev(cond, target, cap=None, expect=None):
        return {"kind": "condition_start", "condition": cond, "arm": "A1", "target": target, "gpu_ready": {"used_mib": 1}, "cache_config": {"kv_tokens": 1},
                "engine_config_from_log": {"max_seq_len_to_capture": cap or [8192]}, "expect_capture": expect}

    def rows(cond, pt, tps, n=5):
        return [{"condition": cond, "i": i, "warmup": False, "http_status": 200, "usage_present": True, "prompt_tokens": pt, "generation_tps": tps, "ttft_ms": 100,
                 "completion_tokens": 256, "finish_reason": "length", "docker_ps_before": ["c"]} for i in range(n)]
    E = [ev("a1_16k_default", 16384), ev("a1_16k_capture", 16384, [32768], 32768)]
    R = rows("a1_16k_default", 14200, 45.0) + rows("a1_16k_capture", 14200, 71.0)
    a = analyse(R, E)
    cases = [("both conditions pass", a["all_preconditions_pass"]),
             ("ratio 71/45 -> measured", a["capture_attribution"]["verdict"].startswith("measured"))]
    R2 = rows("a1_16k_default", 14200, 45.0) + rows("a1_16k_capture", 14200, 46.0)
    cases.append(("ratio 46/45 -> withdrawn", analyse(R2, E)["capture_attribution"]["verdict"].startswith("withdrawn")))
    R3 = rows("a1_16k_default", 14200, 45.0) + rows("a1_16k_capture", 14200, 56.0)
    cases.append(("ratio 56/45 -> partial", analyse(R3, E)["capture_attribution"]["verdict"].startswith("partial")))
    E_nocap = [E[0], ev("a1_16k_capture", 16384, [8192], 32768)]
    a4 = analyse(R, E_nocap)
    cases.append(("capture not in engine config -> P3 fails, unverified", not a4["conditions"]["a1_16k_capture"]["preconditions_pass"] and a4["capture_attribution"]["verdict"].startswith("unverified")))
    E_fail = [E[0], {"kind": "condition_failed", "condition": "a1_16k_capture", "arm": "A1", "reason": "not ready"}]
    a5 = analyse(rows("a1_16k_default", 14200, 45.0), E_fail)
    cases.append(("capture condition failed to start -> unverified", a5["capture_attribution"]["verdict"].startswith("unverified")))
    R6 = rows("a1_16k_default", 8000, 45.0) + rows("a1_16k_capture", 14200, 71.0)
    cases.append(("depth off by > 25% -> P2 fails", not analyse(R6, E)["conditions"]["a1_16k_default"]["preconditions"]["P2_depth_within_25pct"]["pass"]))
    R7 = rows("a1_16k_default", 14200, 45.0) + rows("a1_16k_capture", 14200, 71.0); R7[0]["http_status"] = 500
    cases.append(("HTTP 500 -> P1 fails", not analyse(R7, E)["conditions"]["a1_16k_default"]["preconditions_pass"]))
    R8 = R + [dict(rows("a1_16k_default", 14200, 5.0, 1)[0], warmup=True)]
    cases.append(("warm-up row excluded from median", analyse(R8, E)["conditions"]["a1_16k_default"]["generation_tps_p50"] == 45.0))
    def ev2(cond, target, eager):
        return {"kind": "condition_start", "condition": cond, "arm": "A1", "target": target, "gpu_ready": {"used_mib": 1}, "cache_config": {"kv_tokens": 1},
                "engine_config_from_log": {"max_seq_len_to_capture": [8192], "enforce_eager": [eager, eager]}, "expect_eager": eager}
    E2 = [ev2("a1_4k_default", 4096, False), ev2("a1_4k_eager", 4096, True), ev2("a1_16k_default", 16384, False), ev2("a1_16k_eager", 16384, True)]
    R2x2 = rows("a1_4k_default", 3800, 72.0) + rows("a1_4k_eager", 3800, 46.0) + rows("a1_16k_default", 14200, 45.0) + rows("a1_16k_eager", 14200, 44.5)
    cases.append(("2x2: eager 4k drops, 16k unchanged -> measured", analyse(R2x2, E2)["eager_attribution"]["verdict"].startswith("measured")))
    R2x2b = rows("a1_4k_default", 3800, 72.0) + rows("a1_4k_eager", 3800, 70.0) + rows("a1_16k_default", 14200, 45.0) + rows("a1_16k_eager", 14200, 44.5)
    cases.append(("2x2: eager 4k unchanged -> withdrawn", analyse(R2x2b, E2)["eager_attribution"]["verdict"].startswith("withdrawn")))
    E2bad = [E2[0], dict(E2[1], engine_config_from_log={"max_seq_len_to_capture": [8192], "enforce_eager": [False]})] + E2[2:]
    cases.append(("2x2: eager not in engine config -> unverified", analyse(R2x2, E2bad)["eager_attribution"]["verdict"].startswith("unverified")))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{sum(ok for _, ok in cases)}/{len(cases)} pass")
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    ref = [json.load(open(sys.argv[i + 1], encoding="utf-8")) for i, x in enumerate(sys.argv) if x == "--ref"] or None
    rows = [json.loads(l) for l in open(os.path.join(d, "requests.jsonl"), encoding="utf-8")] if os.path.exists(os.path.join(d, "requests.jsonl")) else []
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf-8")]
    a = analyse(rows, events, ref)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    for k, v in a["conditions"].items():
        print(k, json.dumps({x: v.get(x) for x in ("started", "preconditions_pass", "prompt_tokens_p50", "ttft_ms_p50", "generation_tps_p50", "kv_tokens", "reading")}, ensure_ascii=False))
    print("attribution", a.get("capture_attribution")); print("vs_reference", json.dumps(a.get("vs_reference"))[:400])
    return 0 if a["all_preconditions_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
