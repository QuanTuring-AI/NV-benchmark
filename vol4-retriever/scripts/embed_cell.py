#!/usr/bin/env python3
"""Vol.4 · one embedding cell: the same program for the reference arm (open weights, in this process) and for a NIM
(over HTTP), so that the encoder is the only thing that differs between two cells on the same data set.

Backends
  st    the open weights through Sentence Transformers, loaded the way the published MTEB result loaded them:
        SentenceTransformer(path, device=..., processor_kwargs={"model_max_length": 4096}); queries with
        encode_query(prompt="query: "), passages with encode_document(prompt="passage: "), the model's own pooling
        and normalisation. Nothing else is set.
  nim   POST /v1/embeddings of a running NIM: input_type "query" or "passage" and truncate on every request, the text
        sent as it is (no prefix added here: the prefix is the server's job, and whether it does it is checked by
        the subcommand `probe`).

Text of a passage: title, one space, text, stripped (retrieval_datasets.passage_text, the rule of BEIR and of MTEB).
Text of a query: the query as written.

Subcommands
  count-tokens   st only, tokenizer only (no GPU): how many passages and queries are longer than --max-tokens with
                 their prefix. Writes counts, no text.
  smoke          a small positive control before a cell: 8 queries and 56 passages; every vector must be finite, of the
                 expected size and of unit length, and a passage must be nearer to itself than to the others.
  throughput     the timed part: the first --n passages of the corpus in file order, --batch per request, one discarded
                 pass over the first 4 batches, then --reps timed passes. Reports passages per second per pass and their
                 median. This is the only figure of a cell that is a speed.
  encode         the untimed part: every query and every passage of the data set. Writes the vectors (float32 .npy) and
                 the ids outside the repository; its wall time is recorded and is not a throughput figure.
  probe          nim only, a few requests: what input_type does to a text (against the same text with the prefix
                 written out), whether a prefix written by the client is applied twice, the size of the vector, and what
                 the server does with an input longer than its limit under truncate END and NONE.

usage: embed_cell.py <subcommand> --backend st|nim --dataset NAME --datasets DIR --out FILE.json
                     [--model-path DIR] [--device cuda] [--url http://host:8000 --model NAME] [--truncate END]
                     [--batch 64] [--n 4096] [--reps 3] [--max-tokens 4096] [--emb-dir DIR] [--new-connection]
"""
import argparse, hashlib, json, math, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retrieval_datasets as ds  # noqa: E402

QUERY_PREFIX, PASSAGE_PREFIX = "query: ", "passage: "


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_texts(a, limit_corpus=None):
    """(query ids, query texts, passage ids, passage texts) in file order."""
    d = ds.load(a.datasets, a.dataset)
    if a.dataset in ds.PUBLISHED_COUNTS and limit_corpus is None:
        ds.check_published_counts(d)
    qids = sorted(d.queries); qtexts = [d.queries[q] for q in qids]
    pids, ptexts = [], []
    for pid, title, text in d.iter_corpus():
        pids.append(pid); ptexts.append(ds.passage_text(title, text))
        if limit_corpus and len(pids) >= limit_corpus:
            break
    return d, qids, qtexts, pids, ptexts


