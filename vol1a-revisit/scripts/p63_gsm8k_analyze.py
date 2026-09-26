#!/usr/bin/env python3
"""Vol.1-A revisit, P63 · GSM8K analysis. Rules frozen in prediction_p63_gsm8k.json.
Reads only the published files: items/*.jsonl, events_public.jsonl, g1_scorer_controls.json. Writes analysis.json.
Statistics are P62's (vol1a-revisit/scripts/p62_quality_analyze.py, imported unchanged): Wilson 95% interval, paired
bootstrap 95% interval (10,000 resamples, fixed seed), exact McNemar p, interval verdict against +-2 pp.

Primary metric: exact match with lm-eval's strict-match filter. An output that reached the cap is scored as lm-eval
scores it (in practice wrong): it is the model's behaviour, and it is counted.
Per arm, run "main": n, correct, accuracy, Wilson interval; null (with reasons) if any of:
  G1   the GSM8K scorer controls (P62's, same tool and task): positive 1.0 and negative <= 0.05
  cap  every request of the run carried max_tokens 1024 (the proxy's record); otherwise the run is void
  G2a  every item's server prompt tokens within +-5% of N-BF16's after the arm's constant template offset
  G3   residency and P59's health gate
  G4   every item's request sha256 (body without "model") equal to N-BF16's, same item set
  join every item joined to its proxy record with the same output text
Positive control of the equivalence method: N-BF16 "repeat" minus N-BF16 "main", paired 95% interval. It must lie
inside +-2 pp (and both runs pass cap and join); otherwise every comparison's verdict is null ("the method cannot call a
configuration equal to itself").
Comparisons: N-FP8, O-FP16, O-Q4 minus N-BF16 "main": difference, interval, McNemar p, verdict within / outside /
undetermined (null if either cell is null or the positive control failed).
Reported, never a gate: each run's share of outputs with finish_reason "length"; a sensitivity reading (the same
comparison over items where neither arm hit the cap), never a verdict.
usage: p63_gsm8k_analyze.py <run_dir> | --self-test
"""
import json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p62_quality_analyze import BOUND, G2_TOL, mcnemar, paired, verdict, wilson  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REF, ARMS, CAP = "N-BF16", ["N-FP8", "O-FP16", "O-Q4"], 1024


