#!/usr/bin/env python3
"""Vol.5 · writes the pre-registration of the text-layer ingestion of the corpus list through the RAG Blueprint and of
three probes through its answering path, with its .sha256 file. Run once, before the first container of these cells.
usage: gen_prediction_ingestion_and_generation.py --list LIST.json --probes PROBES.json [--draft]
       (both files lie outside the repository; only their SHA-256 values and counts are written here)
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = os.path.join(VOL, "results", "ingestion_and_generation"); OUT = os.path.join(RES, "prediction_ingestion_and_generation.json"); DRAFT = "--draft" in sys.argv
LIST = sys.argv[sys.argv.index("--list") + 1]; PROBES = sys.argv[sys.argv.index("--probes") + 1]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


L = json.load(open(LIST, encoding="utf-8"))["files"]; P = json.load(open(PROBES, encoding="utf-8"))
fmt = {}
for f in L:
    fmt.setdefault(f["format"], {"files": 0, "text_layer_characters": 0}); fmt[f["format"]]["files"] += 1; fmt[f["format"]]["text_layer_characters"] += f["text_layer_characters"]
SCRIPTS = ["ingest_corpus_smoke.py", "ingest_text_only_smoke.py", "rag_probe.py", "smoke_step.py"]; RECIPE = ["text_only.env", "generation.env", "override.yaml", "override_milvus_cpu.yaml", "prompt_overrides_none.yaml", "up.sh", "up_generation.sh"]
pred = {
 "what": "Pre-registration: the corpus list through the text-only ingestion path of the NVIDIA RAG Blueprint v2.6.2, then three probes through its answering path with Nemotron 3 Nano as the answer model, all on one card",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "host": "one RTX 5090 (32 GB), Windows 11 + Docker Desktop (WSL2), graphics driver 610.88",
 "corpus": {"what": "a corpus of public ESG regulations and standards from Taiwan (with EU, US and Japan jurisdictions); the list and the files are outside the repository until the list has been reviewed for publication",
            "list_sha256": sha(LIST), "files": len(L), "by_format": fmt, "named_in_results_by": "the id of the list (<jurisdiction>-<number>); the files are sent as copies named <id>.<extension>"},
 "cell_5_ingestion": {
  "recipe": "compose_text_only/ (README there): Milvus (CPU image), etcd, SeaweedFS, the text embedding NIM llama-nemotron-embed-1b-v2 1.13.0, redis, the ingestion runtime (nv-ingest 26.3.0) and the ingestor server; "
            "text extraction from the PDF's own text layer (pdfium), tables, charts, infographics and images off; no extraction NIM is started",
  "why_text_only": "the extraction NIMs this Blueprint release names do not become ready on this host (EXTRACTION_NIMS_ON_WSL2.md); the visual path is measured with the newer library in results/visual_path/",
  "program": "ingest_corpus_smoke.py: one upload per file, the Blueprint's default split (512 tokens, overlap 150), no summary", "limits_s": {"services ready": 900, "one file": 600},
  "recorded": "per file: status codes, seconds, task state, chunk count (difference of the row counts in Milvus), for a failure the first 300 characters of the server's message; the card's highest memory, the containers' memory. No text."},
 "cell_6_generation": {
  "after_ingestion": "the ingestor server, the ingestion runtime and redis are stopped; Milvus and the embedding NIM stay",
  "started": {"reranker": "llama-nemotron-rerank-1b-v2 1.10.0 (the Blueprint's compose service and default model)",
              "answer model": "nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12, NVFP4 profile 1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada, NIM_MAX_MODEL_LEN=16384, NIM_KVCACHE_PERCENT=0.650 "
                              "(the smallest budget that started on this card: README section 2), NIM_PASSTHROUGH_ARGS=\"--max-num-seqs 32 --reasoning-parser nemotron_v3\"",
              "RAG server": "nvcr.io/nvidia/blueprint/rag-server:2.6.0 with compose_text_only/generation.env"},
  "what_is_not_a_blueprint_default": ["the answer model (the default is a 120B model on two cards)", "LLM_MAX_TOKENS=2048 (default 16256, which with ten retrieved chunks does not fit a context of 16,384 tokens)",
                                      "the reasoning parser on the answer model's server (without it this model's reasoning is part of the answer text: the judge study of Vol.3)",
                                      "the text embedding model and Milvus, as in the ingestion recipe"],
  "probes": {"file_sha256": sha(PROBES), "n": len(P), "what": "three questions given for this purpose; they show whether the path works and are not part of any question set",
             "per_probe": [{"id": p["id"], "lang": p["lang"], "expected": p["expected"], "question_sha256": hashlib.sha256(p["question"].encode("utf-8")).hexdigest(),
                            "expected_among_the_citations": p.get("expected_file_names")} for p in P]},
  "program": "rag_probe.py: POST /generate, streamed, collection given, citations on, every other field at the server's default", "limits_s": {"each service ready": 900, "one probe": 600},
  "recorded": "per probe: status, seconds to the first answer text and to the end, finish reason, usage, the answer's length and digest, whether it reads as a refusal, the citations' fields (document name = the id, type, score, page number, "
              "length and digest of the content). Answer text and passages stay outside the repository."},
 "cell_7_budget": "card memory read after each service is ready (events file) and at the end: what is on the card together during ingestion and during answering",
 "expectations": {
  "ingestion": "all 15 PDFs finish. The 47 Markdown files finish as well (the ingestion library lists md among its text formats; not tried through this ingestor before: low confidence). "
               "Chunks in total between 1,500 and 8,000. The card stays below 8 GiB during ingestion (one embedding NIM).",
  "services": "the reranker, the answer model and the RAG server become ready; the answer model within 600 s. Together with the embedding NIM they fit the card: below 31,500 MiB in use.",
  "probes": "all three return status 200 without a think tag in the answer. Probes 1 and 2 are answered (not a refusal) with at least one citation, and the expected file is among the citations. "
            "Probe 3 asks for something the corpus does not contain: the answer should read as a refusal, but the Blueprint's default prompt tells the model to answer whenever the context is related, "
            "so an answer built from related passages would not surprise (confidence for a refusal: low). First answer text within 30 s, the whole answer within 120 s.",
  "confidence": "moderate for the services and the PDFs; low for Markdown, for probe 3 and for the memory total (the three have not been on this card together)"},
 "branches_decided_in_advance": {"Markdown files are rejected": "the server's message is the result; the files that failed are listed by id and the probes run on what was ingested",
                                 "the answer model does not fit beside the other two": "the reranker is stopped and the probes run without it (ENABLE_RERANKER false in the request); recorded as a second arm, not as a replacement",
                                 "a probe returns an error": "the first 600 characters of the answer are the result"},
 "not_in_this_file": ["any quality figure: there is no question set yet", "files outside the list", "the visual path (tables, charts, scans): results/visual_path/"],
 "harness_sha256": {**{"scripts/" + f: sha(os.path.join(HERE, f)) for f in SCRIPTS}, **{"eval/rag_eval.py": sha(os.path.join(VOL, "eval", "rag_eval.py"))}, **{"compose_text_only/" + f: sha(os.path.join(VOL, "compose_text_only", f)) for f in RECIPE}},
}
os.makedirs(RES, exist_ok=True)
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
