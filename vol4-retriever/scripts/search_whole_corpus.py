#!/usr/bin/env python3
"""Vol.4 · exact search over a corpus whose vectors are stored in pieces, one piece in memory at a time, and the two
metrics of the result. No index is built and nothing is approximated: every query is compared with every passage.

  search     cosine, as in score_run.py: every vector is divided by its length here, then query x passage products in
             float32, 64 queries at a time. After each piece only the --top highest passages per query are kept
             (100 by default: Recall@100 needs no more). Equal scores: the passage that comes first in the corpus stays.
  pieces     layout of encode_corpus_resumable.py: corpus-NNNNN.npy with ids-NNNNN.json, queries.npy with
             query_ids.json, and the checkpoint file that records the SHA-256 of each. Every file is compared with its
             record before it is used; a file that differs stops the program.
  one file   layout of embed_cell.py encode (corpus.npy, queries.npy, ids.json), for the check of this program against
             a result that exists: --piece-rows cuts the one file into pieces so that the same code runs.
  record     one line per piece in <out-dir>/search_progress.jsonl as it is done (counts and seconds, no ids), and the
             state of the search in a file outside the repository, so that a stopped run goes on from the last piece.
  ranking    a TREC run file outside the repository (it lists passage ids of a data set).
  metrics    retrieval_metrics.evaluate, the program of every other cell: nDCG@10 and Recall@100, with per-query values.
  alignment  every passage id of the qrels is looked for among the ids of the corpus; the counts are in the record. If
             a judged passage is missing the metrics are still written, and `qrels_ids_in_corpus.all_found` is false.
  restricted --only-ids-of DIR: only the passages whose id is in DIR/ids.json take part (the other vectors are read,
             compared with their record and left out). With the ids of a reduced corpus this turns the stored vectors
             of the whole corpus into a search over the reduced one, whose result is known from another run: a check
             that ids and vectors of the whole corpus belong together. Exit 3 if an id asked for is not in the corpus.

Seconds in the record are the wall time of reading, hashing and multiplying on the host CPU. They are not a speed of
any model or server.

usage: search_whole_corpus.py --dataset NAME --datasets DIR --emb-dir DIR --out-dir DIR --run-out FILE.trec --state FILE.npz
                              (--checkpoints FILE.jsonl | --piece-rows N) [--top 100] [--tag TEXT] [--stop-after-pieces N]
                              [--only-ids-of DIR]
exit codes: 0 done · 5 stopped after --stop-after-pieces (a later call goes on) · 2 refused
            3 done, but an id of --only-ids-of was not found in the corpus (the metrics are not those of that corpus)
"""
import argparse, hashlib, io, json, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

QUERY_CHUNK = 64


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def refuse(text):
    print("refused: " + text, file=sys.stderr)
    raise SystemExit(2)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_npy_checked(path, expected_sha256=None):
    """The array of a .npy file read once: the bytes are hashed, compared with the recorded value if one is given, and
    used in place (read-only). Returns (array, sha256)."""
    data = open(path, "rb").read()
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        refuse(f"{os.path.basename(path)} does not have the recorded SHA-256")
    f = io.BytesIO(data)
    version = np.lib.format.read_magic(f)
    shape, fortran, dtype = np.lib.format.read_array_header_1_0(f) if version == (1, 0) else np.lib.format.read_array_header_2_0(f)
    if fortran or dtype != np.float32 or len(shape) != 2:
        refuse(f"{os.path.basename(path)} is not a C-ordered float32 matrix")
    return np.frombuffer(data, dtype=np.float32, count=shape[0] * shape[1], offset=f.tell()).reshape(shape), digest


def unit(v):
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / n, float(n.min()), float(n.max())


def merge_top(best_val, best_idx, scores, number, top):
    """best_val, best_idx: (queries, k) of the search so far, highest first (k may be 0). scores: (queries, rows) of
    one piece; number[j] is the passage number in the corpus of column j (ascending). Returns the new (values,
    passage numbers), highest first, at most `top` wide. Equal scores are ordered by passage number, lower first."""
    n, rows = scores.shape
    keep = min(top, rows)
    if keep < rows:
        part = np.argpartition(-scores, keep - 1, axis=1)[:, :keep]
        cut = np.take_along_axis(scores, part, axis=1).min(axis=1)
        # every score equal to the lowest kept one is a candidate, or which of them stays would be argpartition's choice
        cand = [np.flatnonzero(scores[i] >= cut[i]) for i in range(n)]
    else:
        cand = [np.arange(rows)] * n
    k = min(top, best_val.shape[1] + rows)
    new_val = np.empty((n, k), dtype=np.float32); new_idx = np.empty((n, k), dtype=np.int64)
    for i in range(n):
        v = np.concatenate([best_val[i], scores[i, cand[i]]]); x = np.concatenate([best_idx[i], number[cand[i]]])
        order = np.lexsort((x, -v))[:k]                      # by score, highest first; equal scores by passage number
        new_val[i], new_idx[i] = v[order], x[order]
    return new_val, new_idx