def analyse(items, events, ctl):
    starts = {e["arm"]: e for e in events if e.get("kind") == "arm_start"}
    runs = {(e["arm"], e["run"]): e for e in events if e.get("kind") == "task_run"}
    probe = {a: ((e.get("probe") or {}).get("user_one_word") or {}).get("prompt_tokens") for a, e in starts.items()}
    g1 = ctl["gsm8k_positive"]["strict_match"] == 1.0 and ctl["gsm8k_negative"]["strict_match"] <= 0.05
    ref = items.get((REF, "main")) or {}
    out = {"g1_scorer_controls": {"gsm8k_positive": ctl["gsm8k_positive"], "gsm8k_negative": ctl["gsm8k_negative"], "pass": g1},
           "runs": {}, "cells": {}, "positive_control": None, "comparisons": {}}

    def run_checks(arm, run):
        r = runs.get((arm, run)) or {}
        it = items.get((arm, run)) or {}
        j = r.get("join") or {}
        cap_ok = r.get("max_tokens_seen") == [CAP]
        join_ok = bool(j) and j.get("unjoined") == 0 and j.get("resp_vs_proxy_text_mismatch") == 0 and j.get("items") == len(it)
        length = sum(1 for v in it.values() if v.get("finish_reason") == "length")
        rec = {"items": len(it), "max_tokens_seen": r.get("max_tokens_seen"), "cap_ok": cap_ok, "join": j, "join_ok": join_ok,
               "length_items": length, "length_share": round(length / len(it), 5) if it else None,
               "accuracy_pct": round(100 * sum(v["correct"] for v in it.values()) / len(it), 3) if it else None}
        out["runs"][f"{arm}|{run}"] = rec
        return rec

    for arm in [REF] + ARMS:
        it = items.get((arm, "main"))
        rc = run_checks(arm, "main")
        if not it:
            out["cells"][arm] = {"accuracy_pct": None, "reasons": ["not run"]}; continue
        st_ = starts.get(arm) or {}
        reasons = []
        if not g1:
            reasons.append("G1 scorer controls failed")
        if not rc["cap_ok"]:
            reasons.append("a request carried a max_tokens other than 1024: run void")
        if not rc["join_ok"]:
            reasons.append("join incomplete")
        if not (st_.get("resident") and (st_.get("health") or {}).get("pass")):
            reasons.append("G3 residency or health failed")
        off = 0 if arm.startswith("N-") else ((probe.get(REF) - probe.get(arm)) if probe.get(REF) and probe.get(arm) else None)
        devs = [(v["prompt_tokens"] + off - ref[k]["prompt_tokens"]) / ref[k]["prompt_tokens"] for k, v in it.items()
                if off is not None and k in ref and ref[k].get("prompt_tokens") and v.get("prompt_tokens") is not None]
        g2a = {"template_offset_tokens": off, "items_compared": len(devs), "items_outside_5pct": sum(1 for d in devs if abs(d) > G2_TOL),
               "max_abs_rel_diff": round(max((abs(d) for d in devs), default=0), 4)}
        g2a["pass"] = off is not None and len(devs) == len(it) and g2a["items_outside_5pct"] == 0
        if not g2a["pass"]:
            reasons.append("G2a prompt tokens")
        mism = sum(1 for k, v in it.items() if (ref.get(k) or {}).get("request_sha") != v.get("request_sha"))
        g4 = {"request_sha_mismatches": mism, "pass": mism == 0 and set(it) == set(ref)}
        if not g4["pass"]:
            reasons.append("G4 request contents differ")
        k_, n_ = sum(v["correct"] for v in it.values()), len(it)
        cell = {"n": n_, "correct": k_, "accuracy_pct": round(100 * k_ / n_, 3), "wilson95_pct": wilson(k_, n_),
                "flexible_extract_pct": round(100 * sum(v.get("correct_flexible", 0) for v in it.values()) / n_, 3),
                "length_share": rc["length_share"], "g2a": g2a, "g3": {"resident": st_.get("resident"), "health": st_.get("health")}, "g4": g4, "reasons": reasons}
        if reasons:
            cell["accuracy_pct_if_gates_passed"] = cell.pop("accuracy_pct"); cell["accuracy_pct"] = None
        out["cells"][arm] = cell

    rep = items.get((REF, "repeat")) or {}
    rr = run_checks(REF, "repeat")
    pc = paired(ref, rep) if ref and rep else None
    pc_ok = bool(pc and rr["cap_ok"] and rr["join_ok"] and out["cells"][REF].get("accuracy_pct") is not None
                 and -BOUND <= pc["ci95_pp"][0] and pc["ci95_pp"][1] <= BOUND)
    out["positive_control"] = {"what": "N-BF16 repeat minus N-BF16 main", "paired": pc, "inside_bound": pc_ok}
    for arm in ARMS:
        it = items.get((arm, "main")) or {}
        p = paired(ref, it) if ref and it else None
        why = []
        if out["cells"][REF].get("accuracy_pct") is None:
            why.append("reference cell null")
        if (out["cells"].get(arm) or {}).get("accuracy_pct") is None:
            why.append("arm cell null")
        if not pc_ok:
            why.append("positive control failed: the method cannot call N-BF16 equal to itself within +-2 pp")
        both = {k for k in set(ref) & set(it) if ref[k].get("finish_reason") != "length" and it[k].get("finish_reason") != "length"}
        out["comparisons"][arm] = {"paired": p, "verdict": None if why else verdict(p and p["ci95_pp"]), "verdict_null_reasons": why,
                                   "sensitivity_items_where_neither_hit_the_cap": paired({k: ref[k] for k in both}, {k: it[k] for k in both}) if both else None}
    return out


def load(d):
    items = {}
    for f in sorted(os.listdir(os.path.join(d, "items"))):
        arm, _, run = f[:-6].split("__")
        items[(arm, run)] = {f"{r['task']}|{r['doc_id']}": r for r in (json.loads(l) for l in open(os.path.join(d, "items", f), encoding="utf-8"))}
    ev = [json.loads(l) for l in open(os.path.join(d, "events_public.jsonl"), encoding="utf-8")]
    return items, ev, json.load(open(os.path.join(d, "g1_scorer_controls.json"), encoding="utf-8"))


