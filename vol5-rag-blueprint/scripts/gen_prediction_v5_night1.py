#!/usr/bin/env python3
"""Vol.5 · writes the pre-registration of the volume's first night under the design ticket: the two positive controls
of the deviations, and cell C1 (the Blueprint's default vector store against exact search) on BEIR HotpotQA's whole
corpus. With its .sha256 file. Run once, before the night's first container.
usage: gen_prediction_v5_night1.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE); REPO = os.path.dirname(V5)
RES = os.path.join(V5, "results", "night1"); OUT = os.path.join(RES, "prediction_v5_night1.json")
DRAFT = "--draft" in sys.argv


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def image(im):
    out = subprocess.run(["docker", "image", "inspect", im, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {im}")
    return {"image": im, "id": out}


qcheck = json.load(open(os.path.join(V5, "results", "question_set", "hotpotqa_check_hf_mirror.json"), encoding="utf-8"))
pred = {
 "what": "Vol.5, night 1: the two positive controls of the volume's three deviations from the RAG Blueprint v2.6.2, and cell C1 on BEIR HotpotQA's whole corpus (5,233,329 passages): the Blueprint's default vector store, Elasticsearch 9.3.0 with the index type its server applies, against Vol.4's exact search on the same vectors",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "authorised_by": "the design ticket of 2026-10-18 for Vol.5 (cells on the card only when the owner says start)",
 "settings": "BLUEPRINT_SETTINGS.md (every default quoted with file and line; the three deviations)",
 "question_set": {"id_table": "results/question_set/hotpotqa_ids.jsonl", "check": "results/question_set/hotpotqa_check_hf_mirror.json",
                  "all_matched": qcheck["all_matched"], "source_used": qcheck["source_file"],
                  "official_file": "http://curtis.ml.cmu.edu/datasets/hotpot/hotpot_dev_fullwiki_v1.json did not answer on 2026-10-18 (03:04, 03:05, 03:19 +0800); the matching ran on the Hugging Face copy and is run again on the official file when it can be fetched"},
 "images": {"elasticsearch": image("docker.elastic.co/elasticsearch/elasticsearch:9.3.0"), "rag_server": image("nvcr.io/nvidia/blueprint/rag-server:2.6.0"),
            "ingestor_server": image("nvcr.io/nvidia/blueprint/ingestor-server:2.6.0"), "nv_ingest": image("nvcr.io/nvidia/nemo-microservices/nv-ingest:26.3.0"),
            "embedding_nim": image("nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2"), "es_client": image("vol5-es-client:es8.19.3") | {"dockerfile": "client_es/Dockerfile"}},
 "elasticsearch_as_shipped": {"compose": "deploy/compose/vectordb.yaml lines 90-126: single node, ES_JAVA_OPTS -Xms1024m -Xmx1024m, security off, basic licence, not on the card",
                              "index_type_read_back": "a 9.3.0 node given a 2,048-dimension cosine dense_vector with no index_options (the Blueprint's mapping) reports index_options {type: bbq_hnsw, m: 16, ef_construction: 100, rescore_vector: {oversample: 3.0}} (path test, 2026-10-18 03:1x, read with include_defaults); read again from the real indexes",
                              "query": "kNN, k = num_candidates = 100 (elastic_vdb.py:1107 with VECTOR_DB_TOPK 100)"},
 "control_a": {"what": "the query vectors of the Blueprint's own query path (rag-server 2.6.0's get_embedding_model, embed_query) with the swapped model, against Vol.4's query vectors", "questions": "the first 20 ids of the HotpotQA id table, sorted",
               "rule": "cosine at least 0.9999 for every one of the 20; otherwise stop (the ticket's first stop)", "program": "scripts/control_query_vectors.py"},
 "control_b": {"what": "the first 100,000 passages of the HotpotQA corpus (file order) indexed twice: by the Blueprint's ingestor (uploaded as one text file per passage, batches of 500, its default split) and by es_bulk_load.py with the mapping read from the ingestor's index",
               "questions": "the first 100 ids of the HotpotQA id table, sorted", "rule": "mean overlap of the two indexes' top 100 at least 0.99; otherwise stop",
               "if_slow": "if the ingestor has not finished the 100,000 within 2 hours, the control runs on the passages it finished, at least 20,000, and the record says so",
               "programs": ["scripts/ingest_slice_via_blueprint.py", "scripts/es_bulk_load.py", "scripts/es_ann_vs_exact.py"]},
 "C1": {"load": "es_bulk_load.py into a fresh index created with the captured mapping; vectors from the 16-bit store, proven per piece; 200 documents per request; refresh off while loading",
        "measured": {"load_seconds": "first request to the last piece indexed, then to the refresh", "disk": "_cat/indices store.size after the load", "memory": "the Elasticsearch container's memory (docker stats) and the Docker VM's MemAvailable, sampled every 30 s through load and searches; the peak",
                     "overlap": "per query the share of Vol.4's exact top 10 / top 100 found in the store's top 10 / top 100: mean, lowest, queries under 0.9", "quality": "nDCG@10 and Recall@100 of the store's run beside Vol.4's exact 0.80079 / 0.91567",
                     "latency": "c = 1 over the 7,405 queries, the duration of each call in the client container; p50, p99; the first ten apart"},
        "validity_gate": {"rule": "on the 100,000-passage index of control (b) loaded by es_bulk_load.py: script_score exact search for 200 questions must give the top 100 of numpy's exact search on the same vectors, equal scores swapped apart and listed; otherwise no figure of the store is reported (the ticket's second stop)",
                          "why_on_the_slice": "brute force over the whole index reads about 43 GB of vectors per question, more than the Docker VM holds; the slice is loaded by the same program with the same mapping. Five questions are also searched by brute force on the whole index and listed as a supplement",
                          "questions": "the first 200 ids of the HotpotQA id table, sorted"},
        "negative_control": {"what": "k = 10, num_candidates = 10, query rescore_vector.oversample = 0", "rule": "the mean overlap at 10 falls at least 0.05 below the default query's"},
        "branches": {"heap": "if the index cannot be built with the 1 GB heap: the error is the result; one more try with 4 GB (the only change)", "vm_memory": "Docker VM memory at 85%: stop this corpus and record", "disk": "under 60 GB free: no second corpus"},
        "expectation": {"overlap_at_100": "mean between 0.90 and 0.99 (binary quantisation with a threefold rescore)", "ndcg_at_10": "within 0.02 of 0.80079", "latency_p50_ms": "between 5 and 100", "load": "several hours (JSON floats, as the Blueprint sends them)", "confidence": "low"}},
 "not_this_night": ["MIRACL zh (night 2)", "answers (C2, C3)", "co-residence (C4)"],
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/es_bulk_load.py", "scripts/es_ann_vs_exact.py", "scripts/control_query_vectors.py", "scripts/ingest_slice_via_blueprint.py", "scripts/slice_exact.py", "client_es/Dockerfile", "compose_es/night.env", "compose_es/override_ingestor.yaml", "compose_es/override_vectordb.yaml", "eval/hotpotqa_set.py")}
                   | {"vol4-retriever/scripts/fp16_store.py": sha(os.path.join(REPO, "vol4-retriever", "scripts", "fp16_store.py")), "tools/g8_gate.py": sha(os.path.join(REPO, "tools", "g8_gate.py"))},
 "generator": "scripts/gen_prediction_v5_night1.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
os.makedirs(RES, exist_ok=True)
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
