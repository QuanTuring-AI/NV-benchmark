#!/usr/bin/env python3
"""Vol.5 · writes supplement 7 to the night-1 pre-registration: cell C4, configuration 5 (context 32768), added so that
the Blueprint's own answer-model request fits (sixth supplement to the design ticket, 2026-10-21). With its .sha256 file.
Run once, before the first container of the cell.
usage: gen_addendum_7_c4_context_32768.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
RES = os.path.join(V5, "results", "night1"); OUT = os.path.join(RES, "addendum_7_c4_context_32768.json"); DRAFT = "--draft" in sys.argv


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def image(im):
    out = subprocess.run(["docker", "image", "inspect", im, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {im}")
    return {"image": im, "id": out}


rec = {
 "what": "supplement 7 to the night-1 pre-registration: C4, configuration 5 (answer model context 32768), alone and then with the embedder and the reranker on the card, and the time of each stage after the answer model is ready",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": f, "sha256": sha(os.path.join(RES, f))} for f in ("prediction_v5_night1.json", "addendum_1_control_a_program.json", "addendum_2_control_b_exact.json",
                                                                          "addendum_3_c2_n_o.json", "addendum_4a_day.json", "addendum_4b_night3.json", "addendum_5_c4.json",
                                                                          "addendum_6_c4_ready.json")],
 "why": "supplement 6's cell stayed on the card after the answer model was ready, but every one of its 200 requests was refused (HTTP 400): the Blueprint asks the answer model for max_tokens 16256 by default, and configuration 1's context of 16384 leaves room for a prompt of at most 128 tokens. This configuration is added only so that the Blueprint's default request fits; it is not added to pass the spill rule (the ready cell did not spill). Context length did not change the memory used in supplement 5's four configurations; the ratio did",
 "also_on_record": "the memory cells of supplement 5 called each service once with max_tokens 512 (all answered); the Blueprint's own request was refused at every context of 16384 or less. A reader who deploys with the defaults meets this",
 "configuration": {"name": "ready5",
                   "answer_model": image("nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12") | {"setting": "NIM_MAX_MODEL_LEN 32768, --max-num-seqs 26, NIM_KVCACHE_PERCENT 0.65, --reasoning-parser nemotron_v3; everything else as supplement 6"},
                   "embedder": image("nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2") | {"setting": "as supplement 6 (fp16, deviation 1)"},
                   "reranker": image("nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0") | {"setting": "the NIM's defaults"},
                   "order": "embedder, reranker, answer model; 60 s after the answer model is ready before anything is timed"},
 "steps": [
  "1 the answer model alone at this setting (tag llm5): does it start; S and D as before; max_model_len read back from GET /v1/models and the cache configuration line (vllm:cache_config_info) from GET /metrics",
  "2 while it is alone: two captured requests of the RAG server sent byte for byte (scripts/blueprint_request_probe.py): arm N's (no passages) and arm P's (ten passages), both max_tokens 16256; each must return 200",
  "3 the three on the card in the order above, the answer model's start recorded as before (supplement 5's rule, start transient)",
  "4 60 s after ready, the steady verdict after ready (scripts/c4_ready_judge.py, supplement 6's rule, S of the answer model from step 1, S of the embedder and the reranker from their alone runs kept)",
  "5 the RAG server's stages for the 200 questions of the C3 sample at concurrency 1, then 4 (scripts/c4_timing.py unchanged, compose_es/c4_n3.env)"],
 "branches": {"answer_model_does_not_start": "stop; the error text is recorded; C4 is written in the three layers of the question file",
              "a_probe_request_is_refused": "the error text is recorded; stop (no coresident run)",
              "spilled_after_ready": "the times are still measured; every file and figure is marked coresident_spilled",
              "c4_beyond_the_reported_concurrency": "if concurrency 4 is above what the answer model reports it can hold, that is recorded as it is; no setting is changed"},
 "kept": "the alone runs of the n3 embedder and the reranker (2026-10-21); the not-coresident table",
 "not_done": "no smaller ratio, no other configuration, no change to the embedder or the reranker (the owner's rule)",
 "stop": "the owner gave the card on 2026-10-22 (\"卡給你 開始工作吧\") without an end time; the default end, 08:00, applies; what is not done by then goes into a progress file",
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/spill_judge.py", "scripts/c4_ready_judge.py", "scripts/c4_timing.py", "scripts/blueprint_request_probe.py",
                                                         "compose_es/c4_n3.env", "compose_es/override_rag_server.yaml", "eval/hotpot_scoring.py")},
 "generator": "scripts/gen_addendum_7_c4_context_32768.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen supplement 7 exists")
json.dump(rec, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + rec["written_at"], sha(OUT))
