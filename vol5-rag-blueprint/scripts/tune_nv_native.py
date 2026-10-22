#!/usr/bin/env python3
"""Vol.5 · the NV-native tuning runs: the Blueprint's own rag-server, one configuration at a time, the retrieval layer
only (no answer is generated).

For each question the program sends POST <rag-server>/v1/search with the configuration's request fields and keeps the
ids of the passages it returns, in order: that is the ranking sent to the answer model, and nDCG@10 is scored on it.
What the vector store returned before reranking is not in that answer, so the reranking NIM is reached through a
forwarding proxy (subcommand `proxy`) that logs, per ranking request, the query and a SHA-1 of each passage text in
the order the rag-server sent them (the retrieval order, in the server's batches). Recall@100 is scored on the first
100 of that list, after mapping each SHA-1 back to a passage id (subcommand `text-index`). Nothing of a passage's text
is written: only ids and hashes.

Subcommands
  proxy       --listen PORT --target URL --log FILE      forward POST /v1/ranking (and every GET) to the reranker
  run         --server URL --config FILE --config-id N --queries FILE --sample FILE --out FILE [--proxy-log FILE]
              one JSON line per question: id, the returned ids, the request, latency; resumable
  text-index  --passages FILE --out FILE                 SHA-1 of the text as stored -> passage id, for the candidates
  score       --runs FILE --qrels FILE --out FILE [--proxy-log FILE --text-index FILE]
              nDCG@10 of the returned ranking and Recall@100 of the candidates, per configuration, with n

The configuration file is the table of the pre-registration: {"configurations": [{"id": 1, "env": {...},
"request": {...}}, ...]}. `env` is applied when the rag-server is started (by the driver, not here); `run` checks the
server's GET /v1/configuration against it before the first question and refuses on a difference it can see.
Questions are sent one at a time, so the proxy lines written between two questions belong to the first.
"""
import argparse, hashlib, http.server, json, math, os, sys, threading, time, urllib.error, urllib.request

SEARCH_FIELDS = ("vdb_top_k", "reranker_top_k", "enable_reranker", "enable_query_rewriting", "confidence_threshold")


def sha1(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def post(url, body, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


# ---------------------------------------------------------------- proxy
def make_proxy(target, log_path):
    lock = threading.Lock()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status, body, ctype="application/json"):
            self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            try:
                with urllib.request.urlopen(target + self.path, timeout=60) as r:
                    self._send(r.status, r.read(), r.headers.get("Content-Type", "application/json"))
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read())

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                body = json.loads(raw)
                rec = {"at": time.time(), "path": self.path, "query": sha1((body.get("query") or {}).get("text", "")),
                       "passages": [sha1(p.get("text", "")) for p in body.get("passages", [])]}
            except (ValueError, AttributeError):
                rec = {"at": time.time(), "path": self.path, "unparsed": True}
            req = urllib.request.Request(target + self.path, data=raw, headers={"Content-Type": self.headers.get("Content-Type", "application/json")})
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    status, out = r.status, r.read()
            except urllib.error.HTTPError as e:
                status, out = e.code, e.read()
            rec["status"] = status
            with lock:
                with open(log_path, "a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(rec) + "\n")
            self._send(status, out)
    return H


def cmd_proxy(a):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", int(a.listen)), make_proxy(a.target.rstrip("/"), a.log))
    print(json.dumps({"proxy": f"127.0.0.1:{a.listen}", "target": a.target, "log": a.log}), flush=True)
    srv.serve_forever()


# ---------------------------------------------------------------- run
def load_config(path, cid):
    table = json.load(open(path, encoding="utf-8"))["configurations"]
    hit = [c for c in table if c["id"] == cid]
    if len(hit) != 1:
        raise SystemExit(f"refused: configuration {cid} is not in the table exactly once")
    bad = set(hit[0].get("request", {})) - set(SEARCH_FIELDS)
    if bad:
        raise SystemExit(f"refused: request fields outside /v1/search: {sorted(bad)}")
    return hit[0]


def server_differs(server, cfg):
    """The env settings the server reports back that differ from the table; [] when it reports none of them."""
    try:
        with urllib.request.urlopen(server.rstrip("/") + "/v1/configuration", timeout=30) as r:
            conf = json.loads(r.read())
    except Exception:
        return []
    flat = {}

    def walk(o, pre=""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, pre + k + ".")
        else:
            flat[pre[:-1].split(".")[-1].lower()] = o
    walk(conf)
    out = []
    for k, v in cfg.get("env_reported_as", {}).items():
        if k.lower() in flat and str(flat[k.lower()]).lower() != str(v).lower():
            out.append({"field": k, "server": flat[k.lower()], "table": v})
    return out


def returned_ids(resp):
    ids = []
    for r in resp.get("results", []):
        name = os.path.basename(r.get("document_name") or "")
        ids.append(name[:-4] if name.endswith(".txt") else name)
    return ids


def cmd_run(a):
    cfg = load_config(a.config, int(a.config_id))
    diff = server_differs(a.server, cfg)
    if diff:
        raise SystemExit(f"refused: the server's configuration differs from the table: {diff}")
    queries = {json.loads(l)["_id"]: json.loads(l)["text"] for l in open(a.queries, encoding="utf-8")}
    sample = json.load(open(a.sample, encoding="utf-8"))["ids"]
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["query_id"] for l in open(a.out, encoding="utf-8") if l.strip() and json.loads(l).get("status") == 200}
    url = a.server.rstrip("/") + "/v1/search"
    for q in sample:
        if q in done:
            continue
        body = {"query": queries[q], "messages": [{"role": "user", "content": queries[q]}], **cfg.get("request", {})}
        t0 = time.perf_counter(); rec = {"query_id": q, "config_id": cfg["id"], "at": time.time()}
        if a.proxy_log:
            rec["proxy_lines_before"] = sum(1 for _ in open(a.proxy_log, encoding="utf-8")) if os.path.exists(a.proxy_log) else 0
        try:
            status, raw = post(url, body)
            rec.update(status=status, returned=returned_ids(json.loads(raw)))
        except urllib.error.HTTPError as e:
            rec.update(status=e.code, error=e.read()[:300].decode("utf-8", "replace"))
        except Exception as e:
            rec.update(status=0, error=str(e)[:300])
        rec["ms"] = (time.perf_counter() - t0) * 1000
        if a.proxy_log:
            rec["proxy_lines_after"] = sum(1 for _ in open(a.proxy_log, encoding="utf-8")) if os.path.exists(a.proxy_log) else 0
        with open(a.out, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec) + "\n")
    print(json.dumps({"config": cfg["id"], "questions": len(sample), "written": a.out}))


