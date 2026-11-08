#!/usr/bin/env python3
"""Vol.5 · writes supplement 4B to the night-1 pre-registration: night 3 (the clean-window latency, arm P, cell C3,
MIRACL zh P, cell R). With its .sha256 file. Run once, before the night's first container.
usage: gen_addendum_4b_night3.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
RES = os.path.join(V5, "results", "night1"); OUT = os.path.join(RES, "addendum_4b_night3.json"); DRAFT = "--draft" in sys.argv
C2 = os.path.join(V5, "results", "c2")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def image(im):
    out = subprocess.run(["docker", "image", "inspect", im, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {im}")
    return {"image": im, "id": out}


pc = json.load(open(os.path.join(C2, "p_request_control.json"), encoding="utf-8"))
if not (pc["all_ranking_equal"] and pc["all_answer_equal"]) or any(pc["negative_controls_equal_should_all_be_false"].values()):
    sys.exit("refused: the arm-P request control did not pass")
c3r = json.load(open(os.path.join(C2, "c3_retrieval.json"), encoding="utf-8"))
rec = {
 "what": "supplement 4B to the night-1 pre-registration: night 3, ruled on 2026-10-20 (third supplement to the design ticket)",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": f, "sha256": sha(os.path.join(RES, f))} for f in ("prediction_v5_night1.json", "addendum_1_control_a_program.json", "addendum_2_control_b_exact.json",
                                                                          "addendum_3_c2_n_o.json", "addendum_4a_day.json")],
 "gate": "Steam and game processes 0, no other project's GPU container, G8; one NIM on the card at a time; the card work is not timed and may run while the day's CPU work (supplement 4A) is still running",
 "clean_window": {"when": "with no container on the card and nothing else running on the host: after the day's CPU work (supplement 4A) has ended and after the card work that does not need it (arm P, C3, cell R); MIRACL zh P, which needs the zh index, runs on the card after the clean window",
                  "c1": "the default query (k = num_candidates = 100) for all 7,405 HotpotQA questions, timed as in C1 (c = 1, first ten apart), on the same index; the run compared with C1's first run question by question (run_diff.py: identical, same set in another order, different sets, all listed). The index has merged segments since C1 (store size 52.9 GB at C1, 44.2 GB on 2026-10-20 02:01; 32 segments at 01:58), so differences are possible and are reported, not corrected",
                  "num_candidates": "c = 1 latency on 1,000 questions (seed 20261020) for blueprint:100, 200, 400 and es-only:200, 500, 1000, one setting after the other (es_latency_probe.py)",
                  "zh": "the default query for MIRACL zh's 393 questions, timed, compared with the day's untimed run (run_diff.py)"},
 "arm_P": {"what": "the Blueprint's knowledge-base path, step by step, each request as the RAG server sends it (p_arm.py; control: results/c2/p_request_control.json, 5 of 5 questions equal for ranking and answer bodies, 5 negative controls unequal)",
           "retrieve": "C1's run of the default query (night 1, c1_default.trec), the top 100 per question",
           "rerank": {"nim": image("nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0"), "settings": "the NIM's defaults (the Blueprint's reranker and version, nims.yaml)",
                      "requests": "batches of 32 (32, 32, 32, 4), truncate END, the model the NIM lists; the 10 highest logits over all batches, highest first", "client": "4 questions in flight; not timed"},
           "answer": {"nim": image("nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12"), "settings": "as supplement 3 (NVFP4 profile, the NIM's defaults, concurrency from GET /metrics kv_cache_max_concurrency, at most 32)",
                      "request": "the request of arm O with the reranked 10 passages (answer_arms.py, arm O builder); final answer and token rules as supplement 3"},
           "scores": "contains (main), F1, EM, refusals, finish reasons, Wilson 95%; paired exact McNemar P against N and P against O on the same 7,405 questions; the share of questions whose 10 passages hold both supporting passages / one / none",
           "expectation": {"P_contains": "between O's 0.728 and N's 0.304, nearer O", "P_minus_N": "positive, p below 0.001", "O_minus_P": "positive, p below 0.001", "confidence": "low"}},
 "C3": {"questions": "the 200 of the fixed sample (seed 20261018)", "retrieve": "results/c2/c3_retrieval.json: the kNN query with a filter inside the kNN clause leaving out each question's two supporting passages (%d supporting passages removed from the unfiltered top 100; none left)" % c3r["supporting_passages_removed_from_top100"],
        "then": "rerank and answer as arm P", "measured": "refusal by pattern (rag_eval.py) with Wilson 95%%; contains against the gold answer (an answer from the model's own knowledge); 50 answers (seed 20261020) labelled by hand as refusal / answers anyway / other before the pattern's verdict is looked at, and the agreement reported",
        "expectation": "most answers are not refusals, given the RAG prompt's rule to answer when the context holds relevant data and the reasoning model; confidence low"},
 "zh_P": {"questions": "MIRACL zh dev, 393", "retrieve": "the day's default run on the zh index", "then": "rerank and answer as arm P (the Blueprint's English prompts, as shipped)",
          "measured": "the share of questions whose 10 passages hold a passage judged relevant (qrels relevance > 0), Wilson 95%; refusals by pattern; finish reasons. MIRACL has no answer strings: no answer score",
          "expectation": "share of questions with a judged-relevant passage among the 10 between 0.6 and 0.9; confidence low"},
 "cell_R": {"what": "Nano with the reasoning parser the NIM 2.0.12 documentation gives for reasoning models: the container command-line argument --reasoning-parser nemotron_v3 (docs.nvidia.com/nim/large-language-models/2.0.12/ai-assistant-integrations/codex-cli.html: 'Reasoning models emit thinking tokens. Without a parser, that text lands in the assistant message'; its example serves a Nemotron 3 model with nemotron_v3; parser names are model-specific)",
            "questions": "the 200 of the C3 sample with arm P's reranked passages (not filtered)", "request": "unchanged (the Blueprint's, with nvext.max_thinking_tokens 256)",
            "measured": "the reasoning separated (reasoning_content) or not; reasoning tokens per answer and the share at most 256; whether the content still holds '</think>' or reasoning (what the Blueprint would show); contains on the same 200 against arm P",
            "expectation": "the reasoning comes apart from the answer; whether the 256 budget then holds is open; confidence low"},
 "branches": {"not_finished_by_STOP_AT": "07:45 or the owner's later time: the step stops, the progress file says where; the next night continues from the files",
              "a_NIM_does_not_start": "its log is the result; that step stops, the others go on",
              "finish_reason_length_over_2_percent": "recorded, max_tokens unchanged"},
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/p_arm.py", "scripts/answer_arms.py", "scripts/c3_retrieve.py", "scripts/answers_extra.py", "scripts/es_latency_probe.py",
                                                         "scripts/run_diff.py", "scripts/es_ann_vs_exact.py", "scripts/capture_service_all.py", "scripts/capture_requests_p.py",
                                                         "results/c2/request_params.json", "results/c2/p_request_control.json", "results/c2/c3_retrieval.json", "eval/hotpot_scoring.py", "eval/rag_eval.py")},
 "generator": "scripts/gen_addendum_4b_night3.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen supplement 4B exists")
json.dump(rec, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + rec["written_at"], sha(OUT))
