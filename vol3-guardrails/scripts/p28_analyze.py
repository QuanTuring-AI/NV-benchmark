#!/usr/bin/env python3
"""P28 · analysis of the judge-isolation run (judgements.jsonl from p28_judge_isolation.py).
Rules frozen in prediction_p28.json.

Preconditions (any failure -> every conclusion field is null):
  P1  0 call errors, every text judged REPS times by both judges
  P2  mechanism, positive: the synthetic violating control -> every call of both judges answers Yes
  P3  mechanism, negative: the synthetic benign control    -> every call of both judges answers No
  P3c corpus,    negative: the e3_clean_06 378-token variant (P19 arm C round 1, known No) -> both judges answer No
  P4  config effective: every J3 call reports completion_tokens == 3

Conclusions (corpus texts only; the controls are never counted in a rate):
  agreement_majority  fraction of texts where the two judges' majority verdicts agree
  agreement_strict    fraction of texts where all calls of both judges give the same verdict
  self_consistency    per judge, fraction of texts where its own REPS calls agree  <- the denominator for reading agreement
  yes_rate            per judge, fraction of texts judged Yes (discrimination on this corpus)
  disagreements       every text where the majorities differ, verbatim head + all verdicts + J1024's explanation
usage: p28_analyze.py <run_dir> [--excluded excluded_segments.json] | --self-test"""
import collections, json, os, sys

CORPUS_NEGATIVE_CONTROL_SHA = "6cdb9aa521f7"  # prefix; the e3_clean_06 378-token variant, P19 arm C round 1 (judged No)


def verdicts(calls):
    return [(c.get("first_word") or "").strip().rstrip(".,:;").title() for c in calls]


def majority(vs):
    if not vs:
        return None
    c = collections.Counter(vs).most_common()
    return c[0][0] if (len(c) == 1 or c[0][1] > c[1][1]) else "TIE"


def analyze(recs, reps=3):
    by_kind = collections.defaultdict(list)
    for r in recs:
        by_kind[r["kind"]].append(r)
    corpus = by_kind["corpus"]
    errors = sum(1 for r in recs for j in r["judges"].values() for c in j if c.get("error"))
    shape_ok = all(len(r["judges"].get(j, [])) == reps for r in recs for j in ("J1024", "J3"))
    j3_tok = [c.get("completion_tokens") for r in recs for c in r["judges"].get("J3", [])]
    p4 = bool(j3_tok) and all(t == 3 for t in j3_tok)

    def ctrl_all(kind, want):
        rs = by_kind.get(kind, [])
        if not rs:
            return False, None
        seen = {j: verdicts(rs[0]["judges"].get(j, [])) for j in ("J1024", "J3")}
        return (len(rs) == 1 and all(v == want for vs in seen.values() for v in vs) and all(seen.values())), seen

    p2, p2_seen = ctrl_all("control_violating", "Yes")
    p3, p3_seen = ctrl_all("control_benign", "No")
    neg = next((r for r in corpus if r["sha256"].startswith(CORPUS_NEGATIVE_CONTROL_SHA)), None)
    neg_seen = {j: verdicts(neg["judges"].get(j, [])) for j in ("J1024", "J3")} if neg else None
    p3c = bool(neg) and all(v == "No" for vs in neg_seen.values() for v in vs)
    pre = {"P1_calls_ok": {"errors": errors, "shape_ok": shape_ok, "pass": errors == 0 and shape_ok},
           "P2_mechanism_positive_synthetic_violating": {"verdicts": p2_seen, "pass": p2},
           "P3_mechanism_negative_synthetic_benign": {"verdicts": p3_seen, "pass": p3},
           "P3c_corpus_negative_e3_clean_06_378token": {"sha256_prefix": CORPUS_NEGATIVE_CONTROL_SHA, "verdicts": neg_seen, "pass": p3c},
           "P4_config_effective": {"J3_calls": len(j3_tok), "calls_not_3_tokens": sum(1 for t in j3_tok if t != 3), "pass": p4}}
    ok = all(v["pass"] for v in pre.values())
    out = {"n": {k: len(v) for k, v in by_kind.items()}, "reps": reps, "preconditions": pre, "preconditions_pass": ok,
           "controls_note": "the two synthetic controls check the mechanism (judge alive, config loaded, template rendered); "
                            "they say nothing about the corpus and are never counted in a rate"}
    if not ok:
        out["conclusions"] = None
        return out
    maj = {r["id"]: {j: majority(verdicts(r["judges"][j])) for j in ("J1024", "J3")} for r in corpus}
    agree_maj = sum(1 for r in corpus if maj[r["id"]]["J1024"] == maj[r["id"]]["J3"] and maj[r["id"]]["J1024"] != "TIE")
    agree_strict = sum(1 for r in corpus if len(set(verdicts(r["judges"]["J1024"]) + verdicts(r["judges"]["J3"]))) == 1)
    selfc = {j: sum(1 for r in corpus if len(set(verdicts(r["judges"][j]))) == 1) for j in ("J1024", "J3")}
    yes = {j: sum(1 for r in corpus if maj[r["id"]][j] == "Yes") for j in ("J1024", "J3")}
    dis = []
    for r in corpus:
        m = maj[r["id"]]
        if m["J1024"] != m["J3"] or "TIE" in m.values():
            dis.append({"sha256": r["sha256"], "len": r["len"], "sources": r["sources"], "text_head": r["text_head"],
                        "J1024": verdicts(r["judges"]["J1024"]), "J3": verdicts(r["judges"]["J3"]),
                        "J1024_explanations": [c.get("completion_head") for c in r["judges"]["J1024"]]})
    n = len(corpus)
    pct = lambda x: round(100.0 * x / n, 1) if n else None
    out["conclusions"] = {
        "corpus_texts": n,
        "agreement_majority": {"texts": agree_maj, "pct": pct(agree_maj)},
        "agreement_strict_all_calls": {"texts": agree_strict, "pct": pct(agree_strict)},
        "self_consistency": {j: {"texts": selfc[j], "pct": pct(selfc[j])} for j in ("J1024", "J3")},
        "yes_rate_majority": {j: {"texts": yes[j], "pct": pct(yes[j])} for j in ("J1024", "J3")},
        "disagreements": dis,
        "reading": "agreement is bounded by self-consistency: a judge that does not repeat its own verdict cannot be "
                   "compared with the other judge on that text. Both rates are reported; neither is an absolute claim."}
    return out


