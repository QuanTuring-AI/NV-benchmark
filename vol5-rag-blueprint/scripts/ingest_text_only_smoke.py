#!/usr/bin/env python3
"""Vol.5 · one pass through the text-only ingestion path of the NVIDIA RAG Blueprint: are the services up, does a
document go in, and how many chunks arrive in the vector database. A smoke test, not a measurement.

Steps, each recorded with its HTTP status and seconds:
  1  wait until the ingestor server, the ingestion runtime and the embedding NIM answer their health endpoints
     (the seconds each one took from the start of this program are recorded; they include whatever was already up)
  2  POST /v1/collection           (ingestor server; the vector-database endpoint is given explicitly)
  3  POST /v1/documents            (multipart: the files, and the options as the Blueprint's ingestion notebook sends them,
                                   non-blocking, no summary)
  4  GET  /v1/status?task_id=...   until the task is finished or failed, or the limit is reached
  5  GET  /v1/documents            the documents the collection lists
  6  the collection's row count from Milvus's own REST interface (v2 get_stats and a count query)

Recorded: status codes, seconds, counts, the names of the uploaded files (they are the Blueprint's own sample files),
the keys of every answer, and the state and message fields of the task status. Text of a document or of a chunk is not
read and not recorded. For an error, the first 600 characters of the server's answer are kept.

usage: ingest_text_only_smoke.py --files A.pdf [B.pdf ...] --out FILE.json [--collection NAME]
                                 [--ingestor http://127.0.0.1:8082] [--runtime http://127.0.0.1:7670]
                                 [--embedding http://127.0.0.1:9080] [--milvus http://127.0.0.1:19530]
                                 [--vdb-endpoint http://milvus:19530] [--wait-ready 900] [--wait-task 900]
"""
import argparse, hashlib, json, os, subprocess, sys, time

import requests


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def card():
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30).stdout.strip().splitlines()[0]
        return {"used_mib": int(o.split(",")[0]), "util_pct": int(o.split(",")[1])}
    except Exception as e:
        return {"error": str(e)[:100]}


def keys_of(o, depth=0):
    """Key names and counts of an answer; string values are kept only when short and without white space (states, ids)."""
    if isinstance(o, dict):
        return {k: keys_of(v, depth + 1) for k, v in sorted(o.items())} if depth < 5 else "dict"
    if isinstance(o, list):
        return {"list_length": len(o), "first": keys_of(o[0], depth + 1) if o and depth < 5 else None}
    if isinstance(o, str):
        return o if (len(o) <= 64 and " " not in o.strip()) else {"string_characters": len(o)}
    return o


