"""Tests of the scorer. The three documents and the five questions are invented for these tests (a lighthouse log, notes
on bread, a tram guide); nothing in this file comes from a corpus that is measured anywhere in this repository."""
import json, os, subprocess, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rag_eval as E  # noqa: E402

DOCS = {
 "harbor-log": ["The keeper of Marlow Point lit the lamp at 18:40 on the ninth of March.", "The supply boat Heron arrived two days late because of ice in the channel.",
                "A new lens, weighing 212 kilograms, was installed in April.", "Visitors were not allowed on the gallery while the lens was being fitted, which took most of a week."],
 "bread-notes": ["老麵種每天早上七點餵養一次，比例是一份麵種、兩份麵粉、兩份水。", "全麥吐司的烘烤溫度是攝氏一百九十度，時間四十分鐘。", "出爐後要在網架上放涼至少一小時才能切片。"],
 "tram-guide": ["三番線の路面電車は朝六時十五分に車庫を出発します。", "終点の港町駅までの所要時間は四十二分です。", "冬季は積雪のため、最終便が三十分早まります。"],
}
RAW = {k: "\n".join(v) for k, v in DOCS.items()}
REF = {k: E.normalize(v) for k, v in RAW.items()}


def gold(doc, i):
    s = E.span_of(RAW[doc], DOCS[doc][i], doc); assert s is not None
    return s


QUESTIONS = [
 {"id": "q1", "question": "How heavy was the new lens installed at Marlow Point?", "lang": "en", "answerable": True, "gold_file_ids": ["harbor-log"], "gold_passage_spans": [gold("harbor-log", 2)], "key_facts": ["212 kilograms"]},
 {"id": "q2", "question": "全麥吐司要用幾度烤多久？", "lang": "zh", "answerable": True, "gold_file_ids": ["bread-notes"], "gold_passage_spans": [gold("bread-notes", 1)], "key_facts": ["一百九十度", "四十分鐘"]},
 {"id": "q3", "question": "港町駅までどのくらいかかりますか。", "lang": "ja", "answerable": True, "gold_file_ids": ["tram-guide"], "gold_passage_spans": [gold("tram-guide", 1)], "key_facts": ["四十二分"]},
 {"id": "q4", "question": "Who painted the lighthouse door?", "lang": "en", "answerable": False, "gold_file_ids": [], "gold_passage_spans": [], "key_facts": []},
 {"id": "q5", "question": "老麵種是哪一年開始養的？", "lang": "zh", "answerable": False, "gold_file_ids": [], "gold_passage_spans": [], "key_facts": []},
]


def p(doc, i):
    return {"file_id": doc, "text": DOCS[doc][i]}


def base_outputs():
    return [
     {"id": "q1", "retrieved": [p("harbor-log", 1), p("bread-notes", 0), p("harbor-log", 2)], "answer": "The lens weighed 212 kilograms.", "refused": None, "cited": [2]},
     {"id": "q2", "retrieved": [p("bread-notes", 1)], "answer": "攝氏一百九十度。", "refused": None, "cited": [0]},
     {"id": "q3", "retrieved": [p("tram-guide", 0)], "answer": "四十二分です。", "refused": None, "cited": [0]},
     {"id": "q4", "retrieved": [p("harbor-log", 0)], "answer": "I don't know.", "refused": None, "cited": []},
     {"id": "q5", "retrieved": [p("bread-notes", 0)], "answer": "一九九八年。", "refused": None, "cited": [0]},
    ]


def run(outputs=None, questions=None, ks=(1, 3), context_k=0, min_no_answer=2, overlap_list=None, max_not_located=0.05):
    return E.score(questions or QUESTIONS, outputs or base_outputs(), REF, list(ks), context_k, min_no_answer, overlap_list, max_not_located)


def row(rep, qid):
    return next(r for r in rep["per_question"] if r["id"] == qid)


