#!/usr/bin/env python3
"""Vol.5 · exact top 100 over the first N passages of a whole corpus (the slice of control (b) and of C1's validity
gate), for the given questions, from Vol.4's vectors: the 16-bit store read and proven piece by piece
(fp16_store.piece_from_fp16), the queries checked against their recorded SHA-256. The score is the inner product of the
stored vectors (they are of unit length, checked for MIRACL zh in the first Vol.5 night; this program checks every
passage it reads and refuses a length off by more than 1e-3), which orders like cosine. Equal scores are ordered by
passage position. Writes a TREC run.

usage: slice_exact.py --fp16-dir DIR --checkpoints FILE --n N --ids FILE(json list of query ids) --out-run FILE
"""
import argparse, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(V5), "vol4-retriever", "scripts"))
TOP = 100


def main():
    ap = argparse.ArgumentParser()
    for x in ("--fp16-dir", "--checkpoints", "--ids", "--out-run"):
        ap.add_argument(x, required=True)
    ap.add_argument("--n", type=int, required=True)
    a = ap.parse_args()
    import fp16_store as F, search_whole_corpus as S
    pieces, qrec, _ = S.pieces_from_checkpoints(a.checkpoints)
    q, _ = S.read_npy_checked(os.path.join(a.fp16_dir, "queries.npy"), qrec["queries_sha256"])
    qids = json.load(open(os.path.join(a.fp16_dir, "query_ids.json"), encoding="utf-8")); pos = {x: i for i, x in enumerate(qids)}
    want = json.load(open(a.ids, encoding="utf-8")); Q = np.stack([q[pos[x]] for x in want]).astype(np.float32)
    vecs, pids, rows = [], [], 0
    for vf, vsha, idf, idsha, n in pieces:
        if rows >= a.n:
            break
        v, _ = F.piece_from_fp16(os.path.join(a.fp16_dir, vf), vsha)
        if S.sha256_file(os.path.join(a.fp16_dir, idf)) != idsha:
            raise SystemExit(f"refused: {idf} does not have the recorded SHA-256")
        take = min(n, a.n - rows); vecs.append(v[:take]); pids += json.load(open(os.path.join(a.fp16_dir, idf), encoding="utf-8"))[:take]; rows += take
    X = np.concatenate(vecs)
    lengths = np.linalg.norm(X.astype(np.float64), axis=1)
    if np.abs(lengths - 1).max() > 1e-3:
        raise SystemExit(f"refused: a stored vector is not of unit length (off by {np.abs(lengths - 1).max():.2e})")
    S_ = Q @ X.T
    os.makedirs(os.path.dirname(os.path.abspath(a.out_run)), exist_ok=True)
    with open(a.out_run, "w", encoding="utf-8", newline="\n") as f:
        for qi, qid in enumerate(want):
            order = np.lexsort((np.arange(len(pids)), -S_[qi]))[:TOP]
            for rank, j in enumerate(order, 1):
                f.write(f"{qid} Q0 {pids[j]} {rank} {float(S_[qi, j]):.6f} numpy-exact\n")
    print(json.dumps({"passages": len(pids), "queries": len(want), "out": a.out_run}))


if __name__ == "__main__":
    main()
