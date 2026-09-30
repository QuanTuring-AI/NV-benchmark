#!/usr/bin/env python3
"""Vol.2 (and Vol.1 G1) · P78 · judge every pre-registered prediction from the result files, and list every cell's
wall-clock duration. Written after the run (2026-09-30); the rules it applies were frozen at 21:58 on 2026-09-29 in the
five prediction_p78_*.json files. Where a prediction's text leaves a tie-break open, the rule used here is named in the
output as "added after the run".

Reads: vol1-nim/results/p78_fp8_clean/ (G1), vol2-nemotron/results/p78_quality/ (G2, G3, G4 quality arms),
p78_nim_vs_vllm/ (G4), p78_clean_rerun/ (G6, stopped at 08:56, not judged: P79 section 4), p78_n2_upstream/ (G5).
Writes analysis.json into each results directory it judges, and durations.json into vol2-nemotron/results/p78_quality/
(the cells of the published runs). The stopped G6 levels and the harness tests, which are not published, go to
durations_local.json under that directory's logs/ (kept on the machine).
Events are read from events.jsonl when present, else from events_public.jsonl (the published copy: desktop process
lists reduced to counts, which no rule here reads), so the published files alone reproduce analysis.json.
usage: p78_analyze.py [<root>] | self_test      (<root>: a directory holding the same relative layout; default: the repository)
"""
import ast, datetime as dt, glob, json, math, os, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
if len(sys.argv) > 1 and sys.argv[1] != "self_test":
    REPO = os.path.abspath(sys.argv[1])
R1 = os.path.join(REPO, "vol1-nim", "results", "p78_fp8_clean")
RQ = os.path.join(REPO, "vol2-nemotron", "results", "p78_quality")
RG4 = os.path.join(REPO, "vol2-nemotron", "results", "p78_nim_vs_vllm")
RG6 = os.path.join(REPO, "vol2-nemotron", "results", "p78_clean_rerun")
RG5 = os.path.join(REPO, "vol2-nemotron", "results", "p78_n2_upstream")


def jl(path):
    if not os.path.exists(path) and path.endswith("events.jsonl"):
        path = path[:-len("events.jsonl")] + "events_public.jsonl"
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()] if os.path.exists(path) else []


def _node(n):
    """A Python-literal syntax tree (dicts, lists, tuples, strings, numbers, True/False/None) to its value; anything
    else raises. Some harnesses stored dicts with str(); this reads them back without evaluating code."""
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.Dict):
        return {_node(k): _node(v) for k, v in zip(n.keys, n.values)}
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_node(x) for x in n.elts]
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
        return -_node(n.operand)
    raise ValueError(type(n).__name__)


def lit(v):
    if isinstance(v, str) and v[:1] in "{[":
        try:
            return _node(ast.parse(v, mode="eval").body)
        except Exception:  # noqa: BLE001
            return v
    return v


def ts(s):
    s = s.strip()
    if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
        s = s[:-2] + ":" + s[-2:]
    return dt.datetime.fromisoformat(s)


def secs(a, b):
    return round((ts(b) - ts(a)).total_seconds(), 1)


def pct(x):
    return round(100.0 * x, 2)


def paired(a, b):
    """b - a over the doc_ids both hold, in percentage points, with a 95% CI (mean +- 1.96 sd / sqrt n)."""
    ids = sorted(set(a) & set(b))
    d = [b[i] - a[i] for i in ids]
    n = len(d)
    if n < 2:
        return {"n": n}
    m = st.mean(d); sd = st.stdev(d); h = 1.96 * sd / math.sqrt(n)
    return {"n": n, "diff_pp": pct(m), "ci95_pp": [pct(m - h), pct(m + h)], "flips": sum(1 for x in d if x != 0),
            "b_better": sum(1 for x in d if x > 0), "a_better": sum(1 for x in d if x < 0)}


def within(x, lo, hi):
    return x is not None and lo <= x <= hi


# ---------------------------------------------------------------- the rules (small functions so the self-test can break them)
def rule_range(value, lo, hi):
    return "pass" if within(value, lo, hi) else "fail"


def rule_self_consistency(ci):
    """prediction_p78_quality gates_and_branches.self_consistency: the CI inside [-2, +2] pp keeps that model's
    equivalence verdicts; otherwise they are null."""
    return ci is not None and -2.0 <= ci[0] and ci[1] <= 2.0


