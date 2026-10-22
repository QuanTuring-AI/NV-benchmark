#!/usr/bin/env python3
"""Vol.5 · writes supplement 3 to the night-1 pre-registration: cell C2's arms N (no passages, the Blueprint's
use_knowledge_base false path) and O (the two supporting passages through the Blueprint's RAG prompt), with the
request read from the Blueprint's own server. With its .sha256 file. Run once, before the answer model's container.
usage: gen_addendum_3_c2_n_o.py [--draft]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
RES = os.path.join(V5, "results", "night1"); OUT = os.path.join(RES, "addendum_3_c2_n_o.json"); DRAFT = "--draft" in sys.argv
C2 = os.path.join(V5, "results", "c2")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def image(im):
    out = subprocess.run(["docker", "image", "inspect", im, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {im}")
    return {"image": im, "id": out}


ctl = json.load(open(os.path.join(C2, "request_control.json"), encoding="utf-8"))
if not ctl["all_bodies_equal"]:
    sys.exit("refused: the request control did not pass")
params = json.load(open(os.path.join(C2, "request_params.json"), encoding="utf-8"))["body"]
rec = {
 "what": "supplement 3 to the night-1 pre-registration: cell C2, arms N and O, on BEIR HotpotQA's 7,405 questions",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": f, "sha256": sha(os.path.join(RES, f))} for f in ("prediction_v5_night1.json", "addendum_1_control_a_program.json", "addendum_2_control_b_exact.json")],
 "authorised_by": "the second supplement of 2026-10-18 to the Vol.5 design ticket (arms N and O on the card, the night after it)",
 "arms": {"N": "the Blueprint's path with use_knowledge_base false: system message of prompt.yaml's chat_template, user message 'Query: <question>' (rag_server/main.py _llm_chain). This is the Blueprint's knowledge-base switch, not a single variable: against P it changes the prompt and the passages",
          "O": "the Blueprint's RAG prompt (rag_template) with the question's two supporting passages as the context, each as the server formats a document ('File: <passage id>\\nContent: <Vol.4 passage text>'), joined by a blank line, in the order of the id table's gold_passages (sorted as strings); then 'Query: <question>\\n\\nAnswer: ' (main.py _rag_chain). O differs from the later arm P only in the passages"},
 "request": {"how": "every field other than the messages is the request the Blueprint's RAG server 2.6.0 itself sent to the answer model (read with capture_service.py; results/c2/request_params.json); the client sends it to the NIM unchanged, streaming included",
             "fields": params, "note": "the Blueprint's defaults put the reasoning budget at 256 tokens (LLM_REASONING_BUDGET, sent to a local NIM as nvext.max_thinking_tokens) and the answer limit at 16,256 tokens",
             "control": {"file": "results/c2/request_control.json", "captured_requests": ctl["captured_requests"], "by_arm": ctl["by_arm"], "all_bodies_equal": ctl["all_bodies_equal"],
                         "negative": "built with the passages reversed, as arm N, without nvext, or with one space added to the question, the body differs (each checked once)"},
             "prompt_file": "the rag-server 2.6.0 image's nvidia_rag/rag_server/prompt.yaml (its chat_template and rag_template are line for line those of the v2.6.2 repository)"},
 "questions": "all 7,405 of the HotpotQA id table, in sorted id order; for each question N then O",
 "answer_model": {"nim": image("nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12"), "profile": "NVFP4 (deviation 2 of BLUEPRINT_SETTINGS.md)",
                  "settings": "the NIM's defaults; the only branch: if the NIM's max_model_len is below 17,000 (a request asks for up to 16,256 new tokens), the container is replaced once with NIM_MAX_MODEL_LEN=32768, and that is recorded",
                  "alone": "the only container on the card; Elasticsearch (C1) on the CPU only",
                  "beside_c1": "the answers run while C1 loads its index (the ticket allows it; C1's load time is then measured with the card's work on the same host, and its record says so) and pause while C1's timed searches run (the driver reads C1's events every 30 s and stops the client, which resumes from its files after C1 is done)"},
 "client": {"program": "scripts/answer_arms.py run", "in_flight": "the integer part of the KV-cache concurrency the NIM prints at start ('Maximum concurrency for N tokens per request'), at most 32; read from the log, never typed",
            "timing": "not measured: the result files carry timing_not_measured cpu_shared_with_c1", "stop": "the run stops itself at 09:45 (the owner gave the card until 10:00 on 2026-10-19) and continues the next night from its files; a request that failed is sent again by the next run"},
 "final_answer": "the content of the stream; when it holds '</think>' (reasoning left in the content by a server without a reasoning parser), the text after the last '</think>'. The raw content and the reasoning are both kept (outside the repository)",
 "tokens": "answer tokens and reasoning tokens counted with the model's tokenizer.json (SHA-256 c6021eb6847e682f..., the NIM's NVFP4 snapshot); the usage chunk's completion_tokens kept beside them",
 "scores": {"main": "contains (eval/hotpot_scoring.py)", "second": "token F1", "listed": "EM, refusals by pattern", "intervals": "Wilson 95% per arm",
            "paired": "N against O (exact McNemar) as soon as both are complete; P against O and N after C1",
            "program": "scripts/answer_arms.py score"},
 "branches": {"finish_reason_length": "over 2% of an arm: recorded as it is, max_tokens not changed (it is the default)", "nim_does_not_start": "the error text is the result; stop",
              "not_finished": "the question it stopped at goes in the progress file; the next night continues"},
 "expectation": {"O_contains_rate": "between 0.70 and 0.90", "N_contains_rate": "between 0.25 and 0.50", "O_minus_N": "positive, McNemar p below 0.001",
                 "reasoning_tokens": "near or below 256 per answer if the NIM honours nvext.max_thinking_tokens; if not, many times more (whether it does is a finding either way)",
                 "confidence": "low"},
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/answer_arms.py", "scripts/capture_service.py", "scripts/capture_requests.py", "eval/hotpot_scoring.py",
                                                         "eval/rag_eval.py", "results/c2/request_params.json", "results/c2/request_control.json",
                                                         "compose_es/capture.env", "compose_es/override_rag_server.yaml")},
 "generator": "scripts/gen_addendum_3_c2_n_o.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen supplement 3 exists")
json.dump(rec, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + rec["written_at"], sha(OUT))
