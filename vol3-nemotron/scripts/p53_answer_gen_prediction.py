#!/usr/bin/env python3
"""Vol.2 answer-completion run · write prediction_p53_answer.json once, before the measured run.
usage: p53_answer_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p53_answer")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.2 · answer completion · the speed table's two arms and 50 questions at max_tokens 4096: time and tokens to answer a question, reasoning vs answer split",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p53_answer.sh refuses to start if this file or its .sha256, or the sample or its .sha256, is missing or changed, or if requests.jsonl exists.",
 "runs": "one run",
 "why": "p50_speed measures generation rate but 79 of its 100 completions hit max_tokens 500, so it cannot say how long a question takes or how many tokens the model spends before the answer; both models reason by default. This run raises the cap to 4096 and records the reasoning channel when the image exposes one.",
 "relation_to_p50_speed": "same arms, images, profiles, sample, block order, payload and analyzer preconditions; two differences, both recorded: max_tokens 4096 (the point of the run) and NIM_MAX_MODEL_LEN 8192 on both containers, because a 4096-token completion cannot fit beside any prompt inside 4096 (the harness test at 4096 returned HTTP 400 on every request). A1 keeps NIM_MAX_NUM_SEQS 32 and A2 its default, as in p50_speed.",
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p53_answer.py", "vol2/scripts/p53_answer_analyze.py", "vol2/scripts/run_p53_answer.sh",
                                      "vol2/scripts/p50_speed.py", "vol2/scripts/p50_speed_analyze.py", "vol2/scripts/p50_footprint.py", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {"vol1b/results/p20_coresidence/sample.json": h("vol1b/results/p20_coresidence/sample.json"), "benchmark/questions.json": h("benchmark/questions.json")},
 "design": {"reasoning_split": "per delta the harness records reasoning_content (or reasoning) separately from content, and looks for <think>...</think> in content; the row records which channel appeared. If neither appears the totals are reported without a split and the report says so.",
            "records": "per request TTFT, time to the first answer token when reasoning came first, total latency, engine prompt/completion tokens, finish_reason, reasoning and answer character counts, empty-answer flag"},
 "analysis_rules": {"preconditions": "p50_speed_analyze P1-P3 and its arm-health gate (same bytes per token)",
                    "added": "per arm: total latency, completion tokens, truncation count at 4096, reasoning channel, reasoning/answer chars, time to first answer, empty answers; A2/A1 paired ratios of total latency and completion tokens beside the generation-rate ratio",
                    "program": "vol2/scripts/p53_answer_analyze.py (7 self-test cases on top of p50_speed_analyze's 13)"},
 "predictions": {
   "basis": "p50_speed: A1 72.9 and A2 305.1 tok/s generation, 42/50 and 37/50 completions cut at 500; external report (P52) that Nemotron 3 Nano spends about twice the reasoning tokens of a comparison model; harness test 2026-09-21/22 at NIM_MAX_MODEL_LEN 8192 on the three harness-test questions (not in the sample): every completion ended with stop, A1 948-1,762 and A2 1,578-2,525 completion tokens, A2/A1 total latency 0.40, completion tokens 1.67, and NEITHER image exposed a reasoning channel (no reasoning_content field, no <think> markers: the reasoning is inline in content). R4 below was written before that test and is expected to fail; it is kept as written. The earlier test at NIM_MAX_MODEL_LEN 4096 returned HTTP 400 on every request",
   "R1": "A2 total latency per question is below A1's, but by less than the generation-rate ratio: A2/A1 total latency between 0.35 and 0.8 (generation-rate ratio about 0.24)",
   "R2": "A2 spends more completion tokens per question than A1: A2/A1 completion tokens between 1.1 and 2.5",
   "R3": "truncation at 4096 falls below 10% of completions on both arms",
   "R4": "the reasoning channel is exposed as a separate field (reasoning_content) on at least one arm",
   "confidence": "R1 medium, R2 low, R3 medium, R4 low",
   "reading": "a failed R is reported as failed; pass is P1-P3 plus the health gate"},
 "outputs": ["requests.jsonl", "events.jsonl", "analysis.json", "ctx.txt", "logs/ (not published)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p53_answer.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
