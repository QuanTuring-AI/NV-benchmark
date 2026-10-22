#!/usr/bin/env python3
"""Vol.5 · co-residence cell: after the last service of the Blueprint's set is up on the one card, send one real request
to each service, in the order a question takes through the Blueprint (embed the question, search the vector database,
rerank what it found, answer with the model). Nothing is timed. A service that is not up is recorded as such and the
chain goes on with what it can.

The vector database gets a collection of SciFact's size (5,183 passages) with the schema and the dense-index settings of
the Blueprint's ingestion client (primary key INT64 auto_id, FLOAT_VECTOR, HNSW M 64 efConstruction 512, metric L2,
search ef 100). The passages are embedded by the Blueprint's embedder when it is up; when it is not, the collection is
filled with seeded random unit vectors of the same width, and the record says so.

The model's answer text is not written to the results: only its length, its SHA-256, the finish reason and the token
counts. With --text-out the text goes to a separate file (kept out of the repository).

usage: coresidence_requests.py --scifact DIR --out FILE [--text-out FILE]
       [--embed URL] [--rank URL] [--llm URL] [--milvus URI]
"""
import argparse, hashlib, json, os, sys, time, urllib.error, urllib.request

import numpy as np

DIM = 2048
COLLECTION = "v5_coresidence_scifact"
INDEX = {"index_type": "HNSW", "metric_type": "L2", "params": {"M": 64, "efConstruction": 512}}
SEARCH = {"metric_type": "L2", "params": {"ef": 100}}


