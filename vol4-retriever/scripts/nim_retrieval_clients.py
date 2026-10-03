#!/usr/bin/env python3
"""Requests to the NeMo Retriever embedding and reranking NIMs, built from the OpenAPI files NVIDIA publishes with the
documentation (SOURCES.md lists the files, their versions and their SHA-256). Nothing here was written from memory, and
nothing here has met a real server yet: the request and response shapes are checked against a stand-in server only
(mock_nim_server.py). The first start of a real NIM on a GPU is what settles the format.

Embedding, POST /v1/embeddings (schema `EmbeddingRequest`, documentation versions 1.13.0 and 2.2/2.3):
  required  input        one string or a list of strings, at most 8,192 items, none empty
            model        string
  optional  input_type   "query" | "passage"   (the documentation: models with a query mode and a passage mode need it,
                                                 and the wrong value costs a large part of the retrieval accuracy)
            truncate     "NONE" (default) | "END" | "START"   what the server does with an input longer than the model takes;
                                                               with NONE it answers with an error
            encoding_format, embedding_type, dimensions, modality, user   not set by this harness unless asked
  response  data[]: {index, embedding} · model · usage. The harness puts the vectors back in input order by `index`.

Reranking, POST /v1/ranking (schema `RankRequest`, documentation versions 1.10.0 and 2.3):
  required  model        string
            query        {"text": string}
            passages     list of {"text": string}, 1 to 512 items
  optional  truncate     "NONE" (default) | "END"
  response  rankings[]: {index, logit}, the passages' positions in the request with their scores · usage.

What the harness adds, and only this: batching of the embedding inputs (batch size is a harness setting, recorded per
run), a new connection per request or a kept one (recorded), and the per-request duration.
"""
import time

import requests

INPUT_TYPES = ("query", "passage")
TRUNCATE_EMBEDDING = ("NONE", "END", "START")
TRUNCATE_RANKING = ("NONE", "END")
MAX_EMBEDDING_INPUTS = 8192
MAX_PASSAGES = 512


def embedding_request(model, texts, input_type, truncate="NONE", **extra):
    """The JSON body of one /v1/embeddings request. `texts` is a list of non-empty strings."""
    if input_type not in INPUT_TYPES:
        raise ValueError(f"input_type must be one of {INPUT_TYPES}, got {input_type!r}")
    if truncate not in TRUNCATE_EMBEDDING:
        raise ValueError(f"truncate must be one of {TRUNCATE_EMBEDDING}, got {truncate!r}")
    if not isinstance(texts, (list, tuple)) or not 1 <= len(texts) <= MAX_EMBEDDING_INPUTS:
        raise ValueError(f"texts must be a list of 1 to {MAX_EMBEDDING_INPUTS} strings")
    if any(not isinstance(t, str) or not t for t in texts):
        raise ValueError("every input must be a non-empty string")
    body = {"input": list(texts), "model": model, "input_type": input_type, "truncate": truncate}
    unknown = set(extra) - {"encoding_format", "embedding_type", "dimensions", "modality", "user"}
    if unknown:
        raise ValueError(f"fields that are not in the published schema: {sorted(unknown)}")
    body.update(extra)
    return body


def ranking_request(model, query, passages, truncate="NONE"):
    """The JSON body of one /v1/ranking request."""
    if truncate not in TRUNCATE_RANKING:
        raise ValueError(f"truncate must be one of {TRUNCATE_RANKING}, got {truncate!r}")
    if not isinstance(query, str) or not query:
        raise ValueError("the query must be a non-empty string")
    if not isinstance(passages, (list, tuple)) or not 1 <= len(passages) <= MAX_PASSAGES:
        raise ValueError(f"passages must be a list of 1 to {MAX_PASSAGES} strings (the documented limit of one call)")
    if any(not isinstance(p, str) or not p for p in passages):
        raise ValueError("every passage must be a non-empty string")
    return {"model": model, "query": {"text": query}, "passages": [{"text": p} for p in passages], "truncate": truncate}


class NimError(RuntimeError):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:300]}"); self.status, self.body = status, body


class _Client:
    def __init__(self, base_url, model, timeout=600, keep_alive=True):
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout
        self.session = requests.Session() if keep_alive else None
        self.keep_alive = keep_alive
        self.calls = []   # one record per request: seconds, items, HTTP status

    def _post(self, path, body, items):
        t = time.perf_counter()
        r = (self.session or requests).post(self.base_url + path, json=body, timeout=self.timeout)
        self.calls.append({"path": path, "items": items, "seconds": time.perf_counter() - t, "status": r.status_code})
        if r.status_code != 200:
            raise NimError(r.status_code, r.text)
        return r.json()


class EmbeddingClient(_Client):
    def embed(self, texts, input_type, truncate="NONE", batch_size=64, **extra):
        """Vectors for `texts`, in the order of `texts`. One request per batch of `batch_size` inputs."""
        if batch_size < 1 or batch_size > MAX_EMBEDDING_INPUTS:
            raise ValueError(f"batch_size must be between 1 and {MAX_EMBEDDING_INPUTS}")
        out, usage = [], []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            d = self._post("/v1/embeddings", embedding_request(self.model, batch, input_type, truncate, **extra), len(batch))
            rows = sorted(d["data"], key=lambda e: e["index"])
            if [e["index"] for e in rows] != list(range(len(batch))):
                raise NimError(200, f"the answer does not carry one vector per input: indexes {[e['index'] for e in rows][:8]} for {len(batch)} inputs")
            out.extend(e["embedding"] for e in rows); usage.append(d.get("usage"))
        return out, usage


class RerankClient(_Client):
    def rerank(self, query, passages, truncate="NONE"):
        """Scores for `passages`, in the order of `passages`: a list of logits. One call takes at most 512 passages; a
        longer list is refused here instead of being split, because whether scores from separate calls may be put on one
        scale is a property of the server that has not been checked."""
        d = self._post("/v1/ranking", ranking_request(self.model, query, passages, truncate), len(passages))
        ranks = d["rankings"]
        if sorted(r["index"] for r in ranks) != list(range(len(passages))):
            raise NimError(200, f"the answer does not rank every passage exactly once: {len(ranks)} rankings for {len(passages)} passages")
        logits = [None] * len(passages)
        for r in ranks:
            logits[r["index"]] = r["logit"]
        return logits, d.get("usage")
