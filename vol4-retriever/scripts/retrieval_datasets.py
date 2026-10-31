#!/usr/bin/env python3
"""Readers for the public retrieval data sets of Vol.4. One interface for all of them: a corpus that is read as a
stream, the queries of one split, and the relevance judgements (qrels) of that split.

No data set file is part of this repository. Every reader takes the folder that holds the downloaded data sets
(`--datasets DIR` or the environment variable VOL4_DATASETS) and reads the files in the layout their publishers ship:

  beir-scifact, beir-hotpotqa      the BEIR project's zip, unpacked:  <root>/<name>/<beir name>/{corpus.jsonl, queries.jsonl, qrels/<split>.tsv}
      corpus.jsonl   one JSON object per line: _id, title, text
      queries.jsonl  one JSON object per line: _id, text
      qrels/*.tsv    a header line, then  query-id <tab> corpus-id <tab> score
  miracl-zh, miracl-ja             the MIRACL project's two repositories:
      <root>/miracl-<lang>/topics/miracl-v1.0-<lang>/topics/topics.miracl-v1.0-<lang>-<split>.tsv    query id <tab> query
      <root>/miracl-<lang>/topics/miracl-v1.0-<lang>/qrels/qrels.miracl-v1.0-<lang>-<split>.tsv      query id, Q0, passage id, relevance (TREC format)
      <root>/miracl-<lang>/corpus/miracl-corpus-v1.0-<lang>/docs-<n>.jsonl.gz                        docid, title, text
  miracl-hn-zh, miracl-hn-ja       the MTEB task MIRACLRetrievalHardNegatives, files as the Hugging Face data set
                                   mteb/MIRACLRetrievalHardNegatives ships them (parquet; needs pyarrow):
      <root>/miracl-hard-negatives/<lang>-corpus/<split>-*.parquet     id, text, title
      <root>/miracl-hard-negatives/<lang>-queries/<split>-*.parquet    id, text
      <root>/miracl-hard-negatives/<lang>-qrels/<split>-*.parquet      query-id, corpus-id, score
      Its queries and judgements are those of MIRACL dev. Its corpus is a reduced one: per query, the passages three
      retrievers ranked highest, pooled. A score on it is not a score on the full MIRACL corpus, and the two must not
      be mixed up: `check_published_counts` stops when the corpus that was loaded has another size.

Rules that every reader follows:
  - the queries of a split are the queries that have at least one line in that split's qrels (the BEIR convention: its
    queries file holds the queries of all splits);
  - a judgement of 0 is kept as 0 (MIRACL judges non-relevant passages explicitly); it is not dropped and not counted
    as relevant;
  - ids are strings, exactly as written in the files;
  - the corpus is never loaded as a whole unless the caller asks for it: `iter_corpus()` yields one passage at a time.

usage: retrieval_datasets.py --datasets DIR [--name beir-scifact] [--split test] [--count-corpus]
       prints the counts of one data set, or of all of them with their default split.
"""
import argparse, glob, gzip, json, os, sys

BEIR = {"beir-scifact": "scifact", "beir-hotpotqa": "hotpotqa"}
MIRACL = {"miracl-zh": "zh", "miracl-ja": "ja"}
MIRACL_HN = {"miracl-hn-zh": "zh", "miracl-hn-ja": "ja"}
MIRACL_HN_FOLDER = "miracl-hard-negatives"
DEFAULT_SPLIT = {"beir-scifact": "test", "beir-hotpotqa": "test", "miracl-zh": "dev", "miracl-ja": "dev", "miracl-hn-zh": "dev", "miracl-hn-ja": "dev"}
NAMES = list(DEFAULT_SPLIT)

# What the publishers state for the dev split of the reduced task; `check_published_counts` compares with these.
#   corpus_passages, queries, qrels_rows            the data-set card of mteb/MIRACLRetrievalHardNegatives at revision
#                                                   d7d94fa4b946cec4a27c84653aa0cf6b33f74a3c: `dataset_info`, num_examples of
#                                                   <lang>-corpus, <lang>-queries, <lang>-qrels
#   corpus_passages, queries, qrels_rows_relevant   MTEB 2.14.3, mteb/descriptive_stats/Retrieval/MIRACLRetrievalHardNegatives.json:
#                                                   num_documents, num_queries, num_relevant_docs
# The two sources agree where they overlap.
PUBLISHED_COUNTS = {
    "miracl-hn-zh": {"corpus_passages": 81309, "queries": 393, "qrels_rows": 3928, "qrels_rows_relevant": 994},
    "miracl-hn-ja": {"corpus_passages": 185319, "queries": 860, "qrels_rows": 8354, "qrels_rows_relevant": 1790},
}


