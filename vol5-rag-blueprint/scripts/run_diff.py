#!/usr/bin/env python3
"""Vol.5 · two TREC runs of the same questions, question by question: the same passages in the same order, the same
set in another order, or different sets (listed with how many of the first k differ). Used for the clean-window rerun
of C1 against the first run of the same index.
usage: run_diff.py --a FILE --b FILE --out FILE [--k 100]
"""
import argparse, collections, json


def read(p, k):
    r = collections.defaultdict(list)
    for line in open(p, encoding="utf-8"):
        q, _, d, rank, _s, _t = line.split(); r[q].append((int(rank), d))
    return {q: [d for _, d in sorted(v)][:k] for q, v in r.items()}


def main():
    ap = argparse.ArgumentParser()
    for x in ("--a", "--b", "--out"):
        ap.add_argument(x, required=True)
    ap.add_argument("--k", type=int, default=100)
    a = ap.parse_args()
    A, B = read(a.a, a.k), read(a.b, a.k)
    if set(A) != set(B):
        raise SystemExit(f"refused: the runs hold different questions ({len(A)} vs {len(B)})")
    same, reordered, differ = 0, [], []
    for q in sorted(A):
        if A[q] == B[q]:
            same += 1
        elif set(A[q]) == set(B[q]):
            reordered.append(q)
        else:
            differ.append({"query_id": q, "passages_not_shared": len(set(A[q]) - set(B[q]))})
    rec = {"questions": len(A), "k": a.k, "identical": same, "same_set_other_order": len(reordered), "different_sets": len(differ),
           "reordered": reordered, "differ": differ}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: rec[k] for k in ("questions", "identical", "same_set_other_order", "different_sets")}))


if __name__ == "__main__":
    main()
