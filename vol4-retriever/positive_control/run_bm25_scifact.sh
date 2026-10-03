#!/usr/bin/env bash
# Tool check of Vol.4, step 1: Pyserini's BM25 baseline on BEIR SciFact, in a CPU-only container (no GPU argument).
# The command and the prebuilt index are the ones of Pyserini's reproduction page (pyserini/2cr/beir.yaml, bm25-flat).
#   OUT    a folder outside the repository for the ranking (it lists passage ids of a data set and is not published)
#   CACHE  a folder outside the repository where Pyserini keeps the index it downloads
# usage: OUT=/path/to/out CACHE=/path/to/cache ./run_bm25_scifact.sh
# then:  python check_bm25_scifact.py --run $OUT/run.beir.bm25-flat.scifact.txt --datasets <data sets> \
#            --pyserini-eval $OUT/pyserini_trec_eval.txt --out bm25_scifact.json
set -euo pipefail
: "${OUT:?set OUT to a folder outside the repository}"; : "${CACHE:?set CACHE to a folder outside the repository}"
IMAGE=vol4-bm25-positive-control:pyserini-2.4.0
HERE="$(cd "$(dirname "$0")" && pwd)"
docker image inspect "$IMAGE" >/dev/null 2>&1 || docker build -t "$IMAGE" "$HERE"
mkdir -p "$OUT" "$CACHE"
MSYS_NO_PATHCONV=1 docker run --rm -v "$CACHE:/root/.cache/pyserini" -v "$OUT:/out" "$IMAGE" bash -c '
  set -e
  python -m pyserini.search.lucene --threads 16 --batch-size 128 \
    --index beir-v1.0.0-scifact.flat --topics beir-v1.0.0-scifact-test \
    --output /out/run.beir.bm25-flat.scifact.txt --output-format trec --hits 1000 --bm25 --remove-query
  for m in ndcg_cut.10 recall.100 recall.1000; do
    python -m pyserini.eval.trec_eval -c -m $m beir-v1.0.0-scifact-test /out/run.beir.bm25-flat.scifact.txt
  done | grep -E "^(ndcg_cut_10|recall_100|recall_1000)" > /out/pyserini_trec_eval.txt
  cat /out/pyserini_trec_eval.txt'