class StBackend:
    name = "st"

    def __init__(self, a):
        import sentence_transformers, torch, transformers
        from sentence_transformers import SentenceTransformer
        self.torch = torch
        self.model = SentenceTransformer(a.model_path, device=a.device, processor_kwargs={"model_max_length": a.max_tokens})
        p = next(self.model.parameters())
        self.info = {"backend": "st", "model_path_basename": os.path.basename(os.path.normpath(a.model_path)),
                     "model_safetensors_sha256": sha256_file(os.path.join(a.model_path, "model.safetensors")),
                     "versions": {"torch": torch.__version__, "sentence-transformers": sentence_transformers.__version__, "transformers": transformers.__version__, "numpy": np.__version__},
                     "device": str(p.device), "parameter_dtype": str(p.dtype), "max_seq_length": self.model.max_seq_length,
                     "tokenizer_model_max_length": self.model.tokenizer.model_max_length, "prompts": dict(self.model.prompts),
                     "similarity_fn_name": self.model.similarity_fn_name, "modules": [type(m).__name__ for m in self.model],
                     "processor_kwargs": {"model_max_length": a.max_tokens},
                     "gpu": torch.cuda.get_device_name(0) if p.device.type == "cuda" else None}
        if self.model.prompts.get("query") != QUERY_PREFIX or self.model.prompts.get("document") != PASSAGE_PREFIX:
            raise SystemExit(f"refused: the model's built-in prompts are not the ones of the published conditions: {self.model.prompts}")

    def embed(self, texts, kind, batch):
        f = self.model.encode_query if kind == "query" else self.model.encode_document
        v = f(texts, prompt=QUERY_PREFIX if kind == "query" else PASSAGE_PREFIX, batch_size=batch, convert_to_numpy=True, show_progress_bar=False)
        return np.asarray(v, dtype=np.float32), None

    def sync(self):
        if self.info["device"].startswith("cuda"):
            self.torch.cuda.synchronize()


class NimBackend:
    name = "nim"

    def __init__(self, a):
        import requests
        from nim_retrieval_clients import EmbeddingClient
        self.client = EmbeddingClient(a.url, a.model, timeout=1800, keep_alive=not a.new_connection)
        self.truncate = a.truncate
        meta = {}
        for path in ("/v1/models", "/v1/metadata", "/v1/health/ready"):
            try:
                r = requests.get(a.url.rstrip("/") + path, timeout=30)
                meta[path] = {"status": r.status_code, "body": (r.json() if "json" in r.headers.get("content-type", "") else r.text[:300])}
            except Exception as e:  # recorded, not fatal: the first embedding request decides
                meta[path] = {"error": f"{type(e).__name__}: {e}"[:200]}
        self.info = {"backend": "nim", "url": a.url, "model": a.model, "truncate": a.truncate, "connection": "new per request" if a.new_connection else "one kept connection",
                     "server": meta}

    def embed(self, texts, kind, batch):
        v, usage = self.client.embed(texts, "query" if kind == "query" else "passage", truncate=self.truncate, batch_size=batch)
        tokens = [u.get("total_tokens") for u in usage if isinstance(u, dict) and u.get("total_tokens") is not None]
        return np.asarray(v, dtype=np.float32), (sum(tokens) if tokens else None)

    def sync(self):
        pass


def backend(a):
    return StBackend(a) if a.backend == "st" else NimBackend(a)


def vector_checks(v, dim=None):
    norms = np.linalg.norm(v, axis=1)
    return {"count": int(v.shape[0]), "size": int(v.shape[1]), "all_finite": bool(np.isfinite(v).all()),
            "norm_min": float(norms.min()), "norm_max": float(norms.max()), "size_as_expected": (dim is None or int(v.shape[1]) == dim)}


def cmd_count_tokens(a):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.model_path)
    d, qids, qtexts, pids, ptexts = load_texts(a)
    out = {"what": "token counts with the prefix, tokenizer of the open weights, special tokens included", "dataset": a.dataset, "limit": a.max_tokens, "at": now()}
    for kind, prefix, texts in (("queries", QUERY_PREFIX, qtexts), ("passages", PASSAGE_PREFIX, ptexts)):
        lengths = []
        for i in range(0, len(texts), 2000):
            enc = tok([prefix + t for t in texts[i:i + 2000]], add_special_tokens=True, truncation=False)
            lengths.extend(len(x) for x in enc["input_ids"])
        lengths = np.asarray(lengths)
        out[kind] = {"count": int(len(lengths)), "longer_than_limit": int((lengths > a.max_tokens).sum()), "max": int(lengths.max()),
                     "p50": int(np.percentile(lengths, 50)), "p99": int(np.percentile(lengths, 99)), "total": int(lengths.sum()),
                     "longer_than_512": int((lengths > 512).sum()), "longer_than_2048": int((lengths > 2048).sum()), "longer_than_8192": int((lengths > 8192).sum())}
    return out


