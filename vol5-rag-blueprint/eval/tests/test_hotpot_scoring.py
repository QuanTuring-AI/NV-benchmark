"""hotpot_scoring: the official normalization and scores, the 'contains' rule, the paired test, the fixed sample.
Made-up answers only."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hotpot_scoring as S  # noqa: E402


def test_normalize_is_the_official_one():
    assert S.normalize_answer("The  Eiffel-Tower, in Paris!") == "eiffeltower in paris"
    assert S.normalize_answer("An apple and a pear") == "apple and pear"


def test_em_and_f1_official_values():
    assert S.em("the United States", "United States") is True
    assert S.f1("American actor", "American") == 2 * (1 / 2) * 1 / (1 / 2 + 1)
    assert S.f1("unrelated words", "American") == 0.0


def test_f1_yes_no_rule():
    assert S.f1("yes", "no") == 0.0 and S.f1("yes", "yes") == 1.0
    assert S.f1("no idea", "no") == 0.0          # 'no idea' is not 'no', and gold 'no' needs an equal answer


def test_contains_whole_tokens_only():
    assert S.contains("He was born in the United States in 1950.", "United States")
    assert not S.contains("He was born in Unitedstates.", "United States")
    assert not S.contains("Samsung", "sam")      # a part of a token is not the answer


def test_contains_yes_no_looks_at_the_first_token():
    assert S.contains("Yes, both were American.", "yes")
    assert not S.contains("There is no doubt they were both American.", "no")
    assert S.contains("No, they were not.", "no")


def test_score_answers_counts_failures_against_the_total():
    rows = [{"query_id": "1", "answer": "Paris", "gold": "Paris"}, {"query_id": "2", "answer": None, "gold": "Rome"},
            {"query_id": "3", "answer": "I cannot find that in the context.", "gold": "Oslo"}]
    s = S.score_answers(rows)
    assert (s["contains"], s["questions"], s["failed_calls"], s["refused_by_pattern"]) == (1, 3, 1, 1)
    assert abs(s["contains_rate"] - 1 / 3) < 1e-12


def test_paired_counts_discordant_pairs():
    a = [{"query_id": str(i), "answer": "x" if i < 6 else "y", "gold": "x"} for i in range(10)]
    b = [{"query_id": str(i), "answer": "x" if i < 2 else "y", "gold": "x"} for i in range(10)]
    r = S.paired(a, b)
    assert (r["only_a"], r["only_b"]) == (4, 0) and abs(r["mcnemar_exact_p"] - 0.125) < 1e-12


def test_paired_refuses_different_question_sets():
    try:
        S.paired([{"query_id": "1", "answer": "a", "gold": "a"}], [{"query_id": "2", "answer": "a", "gold": "a"}])
    except ValueError:
        return
    raise AssertionError("different question sets were accepted")


def test_c3_sample_is_fixed_and_independent_of_input_order():
    ids = [f"q{i:05d}" for i in range(7405)]
    a, b = S.c3_sample(ids), S.c3_sample(list(reversed(ids)))
    assert a == b and len(a) == 200 and len(set(a)) == 200
    assert S.c3_sample(ids, seed=S.C3_SEED + 1) != a


def test_score_answers_counts_contains_not_exact_match():
    rows = [{"query_id": "1", "answer": "The capital is Paris.", "gold": "Paris"}]
    s = S.score_answers(rows)
    assert (s["contains"], s["em"]) == (1, 0)
