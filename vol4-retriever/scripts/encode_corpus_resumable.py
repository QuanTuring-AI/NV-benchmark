#!/usr/bin/env python3
"""Vol.4 · encode a whole corpus with a running embedding NIM, in pieces that survive a stop.

The corpus is read as a stream in file order. Every --piece passages (100,000 by default) the vectors of that piece are
written to the folder outside the repository (float32 .npy, with the ids beside them) and one line is appended to the
checkpoint file inside the repository: counts, seconds, SHA-256 values — no text. A later call with the same arguments
reads the checkpoint file, skips the passages already done and goes on. At --stop-at (a time with its UTC offset, because the
program runs in a container whose clock is UTC) the program writes what it has as a shorter piece and ends with exit
code 0.

Not a throughput measurement: the wall time of a piece is recorded and is not a speed figure (other work may share the
card; the timed figure of a cell comes from embed_cell.py throughput).

Requests are those of embed_cell.py's nim backend (the same client class, input_type "passage" or "query", truncate
END, --batch texts per request, one kept connection). The queries of the split are encoded once, at the first call.

usage: encode_corpus_resumable.py --dataset miracl-zh --datasets DIR --url http://host:8000 --model NAME
                                  --emb-dir DIR --checkpoints FILE.jsonl [--piece 100000] [--batch 64]
                                  [--stop-at 2026-10-05T08:00:00+0800] [--limit N] [--dim 2048]
exit codes: 0 finished or stopped at the stop time (the last checkpoint line says which) · 2 refused · 1 error
"""
import argparse, datetime, hashlib, json, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retrieval_datasets as ds  # noqa: E402
from nim_retrieval_clients import EmbeddingClient  # noqa: E402


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_checkpoints(path):
    if not os.path.isfile(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def append(path, rec):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush(); os.fsync(f.fileno())


def done_passages(checkpoints, emb_dir):
    """Passages covered by the pieces on record; every piece on record must be on disk with the recorded hash."""
    n = 0
    for c in checkpoints:
        if c.get("kind") != "piece":
            continue
        if c["first"] != n:
            raise SystemExit(f"refused: the pieces on record are not contiguous (piece {c['piece']} starts at {c['first']}, expected {n})")
        p = os.path.join(emb_dir, c["vectors_file"])
        if not os.path.isfile(p) or sha256_file(p) != c["vectors_sha256"]:
            raise SystemExit(f"refused: {c['vectors_file']} is missing or does not have the recorded SHA-256")
        n += c["passages"]
    return n


def stop_time(text):
    """Seconds since the epoch of a time written with its UTC offset; a time without an offset is refused."""
    if not text:
        return None
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        raise SystemExit(f"refused: --stop-at needs a time with its UTC offset, like 2026-10-05T08:00:00+0800 (got {text!r})")


def write_piece(a, index, first, ids, vectors, seconds, tokens, started, reason):
    name = f"corpus-{index:05d}.npy"; ids_name = f"ids-{index:05d}.json"
    v = np.concatenate(vectors, axis=0).astype(np.float32, copy=False)
    if v.shape[0] != len(ids):
        raise SystemExit(f"error: {v.shape[0]} vectors for {len(ids)} passages")
    np.save(os.path.join(a.emb_dir, name), v)
    json.dump(ids, open(os.path.join(a.emb_dir, ids_name), "w", encoding="utf-8"))
    norms = np.linalg.norm(v, axis=1)
    rec = {"kind": "piece", "piece": index, "first": first, "passages": len(ids), "start": started, "end": now(), "seconds": round(seconds, 1),
           "tokens_reported": tokens or None, "size": int(v.shape[1]), "size_as_expected": (a.dim is None or int(v.shape[1]) == a.dim),
           "all_finite": bool(np.isfinite(v).all()), "norm_min": float(norms.min()), "norm_max": float(norms.max()),
           "vectors_file": name, "vectors_sha256": sha256_file(os.path.join(a.emb_dir, name)), "ids_file": ids_name,
           "ids_sha256": sha256_file(os.path.join(a.emb_dir, ids_name)), "closed_because": reason}
    append(a.checkpoints, rec)
    print(f"  piece {index}: passages {first:,} to {first + len(ids):,}, {seconds:.0f} s ({reason})", flush=True)
    return rec


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=ds.NAMES); ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS"))
    ap.add_argument("--url", required=True); ap.add_argument("--model", required=True); ap.add_argument("--truncate", default="END")
    ap.add_argument("--emb-dir", required=True); ap.add_argument("--checkpoints", required=True)
    ap.add_argument("--piece", type=int, default=100000); ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--stop-at"); ap.add_argument("--limit", type=int); ap.add_argument("--dim", type=int)
    a = ap.parse_args()
    stop = stop_time(a.stop_at)
    os.makedirs(a.emb_dir, exist_ok=True)
    cps = read_checkpoints(a.checkpoints)
    if any(c.get("kind") == "finished" for c in cps):
        print("nothing to do: the checkpoint file says the corpus is finished"); return 0
    head = next((c for c in cps if c.get("kind") == "session"), None)
    for key, val in (("dataset", a.dataset), ("model", a.model), ("piece", a.piece), ("batch", a.batch), ("truncate", a.truncate), ("limit", a.limit)):
        if head and head.get(key) != val:
            raise SystemExit(f"refused: the checkpoint file was started with {key}={head.get(key)!r}, this call says {val!r}")
    done = done_passages(cps, a.emb_dir)
    d = ds.load(a.datasets, a.dataset)
    client = EmbeddingClient(a.url, a.model, timeout=1800, keep_alive=True)
    append(a.checkpoints, {"kind": "session", "at": now(), "dataset": a.dataset, "split": d.split, "model": a.model, "url": a.url, "piece": a.piece, "batch": a.batch,
                            "truncate": a.truncate, "limit": a.limit, "stop_at": a.stop_at, "passages_already_done": done, "storage": "float32 .npy outside the repository",
                            "program_sha256": sha256_file(os.path.abspath(__file__)),
                            "text_of_a_passage": "title, one space, text, stripped (retrieval_datasets.passage_text)"})
    if not os.path.isfile(os.path.join(a.emb_dir, "queries.npy")):
        qids = sorted(d.queries); t = time.perf_counter()
        q, usage = client.embed([d.queries[x] for x in qids], "query", truncate=a.truncate, batch_size=a.batch)
        q = np.asarray(q, dtype=np.float32)
        np.save(os.path.join(a.emb_dir, "queries.npy"), q); json.dump(qids, open(os.path.join(a.emb_dir, "query_ids.json"), "w", encoding="utf-8"))
        append(a.checkpoints, {"kind": "queries", "at": now(), "queries": len(qids), "seconds": round(time.perf_counter() - t, 1), "size": int(q.shape[1]),
                                "all_finite": bool(np.isfinite(q).all()), "queries_sha256": sha256_file(os.path.join(a.emb_dir, "queries.npy")),
                                "query_ids_sha256": sha256_file(os.path.join(a.emb_dir, "query_ids.json"))})
    index = sum(1 for c in cps if c.get("kind") == "piece")
    ids, texts, vectors, tokens, seen = [], [], [], 0, 0
    first = done; started = now(); t0 = time.perf_counter(); stopped = False

    def flush_texts():
        nonlocal texts, tokens
        if texts:
            v, usage = client.embed(texts, "passage", truncate=a.truncate, batch_size=a.batch)
            vectors.append(np.asarray(v, dtype=np.float32))
            tokens += sum(u.get("total_tokens") or 0 for u in usage if isinstance(u, dict))
            texts = []

    for pid, title, text in d.iter_corpus():
        seen += 1
        if seen <= done:
            continue
        if a.limit and seen > a.limit:
            seen -= 1; break
        ids.append(pid); texts.append(ds.passage_text(title, text))
        if len(texts) >= 16 * a.batch:
            flush_texts()
            if stop and time.time() >= stop:
                stopped = True
        if len(ids) >= a.piece or (stopped and not texts):
            flush_texts()
            write_piece(a, index, first, ids, vectors, time.perf_counter() - t0, tokens, started, "the stop time was reached" if stopped and len(ids) < a.piece else "full piece")
            first += len(ids); index += 1; ids, vectors, tokens = [], [], 0; started = now(); t0 = time.perf_counter()
            if stopped:
                break
    if not stopped:
        flush_texts()
        if ids:
            write_piece(a, index, first, ids, vectors, time.perf_counter() - t0, tokens, started, "the end of the corpus" if not a.limit else "the limit of this call")
            first += len(ids)
        append(a.checkpoints, {"kind": "finished", "at": now(), "passages": first, "pieces": index + (1 if ids else 0), "corpus_passages_read": seen,
                                "note": ("--limit was set: this is not the whole corpus" if a.limit else "the whole corpus")})
    else:
        append(a.checkpoints, {"kind": "stopped", "at": now(), "passages_done": first, "reason": "the stop time was reached; a later call with the same arguments goes on from here"})
    print(json.dumps({"passages_done": first, "stopped_at_the_stop_time": stopped}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