def cmd_smoke(a):
    b = backend(a)
    d, qids, qtexts, pids, ptexts = load_texts(a, limit_corpus=56)
    q, _ = b.embed(qtexts[:8], "query", 8); p, _ = b.embed(ptexts, "passage", 8)
    p2, _ = b.embed(ptexts[:8], "passage", 4)                      # the same passages again, another batch size
    self_sim = (p[:8] / np.linalg.norm(p[:8], axis=1, keepdims=True)) @ (p2 / np.linalg.norm(p2, axis=1, keepdims=True)).T
    checks = {"queries": vector_checks(q, a.dim), "passages": vector_checks(p, a.dim),
              "same_passage_other_batch_size_cosine_min": float(np.diag(self_sim).min()),
              "nearest_is_itself": int((self_sim.argmax(axis=1) == np.arange(8)).sum()), "of": 8}
    ok = (checks["queries"]["all_finite"] and checks["passages"]["all_finite"] and checks["queries"]["size_as_expected"] and checks["passages"]["size_as_expected"]
          and abs(checks["passages"]["norm_min"] - 1) < 1e-2 and abs(checks["passages"]["norm_max"] - 1) < 1e-2
          and checks["nearest_is_itself"] == 8 and checks["same_passage_other_batch_size_cosine_min"] > 0.99)
    return {"at": now(), "dataset": a.dataset, "encoder": b.info, "checks": checks, "pass": bool(ok)}


