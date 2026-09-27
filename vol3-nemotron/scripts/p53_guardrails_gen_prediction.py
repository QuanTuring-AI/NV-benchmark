#!/usr/bin/env python3
"""Vol.2 · Guardrails 0.23.0 × Nemotron · write prediction_p53_guardrails.json once, before the measured run.
usage: p53_guardrails_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p53_guardrails")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.2 · NeMo Guardrails 0.23.0 on Nemotron Nano 9B v2 (NIM 1.12.2) and Nemotron 3 Nano (NIM 2.0.12): end-to-end overhead and rail cost, Vol.1-A E3 question set",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p53_guardrails.sh refuses to start if this file or its .sha256 is missing or changed, or if rows.jsonl exists.",
 "runs": "one run",
 "why": "Vol.2's module ladder is NIM x two model families x Guardrails 0.23.0; without this block the volume has two modules. The E9 result used the old stack and does not count.",
 "stack": {"guardrails": "nemoguardrails 0.23.0 in its own venv (the Vol.1-B worker, vol1b/scripts/gr_worker.py, one persistent event loop per worker)",
           "rail_config": "Vol.1's benchmark/guardrails/config.yml with the model name substituted and top_p 0.9 added (as the Vol.1-B bridge did); the self-check prompts and their max_tokens 1024 are the library's defaults, not changed",
           "A1": "nvidia-nemotron-nano-9b-v2:1.12.2, bf16, NIM_MAX_MODEL_LEN 8192, NIM_MAX_NUM_SEQS 32",
           "A2": "nemotron-3-nano:2.0.12, NVFP4, NIM_MAX_MODEL_LEN 8192, NIM_PASSTHROUGH_ARGS --max-num-seqs 32",
           "nim_only_payload": "Vol.1 E3 payload (max_tokens 500, temperature 0.0, stream) + top_p 0.9 + stream_options.include_usage"},
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p53_guardrails.py", "vol2/scripts/p53_guardrails_analyze.py", "vol2/scripts/run_p53_guardrails.sh",
                                      "vol2/scripts/p50_footprint.py", "vol1b/scripts/bridge_2x2.py", "vol1b/scripts/gr_worker.py", "vol1b/scripts/bridge_analyze.py", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {"benchmark/e3_questions.json": h("benchmark/e3_questions.json"), "benchmark/guardrails/config.yml": h("benchmark/guardrails/config.yml"), "vol2/scripts/guardrails_nothink/config.yml": h("vol2/scripts/guardrails_nothink/config.yml")},
 "design": {"cells": "per container arm, three request arms rotated per question: N (nim-only), G (Guardrails 0.23.0 with Vol.1's rail config verbatim), H (Guardrails 0.23.0 with E9's variant of the same config: identical prompts sent with a /no_think system message, vol2/scripts/guardrails_nothink/config.yml), 2 s after every request; 45 questions x 3 rounds; one warm-up request per request arm excluded. H is an addition beyond the four cells asked for: without it the G cell alone cannot separate the rail's cost from the judge's reasoning habit",
            "two_quantities": "end-to-end wall-clock overhead (G/N on clean_passthrough, Vol.1-A's algorithm, includes the output-length effect) and rail cost (self_check_input / self_check_output call durations and tokens from rails.explain()); never mixed",
            "reasoning": "both models reason by default; the judge prompts are sent as the library sends them; what comes back (verdict, empty content, truncation at 1024) is recorded per call and reported",
            "branches": "if the worker cannot connect to a container's endpoint the G cell of that arm is skipped and the error recorded verbatim; if a G answer comes back empty it is counted, not repaired"},
 "analysis_rules": {"preconditions": "per arm: P1 no errors and HTTP 200 on every N row · P2 135 N and 135 G rows, one per (question, round) · P3 one container up. Any failure -> that arm's conclusions null.",
                    "statistics": "clean_passthrough avg ratio (Vol.1-A algorithm); paired Σ(G)/Σ(N)-1 over questions passed in both arms with a 95% bootstrap CI over questions (5000 draws, seed 20260921)",
                    "program": "vol2/scripts/p53_guardrails_analyze.py (10 self-test cases; judge arms G and H analysed separately, each requiring 135 rows)"},
 "predictions": {
   "basis": "Vol.1-B cell 4 (Llama 8B, NIM 2.0.12, GR 0.23.0): clean_passthrough +34.5% end to end, rail cost dominated by the output self-check at max_tokens 1024; Nemotron models reason by default. Harness test 2026-09-22 (A1, two clean questions, G only): the self_check_input judge returned 188-209 tokens per call (reasoning instead of yes/no) and the rail blocked both clean questions (refusal, 35 chars); G end-to-end was therefore faster than N (-60%) because a block skips the answer. That is why arm H exists; R1/R4 below were written before the test and are kept, and R1 is now expected to fail for G",
   "R1": "end-to-end clean_passthrough overhead is above +25% on both arms (per judge arm; H expected to behave as Vol.1-B did, G expected to fail this by blocking)",
   "R2": "at least one arm has G rows whose judge call hit 1024 tokens or returned an empty verdict (recorded count > 0)",
   "R3": "adversarial true blocks under G are between 30 and 45 of 45 per round-set on both arms (this sample; not a model property)",
   "R4": "false blocks on clean and edge questions are at most 5 of 90 per container arm under H; under G they are expected to be the majority",
   "confidence": "R1 medium, R2 medium, R3 low, R4 low",
   "reading": "a failed R is reported as failed; pass is P1-P3 per arm. Detection differences from Vol.1-A's 42/45 are sample differences and are not written as a comparison of models."},
 "outputs": ["rows.jsonl (no response text; SHA-256 and length)", "events.jsonl", "analysis.json", "gr_config_<arm>/config.yml", "versions.txt", "ctx.txt", "logs/ (not published)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p53_guardrails.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
