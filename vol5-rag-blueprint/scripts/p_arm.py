#!/usr/bin/env python3
"""Vol.5 · cell C2, arm P: the Blueprint's knowledge-base path split into its steps, each step's request exactly as the
RAG server (2.6.0) sends it, read from the server itself (capture_service_all.py, capture_requests_p.py).

What the server does with every setting at its default (read from five captured questions):
  retrieve  kNN on the collection, k = num_candidates = 100 (the query of es_ann_vs_exact.py `search`; its run of C1 is
            the retrieval of this arm, with Vol.4's query vectors, which control (a) showed equal to the server's)
  rerank    POST <reranker>/v1/ranking, the 100 passages in retrieval order in batches of 32 (32, 32, 32, 4):
            {"model": <the reranker's served model>, "query": {"text": <question>}, "passages": [{"text": <text>}...],
             "truncate": "END"}; the model name is the first one the reranking service lists at /v1/models
  select    all logits together, highest first, the first 10 (APP_RETRIEVER_TOPK); RERANKER_SCORE_THRESHOLD 0.0 on the
            sigmoid of the logit drops nothing
  answer    the RAG prompt with the 10 passages in that order: the request arm O uses (answer_arms.py `body`, arm "O"),
            so arm P differs from O only in the passages

Subcommands
  control  rebuilds every captured question: the retrieval with the stand-in's constant query vector, the ranking
           bodies, the selection with the stand-in's logits, the answer body; each must equal what the server sent
  rerank   the reranking step for every question of a retrieval run (TREC, 100 per question) against a reranking NIM;
           one JSON line per question (the 10 passage ids in order, all logits); resumable
  texts    the passages of a retrieval run (Vol.4's passage text), written once to a file kept outside
  ids      the reranked top 10 as an id table answer_arms.py can read (gold_passages replaced by the 10 ids, in order)
           and the passages file for them

usage: p_arm.py control --es URL --index NAME --captured DIR --queries FILE --ids FILE --prompts FILE --params FILE --out FILE
       p_arm.py rerank --run FILE --queries FILE --texts FILE --url URL --out FILE [--concurrency 1]
       p_arm.py texts --run FILE --datasets-root DIR --dataset NAME --out FILE
       p_arm.py ids --reranked FILE --ids FILE --datasets-root DIR --dataset NAME --out-ids FILE --out-passages FILE
"""
import argparse, concurrent.futures as cf, glob, hashlib, json, os, re, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
BATCH, TOP_N, TRUNCATE, VDB_TOP_K = 32, 10, "END", 100


def ranking_bodies(model, question, texts):
    return [{"model": model, "query": {"text": question}, "passages": [{"text": t} for t in texts[i:i + BATCH]], "truncate": TRUNCATE}
            for i in range(0, len(texts), BATCH)]


def select(logits, n=TOP_N):
    """logits in retrieval order -> the positions of the first n by logit, highest first (ties: earlier position first)."""
    return sorted(range(len(logits)), key=lambda i: (-logits[i], i))[:n]


def stand_in_logit(text):
    return (int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % 2000) / 100 - 10


def basename_id(source_name):
    return os.path.splitext(os.path.basename(source_name))[0]


