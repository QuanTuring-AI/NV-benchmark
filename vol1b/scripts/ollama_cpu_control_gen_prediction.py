#!/usr/bin/env python3
"""Ollama CPU control · write prediction_ollama_cpu_control.json once, before the measured run.
usage: ollama_cpu_control_gen_prediction.py <written_at>   (pass "$(date +%FT%T%z)")"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol1b", "results", "ollama_cpu_control")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.1-B · Ollama CPU control · the final Ollama measurement in this repository",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_ollama_cpu_control.sh refuses to start if this file or its .sha256, or the P20 "
                   "sample.json or its .sha256, is missing or changed, or if requests.jsonl exists.",
 "runs": "one run; not repeated to obtain a different outcome",
 "purpose": "to measure, on this machine, the generation rate of the same Ollama model when none of it is in GPU memory, "
            "next to the same model fully in GPU memory in the same run. It closes out the Vol.1-A comparison; it does not "
            "reproduce any earlier machine state and does not open a new comparison.",
 "stack": {"ollama": "0.34.0 (recorded again in versions.txt)", "ollama_model": "llama3.1:8b, id 46e0c10c039e (Q4_K_M GGUF)",
           "address": "http://127.0.0.1:11434 only", "nim": "not started; the run refuses to start if any container runs",
           "machine": "CPU model and memory modules recorded by the run in versions.txt",
           "sysmem_fallback_policy": "the NVIDIA Control Panel setting 'CUDA - Sysmem Fallback Policy' is not readable by "
                                     "the harness; it is recorded separately, with its source, and is not changed"},
 "harness_sha256": {k: h(k) for k in ("vol1b/scripts/ollama_cpu_control.py", "vol1b/scripts/ollama_cpu_control_analyze.py",
                                      "vol1b/scripts/run_ollama_cpu_control.sh", "vol1b/scripts/p20v2_coresidence.py")},
 "fixed_inputs_sha256": {"vol1b/results/p20_coresidence/sample.json": h("vol1b/results/p20_coresidence/sample.json"),
                         "benchmark/questions.json": h("benchmark/questions.json")},
 "design": {
   "arms": {"G": "default placement; /api/ps must show size_vram == size",
            "CPU": "options.num_gpu = 0; /api/ps must show size_vram == 0"},
   "sample": "G: the first three questions of the P20 run order; CPU: all 50 questions in the P20 run order",
   "order": "unload -> G warm-up (16 tokens, not measured) -> G on 3 questions -> unload -> CPU warm-up -> CPU on 50 -> unload",
   "placement_gate": "after each warm-up the placement is read; if it is not the arm's required placement the run stops "
                     "before any measured request of that arm, exits 3, and no analysis is run. Placement is also read "
                     "before and after every measured request; a change stops the run the same way.",
   "payload": "Vol.1 run_benchmark.py payload plus temperature 0.0, top_p 0.9, max 500 tokens, keep_alive 60m; 2 s between "
              "requests; timeout 900 s; no response text stored (SHA-256 and length only)",
   "dropped": "none; each arm's model load happens in its warm-up"},
 "analysis_rules": {
   "preconditions": "P1 no errors, all HTTP 200 · P2 placement before and after every request as required by its arm, and "
                    "no container · P3 3 G rows and 50 CPU rows, one per question. Any failure -> conclusions null.",
   "generation_rate": "client: tokens / (total latency - TTFT), tokens counted as in Vol.1 (whitespace words); engine: "
                      "eval_count / eval_duration. Median over requests.",
   "program": "vol1b/scripts/ollama_cpu_control_analyze.py (14 self-test cases; 9 mutations each make at least one case fail)"},
 "predictions": {
   "seen_before_this_file": "a single 16-token request with num_gpu 0 (size_vram 0; eval 16 tokens in 1,336 ms), and two "
                            "harness tests on the three harness-test questions (CPU client-rate medians 10.78 and 10.87, "
                            "G 234.8 and 237.7). The band below was set in the ruling before any of these.",
   "R1": "median client generation rate of the CPU arm between 5 and 40 tokens per second (recorded, not a gate)",
   "R2": "placement as required at every request (this is precondition P2; if it fails, nothing is concluded)",
   "recorded_not_predicted": "the engine rate, the G/CPU ratio on the G questions, TTFT, prompt evaluation time, "
                             "machine details",
   "reading": "a failed R1 is reported as failed and does not void the run; pass is P1-P3"},
 "outputs": ["requests.jsonl", "events.jsonl", "analysis.json", "versions.txt", "ctx.txt", "logs/<run tag>/"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_ollama_cpu_control.json")
if os.path.exists(path):
    sys.exit("prediction_ollama_cpu_control.json exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
