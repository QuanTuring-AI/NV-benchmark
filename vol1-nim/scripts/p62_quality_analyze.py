#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q1 · answer-quality analysis. Rules frozen in prediction_p62_quality.json.
Reads only the files that are published: items/*.jsonl (machine fields per item), events_public.jsonl (arm gates and
template probes), g1_scorer_controls.json, mmlu_sample_ids.json. Writes analysis.json.

Primary metric per task: GSM8K exact match on lm-eval's strict-match filter; IFEval prompt-level strict; MMLU exact
match (strict_match). Reference = N-BF16, run "main".
Per arm x task (run "main"): n, correct, accuracy, Wilson 95% CI. A cell is null (with its reasons) if any gate fails:
  G1  the task's scorer controls: GSM8K positive = 1.0 and negative <= 0.05; MMLU positive = 1.0 and negative within
      0.15-0.35; IFEval constructed positive = 1.0 and both negatives (empty, permuted) <= G1_IFEVAL_NEG
  G2  (a) every item's server prompt-token count within +-5% of N-BF16's for the same item, after removing the arm's
      constant template offset (N-BF16's minus the arm's prompt tokens for the one-word probe message; 0 for NIM arms);
      (b) finish_reason "length" on < 1% of the items (every arm, reference included)
  G3  the arm's residency and P59 health gate (>= 0.40 of peak bandwidth at c=1)
  G4  every item's request sha (request body without "model") equal to N-BF16's, and the same item set
  join every item joined to exactly one proxy record with the same output text
Paired comparison with N-BF16 (items in both): difference in accuracy (arm - reference, pp), paired bootstrap 95% CI
(10,000 resamples of items, drawn as a multinomial over the four (reference, arm) outcome pairs: two binomials by inverse CDF, Python's random with a fixed seed), exact two-sided
McNemar p on the discordant pairs. Verdict against the +-2 pp equivalence bound: CI inside [-2, +2] -> "within";
CI entirely below -2 or above +2 -> "outside"; otherwise "undetermined". The verdict is null if either cell is null or
if the task's noise floor exceeds 2 pp.
Sensitivity reading (reported, never a verdict): the same paired comparison over the items where neither arm's
output ended with finish_reason "length".
Noise floor per task: N-BF16 "main" vs "repeat" -- the share of items whose correctness differs (pp), the share with
identical output sha, and the paired difference with CI and McNemar p.
Concurrency: N-FP8 GSM8K at c=1 and c=32 against each other and against its c=8 "main" run: accuracies, paired CI,
McNemar p, correctness agreement, identical-output share.
usage: p62_quality_analyze.py <run_dir> | --self-test
"""
import bisect, json, math, os, random, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ARMS = ["N-BF16", "N-FP8", "O-FP16", "O-Q4"]
TASKS = ["gsm8k", "ifeval", "mmlu"]
REF = "N-BF16"
BOUND = 2.0
G2_TOL, LEN_MAX = 0.05, 0.01
G1_IFEVAL_NEG = 0.30
BOOT, SEED = 10000, 20260926


def wilson(k, n, z=1.959964):
    if not n:
        return None
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 3), round(100 * (c + h), 3)]


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) * 0.5 ** n)


_CDF = {}


def binom_draw(rng, m, p):
    """Binomial(m, p) by inverse CDF from one uniform draw (cumulative table cached per (m, p))."""
    key = (m, p)
    if key not in _CDF:
        if p <= 0 or m == 0:
            arr = [1.0] * (m + 1)
        elif p >= 1:
            arr = [0.0] * m + [1.0]
        else:
            lp, lq, lg, s, arr = math.log(p), math.log1p(-p), math.lgamma(m + 1), 0.0, []
            for k in range(m + 1):
                s += math.exp(lg - math.lgamma(k + 1) - math.lgamma(m - k + 1) + k * lp + (m - k) * lq); arr.append(s)
        _CDF[key] = arr
    arr = _CDF[key]
    return min(bisect.bisect_left(arr, rng.random() * arr[-1]), m)


def paired(ref, arm):
    keys = sorted(set(ref) & set(arm))
    cnt = {(1, 1): 0, (1, 0): 0, (0, 1): 0, (0, 0): 0}
    for k in keys:
        cnt[(ref[k]["correct"], arm[k]["correct"])] += 1
    n = len(keys)
    if not n:
        return None
    p10, p01 = cnt[(1, 0)] / n, cnt[(0, 1)] / n
    rng = random.Random(SEED); diffs = []
    for _ in range(BOOT):   # resampling n items = a multinomial draw over the four outcome pairs; only the two discordant counts matter
        n10 = binom_draw(rng, n, p10)
        n01 = binom_draw(rng, n - n10, p01 / (1 - p10) if p10 < 1 else 0.0)
        diffs.append(100.0 * (n01 - n10) / n)
    diffs.sort()
    d = 100.0 * (cnt[(0, 1)] - cnt[(1, 0)]) / n
    return {"items": n, "diff_pp": round(d, 3), "ci95_pp": [round(diffs[int(0.025 * BOOT)], 3), round(diffs[int(0.975 * BOOT) - 1], 3)],
            "ref_only_correct": cnt[(1, 0)], "arm_only_correct": cnt[(0, 1)], "mcnemar_p": round(mcnemar(cnt[(1, 0)], cnt[(0, 1)]), 6),
            "correctness_disagreement_pp": round(100.0 * (cnt[(1, 0)] + cnt[(0, 1)]) / n, 3),
            "identical_output_share": round(sum(1 for k in keys if ref[k].get("output_sha") and ref[k]["output_sha"] == arm[k].get("output_sha")) / n, 4)}


def verdict(ci):
    if ci is None:
        return None
    lo, hi = ci
    return "within" if lo >= -BOUND and hi <= BOUND else "outside" if hi < -BOUND or lo > BOUND else "undetermined"


def g1(ctl):
    r = {"gsm8k": ctl["gsm8k_positive"]["strict_match"] == 1.0 and ctl["gsm8k_negative"]["strict_match"] <= 0.05,
         "mmlu": ctl["mmlu_positive"]["exact_match"] == 1.0 and 0.15 <= ctl["mmlu_negative"]["exact_match"] <= 0.35,
         "ifeval": ctl["ifeval_positive_constructed"]["prompt_level_strict"] == 1.0 and ctl["ifeval_negative_empty"]["prompt_level_strict_non_eligible"] <= G1_IFEVAL_NEG
                   and ctl["ifeval_negative_permuted"]["prompt_level_strict"] <= G1_IFEVAL_NEG}
    return r


def analyse(items, events, ctl):
    starts = {e["arm"]: e for e in events if e.get("kind") == "arm_start"}
    runs = {(e["arm"], e["task"], e["run"]): e for e in events if e.get("kind") == "task_run"}
    probe = {a: ((e.get("probe") or {}).get("user_one_word") or {}).get("prompt_tokens") for a, e in starts.items()}
    G1 = g1(ctl)
    out = {"g1_scorer_controls": {"controls": ctl, "pass": G1}, "cells": {}, "paired_vs_ref": {}, "noise_floor": {}, "concurrency_fp8_gsm8k": {}}
    for t in TASKS:
        ref = items.get((REF, t, "main")) or {}
        nf = paired(ref, items.get((REF, t, "repeat")) or {}) if ref and items.get((REF, t, "repeat")) else None
        out["noise_floor"][t] = nf
        for arm in ARMS:
            it = items.get((arm, t, "main"))
            key = f"{arm}|{t}"
            if not it:
                out["cells"][key] = {"accuracy": None, "reasons": ["not run"]}; continue
            st_ = starts.get(arm) or {}
            reasons = []
            if not G1[t]:
                reasons.append("G1 scorer controls failed")
            g3 = bool(st_.get("resident") and (st_.get("health") or {}).get("pass"))
            if not g3:
                reasons.append("G3 residency or health failed")
            off = 0 if arm.startswith("N-") else ((probe.get(REF) or 0) - (probe.get(arm) or 0)) if probe.get(REF) and probe.get(arm) else None
            devs = []
            for k, v in it.items():
                r = ref.get(k)
                if r and r.get("prompt_tokens") and v.get("prompt_tokens") is not None and off is not None:
                    devs.append((v["prompt_tokens"] + off - r["prompt_tokens"]) / r["prompt_tokens"])
            outside = sum(1 for d in devs if abs(d) > G2_TOL)
            length = sum(1 for v in it.values() if v.get("finish_reason") == "length")
            g2 = {"template_offset_tokens": off, "items_compared": len(devs), "items_outside_5pct": outside,
                  "max_abs_rel_diff": round(max((abs(d) for d in devs), default=0), 4),
                  "raw_mean_prompt_tokens": round(sum(v["prompt_tokens"] for v in it.values() if v.get("prompt_tokens")) / max(1, sum(1 for v in it.values() if v.get("prompt_tokens"))), 2),
                  "length_share": round(length / len(it), 5), "length_items": length,
                  "pass": off is not None and len(devs) == len(it) and outside == 0 and length / len(it) < LEN_MAX}
            if not g2["pass"]:
                reasons.append("G2 prompt tokens or length share")
            mism = sum(1 for k, v in it.items() if (ref.get(k) or {}).get("request_sha") != v.get("request_sha"))
            g4 = {"items": len(it), "ref_items": len(ref), "request_sha_mismatches": mism, "pass": mism == 0 and set(it) == set(ref)}
            if not g4["pass"]:
                reasons.append("G4 request contents differ")
            j = (runs.get((arm, t, "main")) or {}).get("join") or {}
            jok = bool(j) and j.get("unjoined") == 0 and j.get("resp_vs_proxy_text_mismatch") == 0 and j.get("items") == len(it)
            if not jok:
                reasons.append("join between lm-eval samples and proxy records incomplete")
            k_ = sum(v["correct"] for v in it.values()); n_ = len(it)
            cell = {"n": n_, "correct": k_, "accuracy_pct": round(100 * k_ / n_, 3), "wilson95_pct": wilson(k_, n_), "g2": g2, "g3": {"resident": st_.get("resident"), "health": st_.get("health")},
                    "g4": g4, "join": j, "reasons": reasons}
            if t == "gsm8k":
                cell["flexible_extract_pct"] = round(100 * sum(v.get("correct_flexible", 0) for v in it.values()) / n_, 3)
            if t == "ifeval":
                cell["prompt_level_loose_pct"] = round(100 * sum(v.get("prompt_level_loose", 0) for v in it.values()) / n_, 3)
                ins = [x for v in it.values() for x in v.get("inst_strict", [])]; insl = [x for v in it.values() for x in v.get("inst_loose", [])]
                cell["inst_level_strict_pct"] = round(100 * sum(ins) / len(ins), 3) if ins else None
                cell["inst_level_loose_pct"] = round(100 * sum(insl) / len(insl), 3) if insl else None
            if reasons:
                cell["accuracy_pct_if_gates_passed"] = cell.pop("accuracy_pct"); cell["accuracy_pct"] = None
            out["cells"][key] = cell
        refcell = out["cells"].get(f"{REF}|{t}") or {}
        for arm in ARMS[1:]:
            c = out["cells"].get(f"{arm}|{t}") or {}
            p = paired(ref, items.get((arm, t, "main")) or {}) if ref and items.get((arm, t, "main")) else None
            why = []
            if refcell.get("accuracy_pct") is None:
                why.append("reference cell null")
            if c.get("accuracy_pct") is None:
                why.append("arm cell null")
            if nf is None:
                why.append("no noise floor")
            elif nf["correctness_disagreement_pp"] > BOUND:
                why.append(f"noise floor {nf['correctness_disagreement_pp']} pp > {BOUND} pp")
            ai = items.get((arm, t, "main")) or {}
            both_stop = {k for k in set(ref) & set(ai) if ref[k].get("finish_reason") != "length" and ai[k].get("finish_reason") != "length"}
            ps = paired({k: ref[k] for k in both_stop}, {k: ai[k] for k in both_stop}) if both_stop else None
            out["paired_vs_ref"][f"{arm}|{t}"] = {"paired": p, "verdict": None if why else verdict(p and p["ci95_pp"]), "verdict_null_reasons": why,
                                                  "sensitivity_items_where_neither_hit_the_cap": ps}
    g = {r: items.get(("N-FP8", "gsm8k", r)) for r in ("c1", "main", "c32")}
    out["concurrency_fp8_gsm8k"] = {"accuracy_pct": {r: (round(100 * sum(v["correct"] for v in x.values()) / len(x), 3) if x else None) for r, x in g.items()},
                                    "c32_vs_c1": paired(g["c1"], g["c32"]) if g["c1"] and g["c32"] else None,
                                    "c1_vs_c8": paired(g["main"], g["c1"]) if g["main"] and g["c1"] else None,
                                    "c32_vs_c8": paired(g["main"], g["c32"]) if g["main"] and g["c32"] else None,
                                    "length_share": {r: (round(sum(1 for v in x.values() if v.get("finish_reason") == "length") / len(x), 5) if x else None) for r, x in g.items()}}
    return out


def load(d):
    items = {}
    idir = os.path.join(d, "items")
    for f in sorted(os.listdir(idir)) if os.path.isdir(idir) else []:
        if not f.endswith(".jsonl"):
            continue
        arm, t, run = f[:-6].split("__")
        items[(arm, t, run)] = {f"{r['task']}|{r['doc_id']}": r for r in (json.loads(l) for l in open(os.path.join(idir, f), encoding="utf-8"))}
    ev = [json.loads(l) for l in open(os.path.join(d, "events_public.jsonl"), encoding="utf-8")] if os.path.exists(os.path.join(d, "events_public.jsonl")) else []
    ctl = json.load(open(os.path.join(d, "g1_scorer_controls.json"), encoding="utf-8"))
    return items, ev, ctl


def self_test():
    rng = random.Random(1)
    def mk(n, acc, sha_pref, pt=1000, fin="stop", flip=None):
        return {f"t|{i}": {"task": "t", "doc_id": i, "correct": int((flip or (lambda i: rng.random() < acc))(i)), "request_sha": f"r{i}", "output_sha": f"{sha_pref}{i}",
                           "prompt_tokens": pt, "finish_reason": fin} for i in range(n)}
    base = {i: rng.random() < 0.8 for i in range(1000)}
    ref = mk(1000, 0, "o", flip=lambda i: base[i])
    same = mk(1000, 0, "o", flip=lambda i: base[i])
    worse = mk(1000, 0, "q", pt=975, flip=lambda i: base[i] and i % 10 != 0)
    items = {(REF, t, r): ref for t in TASKS for r in ("main", "repeat")}
    items.update({("N-FP8", t, "main"): same for t in TASKS}); items.update({("O-Q4", t, "main"): worse for t in TASKS}); items.update({("O-FP16", t, "main"): same for t in TASKS})
    ok_st = {"resident": True, "health": {"pass": True}}
    ev = [{"kind": "arm_start", "arm": a, "probe": {"user_one_word": {"prompt_tokens": 36 if a.startswith("N-") else 11}}, **ok_st} for a in ARMS]
    ev += [{"kind": "task_run", "arm": a, "task": t, "run": "main", "join": {"items": 1000, "unjoined": 0, "resp_vs_proxy_text_mismatch": 0}} for a in ARMS for t in TASKS]
    ctl = {"gsm8k_positive": {"strict_match": 1.0}, "gsm8k_negative": {"strict_match": 0.01}, "mmlu_positive": {"exact_match": 1.0}, "mmlu_negative": {"exact_match": 0.25},
           "ifeval_positive_constructed": {"prompt_level_strict": 1.0}, "ifeval_negative_empty": {"prompt_level_strict_non_eligible": 0.1}, "ifeval_negative_permuted": {"prompt_level_strict": 0.1}}
    x = analyse(items, ev, ctl)
    cases = [("identical arm -> diff 0, within", x["paired_vs_ref"]["N-FP8|gsm8k"]["paired"]["diff_pp"] == 0 and x["paired_vs_ref"]["N-FP8|gsm8k"]["verdict"] == "within"),
             ("arm losing 10% of the reference's correct items -> outside, McNemar p tiny", x["paired_vs_ref"]["O-Q4|gsm8k"]["verdict"] == "outside" and x["paired_vs_ref"]["O-Q4|gsm8k"]["paired"]["mcnemar_p"] < 1e-6),
             ("Ollama template offset 25 tokens absorbed: 975+25 vs 1000 -> G2 pass", x["cells"]["O-Q4|gsm8k"]["g2"]["pass"] is True),
             ("wilson on 800/1000", x["cells"]["N-BF16|gsm8k"]["wilson95_pct"] == wilson(sum(base.values()), 1000))]
    items2 = dict(items); items2[("O-FP16", "gsm8k", "main")] = mk(1000, 0, "o", pt=900, flip=lambda i: base[i])
    y = analyse(items2, ev, ctl)
    cases.append(("prompt tokens 10% short (truncation) -> G2 fails, cell null", y["cells"]["O-FP16|gsm8k"]["accuracy_pct"] is None and y["paired_vs_ref"]["O-FP16|gsm8k"]["verdict"] is None))
    items3 = dict(items); items3[("N-FP8", "ifeval", "main")] = {k: dict(v, finish_reason="length" if v["doc_id"] < 20 else "stop") for k, v in same.items()}
    cases.append(("2% length -> G2 fails", analyse(items3, ev, ctl)["cells"]["N-FP8|ifeval"]["g2"]["pass"] is False))
    items4 = dict(items); items4[("N-FP8", "mmlu", "main")] = {k: dict(v, request_sha="x" if v["doc_id"] == 5 else v["request_sha"]) for k, v in same.items()}
    cases.append(("one request sha differs -> G4 fails", analyse(items4, ev, ctl)["cells"]["N-FP8|mmlu"]["g4"]["pass"] is False))
    items5 = dict(items); items5[(REF, "mmlu", "repeat")] = mk(1000, 0, "o", flip=lambda i: base[i] if i % 30 else not base[i])
    z = analyse(items5, ev, ctl)
    cases.append(("noise floor 3.4 pp > 2 -> verdicts null for that task only", z["paired_vs_ref"]["N-FP8|mmlu"]["verdict"] is None and z["paired_vs_ref"]["N-FP8|gsm8k"]["verdict"] == "within"))
    cases.append(("G1 failure -> task cells null", analyse(items, ev, dict(ctl, gsm8k_positive={"strict_match": 0.99}))["cells"]["N-FP8|gsm8k"]["accuracy_pct"] is None))
    ev2 = [dict(e, health={"pass": False}) if e.get("arm") == "O-FP16" and e["kind"] == "arm_start" else e for e in ev]
    cases.append(("G3 failure -> arm cells null", analyse(items, ev2, ctl)["cells"]["O-FP16|ifeval"]["accuracy_pct"] is None))
    items6 = dict(items); items6[("O-Q4", "gsm8k", "main")] = {k: dict(v, finish_reason="length" if v["doc_id"] % 10 == 0 else "stop") for k, v in worse.items()}
    s6 = analyse(items6, ev, ctl)["paired_vs_ref"]["O-Q4|gsm8k"]
    cases.append(("sensitivity drops the capped items: the 10% the arm lost are exactly those -> diff 0 on the rest", s6["sensitivity_items_where_neither_hit_the_cap"]["diff_pp"] == 0 and s6["sensitivity_items_where_neither_hit_the_cap"]["items"] == 900))
    cases.append(("mcnemar(0,0)=1 and (0,10) ~ 0.00195", mcnemar(0, 0) == 1.0 and abs(mcnemar(0, 10) - 0.001953125) < 1e-9))
    cases.append(("verdict boundaries", verdict([-1.9, 1.9]) == "within" and verdict([-4, -2.1]) == "outside" and verdict([-2.5, 0.5]) == "undetermined"))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    items, ev, ctl = load(d)
    a = analyse(items, ev, ctl)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False, sort_keys=True)
    for k, c in a["cells"].items():
        print(k, c.get("accuracy_pct"), c.get("wilson95_pct"), c.get("reasons"))
    for k, p in a["paired_vs_ref"].items():
        print(k, p["paired"] and (p["paired"]["diff_pp"], p["paired"]["ci95_pp"], p["paired"]["mcnemar_p"]), p["verdict"], p["verdict_null_reasons"])
    print("noise", {t: v and (v["correctness_disagreement_pp"], v["diff_pp"]) for t, v in a["noise_floor"].items()})
    print("conc", a["concurrency_fp8_gsm8k"]["accuracy_pct"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
