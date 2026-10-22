#!/usr/bin/env python3
"""Vol.5 · control (b1) of the second addendum to night 1: does an exact search inside Elasticsearch (script_score
cosine, es_ann_vs_exact.py exact) give the same top 100 as numpy's exact search over the same vectors (slice_exact.py)?

Elasticsearch's script_score reports cosine + 1 (scores must not be negative), numpy the inner product of unit-length
vectors; the program subtracts 1. Two passages count as an equal-score swap when they are absent from one side's top
100 and their score differs from that side's 100th score by at most TIE (5e-5: over five times the largest difference
of one passage's score between the two sides on the first 100 questions, 9e-6; the 16-bit vectors are read as 32-bit
floats on both sides, the two sums run in a different order, and the runs print six decimals). Every swap is listed.

Rule: per question, the top 100 sets are equal once the listed equal-score swaps are set aside; the pass line is every
question (1.0). A set difference that is not an equal-score swap fails the question.
usage: exact_equal_check.py --es-run FILE --numpy-run FILE --out FILE
"""
import argparse, collections, json, sys

TIE, TOP = 5e-5, 100


def read(path, minus):
    run = collections.defaultdict(list)
    for line in open(path, encoding="utf-8"):
        q, _, d, rank, score, _tag = line.split()
        run[q].append((int(rank), d, float(score) - minus))
    return {q: [(d, s) for _, d, s in sorted(v)][:TOP] for q, v in run.items()}


def check(es, npy):
    per, fails, swaps = {}, [], []
    if set(es) != set(npy):
        raise SystemExit(f"refused: the two runs hold different questions ({len(es)} vs {len(npy)})")
    for q in sorted(npy):
        a, b = dict(es[q]), dict(npy[q])
        last_a, last_b = es[q][-1][1], npy[q][-1][1]
        only_a, only_b = set(a) - set(b), set(b) - set(a)
        ok = all(abs(a[d] - last_a) <= TIE for d in only_a) and all(abs(b[d] - last_b) <= TIE for d in only_b)
        if only_a or only_b:
            swaps.append({"question": q, "only_es": sorted(only_a), "only_numpy": sorted(only_b), "es_100th": last_a, "numpy_100th": last_b, "equal_score": ok})
        per[q] = ok
        if not ok:
            fails.append(q)
    return per, fails, swaps


def main():
    ap = argparse.ArgumentParser()
    for x in ("--es-run", "--numpy-run", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    es, npy = read(a.es_run, 1.0), read(a.numpy_run, 0.0)
    per, fails, swaps = check(es, npy)
    worst = max(abs(dict(es[q])[d] - s) for q in npy for d, s in npy[q] if d in dict(es[q]))
    rec = {"questions": len(per), "passed": sum(per.values()), "pass_share": sum(per.values()) / len(per), "pass": not fails,
           "failed_questions": fails, "equal_score_swaps": swaps, "largest_score_difference_on_shared_passages": worst, "tie": TIE}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: rec[k] for k in ("questions", "passed", "pass", "largest_score_difference_on_shared_passages")} | {"swaps": len(swaps)}))
    return 0 if rec["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
