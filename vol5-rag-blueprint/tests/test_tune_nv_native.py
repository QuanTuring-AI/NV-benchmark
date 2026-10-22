"""Vol.5 · tune_nv_native.py against a stand-in rag-server and a stand-in reranker on 12 synthetic passages and 4
synthetic questions (no HotpotQA data). The stand-in server sends its candidates to the reranker through the proxy,
as the Blueprint does, and returns the reranked top k with document_name '<id>.txt'."""
import http.server, json, os, socket, sys, threading, urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import tune_nv_native as T  # noqa: E402

PASSAGES = {str(i): f"synthetic passage number {i}" for i in range(12)}
QUESTIONS = {"q1": "first", "q2": "second", "q3": "third", "q4": "fourth"}
# the stand-in vector store returns the passages rotated by a per-question offset; the reranker reverses its input
OFFSET = {"first": 0, "second": 4, "third": 8, "fourth": 2}


def order(question):
    k = OFFSET[question]; return [str((i + k) % 12) for i in range(12)]
QRELS = {"q1": {"0": 1, "1": 1}, "q2": {"11": 1}, "q3": {"5": 1, "6": 1}, "q4": {"99": 1}}


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def serve(handler):
    port = free_port(); srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv, f"http://127.0.0.1:{port}"


class Reranker(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        n = len(body["passages"]); out = json.dumps({"rankings": [{"index": n - 1 - i, "logit": float(-i)} for i in range(n)]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


def make_server(rerank_url, reported):
    class Server(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj):
            out = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

        def do_GET(self):
            self._json({"vector_store": {"search_type": reported}})

        def do_POST(self):
            b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            cands = order(b["query"])[:b.get("vdb_top_k", 100)]
            if b.get("enable_reranker", True):
                for s in range(0, len(cands), 5):  # batches, as the Blueprint sends them
                    batch = cands[s:s + 5]
                    req = urllib.request.Request(rerank_url + "/v1/ranking", data=json.dumps({"query": {"text": b["query"]}, "passages": [{"text": PASSAGES[c]} for c in batch]}).encode(),
                                                 headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req).read()
                ranked = list(reversed(cands))
            else:
                ranked = cands
            self._json({"total_results": len(ranked), "results": [{"document_name": f"/tmp/x/{c}.txt"} for c in ranked[:b.get("reranker_top_k", 10)]]})
    return Server


@pytest.fixture
def setup(tmp_path):
    rr, rr_url = serve(Reranker)
    log = tmp_path / "proxy.jsonl"
    px, px_url = serve(T.make_proxy(rr_url, str(log)))
    sv, sv_url = serve(make_server(px_url, "dense"))
    (tmp_path / "q.jsonl").write_text("".join(json.dumps({"_id": k, "text": v}) + "\n" for k, v in QUESTIONS.items()))
    (tmp_path / "s.json").write_text(json.dumps({"ids": list(QUESTIONS)}))
    (tmp_path / "c.json").write_text(json.dumps({"configurations": [
        {"id": 1, "env_reported_as": {"search_type": "dense"}, "request": {"vdb_top_k": 8, "reranker_top_k": 3}},
        {"id": 2, "env_reported_as": {"search_type": "hybrid"}, "request": {"vdb_top_k": 8}},
        {"id": 3, "request": {"vdb_top_k": 8, "search_type": "hybrid"}}]}))
    (tmp_path / "p.jsonl").write_text("".join(json.dumps({"id": k, "text": v}) + "\n" for k, v in PASSAGES.items()))
    (tmp_path / "qrels.tsv").write_text("query-id\tcorpus-id\tscore\n" + "".join(f"{q}\t{d}\t{s}\n" for q, r in QRELS.items() for d, s in r.items()))
    yield tmp_path, sv_url, str(log)
    for s in (rr, px, sv):
        s.shutdown()


class A:
    def __init__(self, **k):
        self.__dict__.update({x: None for x in ("listen", "target", "log", "server", "config", "config_id", "queries", "sample", "out", "proxy_log", "passages", "runs", "qrels", "text_index")}); self.__dict__.update(k)


def run_and_score(t, url, log, cid=1):
    T.cmd_run(A(server=url, config=str(t / "c.json"), config_id=str(cid), queries=str(t / "q.jsonl"), sample=str(t / "s.json"), out=str(t / "runs.jsonl"), proxy_log=log))
    T.cmd_text_index(A(passages=str(t / "p.jsonl"), out=str(t / "idx.json")))
    T.cmd_score(A(runs=str(t / "runs.jsonl"), qrels=str(t / "qrels.tsv"), out=str(t / "score.json"), proxy_log=log, text_index=str(t / "idx.json")))
    return json.load(open(t / "score.json"))


def test_end_to_end_ndcg_and_recall(setup):
    t, url, log = setup
    s = run_and_score(t, url, log)
    # candidates (first 8 of the rotation): q1 0-7, q2 4-11, q3 8-11 and 0-3, q4 2-9; returned = their last 3, reversed
    # nDCG@10: only q2 has its relevant passage (11) returned, at rank 1 -> 1/4
    assert s["answered"] == 4 and abs(s["ndcg_cut_10"] - 0.25) < 1e-12
    # Recall@100: q1 1.0 (0, 1), q2 1.0 (11), q3 0 (5, 6 not among its 8), q4 0
    assert abs(s["recall_100"] - 0.5) < 1e-12 and s["candidate_hashes_not_in_the_index"] == 0 and s["candidates_seen_for"] == 4


def test_resume_skips_answered_questions(setup):
    t, url, log = setup
    run_and_score(t, url, log); run_and_score(t, url, log)
    assert sum(1 for _ in open(t / "runs.jsonl")) == 4


def test_refuses_a_server_that_reports_another_setting(setup):
    t, url, log = setup
    with pytest.raises(SystemExit, match="differs"):
        T.cmd_run(A(server=url, config=str(t / "c.json"), config_id="2", queries=str(t / "q.jsonl"), sample=str(t / "s.json"), out=str(t / "r2.jsonl"), proxy_log=log))


def test_refuses_a_request_field_search_does_not_take(setup):
    t, url, log = setup
    with pytest.raises(SystemExit, match="outside /v1/search"):
        T.load_config(str(t / "c.json"), 3)


def test_ndcg_and_recall_by_hand():
    assert T.ndcg_at(["a", "x", "b"], {"a": 1, "b": 1}) == pytest.approx((1 + 1 / 2) / (1 + 1 / __import__("math").log2(3)))
    assert T.ndcg_at(["x"] * 10 + ["a"], {"a": 1}) == 0.0
    assert T.recall_at(["a"] + ["x"] * 99 + ["b"], {"a": 1, "b": 1}) == 0.5


def test_proxy_logs_passages_in_the_order_sent(tmp_path):
    rr, rr_url = serve(Reranker); log = tmp_path / "p.jsonl"
    px, px_url = serve(T.make_proxy(rr_url, str(log)))
    texts = ["alpha", "beta", "gamma"]
    req = urllib.request.Request(px_url + "/v1/ranking", data=json.dumps({"query": {"text": "q"}, "passages": [{"text": x} for x in texts]}).encode(),
                                 headers={"Content-Type": "application/json"})
    assert urllib.request.urlopen(req).status == 200
    rec = json.loads(open(log).readline())
    assert rec["passages"] == [T.sha1(x) for x in texts] and rec["status"] == 200
    for s in (rr, px):
        s.shutdown()
