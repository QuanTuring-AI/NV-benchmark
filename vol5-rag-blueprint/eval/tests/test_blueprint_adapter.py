"""Tests of the adapter for the RAG Blueprint's answers. The records are invented in the shape the server returns."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import blueprint_adapter as A  # noqa: E402
import rag_eval as E  # noqa: E402

DOC = "The keeper of Marlow Point lit the lamp at 18:40 on the ninth of March. A new lens, weighing 212 kilograms, was installed in April."
REC = {"id": "q1", "answer": "It weighed 212 kilograms.",
       "citations": {"total_results": 2, "results": [
           {"document_id": "", "document_name": "harbor-log.md", "document_type": "text", "content": "A new lens, weighing 212 kilograms, was installed in April.", "score": 0.91, "metadata": {"page_number": 0}},
           {"document_id": "", "document_name": "harbor-log.pdf", "document_type": "table", "content": "aGVsbG8=", "score": 0.5, "metadata": {"page_number": 3, "description": "lamp | 18:40", "location": [1, 2, 3, 4]}}]}}


def test_text_chunk_keeps_its_text_and_the_file_id_has_no_extension():
    o = A.to_output(REC); r = o["retrieved"][0]
    assert o["id"] == "q1" and o["answer"] == REC["answer"] and o["refused"] is None and o["cited"] is None
    assert r["file_id"] == "harbor-log" and r["text"].startswith("A new lens") and r["score"] == 0.91 and r["type"] == "text"


def test_a_chunk_that_is_not_text_takes_its_description_not_the_image():
    r = A.to_output(REC)["retrieved"][1]
    assert r["text"] == "lamp | 18:40" and r["page"] == 3 and r["file_id"] == "harbor-log"


def test_no_citations_gives_an_empty_list():
    for rec in ({"id": "x", "answer": "", "citations": None}, {"id": "x", "answer": None, "citations": {"total_results": 0, "results": []}}, {"id": "x"}):
        o = A.to_output(rec); assert o["retrieved"] == [] and o["answer"] == ""


def test_the_adapter_output_is_scored():
    span = E.span_of(DOC, "A new lens, weighing 212 kilograms, was installed in April.", "harbor-log")
    q = [{"id": "q1", "question": "How heavy was the lens?", "lang": "en", "answerable": True, "gold_file_ids": ["harbor-log"], "gold_passage_spans": [span], "key_facts": ["212 kilograms"]}]
    rep = E.score(q, [A.to_output(REC)], {"harbor-log": E.normalize(DOC)}, [1, 2], 0, 0, None, 0.5)
    row = rep["per_question"][0]
    assert rep["all_gates_pass"] and row["passage_hit"]["1"] is True and row["correct"] is True and rep["gates"]["located"]["not_located"] == 1
