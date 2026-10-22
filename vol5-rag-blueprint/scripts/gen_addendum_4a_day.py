#!/usr/bin/env python3
"""Vol.5 · writes supplement 4A to the night-1 pre-registration: the day's work without the card, (1) the
num_candidates probe on HotpotQA's whole-corpus index and (2) MIRACL zh's whole corpus in the Blueprint's
Elasticsearch, measured as C1 was. With its .sha256 file. Run once, before the first search of either.
Supplement 4B (the night: clean-window latency, arm P, C3, cell R, MIRACL zh P) is written separately.
usage: gen_addendum_4a_day.py [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE); REPO = os.path.dirname(V5)
RES = os.path.join(V5, "results", "night1"); OUT = os.path.join(RES, "addendum_4a_day.json"); DRAFT = "--draft" in sys.argv


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


c1 = json.load(open(os.path.join(RES, "c1_score.json"), encoding="utf-8"))
rec = {
 "what": "supplement 4A to the night-1 pre-registration: two pieces of work on the CPU only, ruled on 2026-10-20 (third supplement to the design ticket)",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": f, "sha256": sha(os.path.join(RES, f))} for f in ("prediction_v5_night1.json", "addendum_1_control_a_program.json", "addendum_2_control_b_exact.json", "addendum_3_c2_n_o.json")],
 "num_candidates_probe": {
   "why": "C1's default query (k = num_candidates = 100) gave nDCG@10 %.4f against Vol.4's exact 0.80079 on the same vectors (known before this supplement)" % c1["metrics"]["ndcg_cut_10"],
   "the_blueprint_knob": "one setting moves both numbers: VECTOR_DB_TOPK (or a request's vdb_top_k). The Blueprint passes k = fetch_k = top_k (utils/vdb/elasticsearch/elastic_vdb.py, retrieval_langchain) and langchain-elasticsearch 1.0.0 in the rag-server image passes num_candidates = fetch_k (_sync/vectorstores.py:481). The Blueprint accepts 1..400 (rag_server/validation.py:139). The same number is the count of passages sent to the reranker",
   "settings": {"blueprint": "k = num_candidates = 200 and 400 (400 is the Blueprint's limit); all returned passages kept, the quality read on the first 100",
                "es_only": "k = 100, num_candidates = 200, 500 and 1000 (the search engine's own setting; the ruling's 500 and 1000 are beyond the Blueprint's knob, so they are listed apart)"},
   "unchanged": "the index (the same one, no force-merge), the mapping's rescore_vector oversample 3.0, the query vectors",
   "measured": "per setting, all 7,405 questions: overlap at 10 and 100 with Vol.4's exact run, nDCG@10 and Recall@100; the index's segment count (_cat/segments) before the probe",
   "latency": "not measured (latency_not_measured: daytime_host); the clean window of the night times a fixed 1,000 questions",
   "program": "scripts/es_num_candidates.py (the query of es_ann_vs_exact.py, imported)",
   "expectation": "quality rises with num_candidates and stays below the exact search at every setting; confidence low"},
 "miracl_zh_index": {
   "precondition": "at least 80 GB free on the disk after the load (the index of HotpotQA took 52.9 GB for 5.2 million passages)",
   "load": "es_bulk_load.py, unchanged, into index miracl_zh_whole with the captured mapping and metadata template; MIRACL zh's 4,934,368 passages with Vol.4's vectors from the 16-bit store",
   "validity_gate": "a 100,000-passage slice (the first 100,000 in corpus order) loaded by the same program into miracl_zh_slice100k; Elasticsearch's exact search there against numpy's exact search over the same vectors for the first 200 question ids (sorted) of MIRACL zh dev: every question equal once equal-score swaps at the 100th place are set aside (exact_equal_check.py, tie 5e-5). Not passed: no figure of the zh index is reported",
   "measured": "as C1: the default query (k = num_candidates = 100) for all 393 dev questions: overlap at 10 and 100 with Vol.4's exact run (whole-corpus run of the published volume), nDCG@10 and Recall@100 with MIRACL's dev judgements; negative control (k 10, num_candidates 10, no rescore) at least 0.05 lower at 10; 5 questions by brute force on the whole index against Vol.4's exact; load seconds, index size, Docker VM memory every 30 s",
   "latency": "not measured by day (latency_not_measured: daytime_host); the clean window of the night times it",
   "qrels": "qrels.miracl-v1.0-zh-dev.tsv is in TREC form; it is read as TREC (a copy with the .trec extension, bytes unchanged)",
   "expectation": "overlap at 100 below HotpotQA's 0.784 or near it; nDCG@10 below Vol.4's exact; confidence low"},
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/es_num_candidates.py", "scripts/es_ann_vs_exact.py", "scripts/es_bulk_load.py", "scripts/exact_equal_check.py", "scripts/slice_exact.py")},
 "generator": "scripts/gen_addendum_4a_day.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen supplement 4A exists")
json.dump(rec, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + rec["written_at"], sha(OUT))
