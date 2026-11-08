#!/usr/bin/env python3
"""Vol.5 · cell C1 in the clean window: c = 1 latency of the kNN query at several k / num_candidates settings, on a fixed
set of 1,000 questions (seed 20261020, drawn from the sorted ids of the store's query file), every setting one after
the other on the same index in the same window. The query and the vectors are es_ann_vs_exact.py's own (imported).
Each setting: ten warm-up calls kept apart, then the 1,000 calls one at a time, each timed in the client.

Settings: "blueprint:V" = k = num_candidates = V (the Blueprint's knob, 1..400); "es-only:V" = k = 100, num_candidates = V.
usage (in the client container): es_latency_probe.py --es URL --index NAME --fp16-dir DIR --checkpoints FILE
                                 --settings blueprint:100,blueprint:200,... --out FILE [--n 1000]
"""
import argparse, json, os, random, statistics, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import es_ann_vs_exact as E  # noqa: E402

SEED, WARMUP = 20261020, 10


def kn(setting):
    s, v = setting.split(":"); v = int(v)
    return (v, v) if s == "blueprint" else (100, v)


def main():
    ap = argparse.ArgumentParser()
    for x in ("--es", "--index", "--fp16-dir", "--checkpoints", "--settings", "--out"):
        ap.add_argument(x, required=True)
    ap.add_argument("--n", type=int, default=1000); ap.add_argument("--id-field", default="metadata.source.source_name")
    a = ap.parse_args()
    from elasticsearch import Elasticsearch
    es = Elasticsearch(a.es, request_timeout=600)
    ids, q = E.queries(a.fp16_dir, a.checkpoints); pos = {x: i for i, x in enumerate(ids)}
    chosen = sorted(random.Random(SEED).sample(sorted(ids), min(a.n, len(ids))))
    warm_ids = [x for x in sorted(ids) if x not in set(chosen)][:WARMUP]
    out = {"index": a.index, "questions": len(chosen), "seed": SEED, "settings": {}, "measured_in": "the client container, one call at a time, on the store's Docker network"}
    for st in a.settings.split(","):
        k, nc = kn(st)
        warm = []
        for qid in warm_ids:
            t0 = time.perf_counter(); es.search(index=a.index, body=E.knn_body(q[pos[qid]], k, nc, a.id_field)); warm.append((time.perf_counter() - t0) * 1000)
        d = []
        for qid in chosen:
            t0 = time.perf_counter(); es.search(index=a.index, body=E.knn_body(q[pos[qid]], k, nc, a.id_field)); d.append((time.perf_counter() - t0) * 1000)
        d.sort()
        out["settings"][st] = {"k": k, "num_candidates": nc, "warmup_ms": warm, "calls": len(d),
                               "ms": {"p50": statistics.median(d), "p99": d[min(len(d) - 1, int(round(0.99 * (len(d) - 1))))], "mean": statistics.fmean(d)}}
        json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
        print(json.dumps({st: out["settings"][st]["ms"]}))


if __name__ == "__main__":
    main()
