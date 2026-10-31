"""Tests of the two control programs of the HotpotQA addendum, on invented vectors: each control must pass on a
correct store and fail on a store that is wrong in the way it is meant to catch."""
import json, os, sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import check_stored_vectors as C  # noqa: E402
import subset_search_two_ways as S  # noqa: E402


def store(tmp_path, sizes=(5, 5, 3), dim=8, seed=0):
    """A store in the layout of the resumable encoder: pieces with their ids, in corpus order. -> (dir, pieces, ids, vectors)."""
    rng = np.random.default_rng(seed); v = rng.normal(size=(sum(sizes), dim)).astype(np.float32); v /= np.linalg.norm(v, axis=1, keepdims=True)
    ids = [f"p{i:03d}" for i in range(len(v))]; pieces = []; first = 0
    for k, n in enumerate(sizes):
        np.save(tmp_path / f"corpus-{k:05d}.npy", v[first:first + n]); json.dump(ids[first:first + n], open(tmp_path / f"ids-{k:05d}.json", "w"))
        pieces.append({"kind": "piece", "piece": k, "first": first, "passages": n, "vectors_file": f"corpus-{k:05d}.npy", "ids_file": f"ids-{k:05d}.json"}); first += n
    return str(tmp_path), pieces, ids, v


def test_sample_positions_are_spread_unique_and_inside():
    p = C.sample_positions(1000, 10); assert p == [50, 150, 250, 350, 450, 550, 650, 750, 850, 950]
    p = C.sample_positions(5233329, 1000); assert len(p) == 1000 and p[0] == 2616 and p[-1] < 5233329 and len({x // 100000 for x in p}) == 53
    assert C.sample_positions(3, 10) == [0, 1, 2]


def test_piece_of_at_the_borders():
    _, pieces, _, _ = None, [{"piece": 0, "first": 0, "passages": 5}, {"piece": 1, "first": 5, "passages": 5}, {"piece": 2, "first": 10, "passages": 3}], None, None
    assert C.piece_of(4, pieces)[0]["piece"] == 0 and C.piece_of(5, pieces) == (pieces[1], 0) and C.piece_of(12, pieces) == (pieces[2], 2)
    with pytest.raises(SystemExit):
        C.piece_of(13, pieces)


def test_control_c_passes_on_a_correct_store(tmp_path):
    d, pieces, ids, v = store(tmp_path); pos = [0, 4, 5, 9, 12]
    bad, c, same = C.compare(pos, [ids[i] for i in pos], v[pos] + 1e-5, pieces, d, 0.999)
    assert bad == [] and same == 5 and c.min() > 0.9999


def test_control_c_fails_when_the_rows_are_shifted_by_one(tmp_path):
    d, pieces, ids, v = store(tmp_path); pos = [1, 6, 11]
    bad, c, same = C.compare(pos, [ids[i - 1] for i in pos], v[[i - 1 for i in pos]], pieces, d, 0.999)     # the passages of the positions before
    assert len(bad) == 3 and same == 0 and c.max() < 0.999


def test_control_c_fails_when_the_ids_are_right_but_the_vectors_are_another_passages(tmp_path):
    d, pieces, ids, v = store(tmp_path); pos = [2, 7]
    bad, c, same = C.compare(pos, [ids[i] for i in pos], v[[3, 8]], pieces, d, 0.999)
    assert same == 2 and len(bad) == 2 and all(b["id_equal_at_the_position"] for b in bad)


def test_control_c_fails_when_two_pieces_are_exchanged(tmp_path):
    d, pieces, ids, v = store(tmp_path); pieces[0]["vectors_file"], pieces[1]["vectors_file"] = pieces[1]["vectors_file"], pieces[0]["vectors_file"]
    bad, _, same = C.compare([0, 5], [ids[0], ids[5]], v[[0, 5]], pieces, d, 0.999)
    assert same == 2 and len(bad) == 2


def test_rank_orders_by_score_and_keeps_file_order_for_equal_scores():
    q = np.array([[1.0, 0.0]], dtype=np.float32); d = np.array([[0.0, 1.0], [1.0, 0.0], [0.6, 0.8], [1.0, 0.0]], dtype=np.float32)
    r = S.rank(q, d, ["a", "b", "c", "d"], 3)[0]
    assert [x for x, _ in r] == ["b", "d", "c"] and r[0][1] == pytest.approx(1.0) and r[2][1] == pytest.approx(0.6)
    many = S.rank(np.repeat(q, 600, axis=0), d, ["a", "b", "c", "d"], 2); assert len(many) == 600 and all([x for x, _ in row] == ["b", "d"] for row in many)


def test_gather_takes_the_subset_in_corpus_order(tmp_path):
    d, pieces, ids, v = store(tmp_path); want = {ids[11], ids[0], ids[6]}
    m, got = S.gather(d, pieces, want)
    assert got == [ids[0], ids[6], ids[11]] and np.array_equal(m, v[[0, 6, 11]])


def test_subset_is_the_judged_passages_and_the_first_piece():
    judged, ids = S.subset_ids({"q1": {"p900": 1, "p001": 0}, "q2": {"p950": 1}}, ["p000", "p001", "p002"])
    assert judged == {"p900", "p001", "p950"} and ids == ["p000", "p001", "p002", "p900", "p950"]


def test_the_second_way_gives_the_metric_of_a_ranking_made_by_hand(tmp_path):
    import retrieval_metrics as rm
    d, pieces, ids, v = store(tmp_path); q = v[[3, 10]] + 0.01
    m, got = S.gather(d, pieces, set(ids)); ranked = S.rank(S.unit(q.astype(np.float32)), S.unit(m), got, 5)
    assert ranked[0][0][0] == ids[3] and ranked[1][0][0] == ids[10]
    run = {f"q{k}": {pid: s for pid, s in row} for k, row in enumerate(ranked)}
    out = rm.evaluate({"q0": {ids[3]: 1}, "q1": {ids[10]: 1}}, run)
    assert out["ndcg_cut_10"] == pytest.approx(1.0) and out["recall_100"] == pytest.approx(1.0)