def self_test():
    rng = random.Random(2)
    base = {i: rng.random() < 0.85 for i in range(1319)}
    def mk(flip=lambda i: base[i], pt=400, fin=lambda i: "stop", sha="o"):
        return {f"t|{i}": {"task": "t", "doc_id": i, "correct": int(flip(i)), "request_sha": f"r{i}", "output_sha": f"{sha}{i}", "prompt_tokens": pt, "finish_reason": fin(i)} for i in range(1319)}
    ref = mk(); ok = {"resident": True, "health": {"pass": True}}
    items = {(REF, "main"): ref, (REF, "repeat"): mk(flip=lambda i: base[i] if i % 100 else not base[i]),
             ("N-FP8", "main"): mk(), ("O-FP16", "main"): mk(pt=375), ("O-Q4", "main"): mk(pt=375, flip=lambda i: base[i] and i % 12 != 0)}
    ev = [{"kind": "arm_start", "arm": a, "probe": {"user_one_word": {"prompt_tokens": 36 if a.startswith("N-") else 11}}, **ok} for a in [REF] + ARMS]
    ev += [{"kind": "task_run", "arm": a, "run": r, "max_tokens_seen": [CAP], "join": {"items": 1319, "unjoined": 0, "resp_vs_proxy_text_mismatch": 0}}
           for a, r in [(REF, "main"), (REF, "repeat")] + [(a, "main") for a in ARMS]]
    ctl = {"gsm8k_positive": {"strict_match": 1.0}, "gsm8k_negative": {"strict_match": 0.014}}
    x = analyse(items, ev, ctl)
    cases = [("positive control inside +-2", x["positive_control"]["inside_bound"] is True),
             ("identical arm within", x["comparisons"]["N-FP8"]["verdict"] == "within"),
             ("O-Q4 losing ~7 pp -> outside", x["comparisons"]["O-Q4"]["verdict"] == "outside"),
             ("template offset 25 absorbed (375 + 25 = 400; without it -6.25%)", x["cells"]["O-FP16"]["g2a"]["pass"] is True)]
    items2 = dict(items); items2[(REF, "repeat")] = mk(flip=lambda i: base[i] if i % 12 else False)
    y = analyse(items2, ev, ctl)
    cases.append(("positive control outside -> every verdict null", y["positive_control"]["inside_bound"] is False and all(v["verdict"] is None for v in y["comparisons"].values())))
    ev3 = [dict(e, max_tokens_seen=[256, CAP]) if e.get("arm") == "O-FP16" and e["kind"] == "task_run" else e for e in ev]
    z = analyse(items, ev3, ctl)
    cases.append(("a 256 request -> run void, cell null", z["cells"]["O-FP16"]["accuracy_pct"] is None and z["comparisons"]["O-FP16"]["verdict"] is None))
    items4 = dict(items); items4[("N-FP8", "main")] = mk(fin=lambda i: "length" if i % 20 == 0 else "stop")
    w = analyse(items4, ev, ctl)
    cases.append(("5% length is reported, not a gate", w["cells"]["N-FP8"]["accuracy_pct"] is not None and w["cells"]["N-FP8"]["length_share"] == round(66 / 1319, 5)))
    cases.append(("sensitivity excludes capped items", w["comparisons"]["N-FP8"]["sensitivity_items_where_neither_hit_the_cap"]["items"] == 1319 - 66))
    items5 = dict(items); items5[("N-FP8", "main")] = {k: dict(v, request_sha="x" if v["doc_id"] == 3 else v["request_sha"]) for k, v in items[("N-FP8", "main")].items()}
    cases.append(("G4 mismatch -> null", analyse(items5, ev, ctl)["cells"]["N-FP8"]["accuracy_pct"] is None))
    cases.append(("G1 failure -> null", analyse(items, ev, dict(ctl, gsm8k_negative={"strict_match": 0.2}))["cells"]["N-BF16"]["accuracy_pct"] is None))
    for n, ok_ in cases:
        print(("PASS " if ok_ else "FAIL ") + n)
    return 0 if all(o for _, o in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    a = analyse(*load(d))
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False, sort_keys=True)
    for arm, c in a["cells"].items():
        print(arm, c.get("accuracy_pct"), c.get("wilson95_pct"), c.get("length_share"), c.get("reasons"))
    print("positive control", a["positive_control"]["paired"] and (a["positive_control"]["paired"]["diff_pp"], a["positive_control"]["paired"]["ci95_pp"]), a["positive_control"]["inside_bound"])
    for arm, v in a["comparisons"].items():
        p = v["paired"]; s = v["sensitivity_items_where_neither_hit_the_cap"]
        print(arm, p and (p["diff_pp"], p["ci95_pp"], p["mcnemar_p"]), v["verdict"], v["verdict_null_reasons"], "sens", s and (s["diff_pp"], s["ci95_pp"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
