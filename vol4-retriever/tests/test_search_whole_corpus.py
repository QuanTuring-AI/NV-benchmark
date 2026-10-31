"""Tests of scripts/search_whole_corpus.py: the search over pieces against a search over everything at once, the rule for
equal scores, the refusal of a stored file that differs from its record, and going on after a stop."""
import hashlib, json, os, sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import search_whole_corpus as sw  # noqa: E402


def vectors(queries=7, passages=1037, size=16, seed=3):
    r = np.random.default_rng(seed)
    return r.standard_normal((queries, size)).astype(np.float32), r.standard_normal((passages, size)).astype(np.float32)


def cut(passages, rows):
    return [(None, None, None, None, min(rows, passages - s)) for s in range(0, passages, rows)]


def run(q, p, rows, top, state, stop_after=None, judged=(), only=None):
    qu, _, _ = sw.unit(q); ids = [f"d{i}" for i in range(p.shape[0])]
    pieces = cut(p.shape[0], rows)

    def read_piece(k):
        return p[k * rows:k * rows + pieces[k][4]], ids[k * rows:k * rows + pieces[k][4]]
    return sw.search_pieces(qu, pieces, read_piece, top, set(judged), state, "key", stop_after=stop_after, only=only)


def everything_at_once(q, p, rows, top):
    """The same products as the pieces give (computed piece by piece), ranked over the whole corpus in one step."""
    qu, _, _ = sw.unit(q)
    sc = np.concatenate([sw.piece_scores(qu, sw.unit(p[s:s + rows])[0]) for s in range(0, p.shape[0], rows)], axis=1)
    idx = np.stack([np.lexsort((np.arange(sc.shape[1]), -sc[i]))[:top] for i in range(sc.shape[0])])
    return np.take_along_axis(sc, idx, axis=1), idx


@pytest.mark.parametrize("rows,top", [(100, 100), (333, 100), (1037, 100), (50, 100), (64, 10), (1, 5), (2000, 100)])
def test_pieces_give_the_ranking_of_the_whole(tmp_path, rows, top):
    q, p = vectors()
    finished, val, idx, ids_of, _seen, _n = run(q, p, rows, top, str(tmp_path / "s.npz"))
    want_val, want_idx = everything_at_once(q, p, rows, top)
    assert finished and idx.shape == want_idx.shape
    assert (idx == want_idx).all() and (val == want_val).all()
    assert set(ids_of) == set(int(g) for g in np.unique(idx)) and all(ids_of[g] == f"d{g}" for g in ids_of)


def test_the_score_is_the_cosine(tmp_path):
    """Against a cosine written out here in float64, with vectors of very different lengths."""
    q, p = vectors(passages=500)
    p = p * np.linspace(0.01, 50, 500, dtype=np.float32)[:, None]; q = q * np.float32(7)
    _f, val, idx, _i, _s, norms = run(q, p, 120, 20, str(tmp_path / "s.npz"))
    q64, p64 = q.astype(np.float64), p.astype(np.float64)
    cos = (q64 @ p64.T) / np.linalg.norm(q64, axis=1)[:, None] / np.linalg.norm(p64, axis=1)[None, :]
    assert (idx[:, 0] == cos.argmax(axis=1)).all()
    assert np.abs(val - np.take_along_axis(cos, idx, axis=1)).max() < 1e-5
    assert norms[0] < 1.0 < norms[1]                                             # lengths as stored, before dividing


@pytest.mark.parametrize("rows,top", [(100, 100), (37, 20), (1037, 100)])
def test_a_search_over_some_ids_is_the_search_over_those_passages(tmp_path, rows, top):
    """Leaving passages out by id gives what a corpus made of the others gives, with the passage numbers of the whole."""
    q, p = vectors()
    r = np.random.default_rng(5); kept = np.sort(r.choice(p.shape[0], size=311, replace=False))
    kept = kept[(kept < 400) | (kept >= 500)]                                    # with pieces of 100, one piece keeps nothing
    only = {f"d{i}" for i in kept.tolist()} | {"not in the corpus"}
    finished, val, idx, ids_of, seen, _n = run(q, p, rows, top, str(tmp_path / "s.npz"), only=only)
    qu, _, _ = sw.unit(q)
    parts = []
    for s in range(0, p.shape[0], rows):
        local = [i - s for i in kept.tolist() if s <= i < s + rows]
        if local:
            parts.append(sw.piece_scores(qu, sw.unit(p[s:s + rows][local])[0]))
    sc = np.concatenate(parts, axis=1)
    order = np.stack([np.lexsort((kept, -sc[i]))[:top] for i in range(sc.shape[0])])
    assert finished and (idx == kept[order]).all() and (val == np.take_along_axis(sc, order, axis=1)).all()
    assert seen == {f"d{i}" for i in kept.tolist()} and all(ids_of[g] == f"d{g}" for g in ids_of)
    assert set(idx.ravel().tolist()) <= set(kept.tolist())


def test_more_results_asked_than_passages(tmp_path):
    q, p = vectors(passages=30)
    _f, val, idx, _i, _s, _n = run(q, p, 7, 100, str(tmp_path / "s.npz"))
    assert idx.shape == (7, 30) and all(sorted(row) == list(range(30)) for row in idx.tolist())
    assert (np.diff(val, axis=1) <= 0).all()