# ---------------------------------------------------------------- building blocks
def test_wilson_known_values():
    lo, hi = E.wilson(45, 50); assert lo == pytest.approx(0.7864, abs=5e-4) and hi == pytest.approx(0.9565, abs=5e-4)
    lo, hi = E.wilson(0, 10); assert lo == 0.0 and hi == pytest.approx(0.2775, abs=5e-4)
    lo, hi = E.wilson(10, 10); assert lo == pytest.approx(0.7225, abs=5e-4) and hi == pytest.approx(1.0, abs=1e-12)
    assert E.wilson(0, 0) is None


def test_proportion_marks_small_n():
    assert E.proportion(3, 49)["n_below_50"] is True and E.proportion(3, 50)["n_below_50"] is False
    assert E.proportion(1, 4)["rate"] == 0.25


def test_normalize_removes_white_space_and_folds_width():
    assert E.normalize("a b\n c\t１２") == "abc12"
    assert E.normalize("ｋｇ　２１２") == "kg212"


def test_span_of_needs_exactly_one_occurrence():
    s = E.span_of("one two three", "two", "d"); assert s == {"file_id": "d", "start": 3, "end": 6}
    assert E.span_of("two and two", "two", "d") is None and E.span_of("one", "four", "d") is None and E.span_of("one", " ", "d") is None


def test_locate_as_given_and_after_normalization():
    ref = REF["harbor-log"]; raw = RAW["harbor-log"]; s = gold("harbor-log", 2)
    assert E.locate(DOCS["harbor-log"][2], ref, raw) == ((s["start"], s["end"]), "exact")
    assert E.locate("A new lens, weighing\n212 kilograms,  was installed in April.", ref, raw) == ((s["start"], s["end"]), "normalized")
    assert E.locate(DOCS["harbor-log"][2], ref) == ((s["start"], s["end"]), "normalized")           # no stored text given: only the second step can be said
    assert E.locate("no such sentence here", ref, raw) == (None, None) and E.locate("   ", ref, raw) == (None, None)


def test_nothing_approximate_is_located():
    ref = REF["harbor-log"]; raw = RAW["harbor-log"]; whole = DOCS["harbor-log"][3]
    assert E.locate(whole, ref, raw)[1] == "exact"
    assert E.locate(whole.replace("while ", ""), ref, raw) == (None, None)       # one word dropped inside the passage
    assert E.locate(whole + " And more.", ref, raw) == (None, None)              # a sentence added at the end
    assert E.locate("Page 3. " + whole, ref, raw) == (None, None)                # a mark added in front
    assert E.locate(whole[:40], ref, raw)[0] is not None                         # a true part of the text is located


def test_the_report_counts_how_passages_were_located():
    o = base_outputs(); o[1]["retrieved"] = [{"file_id": "bread-notes", "text": DOCS["bread-notes"][1][:10] + " \n" + DOCS["bread-notes"][1][10:]}]
    g = E.score(QUESTIONS, o, REF, [1, 3], 0, 2, None, 0.05, reference_raw=RAW)["gates"]["located"]
    assert (g["passages_given_as_text"], g["located_exactly_as_given"], g["located_after_normalization"], g["not_located"]) == (7, 6, 1, 0)
    g = run(o)["gates"]["located"]; assert (g["located_exactly_as_given"], g["located_after_normalization"]) == (0, 7)


def test_refusal_patterns_three_languages():
    for a in ("I could not find that in the documents.", "找不到相關內容。", "該当する記載がありません。回答できません。", "", None):
        assert E.refused_by_pattern(a)
    for a in ("The lens weighed 212 kilograms.", "攝氏一百九十度。", "四十二分です。"):
        assert not E.refused_by_pattern(a)


def test_key_facts_all_must_be_present():
    assert E.key_facts_present("It weighed 212 KILOGRAMS", ["212 kilograms"]) and E.key_facts_present("２１２ kilograms", ["212 kilograms"])
    assert not E.key_facts_present("攝氏一百九十度", ["一百九十度", "四十分鐘"]) and E.key_facts_present("一百九十度烤四十分鐘", ["一百九十度", "四十分鐘"])