def call(url, body=None, timeout=600):
    """GET (body None) or POST JSON; returns (status, parsed body or text)."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:600]
    except Exception as e:  # connection refused, timeout
        return None, f"{type(e).__name__}: {e}"[:600]
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw[:600]


def model_of(base):
    s, d = call(base + "/v1/models", timeout=20)
    if s == 200 and isinstance(d, dict) and d.get("data"):
        return d["data"][0]["id"]
    return None


def unit(x):
    x = np.asarray(x, np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def read_jsonl(path, n=None):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            out.append(json.loads(line))
            if n and len(out) >= n:
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scifact", required=True); ap.add_argument("--out", required=True); ap.add_argument("--text-out")
    ap.add_argument("--embed", default="http://p133_embed:8000"); ap.add_argument("--rank", default="http://p133_rank:8000")
    ap.add_argument("--llm", default="http://p133_llm:8000"); ap.add_argument("--milvus", default="http://milvus:19530")
    a = ap.parse_args()
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "timed": False, "steps": {}}
    corpus = read_jsonl(os.path.join(a.scifact, "corpus.jsonl")); query = read_jsonl(os.path.join(a.scifact, "queries.jsonl"), 1)[0]
    texts = [((d.get("title") or "") + " " + d["text"]).strip() for d in corpus]
    rec["question"] = {"source": "SciFact queries.jsonl, first line", "id": query["_id"]}

    # 1 · the embedder: the question, then the passages for the collection
    st = {}; qv = None; pv = None
    em = model_of(a.embed); st["model"] = em
    if em:
        s, d = call(a.embed + "/v1/embeddings", {"input": [query["text"]], "model": em, "input_type": "query", "truncate": "END"})
        st["question_status"] = s
        if s == 200:
            qv = unit([d["data"][0]["embedding"]]); st["question_vector_width"] = int(qv.shape[1])
            vecs, bad = [], 0
            for i in range(0, len(texts), 64):
                s2, d2 = call(a.embed + "/v1/embeddings", {"input": texts[i:i + 64], "model": em, "input_type": "passage", "truncate": "END"})
                if s2 != 200:
                    bad += 1; st["passage_error"] = str(d2)[:300]; break
                vecs += [e["embedding"] for e in d2["data"]]
            st["passages_embedded"] = len(vecs); st["passage_calls_failed"] = bad
            if len(vecs) == len(texts):
                pv = unit(vecs)
        else:
            st["question_error"] = str(d)[:300]
    else:
        st["up"] = False
    rec["steps"]["embedder"] = st

    # 2 · the vector database
    st = {"collection": COLLECTION, "rows": len(texts), "index": INDEX, "search": SEARCH}
    hits = None
    try:
        from pymilvus import MilvusClient, DataType
        c = MilvusClient(uri=a.milvus, timeout=120)
        if c.has_collection(COLLECTION):
            c.drop_collection(COLLECTION)
        if pv is None:
            rng = np.random.default_rng(0); pv = unit(rng.normal(size=(len(texts), DIM))); qv = unit(rng.normal(size=(1, DIM)))
            st["vectors"] = "seeded random unit vectors (the embedder was not up)"
        else:
            st["vectors"] = "the passages as the embedder returned them, divided by their length"
        schema = c.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field("pk", DataType.INT64, is_primary=True); schema.add_field("vector", DataType.FLOAT_VECTOR, dim=int(pv.shape[1]))
        schema.add_field("row", DataType.INT64)
        c.create_collection(COLLECTION, schema=schema)
        for i in range(0, len(pv), 1000):
            c.insert(COLLECTION, [{"vector": pv[j].tolist(), "row": j} for j in range(i, min(i + 1000, len(pv)))])
        c.flush(COLLECTION)
        ip = c.prepare_index_params(); ip.add_index(field_name="vector", index_name="dense", **INDEX); c.create_index(COLLECTION, ip)
        c.load_collection(COLLECTION)
        res = c.search(COLLECTION, data=[qv[0].tolist()], anns_field="vector", limit=10, search_params=SEARCH, output_fields=["row"])
        hits = [h["entity"]["row"] for h in res[0]]
        st["search_ok"] = len(hits) == 10; st["rows_found"] = hits
        c.drop_collection(COLLECTION); st["collection_dropped"] = True
    except Exception as e:
        st["error"] = f"{type(e).__name__}: {e}"[:600]
    rec["steps"]["vector_database"] = st

    # 3 · the reranker over what the search found (or the first ten passages)
    st = {}; order = hits if hits else list(range(10)); st["passages_from"] = "the search" if hits else "the first ten passages (no search result)"
    rm = model_of(a.rank); st["model"] = rm
    if rm:
        s, d = call(a.rank + "/v1/ranking", {"model": rm, "query": {"text": query["text"]}, "passages": [{"text": texts[i]} for i in order], "truncate": "END"})
        st["status"] = s
        if s == 200:
            rk = d["rankings"]; st["ranked"] = len(rk); st["every_passage_once"] = sorted(r["index"] for r in rk) == list(range(len(order)))
            order = [order[r["index"]] for r in rk]
        else:
            st["error"] = str(d)[:300]
    else:
        st["up"] = False
    rec["steps"]["reranker"] = st

    # 4 · the model, with the first four passages as context
    st = {}; lm = model_of(a.llm); st["model"] = lm
    if lm:
        ctx = "\n\n".join(texts[i][:1500] for i in order[:4])
        body = {"model": lm, "max_tokens": 1024, "temperature": 0,
                "messages": [{"role": "system", "content": "Answer the question from the passages. Say if they do not answer it."},
                             {"role": "user", "content": f"Passages:\n{ctx}\n\nQuestion: {query['text']}"}]}
        s, d = call(a.llm + "/v1/chat/completions", body, timeout=900)
        st["status"] = s
        if s == 200:
            ch = d["choices"][0]; text = ch["message"].get("content") or ""
            st.update(finish_reason=ch.get("finish_reason"), usage=d.get("usage"), answer_characters=len(text), answer_sha256=hashlib.sha256(text.encode()).hexdigest(),
                      reasoning_characters=len(ch["message"].get("reasoning_content") or ""))
            if a.text_out:
                os.makedirs(os.path.dirname(a.text_out), exist_ok=True)
                open(a.text_out, "w", encoding="utf-8", newline="\n").write(json.dumps({"answer": text, "reasoning": ch["message"].get("reasoning_content")}, ensure_ascii=False))
        else:
            st["error"] = str(d)[:300]
    else:
        st["up"] = False
    rec["steps"]["model"] = st

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: {kk: v.get(kk) for kk in ("model", "status", "search_ok", "error", "up", "passages_embedded")} for k, v in rec["steps"].items()}))


if __name__ == "__main__":
    sys.exit(main())
