#!/usr/bin/env python3
"""Vol.4 · the method cell: the same requests to the same NIM from two places (a container on the NIM's Docker
network, and the host through the published port) and with two kinds of connection (one kept, a new one per request).
Every request's duration is kept, because the question is the shape of the durations and not only their middle.

Written after the pre-registration was frozen: the pre-registration describes this cell and asks for the per-request
durations, which the bound cell program (embed_cell.py) does not write out. This program takes its texts and its
client from the bound files (embed_cell.load_texts, nim_retrieval_clients.EmbeddingClient) and adds only the recording.
Its SHA-256 is written to the events file before its first use.

  --batch 64   the request of the cells (the first 4,096 passages, 64 per request): 64 requests per pass
  --batch 1    one passage per request (the first --n passages): the server's own time is short, so a cost of the
               connection shows as a share of the whole

usage: method_cell.py --where container|host --dataset NAME --datasets DIR --url URL --model NAME --out FILE.json
                      [--batch 64] [--n 4096] [--reps 3] [--new-connection]
"""
import argparse, collections, hashlib, json, math, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import embed_cell as ec  # noqa: E402
import retrieval_datasets as ds  # noqa: E402
from nim_retrieval_clients import EmbeddingClient  # noqa: E402


def nr(v, p):
    v = sorted(v); return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--where", choices=["container", "host"], required=True); ap.add_argument("--dataset", required=True, choices=ds.NAMES)
    ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS")); ap.add_argument("--url", required=True); ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--batch", type=int, default=64); ap.add_argument("--n", type=int, default=4096)
    ap.add_argument("--reps", type=int, default=3); ap.add_argument("--truncate", default="END"); ap.add_argument("--new-connection", action="store_true")
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    _d, _qids, _qtexts, _pids, texts = ec.load_texts(a, limit_corpus=a.n)
    client = EmbeddingClient(a.url, a.model, timeout=600, keep_alive=not a.new_connection)
    client.embed(texts[: 4 * a.batch], "passage", truncate=a.truncate, batch_size=a.batch)          # discarded
    client.calls.clear()
    passes = []
    for _ in range(a.reps):
        start = ec.now(); first = len(client.calls); t = time.perf_counter()
        client.embed(texts, "passage", truncate=a.truncate, batch_size=a.batch)
        s = time.perf_counter() - t
        passes.append({"start": start, "end": ec.now(), "seconds": round(s, 3), "passages_per_s": round(len(texts) / s, 1), "requests": len(client.calls) - first})
    ms = [round(c["seconds"] * 1000, 2) for c in client.calls]
    width = 2 if a.batch == 1 else 5
    hist = collections.Counter(int(x // width) * width for x in ms)
    rates = sorted(p["passages_per_s"] for p in passes)
    out = {"what": "the same requests from one place with one kind of connection; every request's duration", "at": ec.now(), "where": a.where,
           "connection": "a new connection per request" if a.new_connection else "one kept connection", "url_kind": "the NIM by its name on the Docker network" if a.where == "container" else "the published port on 127.0.0.1",
           "dataset": a.dataset, "model": a.model, "truncate": a.truncate, "batch": a.batch, "passages": len(texts), "reps": a.reps, "discarded": "one pass over the first 4 batches",
           "passes": passes, "passages_per_s_median": rates[len(rates) // 2],
           "request_ms": {"count": len(ms), "p10": nr(ms, 10), "p50": nr(ms, 50), "p90": nr(ms, 90), "p99": nr(ms, 99), "min": min(ms), "max": max(ms),
                          "more_than_10_ms_above_p10": sum(x > nr(ms, 10) + 10 for x in ms), "histogram_bin_ms": width, "histogram": {str(k): hist[k] for k in sorted(hist)}},
           "request_ms_all": ms,
           "program": {"file": "method_cell.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest(), "bound_files_used": ["embed_cell.py", "nim_retrieval_clients.py", "retrieval_datasets.py"]}}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"where": a.where, "connection": out["connection"], "batch": a.batch, "passages_per_s_median": out["passages_per_s_median"], "request_ms": {k: out["request_ms"][k] for k in ("p10", "p50", "p90", "p99", "more_than_10_ms_above_p10")}}))


if __name__ == "__main__":
    sys.exit(main())