# ---------------------------------------------------------------- hits
def test_file_level_and_passage_level_are_different_things():
    rep = run(); r = row(rep, "q1")
    assert r["file_hit"] == {"1": True, "3": True} and r["passage_hit"] == {"1": False, "3": True}
    assert row(rep, "q3")["file_hit"]["1"] is True and row(rep, "q3")["passage_hit"]["3"] is False
    F = rep["figures"]["answerable"]
    assert F["questions"] == 3 and F["file_level"]["hit@1"]["k"] == 3 and F["passage_level"]["hit@1"]["k"] == 1 and F["passage_level"]["hit@3"]["k"] == 2
    assert F["file_level"]["hit@1"]["n"] == 3 and F["file_level"]["hit@1"]["n_below_50"] is True


def test_file_hit_needs_only_one_passage_of_a_gold_file():
    o = base_outputs(); o[0]["retrieved"] = [p("bread-notes", 0), p("harbor-log", 0)]
    assert row(run(o), "q1")["file_hit"] == {"1": False, "3": True}


def test_strict_rule_is_cover_and_overlap_is_only_the_sensitivity_line():
    o = base_outputs(); half = DOCS["bread-notes"][1][:14]                  # the first part of the gold sentence only
    o[1]["retrieved"] = [{"file_id": "bread-notes", "text": DOCS["bread-notes"][0] + half}]
    rep = run(o); r = row(rep, "q2")
    assert r["passage_hit"]["1"] is False and r["passage_overlap"]["1"] is True and r["passage_in_context"] is False
    assert rep["figures"]["answerable"]["sensitivity_any_overlap"]["hit@1"]["k"] == rep["figures"]["answerable"]["passage_level"]["hit@1"]["k"] + 1


def test_a_passage_cut_at_the_end_of_the_gold_span_does_not_cover_it():
    o = base_outputs(); s = gold("bread-notes", 1)
    o[1]["retrieved"] = [{"file_id": "bread-notes", "start": s["start"] + 3, "end": s["end"] + 20}]
    assert row(run(o), "q2")["passage_hit"]["1"] is False
    o[1]["retrieved"] = [{"file_id": "bread-notes", "start": s["start"] - 5, "end": s["end"] - 1}]
    assert row(run(o), "q2")["passage_hit"]["1"] is False
    o[1]["retrieved"] = [{"file_id": "bread-notes", "start": s["start"], "end": s["end"]}]
    assert row(run(o), "q2")["passage_hit"]["1"] is True


def test_a_span_of_another_file_with_the_same_offsets_is_no_hit():
    o = base_outputs(); s = gold("bread-notes", 1)
    o[1]["retrieved"] = [{"file_id": "tram-guide", "start": s["start"], "end": s["end"]}]
    r = row(run(o), "q2"); assert r["passage_hit"]["1"] is False and r["file_hit"]["1"] is False


def test_conditional_hit_counts_only_questions_with_a_file_hit():
    o = base_outputs(); o[2]["retrieved"] = [p("harbor-log", 0)]            # q3: wrong file
    F = run(o)["figures"]["answerable"]
    assert F["file_level"]["hit@3"]["k"] == 2 and F["passage_given_file"]["hit@3"]["n"] == 2 and F["passage_given_file"]["hit@3"]["k"] == 2


def test_by_language_blocks():
    B = run()["figures"]["by_language"]; assert sorted(B) == ["en", "ja", "zh"] and B["zh"]["questions"] == 1 and B["ja"]["passage_level"]["hit@3"]["k"] == 0


