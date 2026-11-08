#!/usr/bin/env python3
"""Vol.5 · are Vol.4's whole-corpus vectors already of unit length? Every vector of one corpus, read from the 16-bit copy
with each piece proven against the recorded SHA-256 of its 32-bit file (vol4-retriever/scripts/fp16_store.py), and the
queries; the length of every vector in float64; the smallest and largest per piece and over all.
If every length is 1 within float rounding, ordering by L2 distance, by inner product and by cosine is the same.
usage: unit_length.py --fp16-dir DIR --checkpoints FILE --out FILE
"""
import argparse, json, os, sys, time

import numpy as np

V5 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(V5), "vol4-retriever", "scripts"))
import fp16_store as F, search_whole_corpus as S  # noqa: E402


def lengths(x):
    return np.sqrt(np.einsum("ij,ij->i", x.astype(np.float64), x.astype(np.float64)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fp16-dir", required=True); ap.add_argument("--checkpoints", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pieces, qrec, total = S.pieces_from_checkpoints(a.checkpoints)
    per, lo, hi, n = [], np.inf, -np.inf, 0
    for vf, vsha, idf, idsha, rows in pieces:
        v, _ = F.piece_from_fp16(os.path.join(a.fp16_dir, vf), vsha)
        ln = lengths(v); per.append({"piece": vf, "vectors": int(len(ln)), "min": float(ln.min()), "max": float(ln.max())})
        lo, hi, n = min(lo, ln.min()), max(hi, ln.max()), n + len(ln)
    q, _ = S.read_npy_checked(os.path.join(a.fp16_dir, "queries.npy"), qrec["queries_sha256"]); ql = lengths(q)
    out = {"what": "the length of every vector of one whole corpus as Vol.4 stored it, and of its queries", "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "passages": {"vectors": int(n), "expected": int(total), "min": float(lo), "max": float(hi)},
           "queries": {"vectors": int(len(ql)), "min": float(ql.min()), "max": float(ql.max())},
           "reading": "unit length within float rounding" if max(abs(lo - 1), abs(hi - 1), abs(ql.min() - 1), abs(ql.max() - 1)) < 1e-3 else "not of unit length",
           "per_piece": per, "program": "scripts/unit_length.py"}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(out["passages"], out["queries"], out["reading"])


if __name__ == "__main__":
    main()
