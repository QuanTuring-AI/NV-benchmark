#!/usr/bin/env python3
"""Vol.4 · the stored vectors of a whole corpus kept as 16-bit floats, with the 32-bit files they came from still
provable from them.

The whole-corpus vectors were written as 32-bit .npy pieces, and the checkpoint file of each corpus (in this
repository) records the SHA-256 of every piece. For the encoder used here every stored number is exactly a 16-bit
float (results/storage_precision), so a 16-bit copy loses nothing. This program makes that copy and proves, per piece
and from the copy alone, that it gives back the recorded file: the 16-bit array is turned into 32 bits, written as a
.npy file in memory, and that file's SHA-256 must be the one in the checkpoint file.

  convert   every piece of a corpus: read (its SHA-256 must be the recorded one), turn into 16 bits, refuse if a single
            value changes on the way back, write the 16-bit piece to a NEW folder, read it back FROM DISK and require
            the recorded SHA-256 of the 32-bit file from it. The id files and the query files are copied and compared.
            One line per piece goes to a list as it is done; a later call goes on after the last listed piece.
            The source folder is only read. Nothing is deleted.
  verify    the same proof from the 16-bit folder alone (no source): every piece against the checkpoint file
  search    the exact search of search_whole_corpus.py over the 16-bit folder, each piece checked as in `verify` and
            given to the search as 32 bits; the result is compared with an existing ranking of the 32-bit files:
            the same passages in the same order for every query, and the same nDCG@10 and Recall@100

exit codes: 0 done · 2 refused (a check failed: nothing more is written) · 6 stopped, less free space than --min-free-gib
usage: fp16_store.py convert --emb-dir SRC --checkpoints FILE --out-dir DST --list FILE.jsonl [--min-free-gib 25]
       fp16_store.py verify  --fp16-dir DST --checkpoints FILE
       fp16_store.py search  --fp16-dir DST --checkpoints FILE --dataset NAME --datasets DIR --ref-run FILE.trec --ref-score FILE.json --out FILE.json --state FILE.npz
"""
import argparse, hashlib, io, json, os, shutil, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_whole_corpus as S  # noqa: E402  (pieces, checked reading, the search: used as they are)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def to_fp16(a):
    """-> (the 16-bit array, True if every value comes back unchanged)"""
    h = a.astype(np.float16)
    return h, bool(np.array_equal(h.astype(np.float32), a))


def rebuilt_bytes(h):
    """The 32-bit .npy file a 16-bit array stands for, as bytes (not written anywhere)."""
    b = io.BytesIO(); np.save(b, h.astype(np.float32)); return b.getvalue()


def read_fp16(path):
    """-> (array, sha256 of the file). Refuses anything that is not a C-ordered 16-bit matrix."""
    data = open(path, "rb").read()
    a = np.load(io.BytesIO(data), allow_pickle=False)
    if a.dtype != np.float16 or a.ndim != 2 or not a.flags["C_CONTIGUOUS"]:
        S.refuse(f"{os.path.basename(path)} is not a C-ordered float16 matrix")
    return a, sha256_bytes(data)


def piece_from_fp16(path, recorded_sha256):
    """A piece read from the 16-bit folder and proven against the recorded SHA-256 of its 32-bit file. -> (float32 array, sha256 of the 16-bit file)"""
    h, digest = read_fp16(path)
    if sha256_bytes(rebuilt_bytes(h)) != recorded_sha256:
        S.refuse(f"{os.path.basename(path)}: the 32-bit file rebuilt from it does not have the recorded SHA-256")
    return h.astype(np.float32), digest


def free_gib(path):
    return shutil.disk_usage(path).free / 2 ** 30


