#!/usr/bin/env python3
"""Vol.4 · one reranking cell: the first --depth results of a first-stage ranking (a TREC run file) are scored again by
a reranking NIM, one call per query, and written as a new run file.

  one call per query, with all --depth passages of that query (the documented limit of a call is 512 passages).
  Scores of different calls are never put on one scale: a query's passages are ordered by the logits of its own call.
  truncate is sent on every request. The query is sent as written, the passage as title, one space, text.

Subcommands
  smoke        three queries: every call must return one finite logit per passage.
  throughput   the timed part: the first --n-queries queries, one discarded pass over the first 4, then --reps timed
               passes. Reports passage-query pairs per second per pass and their median.
  rerank       the untimed part: every query of the run file. Writes the reranked run outside the repository; its wall
               time is recorded and is not a throughput figure.

usage: rerank_cell.py <subcommand> --dataset NAME --datasets DIR --run-in FILE.trec --url URL --model NAME --out FILE.json
                      [--run-out FILE.trec] [--depth 100] [--truncate END] [--n-queries 40] [--reps 3]
"""
import argparse, hashlib, json, math, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retrieval_datasets as ds  # noqa: E402


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_run(path):
    run = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = line.split()
            if len(p) >= 5:
                run.setdefault(p[0], []).append((p[2], float(p[4])))
    return {q: [d for d, _ in sorted(v, key=lambda x: -x[1])] for q, v in run.items()}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["smoke", "throughput", "rerank"])
    ap.add_argument("--dataset", required=True, choices=ds.NAMES); ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS"))
    ap.add_argument("--run-in", required=True); ap.add_argument("--run-out"); ap.add_argument("--url", required=True); ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--depth", type=int, default=100); ap.add_argument("--truncate", default="END")
    ap.add_argument("--n-queries", type=int, default=40); ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    from nim_retrieval_clients import MAX_PASSAGES, RerankClient
    if a.depth > MAX_PASSAGES:
        raise SystemExit(f"refused: --depth {a.depth} is more than one call takes ({MAX_PASSAGES})")
    d = ds.load(a.datasets, a.dataset)
    first = read_run(a.run_in)
    qids = sorted(q for q in first if q in d.queries)
    need = {p for q in qids for p in first[q][: a.depth]}
    text = {pid: ds.passage_text(title, body) for pid, title, body in d.iter_corpus() if pid in need}
    missing = need - set(text)
    if missing:
        raise SystemExit(f"refused: {len(missing)} passages of the run file are not in the corpus")
    client = RerankClient(a.url, a.model, timeout=1800)

    def one(q):
        pids = first[q][: a.depth]
        logits, usage = client.rerank(d.queries[q], [text[p] for p in pids], truncate=a.truncate)
        if any(l is None or not math.isfinite(l) for l in logits):
            raise SystemExit(f"a logit is missing or not finite for one query ({len(logits)} passages)")
        return pids, logits

    rec = {"at": now(), "dataset": a.dataset, "split": d.split, "url": a.url, "model": a.model, "truncate": a.truncate, "depth": a.depth,
           "first_stage_run": {"name": os.path.basename(a.run_in), "sha256": sha256_file(a.run_in)}, "queries_in_the_run": len(qids),
           "connection": "one kept connection", "rule": "one call per query; a query's passages are ordered by the logits of its own call"}
    if a.cmd == "smoke":
        got = [one(q) for q in qids[:3]]
        rec.update({"calls": 3, "passages_per_call": [len(p) for p, _ in got], "pass": all(len(p) == len(l) for p, l in got)})
    elif a.cmd == "throughput":
        sample = qids[: a.n_queries]
        for q in sample[:4]:
            one(q)                                                # discarded
        passes = []
        for _ in range(a.reps):
            start = now(); t = time.perf_counter(); pairs = 0
            for q in sample:
                p, _l = one(q); pairs += len(p)
            s = time.perf_counter() - t
            passes.append({"start": start, "end": now(), "seconds": round(s, 3), "pairs": pairs, "pairs_per_s": round(pairs / s, 1), "queries_per_s": round(len(sample) / s, 2)})
        rates = sorted(p["pairs_per_s"] for p in passes)
        rec.update({"what": "timed passes over the first queries of the run file", "sample_queries": len(sample), "reps": a.reps, "discarded": "one pass over the first 4 queries",
                    "passes": passes, "pairs_per_s_median": rates[len(rates) // 2], "pairs_per_s_min": rates[0], "pairs_per_s_max": rates[-1]})
    else:
        if not a.run_out or os.path.exists(a.run_out):
            raise SystemExit("refused: --run-out is missing or exists")
        start = now(); t = time.perf_counter(); n = 0
        os.makedirs(os.path.dirname(os.path.abspath(a.run_out)), exist_ok=True)
        with open(a.run_out, "w", encoding="utf-8", newline="\n") as f:
            for i, q in enumerate(qids):
                pids, logits = one(q); n += len(pids)
                for r, (p, l) in enumerate(sorted(zip(pids, logits), key=lambda x: -x[1]), 1):
                    f.write(f"{q} Q0 {p} {r} {l:.6f} rerank\n")
                if (i + 1) % 100 == 0:
                    print(f"  {a.dataset}: {i + 1} of {len(qids)} queries, {time.perf_counter() - t:.0f} s", flush=True)
        rec.update({"what": "every query reranked; the wall time is recorded and is not a throughput figure", "start": start, "end": now(), "seconds": round(time.perf_counter() - t, 1),
                    "pairs": n, "run_file": {"name": os.path.basename(a.run_out), "sha256": sha256_file(a.run_out), "kept_outside_the_repository": True}})
    rec["calls"] = len(client.calls)
    rec["program"] = {"file": "rerank_cell.py", "sha256": sha256_file(os.path.abspath(__file__))}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({k: rec[k] for k in rec if k in ("pass", "pairs_per_s_median", "seconds", "pairs", "calls")}))
    return 0 if rec.get("pass", True) else 3


if __name__ == "__main__":
    sys.exit(main())
