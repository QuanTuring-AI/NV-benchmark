#!/usr/bin/env python3
"""Vol.2 speed table · analysis. Rules frozen in prediction_p50_speed.json.

Preconditions (any failure -> every conclusion field is null):
  P1  no request errors, every request HTTP 200, usage present on every request
  P2  every row's served_model is the model of its arm, and exactly one container was up at each request
  P3  each arm has exactly one row per question of the sample (50 each, 100 in total); blocks alternate A1, A2, A1, A2
Arm-health gate (before any ratio is reported):
  generation rate = completion_tokens / (total_latency - ttft) per request; median per arm
  effective bandwidth = median generation rate x bytes read per token (passed in with --bytes, from the pre-registration)
  share of the card's peak (1,792 GB/s); an arm below 10% fails the gate -> conclusions carry "validity": null and no ratio
Conclusions: per-arm ttft, total latency, tps (Vol.1 word formula), tps (usage), generation rate, completion tokens,
finish_reason counts, per-block splits; A2/A1 ratio of means with 95% bootstrap CI over questions (2000 resamples,
seed 20260921) and median per-question ratio, for generation rate and tps_usage.
usage: p50_speed_analyze.py <run_dir> --bytes A1=<int>,A2=<int> | --self-test
"""
import json, os, random, statistics as st, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PEAK_GB_S = 1792.0
GATE_SHARE = 0.10
MODEL_OF = {"A1": "nvidia/nvidia-nemotron-nano-9b-v2", "A2": "nvidia/nemotron-3-nano"}
BOOT, SEED = 2000, 20260921


def gen_rate(r):
    c, t, f = r.get("completion_tokens"), r.get("total_latency_ms"), r.get("ttft_ms")
    if not all(isinstance(x, (int, float)) for x in (c, t, f)) or t <= f or c <= 0:
        return None
    return c / ((t - f) / 1000)


def tps_usage(r):
    c, t = r.get("completion_tokens"), r.get("total_latency_ms")
    return c / (t / 1000) if isinstance(c, int) and isinstance(t, (int, float)) and t > 0 else None


def desc(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "avg": round(sum(xs) / len(xs), 2), "p50": round(st.median(xs), 2),
            "p95": round(xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))], 2), "min": round(xs[0], 2), "max": round(xs[-1], 2)}


def paired_ratio(a_rows, b_rows, f):
    a = {r["question_id"]: f(r) for r in a_rows}; b = {r["question_id"]: f(r) for r in b_rows}
    qs = sorted(q for q in a if q in b and a[q] is not None and b[q] is not None)
    if not qs:
        return {"n": 0}
    rng = random.Random(SEED); boots = []
    for _ in range(BOOT):
        s = [rng.choice(qs) for _ in qs]
        boots.append(sum(b[q] for q in s) / sum(a[q] for q in s))
    boots.sort()
    return {"n": len(qs), "ratio_of_means": round(sum(b[q] for q in qs) / sum(a[q] for q in qs), 4),
            "ci95": [round(boots[int(0.025 * BOOT)], 4), round(boots[int(0.975 * BOOT) - 1], 4)],
            "median_per_question_ratio": round(st.median(b[q] / a[q] for q in qs), 4)}


def analyse(rows, bytes_per_token, n_questions=50):
    by = {"A1": [r for r in rows if r.get("arm") == "A1"], "A2": [r for r in rows if r.get("arm") == "A2"]}
    errs = [r for r in rows if r.get("error") or r.get("http_status") != 200 or not r.get("usage_present")]
    bad2 = [(r.get("arm"), r.get("question_id")) for r in rows
            if r.get("served_model") != MODEL_OF.get(r.get("arm")) or len(r.get("docker_ps_before") or []) != 1]
    counts = {a: sorted(r["question_id"] for r in v) for a, v in by.items()}
    complete = all(len(v) == n_questions and len(set(v)) == n_questions for v in counts.values()) and counts["A1"] == counts["A2"]
    blocks = [r.get("block") for r in rows]
    order_ok = all((r.get("block") % 2 == 0) == (r.get("arm") == "A1") for r in rows) if rows else False
    pre = {"P1_no_errors_usage_present": {"violations": len(errs), "pass": not errs},
           "P2_arm_matches_container": {"violations": len(bad2), "first": bad2[:5], "pass": not bad2},
           "P3_complete_and_alternating": {"rows_per_arm": {a: len(v) for a, v in by.items()}, "blocks": sorted(set(blocks)),
                                           "pass": complete and order_ok}}
    out = {"preconditions": pre, "preconditions_pass": all(v["pass"] for v in pre.values()), "rows": len(rows), "conclusions": None}
    if not out["preconditions_pass"]:
        return out
    health = {}
    for a, v in by.items():
        g = st.median(x for x in (gen_rate(r) for r in v) if x is not None)
        bpt = (bytes_per_token or {}).get(a)
        bw = g * bpt / 1e9 if bpt else None
        health[a] = {"generation_rate_p50": round(g, 2), "bytes_per_token": bpt, "effective_bandwidth_gb_s": round(bw, 1) if bw else None,
                     "share_of_peak": round(bw / PEAK_GB_S, 4) if bw else None,
                     "pass": (bw / PEAK_GB_S >= GATE_SHARE) if bw else None}
    gate_pass = all(h["pass"] is True for h in health.values())
    per = {}
    for a, v in by.items():
        per[a] = {"ttft_ms": desc(r.get("ttft_ms") for r in v), "total_latency_ms": desc(r.get("total_latency_ms") for r in v),
                  "tps_vol1_words": desc(r.get("tps") for r in v), "tps_usage": desc(tps_usage(r) for r in v),
                  "generation_rate": desc(gen_rate(r) for r in v), "completion_tokens": desc(r.get("completion_tokens") for r in v),
                  "prompt_tokens": desc(r.get("prompt_tokens") for r in v),
                  "finish_reason": {k: sum(1 for r in v if r.get("finish_reason") == k) for k in sorted({r.get("finish_reason") for r in v})},
                  "by_block": {b: {"generation_rate_p50": desc(gen_rate(r) for r in v if r.get("block") == b)["p50"],
                                   "ttft_p50": desc(r.get("ttft_ms") for r in v if r.get("block") == b)["p50"]}
                               for b in sorted({r.get("block") for r in v})}}
    con = {"arm_health": health, "validity": gate_pass, "per_arm": per}
    if gate_pass:
        con["A2_over_A1"] = {"generation_rate": paired_ratio(by["A1"], by["A2"], gen_rate),
                             "tps_usage": paired_ratio(by["A1"], by["A2"], tps_usage),
                             "ttft_ms": paired_ratio(by["A1"], by["A2"], lambda r: r.get("ttft_ms"))}
    else:
        con["A2_over_A1"] = None
    con["reading"] = ("two deployment options, each in its own NIM image and version, each at the only precision that fits this "
                      "card; not a single-variable comparison. Ratios are ratio of means over questions with a CI over questions.")
    out["conclusions"] = con
    return out


