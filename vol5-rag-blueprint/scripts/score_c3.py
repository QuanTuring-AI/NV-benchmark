#!/usr/bin/env python3
"""Vol.5 · C3: of the 200 questions whose supporting passages were kept out, how many answers still contain the gold
answer (the model knew it without them), against arm P on the same 200 questions (not kept out); scored with
eval/hotpot_scoring.py (contains, Wilson, exact McNemar), from the answer files kept outside the repository.
usage: score_c3.py --c3 FILE --p FILE --gold FILE --out FILE
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from score_p_r import last, rows  # noqa: E402
import hotpot_scoring as H  # noqa: E402  (score_p_r puts eval/ on the path)


def main():
    ap = argparse.ArgumentParser()
    for x in ("--c3", "--p", "--gold", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    gold = {json.loads(l)["query_id"]: json.loads(l)["answer"] for l in open(a.gold, encoding="utf-8")}
    C, P = last(a.c3), last(a.p); q = set(C)
    rec = {"questions": len(q), "C3": H.score_answers(rows(C, gold)), "P_same_questions": H.score_answers(rows(P, gold, q)),
           "paired_C3_P": H.paired(rows(C, gold), rows(P, gold, q))}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"C3_contains": rec["C3"]["contains"], "C3_rate": rec["C3"]["contains_rate"], "P_contains": rec["P_same_questions"]["contains"], "paired": rec["paired_C3_P"]}))


if __name__ == "__main__":
    main()
