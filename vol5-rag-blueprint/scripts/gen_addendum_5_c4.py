#!/usr/bin/env python3
"""Vol.5 · writes supplement 5 to the night-1 pre-registration: cell C4, what fits on one card and how long each stage
takes. With its .sha256 file. Run once, before the night's first container.
usage: gen_addendum_5_c4.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
RES = os.path.join(V5, "results", "night1"); OUT = os.path.join(RES, "addendum_5_c4.json"); DRAFT = "--draft" in sys.argv


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def image(im):
    out = subprocess.run(["docker", "image", "inspect", im, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {im}")
    return {"image": im, "id": out}


rec = {
 "what": "supplement 5 to the night-1 pre-registration: cell C4 (fourth supplement to the design ticket, 2026-10-20)",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": f, "sha256": sha(os.path.join(RES, f))} for f in ("prediction_v5_night1.json", "addendum_1_control_a_program.json", "addendum_2_control_b_exact.json",
                                                                          "addendum_3_c2_n_o.json", "addendum_4a_day.json", "addendum_4b_night3.json")],
 "owner_rule": "the owner, 2026-10-20: if NVIDIA's modules have a limit, the result is the limit. Only the four configurations below; if all spill, the result is that the card does not hold the three services; no fifth configuration, no change to the embedder or the reranker, no other answer model, no change to the WSL configuration",
 "services": {"embedder": image("nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:2.3.0") | {"settings": "the Blueprint's (its compose service), as on the second night"},
              "reranker": image("nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0") | {"settings": "the NIM's defaults"},
              "answer_model": image("nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12") | {"profile": "NVFP4", "environment": "the Blueprint's nims.yaml environment for its answer model (NIM_ENABLE_CHUNKED_PREFILL=1, NCCL_NVLS_ENABLE=0, VLLM_USE_FLASHINFER_MOE_FP8=0, user 0, nofile 65536), as on the second night",
                                                                          "reasoning_parser": "on in every configuration: NIM_PASSTHROUGH_ARGS carries --reasoning-parser nemotron_v3 (cell R showed it changes what is shown, not the score)"},
              "vector_store": "Elasticsearch 9.3.0 in its CPU container, outside the card's budget; its time is part of the stages"},
 "start_order": "embedder, reranker, answer model last; the positive control starts the answer model first",
 "spill_rule": {"program": "scripts/spill_judge.py (unchanged) through scripts/c4_judge.py",
                "alone": "the embedder and the reranker each alone on the idle card this night: S_i = median Windows 'GPU Adapter Memory' Shared Usage from 10 samples (about 20 s) after ready to the end of the alone run; D_i = the change of the card's used memory its start caused",
                "answer_model_alone": "not run: S = 0 and D = 0 for it (condition 1 is then stricter by the model's own shared use; condition 2 is decided by the two services with an alone run)",
                "condition_1": "the shared value at any sample rises above the sum of S_i of the services started so far + 512 MiB",
                "condition_2": "a service's own start changes the card's used memory by less than half of its D_i",
                "also_not_fitting": "a service that does not come up, or a call to any service that does not answer 200 after all three are up",
                "counters": "every 2 s through each run (the second night's poller, unchanged)"},
 "positive_control": {"what": "the answer model first at the NIM's defaults (gpu_memory_utilization 0.92, the NIM's default context), parser on, then the embedder and the reranker",
                      "rule": "must be judged spilled (or not fitting); otherwise the gate is broken: stop, report, no configuration is searched"},
 "configurations": {"order": "largest first; the first that fits ends the search",
                    "knobs": "NIM_MAX_MODEL_LEN; --max-num-seqs (through NIM_PASSTHROUGH_ARGS: no variable exists for it); NIM_KVCACHE_PERCENT, which the image maps to vLLM's gpu_memory_utilization (nim_llm/config/param_registry.py, default 0.92), the share of the card for the whole process, not the KV cache alone",
                    "1": "16384 / 26 / 0.65", "2": "16384 / 16 / 0.65", "3": "8192 / 16 / 0.65", "4": "8192 / 8 / 0.65",
                    "the_ratio_of_2_to_4": "the ticket asked for the smallest value the NIM 2.0.12 documentation gives; the documentation gives none (environment-variables page; memory troubleshooting page: default 0.9, example 0.85). 0.65 is the smallest share the answer model was measured to start with on this card (the volume's generation recipe, before night 1). The question went to the ticket's author on 2026-10-21 03:5x; this value holds unless ruled otherwise before configuration 2 starts"},
 "if_nothing_fits": "the result is 'the card does not hold the Blueprint's three query-time NIMs without spilling', with each configuration's shared peak and how far above the allowance it went",
 "stages": {"when": "only for the configuration found",
            "how": "the RAG server 2.6.0 (scripts/c4_timing.py): POST /v1/generate with use_knowledge_base true on the HotpotQA whole-corpus index, every other setting its default; the stages are the `metrics` object of the server's last stream chunk (retrieval_time_ms = query embedding + vector search, context_reranker_time_ms, llm_ttft_ms, rag_ttft_ms, llm_generation_time_ms), copied as sent; the whole call and the first answer text timed in the client",
            "questions": "the 200 of the C3 sample (seed 20261018), not filtered", "load": "concurrency 1, then 4",
            "caveat": "the embedder is the Blueprint's default (the ruling) while the index holds Vol.4's nemotron-3-embed-1b vectors: the passages found are not the right ones, so these times say nothing about answer quality",
            "if_nothing_fits": "each service alone on the card, c = 1, the same 200 questions: the embedder's query calls, the reranker's four ranking calls per question (p_arm.py), the answer model's requests of arm P (answer_arms.py), the vector search from the cold latency table; every file and figure marked not_coresident"},
 "stop": "the card is finished by 08:00 unless the owner gives more time",
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/spill_judge.py", "scripts/c4_judge.py", "scripts/c4_timing.py", "compose_es/c4.env", "compose_es/override_rag_server.yaml", "eval/hotpot_scoring.py")},
 "generator": "scripts/gen_addendum_5_c4.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen supplement 5 exists")
json.dump(rec, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + rec["written_at"], sha(OUT))