def mk(arm, qid, block, ttft=50.0, total=6050.0, ct=480, err=None, status=200, usage=True, model=None, docker=None, fr="length"):
    return {"arm": arm, "question_id": qid, "block": block, "ttft_ms": ttft, "total_latency_ms": total, "tokens": ct - 10,
            "tps": round((ct - 10) / total * 1000, 1), "completion_tokens": ct, "prompt_tokens": 30, "usage_present": usage,
            "finish_reason": fr, "http_status": status, "error": err, "served_model": model or MODEL_OF[arm],
            "docker_ps_before": docker if docker is not None else ["c"]}


def base_rows():
    rows = []
    for i in range(50):
        b = 0 if i < 25 else 2
        rows.append(mk("A1", f"q{i:02d}", b, total=6050.0, ct=480))          # gen 480/6 s = 80 tok/s
        rows.append(mk("A2", f"q{i:02d}", b + 1, total=2050.0, ct=480))      # gen 480/2 s = 240 tok/s
    return rows


BYTES = {"A1": 17_776_492_512, "A2": 4_000_000_000}


def self_test():
    cases = []
    a = analyse(base_rows(), BYTES); c = a["conclusions"]
    cases.append(("clean run passes", a["preconditions_pass"]))
    cases.append(("A1 generation rate p50 = 80", c["per_arm"]["A1"]["generation_rate"]["p50"] == 80.0))
    cases.append(("A1 health share = 80 x 17.78 GB / 1792 GB/s = 0.7936", abs(c["arm_health"]["A1"]["share_of_peak"] - 0.7936) < 0.001))
    cases.append(("gate passes", c["validity"] is True))
    cases.append(("A2/A1 generation ratio = 3.0", c["A2_over_A1"]["generation_rate"]["ratio_of_means"] == 3.0))
    low = analyse(base_rows(), {"A1": 17_776_492_512, "A2": 500_000_000})["conclusions"]   # 240 x 0.5 GB = 120 GB/s = 6.7%
    cases.append(("A2 share 6.7% -> gate fails, no ratio", low["validity"] is False and low["A2_over_A1"] is None))
    rows = base_rows(); rows[3] = mk("A2", "q01", 1, usage=False)
    cases.append(("usage missing -> null", analyse(rows, BYTES)["conclusions"] is None))
    rows = base_rows(); rows[3] = mk("A2", "q01", 1, model=MODEL_OF["A1"])
    cases.append(("served model of the other arm -> null", analyse(rows, BYTES)["conclusions"] is None))
    rows = base_rows(); rows[3] = mk("A2", "q01", 1, docker=["c", "d"])
    cases.append(("two containers up -> null", analyse(rows, BYTES)["conclusions"] is None))
    rows = base_rows()[:-1]
    cases.append(("99 rows -> null", analyse(rows, BYTES)["conclusions"] is None))
    rows = base_rows(); rows[0]["block"] = 1
    cases.append(("A1 row in an A2 block -> null", analyse(rows, BYTES)["conclusions"] is None))
    rows = base_rows(); rows[0] = mk("A1", "q00", 0, status=500)
    cases.append(("HTTP 500 -> null", analyse(rows, BYTES)["conclusions"] is None))
    cases.append(("no bytes given -> gate null, ratio withheld", analyse(base_rows(), None)["conclusions"]["A2_over_A1"] is None))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{sum(ok for _, ok in cases)}/{len(cases)} pass")
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    bpt = None
    if "--bytes" in sys.argv:
        bpt = {k: int(v) for k, v in (x.split("=") for x in sys.argv[sys.argv.index("--bytes") + 1].split(","))}
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 50
    rows = [json.loads(l) for l in open(os.path.join(d, "requests.jsonl"), encoding="utf-8")]
    a = analyse(rows, bpt, n)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(json.dumps(a["preconditions"], ensure_ascii=False))
    if a["conclusions"]:
        print("health", json.dumps(a["conclusions"]["arm_health"])); print("A2/A1", json.dumps(a["conclusions"]["A2_over_A1"]))
    return 0 if a["preconditions_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
