"""Tests of scripts/rerank_latency.py on a small synthetic corpus and the stand-in server (mock_nim_server.py).

What they show: one call per query and pass after the discarded calls, the durations of every pass kept as numbers and
not pooled, the percentile rule, and the two refusals. What they do not show: anything about a real NIM or its timing."""
import gzip, json, os, subprocess, sys, threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import mock_nim_server as mock  # noqa: E402
import rerank_latency as rl  # noqa: E402

QUERIES = {f"{i}#0": f"question number {i}" for i in range(10, 17)}      # seven queries
PASSAGES = 60


def make_miracl(root, lang="zh"):
    t = root / f"miracl-{lang}" / "topics" / f"miracl-v1.0-{lang}"; (t / "topics").mkdir(parents=True); (t / "qrels").mkdir()
    (t / "topics" / f"topics.miracl-v1.0-{lang}-dev.tsv").write_text("".join(f"{q}\t{text}\n" for q, text in QUERIES.items()), encoding="utf-8")
    (t / "qrels" / f"qrels.miracl-v1.0-{lang}-dev.tsv").write_text("".join(f"{q} Q0 5#0 1\n" for q in QUERIES), encoding="utf-8")
    c = root / f"miracl-{lang}" / "corpus" / f"miracl-corpus-v1.0-{lang}"; c.mkdir(parents=True)
    with gzip.open(c / "docs-0.jsonl.gz", "wt", encoding="utf-8") as f:
        for i in range(PASSAGES):
            f.write(json.dumps({"docid": f"{i}#0", "title": f"Title {i}", "text": f"synthetic passage number {i}"}) + "\n")


def make_run(path, per_query=12, missing=False):
    with open(path, "w", encoding="utf-8") as f:
        for q in QUERIES:
            for r in range(per_query):
                pid = "9999#0" if missing and r == 0 else f"{r * 3}#0"
                f.write(f"{q} Q0 {pid} {r + 1} {1.0 - r / 100:.6f} first\n")


@pytest.fixture()
def server():
    srv = mock.serve(port=0, model="mock/rerank")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    mock.LOG.clear()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def call(root, run_file, out, url, *extra):
    cmd = [sys.executable, os.path.join(SCRIPTS, "rerank_latency.py"), "--where", "host", "--dataset", "miracl-zh", "--datasets", str(root), "--run-in", str(run_file),
           "--url", url, "--model", "mock/rerank", "--out", str(out), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def test_nearest_rank():
    v = list(range(1, 101))
    assert rl.nearest_rank(v, 50) == 50 and rl.nearest_rank(v, 99) == 99 and rl.nearest_rank(v, 100) == 100
    assert rl.nearest_rank([5.0], 99) == 5.0
    assert rl.nearest_rank(list(range(1, 394)), 99) == 390           # 393 calls: position ceil(389.07)
    assert rl.nearest_rank([3, 1, 2], 50) == 2                        # sorted first
    s = rl.summary([4.0, 1.0, 3.0, 2.0])
    assert s == {"calls": 4, "p50": 2.0, "p90": 4.0, "p99": 4.0, "min": 1.0, "max": 4.0, "mean": 2.5}


def test_one_call_per_query_and_pass(tmp_path, server):
    make_miracl(tmp_path); make_run(tmp_path / "run.trec")
    r = call(tmp_path, tmp_path / "run.trec", tmp_path / "out.json", server, "--depth", "10", "--passes", "3")
    assert r.returncode == 0, r.stderr
    d = json.load(open(tmp_path / "out.json", encoding="utf-8"))
    assert d["queries"] == 7 and d["depth"] == 10 and len(d["passes"]) == 3 and d["where"] == "host"
    for p in d["passes"]:
        assert p["call_ms"]["calls"] == 7 and len(p["call_ms_all"]) == 7 and p["pairs"] == 70
        assert p["passages_per_call"] == {"min": 10, "max": 10}
        assert all(isinstance(x, float) and x > 0 for x in p["call_ms_all"])
        assert p["call_ms"]["min"] <= p["call_ms"]["p50"] <= p["call_ms"]["p90"] <= p["call_ms"]["p99"] <= p["call_ms"]["max"]
    ranking = [x for x in mock.LOG if "passages" in json.dumps(x)]
    assert len(ranking) == 4 + 3 * 7                                   # four discarded calls, then seven per pass
    text = open(tmp_path / "out.json", encoding="utf-8").read()
    assert "synthetic passage" not in text and "question number" not in text and "#0" not in text


def test_an_existing_result_is_not_overwritten(tmp_path, server):
    make_miracl(tmp_path); make_run(tmp_path / "run.trec"); (tmp_path / "out.json").write_text("{}", encoding="utf-8")
    r = call(tmp_path, tmp_path / "run.trec", tmp_path / "out.json", server)
    assert r.returncode != 0 and "exists" in r.stderr and (tmp_path / "out.json").read_text(encoding="utf-8") == "{}"


def test_a_passage_that_is_not_in_the_corpus_is_refused(tmp_path, server):
    make_miracl(tmp_path); make_run(tmp_path / "run.trec", missing=True)
    r = call(tmp_path, tmp_path / "run.trec", tmp_path / "out.json", server, "--depth", "10")
    assert r.returncode != 0 and "not in the corpus" in r.stderr and not os.path.exists(tmp_path / "out.json")
