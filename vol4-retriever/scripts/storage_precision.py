#!/usr/bin/env python3
"""Vol.4 · what the retrieval quality of a stored corpus loses when its vectors are kept in fewer bits.

The vectors of a corpus exist as 32-bit floats (2,048 numbers per passage). This program reads them piece by piece,
turns each piece in memory into what a smaller store would hold, and runs the same exact search as
search_whole_corpus.py on the result: every query against every passage, cosine, no index. Nothing is written back:
no converted vector is stored anywhere.

  --precision fp32   the vectors as they are (the control: the metrics must be those of the existing whole-corpus run)
              fp16   every number as a 16-bit float (half the bytes)
              int8   every number as one signed byte (a quarter of the bytes): the vector is first divided by its
                     length, then multiplied by one scale for the whole corpus and rounded, values beyond +-127 cut.
                     The scale is 127 divided by the 99.9th percentile of the absolute values in the first piece
                     (unit vectors); it is computed once, recorded, and used for every piece.
Queries stay 32-bit floats in every case: the question is what the stored corpus costs.

  also       per piece, the share of its 32-bit numbers that a 16-bit float holds exactly (a NIM that computes in 16 bits
             may return only such numbers; then the fp16 store loses nothing by construction)
  reported   nDCG@10 and Recall@100 (retrieval_metrics.evaluate, as every cell of this volume), and, against a
             32-bit ranking given with --ref-run: per query the share of its first 100 passages that are also among the
             first 100 here (mean, lowest) and the number of queries whose first 10 are the same passages in the same order
  record     as search_whole_corpus.py: one line per piece as it is done, and a state file outside the repository, so
             that a stopped run goes on from the last piece
Seconds in the record are wall time on a host that does other work; they are not a speed of anything.

usage: storage_precision.py --precision fp32|fp16|int8 --dataset NAME --datasets DIR --emb-dir DIR --out-dir DIR --state FILE.npz
                            (--checkpoints FILE.jsonl | --piece-rows N) [--ref-run FILE.trec] [--stop-after-pieces N] [--top 100]
exit codes: 0 done · 5 stopped after --stop-after-pieces (a later call goes on) · 2 refused
"""
import argparse, json, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_whole_corpus as S  # noqa: E402  (pieces, checked reading, the search and its state: used as they are)

BYTES = {"fp32": 4, "fp16": 2, "int8": 1}
PCT = 99.9


def int8_scale(first_piece):
    """One scale for the corpus, from the unit vectors of its first piece. -> float"""
    u, _, _ = S.unit(first_piece)
    return float(127.0 / np.percentile(np.abs(u), PCT))


def stored(p, precision, scale=None):
    """The piece as a store of that precision would give it back, as float32. -> (matrix, share of values cut)"""
    if precision == "fp32":
        return p, 0.0
    if precision == "fp16":
        return p.astype(np.float16).astype(np.float32), 0.0
    u, _, _ = S.unit(p)
    x = np.rint(u * scale)
    cut = float((np.abs(x) > 127).mean())
    return np.clip(x, -127, 127).astype(np.int8).astype(np.float32), cut


def fp16_exact_share(p):
    """The share of a piece's numbers that a 16-bit float holds exactly (1.0: storing it in 16 bits loses nothing). -> float"""
    return float((p.astype(np.float16).astype(np.float32) == p).mean())


def read_run(path):
    run = {}
    for line in open(path, encoding="utf-8"):
        q, _q0, pid, rank, _score, _tag = line.split()
        run.setdefault(q, []).append((int(rank), pid))
    return {q: [p for _r, p in sorted(v)] for q, v in run.items()}


