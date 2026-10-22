"""es_bulk_load: the documents it builds (no Elasticsearch needed). Made-up vectors and passages."""
import os, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import es_bulk_load as L  # noqa: E402

TEMPLATE = {"source": {"source_id": "x", "source_name": "{passage_id}"}, "content_metadata": {"type": "text", "page_number": -1}}


def test_fill_puts_the_id_everywhere_it_is_asked():
    m = L.fill(TEMPLATE, "12")
    assert m["source"]["source_name"] == "12" and m["content_metadata"] == TEMPLATE["content_metadata"] and TEMPLATE["source"]["source_name"] == "{passage_id}"


def test_documents_have_the_blueprint_shape_and_vol4_text():
    vec = np.array([[0.6, 0.8], [1.0, 0.0]], np.float32)
    docs = list(L.documents(vec, ["a", "b"], iter([("a", "Title A", "text a"), ("b", "", "text b")]), TEMPLATE))
    assert [sorted(d) for d in docs] == [["metadata", "text", "vector"]] * 2
    assert docs[0]["text"] == "Title A text a" and docs[1]["text"] == "text b"
    assert docs[0]["vector"] == [float(np.float32(0.6)), float(np.float32(0.8))] and docs[1]["metadata"]["source"]["source_name"] == "b"


def test_a_corpus_out_of_order_stops_the_load():
    vec = np.zeros((2, 2), np.float32)
    try:
        list(L.documents(vec, ["a", "b"], iter([("b", "", "x"), ("a", "", "y")]), TEMPLATE))
    except SystemExit as e:
        assert "refused" in str(e); return
    raise AssertionError("an out-of-order corpus was loaded")
