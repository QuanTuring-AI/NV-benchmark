#!/usr/bin/env python3
"""Vol.5 · cell C2, arms N and O: the answer model's request exactly as the Blueprint's RAG server (2.6.0) would send
it, sent straight to the answer model's NIM, for every HotpotQA question.

  N  the Blueprint's path with use_knowledge_base false (rag_server/main.py _llm_chain): the system message of
     prompt.yaml's chat_template, then a user message "Query: <question>"
  O  the Blueprint's RAG path (main.py _rag_chain) with the two supporting passages of the question as its context:
     the system message of rag_template, its human message with {context}, then "Query: <question>\n\nAnswer: ".
     The context is each passage as the server formats a document (main.py _format_document_with_source with
     ENABLE_SOURCE_METADATA true: "File: <file name without extension>\nContent: <text>"), joined by a blank line; the
     file name is the passage id (the source name the bulk loader writes), the text Vol.4's passage text; the two
     passages in the order of the id table's gold_passages (sorted as strings)
  parameters  every field of the request other than the messages is copied from a request the RAG server itself sent
     (captured by capture_service.py; the file is given with --params), streaming included: the request is the
     server's, byte for byte in content. The stream is read to its end: content, reasoning (reasoning_content or
     reasoning), finish reason, and the usage chunk the server asks for (stream_options include_usage)

  final answer  the response's message.content; when it holds "</think>" (reasoning left in the content by a server
     without a reasoning parser), the text after the last "</think>". Both the raw content and the reasoning are kept.

Subcommands
  passages the supporting passages of every question (Vol.4's passage text), written once to a file kept outside
  control  our request bodies against the captured ones: N for every captured N request, O for every captured O request
           (the O capture fixes the passage order the server used; our body is built with that order)
  run      both arms, question by question in the sorted id table's order (N then O for each), with --concurrency
           requests in flight; one JSON line per answer, written as it arrives; a second run skips what is done
  tokens   adds answer and reasoning token counts to the answer files (the model's tokenizer.json)
  score    the cell's scores per arm (eval/hotpot_scoring.py) and the finish-reason counts

usage: answer_arms.py passages --ids FILE --datasets-root DIR --dataset NAME --out FILE
       answer_arms.py control --prompts FILE --params FILE --captured DIR --corpus-passages FILE --queries FILE --out FILE
       answer_arms.py run --prompts FILE --params FILE --queries FILE --ids FILE --corpus-passages FILE --url URL
                          --out-dir DIR --concurrency N [--limit N] [--arms N,O]
       answer_arms.py tokens --tokenizer FILE --out-dir DIR
       answer_arms.py score --out-dir DIR --gold FILE --out FILE
"""
import argparse, concurrent.futures as cf, glob, json, os, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
ARMS = ("N", "O")


def load_prompts(path):
    import yaml
    return yaml.safe_load(open(path, encoding="utf-8"))


def context_of(passages):
    """passages: [(passage_id, text)] in order -> the server's context string."""
    return "\n\n".join(f"File: {pid}\nContent: {text}" for pid, text in passages)


def messages(prompts, arm, question, passages=None):
    if arm == "N":
        t = prompts["chat_template"]; human = t.get("human", t.get("user", ""))
        msgs = [{"role": "system", "content": t.get("system", "")}]
        if human:
            msgs.append({"role": "user", "content": human})
        msgs.append({"role": "user", "content": f"Query: {question}"})
        return msgs
    if arm == "O":
        t = prompts["rag_template"]; human = t.get("human", t.get("user", ""))
        msgs = [{"role": "system", "content": t.get("system", "")}]
        if human:
            msgs.append({"role": "user", "content": human.replace("{context}", context_of(passages))})
        msgs.append({"role": "user", "content": f"Query: {question}\n\nAnswer: "})
        return msgs
    raise ValueError(arm)


def body(prompts, params, arm, question, passages=None):
    b = {k: v for k, v in params.items() if k != "messages"}
    b["messages"] = messages(prompts, arm, question, passages)
    return b


def read_stream(resp):
    """An OpenAI-style server-sent-event stream -> content, reasoning, finish reason, usage, chunk count."""
    content, reasoning, finish, usage, n = [], [], None, None, 0
    for raw in resp.iter_lines():
        if not raw or not raw.startswith(b"data:"):
            continue
        data = raw[5:].strip()
        if data == b"[DONE]":
            break
        j = json.loads(data); n += 1
        if j.get("usage"):
            usage = j["usage"]
        for ch in j.get("choices") or []:
            d = ch.get("delta") or {}
            if d.get("content"):
                content.append(d["content"])
            r = d.get("reasoning_content") or d.get("reasoning")
            if r:
                reasoning.append(r)
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
    return "".join(content), ("".join(reasoning) or None), finish, usage, n


def final_answer(content):
    if content is None:
        return None, "none"
    if "</think>" in content:
        return content.rsplit("</think>", 1)[1].strip(), "after_last_close_tag"
    return content.strip(), "content"