def against(ref, mine):
    shares, same10 = [], 0
    for q, r in ref.items():
        m = mine[q]; shares.append(len(set(r[:100]) & set(m[:100])) / len(r[:100])); same10 += r[:10] == m[:10]
    return {"queries": len(ref), "share_of_the_first_100_in_common_mean": round(float(np.mean(shares)), 6), "share_of_the_first_100_in_common_lowest": round(min(shares), 4),
            "queries_whose_first_10_are_the_same_in_the_same_order": same10}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import retrieval_datasets as ds
    import retrieval_metrics as rm
    ap = argparse.ArgumentParser()
    ap.add_argument("--precision", required=True, choices=sorted(BYTES)); ap.add_argument("--dataset", required=True, choices=ds.NAMES); ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS"))
    ap.add_argument("--emb-dir", required=True); ap.add_argument("--out-dir", required=True); ap.add_argument("--state", required=True); ap.add_argument("--checkpoints"); ap.add_argument("--piece-rows", type=int)
    ap.add_argument("--ref-run"); ap.add_argument("--stop-after-pieces", type=int); ap.add_argument("--top", type=int, default=100)
    a = ap.parse_args()
    if bool(a.checkpoints) == bool(a.piece_rows):
        S.refuse("give --checkpoints FILE (stored pieces) or --piece-rows N (one corpus.npy), not both")
    score_path = os.path.join(a.out_dir, "score.json"); progress = os.path.join(a.out_dir, "search_progress.jsonl")
    if os.path.exists(score_path):
        S.refuse(f"{score_path} exists")
    os.makedirs(a.out_dir, exist_ok=True); os.makedirs(os.path.dirname(os.path.abspath(a.state)), exist_ok=True)
    d = ds.load(a.datasets, a.dataset); t_all = time.perf_counter()
    if a.checkpoints:
        pieces, qrec, total = S.pieces_from_checkpoints(a.checkpoints)
        q, q_sha = S.read_npy_checked(os.path.join(a.emb_dir, "queries.npy"), qrec["queries_sha256"])
        qids = json.load(open(os.path.join(a.emb_dir, "query_ids.json"), encoding="utf-8"))
        layout = {"layout": "pieces", "checkpoint_file_sha256": S.sha256_file(a.checkpoints), "pieces": len(pieces)}

        def raw_piece(k):
            vf, vsha, idf, idsha, _rows = pieces[k]
            p, _ = S.read_npy_checked(os.path.join(a.emb_dir, vf), vsha)
            if S.sha256_file(os.path.join(a.emb_dir, idf)) != idsha:
                S.refuse(f"{idf} does not have the recorded SHA-256")
            return p, json.load(open(os.path.join(a.emb_dir, idf), encoding="utf-8"))
    else:
        ids = json.load(open(os.path.join(a.emb_dir, "ids.json"), encoding="utf-8"))
        q, q_sha = S.read_npy_checked(os.path.join(a.emb_dir, "queries.npy")); qids = ids["query_ids"]
        whole, whole_sha = S.read_npy_checked(os.path.join(a.emb_dir, "corpus.npy")); total = whole.shape[0]
        pieces = [(None, None, None, None, min(a.piece_rows, total - s)) for s in range(0, total, a.piece_rows)]
        layout = {"layout": "one file cut into pieces", "piece_rows": a.piece_rows, "pieces": len(pieces), "corpus_sha256": whole_sha}

        def raw_piece(k):
            s = k * a.piece_rows
            return whole[s:s + pieces[k][4]], ids["passage_ids"][s:s + pieces[k][4]]
    if q.shape[0] != len(qids) or set(qids) != set(d.queries):
        S.refuse("the stored queries are not the queries of the data set's split")
    scale = int8_scale(raw_piece(0)[0]) if a.precision == "int8" else None
    cut_shares, exact = [], []

    def read_piece(k):
        p, pids = raw_piece(k)
        m, cut = stored(p, a.precision, scale); cut_shares.append(cut); exact.append(fp16_exact_share(p))
        return m, pids

    q_unit, _qmin, _qmax = S.unit(q)
    judged = {p for rels in d.qrels.values() for p in rels}
    key = json.dumps([a.dataset, q_sha, a.top, layout, a.precision, scale], sort_keys=True)

    def line(rec):
        with open(progress, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec) + "\n"); f.flush(); os.fsync(f.fileno())

    line({"kind": "going_on" if os.path.isfile(a.state) else "start", "at": S.now(), "dataset": a.dataset, "precision": a.precision, "int8_scale": scale, "passages": total, **layout,
          "program_sha256": S.sha256_file(os.path.abspath(__file__))})

    def on_piece(k, rows, so_far, read_s, search_s):
        line({"kind": "piece", "piece": k, "passages": rows, "passages_so_far": so_far, "share_of_values_cut": cut_shares[-1], "share_of_values_a_16_bit_float_holds_exactly": exact[-1], "at": S.now()})
        if (k + 1) % 10 == 0 or k + 1 == len(pieces):
            print(f"  piece {k + 1} of {len(pieces)}: {so_far:,} passages", flush=True)

    finished, best_val, best_idx, ids_of, seen, _norms = S.search_pieces(q_unit, pieces, read_piece, a.top, judged, a.state, key, on_piece, a.stop_after_pieces)
    if not finished:
        line({"kind": "stopped", "at": S.now(), "reason": "--stop-after-pieces"}); print(json.dumps({"stopped": True})); return 5
    width = best_idx.shape[1]
    per_piece = {}
    for l in open(progress, encoding="utf-8"):          # every call's lines: a run that went on after a stop read some pieces in an earlier call
        r = json.loads(l)
        if r.get("kind") == "piece":
            per_piece[r["piece"]] = r
    ex = [r["share_of_values_a_16_bit_float_holds_exactly"] for r in per_piece.values()]; cuts = [r["share_of_values_cut"] for r in per_piece.values()]
    ranking = {qid: [ids_of[int(best_idx[i, r])] for r in range(width)] for i, qid in enumerate(qids)}
    run = {qid: {ids_of[int(best_idx[i, r])]: float(best_val[i, r]) for r in range(width)} for i, qid in enumerate(qids)}
    m = rm.evaluate(d.qrels, run, per_query=False)
    rec = {"what": "exact search over the corpus with its vectors turned, in memory, into what a store of fewer bits would hold", "dataset": a.dataset, "split": d.split, "at": S.now(),
           "precision": a.precision, "bytes_per_number": BYTES[a.precision], "bytes_per_passage": BYTES[a.precision] * int(q.shape[1]), "size": int(q.shape[1]), "queries_kept_as": "float32",
           "int8": None if scale is None else {"scale": scale, "scale_is": f"127 / the {PCT}th percentile of the absolute values of the unit vectors of the first piece", "share_of_values_cut_mean": round(float(np.mean(cuts)), 6)},
           "stored_values_and_16_bit_floats": {"pieces": len(ex), "pieces_whose_every_number_a_16_bit_float_holds_exactly": sum(1 for x in ex if x == 1.0), "lowest_share_of_a_piece": min(ex),
                                               "note": "where every piece is 1.0, the fp16 store gives back the same numbers and the fp16 search is the 32-bit search"},
           "source": {"vectors_folder": os.path.basename(os.path.normpath(a.emb_dir)), "queries": int(q.shape[0]), "passages": total, **layout, "queries_sha256": q_sha, "top": width},
           "search": "exact cosine, numpy, one piece in memory at a time; no index; nothing converted is stored",
           "metrics": {k: v for k, v in m.items() if k != "per_query"},
           "against_the_32_bit_ranking": None, "judged_ids_found": len(seen) == len(judged),
           "host_seconds_of_this_call": round(time.perf_counter() - t_all, 1), "seconds_are": "wall time on a host that does other work; not a speed of anything",
           "numpy": np.__version__, "program": {"file": "storage_precision.py", "sha256": S.sha256_file(os.path.abspath(__file__)), "uses": {"search_whole_corpus.py": S.sha256_file(S.__file__)}}}
    if a.ref_run:
        rec["against_the_32_bit_ranking"] = {"file_sha256": S.sha256_file(a.ref_run), **against(read_run(a.ref_run), ranking)}
    json.dump(rec, open(score_path, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    line({"kind": "finished", "at": S.now(), "passages": total})
    print(json.dumps({"dataset": a.dataset, "precision": a.precision, "metrics": rec["metrics"], "against_the_32_bit_ranking": rec["against_the_32_bit_ranking"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
