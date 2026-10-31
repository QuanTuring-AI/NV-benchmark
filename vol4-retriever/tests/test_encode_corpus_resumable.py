"""Tests of encode_corpus_resumable.py on a small synthetic corpus and the stand-in server (mock_nim_server.py).

What they show: the pieces cover the corpus once, in file order, whatever the number of calls and stops; a piece that
was changed on disk is refused; a call with other arguments than the first is refused. What they do not show: anything
about a real NIM (the first call against a real NIM in a session is run with a small --limit and compared with
embed_cell.py's vectors of the same passages)."""
import gzip, json, os, subprocess, sys, threading, time

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import mock_nim_server as mock  # noqa: E402
import retrieval_datasets as ds  # noqa: E402

N = 2500   # passages of the synthetic corpus


def make_miracl(root, lang="zh"):
    t = root / f"miracl-{lang}" / "topics" / f"miracl-v1.0-{lang}"; (t / "topics").mkdir(parents=True); (t / "qrels").mkdir()
    (t / "topics" / f"topics.miracl-v1.0-{lang}-dev.tsv").write_text("10#0\tfirst question\n11#0\tsecond question\n", encoding="utf-8")
    (t / "qrels" / f"qrels.miracl-v1.0-{lang}-dev.tsv").write_text("10#0 Q0 5#0 1\n11#0 Q0 7#0 1\n", encoding="utf-8")
    c = root / f"miracl-{lang}" / "corpus" / f"miracl-corpus-v1.0-{lang}"; c.mkdir(parents=True)
    per = N // 5
    for n in range(5):
        with gzip.open(c / f"docs-{n}.jsonl.gz", "wt", encoding="utf-8") as f:
            for i in range(n * per, (n + 1) * per):
                f.write(json.dumps({"docid": f"{i}#0", "title": f"Title {i}" if i % 3 else "", "text": f"synthetic passage number {i}"}) + "\n")


@pytest.fixture(scope="module")
def server():
    srv = mock.serve(port=0, model="mock/model")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def run(root, out, url, *extra):
    cmd = [sys.executable, os.path.join(SCRIPTS, "encode_corpus_resumable.py"), "--dataset", "miracl-zh", "--datasets", str(root), "--url", url, "--model", "mock/model",
           "--emb-dir", str(out / "vectors"), "--checkpoints", str(out / "checkpoints.jsonl"), "--piece", "1000", "--batch", "16", *extra]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def lines(out):
    return [json.loads(l) for l in open(out / "checkpoints.jsonl", encoding="utf-8")]


def gathered(out):
    cps = [c for c in lines(out) if c["kind"] == "piece"]
    ids = [x for c in cps for x in json.load(open(out / "vectors" / c["ids_file"], encoding="utf-8"))]
    v = np.concatenate([np.load(out / "vectors" / c["vectors_file"]) for c in cps], axis=0)
    return cps, ids, v


def expected(root):
    d = ds.load(str(root), "miracl-zh")
    ids, v = [], []
    for pid, title, text in d.iter_corpus():
        ids.append(pid); v.append(mock.vector("passage", ds.passage_text(title, text)))
    return ids, np.asarray(v, dtype=np.float32)


def test_one_call_covers_the_corpus_once_in_file_order(tmp_path, server):
    make_miracl(tmp_path); out = tmp_path / "a"; out.mkdir()
    r = run(tmp_path, out, server)
    assert r.returncode == 0, r.stderr
    cps, ids, v = gathered(out)
    want_ids, want_v = expected(tmp_path)
    assert [c["passages"] for c in cps] == [1000, 1000, 500]
    assert ids == want_ids and np.array_equal(v, want_v)
    assert lines(out)[-1]["kind"] == "finished" and lines(out)[-1]["passages"] == N
    q = np.load(out / "vectors" / "queries.npy")
    assert q.shape[0] == 2 and np.allclose(q[0], mock.vector("query", "first question"))
    again = run(tmp_path, out, server)                                  # a finished corpus is not encoded twice
    assert again.returncode == 0 and "nothing to do" in again.stdout


