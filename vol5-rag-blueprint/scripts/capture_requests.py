#!/usr/bin/env python3
"""Vol.5 · drives the Blueprint's RAG server (2.6.0, all its model services replaced by capture_service.py) to send the
answer model the requests of arms N and O, and labels each captured request with its arm, its question and, for O, the
passage order the server used (read from the server's own context, "File: <id>" in order).

  N  POST /v1/generate {messages: [user: question], use_knowledge_base: false} for the first --n-questions questions
  O  for the first --o-questions questions: an index holding only the question's two supporting passages, in the
     Blueprint's document shape (the metadata template of the night, the passage id as file name; text = Vol.4's
     passage text; any vector, since the stand-in embedding answers every question with one vector), then
     POST /v1/generate {messages: [user: question], use_knowledge_base: true, collection_names: [that index]};
     everything else in the request is the server's default
The captured files are those capture_service.py writes; this program adds "meta" to each.

usage: capture_requests.py --rag URL --es URL --captured DIR --queries FILE --ids FILE --corpus-passages FILE
                           --mapping FILE --metadata FILE [--n-questions 20] [--o-questions 5]
"""
import argparse, glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from es_bulk_load import fill  # noqa: E402


def newest(captured, before):
    for _ in range(600):
        files = {p for p in glob.glob(os.path.join(captured, "*.json")) if os.path.splitext(os.path.basename(p))[0].isdigit()} - before
        if files:
            return max(files, key=lambda p: int(os.path.splitext(os.path.basename(p))[0]))
        time.sleep(0.1)
    raise SystemExit("refused: the server sent no request to the answer model")


def ask(rag, payload):
    import requests
    r = requests.post(rag.rstrip("/") + "/v1/generate", json=payload, timeout=300, stream=True)
    text = b"".join(r.iter_content(chunk_size=None))
    return r.status_code, text[:400]


def label(path, meta):
    cap = json.load(open(path, encoding="utf-8")); cap["meta"] = meta
    json.dump(cap, open(path, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    for x in ("--rag", "--es", "--captured", "--queries", "--ids", "--corpus-passages", "--mapping", "--metadata"):
        ap.add_argument(x, required=True)
    ap.add_argument("--n-questions", type=int, default=20); ap.add_argument("--o-questions", type=int, default=5)
    a = ap.parse_args()
    import requests
    queries = {r["_id"]: r["text"] for r in (json.loads(l) for l in open(a.queries, encoding="utf-8"))}
    ps = {r["_id"]: r["text"] for r in (json.loads(l) for l in open(a.corpus_passages, encoding="utf-8"))}
    table = sorted((json.loads(l) for l in open(a.ids, encoding="utf-8")), key=lambda r: r["query_id"])
    mapping = json.load(open(a.mapping, encoding="utf-8")); template = json.load(open(a.metadata, encoding="utf-8"))
    log = []
    for r in table[:a.n_questions]:
        before = set(glob.glob(os.path.join(a.captured, "*.json")))
        st, head = ask(a.rag, {"messages": [{"role": "user", "content": queries[r["query_id"]]}], "use_knowledge_base": False})
        f = newest(a.captured, before); label(f, {"arm": "N", "query_id": r["query_id"]})
        log.append({"arm": "N", "query_id": r["query_id"], "status": st, "file": os.path.basename(f)})
    dim = mapping["mappings"]["properties"]["vector"]["dims"]
    for i, r in enumerate(table[:a.o_questions]):
        ix = f"o_capture_{i}"
        requests.delete(f"{a.es}/{ix}")
        c = requests.put(f"{a.es}/{ix}", json=mapping); c.raise_for_status()
        for k, pid in enumerate(r["gold_passages"]):
            v = [0.0] * dim; v[k] = 1.0
            requests.put(f"{a.es}/{ix}/_doc/{pid}", json={"text": ps[pid], "vector": v, "metadata": fill(template, pid)}).raise_for_status()
        requests.post(f"{a.es}/{ix}/_refresh").raise_for_status()
        before = set(glob.glob(os.path.join(a.captured, "*.json")))
        st, head = ask(a.rag, {"messages": [{"role": "user", "content": queries[r["query_id"]]}], "use_knowledge_base": True, "collection_names": [ix]})
        f = newest(a.captured, before)
        body = json.load(open(f, encoding="utf-8"))["body"]
        context = "\n".join(m["content"] for m in body["messages"] if isinstance(m.get("content"), str))
        order = re.findall(r"^File: (\S+)$", context, flags=re.M)
        label(f, {"arm": "O", "query_id": r["query_id"], "passage_order": order, "index": ix})
        log.append({"arm": "O", "query_id": r["query_id"], "status": st, "file": os.path.basename(f), "passage_order": order, "gold_passages": r["gold_passages"]})
        requests.delete(f"{a.es}/{ix}")
    json.dump(log, open(os.path.join(a.captured, "capture_log.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"N": sum(x["arm"] == "N" for x in log), "O": sum(x["arm"] == "O" for x in log), "statuses": sorted({x["status"] for x in log})}))


if __name__ == "__main__":
    main()
