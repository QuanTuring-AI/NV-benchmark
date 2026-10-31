#!/usr/bin/env python3
"""Vol.4 · compare two sets of vectors of the same texts, row by row: the cosine of each pair.

Used where two cells differ in one condition (a library version, a precision) and the question is whether the encoder
gave the same vectors, before any ranking is looked at. Both folders hold queries.npy, corpus.npy and ids.json as
written by embed_cell.py encode; the ids must be the same in the same order, or the comparison is refused. With --first N
only the first N passages are compared (the second folder may then hold only those).

usage: compare_embeddings.py --a DIR --b DIR --out FILE.json [--first N] [--label-a TEXT --label-b TEXT]
"""
import argparse, json, os, sys

import numpy as np


def stats(x, y):
    x = np.asarray(x, dtype=np.float64); y = np.asarray(y, dtype=np.float64)
    cos = (x * y).sum(axis=1) / (np.linalg.norm(x, axis=1) * np.linalg.norm(y, axis=1))
    return {"pairs": int(len(cos)), "cosine_min": float(cos.min()), "cosine_p01": float(np.percentile(cos, 1)), "cosine_median": float(np.median(cos)),
            "cosine_mean": float(cos.mean()), "pairs_below_0.999": int((cos < 0.999).sum()), "pairs_below_0.99": int((cos < 0.99).sum()),
            "rows_equal_bit_for_bit": int((np.asarray(x, dtype=np.float32) == np.asarray(y, dtype=np.float32)).all(axis=1).sum()),
            "largest_absolute_difference": float(np.abs(x - y).max())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True); ap.add_argument("--b", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--first", type=int); ap.add_argument("--label-a", default="a"); ap.add_argument("--label-b", default="b")
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    out = {"what": "cosine of each pair of vectors of the same text in two cells", "a": a.label_a, "b": a.label_b, "first": a.first}
    ia = json.load(open(os.path.join(a.a, "ids.json"), encoding="utf-8")); ib = json.load(open(os.path.join(a.b, "ids.json"), encoding="utf-8"))
    for kind, key, name in (("queries", "query_ids", "queries.npy"), ("passages", "passage_ids", "corpus.npy")):
        xa = np.load(os.path.join(a.a, name), mmap_mode="r"); xb = np.load(os.path.join(a.b, name), mmap_mode="r")
        na, nb = ia[key], ib[key]
        if kind == "passages" and a.first:
            na, nb, xa, xb = na[:a.first], nb[:a.first], xa[:a.first], xb[:a.first]
        if na != nb:
            raise SystemExit(f"refused: the {kind} of the two folders are not the same ids in the same order")
        if xa.shape != xb.shape:
            raise SystemExit(f"refused: the {kind} have shapes {xa.shape} and {xb.shape}")
        out[kind] = stats(xa, xb)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: {m: out[k][m] for m in ("pairs", "cosine_min", "cosine_median", "rows_equal_bit_for_bit")} for k in ("queries", "passages")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
