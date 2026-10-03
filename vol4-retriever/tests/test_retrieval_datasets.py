"""Tests of retrieval_datasets.py on small synthetic folders built in a temporary directory in the publishers' layouts.
No real data set file is used here or kept in the repository. When VOL4_DATASETS points to the downloaded data sets,
the last test also checks the counts of the real files against the numbers their publishers give."""
import gzip, json, os, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import retrieval_datasets as ds  # noqa: E402


def make_beir(root, name="beir-scifact"):
    d = root / name / ds.BEIR[name]; (d / "qrels").mkdir(parents=True)
    with open(d / "corpus.jsonl", "w", encoding="utf-8") as f:
        for i in range(5):
            f.write(json.dumps({"_id": f"doc{i}", "title": f"Title {i}" if i % 2 == 0 else "", "text": f"text of passage {i}"}) + "\n")
    with open(d / "queries.jsonl", "w", encoding="utf-8") as f:
        for q in ("1", "2", "3"):                       # query 3 belongs to another split
            f.write(json.dumps({"_id": q, "text": f"query {q}"}) + "\n")
    (d / "qrels" / "test.tsv").write_text("query-id\tcorpus-id\tscore\n1\tdoc0\t1\n1\tdoc3\t2\n2\tdoc1\t1\n", encoding="utf-8")
    (d / "qrels" / "train.tsv").write_text("query-id\tcorpus-id\tscore\n3\tdoc4\t1\n", encoding="utf-8")


def make_miracl(root, lang="zh"):
    t = root / f"miracl-{lang}" / "topics" / f"miracl-v1.0-{lang}"; (t / "topics").mkdir(parents=True); (t / "qrels").mkdir()
    (t / "topics" / f"topics.miracl-v1.0-{lang}-dev.tsv").write_text("10#0\t第一個問題\n11#0\t第二個問題\n12#0\t沒有判定的問題\n", encoding="utf-8")
    (t / "qrels" / f"qrels.miracl-v1.0-{lang}-dev.tsv").write_text("10#0 Q0 5#1 1\n10#0 Q0 6#0 0\n11#0 Q0 7#2 1\n", encoding="utf-8")
    c = root / f"miracl-{lang}" / "corpus" / f"miracl-corpus-v1.0-{lang}"; c.mkdir(parents=True)
    for n in (0, 1, 2, 10):                             # by number, docs-10 comes after docs-2; by name it would come before it
        with gzip.open(c / f"docs-{n}.jsonl.gz", "wt", encoding="utf-8") as f:
            f.write(json.dumps({"docid": f"{n}#0", "title": f"標題{n}", "text": f"內文{n}"}, ensure_ascii=False) + "\n")


def test_beir_reader(tmp_path):
    make_beir(tmp_path)
    d = ds.load(str(tmp_path), "beir-scifact")
    assert d.split == "test"
    assert d.queries == {"1": "query 1", "2": "query 2"}            # only the queries of the split's qrels
    assert d.qrels == {"1": {"doc0": 1, "doc3": 2}, "2": {"doc1": 1}}
    corpus = list(d.iter_corpus())
    assert len(corpus) == 5 and corpus[0] == ("doc0", "Title 0", "text of passage 0") and corpus[1] == ("doc1", "", "text of passage 1")
    assert d.summary(count_corpus=True) == {"name": "beir-scifact", "split": "test", "queries": 2, "qrels_rows": 3, "qrels_rows_relevant": 3,
                                            "queries_without_a_relevant_passage": 0, "corpus_files": 1, "corpus_passages": 5}
    assert ds.load(str(tmp_path), "beir-scifact", "train").queries == {"3": "query 3"}


def test_beir_qrels_without_header_is_refused(tmp_path):
    make_beir(tmp_path)
    p = tmp_path / "beir-scifact" / "scifact" / "qrels" / "test.tsv"
    p.write_text("1\tdoc0\t1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        ds.load(str(tmp_path), "beir-scifact")


def test_miracl_reader(tmp_path):
    make_miracl(tmp_path)
    d = ds.load(str(tmp_path), "miracl-zh")
    assert d.split == "dev"
    assert d.queries == {"10#0": "第一個問題", "11#0": "第二個問題"}   # the topic without judgements is not a query of the split
    assert d.qrels == {"10#0": {"5#1": 1, "6#0": 0}, "11#0": {"7#2": 1}}   # a judgement of 0 is kept as 0
    assert [os.path.basename(p) for p in d.corpus_files] == ["docs-0.jsonl.gz", "docs-1.jsonl.gz", "docs-2.jsonl.gz", "docs-10.jsonl.gz"]
    assert [c[0] for c in d.iter_corpus()] == ["0#0", "1#0", "2#0", "10#0"]
    s = d.summary(count_corpus=True)
    assert s["qrels_rows"] == 3 and s["qrels_rows_relevant"] == 2 and s["corpus_passages"] == 4


def test_a_query_of_the_qrels_without_text_is_an_error(tmp_path):
    make_miracl(tmp_path)
    q = tmp_path / "miracl-zh" / "topics" / "miracl-v1.0-zh" / "qrels" / "qrels.miracl-v1.0-zh-dev.tsv"
    q.write_text(q.read_text(encoding="utf-8") + "99#0 Q0 5#1 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no text"):
        ds.load(str(tmp_path), "miracl-zh")


def test_passage_text():
    assert ds.passage_text("Title", "body") == "Title body"
    assert ds.passage_text("", "body") == "body" and ds.passage_text(None, "body") == "body"


def test_unknown_name_and_missing_folder():
    with pytest.raises(ValueError, match="unknown data set"):
        ds.load("somewhere", "beir-nothing")
    with pytest.raises(ValueError, match="not given"):
        ds.load(None, "beir-scifact")


# numbers given by the publishers: BEIR's table (corpus size, test queries) and the MIRACL data-set card (dev queries, passages)
PUBLISHED = {"beir-scifact": {"queries": 300, "corpus_passages": 5183}, "beir-hotpotqa": {"queries": 7405, "corpus_passages": 5233329},
             "miracl-zh": {"queries": 393, "corpus_passages": 4934368}, "miracl-ja": {"queries": 860, "corpus_passages": 6953614}}


@pytest.mark.skipif(not os.environ.get("VOL4_DATASETS"), reason="VOL4_DATASETS is not set: the downloaded data sets are not part of the repository")
@pytest.mark.parametrize("name", list(PUBLISHED))
def test_real_files_have_the_published_counts(name):
    d = ds.load(os.environ["VOL4_DATASETS"], name)
    s = d.summary(count_corpus=bool(os.environ.get("VOL4_COUNT_CORPUS")) or name == "beir-scifact")
    assert s["queries"] == PUBLISHED[name]["queries"]
    assert s["queries_without_a_relevant_passage"] == 0
    if "corpus_passages" in s:
        assert s["corpus_passages"] == PUBLISHED[name]["corpus_passages"]
