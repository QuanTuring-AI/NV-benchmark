#!/usr/bin/env python3
"""Vol.5 · arm P, the Blueprint's own requests: drives the RAG server (2.6.0; its model services replaced by
capture_service_all.py) to answer the first --questions questions of the id table through its knowledge-base path on
the HotpotQA whole-corpus index, with every setting at its default, and lists, per question, the request files the
stand-in wrote (embedding, ranking, answer model) in the order they arrived.

  POST /v1/generate {messages: [user: question], use_knowledge_base: true, collection_names: [--collection]}

usage: capture_requests_p.py --rag URL --captured DIR --queries FILE --ids FILE --collection NAME [--questions 5]
"""
import argparse, glob, json, os, re, time


def files(d):
    return {p for p in glob.glob(os.path.join(d, "*.json")) if re.match(r"^\d+_[a-z]+\.json$", os.path.basename(p))}


def main():
    ap = argparse.ArgumentParser()
    for x in ("--rag", "--captured", "--queries", "--ids", "--collection"):
        ap.add_argument(x, required=True)
    ap.add_argument("--questions", type=int, default=5)
    a = ap.parse_args()
    import requests
    queries = {r["_id"]: r["text"] for r in (json.loads(l) for l in open(a.queries, encoding="utf-8"))}
    table = sorted((json.loads(l) for l in open(a.ids, encoding="utf-8")), key=lambda r: r["query_id"])[:a.questions]
    log = []
    for r in table:
        before = files(a.captured)
        resp = requests.post(a.rag.rstrip("/") + "/v1/generate", json={"messages": [{"role": "user", "content": queries[r["query_id"]]}],
                                                                       "use_knowledge_base": True, "collection_names": [a.collection]}, timeout=600, stream=True)
        b"".join(resp.iter_content(chunk_size=None))
        time.sleep(1)
        new = sorted(files(a.captured) - before, key=lambda p: int(os.path.basename(p).split("_")[0]))
        log.append({"query_id": r["query_id"], "status": resp.status_code, "files": [os.path.basename(p) for p in new]})
        print(json.dumps(log[-1]))
    json.dump(log, open(os.path.join(a.captured, "capture_log_p.json"), "w", encoding="utf-8", newline="\n"), indent=1)


if __name__ == "__main__":
    main()