def copy_checked(src, dst, recorded_sha256=None):
    if recorded_sha256 is not None and S.sha256_file(src) != recorded_sha256:
        S.refuse(f"{os.path.basename(src)} does not have the recorded SHA-256")
    if not os.path.isfile(dst):
        shutil.copyfile(src, dst + ".tmp"); os.replace(dst + ".tmp", dst)
    if S.sha256_file(dst) != S.sha256_file(src):
        S.refuse(f"the copy of {os.path.basename(src)} differs from its source")
    return S.sha256_file(dst)


def convert_piece(src_dir, dst_dir, piece):
    """One piece. -> its line for the list. Refuses (exit 2) on any failed check; the 16-bit file is then removed."""
    vf, vsha, idf, idsha, rows = piece
    a, _ = S.read_npy_checked(os.path.join(src_dir, vf), vsha)
    if a.shape[0] != rows:
        S.refuse(f"{vf} has {a.shape[0]} rows, {rows} recorded")
    h, exact = to_fp16(a)
    if not exact:
        S.refuse(f"{vf}: a value changes when it is stored in 16 bits; nothing was written for this piece")
    dst = os.path.join(dst_dir, vf)
    with open(dst + ".tmp", "wb") as f:
        np.save(f, h)
    os.replace(dst + ".tmp", dst)
    back, dsha = read_fp16(dst)                                     # from disk, not from memory
    same_values = bool(np.array_equal(back.astype(np.float32), a)); same_file = sha256_bytes(rebuilt_bytes(back)) == vsha
    if not (same_values and same_file):
        os.remove(dst)
        S.refuse(f"{vf}: read back from disk, " + ("the values differ" if not same_values else "the rebuilt 32-bit file does not have the recorded SHA-256") + "; the 16-bit file was removed")
    ids_sha = copy_checked(os.path.join(src_dir, idf), os.path.join(dst_dir, idf), idsha)
    return {"kind": "piece", "vectors_file": vf, "rows": rows, "sha256_of_the_32_bit_file": vsha, "bytes_of_the_32_bit_file": os.path.getsize(os.path.join(src_dir, vf)),
            "sha256_of_the_16_bit_file": dsha, "bytes_of_the_16_bit_file": os.path.getsize(dst), "values_equal_read_back_from_disk": same_values,
            "rebuilt_32_bit_file_has_the_recorded_sha256": same_file, "ids_file": idf, "ids_sha256": ids_sha, "at": S.now()}


def listed(path):
    return {r["vectors_file"]: r for r in (json.loads(l) for l in open(path, encoding="utf-8") if l.strip()) if r.get("kind") == "piece"} if os.path.isfile(path) else {}


def convert(a):
    pieces, qrec, total = S.pieces_from_checkpoints(a.checkpoints)
    if os.path.abspath(a.out_dir) == os.path.abspath(a.emb_dir):
        S.refuse("the 16-bit folder must not be the source folder")
    os.makedirs(a.out_dir, exist_ok=True); os.makedirs(os.path.dirname(os.path.abspath(a.list)), exist_ok=True)
    done = listed(a.list)

    def line(rec):
        with open(a.list, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec) + "\n"); f.flush(); os.fsync(f.fileno())
    if not done:
        line({"kind": "start", "at": S.now(), "checkpoint_file_sha256": S.sha256_file(a.checkpoints), "pieces": len(pieces), "passages": total, "free_gib_before": round(free_gib(a.out_dir), 1),
              "numpy": np.__version__, "program_sha256": S.sha256_file(os.path.abspath(__file__))})
    for k, p in enumerate(pieces):
        if p[0] in done:
            continue
        if free_gib(a.out_dir) < a.min_free_gib:
            line({"kind": "stopped", "at": S.now(), "reason": f"less than {a.min_free_gib} GiB free", "free_gib": round(free_gib(a.out_dir), 1), "pieces_done": k})
            print(json.dumps({"stopped": "free space", "pieces_done": k})); return 6
        line(convert_piece(a.emb_dir, a.out_dir, p))
        if (k + 1) % 10 == 0 or k + 1 == len(pieces):
            print(f"  piece {k + 1} of {len(pieces)}", flush=True)
    q_sha = copy_checked(os.path.join(a.emb_dir, "queries.npy"), os.path.join(a.out_dir, "queries.npy"), qrec["queries_sha256"])
    qi_sha = copy_checked(os.path.join(a.emb_dir, "query_ids.json"), os.path.join(a.out_dir, "query_ids.json"))
    d = listed(a.list)
    rec = {"kind": "finished", "at": S.now(), "pieces": len(d), "passages": sum(r["rows"] for r in d.values()), "bytes_of_the_32_bit_files": sum(r["bytes_of_the_32_bit_file"] for r in d.values()),
           "bytes_of_the_16_bit_files": sum(r["bytes_of_the_16_bit_file"] for r in d.values()), "queries_sha256": q_sha, "query_ids_sha256": qi_sha, "free_gib_after": round(free_gib(a.out_dir), 1)}
    if len(d) != len(pieces) or rec["passages"] != total:
        S.refuse("the list does not hold every piece of the checkpoint file")
    line(rec); print(json.dumps(rec)); return 0


