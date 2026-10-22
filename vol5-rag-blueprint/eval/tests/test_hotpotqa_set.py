"""hotpotqa_set: the id matching and its checks, on a made-up four-question BEIR folder and source file."""
import json, os, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hotpotqa_set as H  # noqa: E402

CORPUS = [("1", "Alpha"), ("2", "Beta"), ("3", "Gamma"), ("4", "Delta"), ("5", "Epsilon")]
QS = {"qa": ("yes", [["Alpha", 0], ["Beta", 1]], ["1", "2"]), "qb": ("Oslo", [["Gamma", 0], ["Delta", 2]], ["3", "4"]),
      "qc": ("1950", [["Alpha", 1], ["Epsilon", 0]], ["1", "5"]), "qd": ("no", [["Beta", 0], ["Gamma", 3]], ["2", "3"])}


def folder(source_edit=None, qrels_edit=None, corpus=CORPUS):
    d = tempfile.mkdtemp(); b = os.path.join(d, "beir"); os.makedirs(os.path.join(b, "qrels"))
    with open(os.path.join(b, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for i, t in corpus:
            f.write(json.dumps({"_id": i, "title": t, "text": "x"}) + "\n")
    with open(os.path.join(b, "queries.jsonl"), "w", encoding="utf-8") as f:
        for q, (a, sf, _) in QS.items():
            f.write(json.dumps({"_id": q, "text": "?", "metadata": {"answer": a, "supporting_facts": sf}}) + "\n")
    with open(os.path.join(b, "qrels", "test.tsv"), "w", encoding="utf-8") as f:
        f.write("query-id\tcorpus-id\tscore\n")
        for q, (_, _, ids) in QS.items():
            for i in (qrels_edit or {}).get(q, ids):
                f.write(f"{q}\t{i}\t1\n")
    src = [{"_id": q, "answer": a, "type": "bridge", "level": "hard", "supporting_facts": sf} for q, (a, sf, _) in QS.items()]
    if source_edit:
        source_edit(src)
    p = os.path.join(d, "dev.json"); json.dump(src, open(p, "w", encoding="utf-8"))
    return b, p


def test_a_clean_set_matches_whole():
    rows, check = H.load_set(*folder())
    assert check["all_matched"] and len(rows) == 4 and rows[0]["gold_passages"] == ["1", "2"]


def test_a_changed_answer_is_caught():
    def edit(src): src[1]["answer"] = "Bergen"
    _, check = H.load_set(*folder(source_edit=edit))
    assert check["counts"]["answer_differs"] == 1 and not check["all_matched"]


def test_a_changed_fact_is_caught():
    def edit(src): src[0]["supporting_facts"][1][1] = 7
    _, check = H.load_set(*folder(source_edit=edit))
    assert check["counts"]["facts_differ"] == 1 and not check["all_matched"]


def test_a_missing_question_is_caught():
    def edit(src): src.pop()
    _, check = H.load_set(*folder(source_edit=edit))
    assert check["counts"]["in_beir_not_in_source"] == 1 and not check["all_matched"]


def test_a_title_with_two_passages_is_caught():
    _, check = H.load_set(*folder(corpus=CORPUS + [("6", "Gamma")]))
    assert check["counts"]["title_not_one_passage"] >= 1 and not check["all_matched"]


def test_judgements_that_differ_from_the_facts_are_caught():
    _, check = H.load_set(*folder(qrels_edit={"qb": ["3", "5"]}))
    assert check["counts"]["passages_not_the_judgements"] == 1 and not check["all_matched"]


def test_a_judgement_beyond_the_facts_is_caught():
    _, check = H.load_set(*folder(qrels_edit={"qb": ["3", "4", "5"]}))
    assert check["counts"]["passages_not_the_judgements"] == 1 and not check["all_matched"]
