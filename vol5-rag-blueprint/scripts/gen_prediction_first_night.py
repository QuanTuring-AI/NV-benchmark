#!/usr/bin/env python3
"""Vol.5 · writes the pre-registration of the first night (2026-10-16), two cells in one file, with its .sha256 file:
V5-A, the Blueprint's default vector-database settings against exact search on Vol.4's whole MIRACL zh corpus, and
V5-B, the Blueprint's query-time services together on the one card. Run once, before the first serving container of
the registered runs.
usage: gen_prediction_first_night.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE); REPO = os.path.dirname(V5)
RES = os.path.join(V5, "results", "first_night"); OUT = os.path.join(RES, "prediction_first_night.json")
DRAFT = "--draft" in sys.argv


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def image(im):
    out = subprocess.run(["docker", "image", "inspect", im, "--format", "{{.Id}} {{json .RepoDigests}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {im}")
    i, _, d = out.partition(" ")
    return {"image": im, "id": i, "repo_digests": json.loads(d)}


def docker_vm_memory():
    r = subprocess.run(["docker", "run", "--rm", "--entrypoint", "sh", "milvusdb/milvus:v2.6.5-gpu", "-c", "grep MemTotal /proc/meminfo"], capture_output=True, text=True).stdout.split()
    return int(r[1]) * 1024


fp16 = json.load(open(os.path.join(REPO, "vol4-retriever", "results", "fp16_store", "summary.json"), encoding="utf-8"))["corpora"]["miracl-zh"]
n, dim = fp16["passages"], 2048
raw = n * dim * 4
vm = docker_vm_memory()
links = n * 2 * 64 * 4

pred = {
 "what": "Vol.5, first night on one RTX 5090 (2026-10-16): V5-A, the RAG Blueprint's (v2.6.2) default vector-database settings against exact search on Vol.4's whole MIRACL zh corpus; V5-B, the Blueprint's query-time services together on the one card, their memory, and one real request to each",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "authorised_by": "the ruling of 2026-10-16 on the first Vol.5 night (two cells, one pre-registration, frozen before the night's first serving container)",
 "V5-A": {
  "question": "how much the Blueprint's default vector-database settings lose against the exact search of Vol.4, on the whole MIRACL zh corpus",
  "blueprint_settings_verbatim": {
   "source": "github.com/NVIDIA-AI-Blueprints/rag tag v2.6.2 (commit f20716d73ae69a544ad4a692f38d6178a64e6f36); the ingestion client inside nvcr.io/nvidia/blueprint/ingestor-server:2.6.0 (nv_ingest_client/util/vdb/milvus.py); the configuration file inside milvusdb/milvus:v2.6.5-gpu (/milvus/configs/milvus.yaml)",
   "database_image": "milvusdb/milvus:v2.6.5-gpu (deploy/compose/vectordb.yaml, profile milvus), KNOWHERE_GPU_MEM_POOL_SIZE 2048;4096",
   "gpu_build_switch": "APP_VECTORSTORE_ENABLEGPUINDEX default False (deploy/compose/docker-compose-ingestor-server.yaml line 51)",
   "gpu_search_switch": "APP_VECTORSTORE_ENABLEGPUSEARCH default False (docker-compose-ingestor-server.yaml line 53; docker-compose-rag-server.yaml line 54)",
   "index_type_variable": "APP_VECTORSTORE_INDEXTYPE default GPU_CAGRA (docker-compose-rag-server.yaml line 42); with the build switch off the client does not use it",
   "index_the_client_builds_with_the_switches_off": "HNSW, M 64, efConstruction 512",
   "metric": "L2",
   "field_type": "FLOAT_VECTOR (32-bit), primary key INT64 auto_id",
   "search_parameters": "ef = APP_VECTORSTORE_EF, default 100 (docker-compose-rag-server.yaml line 56)",
   "top_k": "VECTOR_DB_TOPK default 100 (docker-compose-rag-server.yaml line 70)",
   "memory_mapping": "queryNode.mmap.vectorField true, queryNode.mmap.vectorIndex false (milvus.yaml lines 509-510): the raw vector field may be mapped from disk, the index may not; an HNSW index holds its own copy of the vectors"},
  "memory_arithmetic": {
   "passages": n, "dimensions": dim, "bytes_per_value": 4,
   "vectors_bytes": raw, "vectors_gib": round(raw / 2**30, 2),
   "hnsw_level0_links_bytes_at_least": links, "note_links": "2 x M neighbours of 4 bytes per vector on the bottom layer; upper layers come on top",
   "index_bytes_at_least": raw + links,
   "docker_vm_memory_bytes": vm, "docker_vm_memory_gib": round(vm / 2**30, 2), "how_read": "MemTotal of /proc/meminfo inside a container, read when this file was written",
   "host_memory": "63.7 GB; the Docker VM is given about half of it",
   "card_memory_mib": 32607},
  "branch": "the index of the whole corpus (at least %.1f GiB) does not fit the memory the database container can have (%.1f GiB). The ruling's branch 'host memory not enough for the CPU index: stop, record the numbers' applies. Nothing is started for V5-A tonight: an attempt would bring the VM that also runs other projects' services to its limit. The GPU path is not the default and would need the same vectors on a 32 GB card." % ((raw + links) / 2**30, vm / 2**30),
  "unit_length": "checked on the whole store this night (every vector's length from the 16-bit copy, min and max), and reported; the exact search of Vol.4 is cosine, the Blueprint's metric is L2: on unit vectors both give the same order",
  "what_would_let_it_run": ["more memory for the Docker VM (a WSL setting; it restarts WSL and with it every container on this host: the owner's decision)", "a prefix of the corpus (not the whole corpus the ruling asks for)", "mapping the index from disk (not the Blueprint's setting)"]},
 "V5-B": {
  "question": "does the Blueprint's query-time set come up together on one 32 GB card, how much memory each service takes, and does each answer one real request",
  "set": {
   "llm": {"blueprint_default": "nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b:2.0.9 on two cards (deploy/compose/nims.yaml, device_ids 1 and 2)",
           "why_not_tried": "120 billion parameters are at least 60 GB at 4 bits, twice the card; the support matrix asks for at least three cards for the self-hosted set; the image is not on this host",
           "used": "the second choice the ruling names: Nemotron 3 Nano 4-bit", "image": image("nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12"),
           "profile": "1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada (vllm-nvfp4-tp1-pp1, the image's list: requires at least 21 GB per card)",
           "settings_from_the_blueprint": "shm 16GB, user 0, nofile 65536, NIM_ENABLE_CHUNKED_PREFILL=1, NCCL_NVLS_ENABLE=0, VLLM_USE_FLASHINFER_MOE_FP8=0; no memory fraction, no context length set (the NIM's defaults)"},
   "embedder": {"blueprint_default": "nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:1.12.0", "used": image("nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:2.3.0"),
                "why": "1.12.0 answers 500 on this card (Vol.4); the only version change against the Blueprint",
                "settings": "shm 16GB, NIM_TRT_ENGINE_HOST_CODE_ALLOWED=1 (the Blueprint's); started as Vol.4 starts the 2.x line: NIM_ENGINE_MODEL_DOWNLOAD_PROVIDER=ngc, the weights mounted at /model, the cache at /opt/cache"},
   "reranker": {"blueprint_default_and_used": image("nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0"), "settings": "shm 16GB (the Blueprint's)"},
   "vector_database": {"images": [image("milvusdb/milvus:v2.6.5-gpu"), image("quay.io/coreos/etcd:v3.6.5"), image("chrislusf/seaweedfs:3.73")],
                       "how": "the Blueprint's compose file deploy/compose/vectordb.yaml, profile milvus, with an override that only renames the containers and the volumes (compose_coresidence/override_vectordb.yaml)",
                       "collection": "SciFact's size: the 5,183 SciFact passages embedded by the set's embedder (seeded random unit vectors if the embedder is not up), the dense field and index of the ingestion client (HNSW M 64 efConstruction 512, L2, ef 100)"}},
  "not_started": {"extraction services of the default profile": "page-elements, graphic-elements, table-structure 1.8.0 and nemotron-ocr 1.3.0 are in the default profile of nims.yaml; on this host (Docker Desktop on WSL2) all four end with a CUDA IPC error (Vol.5 preparation, 2026-10-04): they are left out and the record says so",
                  "services without the card": "ingestor-server, rag-server, redis and the user interface: not started, they hold no card memory"},
  "how_it_differs_from_the_blueprint": ["every service on card 0 (the Blueprint spreads them over three cards)", "the model services started with docker run carrying each service's image, environment, shm size and ports from nims.yaml, not with compose (compose would start them at the same moment; one after the other gives each service's own share of the card)", "embedder and reranker run as the image's default user (the Blueprint sets the host user; that does not touch the card)", "the embedder's version and start as above", "the model's choice as above"],
  "order": "the Blueprint's: the model services in the order of nims.yaml (model, embedder, reranker), then the vector database; each waited for until it answers ready (model up to 20 min, the others 15 min, the database 5 min) or has ended",
  "measured": {"per_service": "up or not; the card's used memory before and after it (one after the other, so the difference is that service's share, desktop included before the first); the host memory of its container; the lines of its log that speak of memory, profiles and errors",
               "after_the_last": "the whole card; one real request to each service in the order a question takes (embed the question, embed the 5,183 passages into the collection, search, rerank the ten found, answer with the model from the first four): status, sizes, finish reason, token counts; the answer's text kept out of the results (length and SHA-256 only). Nothing is timed.",
               "alone": "every service that is not up in the set is started once more alone on the idle card, so that what it needs and what was missing are measured numbers"},
  "branches": {"all up": "the requests; then everything down",
               "a service does not come up": "the services after it are still started (each gets its verdict); the requests go to those that are up; then each one that was not up runs alone",
               "model": "the first choice is out by arithmetic, the second is the one used; the ruling allows one change of the model and it is spent: no third model, no memory fractions changed (that would be a second variable)"},
  "expectation": {"model": "up; the NIM's vLLM takes its default share of the whole card (0.92 of 32,607 MiB, about 29,998 MiB, the share Vol.2 recorded for this profile), so the card is nearly full after it",
                  "embedder": "does not come up: well under 1 GB of the card is left after the model; it needs several GB alone",
                  "reranker": "does not come up, for the same reason",
                  "vector_database": "Milvus' GPU memory pool asks for 2,048 MiB at start: either it does not come up or it comes up without its pool; no guess which",
                  "requests": "the model answers; the chain falls back to the first ten passages and random vectors where services are missing",
                  "alone": "embedder and reranker each come up alone, each taking a few GB",
                  "confidence": "medium: the 0.92 share is from Vol.2's record of this image and profile; whether a NIM checks free memory before it starts is not known here"},
  "time_limit": "nothing is started that cannot end before 08:00"},
 "before_this_file": {"probe": "before the ruling, 2026-10-16 03:27-03:35, the Milvus GPU image ran with four index settings on 20,000 passages (records in results/ann_vs_exact_probe/, named probe); the ruling then narrowed V5-A to the default settings only, and that design was set aside",
                      "path_test": "2026-10-16 ~03:47: the request program against the CPU image of Milvus on a test network, no model service up, no card: the database path (collection, index, search of 10, drop) worked; records in _internal only"},
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/coresidence_requests.py", "compose_coresidence/override_vectordb.yaml", "client_vectordb/Dockerfile")} | {"tools/g8_gate.py": sha(os.path.join(REPO, "tools", "g8_gate.py"))},
 "generator": "scripts/gen_prediction_first_night.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
os.makedirs(RES, exist_ok=True)
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