def piece_scores(q_unit, p_unit):
    out = np.empty((q_unit.shape[0], p_unit.shape[0]), dtype=np.float32)
    for s in range(0, q_unit.shape[0], QUERY_CHUNK):
        out[s:s + QUERY_CHUNK] = q_unit[s:s + QUERY_CHUNK] @ p_unit.T
    return out


def pieces_from_checkpoints(checkpoints):
    """[(vectors file, its recorded sha256, ids file, its recorded sha256, passages)], the queries record, the total."""
    recs = [json.loads(l) for l in open(checkpoints, encoding="utf-8") if l.strip()]
    fin = next((r for r in recs if r.get("kind") == "finished"), None)
    if fin is None:
        refuse("the checkpoint file has no `finished` line (the corpus is not complete)")
    out, n = [], 0
    for r in recs:
        if r.get("kind") != "piece":
            continue
        if r["first"] != n:
            refuse(f"the pieces on record are not contiguous at piece {r['piece']}")
        out.append((r["vectors_file"], r["vectors_sha256"], r["ids_file"], r["ids_sha256"], r["passages"])); n += r["passages"]
    if fin["passages"] != n:
        refuse(f"the pieces hold {n} passages, the `finished` line says {fin['passages']}")
    qrec = next((r for r in recs if r.get("kind") == "queries"), None)
    if qrec is None:
        refuse("the checkpoint file has no `queries` line")
    return out, qrec, n


def save_state(path, done, best_val, best_idx, ids_of, seen_judged, key):
    """The state after `done` pieces, written to a new file that then takes the place of the old one."""
    order = sorted(ids_of)
    tmp = path + ".tmp.npz"
    np.savez(tmp, pieces_done=np.int64(done), best_val=best_val, best_idx=best_idx, key=np.array(key),
             id_index=np.array(order, dtype=np.int64), id_text=np.array([ids_of[i] for i in order], dtype=np.str_),
             judged_seen=np.array(sorted(seen_judged), dtype=np.str_))
    os.replace(tmp, path)


def load_state(path, key):
    if not os.path.isfile(path):
        return None
    s = np.load(path)
    if str(s["key"]) != key:
        refuse("the state file was written for another search (data set, queries, top or pieces differ)")
    ids_of = dict(zip((int(i) for i in s["id_index"]), (str(t) for t in s["id_text"])))
    return int(s["pieces_done"]), s["best_val"], s["best_idx"], ids_of, set(str(t) for t in s["judged_seen"])


