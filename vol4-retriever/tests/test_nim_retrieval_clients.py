"""Tests of nim_retrieval_clients.py against the stand-in server (mock_nim_server.py).

These tests show that the harness sends what it means to send and reads answers the way it means to read them. They show
nothing about a real NIM: the stand-in was written from the same published OpenAPI files as the client, so anything both
misread, both get wrong together. The first start of a real NIM settles the format."""
import os, sys, threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import mock_nim_server as mock  # noqa: E402
import nim_retrieval_clients as nc  # noqa: E402


@pytest.fixture(scope="module")
def server():
    srv = mock.serve(port=0, model="mock/model")          # port 0: the system picks a free port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_embedding_request_body():
    b = nc.embedding_request("m", ["a", "b"], "passage", truncate="END")
    assert b == {"input": ["a", "b"], "model": "m", "input_type": "passage", "truncate": "END"}
    assert nc.embedding_request("m", ["a"], "query")["truncate"] == "NONE"            # the documented default, sent explicitly


@pytest.mark.parametrize("kwargs, message", [
    (dict(input_type="document"), "input_type"), (dict(input_type="query", truncate="MIDDLE"), "truncate"),
    (dict(input_type="query", texts=[]), "1 to 8192"), (dict(input_type="query", texts=["ok", ""]), "non-empty"),
    (dict(input_type="query", prefix="x"), "not in the published schema")])
def test_embedding_request_refuses_what_the_schema_does_not_allow(kwargs, message):
    texts = kwargs.pop("texts", ["a"])
    with pytest.raises(ValueError, match=message):
        nc.embedding_request("m", texts, **kwargs)


def test_ranking_request_body():
    b = nc.ranking_request("m", "q", ["p1", "p2"], truncate="END")
    assert b == {"model": "m", "query": {"text": "q"}, "passages": [{"text": "p1"}, {"text": "p2"}], "truncate": "END"}


@pytest.mark.parametrize("args, message", [
    (("q", ["p"], "START"), "truncate"), (("", ["p"], "NONE"), "query"), (("q", [], "NONE"), "1 to 512"), (("q", ["p"] * 513, "NONE"), "1 to 512"), (("q", ["p", ""], "NONE"), "non-empty")])
def test_ranking_request_refuses_what_the_schema_does_not_allow(args, message):
    with pytest.raises(ValueError, match=message):
        nc.ranking_request("m", *args)


def test_embeddings_come_back_in_input_order_across_batches(server):
    c = nc.EmbeddingClient(server, "mock/model")
    texts = [f"passage number {i}" for i in range(10)]
    vectors, usage = c.embed(texts, "passage", batch_size=4)
    assert vectors == [mock.vector("passage", t) for t in texts]       # the stand-in answers in reverse order; the client sorts by index
    assert [x["items"] for x in c.calls] == [4, 4, 2] and all(x["status"] == 200 for x in c.calls) and len(usage) == 3


def test_query_mode_and_passage_mode_are_sent_as_asked(server):
    c = nc.EmbeddingClient(server, "mock/model")
    q, _ = c.embed(["same text"], "query"); p, _ = c.embed(["same text"], "passage")
    assert q != p and q == [mock.vector("query", "same text")] and p == [mock.vector("passage", "same text")]
    sent = [e["body"] for e in mock.LOG if e["path"] == "/v1/embeddings"][-2:]
    assert [b["input_type"] for b in sent] == ["query", "passage"] and all(set(b) == {"input", "model", "input_type", "truncate"} for b in sent)


def test_a_too_long_input_is_an_error_with_truncate_none_and_accepted_with_end(server):
    c = nc.EmbeddingClient(server, "mock/model")
    with pytest.raises(nc.NimError) as e:
        c.embed(["fine", "MOCK_TOO_LONG text"], "passage")
    assert e.value.status == 400 and c.calls[-1]["status"] == 400
    vectors, _ = c.embed(["fine", "MOCK_TOO_LONG text"], "passage", truncate="END")
    assert len(vectors) == 2


def test_rerank_returns_one_score_per_passage_in_passage_order(server):
    c = nc.RerankClient(server, "mock/model")
    passages = ["nothing in common", "which way should i go", "which way"]
    logits, _ = c.rerank("which way should i go ?", passages)
    assert logits == [0.0, 5.0, 2.0]                                   # the stand-in's rule: shared words; its answer is sorted by score
    sent = [e["body"] for e in mock.LOG if e["path"] == "/v1/ranking"][-1]
    assert sent == {"model": "mock/model", "query": {"text": "which way should i go ?"}, "passages": [{"text": p} for p in passages], "truncate": "NONE"}


def test_rerank_refuses_more_than_one_call_can_take(server):
    c = nc.RerankClient(server, "mock/model")
    before = len(c.calls)
    with pytest.raises(ValueError, match="1 to 512"):
        c.rerank("q", ["p"] * 600)
    assert len(c.calls) == before                                       # nothing was sent


def test_the_stand_in_refuses_a_request_outside_the_schema(server):
    import requests
    r = requests.post(server + "/v1/embeddings", json={"input": ["a"], "model": "m"})            # no input_type
    assert r.status_code == 422
    r = requests.post(server + "/v1/ranking", json={"model": "m", "query": "plain string", "passages": [{"text": "p"}]})
    assert r.status_code == 422
    r = requests.post(server + "/v1/ranking", json={"model": "m", "query": {"text": "q"}, "passages": [{"text": "p"}], "top_n": 3})
    assert r.status_code == 422
