#!/usr/bin/env python3
"""Footprint addendum · write prediction_p50_footprint_addendum.json once, before the addendum run.
usage: p50_footprint_addendum_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p50_footprint_addendum")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.2 · footprint addendum · Nemotron 3 Nano (NVFP4) minimum budget with NIM_MAX_BATCH_SIZE=32",
 "written_at": sys.argv[1],
 "written_before": "the addendum run; the main footprint run (vol2/results/p50_footprint) is complete and is not re-run",
 "runs": "one run",
 "why": "in the main run A2 failed at budgets 0.70 and 0.725 with 'max_num_seqs (256) exceeds available Mamba cache blocks (146)': the bound was the per-sequence Mamba state for the default 256 sequences, not the KV cache. A single-user deployment does not need 256 sequences. This addendum lowers max_num_seqs to 32 (NIM_MAX_BATCH_SIZE, the NIM 2.0.12 variable mapped to it) and repeats the same sweep; A1 already ran with NIM_MAX_NUM_SEQS=32 in the main run, so this also puts the two arms on the same sequence limit.",
 "stack": "as vol2/results/p50_footprint/prediction_p50_footprint.json for A2, plus NIM_MAX_BATCH_SIZE=32",
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p50_footprint_addendum.py", "vol2/scripts/p50_footprint.py",
                                      "vol2/scripts/p50_footprint_analyze.py", "vol2/scripts/run_p50_footprint_addendum.sh")},
 "fixed_inputs_sha256": {"benchmark/questions.json": h("benchmark/questions.json")},
 "design": "identical to the main run's per-arm sequence (default, then 0.85 down in 0.05 steps until failure, then one 0.025 step); same probe (q001, q004, q011 with /no_think, finish_reason stop at max_tokens 1024); rows carry arm label A2B32 and are analysed with the main analyzer after relabelling to A2",
 "predictions": {
   "basis": "main run: A2 passed at 0.75 (25,972 MiB at READY, KV 1,146,880 tokens) and failed at 0.725 on Mamba blocks; NVFP4 weights 19.34 GB on disk; A1 (17.78 GB bf16, 32 sequences) reached 0.70 and failed at 0.675 on KV blocks",
   "R1": "the smallest passing budget is at most 0.70 (22,825 MiB), i.e. below the main run's 0.75",
   "R2": "the first failure below it is a KV-block refusal, not a Mamba-block refusal",
   "confidence": "R1 medium, R2 low",
   "reading": "a failed R is reported as failed; pass is the main analyzer's P1-P3"},
 "outputs": ["configs.jsonl", "analysis.json", "logs/ (not published)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p50_footprint_addendum.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
