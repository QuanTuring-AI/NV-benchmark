#!/usr/bin/env python3
"""Vol.5 · cell C1: the Blueprint's default vector store (Elasticsearch 9.3.0, `bbq_hnsw` as the server applies it to
a 2,048-dimension cosine field) against Vol.4's exact search, on the same vectors.

Subcommands (the first three run in the client container on the store's network; `score` runs on the host):
  search    the Blueprint's query: kNN with k = num_candidates = 100 (`elastic_vdb.py:1107`: k = fetch_k = top_k, and
            VECTOR_DB_TOPK defaults to 100). Every query one at a time; the duration of each call is measured in the
            client (it includes the client's own work and the HTTP round trip on the Docker network). The first ten
            calls are warm-up and are kept apart. Writes a TREC run and a timing record.
  negative  the negative control only: k = 10, num_candidates = 10, and the query's `rescore_vector.oversample` = 0
            (no rescoring with the full vectors). Writes a TREC run.
  exact     brute force inside the store: `script_score` with cosineSimilarity over every document, for the given
            query ids. Writes a TREC run.
  score     on the host: per query the share of the reference's first k passages found in the run's first k (k = 10
            and 100; mean, lowest, how many queries under 0.9), and nDCG@10 and Recall@100 with Vol.4's metric module.

Query vectors are Vol.4's (queries.npy and query_ids.json of the 16-bit store, checked against the recorded SHA-256):
only the store is measured. A passage id is read from the document field --id-field (the place where the loader puts
it: es_bulk_load.py).

usage: es_ann_vs_exact.py search|negative --es URL --index NAME --fp16-dir DIR --checkpoints FILE --out-run FILE
                          [--out-timing FILE] [--id-field metadata.source.source_name] [--only-ids FILE]
       es_ann_vs_exact.py exact --es URL --index NAME --fp16-dir DIR --checkpoints FILE --ids FILE --out-run FILE
       es_ann_vs_exact.py score --run FILE --reference FILE --qrels FILE --out FILE
"""
import argparse, json, os, statistics, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(V5), "vol4-retriever", "scripts"))
K, NUM_CANDIDATES, WARMUP = 100, 100, 10


def get_path(doc, dotted):
    """The passage id of a hit: the field's value, reduced to its file name without extension (the Blueprint's
    ingestor stores a file path there; es_bulk_load.py stores the same form, built from a document of the ingestor)."""
    for part in dotted.split("."):
        doc = doc[part]
    return os.path.splitext(os.path.basename(str(doc)))[0]


def queries(fp16_dir, checkpoints):
    import search_whole_corpus as S
    _, qrec, _ = S.pieces_from_checkpoints(checkpoints)
    q, _ = S.read_npy_checked(os.path.join(fp16_dir, "queries.npy"), qrec["queries_sha256"])
    ids = json.load(open(os.path.join(fp16_dir, "query_ids.json"), encoding="utf-8"))
    if len(ids) != len(q):
        raise SystemExit("refused: query ids and query vectors differ in number")
    return ids, q


def write_run(path, run, tag):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for qid, hits in run.items():
            for rank, (pid, score) in enumerate(hits, 1):
                f.write(f"{qid} Q0 {pid} {rank} {score:.6f} {tag}\n")


def knn_body(vec, k, nc, id_field, no_rescore=False):
    knn = {"field": "vector", "query_vector": [float(x) for x in vec], "k": k, "num_candidates": nc}
    if no_rescore:
        knn["rescore_vector"] = {"oversample": 0}
    return {"knn": knn, "_source": [id_field], "size": k}


