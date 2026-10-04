#!/usr/bin/env python3
"""Vol.4 · from stored vectors to a ranking and its two metrics. The same program scores every embedding cell, so that
the search and the metric are not a variable between cells.

  search     exact: cosine between every query and every passage of the data set (the vectors are divided by their
             length here, whatever the encoder returned), the --top highest per query (1,000, as in the published
             MTEB condition). Ties are left to the metric program's rule.
  ranking    written as a TREC run file outside the repository (it lists passage ids of a data set).
  metrics    retrieval_metrics.evaluate: nDCG@10 and Recall@100 against the data set's qrels, with the per-query values.

With --rerank-from RUN.trec nothing is searched: that run file is scored as it is (used for the reranking cells).

usage: score_run.py --dataset NAME --datasets DIR --emb-dir DIR --run-out FILE.trec --out FILE.json [--top 1000]
                    [--target-ndcg10 X] [--tolerance 0.005] [--tag TEXT]
"""
import argparse, hashlib, json, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retrieval_datasets as ds  # noqa: E402
import retrieval_metrics as rm  # noqa: E402


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def unit(v):
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / n, float(n.min()), float(n.max())


def search(q, p, top, chunk=64):
    """Indexes and scores of the `top` nearest passages per query, highest first."""
    top = min(top, p.shape[0])
    idx = np.empty((q.shape[0], top), dtype=np.int64); val = np.empty((q.shape[0], top), dtype=np.float32)
    for s in range(0, q.shape[0], chunk):
        sc = q[s:s + chunk] @ p.T
        part = np.argpartition(-sc, top - 1, axis=1)[:, :top] if top < p.shape[0] else np.tile(np.arange(p.shape[0]), (sc.shape[0], 1))
        ps = np.take_along_axis(sc, part, axis=1); order = np.argsort(-ps, axis=1, kind="stable")
        idx[s:s + chunk] = np.take_along_axis(part, order, axis=1); val[s:s + chunk] = np.take_along_axis(ps, order, axis=1)
    return idx, val


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=ds.NAMES); ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS"))
    ap.add_argument("--emb-dir"); ap.add_argument("--rerank-from"); ap.add_argument("--run-out"); ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=1000); ap.add_argument("--target-ndcg10", type=float); ap.add_argument("--tolerance", type=float, default=0.005)
    ap.add_argument("--tag", default="vol4")
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    d = ds.load(a.datasets, a.dataset)
    t0 = time.perf_counter(); rec = {"dataset": a.dataset, "split": d.split, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if a.rerank_from:
        run = rm.read_run_trec(a.rerank_from); run_path = a.rerank_from
        rec["source"] = {"scored_as_given": os.path.basename(a.rerank_from)}
    else:
        ids = json.load(open(os.path.join(a.emb_dir, "ids.json"), encoding="utf-8"))
        q = np.load(os.path.join(a.emb_dir, "queries.npy")).astype(np.float32); p = np.load(os.path.join(a.emb_dir, "corpus.npy")).astype(np.float32)
        if q.shape[0] != len(ids["query_ids"]) or p.shape[0] != len(ids["passage_ids"]):
            raise SystemExit("refused: the vectors and the id lists do not have the same length")
        if set(ids["query_ids"]) != set(d.queries):
            raise SystemExit("refused: the stored queries are not the queries of the data set's split")
        if a.dataset in ds.PUBLISHED_COUNTS and p.shape[0] != ds.PUBLISHED_COUNTS[a.dataset]["corpus_passages"]:
            raise SystemExit(f"refused: {p.shape[0]} passage vectors, the task has {ds.PUBLISHED_COUNTS[a.dataset]['corpus_passages']}")
        if not (np.isfinite(q).all() and np.isfinite(p).all()):
            raise SystemExit("refused: a stored vector is not finite")
        q, qmin, qmax = unit(q); p, pmin, pmax = unit(p)
        idx, val = search(q, p, a.top)
        os.makedirs(os.path.dirname(os.path.abspath(a.run_out)), exist_ok=True)
        with open(a.run_out, "w", encoding="utf-8", newline="\n") as f:
            for i, qid in enumerate(ids["query_ids"]):
                for r in range(idx.shape[1]):
                    f.write(f"{qid} Q0 {ids['passage_ids'][idx[i, r]]} {r + 1} {val[i, r]:.6f} {a.tag}\n")
        run = {qid: {ids["passage_ids"][idx[i, r]]: float(val[i, r]) for r in range(idx.shape[1])} for i, qid in enumerate(ids["query_ids"])}
        run_path = a.run_out
        rec["source"] = {"vectors_folder": os.path.basename(os.path.normpath(a.emb_dir)), "queries": int(q.shape[0]), "passages": int(p.shape[0]), "size": int(q.shape[1]),
                         "norms_before_dividing": {"queries": [qmin, qmax], "passages": [pmin, pmax]}, "top": int(idx.shape[1]),
                         "queries_sha256": sha256_file(os.path.join(a.emb_dir, "queries.npy")), "corpus_sha256": sha256_file(os.path.join(a.emb_dir, "corpus.npy"))}
    m = rm.evaluate(d.qrels, run, per_query=True)
    rec.update({"search": "exact cosine, numpy", "run_file": {"name": os.path.basename(run_path), "sha256": sha256_file(run_path), "kept_outside_the_repository": True},
                "metrics": {k: v for k, v in m.items() if k != "per_query"}, "per_query": m.get("per_query"), "seconds": round(time.perf_counter() - t0, 1),
                "program": {"file": "score_run.py", "sha256": sha256_file(os.path.abspath(__file__))}})
    if a.target_ndcg10 is not None:
        got = m["ndcg_cut_10"]
        rec["target"] = {"ndcg_at_10": a.target_ndcg10, "tolerance": a.tolerance, "measured": got, "difference": got - a.target_ndcg10, "within": abs(got - a.target_ndcg10) <= a.tolerance}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"dataset": a.dataset, "metrics": rec["metrics"], "target": rec.get("target")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
