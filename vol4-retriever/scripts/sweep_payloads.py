#!/usr/bin/env python3
"""Vol.4 · the request bodies of the concurrency sweep, written once per NIM before anything is timed.

Four files, each a list of complete request bodies in the form the load tool replays verbatim (AIPerf `inputs-json`:
{"data": [{"session_id": ..., "payloads": [body]}]}). The bodies are built by this volume's own request builders
(nim_retrieval_clients.py), so the load tool sends what the volume's clients send.

  embeddings, query shape     one query per request (input_type "query"): every query of the reduced MIRACL zh task
  embeddings, passage shape   64 passages per request (input_type "passage"): the first 4,096 passages of the reduced
                              MIRACL zh corpus, in file order: the sample of every timed embedding cell of this volume
  ranking, 100 passages       one query and the first 100 passages of its first-stage ranking (the whole-corpus run of
  ranking, 10 passages        MIRACL zh), or the first 10; a passage is title, one space, text, as in rerank_cell.py
`truncate` is END on every request, as in the cells these shapes are compared with.

The files hold text of the public data sets and stay outside the repository; what is written beside the results is a
record without text: counts, characters per request, and the SHA-256 of each file.

usage: sweep_payloads.py embeddings --model NAME --datasets DIR --out-dir DIR --record FILE.json
       sweep_payloads.py ranking --model NAME --datasets DIR --run-in FILE.trec --out-dir DIR --record FILE.json
"""
import argparse, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BATCH, SAMPLE = 64, 4096


def write(path, bodies):
    data = {"data": [{"session_id": f"s{i:05d}", "payloads": [b]} for i, b in enumerate(bodies)]}
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    open(path, "wb").write(raw)
    return hashlib.sha256(raw).hexdigest()


def stats(values):
    v = sorted(values)
    return {"min": v[0], "median": v[len(v) // 2], "max": v[-1], "mean": round(sum(v) / len(v), 1)}


def main():
    import retrieval_datasets as ds
    from nim_retrieval_clients import embedding_request, ranking_request
    ap = argparse.ArgumentParser(); ap.add_argument("kind", choices=("embeddings", "ranking")); ap.add_argument("--model", required=True)
    ap.add_argument("--datasets", required=True); ap.add_argument("--out-dir", required=True); ap.add_argument("--record", required=True); ap.add_argument("--run-in")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True); rec = {"model": a.model, "truncate": "END", "format": "AIPerf inputs-json, one body per session", "files": {}}
    if a.kind == "embeddings":
        d = ds.load(a.datasets, "miracl-hn-zh")
        queries = [d.queries[q] for q in sorted(d.queries)]
        passages = []
        for _pid, title, text in d.iter_corpus():
            passages.append(ds.passage_text(title, text))
            if len(passages) >= SAMPLE:
                break
        if len(passages) < SAMPLE:
            raise SystemExit("refused: the corpus is shorter than the sample")
        qb = [embedding_request(a.model, [q], "query", "END") for q in queries]
        pb = [embedding_request(a.model, passages[i:i + BATCH], "passage", "END") for i in range(0, SAMPLE, BATCH)]
        rec["files"]["query"] = {"file": "emb_query.inputs.json", "requests": len(qb), "items_per_request": 1, "endpoint": "/v1/embeddings", "input_type": "query", "data_set": "miracl-hn-zh, every query",
                                 "characters_per_request": stats([len(q) for q in queries]), "sha256": write(os.path.join(a.out_dir, "emb_query.inputs.json"), qb)}
        rec["files"]["passage"] = {"file": "emb_passage.inputs.json", "requests": len(pb), "items_per_request": BATCH, "endpoint": "/v1/embeddings", "input_type": "passage",
                                   "data_set": f"miracl-hn-zh, the first {SAMPLE} passages in file order", "characters_per_request": stats([sum(len(t) for t in passages[i:i + BATCH]) for i in range(0, SAMPLE, BATCH)]),
                                   "sha256": write(os.path.join(a.out_dir, "emb_passage.inputs.json"), pb)}
    else:
        import rerank_cell as rc
        d = ds.load(a.datasets, "miracl-zh"); first = rc.read_run(a.run_in)
        qids = sorted(q for q in first if q in d.queries)
        need = {p for q in qids for p in first[q][:100]}
        text = {pid: ds.passage_text(title, body) for pid, title, body in d.iter_corpus() if pid in need}
        if need - set(text):
            raise SystemExit(f"refused: {len(need - set(text))} passages of the run file are not in the corpus")
        for depth in (100, 10):
            bodies = [ranking_request(a.model, d.queries[q], [text[p] for p in first[q][:depth]], "END") for q in qids]
            name = f"rank_{depth}.inputs.json"
            rec["files"][f"passages_{depth}"] = {"file": name, "requests": len(bodies), "items_per_request": depth, "endpoint": "/v1/ranking", "data_set": "miracl-zh, every dev query with the first passages of its first-stage ranking",
                                                 "first_stage_run_sha256": hashlib.sha256(open(a.run_in, "rb").read()).hexdigest(),
                                                 "characters_per_request": stats([len(d.queries[q]) + sum(len(text[p]) for p in first[q][:depth]) for q in qids]),
                                                 "sha256": write(os.path.join(a.out_dir, name), bodies)}
    rec["program"] = {"file": "sweep_payloads.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}
    os.makedirs(os.path.dirname(a.record), exist_ok=True)
    json.dump(rec, open(a.record, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({k: {x: v[x] for x in ("requests", "items_per_request", "sha256")} for k, v in rec["files"].items()}))


if __name__ == "__main__":
    main()
