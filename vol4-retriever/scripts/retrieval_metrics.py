#!/usr/bin/env python3
"""The two retrieval metrics of Vol.4, nDCG@10 and Recall@100, computed with pytrec_eval (the Python binding of
trec_eval, the tool the BEIR and MIRACL figures are reported with).

Definitions, fixed here so that a number can be traced:
  nDCG@10      trec_eval's `ndcg_cut.10`: the gain of a passage is its relevance value as written in the qrels (1, 2, ...),
               the discount is 1 / log2(rank + 1), and the ideal ranking is built from all relevant passages of the query.
  Recall@100   trec_eval's `recall.100`: relevant passages among the first 100 results / all relevant passages of the query.
  relevant     a judgement greater than 0. A judgement of 0 is a passage judged not relevant.
  ranking      by score, highest first. The rank column of a run file is not used. Passages with the same score are
               ordered by passage id, later id first (trec_eval's rule); this is tested, not assumed.
  average      over the queries of the qrels that have at least one relevant passage. A query without results counts as
               0 (trec_eval's `-c`). Queries of the run that are not in the qrels are ignored and counted.
  ignore_identical_ids   optional: a result whose passage id equals the query id is removed before scoring (BEIR's
               default for its own evaluation; Pyserini removes them at search time with --remove-query).

A query of the qrels without any relevant passage cannot be scored by these two metrics. The four data sets of Vol.4
have none; if one appears, the evaluation stops instead of deciding silently how to count it.

usage: retrieval_metrics.py --run RUN.trec (--qrels FILE --qrels-format beir|trec | --datasets DIR --name NAME [--split S])
                            [--ignore-identical-ids] [--out FILE.json]
"""
import argparse, json, os, sys

import pytrec_eval

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retrieval_datasets as ds  # noqa: E402

NDCG_K, RECALL_K = 10, 100


def read_run_trec(path):
    """TREC run file: query id, Q0, passage id, rank, score, tag. -> {query id: {passage id: score}}"""
    run = {}
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 6:
                raise ValueError(f"{path}:{n}: expected 6 fields, found {len(parts)}")
            q = run.setdefault(parts[0], {})
            if parts[2] in q:
                raise ValueError(f"{path}:{n}: passage {parts[2]} is listed twice for query {parts[0]}")
            q[parts[2]] = float(parts[4])
    return run


def evaluate(qrels, run, ndcg_k=NDCG_K, recall_k=RECALL_K, ignore_identical_ids=False, per_query=False):
    """qrels: {query id: {passage id: int}} · run: {query id: {passage id: float}} -> dict of the two means and the counts."""
    no_relevant = sorted(q for q, rels in qrels.items() if not any(r > 0 for r in rels.values()))
    if no_relevant:
        raise ValueError(f"{len(no_relevant)} queries of the qrels have no relevant passage (first: {no_relevant[0]}); how to count them has to be decided, it is not decided here")
    if ignore_identical_ids:
        run = {q: {d: s for d, s in docs.items() if d != q} for q, docs in run.items()}
    scored = sorted(qrels)
    usable = {q: {d: float(s) for d, s in run[q].items()} for q in scored if run.get(q)}
    k_ndcg, k_recall = f"ndcg_cut_{ndcg_k}", f"recall_{recall_k}"
    ev = pytrec_eval.RelevanceEvaluator({q: {d: int(r) for d, r in qrels[q].items()} for q in scored}, {f"ndcg_cut.{ndcg_k}", f"recall.{recall_k}"})
    per = ev.evaluate(usable) if usable else {}
    n = len(scored)
    out = {k_ndcg: sum(per.get(q, {}).get(k_ndcg, 0.0) for q in scored) / n, k_recall: sum(per.get(q, {}).get(k_recall, 0.0) for q in scored) / n,
           "queries_scored": n, "queries_with_results": len(usable), "queries_without_results_counted_as_zero": n - len(usable),
           "queries_in_run_not_in_qrels": len(set(run) - set(qrels)), "ignore_identical_ids": ignore_identical_ids,
           "metric_library": {"module": "pytrec_eval", "measures": [f"ndcg_cut.{ndcg_k}", f"recall.{recall_k}"]}}
    if per_query:
        out["per_query"] = {q: {k_ndcg: per.get(q, {}).get(k_ndcg, 0.0), k_recall: per.get(q, {}).get(k_recall, 0.0)} for q in scored}
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--qrels"); ap.add_argument("--qrels-format", choices=["beir", "trec"])
    ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS")); ap.add_argument("--name", choices=ds.NAMES); ap.add_argument("--split")
    ap.add_argument("--ignore-identical-ids", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args()
    if a.qrels:
        if not a.qrels_format:
            sys.exit("--qrels needs --qrels-format beir|trec")
        qrels = ds.read_qrels_beir(a.qrels) if a.qrels_format == "beir" else ds.read_qrels_trec(a.qrels)
        source = {"qrels_file": os.path.basename(a.qrels), "format": a.qrels_format}
    elif a.name:
        d = ds.load(a.datasets, a.name, a.split); qrels = d.qrels; source = {"dataset": d.name, "split": d.split}
    else:
        sys.exit("give --qrels FILE --qrels-format ..., or --datasets DIR --name NAME")
    res = evaluate(qrels, read_run_trec(a.run), ignore_identical_ids=a.ignore_identical_ids)
    res["qrels"] = source; res["run_file"] = os.path.basename(a.run)
    if a.out:
        json.dump(res, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
