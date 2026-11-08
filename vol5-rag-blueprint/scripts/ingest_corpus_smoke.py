#!/usr/bin/env python3
"""Vol.5 · the text-only ingestion path of the NVIDIA RAG Blueprint over a list of files, one file per upload, so that
every file has its own duration, its own chunk count and its own error. A smoke test of the path, not a measurement
of speed. The steps and the request forms are those of ingest_text_only_smoke.py, whose functions are imported.

Per file (named by its id of the list; the files are copies named <id>.<extension> outside the repository):
  POST /v1/documents (one file, non-blocking, no summary, the Blueprint's default split of 512 tokens with 150 overlap)
  GET  /v1/status until the task is finished or failed or the limit is reached
  the collection's row count in Milvus after it: the difference to the count before is the file's chunk count
Recorded: id, format, bytes, status codes, seconds, the task's state and counts, for a failure the first 300
characters of the server's message, the row counts; the card's memory at every poll (its highest value is kept) and
the memory `docker stats` reports per container at the start, after every tenth file and at the end. No text of a file
or of a chunk is read or recorded.

usage: ingest_corpus_smoke.py --list LIST.json --staged-dir DIR --out FILE.json [--collection NAME] [--only-format pdf|md]
                              [--limit N] [--wait-ready 900] [--wait-task 600] [endpoints as ingest_text_only_smoke.py]
"""
import argparse, hashlib, json, os, subprocess, sys, time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_text_only_smoke import call, card, keys_of, now  # noqa: E402

MIME = {"pdf": "application/pdf", "md": "text/markdown", "txt": "text/plain"}


def docker_memory():
    try:
        o = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}"], capture_output=True, text=True, timeout=60).stdout.strip().splitlines()
        out = {}
        for line in o:
            name, use = line.split("\t"); v = use.split("/")[0].strip()
            n = float("".join(c for c in v if c.isdigit() or c == ".")); out[name] = round(n * (1024 if "GiB" in v else 1 if "MiB" in v else 1 / 1024), 1)
        return {"at": now(), "mib_per_container": out, "mib_total": round(sum(out.values()), 1)}
    except Exception as e:
        return {"at": now(), "error": str(e)[:120]}


