#!/usr/bin/env python3
"""Vol.5 · cell C4, the time of each stage of the Blueprint's query path, read from the RAG server itself: for each
question one POST /v1/generate {messages: [user: question], use_knowledge_base: true, collection_names: [--collection]}
(every other setting the server's default), read as a stream to its end.

  stages     the `metrics` object the server puts in its last stream chunk (rag_server/response_generator.py, class
             Metrics): retrieval_time_ms (query embedding + vector search), context_reranker_time_ms, llm_ttft_ms,
             rag_ttft_ms, llm_generation_time_ms; copied as the server sent them
  client     the wall clock of the whole call in the client, and the time to the first chunk that carries answer text
  load       --concurrency calls in flight (1 or 4), questions in a fixed order (the C3 sample, seed 20261018)

One JSON line per question, written as it arrives; a summary (p50, p90, p99, mean per field) at the end.
usage: c4_timing.py --rag URL --queries FILE --ids FILE(question table) --collection NAME --concurrency N --out FILE
"""
import argparse, concurrent.futures as cf, json, os, statistics, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "eval"))
import hotpot_scoring as H  # noqa: E402

FIELDS = ("retrieval_time_ms", "context_reranker_time_ms", "llm_ttft_ms", "rag_ttft_ms", "llm_generation_time_ms", "client_total_ms", "client_first_text_ms")


def one(rag, question, collection, session):
    t0 = time.perf_counter(); first = None; metrics = None; n = 0; status = None
    with session.post(rag.rstrip("/") + "/v1/generate", json={"messages": [{"role": "user", "content": question}], "use_knowledge_base": True,
                                                             "collection_names": [collection]}, stream=True, timeout=1800) as r:
        status = r.status_code
        for raw in r.iter_lines():
            if not raw or not raw.startswith(b"data:"):
                continue
            data = raw[5:].strip()
            if data == b"[DONE]":
                break
            try:
                j = json.loads(data)
            except json.JSONDecodeError:
                continue
            n += 1
            if j.get("metrics"):
                metrics = j["metrics"]
            for ch in j.get("choices") or []:
                txt = ((ch.get("delta") or {}).get("content")) or ((ch.get("message") or {}).get("content"))
                if txt and first is None:
                    first = (time.perf_counter() - t0) * 1000
    return {"status": status, "chunks": n, "metrics": metrics, "client_total_ms": (time.perf_counter() - t0) * 1000, "client_first_text_ms": first}


def main():
    ap = argparse.ArgumentParser()
    for x in ("--rag", "--queries", "--ids", "--collection", "--out"):
        ap.add_argument(x, required=True)
    ap.add_argument("--concurrency", type=int, required=True)
    a = ap.parse_args()
    import requests
    queries = {r["_id"]: r["text"] for r in (json.loads(l) for l in open(a.queries, encoding="utf-8"))}
    ids = sorted(json.loads(l)["query_id"] for l in open(a.ids, encoding="utf-8"))
    sample = H.c3_sample(ids)
    lock = threading.Lock(); fh = open(a.out + ".jsonl", "w", encoding="utf-8", newline="\n"); local = threading.local(); rows = []

    def job(qid):
        s = getattr(local, "s", None) or requests.Session(); local.s = s
        try:
            rec = {"query_id": qid, **one(a.rag, queries[qid], a.collection, s)}
        except Exception as e:
            rec = {"query_id": qid, "status": "error", "error": repr(e)[:500]}
        with lock:
            fh.write(json.dumps(rec) + "\n"); fh.flush(); rows.append(rec)

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        list(ex.map(job, sample))
    summ = {"questions": len(rows), "concurrency": a.concurrency, "wall_seconds": time.time() - t0,
            "ok": sum(1 for r in rows if r.get("status") == 200 and r.get("metrics")), "fields": {}}
    for f in FIELDS:
        v = sorted(x for x in ((r.get("metrics") or {}).get(f) if f not in ("client_total_ms", "client_first_text_ms") else r.get(f) for r in rows) if isinstance(x, (int, float)))
        if v:
            summ["fields"][f] = {"n": len(v), "p50": statistics.median(v), "p90": v[int(0.9 * (len(v) - 1))], "p99": v[min(len(v) - 1, int(round(0.99 * (len(v) - 1))))], "mean": statistics.fmean(v)}
    json.dump(summ, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: summ[k] for k in ("questions", "ok", "concurrency")} | {f: round(v["p50"], 1) for f, v in summ["fields"].items()}))


if __name__ == "__main__":
    main()
