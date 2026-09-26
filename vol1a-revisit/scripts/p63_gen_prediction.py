#!/usr/bin/env python3
"""Vol.1-A revisit, P63 · write prediction_p63_gsm8k.json once, before the measured run.
usage: p63_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "vol1b", "scripts"))
from prediction_guard import check_prediction

OUT = os.path.join(REPO, "vol1a-revisit", "results", "p63_gsm8k")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()
HT = json.load(open(os.path.join(OUT, "harness_test_record.json"), encoding="utf-8"))
p = {
 "experiment": "Vol.1-A revisit, P63 · Llama 3.1 8B Instruct on one RTX 5090 · GSM8K (gsm8k_cot_llama, all 1,319 items) again on the four P62 configurations (N-BF16, N-FP8, O-Q4, O-FP16), with the generation cap raised from 256 to 1024 tokens and N-BF16 run twice.",
 "written_at": sys.argv[1],
 "written_before": "the measured run's first container. run_p63_gsm8k.sh refuses to start if this file or its .sha256 is missing or changed, or if items/ exists.",
 "why": "P62's GSM8K cells were null under two gates whose definitions were wrong, not under a measurement fault: (1) 'finish_reason length below 1%' mixed a truncated prompt (checked separately and passed) with an output that reached the cap, which is model behaviour and is scored; with lm-eval's default cap of 256 even the reference reached it on 3.2% of items; (2) 'items whose correctness differs between two runs of the reference <= 2%' tested a quantity that the paired interval already contains; the question an equivalence test must answer first is whether it can call a configuration equal to itself. P62's pre-registration and results are not changed; this is a new measurement under a new pre-registration, not P62's data re-scored under new rules.",
 "scope": "Answer quality on GSM8K only, with this tool, task version and prompt format, at temperature 0; the comparison is between arms, item by item. IFEval and MMLU are not re-run.",
 "setup": {"harness": "vol1a-revisit/scripts/p63_gsm8k.py, which imports P62's harness (vol1a-revisit/scripts/p62_quality.py) unchanged and changes two things: lm-eval gen_kwargs max_gen_toks=1024, and the per-item join by lm-eval's own response (P62's post-run correction, from the start)",
           "unchanged_from_p62": "images, NIM profiles 092ed421 (bf16) and c4789f7a (fp8), Ollama 0.34.4 llama3.1:8b (Q4_K_M, 16 slots) and llama3.1:8b-instruct-fp16 (8 slots), context 8,192, lm-eval 0.4.13 (lmeval_venv_freeze.txt, unchanged since P62), local-chat-completions through the logging proxy, 8-shot multi-turn chat, concurrency 8, temperature 0, the task's stop strings, residency, P59's health gate, template probe",
           "runs": "O-Q4 main -> N-BF16 main, N-BF16 repeat (same container) -> O-FP16 main -> N-FP8 main",
           "g1": "g1_scorer_controls.json is P62's (same tool, same task; the scorer does not depend on the generation cap): GSM8K positive 1.0, negative 0.0136"},
 "rules": {"program": "vol1a-revisit/scripts/p63_gsm8k_analyze.py (10 self-test cases; mutating the cap check, the positive-control bound, the sensitivity filter, G4, the template offset or G1 each fails one case)",
           "cap_check": "every request of a run must carry max_tokens 1024 in the proxy's record (max_tokens_seen == [1024]); otherwise that run is void",
           "cells": "per arm (run main): accuracy with Wilson 95% interval; null with reasons if G1, cap check, join, G3, G2a (prompt tokens within +-5% of N-BF16's after the constant template offset) or G4 (identical request sha256) fails",
           "positive_control": "N-BF16 repeat minus N-BF16 main, paired bootstrap 95% interval: it must lie entirely inside +-2 pp, else every comparison's verdict is null (the method cannot call a configuration equal to itself)",
           "cap_hits": "an output that reaches the cap is scored as lm-eval scores it (in practice wrong); each run's share is reported and is not a gate",
           "comparisons": "N-FP8, O-FP16, O-Q4 minus N-BF16 main: difference in pp, paired bootstrap 95% interval, exact McNemar p; verdict within (interval inside +-2) / outside (interval entirely beyond) / undetermined",
           "sensitivity": "the same comparison over the items where neither arm reached the cap; reported, never a verdict"},
 "harness_test": HT.get("summary", ""),
 "predictions": {
   "basis": "P62: GSM8K cap-reached share 2.0-3.2% at 256 tokens; N-BF16 84.2% (cell null); N-BF16 against itself [-0.30, +1.67] pp; O-Q4 sensitivity reading -2.21 [-4.03, -0.47]",
   "P63-1": "the share of outputs reaching the cap falls below 1% on every arm, and is not zero on every arm (what remains is looping)",
   "P63-2": "N-BF16 accuracy slightly above P62's 84.2% (reasoning cut at 256 tokens now completes)",
   "P63-3": "the positive control lies inside +-2 pp",
   "P63-4": "N-FP8: within",
   "P63-5": "O-FP16: within",
   "P63-6": "O-Q4: point estimate between -1 and -3 pp, verdict most likely undetermined",
   "P63-7": "every request of every run carries max_tokens 1024",
   "confidence": "P63-1 medium, P63-2 medium, P63-3 medium, P63-4 medium, P63-5 medium, P63-6 low, P63-7 high",
   "reading_of_predictions": "a failed prediction is reported as failed; nothing is re-run. If the positive control fails, GSM8K stays descriptive and is not re-run."},
 "harness_sha256": {k: h(k) for k in ("vol1a-revisit/scripts/p63_gsm8k.py", "vol1a-revisit/scripts/p63_gsm8k_analyze.py", "vol1a-revisit/scripts/p63_gsm8k_postrun.py",
                                      "vol1a-revisit/scripts/run_p63_gsm8k.sh", "vol1a-revisit/scripts/p62_quality.py", "vol1a-revisit/scripts/p62_quality_analyze.py",
                                      "vol1a-revisit/scripts/p59_nim_value.py", "vol2/scripts/p54_engine.py", "vol1a-revisit/results/p63_gsm8k/g1_scorer_controls.json",
                                      "vol1b/scripts/prediction_guard.py")},
}
check_prediction(p)
path = os.path.join(OUT, "prediction_p63_gsm8k.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
