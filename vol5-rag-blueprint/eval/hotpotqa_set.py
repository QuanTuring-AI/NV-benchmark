"""Vol.5 · the HotpotQA question set of the volume: the 7,405 questions of BEIR HotpotQA (test split), matched by id to
the HotpotQA dev set in the fullwiki setting, with each question's answer and the corpus passages that hold its
supporting facts.

The matching is checked, not assumed: every BEIR test query id must be in the source file and the reverse; the answer
and the supporting facts that BEIR keeps in its query metadata must equal the source's; every supporting-fact title
must name exactly one passage of the BEIR corpus (by title); and those passages must be the query's BEIR relevance
judgements. Any difference is counted and listed, never skipped.

The answers are HotpotQA text (CC BY-SA 4.0) and stay outside the repository; what this module writes for the
repository is the id table: query id, question type and level, and the corpus ids of the supporting passages.
Importable: `load_set(beir_dir, source)` returns the checked set; `main` writes the id table and the check record.

usage: hotpotqa_set.py --beir DIR --source FILE(.json|.parquet) --out-ids FILE --out-check FILE
"""
import argparse, collections, hashlib, json, os, sys


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_source(path):
    """id -> {answer, type, level, facts: sorted list of (title, sent_id)} from the official JSON or the parquet copy."""
    out = {}
    if path.endswith(".parquet"):
        import pyarrow.parquet as pq
        for r in pq.read_table(path, columns=["id", "answer", "type", "level", "supporting_facts"]).to_pylist():
            sf = r["supporting_facts"]
            out[r["id"]] = {"answer": r["answer"], "type": r["type"], "level": r["level"], "facts": sorted(zip(sf["title"], sf["sent_id"]))}
    else:
        for r in json.load(open(path, encoding="utf-8")):
            out[r["_id"]] = {"answer": r["answer"], "type": r["type"], "level": r["level"], "facts": sorted((t, int(i)) for t, i in r["supporting_facts"])}
    return out


def read_beir(beir_dir):
    qrels = collections.defaultdict(set)
    with open(os.path.join(beir_dir, "qrels", "test.tsv"), encoding="utf-8") as f:
        next(f)
        for line in f:
            q, d, s = line.rstrip("\n").split("\t")
            if int(s) > 0:
                qrels[q].add(d)
    queries = {}
    with open(os.path.join(beir_dir, "queries.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["_id"] in qrels:
                m = r.get("metadata") or {}
                queries[r["_id"]] = {"answer": m.get("answer"), "facts": sorted((t, int(i)) for t, i in m.get("supporting_facts", []))}
    return queries, qrels


def titles_to_ids(beir_dir, wanted):
    """title -> list of corpus ids, for the titles in `wanted` only (one pass over the corpus)."""
    found = collections.defaultdict(list)
    with open(os.path.join(beir_dir, "corpus.jsonl"), encoding="utf-8") as f:
        for line in f:
            i = line.find('"title": "')
            if i < 0:
                continue
            r = json.loads(line)
            if r["title"] in wanted:
                found[r["title"]].append(r["_id"])
    return found


def load_set(beir_dir, source):
    src = read_source(source)
    queries, qrels = read_beir(beir_dir)
    titles = {t for q in queries for t, _ in src.get(q, {}).get("facts", [])}
    t2id = titles_to_ids(beir_dir, titles)
    check = {"beir_test_queries": len(queries), "source_questions": len(src),
             "in_beir_not_in_source": sorted(set(queries) - set(src))[:20], "in_source_not_in_beir": sorted(set(src) - set(queries))[:20],
             "answer_differs": [], "facts_differ": [], "title_not_one_passage": [], "passages_not_the_judgements": []}
    rows = []
    for q in sorted(queries):
        if q not in src:
            continue
        s, b = src[q], queries[q]
        if b["answer"] is not None and b["answer"] != s["answer"]:
            check["answer_differs"].append(q)
        if b["facts"] and b["facts"] != s["facts"]:
            check["facts_differ"].append(q)
        ids = []
        for t in sorted({t for t, _ in s["facts"]}):
            hit = t2id.get(t, [])
            if len(hit) != 1:
                check["title_not_one_passage"].append([q, t, len(hit)])
            ids += hit
        if set(ids) != qrels[q]:
            check["passages_not_the_judgements"].append(q)
        rows.append({"query_id": q, "type": s["type"], "level": s["level"], "gold_passages": sorted(ids), "answer": s["answer"]})
    check["counts"] = {k: len(v) for k, v in check.items() if isinstance(v, list)}
    check["all_matched"] = all(n == 0 for n in check["counts"].values()) and len(rows) == len(queries) == len(src)
    return rows, check


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beir", required=True); ap.add_argument("--source", required=True); ap.add_argument("--out-ids", required=True); ap.add_argument("--out-check", required=True)
    a = ap.parse_args()
    rows, check = load_set(a.beir, a.source)
    check["source_file"] = {"name": os.path.basename(a.source), "sha256": sha256_file(a.source)}
    check["beir_files"] = {f: sha256_file(os.path.join(a.beir, f)) for f in ("queries.jsonl", "qrels/test.tsv")}
    os.makedirs(os.path.dirname(os.path.abspath(a.out_ids)), exist_ok=True)
    with open(a.out_ids, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps({k: r[k] for k in ("query_id", "type", "level", "gold_passages")}) + "\n")
    json.dump(check, open(a.out_check, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({"rows": len(rows), **check["counts"], "all_matched": check["all_matched"]}))
    return 0 if check["all_matched"] else 1


if __name__ == "__main__":
    sys.exit(main())
