#!/usr/bin/env python3
"""Footprint addendum 2 · write prediction_p50_footprint_addendum2.json once, before the run.
usage: p50_footprint_addendum2_gen_prediction.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..", "vol1b", "scripts"))
from prediction_guard import check_prediction

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "vol2", "results", "p50_footprint_addendum2")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()

p = {
 "experiment": "Vol.2 · footprint addendum 2 · Nemotron 3 Nano (NVFP4) minimum budget with vLLM max_num_seqs 32 via NIM_PASSTHROUGH_ARGS",
 "written_at": sys.argv[1],
 "written_before": "the run; the main footprint run and addendum 1 are complete and are not re-run",
 "runs": "one run",
 "why": "addendum 1 set NIM_MAX_BATCH_SIZE=32 and the engine still resolved max_num_seqs to 256 (its refusal named the same limit). In NIM 2.0.12 max_num_seqs is a per-profile engine argument; NIM_PASSTHROUGH_ARGS is the image's path for user engine arguments. If the value reaches the engine, the Mamba state cache shrinks from 256 to 32 sequences and the floor moves; if it does not, the sweep reproduces addendum 1 and that is the finding.",
 "stack": "as the main run's A2, plus NIM_PASSTHROUGH_ARGS=\"--max-num-seqs 32\"",
 "harness_sha256": {k: h(k) for k in ("vol2/scripts/p50_footprint_addendum2.py", "vol2/scripts/p50_footprint.py",
                                      "vol2/scripts/p50_footprint_analyze.py", "vol2/scripts/run_p50_footprint_addendum2.sh")},
 "fixed_inputs_sha256": {"benchmark/questions.json": h("benchmark/questions.json")},
 "design": "identical sweep and probe to the main run; rows carry arm label A2S32 and are analysed under the A2 label; the startup log's engine-argument line is recorded so that the resolved max_num_seqs is visible",
 "predictions": {
   "basis": "main run: A2 floor 0.75 (Mamba blocks 213 at 0.725, 146 at 0.70, 256 needed); addendum 1: identical, the setting did not reach the engine; A1 with 32 sequences reached 0.70",
   "R1": "the engine resolves max_num_seqs to 32 (visible in the startup log)",
   "R2": "given R1, the smallest passing budget is at most 0.70 (22,825 MiB)",
   "R3": "given R1, the first refusal below the floor is a KV-block refusal, not a Mamba-block refusal",
   "confidence": "R1 low (the mechanism is read from the image's code, not documented), R2 medium given R1, R3 low",
   "reading": "a failed R is reported as failed; pass is the main analyzer's P1-P3"},
 "outputs": ["configs.jsonl", "analysis.json", "logs/ (not published)"]}

check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p50_footprint_addendum2.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
