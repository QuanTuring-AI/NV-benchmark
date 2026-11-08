#!/usr/bin/env python3
"""Vol.5 · the minimal reproduction of the two ingestion behaviours: reads back from Elasticsearch the text the
Blueprint's ingestor stored for each file of issue_repro/ (uploaded with ingest_slice_via_blueprint.py ingest) and
compares it with the file's UTF-8 text.
usage: issue_repro_readback.py --es URL --index NAME --dir DIR --out FILE
"""
import argparse, glob, json, os

ap = argparse.ArgumentParser()
for x in ("--es", "--index", "--dir", "--out"):
    ap.add_argument(x, required=True)
a = ap.parse_args()
import requests
rows = []
for f in sorted(glob.glob(os.path.join(a.dir, "*.txt"))):
    name = os.path.basename(f); text = open(f, encoding="utf-8").read()
    hits = requests.post(f"{a.es}/{a.index}/_search", json={"size": 10, "_source": ["text"], "query": {"term": {"metadata.content_metadata.filename.keyword": name}}}).json()["hits"]["hits"]
    stored = [h["_source"]["text"] for h in hits]
    rows.append({"file": name, "uploaded": text, "stored": stored, "chunks": len(stored), "identical": stored == [text],
                 "stored_is_a_prefix": len(stored) == 1 and text.startswith(stored[0]) and stored[0] != text,
                 "missing_end": text[len(stored[0]):] if len(stored) == 1 and text.startswith(stored[0]) else None})
json.dump({"index": a.index, "files": rows}, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
for r in rows:
    print(json.dumps({k: r[k] for k in ("file", "chunks", "identical", "stored_is_a_prefix", "missing_end")}, ensure_ascii=True))
