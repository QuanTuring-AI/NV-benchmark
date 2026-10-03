"""Tests of retrieval_metrics.py. Each small case is worked out by hand in its comment; the expected digits are written
out, and the closed form is recomputed beside them. Every test names the mistake it would catch."""
import math, os, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import retrieval_metrics as rm  # noqa: E402


def test_perfect_ranking_is_one():
    # three relevant passages ranked first, in the order of their grades: both metrics are exactly 1
    qrels = {"q1": {"a": 2, "b": 1, "c": 1, "x": 0}, "q2": {"m": 1}}
    run = {"q1": {"a": 9.0, "b": 8.0, "c": 7.0, "x": 1.0}, "q2": {"m": 5.0, "n": 1.0}}
    r = rm.evaluate(qrels, run)
    assert r["ndcg_cut_10"] == 1.0 and r["recall_100"] == 1.0
    assert r["queries_scored"] == 2 and r["queries_with_results"] == 2


def test_one_relevant_passage_at_rank_two():
    # DCG = 1 / log2(2 + 1) = 0.6309297535714575 ; ideal DCG = 1 / log2(1 + 1) = 1 ; nDCG@10 = 0.6309297535714575
    r = rm.evaluate({"q": {"d1": 1}}, {"q": {"d2": 2.0, "d1": 1.0}})
    assert r["ndcg_cut_10"] == pytest.approx(0.6309297535714575, abs=1e-15)
    assert r["ndcg_cut_10"] == pytest.approx(1 / math.log2(3), abs=1e-15)
    assert r["recall_100"] == 1.0


def test_graded_relevance_uses_the_grade_as_gain():
    # qrels: a = 2, b = 1, c = 0. Ranking: b, c, a.
    # DCG   = 1/log2(2) + 0/log2(3) + 2/log2(4) = 1 + 0 + 1 = 2
    # ideal = 2/log2(2) + 1/log2(3)             = 2 + 0.6309297535714575 = 2.6309297535714575
    # nDCG@10 = 2 / 2.6309297535714575 = 0.7601875334318685
    # A gain of 2^grade - 1 would give 2.5 / 3.6309297535714575 = 0.6885...: this test fails for it.
    r = rm.evaluate({"q": {"a": 2, "b": 1, "c": 0}}, {"q": {"b": 3.0, "c": 2.0, "a": 1.0}})
    assert r["ndcg_cut_10"] == pytest.approx(0.7601875334318685, abs=1e-15)
    assert r["ndcg_cut_10"] == pytest.approx(2 / (2 + 1 / math.log2(3)), abs=1e-15)
    assert abs(r["ndcg_cut_10"] - 2.5 / (3 + 1 / math.log2(3))) > 0.05


def test_cutoffs_are_ten_and_one_hundred():
    run = {"q": {f"d{i:03d}": float(200 - i) for i in range(1, 121)}}   # d001 is first, d120 last
    # the only relevant passage at rank 11: nDCG@10 = 0 (it is 1/log2(12) = 0.2789 at a cut-off of 20)
    assert rm.evaluate({"q": {"d011": 1}}, run)["ndcg_cut_10"] == 0.0
    # at rank 10: 1/log2(11) = 0.2890648263178879
    assert rm.evaluate({"q": {"d010": 1}}, run)["ndcg_cut_10"] == pytest.approx(0.2890648263178879, abs=1e-15)
    # recall: rank 100 counts, rank 101 does not
    assert rm.evaluate({"q": {"d100": 1}}, run)["recall_100"] == 1.0
    assert rm.evaluate({"q": {"d101": 1}}, run)["recall_100"] == 0.0


def test_recall_counts_relevant_passages_only():
    # two relevant passages, one retrieved; a passage judged 0 at the top changes nothing: recall = 1/2
    # nDCG: DCG = 1/log2(3) = 0.6309297535714575 ; ideal = 1 + 1/log2(3) = 1.6309297535714575 ; 0.38685280723454163
    r = rm.evaluate({"q": {"a": 1, "b": 1, "z": 0}}, {"q": {"z": 3.0, "a": 2.0}})
    assert r["recall_100"] == 0.5
    assert r["ndcg_cut_10"] == pytest.approx(0.38685280723454163, abs=1e-15)


def test_a_query_without_results_counts_as_zero():
    # two queries, results for one of them only (a perfect one): the mean is 0.5, not 1.0
    r = rm.evaluate({"q1": {"a": 1}, "q2": {"b": 1}}, {"q1": {"a": 1.0}})
    assert r["ndcg_cut_10"] == 0.5 and r["recall_100"] == 0.5
    assert r["queries_scored"] == 2 and r["queries_with_results"] == 1 and r["queries_without_results_counted_as_zero"] == 1


def test_queries_outside_the_qrels_are_ignored_and_counted():
    r = rm.evaluate({"q1": {"a": 1}}, {"q1": {"a": 1.0}, "other": {"a": 1.0}})
    assert r["ndcg_cut_10"] == 1.0 and r["queries_in_run_not_in_qrels"] == 1


def test_equal_scores_are_ordered_by_passage_id_later_first():
    # trec_eval's rule, observed here and not assumed: with equal scores, "b" is ranked before "a"
    assert rm.evaluate({"q": {"b": 1}}, {"q": {"a": 1.0, "b": 1.0}})["ndcg_cut_10"] == 1.0
    assert rm.evaluate({"q": {"a": 1}}, {"q": {"a": 1.0, "b": 1.0}})["ndcg_cut_10"] == pytest.approx(0.6309297535714575, abs=1e-15)


def test_ignore_identical_ids_removes_the_query_itself():
    qrels = {"q1": {"d1": 1}}
    run = {"q1": {"q1": 9.0, "d1": 1.0}}          # the query's own id is the top result
    assert rm.evaluate(qrels, run)["ndcg_cut_10"] == pytest.approx(0.6309297535714575, abs=1e-15)
    assert rm.evaluate(qrels, run, ignore_identical_ids=True)["ndcg_cut_10"] == 1.0


def test_a_query_without_a_relevant_passage_stops_the_evaluation():
    with pytest.raises(ValueError, match="no relevant passage"):
        rm.evaluate({"q1": {"a": 0}, "q2": {"b": 1}}, {"q1": {"a": 1.0}, "q2": {"b": 1.0}})


def test_run_file_is_ranked_by_score_not_by_the_rank_column(tmp_path):
    p = tmp_path / "run.trec"
    # the rank column says d2 first, the scores say d1 first; the scores decide
    p.write_text("q1 Q0 d2 1 0.5 tag\nq1 Q0 d1 2 0.9 tag\n", encoding="utf-8")
    run = rm.read_run_trec(str(p))
    assert run == {"q1": {"d2": 0.5, "d1": 0.9}}
    assert rm.evaluate({"q1": {"d1": 1}}, run)["ndcg_cut_10"] == 1.0


def test_run_file_with_a_repeated_passage_is_refused(tmp_path):
    p = tmp_path / "run.trec"
    p.write_text("q1 Q0 d1 1 0.9 tag\nq1 Q0 d1 2 0.8 tag\n", encoding="utf-8")
    with pytest.raises(ValueError, match="listed twice"):
        rm.read_run_trec(str(p))
