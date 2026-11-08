#!/usr/bin/env python3
"""Vol.5 · scores of arm P (C2) and of cell R, from the answer files kept outside the repository; the scoring is
eval/hotpot_scoring.py (contains main, F1, EM, Wilson, exact McNemar), the token counts the model's tokenizer.json.

  p   arm P on the 7,405 questions: the score, finish reasons, how many reached the answer limit without closing their
      reasoning, refusals by pattern; paired against arms N and O (same questions); the number of questions whose
      ten passages hold both, one or none of the two supporting passages
  r   cell R (the reasoning parser on) against arm P on the same 200 questions: reasoning separated, '</think>' left in
      the content, reasoning tokens (median, how many above 256), contains, paired

usage: score_p_r.py p --p FILE --n FILE --o FILE --gold FILE --ids FILE --p-ids FILE --out FILE
       score_p_r.py r --r FILE --p FILE --gold FILE --tokenizer FILE --out FILE
"""
import argparse, json, os, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "eval"))
import hotpot_scoring as H  # noqa: E402


def last(path):
    out = {}
    for l in open(path, encoding="utf-8"):
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            continue
        if r["query_id"] not in out or r.get("status") == "ok":
            out[r["query_id"]] = r
    return out


def rows(d, gold, keep=None):
    return [{"query_id": q, "answer": r.get("answer") if r.get("status") == "ok" else None, "gold": gold[q]} for q, r in sorted(d.items()) if keep is None or q in keep]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("p", "r"))
    for x in ("--p", "--n", "--o", "--r", "--gold", "--ids", "--p-ids", "--tokenizer", "--out"):
        ap.add_argument(x)
    a = ap.parse_args()
    gold = {json.loads(l)["query_id"]: json.loads(l)["answer"] for l in open(a.gold, encoding="utf-8")}
    P = last(a.p)
    if a.cmd == "p":
        N, O = last(a.n), last(a.o)
        s = H.score_answers(rows(P, gold))
        fr = {}
        for r in P.values():
            fr[r.get("finish_reason")] = fr.get(r.get("finish_reason"), 0) + 1
        sup = {json.loads(l)["query_id"]: set(json.loads(l)["gold_passages"]) for l in open(a.ids, encoding="utf-8")}
        ten = {json.loads(l)["query_id"]: set(json.loads(l)["gold_passages"]) for l in open(a.p_ids, encoding="utf-8")}
        k = [len(sup[q] & ten[q]) for q in sup]
        rec = {"arm": "P", "score": s, "finish_reason": fr, "no_close_tag": sum(1 for r in P.values() if r.get("strip_rule") != "after_last_close_tag"),
               "paired_P_N": H.paired(rows(P, gold), rows(N, gold)), "paired_P_O": H.paired(rows(P, gold), rows(O, gold)),
               "supporting_passages_among_the_ten": {"both": k.count(2), "one": k.count(1), "none": k.count(0)}}
    else:
        from tokenizers import Tokenizer
        tok = Tokenizer.from_file(a.tokenizer); n = lambda s: len(tok.encode(s or "", add_special_tokens=False).ids)
        R = last(a.r); q = sorted(R)

        def stats(D, sep):
            reas = [n(D[x].get("reasoning_content")) if sep else n((D[x].get("content") or "").rsplit("</think>", 1)[0]) for x in q]
            return {"answered": sum(D[x].get("status") == "ok" for x in q), "reasoning_separated": sum(bool(D[x].get("reasoning_content")) for x in q),
                    "content_holds_close_tag": sum("</think>" in (D[x].get("content") or "") for x in q), "reasoning_tokens_median": st.median(reas),
                    "reasoning_tokens_above_256": sum(t > 256 for t in reas), "contains": sum(H.contains(D[x].get("answer") or "", gold[x]) for x in q)}
        rec = {"questions": len(q), "R": stats(R, True), "P_same_questions": stats(P, False), "paired_R_P": H.paired(rows(R, gold), rows(P, gold, set(q)))}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(rec)[:600])


if __name__ == "__main__":
    main()
