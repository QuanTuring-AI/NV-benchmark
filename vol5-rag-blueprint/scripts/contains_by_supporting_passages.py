#!/usr/bin/env python3
"""Vol.5 · the share of answers that contain the official answer, split by how many of a question's two supporting
passages were among the ten passages the answer model saw (both / one / none), for arm P and arm P*.

The inputs are the per-question tables of the two arms (one line per question: query_id, contains, f1, refusal, top10;
no answer text), kept outside the repository as supplement 8 says, and results/question_set/hotpotqa_ids.jsonl for
the supporting passages. Their SHA-256 are written into the output. Before writing, the counts are checked against
the arms' score files in this folder (questions per stratum and answers containing the official answer); a table that
does not agree is refused.

usage: contains_by_supporting_passages.py --p FILE --pstar FILE --out results/p_star/contains_by_supporting_passages.json
"""
import argparse, hashlib, json, os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDS = os.path.join(HERE, "results", "question_set", "hotpotqa_ids.jsonl")
SCORES = {"P": os.path.join(HERE, "results", "night3", "p_score.json"), "P*": os.path.join(HERE, "results", "p_star", "p_star_score.json")}
NAMES = {2: "both", 1: "one", 0: "none"}


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def strata(table, support):
    rows = [json.loads(l) for l in open(table, encoding="utf-8") if l.strip()]
    if len(rows) != len({r["query_id"] for r in rows}) or {r["query_id"] for r in rows} != set(support):
        raise ValueError(f"{table}: not one line for each question of the question set")
    out = {n: {"questions": 0, "contains": 0} for n in NAMES.values()}
    for r in rows:
        s = out[NAMES[len(support[r["query_id"]] & set(r["top10"]))]]
        s["questions"] += 1; s["contains"] += int(r["contains"])
    for s in out.values():
        s["contains_rate"] = s["contains"] / s["questions"] if s["questions"] else None
    return out, sum(int(r["contains"]) for r in rows)


def main():
    ap = argparse.ArgumentParser()
    for x in ("--p", "--pstar", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    support = {}
    for l in open(IDS, encoding="utf-8"):
        r = json.loads(l); support[r["query_id"]] = set(r["gold_passages"])
    rec = {"what": "answers that contain the official answer, by the number of the two supporting passages among the ten passages sent",
           "inputs": {"P": {"file": os.path.basename(a.p), "sha256": sha(a.p)}, "P*": {"file": os.path.basename(a.pstar), "sha256": sha(a.pstar)},
                      "supporting_passages": {"file": "results/question_set/hotpotqa_ids.jsonl", "sha256": sha(IDS)}},
           "arms": {}}
    for arm, table in (("P", a.p), ("P*", a.pstar)):
        by, total = strata(table, support)
        score = json.load(open(SCORES[arm], encoding="utf-8"))
        if {n: by[n]["questions"] for n in NAMES.values()} != score["supporting_passages_among_the_ten"]:
            raise ValueError(f"{arm}: the strata do not hold the questions the score file gives")
        if total != round(score["score"]["contains_rate"] * score["score"]["questions"]):
            raise ValueError(f"{arm}: the table's answers containing the official answer differ from the score file")
        rec["arms"][arm] = {"contains": total, "by_supporting_passages_among_the_ten": by}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({arm: {n: round(v["contains_rate"], 3) for n, v in x["by_supporting_passages_among_the_ten"].items()} for arm, x in rec["arms"].items()}))


if __name__ == "__main__":
    main()