def rule_reasoning_off(med_off, med_on):
    """reasoning_really_off: median completion tokens off <= 50% of on, else that model's off cells are null."""
    return med_on > 0 and med_off <= 0.5 * med_on


def rule_positive_ci(ci):
    """Q2 GSM8K: > 0 with the 95% CI above 0."""
    return "pass" if ci and ci[0] > 0 else "fail"


def rule_interval_ci(point, ci, lo, hi):
    """Q2 MMLU 'within [-2, +6] pp' / C1 'within +-3 pp'. Tie-break added after the run: pass if the whole CI is inside,
    fail if the point estimate is outside, otherwise not shown (inconclusive)."""
    if ci and lo <= ci[0] and ci[1] <= hi:
        return "pass"
    if not within(point, lo, hi):
        return "fail"
    return "inconclusive"


def rule_p3(identical, self_repeat_a, self_repeat_b):
    """G4 P3: >= 45/50 identical, interpreted only if each arm repeats itself on >= 9 of 10."""
    if self_repeat_a < 9 or self_repeat_b < 9:
        return "not interpretable"
    return "pass" if identical >= 45 else "fail"


# ---------------------------------------------------------------- G1
def g1():
    pred = json.load(open(os.path.join(R1, "prediction_p78_fp8.json"), encoding="utf-8"))
    ev = jl(os.path.join(R1, "events.jsonl")); lv = [r for r in jl(os.path.join(R1, "levels.jsonl")) if not r.get("warmup")]
    tps = {(r["arm"], r["concurrency"]): (r.get("summary") or {}).get("output_token_throughput", {}).get("avg") for r in lv}
    g8 = [e["pass"] for e in ev if e["kind"] == "g8"]
    det = {}
    for e in ev:
        if e["kind"] == "container_start":
            d = lit(e.get("prefix_detector"))
            det[e["arm"]] = {"threshold": d.get("threshold"), "r_s": (d.get("positive_control_same_prompt_twice") or {}).get("ratio"),
                             "pass": d.get("pass")} if isinstance(d, dict) else d
    fp8, bf16 = tps.get(("N-FP8", 128)), tps.get(("N-BF16", 128))
    den = pred["denominators"]
    r1 = fp8 / den["O-Q4_at_128_tok_s"] if fp8 else None
    r2 = fp8 / bf16 if fp8 and bf16 else None
    r3 = bf16 / den["N-BF16_at_128_P70_tok_s"] - 1 if bf16 else None
    arms_null = [a for a, d in det.items() if isinstance(d, dict) and not d.get("pass")]
    verdict = lambda x: "null (detector)" if arms_null else x  # noqa: E731
    out = {"g8_all_pass": all(g8), "g8_cells": len(g8), "detector": det,
           "tok_s": {f"{a}|{c}": round(v, 1) for (a, c), v in tps.items() if v},
           "R1": {"value": round(r1, 3) if r1 else None, "pass_if": "[10.5, 13.5]", "verdict": verdict(rule_range(r1, 10.5, 13.5))},
           "R2": {"value": round(r2, 3) if r2 else None, "pass_if": "[1.45, 1.75]", "verdict": verdict(rule_range(r2, 1.45, 1.75))},
           "R3": {"value_rel": round(r3, 4) if r3 is not None else None, "pass_if": "within +-5% of 6043.3", "verdict": verdict(rule_range(r3, -0.05, 0.05))}}
    json.dump(out, open(os.path.join(R1, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return out


# ---------------------------------------------------------------- G2 / G3 / G4 quality arms
def quality():
    items = jl(os.path.join(RQ, "items.jsonl")); ev = jl(os.path.join(RQ, "events.jsonl"))
    cells = {}
    for it in items:
        cells.setdefault((it["arm"], it["cell"]), []).append(it)
    ends = {(e["arm"], e["cell"]): e for e in ev if e["kind"] == "cell_end"}
    g8 = {(e["arm"], e["cell"]): e["pass"] for e in ev if e["kind"] == "g8"}
    health = {}
    for e in ev:
        if e["kind"] == "health":
            health.setdefault(e["arm"], []).append({"rate_median": e.get("rate_median"), "share_of_peak": e.get("share_of_peak"), "pass": e.get("pass"), "at": e["at"]})
    per = {}
    for (arm, cell), its in sorted(cells.items()):
        n = len(its); ce = ends.get((arm, cell), {}); sm = ce.get("summary") or {}
        tok = [x.get("completion_tokens") or 0 for x in its]
        per[f"{arm}|{cell}"] = {"items": n, "accuracy_pct": pct(sum(x["correct"] for x in its) / n), "cap_share_pct": pct(sum(bool(x["hit_cap"]) for x in its) / n),
                                "no_answer": sum(x["no_answer"] for x in its), "tokens_median": st.median(tok), "seconds_per_item_median": round(st.median(x["seconds"] for x in its), 2),
                                "http_400": sm.get("http_400"), "engine_exits": sm.get("engine_exits"), "hung_chunks": sm.get("hung_chunks"), "failed_chunks": sm.get("failed_chunks"),
                                "unjoined": sm.get("unjoined"), "null_reason": sm.get("null_reason"), "g8_pass": g8.get((arm, cell)),
                                "start": ce.get("start"), "end": ce.get("end"), "wall_s": secs(ce["start"], ce["end"]) if ce else None}
    # an item is (task, doc_id): mmlu_llama numbers its items per subject, so doc_id alone repeats across subjects
    vec = lambda arm, cell, first=None: {(x["task"], x["doc_id"]): x["correct"] for x in cells.get((arm, cell), []) if first is None or x["doc_id"] < first}  # noqa: E731
    shas = lambda arm, cell: {(x["task"], x["doc_id"]): x["output_sha"] for x in cells.get((arm, cell), [])}  # noqa: E731
    med = lambda arm, cell: per.get(f"{arm}|{cell}", {}).get("tokens_median")  # noqa: E731
    out = {"cells": per, "arm_health": health, "models": {}}
    for arm in ("N3", "N2"):
        sc = paired(vec(arm, "on_gsm8k_1"), vec(arm, "on_gsm8k_2"))
        same = sum(1 for k, v in shas(arm, "on_gsm8k_1").items() if shas(arm, "on_gsm8k_2").get(k) == v)
        consistent = rule_self_consistency(sc.get("ci95_pp"))
        off_ok = {t: rule_reasoning_off(med(arm, f"off_{t}"), med(arm, f"on_{t}" if t == "mmlu" else "on_gsm8k_1")) for t in ("gsm8k", "mmlu")}
        q2g = paired(vec(arm, "off_gsm8k"), vec(arm, "on_gsm8k_1"))
        q2m = paired(vec(arm, "off_mmlu"), vec(arm, "on_mmlu"))
        caps = {c: per.get(f"{arm}|{c}", {}).get("cap_share_pct") for c in ("on_gsm8k_1", "on_mmlu", "on_gsm8k_2")}
        capmax = 5.0 if arm == "N3" else 10.0
        null_off = lambda v, t: v if off_ok[t] else "null (reasoning not really off)"  # noqa: E731
        null_eq = lambda v: v if consistent else "null (self-consistency)"  # noqa: E731
        m = {"self_consistency_on_gsm8k_run2_minus_run1": {**sc, "byte_identical": same, "equivalence_verdicts_kept": consistent},
             "reasoning_really_off": {t: {"off_median": med(arm, f"off_{t}"), "on_median": med(arm, f"on_{t}" if t == "mmlu" else "on_gsm8k_1"), "ok": ok} for t, ok in off_ok.items()},
             "Q1_gsm8k_on": {"value_pct": per.get(f"{arm}|on_gsm8k_1", {}).get("accuracy_pct"), "pass_if": ">= 88" if arm == "N3" else ">= 85"},
             "Q1_mmlu_on": {"value_pct": per.get(f"{arm}|on_mmlu", {}).get("accuracy_pct"), "pass_if": ">= 75" if arm == "N3" else ">= 70"},
             "Q2_gsm8k_on_minus_off": {**q2g, "verdict": null_off(rule_positive_ci(q2g.get("ci95_pp")), "gsm8k")},
             "Q2_mmlu_on_minus_off": {**q2m, "verdict": null_off(null_eq(rule_interval_ci(q2m.get("diff_pp"), q2m.get("ci95_pp"), -2, 6)), "mmlu"),
                                      "tie_break_added_after_the_run": "pass = whole CI inside; fail = point outside; otherwise inconclusive"},
             "Q2_tokens_gsm8k": {"off_median": med(arm, "off_gsm8k"), "on_median": med(arm, "on_gsm8k_1"),
                                 "verdict": "pass" if med(arm, "off_gsm8k") <= 0.25 * med(arm, "on_gsm8k_1") else "fail"},
             "Q2_cap_share_on": {"values_pct": caps, "pass_if": f"<= {capmax}%", "verdict": "pass" if all(v is not None and v <= capmax for v in caps.values()) else "fail"}}
        thr = 88 if arm == "N3" else 85
        m["Q1_gsm8k_on"]["verdict"] = "pass" if (m["Q1_gsm8k_on"]["value_pct"] or 0) >= thr else "fail"
        thr = 75 if arm == "N3" else 70
        m["Q1_mmlu_on"]["verdict"] = "pass" if (m["Q1_mmlu_on"]["value_pct"] or 0) >= thr else "fail"
        out["models"][arm] = m
    # C1: N3 reasoning off x GSM8K, first 200 items, c=1 vs c=16
    a, b = vec("N3", "off_gsm8k", 200), vec("N3", "off_gsm8k_c1_first200")
    c1 = paired(a, b)
    s16, s1 = shas("N3", "off_gsm8k"), shas("N3", "off_gsm8k_c1_first200")
    c1["byte_identical"] = sum(1 for k, v in s1.items() if s16.get(k) == v)
    c1["accuracy_c16_pct"] = pct(sum(a.values()) / len(a)) if a else None
    c1["accuracy_c1_pct"] = pct(sum(b.values()) / len(b)) if b else None
    kept = out["models"]["N3"]["self_consistency_on_gsm8k_run2_minus_run1"]["equivalence_verdicts_kept"]
    c1["verdict"] = rule_interval_ci(c1.get("diff_pp"), c1.get("ci95_pp"), -3, 3) if kept else "null (self-consistency)"
    c1["tie_break_added_after_the_run"] = "pass = whole CI inside; fail = point outside; otherwise inconclusive"
    out["C1_concurrency_N3"] = c1
    # G4 quality arms beside N3's reasoning-off GSM8K (record; P5 is judged in g4())
    out["G4_quality_arms_vs_N3_off_gsm8k"] = {arm: paired(vec("N3", "off_gsm8k"), vec(arm, "off_gsm8k")) for arm in ("V3B1", "V3B2")}
    json.dump(out, open(os.path.join(RQ, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return out


# ---------------------------------------------------------------- G4
def g4(q):
    ev = jl(os.path.join(RG4, "events.jsonl")); req = jl(os.path.join(RG4, "requests.jsonl"))
    lv = [r for r in jl(os.path.join(RG4, "levels.jsonl")) if not r.get("warmup")]
    traps = {}
    for e in ev:
        if e["kind"] == "engine_start":
            s = lit(e["start"])
            traps[e["arm"]] = s.get("traps") if isinstance(s, dict) else None
    ident = next((e for e in ev if e["kind"] == "answers_identical"), {})
    rate = {arm: st.median(r["tps"] for r in req if r["arm"] == arm and r.get("repeat") == 0 and r.get("tps")) for arm in ("N3", "V3B1", "V3B2")}
    tps = {(r["arm"], r["concurrency"]): (r.get("summary") or {}).get("output_token_throughput", {}).get("avg") for r in lv}
    slo = {}
    for r in lv:
        s = r.get("summary") or {}
        t99 = (s.get("time_to_first_token") or {}).get("p99"); i99 = (s.get("inter_token_latency") or {}).get("p99")
        slo[f"{r['arm']}|{r['concurrency']}"] = {"ttft_p99_ms": round(t99, 1) if t99 else None, "itl_p99_ms": round(i99, 2) if i99 else None,
                                                "inside_server_slo": bool(t99 is not None and i99 is not None and t99 <= 2000 and i99 <= 100)}
    levels = sorted({c for (_, c) in tps})
    p4 = {c: round(tps[("V3B2", c)] / tps[("N3", c)], 3) for c in levels if tps.get(("V3B2", c)) and tps.get(("N3", c))}
    sr = ident.get("self_repeat", {}); pairs = ident.get("pairs", {})
    t1, t2 = (traps.get("V3B1") or {}), (traps.get("V3B2") or {})
    p5_applies = t1.get("mamba_ssm_cache_dtype") != "float32" and t2.get("mamba_ssm_cache_dtype") == "float32"
    qa = q["G4_quality_arms_vs_N3_off_gsm8k"]
    out = {"P1_record": {"V3B1_started": "V3B1" in traps, "traps": traps},
           "P2": {"rates_median_tok_s": {k: round(v, 1) for k, v in rate.items()}, "ratio_V3B2_over_N3": round(rate["V3B2"] / rate["N3"], 3),
                  "pass_if": "[0.95, 1.05]", "verdict": rule_range(rate["V3B2"] / rate["N3"], 0.95, 1.05)},
           "P3": {"identical_N3_V3B2": pairs.get("N3==V3B2"), "self_repeat": sr, "all_pairs": pairs,
                  "verdict": rule_p3(pairs.get("N3==V3B2", 0), sr.get("N3", {}).get("identical", 0), sr.get("V3B2", {}).get("identical", 0))},
           "P4": {"ratio_V3B2_over_N3_by_level": p4, "pass_if": "every level within [0.90, 1.10]", "verdict": "pass" if p4 and all(0.9 <= v <= 1.1 for v in p4.values()) else "fail"},
           "P5": {"applies": p5_applies, "verdict": "not triggered (V3B1 is also float32)" if not p5_applies else
                  ("pass" if qa["V3B1"].get("diff_pp", 0) < qa["V3B2"].get("diff_pp", 0) else "fail")},
           "tok_s_by_level": {f"{a}|{c}": round(v, 1) for (a, c), v in sorted(tps.items()) if v}, "slo_by_level": slo,
           "g8_all_pass": all(e["pass"] for e in ev if e["kind"] == "g8"), "g8_cells": sum(1 for e in ev if e["kind"] == "g8")}
    json.dump(out, open(os.path.join(RG4, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return out


# ---------------------------------------------------------------- durations (every cell, the harness tests included)
def durations():
    rows, local = [], []
    add = lambda stage, run, what, start, end, s: (local if stage.startswith("G6") or run != "real" else rows).append(  # noqa: E731
        {"stage": stage, "run": run, "what": what, "start": start, "end": end, "s": s})
    for r in jl(os.path.join(R1, "levels.jsonl")):
        add("G1", "real", f"{r['arm']} c={r['concurrency']}{' warm-up' if r.get('warmup') else ''}", r["start"], r["end"], secs(r["start"], r["end"]))
    for e in jl(os.path.join(R1, "events.jsonl")):
        if e["kind"] == "container_start":
            add("G1", "real", f"{e['arm']} container to READY", None, e["at"], e.get("seconds_to_ready"))
    for e in jl(os.path.join(RQ, "events.jsonl")):
        stage = {"N3": "G2", "N2": "G3"}.get(e.get("arm"), "G4q")
        if e["kind"] == "cell_end":
            add(stage, "real", f"{e['arm']} {e['cell']}", e["start"], e["end"], secs(e["start"], e["end"]))
        if e["kind"] == "engine_start":
            s = lit(e.get("start"))
            add(stage, "real", f"{e['arm']} engine to READY", None, e["at"], s.get("seconds_to_verdict") if isinstance(s, dict) else None)
    for r in jl(os.path.join(RG4, "levels.jsonl")):
        add("G4", "real", f"{r['arm']} c={r['concurrency']}{' warm-up' if r.get('warmup') else ''}", r["start"], r["end"], secs(r["start"], r["end"]))
    g4ev = jl(os.path.join(RG4, "events.jsonl")); g4rq = jl(os.path.join(RG4, "requests.jsonl"))
    for arm in ("N3", "V3B1", "V3B2"):
        st_ = next((e for e in g4ev if e["kind"] == "engine_start" and e.get("arm") == arm), None)
        en = next((e for e in g4ev if e["kind"] == "engine_end" and e.get("arm") == arm), None)
        rq = [r for r in g4rq if r["arm"] == arm]
        if st_:
            s = lit(st_["start"])
            add("G4", "real", f"{arm} engine to READY", None, st_["at"], s.get("seconds_to_verdict") if isinstance(s, dict) else None)
        if rq:
            add("G4", "real", f"{arm} single stream (50 + 10 repeats)", rq[0]["at"], rq[-1]["at"], secs(rq[0]["at"], rq[-1]["at"]))
        if st_ and en:
            add("G4", "real", f"{arm} whole arm (READY to stop)", st_["at"], en["at"], secs(st_["at"], en["at"]))
    for r in jl(os.path.join(RG6, "levels.jsonl")):
        add("G6 (stopped, P79)", "real", f"{r.get('sweep')} c={r['concurrency']}{' warm-up' if r.get('warmup') else ''}", r["start"], r["end"], secs(r["start"], r["end"]))
    for base, stage in ((R1, "G1"), (RQ, "G2/G3/G4q"), (RG4, "G4"), (RG6, "G6"), (RG5, "G5")):
        for d in sorted(glob.glob(os.path.join(base, "harness_test", "*"))):
            at = [e.get("at") or e.get("start") for e in jl(os.path.join(d, "events.jsonl"))] + [r.get("end") for r in jl(os.path.join(d, "levels.jsonl"))]
            at = [a for a in at if a]
            if at:
                a0, a1 = min(at, key=ts), max(at, key=ts)
                add(stage, "harness test", os.path.basename(d), a0, a1, secs(a0, a1))
    json.dump(rows, open(os.path.join(RQ, "durations.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    if local and os.path.isdir(os.path.join(RQ, "logs")):
        json.dump(local, open(os.path.join(RQ, "logs", "durations_local.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return rows + local


# ---------------------------------------------------------------- self-test with mutation tests
def self_test():
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want; ok &= good
        print(f"  {'PASS' if good else 'FAIL'} {name}: {got} (want {want})")
    check("literal reader: dict with a list, a bool and a negative number", lit("{'a': [1, -2.5], 'b': True, 'c': None}"), {"a": [1, -2.5], "b": True, "c": None})
    check("literal reader refuses a call", lit("{'a': __import__('os')}"), "{'a': __import__('os')}")
    check("paired: identical vectors -> diff 0", paired({1: 1, 2: 0}, {1: 1, 2: 0})["diff_pp"], 0.0)
    check("paired: b - a direction", paired({1: 0, 2: 0, 3: 1}, {1: 1, 2: 0, 3: 1})["diff_pp"], 33.33)
    check("paired: (task, doc_id) keys keep two subjects' item 0 apart", paired({("x", 0): 0, ("y", 0): 1}, {("x", 0): 1, ("y", 0): 1})["n"], 2)
    check("self-consistency: N3's CI [-0.93, 0.78] kept", rule_self_consistency([-0.93, 0.78]), True)
    check("self-consistency: [-2.5, 0.1] -> null", rule_self_consistency([-2.5, 0.1]), False)
    check("reasoning off: 117 vs 300 -> ok", rule_reasoning_off(117, 300), True)
    check("reasoning off: 200 vs 300 -> not off", rule_reasoning_off(200, 300), False)
    check("positive CI: [1, 7] -> pass", rule_positive_ci([1.0, 7.0]), "pass")
    check("positive CI: [-0.1, 7] -> fail", rule_positive_ci([-0.1, 7.0]), "fail")
    check("interval: point outside -> fail", rule_interval_ci(12.0, [10.0, 14.0], -2, 6), "fail")
    check("interval: CI inside -> pass", rule_interval_ci(1.0, [-1.0, 3.0], -2, 6), "pass")
    check("interval: point inside, CI crossing -> inconclusive", rule_interval_ci(5.0, [3.0, 7.0], -2, 6), "inconclusive")
    check("P3: self-repeat 0/10 -> not interpretable", rule_p3(1, 0, 0), "not interpretable")
    check("P3: 46/50 with 10/10 -> pass", rule_p3(46, 10, 10), "pass")
    check("range: 11.61 in [10.5, 13.5]", rule_range(11.61, 10.5, 13.5), "pass")
    # mutations: each broken rule must change a verdict above
    check("mutation: self-consistency with [-3, +3] keeps [-2.5, 0.1] (rule broken)", (lambda ci: -3 <= ci[0] and ci[1] <= 3)([-2.5, 0.1]), True)
    check("mutation: reasoning-off at 90% passes 200 vs 300 (rule broken)", (lambda o, n: o <= 0.9 * n)(200, 300), True)
    check("mutation: P3 without the self-repeat gate reads 1/50 as a fail (rule broken)", (lambda i: "pass" if i >= 45 else "fail")(1), "fail")
    check("mutation: positive-CI on the point estimate passes [-0.1, 7] (rule broken)", (lambda ci: "pass" if (ci[0] + ci[1]) / 2 > 0 else "fail")([-0.1, 7.0]), "pass")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "self_test":
        raise SystemExit(self_test())
    a = g1(); q = quality(); b = g4(q); d = durations()
    print(json.dumps({"G1": a, "quality_models": q["models"], "C1": q["C1_concurrency_N3"], "G4q": q["G4_quality_arms_vs_N3_off_gsm8k"],
                      "G4": {k: v for k, v in b.items() if k not in ("tok_s_by_level", "slo_by_level")}}, indent=1, ensure_ascii=False))
    print("durations rows", len(d))
