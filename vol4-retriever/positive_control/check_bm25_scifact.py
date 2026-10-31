#!/usr/bin/env python3
"""Tool check of Vol.4: does our metric program give the published score on a ranking somebody else produced?

The ranking is Pyserini's BM25 baseline on BEIR SciFact, made with the command and the prebuilt index of Pyserini's own
reproduction page (run_bm25_scifact.sh). The published scores are the ones in pyserini/2cr/beir.yaml. This program scores
that ranking with scripts/retrieval_metrics.py against the qrels of the BEIR download and compares four decimals.

Two controls that must fail, so that a match means something:
  - the qrels given to the wrong queries (a fixed shuffle): the score must collapse;
  - half of the queries removed from the ranking: the score must fall to about half (missing queries count as 0).

usage: check_bm25_scifact.py --run RUN.trec --datasets DIR --out bm25_scifact.json [--pyserini-eval FILE]
  --pyserini-eval  the text Pyserini's own trec_eval printed for the same ranking (kept beside ours in the record)
"""
import argparse, hashlib, importlib.metadata as md, json, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import retrieval_datasets as ds  # noqa: E402
import retrieval_metrics as rm  # noqa: E402

PUBLISHED = {"source": "pyserini/2cr/beir.yaml, condition bm25-flat, dataset scifact", "repository": "https://github.com/castorini/pyserini",
             "commit": "2aa191adb329", "commit_date": "2026-09-30", "nDCG@10": 0.6789, "R@100": 0.9253, "R@1000": 0.9767,
             "command": "python -m pyserini.search.lucene --threads 16 --batch-size 128 --index beir-v1.0.0-scifact.flat --topics beir-v1.0.0-scifact-test "
                        "--output run.beir.bm25-flat.scifact.txt --output-format trec --hits 1000 --bm25 --remove-query"}


def library_version():
    """Which distribution provides the pytrec_eval module here, and its version."""
    for dist in ("pytrec-eval-terrier", "pytrec_eval"):
        try:
            return {"distribution": dist, "version": md.version(dist)}
        except md.PackageNotFoundError:
            pass
    return {"distribution": None, "version": None}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS")); ap.add_argument("--out", required=True); ap.add_argument("--pyserini-eval")
    a = ap.parse_args()
    d = ds.load(a.datasets, "beir-scifact", "test"); run = rm.read_run_trec(a.run)
    ours = rm.evaluate(d.qrels, run)
    q = sorted(d.qrels); shuffled = q[:]; random.Random(1).shuffle(shuffled)
    wrong = rm.evaluate({x: d.qrels[y] for x, y in zip(q, shuffled)}, run)
    half = rm.evaluate(d.qrels, {x: run[x] for x in sorted(run)[: len(run) // 2]})
    same = round(ours["ndcg_cut_10"], 4) == PUBLISHED["nDCG@10"] and round(ours["recall_100"], 4) == PUBLISHED["R@100"]
    qrels_file = os.path.join(a.datasets, "beir-scifact", "scifact", "qrels", "test.tsv")
    rec = {"what": "our metric program on Pyserini's BM25 ranking of BEIR SciFact, against the published scores",
           "published": PUBLISHED,
           "ranking": {"file": os.path.basename(a.run), "sha256": sha256(a.run), "lines": sum(1 for _ in open(a.run, encoding="utf-8")), "queries": len(run),
                       "kept": "outside the repository (a ranking of a data set's passage ids)"},
           "qrels": {"file": "scifact/qrels/test.tsv of the BEIR zip", "sha256": sha256(qrels_file), "queries": len(d.qrels), "rows": sum(len(v) for v in d.qrels.values())},
           "ours": {"program": "scripts/retrieval_metrics.py", "nDCG@10": ours["ndcg_cut_10"], "R@100": ours["recall_100"], "queries_scored": ours["queries_scored"],
                    "queries_with_results": ours["queries_with_results"], "metric_library": library_version()},
           "rounded_to_four_decimals": {"nDCG@10": round(ours["ndcg_cut_10"], 4), "R@100": round(ours["recall_100"], 4)},
           "verdict": "identical to the published four decimals" if same else "DIFFERENT from the published four decimals",
           "controls_that_must_fail": {
               "qrels_given_to_the_wrong_queries": {"nDCG@10": wrong["ndcg_cut_10"], "R@100": wrong["recall_100"], "fails_as_it_should": wrong["ndcg_cut_10"] < 0.1},
               "half_of_the_queries_removed_from_the_ranking": {"nDCG@10": half["ndcg_cut_10"], "R@100": half["recall_100"], "queries_counted_as_zero": half["queries_without_results_counted_as_zero"],
                                                                "fails_as_it_should": abs(half["ndcg_cut_10"] - ours["ndcg_cut_10"] / 2) < 0.05}}}
    if a.pyserini_eval:
        t = open(a.pyserini_eval, encoding="utf-8", errors="replace").read()
        rec["pyserini_own_evaluation_of_the_same_ranking"] = {m.group(1): float(m.group(2)) for m in re.finditer(r"^(ndcg_cut_10|recall_100|recall_1000)\s+all\s+([0-9.]+)\s*$", t, re.M)}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"verdict": rec["verdict"], **rec["rounded_to_four_decimals"], "controls": {k: v["fails_as_it_should"] for k, v in rec["controls_that_must_fail"].items()}}))
    return 0 if same and all(v["fails_as_it_should"] for v in rec["controls_that_must_fail"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
