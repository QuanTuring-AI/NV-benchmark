#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q2 + Q4 · analysis. Rules frozen in prediction_p62_levels.json.

Q2: P59's analysis program (vol1a-revisit/scripts/p59_analyze.py, imported unchanged) on this run's levels.jsonl and
events.jsonl: the same gates (residency, health >= 0.40), the same container checks (isolation, prefix-cache detector),
calibration on profile C, per-level usability, SLO cells and crossing rule ("between X and Y", never interpolated),
over levels 1, 2, 4 and 8 (O-Q4 also 9, 12, 16). Profile R was not run, so every R entry is null by construction.
Anchors: c=1 and c=8 of each arm beside P59's value for the same cell (ratio this run / P59); a ratio outside 0.85-1.15
is flagged "anchor moved" and printed, not corrected.
Q4 (O-Q4 only): per level, total output tok/s, the most requests decoding at once and the share of time with k decoding
(concurrency.jsonl), and the `ollama ps` samples (processor column; any sample not "100% GPU" is counted).
  flat_to_8   total at c=4 and at c=8 each between 0.80 and 1.25 x total at c=1 (P59's c=8 = c=1 reproduced)
  step        the first level L of 9, 12, 16 whose total >= 1.5 x total at c=8 -> "between <previous level> and L"
  (both computed only on usable levels; a missing or unusable level -> that verdict null)
usage: p62_levels_analyze.py <run_dir> <p59_analysis.json> | --self-test
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p59_analyze as A  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ANCHOR = (0.85, 1.15)
FLAT = (0.80, 1.25)
STEP = 1.5
Q4_LEVELS = [9, 12, 16]


def q4(table, conc, ps_rows):
    t = table.get(("O-Q4", "C", "main"), {})
    tot = {n: (c["total_tps"] if c["usable"] else None) for n, c in t.items()}
    flat = None
    if all(tot.get(n) for n in (1, 4, 8)):
        r4, r8 = tot[4] / tot[1], tot[8] / tot[1]
        flat = {"ratio_c4_over_c1": round(r4, 3), "ratio_c8_over_c1": round(r8, 3), "flat": FLAT[0] <= r4 <= FLAT[1] and FLAT[0] <= r8 <= FLAT[1]}
    step = None
    if tot.get(8) and all(n in tot for n in Q4_LEVELS):
        prev = 8; step = {"found": None, "ratios_over_c8": {n: (round(tot[n] / tot[8], 3) if tot[n] else None) for n in Q4_LEVELS}}
        for n in Q4_LEVELS:
            if tot[n] is None:
                step = None; break
            if tot[n] >= STEP * tot[8]:
                step["found"] = f"between {prev} and {n}"; break
            prev = n
    procs = [r.get("ollama_ps", "") for r in ps_rows]
    return {"total_tps_by_level": {n: tot[n] for n in sorted(tot)},
            "decoding_at_once": {c["concurrency"]: {k: c.get(k) for k in ("max_decoding_at_once", "time_share_by_decoding")} for c in conc if c.get("arm") == "O-Q4"},
            "flat_to_8": flat, "step": step,
            "ollama_ps_samples": {"n": len(procs), "not_100pct_gpu": sum(1 for p in procs if p and "100% GPU" not in p), "empty": sum(1 for p in procs if not p)}}


def analyse(levels, events, conc, ps_rows, p59):
    out = A.analyse(levels, events)
    table = {}
    for k, v in out["levels"].items():
        arm, prof, cont = k.split("|"); table[(arm, prof, cont)] = v
    anchors = {}
    for (arm, prof, cont), v in table.items():
        if prof != "C" or cont != "main":
            continue
        old = (p59.get("levels") or {}).get(f"{arm}|C|main") or {}
        for n in (1, 8):
            new, o = v.get(n), old.get(str(n)) or old.get(n)
            if new and o and new.get("total_tps") and o.get("total_tps"):
                r = new["total_tps"] / o["total_tps"]
                anchors[f"{arm}|c{n}"] = {"this_run": new["total_tps"], "p59": o["total_tps"], "ratio": round(r, 3), "moved": not (ANCHOR[0] <= r <= ANCHOR[1])}
            else:
                anchors[f"{arm}|c{n}"] = None
    out["anchors_vs_p59"] = anchors
    out["q4"] = q4(table, conc, ps_rows)
    out["crossings"] = {k: v for k, v in out["crossings"].items() if "|R|" not in k}
    return out


def self_test():
    def lv(arm, n, tot, per, itl=10.0):
        return {"arm": arm, "profile": "C", "container": "main", "concurrency": n, "rc": 0, "engine_dead": False,
                "summary": {"output_token_throughput": {"avg": tot}, "output_token_throughput_per_user": {"avg": per},
                            "time_to_first_token": {"p50": 30.0, "p99": 100.0}, "inter_token_latency": {"p50": itl, "p99": itl}, "error_request_count": {"avg": 0}},
                "checks": {"truncated_requests": 0, "server_over_client_prompt_min": None, "requests_without_server_prompt_count": 5,
                           "completion_tokens_p50": 200, "completion_below_90pct_of_target": False}}
    good = {"isolation": {"pass": True}, "prefix_detector": {"pass": True, "positive_control_same_prompt_twice": {"fired": True}}}
    ev = [{"kind": "container_start", "arm": "O-Q4", "container": "main", "load": {"full_gpu": True}, **good},
          {"kind": "container_start", "arm": "N-BF16", "container": "main", "captured_graph_sizes": {"x": 1}, **good},
          {"kind": "profile_start", "arm": "O-Q4", "profile": "C", "container": "main", "calibration": {"ttft_ms_p50": 30.0, "itl_ms_p50": 5.8}},
          {"kind": "profile_start", "arm": "N-BF16", "profile": "C", "container": "main", "calibration": {"ttft_ms_p50": 30.0, "itl_ms_p50": 11.4}}]
    oq = {1: 172, 2: 174, 4: 176, 8: 175, 9: 420, 12: 520, 16: 600}
    nb = {1: 87, 2: 170, 4: 330, 8: 607}
    L = [lv("O-Q4", n, t, t / n, itl=5.8 if n == 1 else 20.0) for n, t in oq.items()] + [lv("N-BF16", n, t, t / n, itl=11.4 if n == 1 else 12.0) for n, t in nb.items()]
    p59 = {"levels": {"O-Q4|C|main": {"1": {"total_tps": 172}, "8": {"total_tps": 175}}, "N-BF16|C|main": {"1": {"total_tps": 87}, "8": {"total_tps": 400}}}}
    x = analyse(L, ev, [], [{"ollama_ps": "llama3.1:8b ... 100% GPU"}, {"ollama_ps": "llama3.1:8b 20%/80% CPU/GPU"}], p59)
    cases = [("crossing total between 2 and 4 (N-BF16 170 < 174, 330 > 176)", x["crossings"]["N-BF16 vs O-Q4|C|total_tps"]["crossings"] == ["between 2 and 4: N-BF16 ahead from 4"]),
             ("flat_to_8 true", x["q4"]["flat_to_8"]["flat"] is True),
             ("step between 8 and 9", x["q4"]["step"]["found"] == "between 8 and 9"),
             ("anchor moved flagged (607 vs 400)", x["anchors_vs_p59"]["N-BF16|c8"]["moved"] is True and x["anchors_vs_p59"]["O-Q4|c1"]["moved"] is False),
             ("ollama ps non-GPU sample counted", x["q4"]["ollama_ps_samples"]["not_100pct_gpu"] == 1),
             ("R crossings removed", not any("|R|" in k for k in x["crossings"]))]
    L2 = [dict(r, summary=dict(r["summary"], output_token_throughput={"avg": 250})) if r["arm"] == "O-Q4" and r["concurrency"] == 12 else r for r in L]
    L2 = [dict(r, summary=dict(r["summary"], output_token_throughput={"avg": 200})) if r["arm"] == "O-Q4" and r["concurrency"] == 9 else r for r in L2]
    y = analyse(L2, ev, [], [], p59)
    cases.append(("step moves to between 12 and 16 when 9 and 12 stay low", y["q4"]["step"]["found"] == "between 12 and 16"))
    L3 = [dict(r, summary=dict(r["summary"], output_token_throughput={"avg": 400})) if r["arm"] == "O-Q4" and r["concurrency"] == 8 else r for r in L]
    z = analyse(L3, ev, [], [], p59)
    cases.append(("flat_to_8 false when c=8 doubles", z["q4"]["flat_to_8"]["flat"] is False))
    L4 = [dict(r, summary=dict(r["summary"], error_request_count={"avg": 2})) if r["arm"] == "O-Q4" and r["concurrency"] == 9 else r for r in L]
    cases.append(("unusable c=9 -> step null", analyse(L4, ev, [], [], p59)["q4"]["step"] is None))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d, p59p = sys.argv[1], sys.argv[2]
    rd = lambda f: [json.loads(l) for l in open(os.path.join(d, f), encoding="utf-8")] if os.path.exists(os.path.join(d, f)) else []
    ps_rows = rd("ollama_ps_O-Q4.jsonl")
    a = analyse(rd("levels.jsonl"), rd("events.jsonl"), rd("concurrency.jsonl"), ps_rows, json.load(open(p59p, encoding="utf-8")))
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    for arm, v in a["arms"].items():
        print(arm, "usable", v["usable"], "health", v["gate_health"]["share_of_peak"], "cal C", v["calibration"]["C"]["pass"])
    for k, v in a["crossings"].items():
        print(k, v and v["crossings"])
    print("anchors", {k: v and (v["ratio"], v["moved"]) for k, v in a["anchors_vs_p59"].items()})
    print("q4", json.dumps({k: a["q4"][k] for k in ("total_tps_by_level", "flat_to_8", "step", "ollama_ps_samples")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
