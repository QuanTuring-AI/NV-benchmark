#!/usr/bin/env python3
"""Vol.5 · loads a whole corpus into the Blueprint's Elasticsearch index with the vectors of Vol.4 (deviation 3 of
BLUEPRINT_SETTINGS.md): the index is created with the mapping the Blueprint's own ingestor wrote for a small collection
(captured to a file on the night), and every document has the shape the Blueprint writes: `text`, `vector`,
`metadata` {`source`, `content_metadata`}, the metadata taken from a document the ingestor wrote, with the passage id
put where the ingestor puts the file name.

  text     Vol.4's passage text: title, one space, text (vol4-retriever/scripts/retrieval_datasets.py passage_text)
  vector   Vol.4's vector of the passage, read from the 16-bit copy and proven against the recorded SHA-256 of its 32-bit
           piece (fp16_store.piece_from_fp16), written as 32-bit floats
  order    the passages of each piece must be the corpus's passages in file order, id by id; a difference stops the load
  batches  200 documents per bulk request (the Blueprint's write_to_index); refresh_interval -1 while loading, then 1s,
           as the Blueprint does
  resume   one line per finished piece in --progress; a second run starts at the first piece not on record

usage: es_bulk_load.py --es URL --index NAME --mapping FILE --metadata FILE --dataset NAME --datasets-root DIR
                       --fp16-dir DIR --checkpoints FILE --progress FILE [--limit N] [--batch 200]
  --mapping   {"settings": ..., "mappings": ...} as read from GET /<index> of the ingestor's collection
  --metadata  one `metadata` object of a document the ingestor wrote, with the string {passage_id} where the
              passage id goes (written by hand from the captured document, and kept beside the results)
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(V5), "vol4-retriever", "scripts"))


def fill(template, passage_id):
    """The metadata template with every '{passage_id}' string replaced."""
    if isinstance(template, dict):
        return {k: fill(v, passage_id) for k, v in template.items()}
    if isinstance(template, list):
        return [fill(v, passage_id) for v in template]
    if isinstance(template, str):
        return template.replace("{passage_id}", passage_id)
    return template


def documents(vectors, ids, corpus_iter, template):
    """One document per passage of a piece; the corpus iterator must yield the same ids in the same order."""
    import retrieval_datasets as R
    for k, pid in enumerate(ids):
        cid, title, text = next(corpus_iter)
        if str(cid) != str(pid):
            raise SystemExit(f"refused: the piece has passage {pid} at row {k}, the corpus has {cid}")
        yield {"text": R.passage_text(title, text), "vector": [float(x) for x in vectors[k]], "metadata": fill(template, str(pid))}


def done_pieces(progress):
    if not os.path.isfile(progress):
        return {}
    return {r["piece"]: r for r in (json.loads(l) for l in open(progress, encoding="utf-8") if l.strip())}


def main():
    ap = argparse.ArgumentParser()
    for a in ("--es", "--index", "--mapping", "--metadata", "--dataset", "--datasets-root", "--fp16-dir", "--checkpoints", "--progress"):
        ap.add_argument(a, required=True)
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--batch", type=int, default=200)
    a = ap.parse_args()
    import fp16_store as F, search_whole_corpus as S, retrieval_datasets as R
    from elasticsearch import Elasticsearch, helpers
    es = Elasticsearch(a.es, request_timeout=300)
    mapping = json.load(open(a.mapping, encoding="utf-8")); template = json.load(open(a.metadata, encoding="utf-8"))
    if not es.indices.exists(index=a.index):
        es.indices.create(index=a.index, settings=mapping.get("settings", {}), mappings=mapping["mappings"])
    es.indices.put_settings(index=a.index, settings={"index": {"refresh_interval": "-1"}})
    pieces, _, total = S.pieces_from_checkpoints(a.checkpoints)
    done = done_pieces(a.progress); corpus = R.load(a.datasets_root, a.dataset).iter_corpus()
    loaded = 0
    try:
        for p, (vf, vsha, idf, idsha, n) in enumerate(pieces):
            if a.limit and loaded >= a.limit:
                break
            if p in done:
                for _ in range(n):
                    next(corpus)
                loaded += n; continue
            t0 = time.time()
            vec, _ = F.piece_from_fp16(os.path.join(a.fp16_dir, vf), vsha)
            if S.sha256_file(os.path.join(a.fp16_dir, idf)) != idsha:
                raise SystemExit(f"refused: {idf} does not have the recorded SHA-256")
            ids = json.load(open(os.path.join(a.fp16_dir, idf), encoding="utf-8"))
            take = min(n, a.limit - loaded) if a.limit else n
            ok, errors = 0, []
            for good, info in helpers.streaming_bulk(es, ({"_index": a.index, "_source": d} for d in documents(vec[:take], ids[:take], corpus, template)),
                                                     chunk_size=a.batch, raise_on_error=False, max_retries=3):
                ok += good
                if not good and len(errors) < 5:
                    errors.append(str(info)[:300])
            rec = {"piece": p, "passages": take, "indexed": ok, "errors": errors, "seconds": round(time.time() - t0, 1), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            open(a.progress, "a", encoding="utf-8", newline="\n").write(json.dumps(rec) + "\n")
            print(json.dumps(rec)); loaded += take
            if ok != take:
                raise SystemExit(f"stopped: piece {p} indexed {ok} of {take}")
    finally:
        es.indices.put_settings(index=a.index, settings={"index": {"refresh_interval": "1s"}})
    es.indices.refresh(index=a.index)
    print(json.dumps({"index": a.index, "count": es.count(index=a.index)["count"], "loaded_this_run_or_before": loaded, "corpus_total": total}))


if __name__ == "__main__":
    main()
