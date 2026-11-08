"""Vol.5 · score_p_star.py on synthetic questions (no HotpotQA data): the pair labels, the supporting-passage counts,
the equal-ten count, and the refusal to score arms that do not hold the same questions."""
import os, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import score_p_star as S  # noqa: E402

GOLD = {"q1": "Paris", "q2": "1999", "q3": "blue whale"}


def arm(answers):
    return {q: {"query_id": q, "status": "ok", "answer": a, "finish_reason": "stop"} for q, a in answers.items()}


SUP = {"q1": {"a", "b"}, "q2": {"c", "d"}, "q3": {"e", "f"}}
TEN_STAR = {"q1": {"a", "b", "x"}, "q2": {"c", "y"}, "q3": {"e", "z"}}
TEN_P = {"q1": {"a", "b", "x"}, "q2": {"y"}, "q3": {"z"}}


def test_pairs_are_labelled_from_p_star():
    pstar = arm({"q1": "It is Paris.", "q2": "In 1999.", "q3": "I cannot answer."})
    p = arm({"q1": "It is Paris.", "q2": "No idea.", "q3": "No idea."})
    o = arm({"q1": "It is Paris.", "q2": "In 1999.", "q3": "The blue whale."})
    r = S.score(pstar, p, o, GOLD, SUP, TEN_STAR, TEN_P)
    assert r["score"]["contains"] == 2
    assert (r["paired_Pstar_P"]["only_a"], r["paired_Pstar_P"]["only_b"]) == (1, 0)
    assert (r["paired_Pstar_O"]["only_a"], r["paired_Pstar_O"]["only_b"]) == (0, 1)


def test_supporting_counts_and_equal_tens():
    a = arm({q: "x" for q in GOLD})
    r = S.score(a, a, a, GOLD, SUP, TEN_STAR, TEN_P)
    assert r["supporting_passages_among_the_ten"] == {"both": 1, "one": 2, "none": 0}
    assert r["ten_equal_to_P"] == 1


def test_failed_call_counts_as_not_containing():
    pstar = arm({q: "Paris 1999 blue whale" for q in GOLD}); pstar["q1"]["status"] = "error"
    r = S.score(pstar, pstar, pstar, GOLD, SUP, TEN_STAR, TEN_P)
    assert r["score"]["contains"] == 2 and r["score"]["failed_calls"] == 1


def test_refuses_different_question_sets():
    a = arm({q: "x" for q in GOLD}); b = arm({"q1": "x", "q2": "x"})
    with pytest.raises(ValueError, match="id tables"):
        S.score(a, b, a, GOLD, SUP, TEN_STAR, TEN_P)
