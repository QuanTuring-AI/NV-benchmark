#!/usr/bin/env python3
"""Vol.5 · cell C1, the num_candidates probe: the same kNN query as es_ann_vs_exact.py `search`, with other values of
k and num_candidates, for every question; quality only (no timing: the calls are not timed, the record says
latency_not_measured). The query, the vectors and the id field are es_ann_vs_exact.py's own (imported, not copied).

Two settings, because the Blueprint has one knob for both numbers:
  blueprint  k = num_candidates = V: what VECTOR_DB_TOPK (or a request's vdb_top_k) does. langchain-elasticsearch 1.0.0
             passes num_candidates = fetch_k, and the Blueprint passes k = fetch_k = top_k (elastic_vdb.py:1107);
             the Blueprint accepts 1..400 (rag_server/validation.py:139). V is also the number of passages sent to the
             reranker, so the run keeps all V results.
  es-only    k = 100, num_candidates = V: the search engine's own setting, not reachable through the Blueprint.
The index's rescore setting (oversample 3.0, from the mapping) is not changed.

usage: es_num_candidates.py --es URL --index NAME --fp16-dir DIR --checkpoints FILE --setting blueprint|es-only --value V
                            --out-run FILE
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import es_ann_vs_exact as E  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    for x in ("--es", "--index", "--fp16-dir", "--checkpoints", "--setting", "--out-run"):
        ap.add_argument(x, required=True)
    ap.add_argument("--value", type=int, required=True); ap.add_argument("--id-field", default="metadata.source.source_name")
    a = ap.parse_args()
    if a.setting == "blueprint":
        if not 1 <= a.value <= 400:
            raise SystemExit("refused: the Blueprint accepts vdb_top_k 1..400")
        k, nc = a.value, a.value
    elif a.setting == "es-only":
        k, nc = 100, a.value
    else:
        raise SystemExit("refused: --setting is blueprint or es-only")
    from elasticsearch import Elasticsearch
    es = Elasticsearch(a.es, request_timeout=600)
    ids, q = E.queries(a.fp16_dir, a.checkpoints); run = {}
    for qid, vec in zip(ids, q):
        r = es.search(index=a.index, body=E.knn_body(vec, k, nc, a.id_field))
        run[qid] = [(str(E.get_path(h["_source"], a.id_field)), h["_score"]) for h in r["hits"]["hits"]]
    E.write_run(a.out_run, run, f"es-knn-{a.setting}-{a.value}")
    rec = {"queries": len(run), "setting": a.setting, "k": k, "num_candidates": nc, "latency_not_measured": "daytime_host",
           "results_per_query": sorted({len(v) for v in run.values()}), "out": a.out_run}
    json.dump(rec, open(os.path.splitext(a.out_run)[0] + ".json", "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