# ---------------------------------------------------------------- text index
def cmd_text_index(a):
    idx = {}
    for l in open(a.passages, encoding="utf-8"):
        r = json.loads(l)
        idx[sha1(r["text"])] = str(r["id"])
    json.dump(idx, open(a.out, "w", encoding="utf-8", newline="\n"))
    print(json.dumps({"passages": len(idx), "out": a.out}))


# ---------------------------------------------------------------- score
def ndcg_at(ranked, rel, k=10):
    dcg = sum(1.0 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if rel.get(d, 0) > 0)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(k, sum(1 for v in rel.values() if v > 0))))
    return dcg / ideal if ideal else 0.0


def recall_at(cands, rel, k=100):
    pos = {d for d, v in rel.items() if v > 0}
    return len(pos & set(cands[:k])) / len(pos) if pos else 0.0


def candidates_by_question(runs, proxy_lines, index):
    """The proxy lines written while a question was being answered, in order, flattened into one candidate list."""
    out = {}
    for r in runs:
        if "proxy_lines_before" not in r:
            continue
        seq = []
        for p in proxy_lines[r["proxy_lines_before"]:r["proxy_lines_after"]]:
            seq += [index.get(h) for h in p.get("passages", [])]
        out[r["query_id"]] = seq
    return out


def score(runs, qrels, proxy_lines=None, index=None):
    ok = [r for r in runs if r.get("status") == 200]
    n = [ndcg_at(r["returned"], qrels.get(r["query_id"], {})) for r in ok]
    rec = {"questions": len(runs), "answered": len(ok), "failed": len(runs) - len(ok),
           "ndcg_cut_10": sum(n) / len(runs) if runs else None,
           "ms_p50": sorted(r["ms"] for r in ok)[len(ok) // 2] if ok else None}
    if proxy_lines is not None:
        c = candidates_by_question(ok, proxy_lines, index)
        unmapped = sum(1 for s in c.values() for x in s if x is None)
        rec["recall_100"] = sum(recall_at(c.get(r["query_id"], []), qrels.get(r["query_id"], {})) for r in ok) / len(runs) if runs else None
        rec["candidates_seen_for"] = len(c); rec["candidate_hashes_not_in_the_index"] = unmapped
    return rec


def cmd_score(a):
    runs = [json.loads(l) for l in open(a.runs, encoding="utf-8") if l.strip()]
    last = {}
    for r in runs:
        if r["query_id"] not in last or r.get("status") == 200:
            last[r["query_id"]] = r
    qrels = {}
    for l in open(a.qrels, encoding="utf-8"):
        if l.strip() and not l.startswith("query-id"):
            q, d, s = l.split()[:3]
            qrels.setdefault(q, {})[d] = int(s)
    pl = [json.loads(l) for l in open(a.proxy_log, encoding="utf-8")] if a.proxy_log else None
    idx = json.load(open(a.text_index, encoding="utf-8")) if a.text_index else None
    rec = score(list(last.values()), qrels, pl, idx)
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(rec))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("proxy", "run", "text-index", "score"))
    for x in ("--listen", "--target", "--log", "--server", "--config", "--config-id", "--queries", "--sample", "--out",
              "--proxy-log", "--passages", "--runs", "--qrels", "--text-index"):
        ap.add_argument(x)
    a = ap.parse_args()
    {"proxy": cmd_proxy, "run": cmd_run, "text-index": cmd_text_index, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