def read_queries(path):
    return {r["_id"]: r["text"] for r in (json.loads(l) for l in open(path, encoding="utf-8"))}


def read_passages(path):
    return {r["_id"]: r["text"] for r in (json.loads(l) for l in open(path, encoding="utf-8"))}


def control(a):
    prompts = load_prompts(a.prompts); queries = read_queries(a.queries); ps = read_passages(a.corpus_passages)
    params = json.load(open(a.params, encoding="utf-8")); params = params.get("body", params)
    rows = []
    for f in sorted((p for p in glob.glob(os.path.join(a.captured, "*.json")) if os.path.splitext(os.path.basename(p))[0].isdigit()), key=lambda p: int(os.path.splitext(os.path.basename(p))[0])):
        cap = json.load(open(f, encoding="utf-8")); meta = cap.get("meta") or {}
        got = cap["body"]; arm, qid = meta.get("arm"), meta.get("query_id")
        if arm is None:
            continue
        passages = [(pid, ps[pid]) for pid in meta.get("passage_order", [])] if arm == "O" else None
        mine = body(prompts, params, arm, queries[qid], passages)
        mine_msgs, got_msgs = mine["messages"], got["messages"]
        rows.append({"file": os.path.basename(f), "arm": arm, "query_id": qid, "messages_equal": mine_msgs == got_msgs, "body_equal": mine == got,
                     "first_difference": next(({"index": i, "ours": m, "server": g} for i, (m, g) in enumerate(zip(mine_msgs, got_msgs)) if m != g), None) if mine_msgs != got_msgs else None,
                     "message_count": [len(mine_msgs), len(got_msgs)], "server_fields": sorted(got)})
    fields = {tuple(r["server_fields"]) for r in rows}
    rec = {"captured_requests": len(rows), "by_arm": {x: sum(r["arm"] == x for r in rows) for x in ARMS},
           "all_messages_equal": bool(rows) and all(r["messages_equal"] for r in rows), "all_bodies_equal": bool(rows) and all(r["body_equal"] for r in rows),
           "params_file_fields": sorted(k for k in params if k != "messages"), "server_field_sets": [list(x) for x in fields], "rows": rows}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({k: rec[k] for k in ("captured_requests", "by_arm", "all_messages_equal", "all_bodies_equal")}))
    return 0 if rec["all_bodies_equal"] else 1


def records(path):
    """The JSON lines of an answer file; a last line cut by a stopped run (not valid JSON) is skipped."""
    out = []
    for l in open(path, encoding="utf-8"):
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    return out


def done_ids(path):
    if not os.path.isfile(path):
        return set()
    return {r["query_id"] for r in records(path) if r.get("status") == "ok"}


def run(a):
    import requests
    prompts = load_prompts(a.prompts); params = json.load(open(a.params, encoding="utf-8"))
    params = params.get("body", params)
    queries = read_queries(a.queries); ps = read_passages(a.corpus_passages)
    table = sorted((json.loads(l) for l in open(a.ids, encoding="utf-8")), key=lambda r: r["query_id"])
    if a.limit:
        table = table[:a.limit]
    arms = a.arms.split(","); os.makedirs(a.out_dir, exist_ok=True)
    outs = {x: os.path.join(a.out_dir, f"answers_{x}.jsonl") for x in arms}; done = {x: done_ids(outs[x]) for x in arms}
    locks = {x: threading.Lock() for x in arms}; fh = {x: open(outs[x], "a", encoding="utf-8", newline="\n") for x in arms}
    jobs = [(r, x) for r in table for x in arms if r["query_id"] not in done[x]]
    url = a.url.rstrip("/") + "/v1/chat/completions"; session = threading.local()

    def one(job):
        r, arm = job; qid = r["query_id"]
        passages = [(pid, ps[pid]) for pid in r["gold_passages"]] if arm == "O" else None
        b = body(prompts, params, arm, queries[qid], passages)
        s = getattr(session, "s", None) or requests.Session(); session.s = s
        t0 = time.time()
        try:
            resp = s.post(url, json=b, timeout=a.timeout, stream=bool(b.get("stream")))
            if resp.status_code != 200:
                rec = {"query_id": qid, "arm": arm, "status": f"http_{resp.status_code}", "error": resp.text[:2000], "t0": t0, "t1": time.time()}
            else:
                content, reasoning, finish, usage, chunks = read_stream(resp)
                ans, rule = final_answer(content)
                rec = {"query_id": qid, "arm": arm, "status": "ok", "answer": ans, "strip_rule": rule, "content": content,
                       "reasoning_content": reasoning, "finish_reason": finish, "usage": usage, "chunks": chunks, "t0": t0, "t1": time.time()}
        except Exception as e:  # recorded, the run goes on; a second run retries it
            rec = {"query_id": qid, "arm": arm, "status": "error", "error": repr(e)[:2000], "t0": t0, "t1": time.time()}
        with locks[arm]:
            fh[arm].write(json.dumps(rec, ensure_ascii=False) + "\n"); fh[arm].flush()
        return rec["status"]

    counts = {}
    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        for st in ex.map(one, jobs):
            counts[st] = counts.get(st, 0) + 1
    print(json.dumps({"jobs": len(jobs), "status": counts, "skipped_done": {x: len(done[x]) for x in arms}}))
    return 0