def passage_text(title, text, sep=" "):
    """Title and text as one string. BEIR's own loader joins them with one space when a title is present, and so does
    MTEB 2.14.3 (`mteb/_create_dataloaders.py`, `_corpus_to_dict`: `(row["title"] + " " + row["text"]).strip()`)."""
    title = (title or "").strip()
    return (title + sep + text).strip() if title else (text or "").strip()


class RetrievalDataset:
    def __init__(self, name, split, corpus_files, queries, qrels, source):
        self.name, self.split, self.corpus_files, self.queries, self.qrels, self.source = name, split, corpus_files, queries, qrels, source

    def iter_corpus(self):
        """Yields (passage id, title, text) in file order."""
        for path in self.corpus_files:
            if path.endswith(".parquet"):
                for i, title, text in read_parquet_rows(path, ("id", "title", "text")):
                    yield str(i), title or "", text or ""
                continue
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    yield str(d["_id"] if "_id" in d else d["docid"]), d.get("title") or "", d.get("text") or ""

    def corpus_count(self):
        return sum(1 for _ in self.iter_corpus())

    def summary(self, count_corpus=False):
        judged = sum(len(v) for v in self.qrels.values())
        relevant = sum(1 for v in self.qrels.values() for r in v.values() if r > 0)
        out = {"name": self.name, "split": self.split, "queries": len(self.queries), "qrels_rows": judged, "qrels_rows_relevant": relevant,
               "queries_without_a_relevant_passage": sum(1 for v in self.qrels.values() if not any(r > 0 for r in v.values())), "corpus_files": len(self.corpus_files)}
        if count_corpus:
            out["corpus_passages"] = self.corpus_count()
        return out


def read_qrels_beir(path):
    """BEIR qrels: a header line, then query-id, corpus-id, score separated by tabs."""
    qrels = {}
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        if header[:2] != ["query-id", "corpus-id"]:
            raise ValueError(f"{path}: the first line is not the BEIR qrels header: {header}")
        for n, line in enumerate(f, 2):
            if not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                raise ValueError(f"{path}:{n}: expected 3 tab-separated fields, found {len(parts)}")
            qrels.setdefault(parts[0], {})[parts[1]] = int(parts[2])
    return qrels


def read_qrels_trec(path):
    """TREC qrels: query id, an unused field, passage id, relevance, separated by white space."""
    qrels = {}
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 4:
                raise ValueError(f"{path}:{n}: expected 4 fields, found {len(parts)}")
            qrels.setdefault(parts[0], {})[parts[2]] = int(parts[3])
    return qrels


