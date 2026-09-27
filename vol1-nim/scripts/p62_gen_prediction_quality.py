#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q1 · write prediction_p62_quality.json once, before the measured run.
usage: p62_gen_prediction_quality.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "vol1b", "scripts"))
from prediction_guard import check_prediction
sys.path.insert(0, HERE)
import p62_quality_analyze as QA

OUT = os.path.join(REPO, "vol1a-revisit", "results", "p62_quality")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()
G1 = json.load(open(os.path.join(OUT, "g1_scorer_controls.json"), encoding="utf-8"))
HT = json.load(open(os.path.join(OUT, "harness_test_record.json"), encoding="utf-8"))
FREEZE = open(os.path.join(OUT, "logs", "lmeval_venv_freeze.txt"), encoding="utf-8").read().split()
pin = [l for l in FREEZE if l.split("==")[0].lower() in ("lm_eval", "datasets", "transformers", "torch", "nltk", "langdetect", "immutabledict", "aiohttp")]
p = {
 "experiment": "Vol.1-A revisit, P62 Q1 · Llama 3.1 8B Instruct on one RTX 5090 · answer quality of the four configurations whose speed P59 measured (N-BF16, N-FP8, O-Q4, O-FP16) on three public task sets: GSM8K (all 1,319), IFEval (all 541) and a 2,850-item MMLU sample (50 from each of 57 subjects). The question: is the faster configuration faster because it answers worse?",
 "written_at": sys.argv[1],
 "written_before": "the measured run's first container. run_p62_quality.sh refuses to start if this file or its .sha256 is missing or changed, or if items/ exists.",
 "scope": "Answer quality on these three task sets with this tool, task version and prompt format, at temperature 0. The absolute accuracies depend on the prompt format (the same model's GSM8K accuracy moves by several points between prompt formats), so they are not set beside other publications' numbers as a result; the comparison is between arms, item by item. Nothing here says anything about speed.",
 "tool": {"lm_evaluation_harness": "0.4.13 (pinned; the venv's package list is kept in logs/lmeval_venv_freeze.txt)", "pinned_packages": pin,
          "backend": "local-chat-completions through a logging proxy on 127.0.0.1 (vol1a-revisit/scripts/p62_quality.py), chat template applied by each server, few-shot examples as multi-turn chat, concurrency 8 (lm-eval num_concurrent), max_retries 3, timeout 1,800 s",
          "tasks": {"gsm8k_cot_llama": "8-shot, generation until the task's stop strings (the backend sends the first four) or 256 tokens (lm-eval's default; the task sets none), primary metric exact match with the strict-match filter ('The final answer is N'); flexible-extract also recorded",
                    "ifeval": "0-shot, up to 1,280 tokens, primary metric prompt-level strict accuracy; prompt-level loose and both instruction-level accuracies recorded",
                    "mmlu_llama": "5-shot, the task's assistant prefix 'The best answer is', up to 10 tokens, stop '.', exact match (strict_match filter); restricted to mmlu_sample_ids.json"},
          "request_fields": "the backend sends max_tokens (not max_completion_tokens), temperature 0 (IFEval sets 0.0; the other two send the backend default 0), seed 1234 and the stop list; for MMLU the request also carries continue_final_message=true and add_generation_prompt=false (see mmlu_prefix)",
          "mmlu_prefix": "mmlu_llama ends every prompt with an assistant message 'The best answer is'. Sent as is, vLLM closes that message and opens a new assistant turn; Ollama continues it. The two fields make vLLM continue it as Ollama does. They are sent to every arm, so the request bodies stay identical (G4). Shown in the harness test: see harness_test.",
          "mmlu_sample": {"file": "vol1a-revisit/results/p62_quality/mmlu_sample_ids.json", "sha256": h("vol1a-revisit/results/p62_quality/mmlu_sample_ids.json"),
                          "rule": "random.Random(f'20260926:{subject}').sample(range(n_test_items), 50) per mmlu_llama subject, sorted"}},
 "arms": {"N-BF16": "NIM 2.0.12, profile 092ed421 (vllm-bf16), NIM_MAX_MODEL_LEN 8192, VLLM_USE_V2_MODEL_RUNNER=0 -- the reference",
          "N-FP8": "NIM 2.0.12, profile c4789f7a (vllm-fp8, the profile NIM selects on this card when nothing is set), same settings",
          "O-Q4": "ollama/ollama:latest (0.34.4), llama3.1:8b (manifest 46e0c10c039e), OLLAMA_CONTEXT_LENGTH 8192, OLLAMA_NUM_PARALLEL 16 (P59); its quantization is recorded from `ollama show`, not assumed",
          "O-FP16": "ollama/ollama:latest, llama3.1:8b-instruct-fp16 (manifest 4aacac419454), OLLAMA_CONTEXT_LENGTH 8192, OLLAMA_NUM_PARALLEL 8 (P59)",
          "order": "O-Q4 -> N-BF16 -> O-FP16 -> N-FP8; per arm GSM8K, IFEval, MMLU; then N-BF16's repeat of all three (noise floor), N-FP8's GSM8K at concurrency 1 and 32",
          "note": "FP16 and bf16 are both 16-bit formats with different ranges: 'comparable precision', not 'the same precision'"},
 "extra_runs": {"noise_floor": "N-BF16 runs all three task sets twice in the same container (the ticket asks for GSM8K; IFEval and MMLU are added so that each task has its own noise floor)",
                "concurrency": "N-FP8 runs GSM8K at concurrency 1 and 32 in addition to its concurrency-8 run"},
 "gates": {"G1": "scorer controls, run through lm-eval's own pipeline with a stand-in model before this file was written (no GPU, no model): values below. Rule: GSM8K positive 1.0 and negative <= 0.05; MMLU positive 1.0 and negative 0.15-0.35; IFEval constructed positive 1.0 and both negatives <= %.2f. A failed G1 makes every cell of that task null." % QA.G1_IFEVAL_NEG,
           "G1_measured": G1,
           "G2": "per arm and task, every item's server prompt-token count within +-5% of N-BF16's for the same item after removing the arm's constant template offset (N-BF16 minus the arm for the one-word probe message; NIM arms 0), and finish_reason 'length' on < 1% of items; else that cell is null",
           "G3": "the arm's residency (Ollama `ollama ps` 100% GPU; NIM CUDA graphs captured) and P59's health gate (decode rate at c=1 from 20 own-client calibration requests x bytes per token / 1,792 GB/s >= 0.40); else every cell of that arm is null",
           "G4": "every item's request sha256 (request body without 'model') equal to N-BF16's, same item set; else that cell is null",
           "join": "every item joined to exactly one proxy record by the sha of its messages, with the proxy's output text equal to lm-eval's; else that cell is null"},
 "statistics": {"program": "vol1a-revisit/scripts/p62_quality_analyze.py (13 self-test cases), reading only the published files",
                "per_cell": "accuracy with a Wilson 95% interval",
                "paired": "arm minus N-BF16 over the same items: difference in pp, paired bootstrap 95% interval (10,000 resamples, fixed seed), exact McNemar p",
                "equivalence": "bound +-2 pp for all three tasks: interval inside -> 'within'; entirely beyond -> 'outside'; otherwise 'undetermined'. Null if either cell is null or the task's noise floor (share of items whose correctness differs between N-BF16's two runs) exceeds 2 pp; the bound is not changed.",
                "sensitivity": "reported, never a verdict: the paired comparison over the items where neither arm's output ended with finish_reason 'length' (the output cap); a model that loops until the cap is not a truncated prompt, but G2 counts it as the ticket defines G2",
                "concurrency": "N-FP8 GSM8K c=1 vs c=32 (and each against c=8): accuracies, paired interval, McNemar p, correctness agreement, identical-output share"},
 "public_content": "per item: task, item id, correct, the extracted answer (GSM8K the number the filter took, MMLU the letter or '[other]', IFEval one boolean per instruction), request / messages / output sha256, output length in characters, server prompt and completion tokens, finish_reason. Output text stays in the local process files. analysis.json is recomputed from the published files alone after the run and must match byte for byte (recompute_check.txt).",
 "harness_test": HT.get("summary", ""),
 "predictions": {
   "basis": "third-party measurements of this model: FP8 weights keep about 99% of bf16's accuracy, 4-bit integer weights about 98.7% (arXiv 2411.02355); llama.cpp quantization of this model is studied in arXiv 2601.14277. These set expectations only; they are not arms.",
   "Q1-1": "N-FP8 minus N-BF16 within +-1 pp (point estimate) on each of the three tasks",
   "Q1-2": "O-FP16 minus N-BF16 within +-1 pp on each task",
   "Q1-3": "O-Q4 minus N-BF16 no lower than -3 pp on each task",
   "Q1-4": "N-BF16 GSM8K strict-match accuracy between 78% and 88%",
   "Q1-5": "noise floor (N-BF16 run twice): correctness differs on <= 2% of items on each task",
   "Q1-6": "N-FP8 GSM8K: c=1 and c=32 accuracies within 1 pp of each other, with fewer than 100% identical outputs",
   "Q1-7": "every arm passes G2, G3 and G4 on every task",
   "Q1-8": "`ollama show` reports O-Q4's quantization as Q4_K_M (the harness test already showed it)",
   "Q1-9": "GSM8K finish_reason 'length' below 1% on every arm (the harness test had 1 of 3 N-BF16 items at the 256-token cap; this is the prediction most at risk of nulling GSM8K cells through G2)",
   "confidence": "Q1-1 medium, Q1-2 medium, Q1-3 medium, Q1-4 medium, Q1-5 low, Q1-6 medium, Q1-7 low, Q1-8 high, Q1-9 low",
   "reading_of_predictions": "a failed prediction is reported as failed; nothing is re-run to chase a result"},
 "harness_sha256": {k: h(k) for k in ("vol1a-revisit/scripts/p62_quality.py", "vol1a-revisit/scripts/p62_quality_analyze.py", "vol1a-revisit/scripts/p62_quality_postrun.py",
                                      "vol1a-revisit/scripts/p62_scorer_controls.py", "vol1a-revisit/scripts/p62_mmlu_sample.py", "vol1a-revisit/scripts/run_p62_quality.sh",
                                      "vol1a-revisit/scripts/p59_nim_value.py", "vol2/scripts/p54_engine.py", "vol1a-revisit/results/p62_quality/g1_scorer_controls.json",
                                      "vol1b/scripts/prediction_guard.py")},
}
check_prediction(p)
path = os.path.join(OUT, "prediction_p62_quality.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
