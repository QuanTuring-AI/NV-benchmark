#!/usr/bin/env python3
"""Vol.5 · writes the second pre-registration of the volume (supplement 2 to the first night's file), with its .sha256
file: V5-B', the Blueprint's query-time services on the one card in reverse order with a spill gate, and the place of
V5-A' (held until the vector store question is ruled). Run once, before the first serving container of the night.
usage: gen_prediction_second_night.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE); REPO = os.path.dirname(V5)
RES = os.path.join(V5, "results", "second_night"); OUT = os.path.join(RES, "prediction_second_night.json")
FIRST = os.path.join(V5, "results", "first_night", "prediction_first_night.json")
DRAFT = "--draft" in sys.argv


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def image(im):
    out = subprocess.run(["docker", "image", "inspect", im, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {im}")
    return {"image": im, "id": out}


first = json.load(open(os.path.join(V5, "results", "coresidence_alone_added", "summary.json"), encoding="utf-8")) if os.path.isfile(os.path.join(V5, "results", "coresidence_alone_added", "summary.json")) else None
alone = {s["service"]: s["card_used_delta_mib"] for s in (first or {}).get("steps", []) if s["step"] == "service_verdict"}
pred = {
 "what": "Vol.5, second night on one RTX 5090: V5-B', the RAG Blueprint's (v2.6.2) query-time services together on the card, started in reverse order, with a gate that tells a configuration that fits on the card from one that spills into system memory",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"file": "../first_night/prediction_first_night.json", "sha256": sha(FIRST)},
 "authorised_by": "the ruling of 2026-10-16 on the second Vol.5 night",
 "why": "the first night started every service and every request answered, but the services alone took 42,050 MiB of a 32,607 MiB card, and Windows reported shared GPU memory rising to 3,572 MiB during the requests: on this host a service that does not fit is paged into system memory instead of failing. 'Comes up' is therefore not 'fits'.",
 "V5-B'": {
  "services": {"embedder": image("nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:2.3.0"), "reranker": image("nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0"),
               "answer_model": image("nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12") | {"profile": "1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada (NVFP4)"},
               "vector_database": "none on the card in the Blueprint's default (Elasticsearch, a CPU service); the optional Milvus GPU image only if the ruling asks for it",
               "started_as": "as on the first night (the same docker run lines, prefix p134_), every service on card 0"},
  "configurations": {
   "C1": {"order": "embedder, reranker, answer model last", "answer_model": "the NIM's default memory share (no memory setting)"},
   "C2": {"order": "the same", "answer_model": "NIM_KVCACHE_PERCENT=0.650, NIM_MAX_MODEL_LEN=16384, NIM_PASSTHROUGH_ARGS='--max-num-seqs 32': the smallest budget that started and answered at a context of 16,384 in the preparation cell (README section 2); 16,384 holds the Blueprint's LLM_MAX_TOKENS of 16,256"},
   "C3": {"order": "answer model first, then embedder and reranker (the first night's order)", "answer_model": "the NIM's default", "role": "positive control of the spill gate: the shared value must rise to the GB range again, or the gate does not see a spill"}},
  "spill_gate": {"counter": "Windows performance counter 'GPU Adapter Memory' Shared Usage of the card, logged every ~2 s from before the first start to after the teardown (gpu_memory_poller.ps1)",
                 "baseline": "median of the first three samples, before the first service of the configuration starts",
                 "rule": "spilled when the shared value rises more than 256 MiB above the baseline at any sample of the configuration; a spilled configuration is never reported as fitting"},
  "measured": {"per_service": "up or not, seconds to ready, nvidia-smi's used memory after it (card_used_delta_mib, a change, not a need), the shared value, the host memory of its container, memory lines of its log",
               "answer_model": "the engine's cache_config_info from /metrics (num_gpu_blocks, block_size, gpu_memory_utilization) and the log's KV cache line, verbatim",
               "requests": "one real request to each service after the last is up, with the first night's program unchanged (scripts/coresidence_requests.py, its SHA-256 below); nothing is timed"},
  "expectation": {"C1": "the answer model either refuses to start (its default share of the whole card is more than what is free after the embedder and the reranker) or starts and spills; no guess which",
                  "C2": "fits: about 21,195 MiB for the answer model plus about 9,100 MiB for the embedder and the reranker alone (the first night) is under the card's 32,607 MiB; not spilled; the KV cache near the preparation cell's 167,040 tokens (ten requests of 16,384 tokens)",
                  "C3": "spilled: the shared value rises above 1,024 MiB, as on the first night (3,572 MiB during the requests)",
                  "confidence": "low for C1 (the engine's check of free memory on this host is not known), medium for C2 (the margin is about 1 GB and the desktop's own use varies), high for C3",
                  "alone_on_the_first_night_mib": alone or None},
  "branches": {"C1 and C2 both spill": "the card does not hold the query path: the record is the peak shared value; no other answer model, no other setting of the embedder or the reranker",
               "C3 does not spill": "the gate is blind on this host: no configuration is reported as fitting",
               "C2 fits": "the timing half of V5-C (section 2.4 of the ruling) may run on C2; its design is registered in a supplement before it runs"}},
 "V5-A'": {"state": "held: the Blueprint's default vector store is Elasticsearch, not Milvus (question to the benchmark line, 2026-10-17); nothing of V5-A' runs before the ruling"},
 "time_limit": "nothing is started that cannot end before 08:00",
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/coresidence_requests.py", "scripts/coresidence_summary.py", "client_vectordb/Dockerfile")} | {"tools/g8_gate.py": sha(os.path.join(REPO, "tools", "g8_gate.py"))},
 "generator": "scripts/gen_prediction_second_night.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
os.makedirs(RES, exist_ok=True)
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