def passages(a):
    """The supporting passages of every question of the id table, as Vol.4's passage text, one JSON line each."""
    sys.path.insert(0, os.path.join(os.path.dirname(V5), "vol4-retriever", "scripts")); import retrieval_datasets as R
    want = {pid for r in (json.loads(l) for l in open(a.ids, encoding="utf-8")) for pid in r["gold_passages"]}
    got = {}
    for pid, title, text in R.load(a.datasets_root, a.dataset).iter_corpus():
        if str(pid) in want:
            got[str(pid)] = R.passage_text(title, text)
    if set(got) != want:
        raise SystemExit(f"refused: {len(want - set(got))} passages not in the corpus")
    with open(a.out, "w", encoding="utf-8", newline="\n") as w:
        for pid in sorted(got):
            w.write(json.dumps({"_id": pid, "text": got[pid]}, ensure_ascii=False) + "\n")
    print(json.dumps({"passages": len(got)}))
    return 0


def tokens(a):
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(a.tokenizer); n = lambda s: len(tok.encode(s or "", add_special_tokens=False).ids)
    for f in sorted(glob.glob(os.path.join(a.out_dir, "answers_*.jsonl"))):
        rows = records(f)
        for r in rows:
            if r.get("status") == "ok":
                r["answer_tokens"] = n(r["answer"]); r["reasoning_tokens_text"] = n(r.get("reasoning_content"))
                r["content_tokens"] = n(r["content"]); r["completion_tokens"] = (r.get("usage") or {}).get("completion_tokens")
        tmp = f + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as w:
            for r in rows:
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, f)
        print(os.path.basename(f), len(rows))
    return 0


def score(a):
    sys.path.insert(0, os.path.join(V5, "eval")); import hotpot_scoring as H
    gold = {r["query_id"]: r["answer"] for r in (json.loads(l) for l in open(a.gold, encoding="utf-8"))}
    out = {}
    for f in sorted(glob.glob(os.path.join(a.out_dir, "answers_*.jsonl"))):
        arm = os.path.basename(f)[len("answers_"):-len(".jsonl")]
        last = {}
        for r in records(f):
            if r["query_id"] not in last or r.get("status") == "ok":
                last[r["query_id"]] = r
        rows = [{"query_id": q, "answer": r.get("answer") if r.get("status") == "ok" else None, "gold": gold[q]} for q, r in sorted(last.items())]
        fr = {}
        for r in last.values():
            k = r.get("finish_reason") if r.get("status") == "ok" else r.get("status"); fr[k] = fr.get(k, 0) + 1
        s = H.score_answers(rows); s["finish_reason"] = fr
        s["strip_rule"] = {k: sum(1 for r in last.values() if r.get("strip_rule") == k) for k in ("content", "after_last_close_tag", "none")}
        toks = [r for r in last.values() if "answer_tokens" in r]
        if toks:
            s["tokens_mean"] = {k: sum(r[k] or 0 for r in toks) / len(toks) for k in ("answer_tokens", "reasoning_tokens_text", "completion_tokens")}
        out[arm] = s
    if set(ARMS) <= set(out):
        def best(path):
            last = {}
            for r in records(path):
                if r["query_id"] not in last or r.get("status") == "ok":
                    last[r["query_id"]] = r
            return last
        rows = {arm: [{"query_id": q, "answer": (r.get("answer") if r.get("status") == "ok" else None), "gold": gold[q]}
                      for q, r in sorted(best(os.path.join(a.out_dir, f"answers_{arm}.jsonl")).items())] for arm in ARMS}
        if {r["query_id"] for r in rows["N"]} == {r["query_id"] for r in rows["O"]}:
            out["paired_N_O"] = H.paired(rows["N"], rows["O"])
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: {x: v.get(x) for x in ("questions", "contains_rate", "finish_reason")} if k in ARMS else v for k, v in out.items()}))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("passages", "control", "run", "tokens", "score"))
    for x in ("--prompts", "--captured", "--corpus-passages", "--queries", "--out", "--params", "--ids", "--url", "--out-dir", "--tokenizer", "--gold", "--datasets-root", "--dataset"):
        ap.add_argument(x)
    ap.add_argument("--concurrency", type=int, default=1); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--arms", default="N,O"); ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()
    sys.exit({"passages": passages, "control": control, "run": run, "tokens": tokens, "score": score}[a.cmd](a))