def search_pieces(q_unit, pieces, read_piece, top, judged, state_path, key, on_piece=None, stop_after=None, only=None):
    """Runs the pieces not yet done. read_piece(k) -> (vectors, ids). Returns (finished, best_val, best_idx, ids_of,
    seen_judged, [norm min, norm max]); the state file is rewritten after every piece. With `only` (a set of ids), the
    passages whose id is not in it are left out; `seen_judged` then holds the ids of `only` that were met."""
    st = load_state(state_path, key)
    if st:
        done, best_val, best_idx, ids_of, seen = st
    else:
        done, ids_of, seen = 0, {}, set()
        best_val, best_idx = np.empty((q_unit.shape[0], 0), np.float32), np.empty((q_unit.shape[0], 0), np.int64)
    offset = sum(p[4] for p in pieces[:done]); lo, hi, this_call = float("inf"), 0.0, 0
    for k in range(done, len(pieces)):
        rows = pieces[k][4]
        t0 = time.perf_counter()
        p, pids = read_piece(k)
        if p.shape[0] != rows or len(pids) != rows or p.shape[1] != q_unit.shape[1]:
            refuse(f"piece {k} has {p.shape[0]} vectors and {len(pids)} ids; {rows} expected")
        if not np.isfinite(p).all():
            refuse(f"a vector of piece {k} is not finite")
        t1 = time.perf_counter()
        number = np.arange(offset, offset + rows, dtype=np.int64)
        if only is not None:
            number = number[np.fromiter((x in only for x in pids), dtype=bool, count=rows)]
            p = p[number - offset]
        if number.size:
            p_unit, a, b = unit(p); lo, hi = min(lo, a), max(hi, b)
            best_val, best_idx = merge_top(best_val, best_idx, piece_scores(q_unit, p_unit), number, top)
        for g in np.unique(best_idx[best_idx >= offset]):
            ids_of[int(g)] = pids[int(g) - offset]
        alive = set(int(g) for g in np.unique(best_idx)); ids_of = {g: t for g, t in ids_of.items() if g in alive}
        seen.update(x for x in pids if x in (judged if only is None else only))
        offset += rows; this_call += 1
        save_state(state_path, k + 1, best_val, best_idx, ids_of, seen, key)
        if on_piece:
            on_piece(k, rows, offset, t1 - t0, time.perf_counter() - t1)
        if stop_after and this_call >= stop_after and k + 1 < len(pieces):
            return False, best_val, best_idx, ids_of, seen, [lo, hi]
    return True, best_val, best_idx, ids_of, seen, [lo, hi]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import retrieval_datasets as ds
    import retrieval_metrics as rm
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=ds.NAMES); ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS"))
    ap.add_argument("--emb-dir", required=True); ap.add_argument("--out-dir", required=True); ap.add_argument("--run-out", required=True); ap.add_argument("--state", required=True)
    ap.add_argument("--checkpoints"); ap.add_argument("--piece-rows", type=int); ap.add_argument("--top", type=int, default=100); ap.add_argument("--tag", default="vol4")
    ap.add_argument("--stop-after-pieces", type=int); ap.add_argument("--only-ids-of")
    a = ap.parse_args()
    if bool(a.checkpoints) == bool(a.piece_rows):
        refuse("give --checkpoints FILE (stored pieces) or --piece-rows N (one corpus.npy), not both")
    score_path = os.path.join(a.out_dir, "score.json"); progress = os.path.join(a.out_dir, "search_progress.jsonl")
    if os.path.exists(score_path):
        refuse(f"{score_path} exists")
    os.makedirs(a.out_dir, exist_ok=True); os.makedirs(os.path.dirname(os.path.abspath(a.run_out)), exist_ok=True)
    d = ds.load(a.datasets, a.dataset)
    t_all = time.perf_counter()

    if a.checkpoints:
        pieces, qrec, total = pieces_from_checkpoints(a.checkpoints)
        q, q_sha = read_npy_checked(os.path.join(a.emb_dir, "queries.npy"), qrec["queries_sha256"])
        if sha256_file(os.path.join(a.emb_dir, "query_ids.json")) != qrec["query_ids_sha256"]:
            refuse("query_ids.json does not have the recorded SHA-256")
        qids = json.load(open(os.path.join(a.emb_dir, "query_ids.json"), encoding="utf-8"))
        layout = {"layout": "pieces", "checkpoint_file": os.path.basename(a.checkpoints), "checkpoint_file_sha256": sha256_file(a.checkpoints), "pieces": len(pieces)}

        def read_piece(k):
            vf, vsha, idf, idsha, _rows = pieces[k]
            p, _ = read_npy_checked(os.path.join(a.emb_dir, vf), vsha)
            if sha256_file(os.path.join(a.emb_dir, idf)) != idsha:
                refuse(f"{idf} does not have the recorded SHA-256")
            return p, json.load(open(os.path.join(a.emb_dir, idf), encoding="utf-8"))
    else:
        ids = json.load(open(os.path.join(a.emb_dir, "ids.json"), encoding="utf-8"))
        q, q_sha = read_npy_checked(os.path.join(a.emb_dir, "queries.npy")); qids = ids["query_ids"]
        whole, whole_sha = read_npy_checked(os.path.join(a.emb_dir, "corpus.npy"))
        total = whole.shape[0]
        if total != len(ids["passage_ids"]):
            refuse("corpus.npy and ids.json do not have the same length")
        pieces = [(None, None, None, None, min(a.piece_rows, total - s)) for s in range(0, total, a.piece_rows)]
        layout = {"layout": "one file cut into pieces", "piece_rows": a.piece_rows, "pieces": len(pieces), "corpus_sha256": whole_sha}

        def read_piece(k):
            s = k * a.piece_rows
            return whole[s:s + pieces[k][4]], ids["passage_ids"][s:s + pieces[k][4]]
    if q.shape[0] != len(qids) or set(qids) != set(d.queries):
        refuse("the stored queries are not the queries of the data set's split")
    only = set(json.load(open(os.path.join(a.only_ids_of, "ids.json"), encoding="utf-8"))["passage_ids"]) if a.only_ids_of else None
    if only is not None:
        layout = {**layout, "only_the_ids_of": os.path.basename(os.path.normpath(a.only_ids_of)), "ids_asked_for": len(only)}
    if a.dataset in ds.PUBLISHED_COUNTS and total != ds.PUBLISHED_COUNTS[a.dataset]["corpus_passages"]:
        refuse(f"{total} passage vectors, the task has {ds.PUBLISHED_COUNTS[a.dataset]['corpus_passages']}")
    if not np.isfinite(q).all():
        refuse("a stored query vector is not finite")
    q_unit, qmin, qmax = unit(q)
    judged = {p for rels in d.qrels.values() for p in rels}; relevant = {p for rels in d.qrels.values() for p, r in rels.items() if r > 0}
    key = json.dumps([a.dataset, q_sha, a.top, layout], sort_keys=True)

    def line(rec):
        with open(progress, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec) + "\n"); f.flush(); os.fsync(f.fileno())

    if not os.path.isfile(a.state):
        if os.path.exists(progress):
            refuse(f"{progress} exists and there is no state file to go on from")
        line({"kind": "start", "at": now(), "dataset": a.dataset, "split": d.split, "queries": int(q.shape[0]), "passages": total, "top": a.top, **layout,
              "program_sha256": sha256_file(os.path.abspath(__file__))})
    else:
        line({"kind": "going_on", "at": now()})

    def on_piece(k, rows, so_far, read_s, search_s):
        line({"kind": "piece", "piece": k, "passages": rows, "passages_so_far": so_far, "files_compared_with_their_record": bool(a.checkpoints),
              "read_and_hash_s": round(read_s, 2), "search_s": round(search_s, 2), "at": now()})
        if (k + 1) % 10 == 0 or k + 1 == len(pieces):
            print(f"  piece {k + 1} of {len(pieces)}: {so_far:,} passages", flush=True)

    finished, best_val, best_idx, ids_of, seen, norms = search_pieces(q_unit, pieces, read_piece, a.top, judged, a.state, key, on_piece, a.stop_after_pieces, only)
    if not finished:
        line({"kind": "stopped", "at": now(), "reason": "--stop-after-pieces"})
        print(json.dumps({"stopped": True})); return 5

    width = best_idx.shape[1]
    with open(a.run_out, "w", encoding="utf-8", newline="\n") as f:
        for i, qid in enumerate(qids):
            for r in range(width):
                f.write(f"{qid} Q0 {ids_of[int(best_idx[i, r])]} {r + 1} {best_val[i, r]:.6f} {a.tag}\n")
    run = {qid: {ids_of[int(best_idx[i, r])]: float(best_val[i, r]) for r in range(width)} for i, qid in enumerate(qids)}
    m = rm.evaluate(d.qrels, run, per_query=True)
    rec = {"dataset": a.dataset, "split": d.split, "at": now(),
           "source": {"vectors_folder": os.path.basename(os.path.normpath(a.emb_dir)), "queries": int(q.shape[0]), "passages": total, "size": int(q.shape[1]), **layout,
                      "queries_sha256": q_sha, "norms_before_dividing": {"queries": [qmin, qmax], "passages_of_this_call": norms}, "top": width},
           "search": "exact cosine, numpy, one piece in memory at a time; no index",
           "qrels_ids_in_corpus": ({"judged_ids": len(judged), "judged_ids_found": len(seen), "relevant_ids": len(relevant), "relevant_ids_found": len(relevant & seen),
                                    "all_found": seen == judged} if only is None else
                                   {"not_counted": "this call searched only the ids asked for", "relevant_ids": len(relevant), "relevant_ids_among_those_searched": len(relevant & seen)}),
           "restricted_search": (None if only is None else {"ids_asked_for": len(only), "ids_found_in_the_corpus": len(seen), "all_found": seen == only}),
           "run_file": {"name": os.path.basename(a.run_out), "sha256": sha256_file(a.run_out), "kept_outside_the_repository": True},
           "metrics": {k: v for k, v in m.items() if k != "per_query"}, "per_query": m.get("per_query"),
           "host_cpu_seconds_of_this_call": round(time.perf_counter() - t_all, 1),
           "seconds_are": "wall time of reading, hashing and multiplying on the host CPU; not a speed of a model or a server",
           "numpy": np.__version__, "program": {"file": "search_whole_corpus.py", "sha256": sha256_file(os.path.abspath(__file__))}}
    json.dump(rec, open(score_path, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    line({"kind": "finished", "at": now(), "passages": total, "pieces": len(pieces)})
    print(json.dumps({"dataset": a.dataset, "passages": total, "metrics": rec["metrics"], "qrels_ids_in_corpus": rec["qrels_ids_in_corpus"],
                      "restricted_search": rec["restricted_search"]}, ensure_ascii=False))
    return 0 if only is None or seen == only else 3


if __name__ == "__main__":
    sys.exit(main())
