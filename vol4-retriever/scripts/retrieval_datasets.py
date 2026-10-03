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

Rules that every reader follows:
  - the queries of a split are the queries that have at least one line in that split's qrels (the BEIR convention: its
    queries file holds the queries of all splits);
  - a judgement of 0 is kept as 0 (MIRACL judges non-relevant passages explicitly); it is not dropped and not counted
    as relevant;
  - ids are strings, exactly as written in the files;
  - the corpus is never loaded as a whole unless the caller asks for it: `iter_corpus()` yields one passage at a time.

usage: retrieval_datasets.py --datasets DIR [--name beir-scifact] [--split test] [--count-corpus]
       prints the counts of one data set, or of all four with their default split.
"""
import argparse, gzip, json, os, sys

BEIR = {"beir-scifact": "scifact", "beir-hotpotqa": "hotpotqa"}
MIRACL = {"miracl-zh": "zh", "miracl-ja": "ja"}
DEFAULT_SPLIT = {"beir-scifact": "test", "beir-hotpotqa": "test", "miracl-zh": "dev", "miracl-ja": "dev"}
NAMES = list(DEFAULT_SPLIT)


def passage_text(title, text, sep=" "):
    """Title and text as one string. BEIR's own loader joins them with one space when a title is present."""
    title = (title or "").strip()
    return (title + sep + text).strip() if title else (text or "").strip()


class RetrievalDataset:
    def __init__(self, name, split, corpus_files, queries, qrels, source):
        self.name, self.split, self.corpus_files, self.queries, self.qrels, self.source = name, split, corpus_files, queries, qrels, source

    def iter_corpus(self):
        """Yields (passage id, title, text) in file order."""
        for path in self.corpus_files:
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


def load(root, name, split=None):
    if not root:
        raise ValueError("the data-set folder is not given: pass --datasets or set VOL4_DATASETS")
    if name not in DEFAULT_SPLIT:
        raise ValueError(f"unknown data set {name!r}; known: {NAMES}")
    split = split or DEFAULT_SPLIT[name]
    return load_beir(root, name, split) if name in BEIR else load_miracl(root, name, split)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default=os.environ.get("VOL4_DATASETS")); ap.add_argument("--name", choices=NAMES); ap.add_argument("--split")
    ap.add_argument("--count-corpus", action="store_true", help="read the whole corpus to count its passages (minutes for the large ones)")
    a = ap.parse_args()
    for name in ([a.name] if a.name else NAMES):
        print(json.dumps(load(a.datasets, name, a.split).summary(a.count_corpus)))


if __name__ == "__main__":
    main()
