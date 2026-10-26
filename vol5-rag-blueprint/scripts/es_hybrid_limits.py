#!/usr/bin/env python3
"""Vol.5 · what the Elasticsearch the Blueprint ships (vectordb.yaml: basic licence) accepts of the Blueprint's two
hybrid searches, asked directly on the HotpotQA index:

  rrf        the default ranker (APP_VECTORSTORE_RANKER_TYPE rrf): the ES client's DenseVectorStrategy(hybrid=True)
             sends rank: {rrf: {}}; the newer retriever form is asked too
  weighted   es_queries.py:239-275 of the Blueprint: knn with num_candidates fixed at 100 and k = vdb_top_k, plus a
             match on "text"; asked at k = 100, 200 and 400
  controls   the same index answers a plain kNN and a plain match (so a refusal above is about the feature, not the
             index or the connection)

The query vector is a fixed unit vector (every component 1/sqrt(2048)) and the text a fixed word; only the request's
shape, the HTTP status and Elasticsearch's own error text are written, never a passage.
usage: es_hybrid_limits.py --es URL --index NAME --out FILE
"""
import argparse, json, math, time, urllib.error, urllib.request


def ask(es, path, body=None):
    req = urllib.request.Request(es + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    ap = argparse.ArgumentParser()
    for x in ("--es", "--index", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    dims = 2048; v = [1 / math.sqrt(dims)] * dims
    knn = lambda k, nc, **kw: {"field": "vector", "query_vector": "<fixed unit vector>", "k": k, "num_candidates": nc, **kw}
    shapes = [
     ("rrf, top-level rank (what the client sends)", {"knn": knn(100, 100), "query": {"match": {"text": "probe"}}, "rank": {"rrf": {}}, "size": 100}),
     ("rrf, retriever form", {"retriever": {"rrf": {"retrievers": [{"standard": {"query": {"match": {"text": "probe"}}}}, {"knn": knn(100, 100)}]}}, "size": 100}),
     ("weighted, vdb_top_k 100", {"knn": knn(100, 100, boost=0.5), "query": {"match": {"text": {"query": "probe", "boost": 0.5}}}, "size": 100}),
     ("weighted, vdb_top_k 200", {"knn": knn(200, 100, boost=0.5), "query": {"match": {"text": {"query": "probe", "boost": 0.5}}}, "size": 200}),
     ("weighted, vdb_top_k 400", {"knn": knn(400, 100, boost=0.5), "query": {"match": {"text": {"query": "probe", "boost": 0.5}}}, "size": 400}),
     ("control: kNN alone", {"knn": knn(100, 100), "size": 100}),
     ("control: match alone", {"query": {"match": {"text": "probe"}}, "size": 100})]
    st, lic = ask(a.es, "/_license")
    out = {"what": "the Blueprint's hybrid searches against the Elasticsearch it ships (scripts/es_hybrid_limits.py)",
           "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "index": a.index,
           "licence": {"status": st, "type": (lic.get("license") or {}).get("type")},
           "version": ask(a.es, "/")[1].get("version", {}).get("number"), "asked": []}
    for name, shape in shapes:
        body = json.loads(json.dumps(shape).replace('"<fixed unit vector>"', json.dumps(v)))
        body["_source"] = False
        status, r = ask(a.es, f"/{a.index}/_search", body)
        err = r.get("error") or {}
        out["asked"].append({"name": name, "request_shape": shape, "status": status,
                             "hits": len(r["hits"]["hits"]) if status == 200 else None,
                             "error_type": err.get("type"), "error_reason": err.get("reason")})
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps([(x["name"], x["status"], x["error_reason"]) for x in out["asked"]], indent=1))


if __name__ == "__main__":
    main()