def self_test():
    def mk(kind, sha, j1024, j3, tok3=3, head="No\n\nThe", err=False):
        f = lambda vs: [{"first_word": v, "completion_head": head, "completion_tokens": (86 if v else None),
                         "is_safe": v == "No", "duration_ms": 100.0} for v in vs]
        g = lambda vs: [{"first_word": v, "completion_head": "X", "completion_tokens": tok3, "is_safe": v == "No", "duration_ms": 50.0} for v in vs]
        r = {"id": sha, "kind": kind, "sha256": sha, "len": 100, "sources": ["x"], "text_head": "head",
             "judges": {"J1024": f(j1024), "J3": g(j3)}}
        if err:
            r["judges"]["J1024"][0] = {"error": "boom"}
        return r

    def base(**kw):
        recs = [mk("control_violating", "ctrlv", ["Yes"] * 3, ["Yes"] * 3), mk("control_benign", "ctrlb", ["No"] * 3, ["No"] * 3),
                mk("corpus", CORPUS_NEGATIVE_CONTROL_SHA + "aa", ["No"] * 3, ["No"] * 3)]
        for i in range(10):
            recs.append(mk("corpus", f"t{i:03d}", ["No"] * 3, ["No"] * 3))
        for k, v in kw.items():
            if k == "disagree":
                recs[5] = mk("corpus", "t002", ["Yes"] * 3, ["No"] * 3)
            elif k == "flaky1024":
                recs[6] = mk("corpus", "t003", ["Yes", "No", "No"], ["No"] * 3)
            elif k == "ctrl_violating_no":
                recs[0] = mk("control_violating", "ctrlv", ["Yes", "No", "Yes"], ["Yes"] * 3)
            elif k == "ctrl_benign_yes":
                recs[1] = mk("control_benign", "ctrlb", ["No"] * 3, ["Yes"] * 3)
            elif k == "corpus_neg_yes":
                recs[2] = mk("corpus", CORPUS_NEGATIVE_CONTROL_SHA + "aa", ["Yes"] * 3, ["No"] * 3)
            elif k == "j3_tokens":
                recs[4] = mk("corpus", "t001", ["No"] * 3, ["No"] * 3, tok3=41)
            elif k == "an_error":
                recs[4] = mk("corpus", "t001", ["No"] * 3, ["No"] * 3, err=True)
            elif k == "short_reps":
                recs[4]["judges"]["J3"] = recs[4]["judges"]["J3"][:2]
        return recs

    cases = []
    r = analyze(base())
    cases.append(("all pass -> conclusions, agreement 100%", r["conclusions"] is not None and r["conclusions"]["agreement_majority"]["pct"] == 100.0))
    cases.append(("controls excluded from the corpus count", r["conclusions"]["corpus_texts"] == 11))
    r = analyze(base(disagree=1))
    cases.append(("one disagreeing text -> listed and rate drops", len(r["conclusions"]["disagreements"]) == 1 and r["conclusions"]["agreement_majority"]["texts"] == 10))
    r = analyze(base(flaky1024=1))
    cases.append(("a judge not repeating itself -> self-consistency drops, majority still agrees",
                  r["conclusions"]["self_consistency"]["J1024"]["texts"] == 10 and r["conclusions"]["agreement_majority"]["texts"] == 11
                  and r["conclusions"]["agreement_strict_all_calls"]["texts"] == 10))
    r = analyze(base(ctrl_violating_no=1))
    cases.append(("violating control not Yes in every call -> P2 fails, conclusions null",
                  r["preconditions"]["P2_mechanism_positive_synthetic_violating"]["pass"] is False and r["conclusions"] is None))
    r = analyze(base(ctrl_benign_yes=1))
    cases.append(("benign control judged Yes -> P3 fails", r["preconditions"]["P3_mechanism_negative_synthetic_benign"]["pass"] is False and r["conclusions"] is None))
    r = analyze(base(corpus_neg_yes=1))
    cases.append(("corpus negative control judged Yes -> P3c fails", r["preconditions"]["P3c_corpus_negative_e3_clean_06_378token"]["pass"] is False and r["conclusions"] is None))
    r = analyze(base(j3_tokens=1))
    cases.append(("a J3 call above 3 tokens -> P4 fails", r["preconditions"]["P4_config_effective"]["pass"] is False and r["conclusions"] is None))
    r = analyze(base(an_error=1))
    cases.append(("a call error -> P1 fails", r["preconditions"]["P1_calls_ok"]["pass"] is False and r["conclusions"] is None))
    r = analyze(base(short_reps=1))
    cases.append(("a text judged fewer than reps times -> P1 fails", r["preconditions"]["P1_calls_ok"]["pass"] is False))
    recs = base(); recs[7] = mk("corpus", "t004", ["Yes", "No", "Maybe"], ["No"] * 3)
    r = analyze(recs)
    cases.append(("a three-way split counts as TIE and is listed", any(d["sha256"] == "t004" for d in r["conclusions"]["disagreements"])))
    recs = base(); recs[8] = mk("corpus", "t005", ["Yes", "No", "Maybe"], ["Yes", "No", "Maybe"])
    r = analyze(recs)
    cases.append(("both judges split three ways -> NOT agreement, and listed",
                  r["conclusions"]["agreement_majority"]["texts"] == 10 and any(d["sha256"] == "t005" for d in r["conclusions"]["disagreements"])))
    for name, okc in cases:
        print(("PASS " if okc else "FAIL ") + name)
    return 0 if all(c[1] for c in cases) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--self-test":
        sys.exit(self_test())
    d = sys.argv[1]
    recs = [json.loads(l) for l in open(os.path.join(d, "judgements.jsonl"), encoding="utf-8") if l.strip()]
    res = analyze(recs)
    if "--excluded" in sys.argv:
        ex = json.load(open(sys.argv[sys.argv.index("--excluded") + 1], encoding="utf-8"))
        res["excluded_segments"] = {"count": ex["count"], "rows_by_question": ex["rows_by_question"],
                                    "note": "answers that cannot be re-judged on the same text; see excluded_segments.json for each row and reason"}
    json.dump(res, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("n", "preconditions_pass", "conclusions") if k in res}, ensure_ascii=False, indent=1)[:3000])
