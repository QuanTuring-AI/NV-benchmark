#!/usr/bin/env python3
"""Vol.5 · writes supplement 6 to the night-1 pre-registration: cell C4, the stages with all three services on the card
after the answer model is ready (fifth supplement to the design ticket, 2026-10-21). With its .sha256 file.
Run once, before the first container of the cell.
usage: gen_addendum_6_c4_ready.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
RES = os.path.join(V5, "results", "night1"); OUT = os.path.join(RES, "addendum_6_c4_ready.json"); DRAFT = "--draft" in sys.argv


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def image(im):
    out = subprocess.run(["docker", "image", "inspect", im, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {im}")
    return {"image": im, "id": out}


rec = {
 "what": "supplement 6 to the night-1 pre-registration: C4, the time of each stage with the embedder, the reranker and the answer model all on the card, measured after the answer model is ready",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": f, "sha256": sha(os.path.join(RES, f))} for f in ("prediction_v5_night1.json", "addendum_1_control_a_program.json", "addendum_2_control_b_exact.json",
                                                                          "addendum_3_c2_n_o.json", "addendum_4a_day.json", "addendum_4b_night3.json", "addendum_5_c4.json")],
 "why": "supplement 5's four configurations spilled only while the answer model was starting; after it was ready the three services stayed on the card (about 21.9 GB, shared 549-569 MiB) and answered. This cell times that steady state. It is not a fifth configuration: it is configuration 1 of supplement 5",
 "configuration": {"answer_model": image("nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12") | {"setting": "NIM_MAX_MODEL_LEN 16384, --max-num-seqs 26, NIM_KVCACHE_PERCENT 0.65, --reasoning-parser nemotron_v3; the Blueprint's nims.yaml environment (as supplement 5)"},
                   "embedder": image("nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2") | {"setting": "fp16 (NIM_ENGINE_PRECISION=fp16), the volume's deviation 1: the same vector space as the HotpotQA index, so the passages found are the right ones (supplement 5's memory cells used the Blueprint's default embedder and stay as they are)"},
                   "reranker": image("nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0") | {"setting": "the NIM's defaults"},
                   "order": "embedder, reranker, answer model; 60 s after the answer model is ready before anything is timed"},
 "alone_runs": {"new": "the n3 embedder alone, and the answer model alone at the configuration's setting: S (steady Windows shared usage, spill_judge.steady_shared) and D (card delta)",
                "kept": "the reranker's alone run of supplement 5 (2026-10-21 03:5x)",
                "embedder_alone_times": "while the n3 embedder is alone: its query calls for the same 200 questions at c = 1 (stage_alone_timing.py embed), so the not-coresident table has the same embedder"},
 "spill_after_ready": {"program": "scripts/c4_ready_judge.py", "window": "the Windows counter samples from 30 samples (60 s) after the answer model's ready sample to the end of the timing runs",
                       "rule": "spilled_after_ready if any sample of the window rises above S_embed + S_rank + S_llm + 512 MiB",
                       "branch": "the times are measured either way; if it holds, every file and figure is marked coresident_spilled"},
 "stages": {"program": "scripts/c4_timing.py (unchanged) through the RAG server 2.6.0 with compose_es/c4_n3.env",
            "how": "POST /v1/generate, use_knowledge_base true, collection hotpotqa_whole, every other setting the default; per question the server's own metrics of its last stream chunk (retrieval_time_ms = query embedding + vector search, context_reranker_time_ms, llm_ttft_ms, rag_ttft_ms, llm_generation_time_ms) copied as sent, and in the client the whole call and the first answer text",
            "questions": "the 200 of the C3 sample (seed 20261018), not filtered", "load": "concurrency 1, then 4",
            "compare": "beside the not-coresident table (each service alone, the same 200 questions): how much each stage slows down on the shared card",
            "branch": "if the answer model refuses requests at c = 4 (sequence limit), that is recorded as it is; no setting is changed"},
 "not_done": "no smaller ratio, no other configuration (the owner's rule)",
 "stop": "the owner gave the card until 20:30 on 2026-10-21",
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/spill_judge.py", "scripts/c4_ready_judge.py", "scripts/c4_timing.py", "scripts/stage_alone_timing.py",
                                                         "compose_es/c4_n3.env", "compose_es/override_rag_server.yaml", "eval/hotpot_scoring.py")},
 "generator": "scripts/gen_addendum_6_c4_ready.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen supplement 6 exists")
json.dump(rec, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + rec["written_at"], sha(OUT))
