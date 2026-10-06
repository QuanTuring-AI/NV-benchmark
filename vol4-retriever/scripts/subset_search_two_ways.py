#!/usr/bin/env python3
"""Vol.4 · the search and the two metrics on a fixed subset of a corpus, computed a second way (control A_H of the
HotpotQA addendum).

The subset: every passage that has a judgement in the split, and the first piece of the corpus file (the first
100,000 passages). The first way is search_whole_corpus.py with --only-ids-of (it reads every stored piece and lets
only the subset's passages take part). The second way is this program: it gathers the subset's vectors into one
matrix, scores every query against it with one matrix product, orders with a stable sort (equal scores: the passage
earlier in the corpus file first), and calls the same metric function. The two share the stored vectors and the
metric function and nothing else: not the piece loop, not the merging of partial results, not the tie handling code.

  ids         writes <subset-dir>/ids.json ({"passage_ids": [...]}) for the first way, and a record of how many
  second-way  computes the second way and compares it with the first way's score.json: nDCG@10 and Recall@100 must
              agree to five decimals; the number of queries whose own two values are equal is reported as well

usage: subset_search_two_ways.py ids --dataset NAME --datasets DIR --emb-dir DIR --checkpoints FILE --subset-dir DIR --out FILE.json
       subset_search_two_ways.py second-way --dataset NAME --datasets DIR --emb-dir DIR --checkpoints FILE --subset-dir DIR
                                            --first-way-score SCORE.json --out FILE.json [--top 100]
exit codes: 0 · 3 the two ways do not agree · 2 refused
"""
import argparse, hashlib, json, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retrieval_datasets as ds  # noqa: E402
import retrieval_metrics as rm  # noqa: E402


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def pieces_of(checkpoints):
    recs = [json.loads(l) for l in open(checkpoints, encoding="utf-8") if l.strip()]
    if not any(r.get("kind") == "finished" for r in recs):
        raise SystemExit("refused: the checkpoint file has no `finished` line (the corpus is not complete)")
    return [r for r in recs if r.get("kind") == "piece"]


def subset_ids(qrels, first_piece_ids):
    judged = {p for rels in qrels.values() for p in rels}
    return judged, sorted(judged | set(first_piece_ids))


def rank(q_unit, d_unit, ids, top, chunk=256):
    """-> {query row: [(passage id, score), ...]} highest first; equal scores keep the order of `ids` (stable sort)."""
    out = []
    for s in range(0, q_unit.shape[0], chunk):
        scores = q_unit[s:s + chunk] @ d_unit.T
        order = np.argsort(-scores, axis=1, kind="stable")[:, :top]
        for r in range(scores.shape[0]):
            out.append([(ids[j], float(scores[r, j])) for j in order[r]])
    return out


def gather(emb_dir, pieces, wanted):
    """The subset's vectors in the order of the corpus file. -> (matrix, ids)."""
    rows, ids = [], []
    for p in pieces:
        pid = json.load(open(os.path.join(emb_dir, p["ids_file"]), encoding="utf-8"))
        take = [i for i, x in enumerate(pid) if x in wanted]
        if take:
            v = np.load(os.path.join(emb_dir, p["vectors_file"]), mmap_mode="r")
            rows.append(np.asarray(v[take], dtype=np.float32)); ids += [pid[i] for i in take]
    return np.concatenate(rows, axis=0), ids