def load_beir(root, name, split):
    d = os.path.join(root, name, BEIR[name])
    qrels = read_qrels_beir(os.path.join(d, "qrels", split + ".tsv"))
    queries = {}
    with open(os.path.join(d, "queries.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                q = json.loads(line)
                if str(q["_id"]) in qrels:
                    queries[str(q["_id"])] = q["text"]
    missing = sorted(set(qrels) - set(queries))
    if missing:
        raise ValueError(f"{name}/{split}: {len(missing)} queries in the qrels have no text in queries.jsonl")
    return RetrievalDataset(name, split, [os.path.join(d, "corpus.jsonl")], queries, qrels, "BEIR")


def load_miracl(root, name, split):
    lang = MIRACL[name]
    t = os.path.join(root, name, "topics", f"miracl-v1.0-{lang}")
    qrels = read_qrels_trec(os.path.join(t, "qrels", f"qrels.miracl-v1.0-{lang}-{split}.tsv"))
    queries = {}
    with open(os.path.join(t, "topics", f"topics.miracl-v1.0-{lang}-{split}.tsv"), encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                raise ValueError(f"{name} topics line {n}: expected 2 tab-separated fields, found {len(parts)}")
            if parts[0] in qrels:
                queries[parts[0]] = parts[1]
    missing = sorted(set(qrels) - set(queries))
    if missing:
        raise ValueError(f"{name}/{split}: {len(missing)} queries in the qrels have no text in the topics file")
    c = os.path.join(root, name, "corpus", f"miracl-corpus-v1.0-{lang}")
    files = sorted((f for f in os.listdir(c) if f.startswith("docs-") and f.endswith(".jsonl.gz")), key=lambda f: int(f.split("-")[1].split(".")[0]))
    return RetrievalDataset(name, split, [os.path.join(c, f) for f in files], queries, qrels, "MIRACL")


def read_parquet_rows(path, columns):
    """Yields one tuple per row of a parquet file, in file order and in the column order asked for, one batch at a time."""
    try:
        import pyarrow.parquet as pq
    except ImportError as e:
        raise ImportError("the MIRACL hard-negatives files are parquet: install pyarrow (requirements.txt)") from e
    f = pq.ParquetFile(path)
    missing = [c for c in columns if c not in f.schema_arrow.names]
    if missing:
        raise ValueError(f"{path}: no column {missing}; the file has {f.schema_arrow.names}")
    for batch in f.iter_batches(batch_size=8192, columns=list(columns)):
        yield from zip(*(batch.column(c).to_pylist() for c in columns))


def load_miracl_hn(root, name, split):
    lang = MIRACL_HN[name]
    d = os.path.join(root, MIRACL_HN_FOLDER)

    def files(part):
        found = sorted(glob.glob(os.path.join(d, f"{lang}-{part}", f"{split}-*.parquet")))
        if not found:
            raise FileNotFoundError(f"{name}/{split}: no parquet file in {os.path.join(d, lang + '-' + part)}")
        return found

    qrels = {}
    for path in files("qrels"):
        for q, p, score in read_parquet_rows(path, ("query-id", "corpus-id", "score")):
            if str(p) in qrels.setdefault(str(q), {}):
                raise ValueError(f"{path}: query {q} judges one passage twice")
            qrels[str(q)][str(p)] = int(score)
    queries = {}
    for path in files("queries"):
        for q, text in read_parquet_rows(path, ("id", "text")):
            if str(q) in qrels:
                queries[str(q)] = text
    missing = sorted(set(qrels) - set(queries))
    if missing:
        raise ValueError(f"{name}/{split}: {len(missing)} queries in the qrels have no text in the queries file")
    return RetrievalDataset(name, split, files("corpus"), queries, qrels, "MTEB MIRACLRetrievalHardNegatives")


def check_published_counts(dataset, count_corpus=True):
    """Stops with a ValueError when a data set that has published counts was not loaded with exactly those counts.
    The corpus count is what tells the reduced MIRACL task from the full MIRACL corpus: their queries and judgements
    are the same. Counting stops at the first passage past the published number."""
    want = PUBLISHED_COUNTS.get(dataset.name)
    if want is None:
        raise ValueError(f"no published counts are recorded for {dataset.name!r}")
    if dataset.split != DEFAULT_SPLIT[dataset.name]:
        raise ValueError(f"the published counts of {dataset.name} are for the split {DEFAULT_SPLIT[dataset.name]!r}, not {dataset.split!r}")
    s = dataset.summary()
    got = {k: s[k] for k in ("queries", "qrels_rows", "qrels_rows_relevant")}
    if count_corpus:
        n = 0
        for _ in dataset.iter_corpus():
            n += 1
            if n > want["corpus_passages"]:
                break
        got["corpus_passages"] = n
    wrong = {k: {"published": want[k], "loaded": f"more than {want[k]}" if k == "corpus_passages" and v > want[k] else v}
             for k, v in got.items() if v != want[k]}
    if wrong:
        raise ValueError(f"{dataset.name}: the loaded files do not have the published counts: {json.dumps(wrong)}")
    return got


def load(root, name, split=None):
    if not root:
        raise ValueError("the data-set folder is not given: pass --datasets or set VOL4_DATASETS")
    if name not in DEFAULT_SPLIT:
        raise ValueError(f"unknown data set {name!r}; known: {NAMES}")
    split = split or DEFAULT_SPLIT[name]
    if name in BEIR:
        return load_beir(root, name, split)
    return load_miracl_hn(root, name, split) if name in MIRACL_HN else load_miracl(root, name, split)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS")); ap.add_argument("--name", choices=NAMES); ap.add_argument("--split")
    ap.add_argument("--count-corpus", action="store_true", help="read the whole corpus to count its passages (minutes for the large ones)")
    ap.add_argument("--check-published", action="store_true", help="for the data sets that have published counts: stop unless the loaded files have exactly those counts")
    a = ap.parse_args()
    for name in ([a.name] if a.name else NAMES):
        d = load(a.datasets, name, a.split)
        out = d.summary(a.count_corpus)
        if a.check_published and name in PUBLISHED_COUNTS:
            out["published_counts_met"] = check_published_counts(d)
        print(json.dumps(out))


if __name__ == "__main__":
    main()
