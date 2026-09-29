#!/usr/bin/env python3
"""P20 · write prediction_p20.json. Run once, before the measured run; the output is frozen with a .sha256 sidecar.
usage: p20_gen_prediction.py <written_at>   (pass "$(date +%FT%T%z)")"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol1b", "results", "p20_coresidence")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.1-B · P20 · co-residence of NIM and Ollama on one GPU, against each engine alone",
 "written_at": sys.argv[1],
 "written_before": "the measured run. run_p20.sh refuses to start if this file or its .sha256, or sample.json or its .sha256, "
                   "is missing or changed, or if requests.jsonl exists.",
 "runs": "one run; not repeated to obtain a different outcome",
 "question": "How large is the effect of NIM and Ollama sharing one GPU -- the condition under which Vol.1 measured 7.3x and "
             "221 ms, which was neither recorded nor controlled -- on TTFT, end-to-end latency and throughput, compared "
             "with each engine alone?",
 "not_a_replication": "the stack differs from Vol.1 (NIM 2.0.12 instead of 1.13.1; explicit temperature and top_p; today's "
                      "Ollama). No figure from this run is to be set against 7.3x or 221 ms by subtraction.",
 "stack": {"nim_image": "nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12",
           "nim_index_digest": "sha256:d2c94c1d654c3e80b8bc08cc83298d2ba4e219dff41d1092555795edb93c6545",
           "nim_profile": "092ed4213624e774d24cdaf84e3b6222839bab2008a21d3c214ab46626366f90",
           "nim_profile_description": "vllm-bf16-tp1-pp1",
           "nim_env": "NIM_MAX_MODEL_LEN=8192 · VLLM_USE_V2_MODEL_RUNNER=0 · all other NIM settings default",
           "nim_launcher": "vol1b/scripts/p17_container.sh (the cell 4 launcher, unchanged)",
           "ollama": "0.34.0 (recorded again in versions.txt at run time)",
           "ollama_model": "llama3.1:8b, id 46e0c10c039e (Q4 GGUF, as in Vol.1)",
           "vol1_ollama_version": "not recorded (DEPLOYMENT_NOTES.md says 'latest'; benchmark/README.md says 'version not recorded')"},
 "harness_sha256": {k: h(k) for k in ("vol1b/scripts/p20_coresidence.py", "vol1b/scripts/p20_analyze.py",
                                      "vol1b/scripts/run_p20.sh", "vol1b/scripts/p17_container.sh",
                                      "vol1b/scripts/p20_sample.py", "vol1b/scripts/prediction_guard.py")},
 "fixed_inputs_sha256": {"vol1b/results/p20_coresidence/sample.json": h("vol1b/results/p20_coresidence/sample.json"),
                         "benchmark/questions.json": h("benchmark/questions.json")},
 "design": {
   "arms": {"S-N": "NIM alone: container up, Ollama model unloaded; Ollama /api/ps empty before every request",
            "S-O": "Ollama alone: NIM container stopped; `docker ps` empty before every request",
            "C": "co-resident: NIM up and Ollama model loaded; one NIM request, 2 s, one Ollama request, 2 s -- the rhythm of "
                 "Vol.1 run_benchmark.py"},
   "sample": "50 of the 100 Vol.1 E2 questions, sample.json (seed 20260917; strata = four English categories and, inside "
             "multilingual, each language; every second question by length from a seeded start). One round.",
   "order": {"phases": "S-O on even run positions (NIM stopped) -> NIM up -> S-N and C on all 50, interleaved -> NIM down -> "
                       "S-O on odd run positions",
             "interleaving": "even positions run S-N then C, odd positions C then S-N, so each Ollama load or unload happens "
                             "once per question",
             "deviation_from_work_order": "the work order asks for all three arms rotated question by question. S-O requires the "
                                          "NIM container to be stopped, and a NIM start takes minutes, so S-O cannot rotate "
                                          "per question. It runs as two blocks placed before and after the NIM phase, so a "
                                          "drift over the run would show as a difference between the two halves."},
   "address": "both engines are addressed as 127.0.0.1, not localhost as in Vol.1. On this machine localhost resolves to ::1 "
              "first and Ollama listens on IPv4 only, so every request to http://localhost:11434 first spends about 2,050 ms "
              "being refused (measured 2026-09-17: localhost 2,044-2,079 ms, 127.0.0.1 6.5-23 ms). With localhost that "
              "constant would sit inside every Ollama TTFT and total latency and pull every Ollama ratio toward 1. Each phase "
              "records both addresses once (events.jsonl, kind connect_probe).",
   "payload": "Vol.1 run_benchmark.py payloads, plus temperature 0.0 and top_p 0.9 on both engines, NIM stream_options."
              "include_usage, and a request timeout of 300 s instead of 90 s. No response text is stored; each row keeps the "
              "SHA-256 and length of the response.",
   "measures": "TTFT and total latency (Vol.1 timing), tps by the Vol.1 formula (whitespace-split streamed fragments / total "
               "seconds), tps from engine-reported completion tokens / total seconds, completion tokens, finish reason, Ollama "
               "load / prompt-eval / eval durations, and before every request: GPU memory, Ollama /api/ps (size and size_vram), "
               "docker ps",
   "warm_up": "an unmeasured 'Hello' request after each Ollama load that starts a phase, and the launcher's discarded first NIM "
              "request; in addition the first measured request of each series is dropped (49 valid per series)"},
 "analysis_rules": {
   "preconditions": "P1 no request errors, all HTTP 200 · P2 isolation at every request (S-N: /api/ps lists no model; S-O: "
                    "docker ps lists nothing; C: /api/ps lists llama3.1:8b and docker ps lists the NIM container) · P3 first "
                    "request of each series dropped, 49 valid per series · P4 one row per question in each of the four series. "
                    "Any failure -> every conclusion field is null.",
   "effect": "ratio of means C / alone over questions valid in both, 95% bootstrap CI (2000 resamples of questions, seed "
             "20260917), and the median per-question ratio; metrics ttft_ms, total_latency_ms, tps, tps_usage",
   "throughput_ratio": "NIM / Ollama for tps and tps_usage, alone and co-resident, same statistics",
   "descriptive": "avg, p50 and p95 per series; completion tokens and finish reasons per series; Ollama GPU share per series",
   "program": "vol1b/scripts/p20_analyze.py (13 self-test cases; 7 mutations each make at least one case fail)"},
 "predictions": {
   "basis": "Vol.2 C (NIM 1.13.1, Ollama fully on the GPU beside NIM): NIM TTFT 13.9x its alone value. Vol.2 B' (Ollama GPU "
            "layers limited): about 3-4x. Vol.1 E2 (co-resident): NIM 73.8 and Ollama 10.1 words/s, Ollama TTFT 2,876 ms. "
            "Seen before this file was written: two harness tests on 2026-09-17 on the three questions outside the sample "
            "(q070, q043, q098). The first, through localhost, showed NIM TTFT alone 50-508 ms and co-resident 1,227-5,510 ms, "
            "NIM words/s alone 89-97 and co-resident 26-78, Ollama alone about 116 words/s on 500-token answers, the Ollama "
            "model reported fully in GPU memory in both Ollama arms with total GPU use near 31.9 GB co-resident, and the "
            "2-second localhost delay described under design.address. The second test, through 127.0.0.1, is recorded in "
            "harness_test/. No sampled question was run before this file was frozen.",
   "confidence": "low: the two earlier co-residence measurements differ from each other by a factor of three",
   "R1": "NIM TTFT, C / alone: ratio of means >= 2",
   "R2": "NIM tps (Vol.1 formula), C / alone: ratio of means < 1",
   "R3": "Ollama tps (Vol.1 formula), C / alone: ratio of means < 1",
   "R4": "NIM / Ollama tps ratio is larger co-resident than alone",
   "R5_recorded_not_predicted": "the size of every ratio, the Ollama GPU share co-resident, and whether Ollama's harness TTFT "
                                "tracks its eval duration in every arm",
   "reading": "R1-R4 are directions with one threshold (R1). A failed R is reported as failed; it does not void the run. "
              "Pass is P1-P4, not R1-R4."},
 "outputs": ["requests.jsonl (one line per request, written as it completes)", "events.jsonl", "analysis.json",
             "versions.txt", "ctx.txt", "memory_clamp_line.txt", "metrics_at_ready.txt", "logs/<run tag>/"]}

check_prediction(p)
check_prediction({"stack": {"profile": p["stack"]["nim_profile"]}})
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p20.json")
if os.path.exists(path):
    sys.exit("prediction_p20.json exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("written", path)
