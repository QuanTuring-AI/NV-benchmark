#!/usr/bin/env python3
"""Vol.5 · cell C3, questions without their answer in the store: the 200 questions of the fixed sample
(eval/hotpot_scoring.py c3_sample, seed 20261018) retrieved as arm P retrieves (kNN, k = num_candidates = 100, Vol.4's
query vectors), with each question's two supporting passages kept out by a filter inside the kNN clause:

  knn.filter = {"bool": {"must_not": {"terms": {"metadata.source.source_name.keyword": [the two source names]}}}}

Elasticsearch applies a kNN filter during the graph search (a pre-filter), not after it, so the 100 results are the
nearest of the passages that remain; the record lists how many results each question got. The source name is built
from the night's metadata template (the form es_bulk_load.py wrote). The same query without the filter is run too, so
that the record shows how many supporting passages the filter removed from the top 100 (a positive control: the
filter must remove at least one supporting passage for some questions, and leave none in any filtered run).

usage (in the client container): c3_retrieve.py --es URL --index NAME --fp16-dir DIR --checkpoints FILE --ids FILE
                                 --metadata FILE --out-run FILE --out-unfiltered FILE --out FILE
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(V5, "eval"))
import es_ann_vs_exact as E  # noqa: E402
from es_bulk_load import fill  # noqa: E402
import hotpot_scoring as H  # noqa: E402

K = 100
FIELD = "metadata.source.source_name"


def main():
    ap = argparse.ArgumentParser()
    for x in ("--es", "--index", "--fp16-dir", "--checkpoints", "--ids", "--metadata", "--out-run", "--out-unfiltered", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    from elasticsearch import Elasticsearch
    es = Elasticsearch(a.es, request_timeout=600)
    table = {r["query_id"]: r for r in (json.loads(l) for l in open(a.ids, encoding="utf-8"))}
    sample = H.c3_sample(list(table)); template = json.load(open(a.metadata, encoding="utf-8"))
    qids, q = E.queries(a.fp16_dir, a.checkpoints); pos = {x: i for i, x in enumerate(qids)}
    run, plain, rows = {}, {}, []
    for qid in sample:
        gold = table[qid]["gold_passages"]; names = [fill(template, g)["source"]["source_name"] for g in gold]
        body = E.knn_body(q[pos[qid]], K, K, FIELD)
        r0 = es.search(index=a.index, body=body)
        plain[qid] = [(str(E.get_path(h["_source"], FIELD)), h["_score"]) for h in r0["hits"]["hits"]]
        body["knn"]["filter"] = {"bool": {"must_not": {"terms": {FIELD + ".keyword": names}}}}
        r1 = es.search(index=a.index, body=body)
        run[qid] = [(str(E.get_path(h["_source"], FIELD)), h["_score"]) for h in r1["hits"]["hits"]]
        rows.append({"query_id": qid, "gold_in_unfiltered_top100": sum(p in gold for p, _ in plain[qid]), "gold_in_filtered": sum(p in gold for p, _ in run[qid]),
                     "results_filtered": len(run[qid])})
    E.write_run(a.out_run, run, "c3-knn-filtered"); E.write_run(a.out_unfiltered, plain, "c3-knn-unfiltered")
    rec = {"questions": len(rows), "seed": H.C3_SEED, "filter": "knn.filter bool must_not terms " + FIELD + ".keyword",
           "gold_left_in_any_filtered_run": sum(r["gold_in_filtered"] for r in rows),
           "questions_whose_unfiltered_top100_held_a_supporting_passage": sum(r["gold_in_unfiltered_top100"] > 0 for r in rows),
           "supporting_passages_removed_from_top100": sum(r["gold_in_unfiltered_top100"] for r in rows),
           "results_per_question": sorted({r["results_filtered"] for r in rows}), "rows": rows}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: v for k, v in rec.items() if k != "rows"}))
    ok = rec["gold_left_in_any_filtered_run"] == 0 and rec["supporting_passages_removed_from_top100"] > 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
