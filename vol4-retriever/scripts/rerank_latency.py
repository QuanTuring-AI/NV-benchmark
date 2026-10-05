#!/usr/bin/env python3
"""Vol.4 · how long one reranking call takes: every query of a first-stage ranking, its first --depth passages in one
call, one call after the other on one kept connection, and the duration of every call.

The request is the one of rerank_cell.py (the same client class, truncate sent on every request, the query as written,
a passage as title, one space, text); that program writes the reranked ranking and a rate over 40 queries, and does not
keep the durations. This one keeps them and writes no ranking.

  discarded   one pass over the first 4 queries.
  timed       --passes passes over all queries of the run file, in the order of their ids. A pass is one sample of
              (number of queries) call durations; the passes are reported one by one and are not pooled.
  percentile  nearest rank: the value at position ceil(p/100 x n) of the sorted durations.
  written     per pass the durations in milliseconds in call order (numbers only), their p50 / p90 / p99 / min / max,
              the pass's wall time and pairs per second; the number of passages per call; no text and no ids.

A duration is measured in the client: from sending the request to having the parsed answer. Where the client runs
(--where container: on the NIM's Docker network; host: through the published port) is part of the result.

usage: rerank_latency.py --where container|host --dataset NAME --datasets DIR --run-in FILE.trec --url URL --model NAME
                         --out FILE.json [--depth 100] [--passes 2] [--truncate END]
"""
import argparse, hashlib, json, math, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def nearest_rank(values, p):
    v = sorted(values)
    return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def summary(ms):
    return {"calls": len(ms), "p50": nearest_rank(ms, 50), "p90": nearest_rank(ms, 90), "p99": nearest_rank(ms, 99), "min": min(ms), "max": max(ms),
            "mean": round(sum(ms) / len(ms), 2)}


def main():
    import rerank_cell as rc
    import retrieval_datasets as ds
    from nim_retrieval_clients import MAX_PASSAGES, RerankClient
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--where", choices=["container", "host"], required=True); ap.add_argument("--dataset", required=True, choices=ds.NAMES)
    ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS")); ap.add_argument("--run-in", required=True); ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True); ap.add_argument("--out", required=True); ap.add_argument("--depth", type=int, default=100)
    ap.add_argument("--passes", type=int, default=2); ap.add_argument("--truncate", default="END")
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    if a.depth > MAX_PASSAGES:
        raise SystemExit(f"refused: --depth {a.depth} is more than one call takes ({MAX_PASSAGES})")
    d = ds.load(a.datasets, a.dataset)
    first = rc.read_run(a.run_in)
    qids = sorted(q for q in first if q in d.queries)
    need = {p for q in qids for p in first[q][: a.depth]}
    text = {pid: ds.passage_text(title, body) for pid, title, body in d.iter_corpus() if pid in need}
    if need - set(text):
        raise SystemExit(f"refused: {len(need - set(text))} passages of the run file are not in the corpus")
    client = RerankClient(a.url, a.model, timeout=600)

    def one(q):
        pids = first[q][: a.depth]
        logits, _usage = client.rerank(d.queries[q], [text[p] for p in pids], truncate=a.truncate)
        if any(l is None or not math.isfinite(l) for l in logits):
            raise SystemExit("a logit is missing or not finite")
        return len(pids)

    for q in qids[:4]:
        one(q)                                                # discarded
    passes = []
    for _ in range(a.passes):
        client.calls.clear(); start = now(); t = time.perf_counter()
        pairs = sum(one(q) for q in qids)
        s = time.perf_counter() - t
        ms = [round(c["seconds"] * 1000, 2) for c in client.calls]
        passes.append({"start": start, "end": now(), "seconds": round(s, 3), "pairs": pairs, "pairs_per_s": round(pairs / s, 1),
                       "call_ms": summary(ms), "passages_per_call": {"min": min(c["items"] for c in client.calls), "max": max(c["items"] for c in client.calls)},
                       "call_ms_all": ms})
    out = {"what": "the duration of every reranking call: one call per query with its first passages, one after the other on one kept connection",
           "at": now(), "where": a.where, "url_kind": "the NIM by its name on the Docker network" if a.where == "container" else "the published port on 127.0.0.1",
           "dataset": a.dataset, "split": d.split, "model": a.model, "truncate": a.truncate, "depth": a.depth, "queries": len(qids),
           "first_stage_run": {"name": os.path.basename(a.run_in), "sha256": hashlib.sha256(open(a.run_in, "rb").read()).hexdigest()},
           "discarded": "one pass over the first 4 queries", "percentile": "nearest rank", "passes": passes,
           "program": {"file": "rerank_latency.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
                       "bound_files_used": ["rerank_cell.py", "nim_retrieval_clients.py", "retrieval_datasets.py"]}}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"dataset": a.dataset, "queries": len(qids), "passes": [{k: p[k] for k in ("seconds", "pairs_per_s")} | {"call_ms": p["call_ms"]} for p in passes]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