def control(a):
    import requests, answer_arms as A
    prompts = A.load_prompts(a.prompts); params = json.load(open(a.params, encoding="utf-8")); params = params.get("body", params)
    queries = A.read_queries(a.queries)
    log = json.load(open(os.path.join(a.captured, "capture_log_p.json"), encoding="utf-8")); rows = []
    for item in log:
        qid = item["query_id"]; q = queries[qid]
        cap = {f: json.load(open(os.path.join(a.captured, f), encoding="utf-8"))["body"] for f in item["files"]}
        emb = [cap[f] for f in item["files"] if f.endswith("_embeddings.json")]
        rank = [cap[f] for f in item["files"] if f.endswith("_ranking.json")]
        chat = [cap[f] for f in item["files"] if f.endswith("_chat.json")][0]
        dim = 2048; vec = [1.0 / dim ** 0.5] * dim
        r = requests.post(f"{a.es}/{a.index}/_search", json={"knn": {"field": "vector", "query_vector": vec, "k": VDB_TOP_K, "num_candidates": VDB_TOP_K},
                                                           "_source": ["text", "metadata.source.source_name"], "size": VDB_TOP_K}).json()
        hits = [(basename_id(h["_source"]["metadata"]["source"]["source_name"]), h["_source"]["text"]) for h in r["hits"]["hits"]]
        texts = [t for _, t in hits]
        mine_rank = ranking_bodies(rank[0]["model"], q, texts)
        logits = [stand_in_logit(t) for t in texts]
        top = [hits[i] for i in select(logits)]
        mine_chat = A.body(prompts, params, "O", q, top)
        rows.append({"query_id": qid, "embedding_input_is_the_question": emb[0]["input"] == [q] if emb else None,
                     "ranking_requests": [len(mine_rank), len(rank)], "ranking_bodies_equal": mine_rank == rank,
                     "answer_body_equal": mine_chat == chat, "passages_in_answer": len(top),
                     "first_difference": None if mine_chat == chat else next(({"index": i, "ours": m["content"][:300], "server": g["content"][:300]} for i, (m, g) in enumerate(zip(mine_chat["messages"], chat["messages"])) if m != g), "other fields")})
    neg = {}
    if rows:
        item = log[0]; qid = item["query_id"]; q = queries[qid]
        cap = {f: json.load(open(os.path.join(a.captured, f), encoding="utf-8"))["body"] for f in item["files"]}
        rank = [cap[f] for f in item["files"] if f.endswith("_ranking.json")]; chat = [cap[f] for f in item["files"] if f.endswith("_chat.json")][0]
        dim = 2048; vec = [1.0 / dim ** 0.5] * dim
        r = requests.post(f"{a.es}/{a.index}/_search", json={"knn": {"field": "vector", "query_vector": vec, "k": VDB_TOP_K, "num_candidates": VDB_TOP_K},
                                                           "_source": ["text", "metadata.source.source_name"], "size": VDB_TOP_K}).json()
        hits = [(basename_id(h["_source"]["metadata"]["source"]["source_name"]), h["_source"]["text"]) for h in r["hits"]["hits"]]
        texts = [t for _, t in hits]; logits = [stand_in_logit(t) for t in texts]
        neg = {"ranking_in_reverse_retrieval_order": ranking_bodies(rank[0]["model"], q, texts[::-1]) == rank,
               "ranking_batches_of_25": [{"model": rank[0]["model"], "query": {"text": q}, "passages": [{"text": t} for t in texts[i:i + 25]], "truncate": TRUNCATE} for i in range(0, len(texts), 25)] == rank,
               "answer_with_first_10_retrieved_not_reranked": A.body(prompts, params, "O", q, hits[:10]) == chat,
               "answer_with_lowest_logit_first": A.body(prompts, params, "O", q, [hits[i] for i in select(logits)][::-1]) == chat,
               "answer_with_11_passages": A.body(prompts, params, "O", q, [hits[i] for i in select(logits, 11)]) == chat}
    rec = {"captured_questions": len(rows), "all_ranking_equal": bool(rows) and all(r["ranking_bodies_equal"] for r in rows),
           "all_answer_equal": bool(rows) and all(r["answer_body_equal"] for r in rows), "rows": rows,
           "negative_controls_equal_should_all_be_false": neg}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({k: rec[k] for k in ("captured_questions", "all_ranking_equal", "all_answer_equal", "negative_controls_equal_should_all_be_false")}))
    return 0 if rec["all_ranking_equal"] and rec["all_answer_equal"] and not any(neg.values()) else 1


def read_run(path):
    run = {}
    for line in open(path, encoding="utf-8"):
        q, _, d, rank, score, _t = line.split()
        run.setdefault(q, []).append((int(rank), d))
    return {q: [d for _, d in sorted(v)] for q, v in run.items()}