def call(steps, what, method, url, timeout=120, **kw):
    t = time.perf_counter()
    try:
        r = requests.request(method, url, timeout=timeout, **kw)
        rec = {"step": what, "method": method, "path": url.split("//", 1)[1].split("/", 1)[1] if "/" in url.split("//", 1)[1] else "", "status": r.status_code, "seconds": round(time.perf_counter() - t, 3)}
        try:
            body = r.json()
        except ValueError:
            body = None
        if r.status_code >= 400:
            rec["body"] = r.text[:600]
        elif body is not None:
            rec["answer"] = keys_of(body)
        steps.append(rec)
        return r.status_code, body
    except Exception as e:
        steps.append({"step": what, "method": method, "error": f"{type(e).__name__}: {e}"[:300], "seconds": round(time.perf_counter() - t, 3)})
        return None, None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="+", required=True); ap.add_argument("--out", required=True); ap.add_argument("--collection", default="text_only_smoke")
    ap.add_argument("--ingestor", default="http://127.0.0.1:8082"); ap.add_argument("--runtime", default="http://127.0.0.1:7670")
    ap.add_argument("--embedding", default="http://127.0.0.1:9080"); ap.add_argument("--milvus", default="http://127.0.0.1:19530")
    ap.add_argument("--vdb-endpoint", default="http://milvus:19530"); ap.add_argument("--wait-ready", type=int, default=900); ap.add_argument("--wait-task", type=int, default=900)
    ap.add_argument("--chunk-size", type=int, default=512); ap.add_argument("--chunk-overlap", type=int, default=150)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    out = {"at": now(), "what": "one pass through the text-only ingestion path; counts and status codes only", "collection": a.collection,
           "files": [{"name": os.path.basename(f), "bytes": os.path.getsize(f), "sha256": hashlib.sha256(open(f, "rb").read()).hexdigest()} for f in a.files],
           "split_options": {"chunk_size": a.chunk_size, "chunk_overlap": a.chunk_overlap}, "card_at_start": card(), "ready": {}, "steps": []}
    steps = out["steps"]
    t0 = time.time()
    health = {"ingestor-server": a.ingestor + "/v1/health", "nv-ingest-ms-runtime": a.runtime + "/v1/health/ready", "nemotron-embedding-ms": a.embedding + "/v1/health/ready"}
    while time.time() - t0 < a.wait_ready and len(out["ready"]) < len(health):
        for name, url in health.items():
            if name in out["ready"]:
                continue
            try:
                if requests.get(url, timeout=5).status_code == 200:
                    out["ready"][name] = {"seconds_from_the_start_of_this_program": round(time.time() - t0, 1), "endpoint": url.split("//", 1)[1].split("/", 1)[1]}
            except Exception:
                pass
        time.sleep(3)
    out["all_ready"] = len(out["ready"]) == len(health)
    out["card_when_ready"] = card()
    if out["all_ready"]:
        call(steps, "health with dependencies", "GET", a.ingestor + "/v1/health", params={"check_dependencies": "true"})
        call(steps, "create the collection", "POST", a.ingestor + "/v1/collection", json={"vdb_endpoint": a.vdb_endpoint, "collection_name": a.collection})
        data = {"vdb_endpoint": a.vdb_endpoint, "collection_name": a.collection, "blocking": False,
                "split_options": {"chunk_size": a.chunk_size, "chunk_overlap": a.chunk_overlap}, "generate_summary": False}
        files = [("documents", (os.path.basename(f), open(f, "rb"), "application/pdf" if f.lower().endswith(".pdf") else "application/octet-stream")) for f in a.files]
        status, body = call(steps, "upload", "POST", a.ingestor + "/v1/documents", timeout=600, files=files, data={"data": json.dumps(data)})
        task = (body or {}).get("task_id") if isinstance(body, dict) else None
        out["task_id_returned"] = bool(task)
        if task:
            t1 = time.time(); state = None; polls = 0; last = None
            while time.time() - t1 < a.wait_task:
                try:
                    r = requests.get(a.ingestor + "/v1/status", params={"task_id": task}, timeout=60); polls += 1
                    last = r.json() if r.status_code == 200 else {"http": r.status_code, "body": r.text[:300]}
                    state = last.get("state") if isinstance(last, dict) else None
                    if state in ("FINISHED", "FAILED", "SUCCESS", "FAILURE"):
                        break
                except Exception as e:
                    last = {"error": str(e)[:200]}
                time.sleep(5)
            res = (last or {}).get("result") if isinstance(last, dict) else None
            out["task"] = {"state": state, "seconds": round(time.time() - t1, 1), "polls": polls, "limit_s": a.wait_task, "answer": keys_of(last),
                           "total_documents": (res or {}).get("total_documents") if isinstance(res, dict) else None,
                           "documents_completed": (res or {}).get("documents_completed") if isinstance(res, dict) else None,
                           "failed_documents": len((res or {}).get("failed_documents") or []) if isinstance(res, dict) else None,
                           "message": ((res or {}).get("message") or "")[:300] if isinstance(res, dict) else None}
        _, docs = call(steps, "list the documents", "GET", a.ingestor + "/v1/documents", params={"collection_name": a.collection, "vdb_endpoint": a.vdb_endpoint})
        if isinstance(docs, dict):
            out["documents_listed"] = docs.get("total_documents", len(docs.get("documents") or []))
        _, stats = call(steps, "Milvus: collection statistics", "POST", a.milvus + "/v2/vectordb/collections/get_stats", json={"collectionName": a.collection})
        _, count = call(steps, "Milvus: count of rows", "POST", a.milvus + "/v2/vectordb/entities/query", json={"collectionName": a.collection, "filter": "", "outputFields": ["count(*)"], "limit": 1})
        try:
            out["chunks_in_the_vector_database"] = {"get_stats_rowCount": ((stats or {}).get("data") or {}).get("rowCount"),
                                                    "count_query": ((count or {}).get("data") or [{}])[0].get("count(*)")}
        except Exception as e:
            out["chunks_in_the_vector_database"] = {"error": str(e)[:200]}
    out["card_at_end"] = card()
    out["program_sha256"] = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"all_ready": out["all_ready"], "ready": {k: v["seconds_from_the_start_of_this_program"] for k, v in out["ready"].items()}, "task": out.get("task", {}).get("state"),
                      "documents_listed": out.get("documents_listed"), "chunks": out.get("chunks_in_the_vector_database"),
                      "steps": [(s["step"], s.get("status") or s.get("error", "")[:60]) for s in steps]}, ensure_ascii=False)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