# ---------------------------------------------------------------- answer map
def test_answer_map_four_cells_and_correctness():
    M = run()["figures"]["answer_map"]
    assert M["questions"] == 3 and M["answered_with_passage"]["k"] == 2 and M["answered_with_passage_correct"]["k"] == 1 and M["answered_with_passage_wrong"]["k"] == 1
    assert M["answered_without_passage"]["k"] == 1 and M["refused_with_passage"]["k"] == 0 and M["refused_without_passage"]["k"] == 0
    assert M["correctness_from"] == ["key facts"] and M["refusal_from"] == ["pattern"]
    o = base_outputs(); o[0]["answer"] = "I could not find that in the documents."; o[2]["answer"] = "見つかりません。"
    M = run(o)["figures"]["answer_map"]
    assert M["refused_with_passage"]["k"] == 1 and M["refused_without_passage"]["k"] == 1 and M["answered_with_passage"]["k"] == 1 and M["answered_without_passage"]["k"] == 0


def test_context_k_limits_what_counts_as_given_to_the_system():
    assert row(run(context_k=2), "q1")["passage_in_context"] is False and row(run(context_k=3), "q1")["passage_in_context"] is True
    assert run(context_k=2)["figures"]["answer_map"]["answered_without_passage"]["k"] == 2


def test_refusal_flag_of_the_output_wins_over_the_pattern():
    o = base_outputs(); o[0]["refused"] = True                             # the answer text reads like an answer
    rep = run(o); r = row(rep, "q1")
    assert r["refused"] is True and r["refusal_from"] == "output" and r["correct"] is None and rep["figures"]["answer_map"]["refused_with_passage"]["k"] == 1
    o = base_outputs(); o[3]["refused"] = False                            # "I don't know." but the system says it answered
    assert run(o)["figures"]["no_answer_set"]["refused"]["k"] == 0


def test_a_judge_verdict_wins_over_key_facts_and_no_key_facts_means_not_judged():
    o = base_outputs(); o[0]["judged_correct"] = False; o[1]["judged_correct"] = True
    M = run(o)["figures"]["answer_map"]; assert M["answered_with_passage_correct"]["k"] == 1 and M["answered_with_passage_wrong"]["k"] == 1 and M["correctness_from"] == ["judge"]
    assert row(run(o), "q1")["correct"] is False and row(run(o), "q2")["correct"] is True
    q = json.loads(json.dumps(QUESTIONS)); q[0]["key_facts"] = []
    M = run(questions=q)["figures"]["answer_map"]; assert M["answered_with_passage_not_judged"]["k"] == 1 and M["answered_with_passage_correct"]["k"] == 0 and M["answered_with_passage_wrong"]["k"] == 1


def test_no_answer_set_is_reported_apart():
    N = run()["figures"]["no_answer_set"]
    assert N["questions"] == 2 and N["refused"]["k"] == 1 and N["answered"]["k"] == 1 and N["answered_with_citations"]["k"] == 1
    o = base_outputs(); o[4]["cited"] = []
    assert run(o)["figures"]["no_answer_set"]["answered_with_citations"]["k"] == 0
    rep = run(); assert rep["figures"]["answerable"]["questions"] == 3 and row(rep, "q4")["passage_in_context"] is None


# ---------------------------------------------------------------- gates
def no_figures(rep, gate):
    assert rep["all_gates_pass"] is False and rep["figures"] is None and rep["per_question"] is None and rep["gates"][gate]["pass"] is False


def test_gate_no_answer_set():
    no_figures(run(min_no_answer=3), "no_answer_set"); assert run(min_no_answer=2)["all_gates_pass"] is True


