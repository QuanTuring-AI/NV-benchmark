#!/usr/bin/env python3
"""Vol.4 · do the stored vectors of a corpus belong to the ids stored beside them? (control C_H of the HotpotQA addendum)

A sample of passages spread evenly over the corpus file is encoded again with the running embedding NIM, in one new
stream of requests, and each new vector is compared with the stored row that the checkpoint layout gives for that
passage's position. Two things are checked per passage: the id stored at that position is the passage's id, and the
cosine of the new vector with the stored one is at least --min-cosine. A shift of one row, a piece written in another
order or ids from another file would fail one of the two.

The requests are those of encode_corpus_resumable.py (the same client class, input_type passage, truncate END, the
same text of a passage). Written: counts, the cosines' minimum and percentiles, ids and positions of passages that
fail (ids only, no text).

usage: check_stored_vectors.py --dataset beir-hotpotqa --datasets DIR --url http://host:8000 --model NAME
                               --emb-dir DIR --checkpoints FILE.jsonl --out FILE.json [--n 1000] [--min-cosine 0.999]
exit codes: 0 every passage passed · 3 at least one failed · 2 refused
"""
import argparse, hashlib, json, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retrieval_datasets as ds  # noqa: E402
from nim_retrieval_clients import EmbeddingClient  # noqa: E402


def sample_positions(total, n):
    """n positions spread evenly over 0..total-1: the middle of each of n equal stretches."""
    n = min(n, total); step = total / n
    return sorted({int(i * step + step / 2) for i in range(n)})


def piece_of(position, pieces):
    """-> (piece record, row inside it) for a position in the corpus file."""
    for p in pieces:
        if p["first"] <= position < p["first"] + p["passages"]:
            return p, position - p["first"]
    raise SystemExit(f"refused: position {position} lies in no stored piece")


def cosines(a, b):
    a = np.asarray(a, dtype=np.float64); b = np.asarray(b, dtype=np.float64)
    return (a * b).sum(axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))


def compare(positions, ids_new, vectors_new, pieces, emb_dir, min_cosine):
    """-> (records of the passages that fail, array of cosines, number of ids equal at their position)."""
    stored = np.zeros_like(np.asarray(vectors_new, dtype=np.float32)); same_id = []
    cache = {}
    for k, (pos, pid) in enumerate(zip(positions, ids_new)):
        p, row = piece_of(pos, pieces)
        if p["piece"] not in cache:
            cache.clear()
            cache[p["piece"]] = (np.load(os.path.join(emb_dir, p["vectors_file"]), mmap_mode="r"), json.load(open(os.path.join(emb_dir, p["ids_file"]), encoding="utf-8")))
        v, ids = cache[p["piece"]]
        stored[k] = v[row]; same_id.append(ids[row] == pid)
    c = cosines(vectors_new, stored)
    bad = [{"position": int(pos), "id": pid, "id_equal_at_the_position": bool(s), "cosine": float(x)} for pos, pid, s, x in zip(positions, ids_new, same_id, c) if not s or x < min_cosine]
    return bad, c, sum(same_id)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=ds.NAMES); ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS"))
    ap.add_argument("--url", required=True); ap.add_argument("--model", required=True); ap.add_argument("--truncate", default="END"); ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--emb-dir", required=True); ap.add_argument("--checkpoints", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=1000); ap.add_argument("--min-cosine", type=float, default=0.999)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    recs = [json.loads(l) for l in open(a.checkpoints, encoding="utf-8") if l.strip()]
    fin = [r for r in recs if r.get("kind") == "finished"]; pieces = [r for r in recs if r.get("kind") == "piece"]
    if not fin:
        raise SystemExit("refused: the checkpoint file has no `finished` line (the corpus is not complete)")
    total = fin[-1]["passages"]
    if sum(p["passages"] for p in pieces) != total:
        raise SystemExit("refused: the pieces do not add up to the finished count")
    positions = sample_positions(total, a.n); want = set(positions)
    d = ds.load(a.datasets, a.dataset); ids, texts = [], []; t0 = time.perf_counter()
    for i, (pid, title, text) in enumerate(d.iter_corpus()):
        if i in want:
            ids.append(pid); texts.append(ds.passage_text(title, text))
        if i >= positions[-1]:
            break
    read_s = time.perf_counter() - t0
    if len(ids) != len(positions):
        raise SystemExit(f"refused: {len(ids)} passages read for {len(positions)} positions")
    client = EmbeddingClient(a.url, a.model, timeout=1800, keep_alive=True); t1 = time.perf_counter()
    v, _ = client.embed(texts, "passage", truncate=a.truncate, batch_size=a.batch)
    v = np.asarray(v, dtype=np.float32); enc_s = time.perf_counter() - t1
    bad, c, same = compare(positions, ids, v, pieces, a.emb_dir, a.min_cosine)
    out = {"what": "a sample of passages encoded again and compared with the stored row at each passage's position", "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "dataset": a.dataset, "model": a.model,
           "corpus_passages": total, "pieces": len(pieces), "checkpoint_file_sha256": hashlib.sha256(open(a.checkpoints, "rb").read()).hexdigest(),
           "sample": {"passages": len(positions), "rule": "the middle of each of n equal stretches of the corpus file", "first_position": positions[0], "last_position": positions[-1],
                      "pieces_touched": len({piece_of(p, pieces)[0]["piece"] for p in positions})},
           "ids_equal_at_their_position": same, "cosine": {"min": float(c.min()), "p01": float(np.percentile(c, 1)), "median": float(np.median(c)), "max": float(c.max())},
           "rule": f"the id stored at the position is the passage's id, and cosine >= {a.min_cosine}", "failed": len(bad), "failed_passages": bad[:50],
           "seconds": {"reading_the_corpus_file": round(read_s, 1), "encoding_the_sample": round(enc_s, 1)}, "program_sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
           "pass": not bad and same == len(positions)}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: out[k] for k in ("corpus_passages", "ids_equal_at_their_position", "cosine", "failed", "pass")} | {"sample": len(positions)}))
    return 0 if out["pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