def verify(a):
    pieces, qrec, total = S.pieces_from_checkpoints(a.checkpoints); rows = 0
    for k, (vf, vsha, idf, idsha, n) in enumerate(pieces):
        v, _ = piece_from_fp16(os.path.join(a.fp16_dir, vf), vsha)
        if v.shape[0] != n or S.sha256_file(os.path.join(a.fp16_dir, idf)) != idsha:
            S.refuse(f"{vf}: rows or ids do not match the checkpoint file")
        rows += n
    S.read_npy_checked(os.path.join(a.fp16_dir, "queries.npy"), qrec["queries_sha256"])
    rec = {"verified_from_the_16_bit_folder_alone": True, "pieces": len(pieces), "passages": rows, "every_rebuilt_32_bit_file_has_the_recorded_sha256": True, "checkpoint_file_sha256": S.sha256_file(a.checkpoints)}
    if rows != total:
        S.refuse("the pieces do not hold every passage")
    print(json.dumps(rec)); return 0


def same_ranking(ref, mine):
    """ref, mine: {query: [passage ids, best first]}. -> counts of the comparison, over the length of the shorter list per query."""
    same, first_diff = 0, None
    for q, r in ref.items():
        m = mine.get(q, []); n = min(len(r), len(m))
        if n and r[:n] == m[:n] and len(m) >= min(len(r), 100):
            same += 1
        elif first_diff is None:
            first_diff = q
    return {"queries": len(ref), "queries_with_the_same_passages_in_the_same_order": same, "first_query_that_differs": first_diff}


def read_run(path):
    run = {}
    for l in open(path, encoding="utf-8"):
        q, _q0, pid, rank, _score, _tag = l.split()
        run.setdefault(q, []).append((int(rank), pid))
    return {q: [p for _r, p in sorted(v)] for q, v in run.items()}