def cmd_throughput(a):
    b = backend(a)
    d, qids, qtexts, pids, ptexts = load_texts(a, limit_corpus=a.n)
    if len(ptexts) < a.n:
        raise SystemExit(f"refused: the corpus has {len(ptexts)} passages, fewer than --n {a.n}")
    chars = sum(len(t) for t in ptexts)
    b.embed(ptexts[: 4 * a.batch], "passage", a.batch); b.sync()                 # discarded
    passes = []
    for r in range(a.reps):
        start = now(); t = time.perf_counter()
        v, tokens = b.embed(ptexts, "passage", a.batch); b.sync()
        s = time.perf_counter() - t
        passes.append({"start": start, "end": now(), "seconds": round(s, 3), "passages_per_s": round(len(ptexts) / s, 1), "tokens_reported": tokens,
                       "tokens_per_s": (round(tokens / s, 1) if tokens else None), "vectors": vector_checks(v, a.dim)})
    rates = sorted(p["passages_per_s"] for p in passes)
    out = {"what": "timed passes over a fixed sample of the corpus", "at": now(), "dataset": a.dataset, "encoder": b.info, "sample": {"passages": len(ptexts), "selection": "the first passages of the corpus in file order", "characters": chars},
           "batch": a.batch, "reps": a.reps, "discarded": "one pass over the first 4 batches", "passes": passes,
           "passages_per_s_median": rates[len(rates) // 2], "passages_per_s_min": rates[0], "passages_per_s_max": rates[-1]}
    if a.backend == "nim":
        out["per_request_seconds"] = {"count": len(b.client.calls), "p50": round(float(np.percentile([c["seconds"] for c in b.client.calls], 50)), 4),
                                      "p99": round(float(np.percentile([c["seconds"] for c in b.client.calls], 99)), 4)}
    return out


def cmd_encode(a):
    b = backend(a)
    d, qids, qtexts, pids, ptexts = load_texts(a)
    os.makedirs(a.emb_dir, exist_ok=True)
    for name in ("queries.npy", "corpus.npy"):
        if os.path.exists(os.path.join(a.emb_dir, name)):
            raise SystemExit(f"refused: {os.path.join(a.emb_dir, name)} exists")
    start = now(); t = time.perf_counter()
    q, qtok = b.embed(qtexts, "query", a.batch); b.sync(); tq = time.perf_counter() - t
    t = time.perf_counter()
    parts, ptok = [], 0
    for i in range(0, len(ptexts), 8192):                              # in pieces, so that a failure late in a large corpus is seen early
        v, tok = b.embed(ptexts[i:i + 8192], "passage", a.batch); parts.append(v); ptok += tok or 0
        print(f"  {a.dataset}: {min(i + 8192, len(ptexts))} of {len(ptexts)} passages, {time.perf_counter() - t:.0f} s", flush=True)
    b.sync(); tp = time.perf_counter() - t
    p = np.concatenate(parts, axis=0)
    np.save(os.path.join(a.emb_dir, "queries.npy"), q); np.save(os.path.join(a.emb_dir, "corpus.npy"), p)
    json.dump({"query_ids": qids, "passage_ids": pids}, open(os.path.join(a.emb_dir, "ids.json"), "w", encoding="utf-8"))
    return {"what": "every query and passage of the data set encoded; wall times are recorded and are not throughput figures", "start": start, "end": now(),
            "dataset": a.dataset, "split": d.split, "encoder": b.info, "batch": a.batch, "queries": vector_checks(q, a.dim), "passages": vector_checks(p, a.dim),
            "seconds": {"queries": round(tq, 1), "passages": round(tp, 1)}, "tokens_reported": {"queries": qtok, "passages": ptok or None},
            "vectors": {"folder": os.path.basename(os.path.normpath(a.emb_dir)), "queries_sha256": sha256_file(os.path.join(a.emb_dir, "queries.npy")),
                        "corpus_sha256": sha256_file(os.path.join(a.emb_dir, "corpus.npy")), "ids_sha256": sha256_file(os.path.join(a.emb_dir, "ids.json"))}}


def cmd_probe(a):
    """What the server does with input_type, with a prefix the client writes itself, and with an over-long input."""
    import requests
    from nim_retrieval_clients import embedding_request
    url = a.url.rstrip("/") + "/v1/embeddings"

    def post(texts, input_type, truncate, **extra):
        body = embedding_request(a.model, texts, input_type, truncate, **extra)
        r = requests.post(url, json=body, timeout=600)
        if r.status_code != 200:
            return None, {"status": r.status_code, "body": r.text[:400]}
        d = r.json(); rows = sorted(d["data"], key=lambda e: e["index"])
        return np.asarray([e["embedding"] for e in rows], dtype=np.float32), {"status": 200, "usage": d.get("usage"), "model": d.get("model")}

    def cos(x, y):
        return float((x @ y) / (np.linalg.norm(x) * np.linalg.norm(y)))

    d, qids, qtexts, pids, ptexts = load_texts(a, limit_corpus=16)
    out = {"at": now(), "dataset": a.dataset, "url": a.url, "model": a.model, "texts": {"queries": 8, "passages": 8}, "cases": {}}
    q_plain, m1 = post(qtexts[:8], "query", "END"); p_plain, m2 = post(ptexts[:8], "passage", "END")
    out["cases"]["plain"] = {"query": m1, "passage": m2, "size": (int(q_plain.shape[1]) if q_plain is not None else None),
                             "norm_min_max": ([float(np.linalg.norm(q_plain, axis=1).min()), float(np.linalg.norm(q_plain, axis=1).max())] if q_plain is not None else None)}
    if q_plain is None or p_plain is None:
        return out
    # the same text with the other input_type: if input_type did nothing, the two vectors would be equal
    q_as_p, _ = post(qtexts[:8], "passage", "END")
    out["cases"]["query_text_sent_as_passage"] = {"cosine_with_query_mode": [round(cos(q_plain[i], q_as_p[i]), 6) for i in range(8)]}
    # the prefix written by the client as well: equal to plain -> the server ignores or strips it; different -> it is applied on top
    q_pref, _ = post([QUERY_PREFIX + t for t in qtexts[:8]], "query", "END"); p_pref, _ = post([PASSAGE_PREFIX + t for t in ptexts[:8]], "passage", "END")
    out["cases"]["client_prefix_plus_input_type"] = {"query_cosine_with_plain": [round(cos(q_plain[i], q_pref[i]), 6) for i in range(8)],
                                                     "passage_cosine_with_plain": [round(cos(p_plain[i], p_pref[i]), 6) for i in range(8)]}
    if a.reference_dir:                                               # vectors of the same eight texts from the reference arm
        ref = json.load(open(os.path.join(a.reference_dir, "ids.json"), encoding="utf-8"))
        rq = np.load(os.path.join(a.reference_dir, "queries.npy"), mmap_mode="r"); rp = np.load(os.path.join(a.reference_dir, "corpus.npy"), mmap_mode="r")
        qi = [ref["query_ids"].index(x) for x in qids[:8]]; pi = [ref["passage_ids"].index(x) for x in pids[:8]]
        out["cases"]["against_the_reference_arm"] = {
            "query_mode_vs_reference_query": [round(cos(q_plain[i], np.asarray(rq[qi[i]])), 6) for i in range(8)],
            "passage_mode_vs_reference_passage": [round(cos(p_plain[i], np.asarray(rp[pi[i]])), 6) for i in range(8)],
            "client_prefixed_query_vs_reference_query": [round(cos(q_pref[i], np.asarray(rq[qi[i]])), 6) for i in range(8)],
            "query_text_sent_as_passage_vs_reference_query": [round(cos(q_as_p[i], np.asarray(rq[qi[i]])), 6) for i in range(8)]}
    # an over-long input: a passage repeated until it is far past any documented limit
    long_text = (ptexts[0] + " ") * (1 + 200000 // max(1, len(ptexts[0])))
    v_end, m_end = post([long_text], "passage", "END"); v_none, m_none = post([long_text], "passage", "NONE")
    out["cases"]["over_long_input"] = {"characters": len(long_text), "truncate_END": m_end, "truncate_NONE": m_none}
    for dim in (1024,):
        v_dim, m_dim = post(qtexts[:2], "query", "END", dimensions=dim)
        out["cases"][f"dimensions_{dim}"] = {"answer": m_dim, "size": (int(v_dim.shape[1]) if v_dim is not None else None)}
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["count-tokens", "smoke", "throughput", "encode", "probe"])
    ap.add_argument("--backend", choices=["st", "nim"], required=True); ap.add_argument("--dataset", required=True, choices=ds.NAMES)
    ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS")); ap.add_argument("--out", required=True)
    ap.add_argument("--model-path"); ap.add_argument("--device", default="cuda"); ap.add_argument("--url"); ap.add_argument("--model")
    ap.add_argument("--truncate", default="END"); ap.add_argument("--batch", type=int, default=64); ap.add_argument("--n", type=int, default=4096)
    ap.add_argument("--reps", type=int, default=3); ap.add_argument("--max-tokens", type=int, default=4096); ap.add_argument("--dim", type=int, default=None)
    ap.add_argument("--emb-dir"); ap.add_argument("--reference-dir"); ap.add_argument("--new-connection", action="store_true")
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    if a.backend == "st" and not a.model_path:
        raise SystemExit("--model-path is needed for the st backend")
    if a.backend == "nim" and not (a.url and a.model) and a.cmd != "count-tokens":
        raise SystemExit("--url and --model are needed for the nim backend")
    out = {"count-tokens": cmd_count_tokens, "smoke": cmd_smoke, "throughput": cmd_throughput, "encode": cmd_encode, "probe": cmd_probe}[a.cmd](a)
    argv, paths = [], ("--datasets", "--model-path", "--emb-dir", "--reference-dir", "--out")
    for i, x in enumerate(sys.argv[1:]):                              # folders are recorded by their last part only
        argv.append(os.path.basename(os.path.normpath(x)) if i and sys.argv[i] in paths else x)
    out["program"] = {"file": "embed_cell.py", "sha256": sha256_file(os.path.abspath(__file__)), "argv": argv}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({k: out[k] for k in out if k in ("pass", "passages_per_s_median", "seconds", "queries", "passages")}, ensure_ascii=False)[:600])
    return 0 if out.get("pass", True) else 3


if __name__ == "__main__":
    sys.exit(main())
