#!/usr/bin/env python3
"""Vol.5 · the diagnosis of control (b) of night 1 (2026-10-18), no card used: the overlaps of the five runs on the
100,000-passage slice (approximate and exact search on the index written by the Blueprint's ingestor and on the index
written by es_bulk_load.py, and numpy's exact search); the text the ingestor stored for each passage against the file
uploaded (identical, only the end missing, changed inside, split into more than one chunk); the cosine of the
ingestor's vectors against Vol.4's vectors of the same passages, for a seeded sample of each class.
Elasticsearch at 127.0.0.1:9200 (the night's container). Run from the vol5-wip worktree. Writes one JSON.
usage: control_b_diagnosis.py HOLD_NIGHT1 FP16_DIR CHECKPOINTS OUT_JSON"""
import collections, json, os, random, statistics as st, sys, time
import numpy as np, requests
sys.path.insert(0, "vol4-retriever/scripts"); import fp16_store as F, search_whole_corpus as S
H, FP, CK, OUT = sys.argv[1:5]; ES = "http://127.0.0.1:9200"

def run(p):
    r = collections.defaultdict(list)
    for l in open(os.path.join(H, p)):
        q, _, d, k, s, _t = l.split(); r[q].append((int(k), d))
    return {q: [d for _, d in sorted(v)] for q, v in r.items()}
R = {"numpy_exact": run("diag_numpy_exact_b100.trec"), "bulk_exact": run("diag_exact_slice_bulk.trec"), "ingestor_exact": run("diag_exact_slice_ingestor.trec"),
     "bulk_ann": run("control_b_slice_bulk.trec"), "ingestor_ann": run("control_b_slice_ingestor.trec")}
qs = sorted(R["numpy_exact"])
def ov(a, b, k):
    v = [len(set(R[a][q][:k]) & set(R[b][q][:k])) / k for q in qs]
    return {"mean": round(st.mean(v), 4), "lowest": min(v), "under_0.9": sum(x < 0.9 for x in v)}
pairs = [("bulk_exact", "numpy_exact"), ("ingestor_exact", "numpy_exact"), ("ingestor_exact", "bulk_exact"), ("bulk_ann", "bulk_exact"),
         ("ingestor_ann", "ingestor_exact"), ("ingestor_ann", "bulk_ann")]
overlaps = {f"{a} vs {b}": {"at_10": ov(a, b, 10), "at_100": ov(a, b, 100)} for a, b in pairs}

r = requests.post(f"{ES}/slice_ingestor/_search?scroll=5m", json={"size": 5000, "_source": ["text", "metadata.content_metadata.filename"]}).json(); sid = r["_scroll_id"]
docs = collections.defaultdict(list)
while r["hits"]["hits"]:
    for h in r["hits"]["hits"]:
        docs[h["_source"]["metadata"]["content_metadata"]["filename"][:-4]].append(h["_source"]["text"])
    r = requests.post(f"{ES}/_search/scroll", json={"scroll": "5m", "scroll_id": sid}).json()
c = collections.Counter(); cls = {}; dropped = collections.Counter()
for p, v in docs.items():
    t = open(os.path.join(H, "slice_txt", p + ".txt"), encoding="utf-8").read(); na = any(ord(ch) > 127 for ch in t); c["passages_with_non_ascii"] += na
    if len(v) > 1: c["split_into_two_or_more"] += 1; c["extra_documents"] += len(v) - 1; cls[p] = "split"; continue
    s = v[0]
    if s == t: c["identical"] += 1; cls[p] = "identical"
    elif s == t[:len(s)] and len(s) < len(t):
        c["only_the_end_missing"] += 1; cls[p] = "end"; c["end_missing_one_character" if len(t) - len(s) == 1 else "end_missing_a_word"] += 1
        if len(t) - len(s) == 1: dropped[t[-1]] += 1
    else: c["changed_inside"] += 1; c["changed_inside_with_non_ascii"] += na; cls[p] = "inside"

pieces, _, _ = S.pieces_from_checkpoints(CK); vecs, pids, rows = [], [], 0
for vf, vsha, idf, idsha, n in pieces:
    if rows >= 100000: break
    v, _ = F.piece_from_fp16(os.path.join(FP, vf), vsha); take = min(n, 100000 - rows)
    vecs.append(v[:take]); pids += json.load(open(os.path.join(FP, idf), encoding="utf-8"))[:take]; rows += take
X = np.concatenate(vecs).astype(np.float64); pos = {p: i for i, p in enumerate(pids)}
random.seed(20261018); byc = collections.defaultdict(list)
for k in ("end", "inside", "split"):
    pool = sorted(p for p, x in cls.items() if x == k); byc[k] = random.sample(pool, min(200, len(pool)))
cos = {}
for k, sample in byc.items():
    vals = []
    for p in sample:
        for h in requests.post(f"{ES}/slice_ingestor/_search", json={"size": 10, "_source": ["vector"], "query": {"term": {"metadata.content_metadata.filename.keyword": p + ".txt"}}}).json()["hits"]["hits"]:
            v = np.array(h["_source"]["vector"], dtype=np.float64); w = X[pos[p]]; vals.append(float(v @ w / np.linalg.norm(v) / np.linalg.norm(w)))
    cos[k] = {"passages": len(sample), "vectors": len(vals), "min": round(min(vals), 5), "median": round(float(np.median(vals)), 5), "max": round(max(vals), 5)}
rec = {"written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "questions": len(qs), "overlaps": overlaps, "ingestor_text": dict(c),
       "dropped_last_character_top": dropped.most_common(6), "cosine_ingestor_vs_vol4_by_class": cos,
       "sources": {"split_text": "nv-ingest 26.3.0 image, nv_ingest_api/internal/transform/split_text.py:103 `text[chunk[0][0] : chunk[-1][0]]` (slice ends at the start of the last token)",
                   "decoding": "ingestor-server 2.6.0 image, nv_ingest_client/util/file_processing/extract.py:111-118 charset_normalizer.detect then decode"}}
json.dump(rec, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
print(json.dumps({"ingestor_text": dict(c), "cos": cos}))
