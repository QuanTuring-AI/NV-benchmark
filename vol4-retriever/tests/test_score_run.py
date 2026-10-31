"""Tests of the search in score_run.py on small vectors worked out by hand. Written after the first GPU session; the
program under test is bound by that session's pre-registration and is not changed by these tests."""
import os, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import score_run as sr  # noqa: E402


def test_unit_divides_by_the_length_and_reports_the_range():
    v = np.array([[3.0, 4.0], [0.0, 2.0]], dtype=np.float32)
    u, lo, hi = sr.unit(v)
    assert np.allclose(u, [[0.6, 0.8], [0.0, 1.0]]) and (lo, hi) == (2.0, 5.0)


def test_search_orders_by_cosine_highest_first_and_keeps_top():
    q = np.array([[1.0, 0.0]], dtype=np.float32)
    p = np.array([[0.0, 1.0], [1.0, 0.0], [0.6, 0.8], [0.8, 0.6], [-1.0, 0.0]], dtype=np.float32)      # cosines 0, 1, 0.6, 0.8, -1
    idx, val = sr.search(q, p, top=3)
    assert idx.tolist() == [[1, 3, 2]] and np.allclose(val, [[1.0, 0.8, 0.6]])


def test_search_with_top_at_least_the_corpus_returns_every_passage_in_order():
    q = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    p = np.array([[0.0, 1.0], [1.0, 0.0], [0.6, 0.8]], dtype=np.float32)
    idx, val = sr.search(q, p, top=1000)
    assert idx.tolist() == [[1, 2, 0], [0, 2, 1]] and idx.shape == (2, 3)


def test_search_in_chunks_gives_the_same_as_in_one_piece():
    rng = np.random.default_rng(7)
    q, _, _ = sr.unit(rng.standard_normal((130, 16)).astype(np.float32)); p, _, _ = sr.unit(rng.standard_normal((500, 16)).astype(np.float32))
    a_idx, a_val = sr.search(q, p, top=10, chunk=64); b_idx, b_val = sr.search(q, p, top=10, chunk=1000)
    assert (a_idx == b_idx).all() and np.allclose(a_val, b_val)
    full = q @ p.T                                                     # the reference: sort every row completely
    assert (a_idx == np.argsort(-full, axis=1, kind="stable")[:, :10]).all()
