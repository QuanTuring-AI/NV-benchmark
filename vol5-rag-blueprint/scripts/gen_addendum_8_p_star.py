#!/usr/bin/env python3
"""Vol.5 · writes supplement 8 to the night-1 pre-registration: arm P*, the answer model given the reranked top 10 of
exact search instead of the Blueprint's approximate top 100 (the third and fourth rulings of 2026-10-22 on the Vol.5
design ticket). With its .sha256 file.
Run once, before the first container of the arm.
usage: gen_addendum_8_p_star.py --hold DIR --runner FILE [--draft]
"""
import argparse, hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
RES = os.path.join(V5, "results", "night1"); OUT = os.path.join(RES, "addendum_8_p_star.json")
ap = argparse.ArgumentParser(); ap.add_argument("--hold", required=True); ap.add_argument("--runner", required=True); ap.add_argument("--draft", action="store_true")
a = ap.parse_args()


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def image(im):
    out = subprocess.run(["docker", "image", "inspect", im, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {im}")
    return {"image": im, "id": out}


def hold(rel):
    p = os.path.join(a.hold, rel)
    return {"file": "<hold>/" + rel, "sha256": sha(p)}


rec = {
 "what": "supplement 8 to the night-1 pre-registration: arm P*, the answer model given the reranked top 10 of Vol.4's exact search over the whole HotpotQA corpus instead of the Blueprint's approximate top 100",
 "draft": a.draft, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": f, "sha256": sha(os.path.join(RES, f))} for f in ("prediction_v5_night1.json", "addendum_1_control_a_program.json", "addendum_2_control_b_exact.json",
                                                                          "addendum_3_c2_n_o.json", "addendum_4a_day.json", "addendum_4b_night3.json", "addendum_5_c4.json",
                                                                          "addendum_6_c4_ready.json", "addendum_7_c4_context_32768.json")],
 "why": "arm P (0.534) lost to arm O (0.728) partly in retrieval: the default index keeps both supporting passages among the ten for 4,271 of 7,405 questions. P* puts exact search in its place and changes nothing else, so the difference P* - P is the cost of the approximate index to the answer, and O - P* what reranking and ten passages leave",
 "status_in_the_comparison": "a reference beside the tuned versions, not one of them: exact search, nothing tuned",
 "arm": {
  "retrieve": "Vol.4's exact search, top 100 per question, every passage of HotpotQA (nDCG@10 0.801): the run file below",
  "rerank": "scripts/p_arm.py rerank, unchanged from arm P: the 100 passages in retrieval order in the Blueprint's batches of 32, 32, 32, 4, all logits together, the first 10",
  "answer": "scripts/answer_arms.py run with arm O's request body and the ten passages in reranked order (p_arm.py ids): every field as arm P; only the passages differ",
  "answer_model": "Nemotron 3 Nano at the NIM's defaults, no reasoning parser, as arm P on night 3",
  "questions": "the 7,405 questions of arm P (results/question_set/hotpotqa_ids.jsonl)"},
 "images": {"reranker": image("nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0"), "answer_model": image("nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12") | {"profile": "1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada"}},
 "inputs_outside_the_repository": {
  "exact_top_100": hold("vol4_hotpotqa/whole_corpus/run.trec"),
  "passage_texts": hold("vol5_es/p_star/texts_exact_top100.jsonl") | {"made_by": "p_arm.py texts on the run above (CPU, 2026-10-22)"},
  "prompts": hold("vol5_es/night2_capture/prompt_rag_server_2.6.0.yaml"),
  "arm_P_answers": hold("vol5_es/night3/p/answers_O.jsonl"), "arm_P_ten": hold("vol5_es/night3/p_ids.jsonl"),
  "arm_O_answers": hold("vol5_es/c2/night2/answers_O.jsonl"), "gold_answers": hold("vol5_es/c2/gold_answers.jsonl")},
 "measures": {"arm": "contains the official answer (rate, Wilson 95%), F1, EM, refusals by pattern, finish reasons",
              "paired": "P* against P and P* against O on the same 7,405 questions, exact McNemar",
              "passages": "both / one / none of the two supporting passages among P*'s ten; questions whose ten equal P's",
              "program": "scripts/score_p_star.py"},
 "seen_before_this_supplement": {
  "note": "known when the interval was set, all without generating an answer; the counts for P* come from Vol.4's reranked run (one call of 100 per question), not from the batches this arm uses",
  "supporting_passages_among_the_ten": {"P": {"both": 4271, "one": 2363, "none": 771}, "P_star_from_vol4_reranking": {"both": 5706, "one": 1628, "none": 71}},
  "P_contains_by_supporting_passages": {"none": 0.065, "one": 0.354, "both": 0.718},
  "projection": "P's rates by supporting-passage count applied to P*'s counts: 0.632"},
 "expect": {"contains_rate": {"low": 0.58, "high": 0.68},
            "why": "the projection is 0.632; the band allows the other eight passages to change answers either way",
            "P_star_vs_P": "P* right and P wrong outnumbers the reverse, exact McNemar p < 0.001",
            "P_star_vs_O": "O stays higher, exact McNemar p < 0.001",
            "outside_the_band": "reported as it is, with the passage counts; no rerun"},
 "branches": {"reranker_or_answer_model_does_not_start": "stop; the error is recorded",
              "a_question_fails": "retried by answer_arms.py as on night 3; a question still failing counts as not containing the answer",
              "not_done_by_the_stop_time": "the answers written so far stay; the run resumes on another night the owner gives; nothing is scored before all 7,405 are in"},
 "stop": "08:00 of the night the owner gives, unless the owner names another end",
 "per_question_table": "after scoring, one line per question (query_id, contains, f1, refusal, the ten passage ids; no answer text) for the external evaluation, kept outside the repository",
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/p_arm.py", "scripts/answer_arms.py", "scripts/score_p_star.py", "eval/hotpot_scoring.py", "eval/rag_eval.py",
                                                         "results/question_set/hotpotqa_ids.jsonl", "results/c2/request_params.json")},
 "runner_outside_the_repository_sha256": {"file": os.path.basename(a.runner), "sha256": sha(a.runner)},
 "generator": "scripts/gen_addendum_8_p_star.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen supplement 8 exists")
json.dump(rec, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not a.draft:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if a.draft else "FROZEN ") + rec["written_at"], sha(OUT))