def rows_in(a, steps):
    _, count = call(steps, "Milvus: count of rows", "POST", a.milvus + "/v2/vectordb/entities/query", json={"collectionName": a.collection, "filter": "", "outputFields": ["count(*)"], "limit": 1})
    try:
        return ((count or {}).get("data") or [{}])[0].get("count(*)")
    except Exception:
        return None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True); ap.add_argument("--staged-dir", required=True); ap.add_argument("--out", required=True); ap.add_argument("--collection", default="vol5_corpus_smoke")
    ap.add_argument("--only-format"); ap.add_argument("--limit", type=int)
    ap.add_argument("--ingestor", default="http://127.0.0.1:8082"); ap.add_argument("--runtime", default="http://127.0.0.1:7670")
    ap.add_argument("--embedding", default="http://127.0.0.1:9080"); ap.add_argument("--milvus", default="http://127.0.0.1:19530")
    ap.add_argument("--vdb-endpoint", default="http://milvus:19530"); ap.add_argument("--wait-ready", type=int, default=900); ap.add_argument("--wait-task", type=int, default=600)
    ap.add_argument("--chunk-size", type=int, default=512); ap.add_argument("--chunk-overlap", type=int, default=150)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    L = json.load(open(a.list, encoding="utf-8")); files = [f for f in L["files"] if not a.only_format or f["format"] == a.only_format][: a.limit]
    for f in files:
        p = os.path.join(a.staged_dir, f"{f['id']}.{f['format']}")
        if hashlib.sha256(open(p, "rb").read()).hexdigest() != f["sha256"]:
            raise SystemExit(f"refused: the staged copy of {f['id']} does not have the SHA-256 of the list")
    out = {"at": now(), "what": "the text-only ingestion path over a list of files, one upload per file; ids, counts, seconds and status codes only", "collection": a.collection,
           "list": {"sha256": hashlib.sha256(open(a.list, "rb").read()).hexdigest(), "files_in_the_list": len(L["files"]), "files_sent": len(files)},
           "split_options": {"chunk_size": a.chunk_size, "chunk_overlap": a.chunk_overlap}, "card_at_start": card(), "container_memory": [docker_memory()], "ready": {}, "steps": [], "files": []}
    steps = out["steps"]; t0 = time.time(); peak = out["card_at_start"].get("used_mib") or 0
    health = {"ingestor-server": a.ingestor + "/v1/health", "nv-ingest-ms-runtime": a.runtime + "/v1/health/ready", "nemotron-embedding-ms": a.embedding + "/v1/health/ready"}
    while time.time() - t0 < a.wait_ready and len(out["ready"]) < len(health):
        for name, url in health.items():
            if name not in out["ready"]:
                try:
                    if requests.get(url, timeout=5).status_code == 200:
                        out["ready"][name] = {"seconds_from_the_start_of_this_program": round(time.time() - t0, 1)}
                except Exception:
                    pass
        time.sleep(3)
    out["all_ready"] = len(out["ready"]) == len(health)
    if out["all_ready"]:
        call(steps, "create the collection", "POST", a.ingestor + "/v1/collection", json={"vdb_endpoint": a.vdb_endpoint, "collection_name": a.collection})
        before = rows_in(a, steps) or 0; setup_steps = len(steps)
        for i, f in enumerate(files, 1):
            p = os.path.join(a.staged_dir, f"{f['id']}.{f['format']}"); rec = {"id": f["id"], "format": f["format"], "bytes": f["bytes"], "pages": f.get("pages"), "at": now()}
            data = {"vdb_endpoint": a.vdb_endpoint, "collection_name": a.collection, "blocking": False, "split_options": {"chunk_size": a.chunk_size, "chunk_overlap": a.chunk_overlap}, "generate_summary": False}
            t1 = time.time(); one = []
            status, body = call(one, "upload", "POST", a.ingestor + "/v1/documents", timeout=600, files=[("documents", (os.path.basename(p), open(p, "rb"), MIME.get(f["format"], "application/octet-stream")))],
                                data={"data": json.dumps(data)})
            rec["upload_status"] = status; task = (body or {}).get("task_id") if isinstance(body, dict) else None
            if status is None or status >= 400:
                rec["upload_answer"] = one[-1].get("body") or one[-1].get("error")
            state = last = None; polls = 0
            while task and time.time() - t1 < a.wait_task:
                try:
                    r = requests.get(a.ingestor + "/v1/status", params={"task_id": task}, timeout=60); polls += 1
                    last = r.json() if r.status_code == 200 else {"http": r.status_code, "body": r.text[:300]}
                    state = last.get("state") if isinstance(last, dict) else None
                except Exception as e:
                    last = {"error": str(e)[:200]}
                peak = max(peak, card().get("used_mib") or 0)
                if state in ("FINISHED", "FAILED", "SUCCESS", "FAILURE"):
                    break
                time.sleep(2)
            res = (last or {}).get("result") if isinstance(last, dict) else None; res = res if isinstance(res, dict) else {}
            failed = res.get("failed_documents") or []
            after = rows_in(a, one); waited = 0            # the count can trail the task by a moment: wait up to 10 s for it to move
            while state in ("FINISHED", "SUCCESS") and not failed and isinstance(after, int) and after <= before and waited < 10:
                time.sleep(1); waited += 1; after = rows_in(a, one)
            rec.update({"task_state": state, "seconds": round(time.time() - t1, 1), "polls": polls, "documents_completed": res.get("documents_completed"), "failed_documents": len(failed),
                        "failure_message": (json.dumps(failed[0], ensure_ascii=False)[:300] if failed else None) or ((res.get("message") or "")[:300] if state in ("FAILED", "FAILURE") else None),
                        "task_answer_keys": keys_of(last) if state not in ("FINISHED", "SUCCESS") else None,
                        "rows_after": after, "chunks_of_this_file": (after - before) if isinstance(after, int) else None})
            before = after if isinstance(after, int) else before
            out["files"].append(rec)
            if i % 10 == 0:
                out["container_memory"].append(docker_memory())
            print(json.dumps({k: rec[k] for k in ("id", "task_state", "seconds", "chunks_of_this_file", "failure_message")}, ensure_ascii=False)[:300], flush=True)
        _, docs = call(steps, "list the documents", "GET", a.ingestor + "/v1/documents", params={"collection_name": a.collection, "vdb_endpoint": a.vdb_endpoint})
        out["documents_listed"] = docs.get("total_documents", len(docs.get("documents") or [])) if isinstance(docs, dict) else None
        _, stats = call(steps, "Milvus: collection statistics", "POST", a.milvus + "/v2/vectordb/collections/get_stats", json={"collectionName": a.collection})
        out["rows_in_the_vector_database"] = {"get_stats_rowCount": ((stats or {}).get("data") or {}).get("rowCount") if isinstance(stats, dict) else None, "count_query": rows_in(a, steps)}
        ok = [f for f in out["files"] if f["task_state"] in ("FINISHED", "SUCCESS") and not f["failed_documents"]]
        out["totals"] = {"files_sent": len(files), "finished_without_a_failed_document": len(ok), "not_finished_or_failed": [f["id"] for f in out["files"] if f not in ok],
                         "chunks": sum(f["chunks_of_this_file"] or 0 for f in out["files"]), "seconds_of_all_uploads": round(sum(f["seconds"] for f in out["files"]), 1),
                         "by_format": {fmt: {"files": sum(1 for f in out["files"] if f["format"] == fmt), "finished": sum(1 for f in ok if f["format"] == fmt), "chunks": sum(f["chunks_of_this_file"] or 0 for f in out["files"] if f["format"] == fmt)}
                                       for fmt in sorted({f["format"] for f in out["files"]})}}
    out["container_memory"].append(docker_memory())
    out["card_at_end"] = card(); out["card_memory_highest_seen_mib"] = max(peak, out["card_at_end"].get("used_mib") or 0)
    out["container_memory_highest_total_mib"] = max((m.get("mib_total") or 0) for m in out["container_memory"])
    out["program_sha256"] = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"all_ready": out["all_ready"], "totals": out.get("totals"), "rows": out.get("rows_in_the_vector_database"), "card_peak_mib": out["card_memory_highest_seen_mib"],
                      "container_memory_peak_mib": out["container_memory_highest_total_mib"]}, ensure_ascii=False)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