def run_search(a, k, nc, no_rescore, tag):
    from elasticsearch import Elasticsearch
    es = Elasticsearch(a.es, request_timeout=600)
    ids, q = queries(a.fp16_dir, a.checkpoints)
    keep = set(json.load(open(a.only_ids))) if a.only_ids else None
    run, durations, warm = {}, [], []
    for i, (qid, vec) in enumerate(zip(ids, q)):
        if keep is not None and qid not in keep:
            continue
        t0 = time.perf_counter()
        r = es.search(index=a.index, body=knn_body(vec, k, nc, a.id_field, no_rescore))
        ms = (time.perf_counter() - t0) * 1000
        (warm if len(warm) < WARMUP else durations).append(ms)
        run[qid] = [(str(get_path(h["_source"], a.id_field)), h["_score"]) for h in r["hits"]["hits"]]
    write_run(a.out_run, run, tag)
    if a.out_timing:
        d = sorted(durations)
        rec = {"queries": len(run), "warmup_calls_ms": warm, "timed_calls": len(d), "k": k, "num_candidates": nc, "rescore_off": no_rescore,
               "ms": {"p50": statistics.median(d), "p99": d[min(len(d) - 1, int(round(0.99 * (len(d) - 1))))], "mean": statistics.fmean(d)} if d else None,
               "measured_in": "the client container, one call at a time, on the store's Docker network"}
        json.dump(rec, open(a.out_timing, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"queries": len(run), "out": a.out_run}))


def run_exact(a):
    from elasticsearch import Elasticsearch
    es = Elasticsearch(a.es, request_timeout=3600)
    ids, q = queries(a.fp16_dir, a.checkpoints); want = json.load(open(a.ids))
    pos = {qid: i for i, qid in enumerate(ids)}; run = {}
    for qid in want:
        body = {"query": {"script_score": {"query": {"match_all": {}}, "script": {"source": "cosineSimilarity(params.q, 'vector') + 1.0", "params": {"q": [float(x) for x in q[pos[qid]]]}}}},
                "_source": [a.id_field], "size": K}
        r = es.search(index=a.index, body=body)
        run[qid] = [(str(get_path(h["_source"], a.id_field)), h["_score"]) for h in r["hits"]["hits"]]
    write_run(a.out_run, run, "es-exact")
    print(json.dumps({"queries": len(run), "out": a.out_run}))


def overlap(run, ref, k):
    vals = {}
    for qid, hits in run.items():
        top_ref = [p for p, _ in ref.get(qid, [])][:k]
        if not top_ref:
            continue
        vals[qid] = len(set(p for p, _ in hits[:k]) & set(top_ref)) / len(top_ref)
    v = list(vals.values())
    return {"k": k, "queries": len(v), "mean": statistics.fmean(v) if v else None, "lowest": min(v) if v else None, "under_0_9": sum(1 for x in v if x < 0.9)}


def read_run(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        qid, _, pid, rank, score, _ = line.split()
        out.setdefault(qid, []).append((pid, float(score)))
    return out


def run_score(a):
    import retrieval_metrics as M
    run, ref = read_run(a.run), read_run(a.reference)
    rec = {"run": os.path.basename(a.run), "reference": os.path.basename(a.reference), "overlap_at_10": overlap(run, ref, 10), "overlap_at_100": overlap(run, ref, 100)}
    if a.qrels:
        import retrieval_datasets as R
        qrels = R.read_qrels_beir(a.qrels) if a.qrels.endswith(".tsv") else R.read_qrels_trec(a.qrels)
        rec["metrics"] = M.evaluate(qrels, {q: {p: s for p, s in h} for q, h in run.items()})
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: v for k, v in rec.items() if k != "metrics"}))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("search", "negative", "exact", "score"))
    for x in ("--es", "--index", "--fp16-dir", "--checkpoints", "--out-run", "--out-timing", "--ids", "--only-ids", "--run", "--reference", "--qrels", "--out"):
        ap.add_argument(x)
    ap.add_argument("--id-field", default="metadata.source.source_name")
    a = ap.parse_args()
    if a.cmd == "search":
        run_search(a, K, NUM_CANDIDATES, False, "es-knn-default")
    elif a.cmd == "negative":
        run_search(a, 10, 10, True, "es-knn-nc10-norescore")
    elif a.cmd == "exact":
        run_exact(a)
    else:
        run_score(a)


if __name__ == "__main__":
    main()
