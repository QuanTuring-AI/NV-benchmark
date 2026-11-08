#!/usr/bin/env python3
"""Vol.5 · cell C4, the branch where no configuration fits (supplement 5): each model service alone on the card, c = 1,
the 200 questions of the C3 sample, each request the one the Blueprint's RAG server sends (read from the server:
results/c2/request_params.json, p_request_control.json). Files and figures are marked not_coresident.

  embed  POST /v1/embeddings {"input": [question], "model": M, "encoding_format": "float", "input_type": "query",
         "truncate": "END", "dimensions": 2048} (the captured body); the call's duration
  rank   the question's 100 passages of C1's run, in the four ranking requests of p_arm.py (32, 32, 32, 4), one after
         the other; each call's duration and their sum
  llm    arm P's answer request for the question (answer_arms.py arm O builder with its reranked 10 passages), streamed:
         time to the first chunk with any text (reasoning or answer), to the first answer text, and to the end
usage: stage_alone_timing.py embed --url URL --model M --queries FILE --ids FILE --out FILE
       stage_alone_timing.py rank --url URL --queries FILE --ids FILE --run FILE --texts FILE --out FILE
       stage_alone_timing.py llm --url URL --queries FILE --ids FILE --p-ids FILE --passages FILE --prompts FILE --params FILE --out FILE
"""
import argparse, json, os, statistics, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(V5, "eval"))
import hotpot_scoring as H  # noqa: E402


def summary(v):
    v = sorted(x for x in v if isinstance(x, (int, float)))
    return {"n": len(v), "p50": statistics.median(v), "p90": v[int(0.9 * (len(v) - 1))], "p99": v[min(len(v) - 1, int(round(0.99 * (len(v) - 1))))], "mean": statistics.fmean(v)} if v else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("embed", "rank", "llm"))
    for x in ("--url", "--model", "--queries", "--ids", "--run", "--texts", "--p-ids", "--passages", "--prompts", "--params", "--out"):
        ap.add_argument(x)
    a = ap.parse_args()
    import requests
    s = requests.Session()
    queries = {r["_id"]: r["text"] for r in (json.loads(l) for l in open(a.queries, encoding="utf-8"))}
    sample = H.c3_sample(sorted(json.loads(l)["query_id"] for l in open(a.ids, encoding="utf-8")))
    rows = []; fh = open(a.out + ".jsonl", "w", encoding="utf-8", newline="\n")
    if a.cmd == "embed":
        for q in sample:
            t0 = time.perf_counter()
            r = s.post(a.url.rstrip("/") + "/v1/embeddings", json={"input": [queries[q]], "model": a.model, "encoding_format": "float", "input_type": "query", "truncate": "END", "dimensions": 2048}, timeout=300)
            rows.append({"query_id": q, "status": r.status_code, "embed_ms": (time.perf_counter() - t0) * 1000})
            fh.write(json.dumps(rows[-1]) + "\n"); fh.flush()
        fields = ("embed_ms",)
    elif a.cmd == "rank":
        import p_arm as P
        texts = {r["_id"]: r["text"] for r in (json.loads(l) for l in open(a.texts, encoding="utf-8"))}
        run = P.read_run(a.run); model = s.get(a.url.rstrip("/") + "/v1/models", timeout=60).json()["data"][0]["id"]
        for q in sample:
            calls = []
            for b in P.ranking_bodies(model, queries[q], [texts[i] for i in run[q][:P.VDB_TOP_K]]):
                t0 = time.perf_counter(); r = s.post(a.url.rstrip("/") + "/v1/ranking", json=b, timeout=300); calls.append((time.perf_counter() - t0) * 1000)
            rows.append({"query_id": q, "status": r.status_code, "rank_calls_ms": calls, "rank_ms": sum(calls)})
            fh.write(json.dumps(rows[-1]) + "\n"); fh.flush()
        fields = ("rank_ms",)
    else:
        import answer_arms as A
        prompts = A.load_prompts(a.prompts); params = json.load(open(a.params, encoding="utf-8"))["body"]
        ps = A.read_passages(a.passages); pid = {json.loads(l)["query_id"]: json.loads(l)["gold_passages"] for l in open(a.p_ids, encoding="utf-8")}
        for q in sample:
            body = A.body(prompts, params, "O", queries[q], [(p, ps[p]) for p in pid[q]])
            t0 = time.perf_counter(); first_any = first_answer = None; usage = None
            with s.post(a.url.rstrip("/") + "/v1/chat/completions", json=body, stream=True, timeout=1800) as r:
                for raw in r.iter_lines():
                    if not raw or not raw.startswith(b"data:"):
                        continue
                    d = raw[5:].strip()
                    if d == b"[DONE]":
                        break
                    j = json.loads(d); usage = j.get("usage") or usage
                    for ch in j.get("choices") or []:
                        dl = ch.get("delta") or {}
                        if (dl.get("reasoning_content") or dl.get("reasoning") or dl.get("content")) and first_any is None:
                            first_any = (time.perf_counter() - t0) * 1000
                        if dl.get("content") and first_answer is None:
                            first_answer = (time.perf_counter() - t0) * 1000
            rows.append({"query_id": q, "status": r.status_code, "first_token_ms": first_any, "first_answer_ms": first_answer, "done_ms": (time.perf_counter() - t0) * 1000,
                         "completion_tokens": (usage or {}).get("completion_tokens")})
            fh.write(json.dumps(rows[-1]) + "\n"); fh.flush()
        fields = ("first_token_ms", "first_answer_ms", "done_ms")
    rec = {"not_coresident": True, "stage": a.cmd, "questions": len(rows), "ok": sum(1 for r in rows if r["status"] == 200), "concurrency": 1,
           "fields": {f: summary([r.get(f) for r in rows]) for f in fields}}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: rec[k] for k in ("stage", "questions", "ok")} | {f: round(v["p50"], 1) for f, v in rec["fields"].items() if v}))


if __name__ == "__main__":
    main()