def test_a_stop_and_two_later_calls_give_the_same_vectors(tmp_path, server):
    make_miracl(tmp_path); out = tmp_path / "b"; out.mkdir()
    past = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(time.time() - 60))
    r1 = run(tmp_path, out, server, "--stop-at", past)                   # stops at the first look at the clock
    assert r1.returncode == 0, r1.stderr
    first = lines(out)
    assert first[-1]["kind"] == "stopped" and 0 < first[-1]["passages_done"] < 1000
    r2 = run(tmp_path, out, server, "--stop-at", past)                   # goes on from there, stops again
    assert r2.returncode == 0 and lines(out)[-1]["passages_done"] == 2 * first[-1]["passages_done"]
    r3 = run(tmp_path, out, server)                                      # no stop time: to the end
    assert r3.returncode == 0, r3.stderr
    cps, ids, v = gathered(out)
    want_ids, want_v = expected(tmp_path)
    assert ids == want_ids and np.array_equal(v, want_v)
    assert sum(c["passages"] for c in cps) == N and [c["first"] for c in cps] == list(np.cumsum([0] + [c["passages"] for c in cps[:-1]]))
    assert sum(1 for c in lines(out) if c["kind"] == "queries") == 1     # the queries are encoded once


def test_a_changed_piece_is_refused(tmp_path, server):
    make_miracl(tmp_path); out = tmp_path / "c"; out.mkdir()
    assert run(tmp_path, out, server, "--limit", "1500").returncode == 0
    cps = [c for c in lines(out) if c["kind"] == "piece"]
    assert lines(out)[-1]["note"].startswith("--limit was set")
    # make the record unfinished again, then change one stored piece
    kept = [l for l in open(out / "checkpoints.jsonl", encoding="utf-8") if '"kind": "finished"' not in l]
    open(out / "checkpoints.jsonl", "w", encoding="utf-8", newline="\n").writelines(kept)
    p = out / "vectors" / cps[0]["vectors_file"]
    v = np.load(p); v[0, 0] += 1.0; np.save(p, v)
    r = run(tmp_path, out, server, "--limit", "1500")
    assert r.returncode != 0 and "does not have the recorded SHA-256" in (r.stderr + r.stdout)


def test_other_arguments_than_the_first_call_are_refused(tmp_path, server):
    make_miracl(tmp_path); out = tmp_path / "d"; out.mkdir()
    past = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(time.time() - 60))
    assert run(tmp_path, out, server, "--stop-at", past).returncode == 0
    r = run(tmp_path, out, server, "--truncate", "NONE")
    assert r.returncode != 0 and "refused" in (r.stderr + r.stdout)


def test_a_stop_time_without_an_offset_is_refused(tmp_path, server):
    make_miracl(tmp_path); out = tmp_path / "e"; out.mkdir()
    r = run(tmp_path, out, server, "--stop-at", "2026-10-05T08:00:00")
    assert r.returncode != 0 and "UTC offset" in (r.stderr + r.stdout)


def test_a_stop_time_in_the_future_does_not_stop(tmp_path, server):
    make_miracl(tmp_path); out = tmp_path / "f"; out.mkdir()
    future = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(time.time() + 3600))
    r = run(tmp_path, out, server, "--stop-at", future)
    assert r.returncode == 0 and lines(out)[-1]["kind"] == "finished"
    east = (__import__("datetime").datetime.now(__import__("datetime").timezone(__import__("datetime").timedelta(hours=8))) - __import__("datetime").timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S%z")
    out2 = tmp_path / "g"; out2.mkdir()
    r2 = run(tmp_path, out2, server, "--stop-at", east)                  # one minute ago, written with +0800: stops
    assert r2.returncode == 0 and lines(out2)[-1]["kind"] == "stopped"