def test_gate_complete():
    no_figures(run(base_outputs()[:4]), "complete")
    no_figures(run(base_outputs() + [base_outputs()[0]]), "complete")
    q = json.loads(json.dumps(QUESTIONS)); q[0]["gold_passage_spans"][0]["end"] = 10 ** 6; no_figures(run(questions=q), "complete")
    q = json.loads(json.dumps(QUESTIONS)); q[0]["gold_file_ids"] = ["no-such-file"]; q[0]["gold_passage_spans"][0]["file_id"] = "no-such-file"; rep = run(questions=q); no_figures(rep, "complete")
    assert rep["gates"]["complete"]["gold_files_without_reference_text"] == 1
    q = json.loads(json.dumps(QUESTIONS)); q[0]["gold_file_ids"] = ["harbor-log", "no-such-file"]; rep = run(questions=q); no_figures(rep, "complete")
    assert rep["gates"]["complete"]["gold_files_without_reference_text"] == 1 and rep["gates"]["complete"]["spans_outside_their_file"] == 0
    q = json.loads(json.dumps(QUESTIONS)); q[3]["answerable"] = True; no_figures(run(questions=q), "complete")
    q = json.loads(json.dumps(QUESTIONS)); q[0]["gold_passage_spans"] = []; no_figures(run(questions=q), "complete")
    q = json.loads(json.dumps(QUESTIONS)); q[0]["gold_passage_spans"][0] = {"file_id": "bread-notes", "start": 0, "end": 5}; rep = run(questions=q); no_figures(rep, "complete")
    assert rep["gates"]["complete"]["spans_outside_their_file"] == 1


def test_gate_train_test_overlap(tmp_path):
    clean = tmp_path / "clean.txt"; clean.write_text(E.digest("something else") + "\n" + E.digest("another item") + "  note\n", encoding="utf-8")
    rep = run(overlap_list=str(clean)); g = rep["gates"]["train_test_overlap"]
    assert rep["all_gates_pass"] is True and g == {"digests_in_the_list": 2, "overlap": 0, "planted_control_found": True, "pass": True}
    leaked = tmp_path / "leaked.txt"; leaked.write_text(E.digest(E.normalize("  全麥吐司要用幾度烤多久？ ").casefold()) + "\n", encoding="utf-8")
    rep = run(overlap_list=str(leaked)); no_figures(rep, "train_test_overlap"); assert rep["gates"]["train_test_overlap"]["overlap"] == 1
    assert run()["gates"]["train_test_overlap"]["pass"] is True and "skipped" in run()["gates"]["train_test_overlap"]


def test_gate_located():
    o = base_outputs(); o[0]["retrieved"][0] = {"file_id": "harbor-log", "text": "A passage the file does not contain at all, long enough to be looked for by its anchors, and still absent."}
    rep = run(o); no_figures(rep, "located"); assert rep["gates"]["located"]["not_located"] == 1 and rep["gates"]["located"]["passages_given_as_text"] == 7
    rep = run(o, max_not_located=0.2); assert rep["all_gates_pass"] is True and row(rep, "q1")["passage_hit"]["3"] is True
    o[0]["retrieved"][0] = {"file_id": "a-file-outside-the-reference", "text": "anything"}
    assert run(o, max_not_located=0.2)["gates"]["located"]["not_located"] == 1


# ---------------------------------------------------------------- paired comparison
def test_exact_mcnemar_and_smallest_detectable():
    assert E.binom_two_sided(8, 1) == pytest.approx(0.0390625) and E.binom_two_sided(1, 8) == pytest.approx(0.0390625)
    assert E.binom_two_sided(5, 5) == 1.0 and E.binom_two_sided(0, 0) == 1.0 and E.binom_two_sided(3, 2) == 1.0
    assert E.smallest_detectable(6) == 6 and E.smallest_detectable(5) is None and E.smallest_detectable(9) == 7 and E.smallest_detectable(0) is None


def test_compare_two_systems_on_the_same_questions():
    a = run()["per_question"]; o = base_outputs(); o[0]["retrieved"] = [p("bread-notes", 0)]; b = run(o)["per_question"]
    C = E.compare(a, b, "passage_hit@3"); f = C["figures"]
    assert C["pass"] and (f["a_only"], f["b_only"], f["both"], f["neither"]) == (1, 0, 1, 1) and f["difference_a_minus_b"] == pytest.approx(1 / 3)
    assert f["mcnemar_exact_p"] == 1.0 and f["difference_wald95"][0] < 1 / 3 < f["difference_wald95"][1] and f["smallest_detectable_imbalance_at_this_number_of_discordant_pairs"] is None
    assert E.compare(b, a, "passage_hit@3")["figures"]["difference_a_minus_b"] == pytest.approx(-1 / 3)
    assert E.compare(a, b, "file_hit@1")["figures"]["a_only"] == 1
    assert E.compare(a, [r for r in b if r["id"] != "q1"], "passage_hit@3") == {"pass": False, "why": "the two reports are not about the same questions", "figures": None}


