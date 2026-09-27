#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q2 + Q4 · write prediction_p62_levels.json once, before the measured run.
usage: p62_gen_prediction_levels.py <written_at>"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "vol1b", "scripts"))
from prediction_guard import check_prediction

OUT = os.path.join(REPO, "vol1a-revisit", "results", "p62_levels")
h = lambda p: hashlib.sha256(open(os.path.join(REPO, p), "rb").read()).hexdigest()
p = {
 "experiment": "Vol.1-A revisit, P62 Q2 + Q4 · Llama 3.1 8B Instruct on one RTX 5090 · the chat profile (C) at 1, 2, 4 and 8 concurrent requests for the five P59 configurations, to place the NIM-vs-Ollama crossing that P59 could only put 'between 1 and 8'; and Ollama 4-bit (O-Q4) also at 9, 12 and 16, with `ollama ps` sampled every second, to find where its total throughput stops being flat.",
 "written_at": sys.argv[1],
 "written_before": "the measured run's first container. run_p62_levels.sh refuses to start if this file or its .sha256 is missing or changed, or if levels.jsonl exists.",
 "why": {"Q2": "P59 measured 1, 8, 16, 32, 64, 128. On profile C, N-BF16 was behind O-Q4 at 1 and ahead at 8 on both total and per-user throughput, so the crossing could only be placed between 1 and 8.",
         "Q4": "P59's O-Q4 (16 slots) served 172 tok/s in total at c=1 and 175 at c=8, then 597 at c=16. Before this run, P59's per-request timestamps (kept locally, not published) were read without the GPU: at c=8 up to 8 requests were decoding at the same time, and all 8 for about two thirds of the level, each at roughly an eighth of the single-stream rate. So the slots were in use; that reading does not say why eight concurrent decodes add no throughput, so the ticket's one targeted re-run is done. c=9 is added to the ticket's 4, 8, 12, 16 because a limit on the batch size of one code path would show as a step between 8 and 9; this is a hypothesis about the decoder's internals, not something this run can see."},
 "scope": "Speed only, profile C (200+-50 input / 200+-50 output tokens, AIPerf 0.11.0 closed loop). Main containers only (no fresh-container repeats). NIM on this card uses vLLM profiles only; nothing here says what NIM does on data-centre GPUs.",
 "arms": "the five P59 configurations as frozen in vol1a-revisit/results/p59_nim_value/prediction_p59_nim_value.json, with the Ollama slot counts P59 found instead of re-walking its ladder: O-Q4 OLLAMA_NUM_PARALLEL 16, O-FP16 8, O-Q4-def not set; NIM arms N-BF16 (profile 092ed421) and N-FP8 (profile c4789f7a); context 8,192 on every arm",
 "order": "O-Q4 -> N-BF16 -> O-FP16 -> N-FP8 -> O-Q4-def (P59's order)",
 "harness": "vol1a-revisit/scripts/p62_levels.py, which imports P59's harness unchanged: isolation check, prefix-cache detector, discarded 120 s warm-up level (seed 20260926+9000), the harness's own calibration (20 requests, fresh connection each), levels 60 s each with seed 20260926+n, --use-legacy-max-tokens on every arm, client token counts. Added: per level, the share of time with k requests decoding at once (from AIPerf's per-request export, first token to last), and, for O-Q4 only, `ollama ps` sampled every second from its first measured level to its last.",
 "analysis_rules": {"program": "vol1a-revisit/scripts/p62_levels_analyze.py (9 self-test cases), which runs P59's frozen analysis program on this run's files: the same gates, container checks, profile-C calibration, level usability, SLO cells and crossing rule ('between X and Y' from a change of sign between two consecutive usable levels, never interpolated)",
   "anchors": "c=1 and c=8 of every arm are reported beside P59's value for the same cell; a ratio outside 0.85-1.15 is flagged 'anchor moved' and reported, not corrected, and the crossing is read from this run's levels only",
   "q4": "flat_to_8: total at c=4 and at c=8 each between 0.80 and 1.25 x total at c=1. step: the first of 9, 12, 16 whose total >= 1.5 x total at c=8, reported as 'between <previous level> and L'. Any `ollama ps` sample not showing 100% GPU is counted and reported.",
   "reading": "If flat_to_8 holds and the step is between 8 and 9, the report says the O-Q4 total stays flat up to 8 concurrent requests and rises from 9, which is consistent with a batch-size limit of 8 on one code path, not shown by this run. If the step is elsewhere or absent, that is reported as measured. 'Cannot be determined' is a legal outcome."},
 "predictions": {
   "basis": "P59's C-profile values (N-BF16 87 / 607 tok/s total at c=1 / 8, O-Q4 172 / 175, O-Q4-def 183 / 199, O-FP16 79 / 317, N-FP8 151 / 1,099) and a roughly linear rise of the NIM arms' total between 1 and 8",
   "L1": "N-BF16 vs O-Q4, total throughput: the crossing is between 2 and 4 (N-BF16 about 170 at c=2 against O-Q4 about 175)",
   "L2": "N-BF16 vs O-Q4-def, total throughput: the crossing is between 2 and 4",
   "L3": "N-BF16 vs O-Q4, per-user throughput (1 / inter-token latency): the crossing is between 2 and 4",
   "L4": "N-BF16 vs O-FP16 and N-FP8 vs N-BF16, total throughput: N-BF16 and N-FP8 respectively ahead at every level 1-8",
   "L5": "every anchor (c=1 and c=8 of every arm) within 0.85-1.15 of P59",
   "L6": "O-Q4: flat_to_8 holds (c=4 and c=8 within 0.80-1.25 of c=1)",
   "L7": "O-Q4: the step is between 8 and 9",
   "L8": "every O-Q4 `ollama ps` sample shows 100% GPU",
   "confidence": "L1 low (c=2 is close to a tie), L2 low, L3 low, L4 high, L5 medium, L6 high, L7 low, L8 high",
   "reading_of_predictions": "a failed prediction is reported as failed; nothing is re-run to agree with a prediction"},
 "harness_sha256": {k: h(k) for k in ("vol1a-revisit/scripts/p62_levels.py", "vol1a-revisit/scripts/p62_levels_analyze.py", "vol1a-revisit/scripts/run_p62_levels.sh",
                                      "vol1a-revisit/scripts/p59_nim_value.py", "vol1a-revisit/scripts/p59_analyze.py", "vol2/scripts/p54_engine.py",
                                      "vol1a-revisit/results/p59_nim_value/analysis.json", "vol1b/scripts/prediction_guard.py")},
}
check_prediction(p)
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "prediction_p62_levels.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", path)