def test_equal_scores_the_earlier_passage_stays():
    empty_v, empty_i = np.empty((1, 0), np.float32), np.empty((1, 0), np.int64)
    v, i = sw.merge_top(empty_v, empty_i, np.array([[5, 4, 4, 4]], np.float32), np.arange(0, 4), 3)
    assert i.tolist() == [[0, 1, 2]] and v.tolist() == [[5, 4, 4]]
    v, i = sw.merge_top(v, i, np.array([[4, 6]], np.float32), np.arange(4, 6), 3)             # the 4 of the later piece does not push out an earlier 4
    assert i.tolist() == [[5, 0, 1]] and v.tolist() == [[6, 5, 4]]
    v, i = sw.merge_top(v, i, np.array([[4, 4, 5]], np.float32), np.arange(6, 9), 3)             # a 5 of a later piece comes after the earlier 5
    assert i.tolist() == [[5, 0, 8]]


def test_equal_scores_at_the_cut_inside_one_piece():
    """4,000 passages of one piece share the lowest score that is kept; the first of them in the corpus must be the ones kept."""
    r = np.random.default_rng(11)
    for _ in range(20):
        sc = np.full((1, 4000), 1.0, np.float32)
        high = r.choice(4000, size=3, replace=False); sc[0, high] = 2.0
        _v, i = sw.merge_top(np.empty((1, 0), np.float32), np.empty((1, 0), np.int64), sc, np.arange(100, 4100), 10)
        ones = [x for x in range(4000) if x not in set(high.tolist())][:7]
        assert i[0].tolist() == [h + 100 for h in sorted(high.tolist())] + [x + 100 for x in ones]


def test_a_stop_and_a_later_call_give_the_same_as_one_run(tmp_path):
    q, p = vectors(passages=901)
    _f, val, idx, ids_of, seen, _n = run(q, p, 100, 100, str(tmp_path / "one.npz"), judged={"d5", "d450", "d900", "x"})
    state = str(tmp_path / "steps.npz"); calls = 0
    for _ in range(6):                                                           # ten pieces, three per call: four calls
        finished, v2, i2, ids2, seen2, _n = run(q, p, 100, 100, state, stop_after=3, judged={"d5", "d450", "d900", "x"}); calls += 1
        if finished:
            break
    assert finished and calls == 4
    assert (i2 == idx).all() and (v2 == val).all() and ids2 == ids_of
    assert seen2 == seen == {"d5", "d450", "d900"}


def test_a_state_of_another_search_is_refused(tmp_path):
    q, p = vectors(passages=300)
    run(q, p, 100, 100, str(tmp_path / "s.npz"), stop_after=1)
    with pytest.raises(SystemExit) as e:
        sw.load_state(str(tmp_path / "s.npz"), "another key")
    assert e.value.code == 2


def test_a_stored_file_that_differs_from_its_record_is_refused(tmp_path):
    _q, p = vectors(passages=40)
    path = str(tmp_path / "corpus-00000.npy"); np.save(path, p)
    good = hashlib.sha256(open(path, "rb").read()).hexdigest()
    arr, digest = sw.read_npy_checked(path, good)
    assert digest == good and arr.shape == p.shape and (arr == p).all()
    raw = bytearray(open(path, "rb").read()); raw[-1] ^= 1; open(path, "wb").write(bytes(raw))
    with pytest.raises(SystemExit) as e:
        sw.read_npy_checked(path, good)
    assert e.value.code == 2


def test_only_float32_matrices_are_read(tmp_path):
    path = str(tmp_path / "x.npy"); np.save(path, np.zeros((3, 4), np.float64))
    with pytest.raises(SystemExit):
        sw.read_npy_checked(path)


def checkpoint_file(tmp_path, recs):
    path = str(tmp_path / "checkpoints.jsonl")
    open(path, "w", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in recs))
    return path


def piece(i, first, n):
    return {"kind": "piece", "piece": i, "first": first, "passages": n, "vectors_file": f"corpus-{i:05d}.npy", "vectors_sha256": "a", "ids_file": f"ids-{i:05d}.json", "ids_sha256": "b"}


QUERIES = {"kind": "queries", "queries_sha256": "q", "query_ids_sha256": "r"}


def test_the_checkpoint_file_is_read_as_written(tmp_path):
    recs = [{"kind": "session"}, QUERIES, piece(0, 0, 100), piece(1, 100, 100), {"kind": "stopped"}, {"kind": "session"}, piece(2, 200, 37), {"kind": "finished", "passages": 237}]
    pieces, qrec, total = sw.pieces_from_checkpoints(checkpoint_file(tmp_path, recs))
    assert total == 237 and [p[4] for p in pieces] == [100, 100, 37] and qrec["queries_sha256"] == "q"


@pytest.mark.parametrize("recs", [
    [QUERIES, piece(0, 0, 100), piece(1, 100, 100)],                                              # no `finished` line
    [QUERIES, piece(0, 0, 100), piece(1, 150, 100), {"kind": "finished", "passages": 200}],       # a gap
    [QUERIES, piece(0, 0, 100), {"kind": "finished", "passages": 200}],                           # the total differs
    [piece(0, 0, 100), {"kind": "finished", "passages": 100}],                                    # no `queries` line
])
def test_an_incomplete_checkpoint_file_is_refused(tmp_path, recs):
    with pytest.raises(SystemExit) as e:
        sw.pieces_from_checkpoints(checkpoint_file(tmp_path, recs))
    assert e.value.code == 2