def unit(v):
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ids", "second-way"):
        s = sub.add_parser(name); s.add_argument("--dataset", required=True, choices=ds.NAMES); s.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS"))
        s.add_argument("--emb-dir", required=True); s.add_argument("--checkpoints", required=True); s.add_argument("--subset-dir", required=True); s.add_argument("--out", required=True)
        if name == "second-way":
            s.add_argument("--first-way-score", required=True); s.add_argument("--top", type=int, default=100)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    d = ds.load(a.datasets, a.dataset); pieces = pieces_of(a.checkpoints); ids_path = os.path.join(a.subset_dir, "ids.json")
    if a.cmd == "ids":
        first = json.load(open(os.path.join(a.emb_dir, pieces[0]["ids_file"]), encoding="utf-8"))
        judged, ids = subset_ids(d.qrels, first)
        os.makedirs(a.subset_dir, exist_ok=True); json.dump({"passage_ids": ids}, open(ids_path, "w", encoding="utf-8"))
        rec = {"what": "the subset of control A_H: every passage with a judgement in the split and the first piece of the corpus file", "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "dataset": a.dataset, "split": d.split,
               "passages_with_a_judgement": len(judged), "passages_of_the_first_piece": len(first), "in_both": len(judged & set(first)), "subset_passages": len(ids), "ids_file_sha256": sha256_file(ids_path),
               "program_sha256": sha256_file(os.path.abspath(__file__))}
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True); json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
        print(json.dumps({k: rec[k] for k in ("passages_with_a_judgement", "passages_of_the_first_piece", "in_both", "subset_passages")})); return 0
    wanted = set(json.load(open(ids_path, encoding="utf-8"))["passage_ids"]); t0 = time.perf_counter()
    D, ids = gather(a.emb_dir, pieces, wanted)
    if set(ids) != wanted:
        raise SystemExit(f"refused: {len(wanted - set(ids))} ids of the subset are not in the stored corpus")
    q = np.load(os.path.join(a.emb_dir, "queries.npy")); qids = json.load(open(os.path.join(a.emb_dir, "query_ids.json"), encoding="utf-8"))
    if q.shape[0] != len(qids) or set(qids) != set(d.queries):
        raise SystemExit("refused: the stored queries are not the queries of the data set's split")
    gather_s = time.perf_counter() - t0; t1 = time.perf_counter()
    ranked = rank(unit(np.asarray(q, dtype=np.float32)), unit(D), ids, a.top)
    run = {qid: {pid: s for pid, s in row} for qid, row in zip(qids, ranked)}
    m = rm.evaluate(d.qrels, run, per_query=True); rank_s = time.perf_counter() - t1
    F = json.load(open(a.first_way_score, encoding="utf-8")); fm = F["metrics"]; fq = F.get("per_query") or {}
    keys = ("ndcg_cut_10", "recall_100")
    agree = {k: round(m[k], 5) == round(fm[k], 5) for k in keys}
    same_q = sum(1 for x in m["per_query"] if x in fq and all(abs(m["per_query"][x][k] - fq[x][k]) < 1e-9 for k in keys))
    rec = {"what": "control A_H: the subset's search and metrics computed a second way and set beside the first way", "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "dataset": a.dataset, "split": d.split,
           "subset_passages": len(ids), "queries": len(qids), "top": a.top,
           "first_way": {"program": "search_whole_corpus.py --only-ids-of", "score_file_sha256": sha256_file(a.first_way_score), **{k: fm[k] for k in keys}, "restricted_search": F.get("restricted_search")},
           "second_way": {"program": os.path.basename(__file__), "one_matrix": list(D.shape), "order": "stable sort of the negated scores: equal scores keep the order of the corpus file", **{k: m[k] for k in keys},
                          "seconds": {"gathering_the_vectors": round(gather_s, 1), "ranking_and_metrics": round(rank_s, 1)}},
           "difference": {k: m[k] - fm[k] for k in keys}, "equal_at_five_decimals": agree, "queries_whose_two_values_are_equal_in_both_ways": same_q, "queries_compared": len(m["per_query"]),
           "program_sha256": sha256_file(os.path.abspath(__file__)), "pass": all(agree.values())}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True); json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: rec[k] for k in ("subset_passages", "equal_at_five_decimals", "difference", "queries_whose_two_values_are_equal_in_both_ways", "queries_compared", "pass")}))
    return 0 if rec["pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