# ---------------------------------------------------------------- the program as it is called
def files(tmp_path, outputs=None):
    ref = tmp_path / "reference"; ref.mkdir()
    for k, v in RAW.items():
        (ref / (k + ".txt")).write_text(v, encoding="utf-8")
    q = tmp_path / "questions.jsonl"; q.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in QUESTIONS) + "\n", encoding="utf-8")
    o = tmp_path / "outputs.jsonl"; o.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in (outputs or base_outputs())) + "\n", encoding="utf-8")
    return str(q), str(o), str(ref)


def call(*args):
    return subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(E.__file__)), "rag_eval.py"), *args], capture_output=True, text=True, encoding="utf-8")


def test_command_line_exit_codes_and_no_text_in_the_report(tmp_path):
    q, o, ref = files(tmp_path); out = str(tmp_path / "report.json")
    r = call("score", "--questions", q, "--outputs", o, "--reference-dir", ref, "--out", out, "--no-overlap-list", "--k", "1,3")
    assert r.returncode == 3 and json.load(open(out, encoding="utf-8"))["figures"] is None          # five questions: the no-answer set is too small
    r = call("score", "--questions", q, "--outputs", o, "--reference-dir", ref, "--out", out, "--no-overlap-list", "--k", "1,3", "--min-no-answer", "2")
    assert r.returncode == 0, r.stderr
    text = open(out, encoding="utf-8").read(); rep = json.loads(text)
    assert rep["figures"]["answerable"]["passage_level"]["hit@3"]["k"] == 2 and rep["inputs"]["questions"]["n"] == 5 and len(rep["inputs"]["questions"]["sha256"]) == 64
    for secret in [x["question"] for x in QUESTIONS] + [x["answer"] for x in base_outputs()] + [s for d in DOCS.values() for s in d]:
        assert secret not in text
    assert call("score", "--questions", q, "--outputs", o, "--reference-dir", ref, "--out", out).returncode == 2      # the overlap list is asked for by name or waived by name


def test_command_line_compare(tmp_path):
    q, o, ref = files(tmp_path); a = str(tmp_path / "a.json"); b = str(tmp_path / "b.json"); c = str(tmp_path / "c.json")
    common = ["--questions", q, "--reference-dir", ref, "--no-overlap-list", "--k", "1,3"]
    assert call("score", *common, "--outputs", o, "--out", a, "--min-no-answer", "2").returncode == 0
    assert call("score", *common, "--outputs", o, "--out", b).returncode == 3
    r = call("compare", "--a", a, "--b", b, "--out", c, "--metric", "passage_hit@3"); assert r.returncode == 3 and json.load(open(c, encoding="utf-8"))["figures"] is None
    assert call("score", *common, "--outputs", o, "--out", b, "--min-no-answer", "2").returncode == 0
    r = call("compare", "--a", a, "--b", b, "--out", c, "--metric", "passage_hit@3"); f = json.load(open(c, encoding="utf-8"))["figures"]
    assert r.returncode == 0 and f["a_only"] == 0 and f["b_only"] == 0 and f["both"] == 2 and f["questions"] == 3
    other = tmp_path / "other"; other.mkdir(); q2, o2, ref2 = files(other, base_outputs())
    open(q2, "a", encoding="utf-8").write("\n")                             # another question file by its bytes
    assert call("score", "--questions", q2, "--outputs", o2, "--reference-dir", ref2, "--no-overlap-list", "--k", "1,3", "--out", b, "--min-no-answer", "2").returncode == 0
    assert call("compare", "--a", a, "--b", b, "--out", c).returncode == 3