def search(a):
    import retrieval_datasets as ds
    import retrieval_metrics as rm
    if os.path.exists(a.out):
        S.refuse(f"{a.out} exists")
    d = ds.load(a.datasets, a.dataset); t0 = time.perf_counter()
    pieces, qrec, total = S.pieces_from_checkpoints(a.checkpoints)
    q, q_sha = S.read_npy_checked(os.path.join(a.fp16_dir, "queries.npy"), qrec["queries_sha256"])
    qids = json.load(open(os.path.join(a.fp16_dir, "query_ids.json"), encoding="utf-8"))
    if q.shape[0] != len(qids) or set(qids) != set(d.queries):
        S.refuse("the stored queries are not the queries of the data set's split")
    fp16_sha = {}

    def read_piece(k):
        vf, vsha, idf, idsha, _rows = pieces[k]
        v, fp16_sha[vf] = piece_from_fp16(os.path.join(a.fp16_dir, vf), vsha)
        if S.sha256_file(os.path.join(a.fp16_dir, idf)) != idsha:
            S.refuse(f"{idf} does not have the recorded SHA-256")
        return v, json.load(open(os.path.join(a.fp16_dir, idf), encoding="utf-8"))

    q_unit, _lo, _hi = S.unit(q)
    judged = {p for rels in d.qrels.values() for p in rels}
    key = json.dumps([a.dataset, q_sha, a.top, S.sha256_file(a.checkpoints), "fp16 store"], sort_keys=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.state)), exist_ok=True); os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    finished, best_val, best_idx, ids_of, seen, _norms = S.search_pieces(q_unit, pieces, read_piece, a.top, judged, a.state, key,
                                                                           lambda k, rows, so_far, _r, _s: print(f"  piece {k + 1} of {len(pieces)}", flush=True) if (k + 1) % 10 == 0 else None)
    width = best_idx.shape[1]
    ranking = {qid: [ids_of[int(best_idx[i, r])] for r in range(width)] for i, qid in enumerate(qids)}
    run = {qid: {ids_of[int(best_idx[i, r])]: float(best_val[i, r]) for r in range(width)} for i, qid in enumerate(qids)}
    m = rm.evaluate(d.qrels, run, per_query=False); mine = {k: v for k, v in m.items() if k != "per_query"}
    ref_metrics = json.load(open(a.ref_score, encoding="utf-8"))["metrics"]
    cmp = same_ranking(read_run(a.ref_run), ranking)
    rec = {"what": "exact search over the 16-bit copy of a whole corpus, every piece proven against the recorded SHA-256 of its 32-bit file and searched as 32 bits; compared with the existing ranking of the 32-bit files",
           "dataset": a.dataset, "split": d.split, "at": S.now(), "passages": total, "queries": int(q.shape[0]), "top": width, "checkpoint_file_sha256": S.sha256_file(a.checkpoints),
           "metrics": mine, "metrics_of_the_32_bit_run": {k: ref_metrics.get(k) for k in ("ndcg_cut_10", "recall_100", "queries_scored")},
           "same_metrics": bool(mine["ndcg_cut_10"] == ref_metrics["ndcg_cut_10"] and mine["recall_100"] == ref_metrics["recall_100"]),
           "against_the_32_bit_ranking": {"file_sha256": S.sha256_file(a.ref_run), **cmp}, "pieces_proven_in_this_call": len(fp16_sha),
           "host_seconds_of_this_call": round(time.perf_counter() - t0, 1), "seconds_are": "wall time on a host that does other work; not a speed of anything", "numpy": np.__version__,
           "program": {"file": "fp16_store.py", "sha256": S.sha256_file(os.path.abspath(__file__)), "uses": {"search_whole_corpus.py": S.sha256_file(S.__file__)}}}
    rec["identical"] = bool(rec["same_metrics"] and cmp["queries_with_the_same_passages_in_the_same_order"] == cmp["queries"] == len(ranking))
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({k: rec[k] for k in ("dataset", "identical", "same_metrics", "against_the_32_bit_ranking", "metrics")}))
    return 0 if rec["identical"] else 2


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert"); c.add_argument("--emb-dir", required=True); c.add_argument("--checkpoints", required=True); c.add_argument("--out-dir", required=True); c.add_argument("--list", required=True)
    c.add_argument("--min-free-gib", type=float, default=25.0)
    v = sub.add_parser("verify"); v.add_argument("--fp16-dir", required=True); v.add_argument("--checkpoints", required=True)
    s = sub.add_parser("search"); s.add_argument("--fp16-dir", required=True); s.add_argument("--checkpoints", required=True); s.add_argument("--dataset", required=True); s.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS"))
    s.add_argument("--ref-run", required=True); s.add_argument("--ref-score", required=True); s.add_argument("--out", required=True); s.add_argument("--state", required=True); s.add_argument("--top", type=int, default=100)
    a = ap.parse_args()
    return {"convert": convert, "verify": verify, "search": search}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