def rerank(a):
    import requests
    queries = {r["_id"]: r["text"] for r in (json.loads(l) for l in open(a.queries, encoding="utf-8"))}
    texts = {r["_id"]: r["text"] for r in (json.loads(l) for l in open(a.texts, encoding="utf-8"))}
    run = read_run(a.run)
    model = requests.get(a.url.rstrip("/") + "/v1/models", timeout=60).json()["data"][0]["id"]
    done = set()
    if os.path.isfile(a.out):
        for l in open(a.out, encoding="utf-8"):
            try:
                done.add(json.loads(l)["query_id"])
            except (json.JSONDecodeError, KeyError):
                pass
    lock = threading.Lock(); fh = open(a.out, "a", encoding="utf-8", newline="\n"); session = threading.local()

    def one(qid):
        ids = run[qid][:VDB_TOP_K]; ts = [texts[i] for i in ids]
        s = getattr(session, "s", None) or requests.Session(); session.s = s
        logits = [None] * len(ids); t0 = time.time()
        for b, body in enumerate(ranking_bodies(model, queries[qid], ts)):
            r = s.post(a.url.rstrip("/") + "/v1/ranking", json=body, timeout=600); r.raise_for_status()
            for x in r.json()["rankings"]:
                logits[b * BATCH + x["index"]] = x["logit"]
        if any(v is None for v in logits):
            raise RuntimeError(f"{qid}: a passage without a logit")
        top = select(logits)
        rec = {"query_id": qid, "model": model, "top": [ids[i] for i in top], "top_logits": [logits[i] for i in top], "logits": logits, "retrieved": ids, "t0": t0, "t1": time.time()}
        with lock:
            fh.write(json.dumps(rec) + "\n"); fh.flush()
        return 1

    todo = [q for q in sorted(run) if q not in done]
    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        n = sum(ex.map(one, todo))
    print(json.dumps({"questions": n, "skipped_done": len(done), "model": model}))
    return 0


def texts(a):
    """Every passage of a retrieval run (first 100 per question), Vol.4's passage text, one JSON line each."""
    sys.path.insert(0, os.path.join(os.path.dirname(V5), "vol4-retriever", "scripts")); import retrieval_datasets as R
    want = {p for v in read_run(a.run).values() for p in v[:VDB_TOP_K]}; n = 0
    with open(a.out, "w", encoding="utf-8", newline="\n") as w:
        for pid, title, text in R.load(a.datasets_root, a.dataset).iter_corpus():
            if str(pid) in want:
                w.write(json.dumps({"_id": str(pid), "text": R.passage_text(title, text)}, ensure_ascii=False) + "\n"); n += 1
    if n != len(want):
        raise SystemExit(f"refused: {len(want) - n} passages of the run not in the corpus")
    print(json.dumps({"passages": n}))
    return 0


def ids(a):
    sys.path.insert(0, os.path.join(os.path.dirname(V5), "vol4-retriever", "scripts")); import retrieval_datasets as R
    top = {}
    for l in open(a.reranked, encoding="utf-8"):
        try:
            r = json.loads(l); top[r["query_id"]] = r["top"]
        except (json.JSONDecodeError, KeyError):
            pass
    table = [json.loads(l) for l in open(a.ids, encoding="utf-8")]
    missing = [r["query_id"] for r in table if r["query_id"] not in top]
    if missing:
        raise SystemExit(f"refused: {len(missing)} questions without a reranked list")
    want = {p for v in top.values() for p in v}; got = {}
    for pid, title, text in R.load(a.datasets_root, a.dataset).iter_corpus():
        if str(pid) in want:
            got[str(pid)] = R.passage_text(title, text)
    with open(a.out_ids, "w", encoding="utf-8", newline="\n") as w:
        for r in table:
            w.write(json.dumps({**{k: v for k, v in r.items() if k != "gold_passages"}, "gold_passages": top[r["query_id"]], "note": "gold_passages holds arm P's reranked top 10, in order"}) + "\n")
    with open(a.out_passages, "w", encoding="utf-8", newline="\n") as w:
        for pid in sorted(got):
            w.write(json.dumps({"_id": pid, "text": got[pid]}, ensure_ascii=False) + "\n")
    print(json.dumps({"questions": len(table), "passages": len(got)}))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("control", "rerank", "texts", "ids"))
    for x in ("--es", "--index", "--captured", "--queries", "--ids", "--prompts", "--params", "--out", "--run", "--texts", "--url", "--reranked",
              "--datasets-root", "--dataset", "--out-ids", "--out-passages"):
        ap.add_argument(x)
    ap.add_argument("--concurrency", type=int, default=1)
    a = ap.parse_args()
    sys.exit({"control": control, "rerank": rerank, "texts": texts, "ids": ids}[a.cmd](a))
