#!/usr/bin/env python3
"""P20 v2 · write prediction_p20v2.json once, before the measured run.
usage: p20v2_gen_prediction.py <written_at>   (pass "$(date +%FT%T%z)")"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol1b", "results", "p20_coresidence_v2")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.1-B · P20 v2 · co-residence of NIM and Ollama on one GPU, with Ollama alone measured through both addresses",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p20v2.sh refuses to start if this file or its .sha256, or the v1 sample.json or its "
                   ".sha256, is missing or changed, or if requests.jsonl exists.",
 "runs": "one run; not repeated to obtain a different outcome",
 "relation_to_v1": "v1 (vol1b/results/p20_coresidence, committed) stands as run. v2 is a new pre-registration with two changes: "
                   "(1) Ollama alone is measured through 127.0.0.1 and through localhost on every question, so the client-side "
                   "address delay found during v1 becomes a measured quantity; (2) after every Ollama unload, unmeasured NIM "
                   "warm-up requests are sent until GPU memory in use is back within 1,000 MiB of the NIM-alone level, because "
                   "in v1 half of the NIM-alone requests followed an unload while part of NIM's memory was still outside the GPU.",
 "question": "On this machine: (a) how large is the effect of co-residence on each engine, against a clean alone baseline; "
             "(b) what is the NIM/Ollama throughput ratio alone through each Ollama address and co-resident; (c) how large is "
             "the client-side delay of addressing Ollama as localhost?",
 "not_a_replication": "the stack differs from Vol.1 (NIM 2.0.12, explicit sampling settings, today's Ollama). No figure is to be "
                      "set against 7.3x or 221 ms by subtraction.",
 "stack": {"nim_image": "nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12",
           "nim_index_digest": "sha256:d2c94c1d654c3e80b8bc08cc83298d2ba4e219dff41d1092555795edb93c6545",
           "nim_profile": "092ed4213624e774d24cdaf84e3b6222839bab2008a21d3c214ab46626366f90",
           "nim_profile_description": "vllm-bf16-tp1-pp1",
           "nim_env": "NIM_MAX_MODEL_LEN=8192 · VLLM_USE_V2_MODEL_RUNNER=0 · all other NIM settings default",
           "nim_launcher": "vol1b/scripts/p17_container.sh (unchanged)",
           "ollama": "0.34.0 (recorded again in versions.txt)", "ollama_model": "llama3.1:8b, id 46e0c10c039e (Q4 GGUF)"},
 "harness_sha256": {k: h(k) for k in ("vol1b/scripts/p20v2_coresidence.py", "vol1b/scripts/p20v2_analyze.py",
                                      "vol1b/scripts/run_p20v2.sh", "vol1b/scripts/p20_analyze.py",
                                      "vol1b/scripts/p17_container.sh", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {"vol1b/results/p20_coresidence/sample.json": h("vol1b/results/p20_coresidence/sample.json"),
                         "benchmark/questions.json": h("benchmark/questions.json")},
 "design": {
   "arms": {"S-N": "NIM alone via localhost:8000; Ollama unloaded; GPU memory back at the NIM-alone level (see recovery)",
            "S-OL": "Ollama alone via 127.0.0.1:11434; NIM container stopped",
            "S-OH": "Ollama alone via localhost:11434 -- the address Vol.1's harness used; NIM container stopped",
            "C": "co-resident; NIM via localhost:8000, then 2 s, Ollama via 127.0.0.1:11434, then 2 s"},
   "sample": "the 50 questions and run order of v1's sample.json (seed 20260917); one round",
   "order": "S-OL and S-OH on even run positions (NIM stopped; both arms on each question, which one first alternates in "
            "pairs of positions) -> NIM up -> S-N and C on all 50 (even positions S-N then C, odd C then S-N) -> NIM down -> "
            "S-OL and S-OH on odd run positions",
   "recovery": "the NIM-alone level is GPU memory in use 10 s after NIM is ready and before any Ollama load. After each "
               "unload, 16-token NIM requests (not measured) are sent until memory in use is at least that level minus "
               "1,000 MiB, at most 10 of them; each is recorded as an event. Every S-N row carries the level and the floor.",
   "payload": "Vol.1 run_benchmark.py payloads plus temperature 0.0 and top_p 0.9, NIM include_usage, timeout 300 s; no "
              "response text stored (SHA-256 and length only)",
   "warm_up": "an unmeasured 16-token request per Ollama address at the start of each S-O phase, one after the first "
              "co-resident load, the launcher's discarded first NIM request; and the first measured request of each series "
              "is dropped (49 valid per series)",
   "connect_probe": "three GETs through localhost and three through 127.0.0.1 at the start of each phase",
   "prompt_cache": "observed in the v2 harness test: when the same prompt is sent to Ollama twice in a row, the second answer "
                   "can differ from the first (Ollama reuses the previous request's prompt cache), while a prompt sent after a "
                   "different prompt returns the same text as in other arms. The second address arm on each question is "
                   "therefore a repeat. Which address goes first alternates in pairs of run positions, so each address is "
                   "first on half the questions; the analysis reports the TTFT difference separately for each order."},
 "analysis_rules": {
   "preconditions": "P1 no errors, all HTTP 200 · P2 isolation and address at every request (S-N: Ollama not listed and GPU "
                    "memory at or above the recorded floor; S-OL/S-OH: no container; C: both up; each row's address equals "
                    "its arm's) · P3 first request of each series dropped, 49 valid · P4 one row per question in each of the "
                    "five series. Any failure -> every conclusion field is null.",
   "statistics": "ratio of means over questions valid in both series, 95% bootstrap CI (2000 resamples of questions, seed "
                 "20260917), median per-question ratio; for the address delay, the per-question difference S-OH minus "
                 "S-OL with a bootstrap CI of its mean, its median, min and max",
   "program": "vol1b/scripts/p20v2_analyze.py (16 self-test cases; 8 mutations each make at least one case fail)"},
 "predictions": {
   "basis": "P20 v1 (committed): NIM TTFT co-resident / alone 2.55 with an unclean alone series, and about 15x-22x against "
            "its clean half (post-hoc); Ollama TTFT co-resident / alone 10.9; tps ratios 0.87 (NIM) and 0.62 (Ollama); "
            "NIM/Ollama tps 0.39 alone and 0.55 co-resident; localhost probe 2,024-2,088 ms against 8.6-21.9 ms. "
            "Vol.1 E2 (published): Ollama TTFT never below 2,405.9 ms in 300 requests. Seen before this file was written: "
            "the v2 harness test on the three questions outside the sample (harness_test/).",
   "confidence": "medium for R1-R3, low for R4",
   "R1": "NIM TTFT, C / S-N: ratio of means >= 5 (the alone series is now clean)",
   "R2": "address delay, S-OH minus S-OL TTFT: median over all questions between 1,500 and 2,500 ms",
   "R3": "NIM/Ollama tps is larger through localhost than through 127.0.0.1 (SN/SOH > SN/SOL)",
   "R4": "NIM/Ollama tps through 127.0.0.1 is below 1 (Ollama faster alone)",
   "recorded_not_predicted": "every other ratio; whether recovery needed any warm-up request; the Ollama GPU share",
   "reading": "a failed R is reported as failed and does not void the run; pass is P1-P4"},
 "outputs": ["requests.jsonl", "events.jsonl", "analysis.json", "versions.txt", "ctx.txt", "memory_clamp_line.txt",
             "metrics_at_ready.txt", "logs/<run tag>/"]}

check_prediction(p)
check_prediction({"stack": {"profile": p["stack"]["nim_profile"]}})
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p20v2.json")
if os.path.exists(path):
    sys.exit("prediction_p20v2.json exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
