#!/usr/bin/env python3
"""Vol.5 · measures of answer files that have no gold answer (answer_arms.py output), for cells C3 and MIRACL zh P,
and the hand-labelling sheet of C3.

  refusals  per answer file: answered calls, finish reasons, refusals by the volume's pattern list (rag_eval.py
            refused_by_pattern) on the final answer
  judged    MIRACL zh P: for each question, whether any of the passages sent to the answer model (the id table's
            gold_passages field, which holds the reranked 10) is judged relevant (relevance > 0) in the qrels
  sheet     C3: 50 answers drawn with seed 20261020 from the answer file, written for labelling by hand
            (refusal / answers anyway / other) with the pattern's verdict hidden; a second call with --labels
            compares the hand labels with the pattern (agreement, and both kinds of disagreement)

usage: answers_extra.py refusals --answers FILE --out FILE
       answers_extra.py judged --ids FILE --qrels FILE(trec) --out FILE
       answers_extra.py sheet --answers FILE --queries FILE --out FILE [--labels FILE]
"""
import argparse, json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(V5, "eval"))
from rag_eval import refused_by_pattern, wilson  # noqa: E402


def records(path):
    out = {}
    for l in open(path, encoding="utf-8"):
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            continue
        if r["query_id"] not in out or r.get("status") == "ok":
            out[r["query_id"]] = r
    return out


def refusals(a):
    rs = records(a.answers); ok = [r for r in rs.values() if r.get("status") == "ok"]
    n_ref = sum(refused_by_pattern(r["answer"] or "") for r in ok); fr = {}
    for r in rs.values():
        k = r.get("finish_reason") if r.get("status") == "ok" else r.get("status"); fr[k] = fr.get(k, 0) + 1
    lo, hi = wilson(n_ref, len(rs))
    rec = {"questions": len(rs), "answered_calls": len(ok), "refused_by_pattern": n_ref, "refusal_rate": n_ref / len(rs) if rs else None,
           "refusal_wilson95": [lo, hi], "finish_reason": fr, "strip_rule": {k: sum(1 for r in ok if r.get("strip_rule") == k) for k in ("content", "after_last_close_tag", "none")}}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(rec))


def judged(a):
    rel = {}
    for line in open(a.qrels, encoding="utf-8"):
        p = line.split()
        if len(p) == 4 and int(p[3]) > 0:
            rel.setdefault(p[0], set()).add(p[2])
    rows = [json.loads(l) for l in open(a.ids, encoding="utf-8")]
    hit = [r["query_id"] for r in rows if rel.get(r["query_id"], set()) & set(r["gold_passages"])]
    lo, hi = wilson(len(hit), len(rows))
    rec = {"questions": len(rows), "with_a_judged_relevant_passage_among_those_sent": len(hit), "share": len(hit) / len(rows), "wilson95": [lo, hi],
           "questions_without_any_judgement": sum(1 for r in rows if r["query_id"] not in rel)}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(rec))


def sheet(a):
    rs = records(a.answers); queries = {r["_id"]: r["text"] for r in (json.loads(l) for l in open(a.queries, encoding="utf-8"))}
    pick = sorted(random.Random(20261020).sample(sorted(q for q, r in rs.items() if r.get("status") == "ok"), 50))
    if not a.labels:
        with open(a.out, "w", encoding="utf-8", newline="\n") as w:
            for q in pick:
                w.write(json.dumps({"query_id": q, "question": queries[q], "answer": rs[q]["answer"], "label": None}, ensure_ascii=False) + "\n")
        print(json.dumps({"sheet": a.out, "items": len(pick)}))
        return
    lab = {r["query_id"]: r["label"] for r in (json.loads(l) for l in open(a.labels, encoding="utf-8"))}
    if set(lab) != set(pick) or any(v not in ("refusal", "answers_anyway", "other") for v in lab.values()):
        raise SystemExit("refused: the labels are not the 50 drawn answers, or a label is not refusal / answers_anyway / other")
    pat = {q: refused_by_pattern(rs[q]["answer"] or "") for q in pick}
    rec = {"items": 50, "hand_refusal": sum(v == "refusal" for v in lab.values()), "pattern_refusal": sum(pat.values()),
           "agree": sum((lab[q] == "refusal") == pat[q] for q in pick), "pattern_yes_hand_no": [q for q in pick if pat[q] and lab[q] != "refusal"],
           "pattern_no_hand_yes": [q for q in pick if not pat[q] and lab[q] == "refusal"], "hand_labels": {k: sum(v == k for v in lab.values()) for k in ("refusal", "answers_anyway", "other")}}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: v for k, v in rec.items() if not isinstance(v, list)}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("refusals", "judged", "sheet"))
    for x in ("--answers", "--out", "--ids", "--qrels", "--queries", "--labels"):
        ap.add_argument(x)
    a = ap.parse_args()
    {"refusals": refusals, "judged": judged, "sheet": sheet}[a.cmd](a)
