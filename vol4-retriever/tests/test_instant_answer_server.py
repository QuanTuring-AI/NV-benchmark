"""instant_answer_server.py: the prepared bodies have the asked size and the right shape, and the server reads a whole
request before it answers, on a kept connection. A local socket; no model and no card."""
import asyncio, http.client, json, os, sys, threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import instant_answer_server as I  # noqa: E402

TARGETS = {"query": 39780, "passage": 2538700, "passages_100": 3400, "passages_10": 390}


def test_bodies_have_the_asked_size_and_shape():
    answers, rec = I.table(TARGETS)
    for shape, target in TARGETS.items():
        assert abs(rec[shape]["body_bytes"] - target) <= 0.03 * target, (shape, rec[shape])
        head, body = answers["/shape/" + shape].split(b"\r\n\r\n", 1)
        assert f"Content-Length: {len(body)}".encode() in head and len(body) == rec[shape]["body_bytes"]
        d = json.loads(body); kind, count = I.SHAPES[shape]
        if kind == "embedding":
            assert len(d["data"]) == count and all(len(x["embedding"]) == 2048 for x in d["data"]) and [x["index"] for x in d["data"]] == list(range(count))
        else:
            assert len(d["rankings"]) == count and set(d["rankings"][0]) == {"index", "logit"}


def test_more_decimals_make_a_longer_body_and_the_nearest_is_taken():
    a, b = I.embedding_body(1, 6), I.embedding_body(1, 12)
    assert len(a) < len(b)
    body, digits = I.body_of_about("query", len(a))
    assert digits == 6 and body == a
    assert I.embedding_body(1, 6) == a                                    # the same bytes on every call


def test_targets_are_checked():
    assert I.parse_targets("query=10,passages_10=20") == {"query": 10, "passages_10": 20}
    for bad in ("queries=10", "query=10,passage=20", "passages_100=5,passages_10=5"):            # an unknown shape; two shapes for one NIM path
        try:
            I.parse_targets(bad); raise AssertionError(bad + " was accepted")
        except SystemExit:
            pass


def run_server(answers):
    loop = asyncio.new_event_loop(); box = {}

    def go():
        asyncio.set_event_loop(loop)
        box["server"] = loop.run_until_complete(I.serve(answers, 0, host="127.0.0.1")); box["port"] = box["server"].sockets[0].getsockname()[1]; ready.set()
        loop.run_forever()
    ready = threading.Event(); t = threading.Thread(target=go, daemon=True); t.start(); assert ready.wait(10)
    return loop, box


async def _shut(server):
    server.close(); await server.wait_closed()


def test_the_server_answers_each_path_on_a_kept_connection():
    answers, rec = I.table({"query": 30000, "passages_10": 390})
    loop, box = run_server(answers)
    try:
        c = http.client.HTTPConnection("127.0.0.1", box["port"], timeout=10)
        for path, shape in (("/shape/query", "query"), ("/shape/passages_10", "passages_10"), ("/shape/query?x=1", "query"), ("/v1/embeddings", "query"), ("/v1/ranking", "passages_10")):
            c.request("POST", path, body=b"x" * 70000, headers={"Content-Type": "application/json"})          # a request longer than one read
            r = c.getresponse(); body = r.read()
            assert r.status == 200 and len(body) == rec[shape]["body_bytes"] and json.loads(body)
        c.request("POST", "/shape/passage", body=b"{}"); r = c.getresponse(); r.read(); assert r.status == 404      # a shape this server was not given
        c.request("GET", "/v1/health/ready"); r = c.getresponse(); assert r.status == 200 and json.loads(r.read())["message"] == "Service is ready."
        c.request("GET", "/other"); r = c.getresponse(); r.read(); assert r.status == 404
        c.close()
    finally:
        asyncio.run_coroutine_threadsafe(_shut(box["server"]), loop).result(10); loop.call_soon_threadsafe(loop.stop)
