#!/usr/bin/env python3
"""Vol.5 · scores of arm P* (supplement 8): the answer model given the reranked top 10 of exact search. From the answer
files kept outside the repository; the scoring is eval/hotpot_scoring.py, the same as every other arm.

  score              contains, F1, EM, refusals by pattern, finish reasons of P*
  paired_Pstar_P     P* against arm P on the same 7,405 questions (only_a = P* right and P wrong), exact McNemar
  paired_Pstar_O     P* against arm O (only_a = P* right and O wrong)
  supporting_passages_among_the_ten   both / one / none of a question's two supporting passages in P*'s ten
  ten_equal_to_P     questions whose ten passages are the same set as arm P's

usage: score_p_star.py --pstar FILE --p FILE --o FILE --gold FILE --ids FILE --pstar-ids FILE --p-ids FILE --out FILE
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "eval"))
import hotpot_scoring as H  # noqa: E402


def last(path):
    """One record per question: a resumed question keeps its ok record."""
    out = {}
    for l in open(path, encoding="utf-8"):
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            continue
        if r["query_id"] not in out or r.get("status") == "ok":
            out[r["query_id"]] = r
    return out


def rows(d, gold):
    return [{"query_id": q, "answer": r.get("answer") if r.get("status") == "ok" else None, "gold": gold[q]} for q, r in sorted(d.items())]


def id_sets(path):
    return {json.loads(l)["query_id"]: set(json.loads(l)["gold_passages"]) for l in open(path, encoding="utf-8")}


def score(pstar, p, o, gold, sup, ten_star, ten_p):
    if not (set(pstar) == set(p) == set(o) == set(gold) == set(sup) == set(ten_star)):
        raise ValueError("the arms, the gold answers and the id tables do not hold the same questions")
    k = [len(sup[q] & ten_star[q]) for q in sorted(sup)]
    fr = {}
    for r in pstar.values():
        fr[r.get("finish_reason")] = fr.get(r.get("finish_reason"), 0) + 1
    return {"arm": "P*", "score": H.score_answers(rows(pstar, gold)), "finish_reason": fr,
            "paired_Pstar_P": H.paired(rows(pstar, gold), rows(p, gold)),
            "paired_Pstar_O": H.paired(rows(pstar, gold), rows(o, gold)),
            "supporting_passages_among_the_ten": {"both": k.count(2), "one": k.count(1), "none": k.count(0)},
            "ten_equal_to_P": sum(1 for q in ten_star if ten_star[q] == ten_p.get(q))}


def main():
    ap = argparse.ArgumentParser()
    for x in ("--pstar", "--p", "--o", "--gold", "--ids", "--pstar-ids", "--p-ids", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    gold = {json.loads(l)["query_id"]: json.loads(l)["answer"] for l in open(a.gold, encoding="utf-8")}
    rec = score(last(a.pstar), last(a.p), last(a.o), gold, id_sets(a.ids), id_sets(a.pstar_ids), id_sets(a.p_ids))
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(rec)[:600])


if __name__ == "__main__":
    main()
