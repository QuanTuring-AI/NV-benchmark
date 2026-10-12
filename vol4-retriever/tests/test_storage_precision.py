"""storage_precision.py: what a piece looks like after being stored in fewer bits, the one scale of the int8 store, and
the comparison with a 32-bit ranking. Small made-up matrices with known answers; no data set and no card."""
import os, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import storage_precision as Z  # noqa: E402


def halves(rows):
    """Rows of four numbers, each +-0.5: unit vectors whose every component has the absolute value 0.5."""
    signs = np.array([[1, 1, 1, 1], [1, -1, 1, -1], [-1, 1, 1, -1], [1, 1, -1, -1]], dtype=np.float32)
    return np.vstack([signs[i % 4] for i in range(rows)]) * np.float32(0.5)


def test_fp32_is_the_piece_itself():
    p = halves(8)
    m, cut = Z.stored(p, "fp32")
    assert m is p and cut == 0.0


def test_fp16_loses_what_sixteen_bits_cannot_hold():
    p = np.array([[1.0 + 1e-5, 0.25, -3.0, 0.1]], dtype=np.float32)
    m, cut = Z.stored(p, "fp16")
    assert m.dtype == np.float32 and cut == 0.0
    assert m[0, 0] == np.float32(1.0)                      # 1.00001 is not a 16-bit float
    assert m[0, 1] == np.float32(0.25) and m[0, 2] == np.float32(-3.0)
    assert abs(float(m[0, 3]) - 0.1) < 1e-4 and m[0, 3] != p[0, 3]


def test_the_scale_is_127_over_the_percentile_not_over_the_largest_value():
    p = np.vstack([halves(999), np.array([[1, 0, 0, 0]], dtype=np.float32)])     # 3,996 values of 0.5, one of 1.0, three of 0
    assert abs(Z.int8_scale(p) - 254.0) < 1e-3


def test_the_scale_comes_from_unit_vectors():
    assert abs(Z.int8_scale(halves(100) * np.float32(7.0)) - 254.0) < 1e-3


def test_int8_values_are_whole_bytes_and_large_values_are_cut():
    p = np.vstack([halves(3), np.array([[1, 0, 0, 0]], dtype=np.float32)])
    m, cut = Z.stored(p, "int8", 254.0)
    assert m.dtype == np.float32 and np.array_equal(m, np.rint(m))
    assert np.array_equal(np.abs(m[:3]), np.full((3, 4), 127.0, dtype=np.float32))
    assert m[3].tolist() == [127.0, 0.0, 0.0, 0.0]         # 1.0 x 254 = 254 is cut to 127, not wrapped
    assert abs(cut - 1 / 16) < 1e-9


def test_int8_does_not_depend_on_the_length_of_a_vector():
    p = halves(6)
    a, _ = Z.stored(p, "int8", 100.0); b, _ = Z.stored(p * np.float32(3.0), "int8", 100.0)     # 0.5 x 100 = 50: below the cut, so a vector three times as long would show
    assert np.array_equal(a, b) and np.array_equal(np.abs(a), np.full((6, 4), 50.0, dtype=np.float32))


def test_int8_keeps_small_differences_that_a_scale_of_one_would_lose():
    p = np.array([[0.50, 0.50, 0.50, 0.50], [0.52, 0.50, 0.50, 0.48]], dtype=np.float32)
    m, _ = Z.stored(p, "int8", 254.0)
    assert not np.array_equal(m[0], m[1])


def test_against_a_reference_ranking():
    ref = {q: [f"p{i}" for i in range(100)] for q in ("q1", "q2", "q3")}
    mine = {"q1": [f"p{i}" for i in range(100)], "q2": [f"p{i}" for i in range(1, 51)] + [f"x{i}" for i in range(50)],
            "q3": ["p1", "p0"] + [f"p{i}" for i in range(2, 100)]}                     # the same hundred, the first two swapped
    r = Z.against(ref, mine)
    assert r["queries"] == 3 and r["queries_whose_first_10_are_the_same_in_the_same_order"] == 1
    assert abs(r["share_of_the_first_100_in_common_mean"] - 2.5 / 3) < 1e-6 and r["share_of_the_first_100_in_common_lowest"] == 0.5


def test_read_run_orders_by_rank(tmp_path):
    f = tmp_path / "run.trec"
    f.write_text("q1 Q0 b 2 0.5 t\nq1 Q0 a 1 0.9 t\nq2 Q0 c 1 0.7 t\n", encoding="utf-8")
    assert Z.read_run(str(f)) == {"q1": ["a", "b"], "q2": ["c"]}


def test_the_share_a_16_bit_float_holds_exactly():
    assert Z.fp16_exact_share(np.array([[0.25, -3.0, 0.5, 1.0]], dtype=np.float32)) == 1.0
    assert Z.fp16_exact_share(np.array([[0.25, 0.1, 0.5, 1.0 + 1e-5]], dtype=np.float32)) == 0.5
