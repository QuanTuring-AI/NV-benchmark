#!/usr/bin/env python3
"""Vol.5 · the Blueprint's own ingestion of a slice of a corpus, for two uses of the design:
  - control (b): the slice indexed by the Blueprint's ingestor is compared with the same slice bulk-loaded by
    es_bulk_load.py (top 100 of 100 questions, overlap at least 0.99);
  - the mapping: the index the ingestor creates is read back (`GET /<index>`: settings and mappings) together with the
    `metadata` of one of its documents; es_bulk_load.py creates its indexes from these.

  stage    writes the first --n passages of a corpus as text files <passage id>.txt (Vol.4's passage text: title, one
           space, text) into --staged-dir, outside the repository
  ingest   creates the collection, uploads the staged files in batches of --batch per request (non-blocking), polls
           each task to its end; one record line per batch (status codes, seconds, task state, counts)
  capture  reads the index back from Elasticsearch: settings, mappings, the document count, and one document's
           metadata; writes them to --out (the mapping file of es_bulk_load.py is written from it)

usage: ingest_slice_via_blueprint.py stage --dataset NAME --datasets-root DIR --n 100000 --staged-dir DIR
       ingest_slice_via_blueprint.py ingest --staged-dir DIR --collection NAME --record FILE [--batch 500]
                                     [--ingestor URL] [--vdb-endpoint URL]
       ingest_slice_via_blueprint.py capture --es URL --index NAME --out FILE
"""
import argparse, glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(V5), "vol4-retriever", "scripts"))


def stage(a):
    import retrieval_datasets as R
    os.makedirs(a.staged_dir, exist_ok=True); n = 0
    for pid, title, text in R.load(a.datasets_root, a.dataset).iter_corpus():
        if n >= a.n:
            break
        open(os.path.join(a.staged_dir, f"{pid}.txt"), "w", encoding="utf-8", newline="\n").write(R.passage_text(title, text))
        n += 1
    print(json.dumps({"staged": n, "dir": a.staged_dir}))


def ingest(a):
    import requests
    files = sorted(glob.glob(os.path.join(a.staged_dir, "*.txt")))
    r = requests.post(a.ingestor + "/v1/collection", json={"vdb_endpoint": a.vdb_endpoint, "collection_name": a.collection}, timeout=120)
    log = open(a.record, "a", encoding="utf-8", newline="\n")
    log.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "step": "create collection", "status": r.status_code, "body": r.text[:300]}) + "\n")
    for b in range(0, len(files), a.batch):
        part = files[b:b + a.batch]; t0 = time.time()
        handles = [("documents", (os.path.basename(p), open(p, "rb"), "text/plain")) for p in part]
        data = {"data": json.dumps({"vdb_endpoint": a.vdb_endpoint, "collection_name": a.collection, "blocking": False, "generate_summary": False})}
        r = requests.post(a.ingestor + "/v1/documents", files=handles, data=data, timeout=1800)
        for _, (_, fh, _) in handles:
            fh.close()
        task = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("task_id")
        state, body = None, None
        while task:
            s = requests.get(a.ingestor + "/v1/status", params={"task_id": task}, timeout=120)
            body = s.json() if s.status_code == 200 else {"status_code": s.status_code}
            state = body.get("state")
            if state in ("FINISHED", "FAILED", "UNKNOWN"):
                break
            time.sleep(5)
        rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "batch": b // a.batch, "files": len(part), "upload_status": r.status_code, "task": task, "state": state,
               "seconds": round(time.time() - t0, 1), "result": {k: v for k, v in (body or {}).items() if k in ("state", "result")} if body else None,
               "error": None if r.status_code == 200 else r.text[:300]}
        log.write(json.dumps(rec) + "\n"); log.flush()
        print(json.dumps({k: rec[k] for k in ("batch", "files", "upload_status", "state", "seconds")}))
        if r.status_code != 200 or state != "FINISHED":
            raise SystemExit(f"stopped at batch {b // a.batch}")


def capture(a):
    from elasticsearch import Elasticsearch
    es = Elasticsearch(a.es, request_timeout=300)
    info = es.indices.get(index=a.index)[a.index]
    one = es.search(index=a.index, body={"size": 1, "query": {"match_all": {}}})["hits"]["hits"][0]["_source"]
    rec = {"index": a.index, "settings": info["settings"], "mappings": info["mappings"], "count": es.count(index=a.index)["count"],
           "one_document_metadata": one.get("metadata"), "one_document_fields": sorted(one)}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"count": rec["count"], "fields": rec["one_document_fields"]}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("stage", "ingest", "capture"))
    for x in ("--dataset", "--datasets-root", "--staged-dir", "--collection", "--record", "--es", "--index", "--out"):
        ap.add_argument(x)
    ap.add_argument("--n", type=int, default=100000); ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--ingestor", default="http://ingestor-server:8082"); ap.add_argument("--vdb-endpoint", default="http://elasticsearch:9200")
    a = ap.parse_args()
    {"stage": stage, "ingest": ingest, "capture": capture}[a.cmd](a)
