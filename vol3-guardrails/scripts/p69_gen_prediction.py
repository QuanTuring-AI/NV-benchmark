#!/usr/bin/env python3
"""Vol.2, P69 · write prediction_p69.json once, before the first re-run level.
Paths are derived from this file's location and from the imported modules' own files; no volume directory name is written
here. usage: p69_gen_prediction.py <written_at>"""
import glob, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
RES = os.path.abspath(os.path.join(HERE, "..", "results"))
sys.path.insert(0, HERE)
import p69_clean_rerun as R  # noqa: E402  (imports P66's and P67's harnesses, and through them P59's)
from prediction_guard import check_prediction  # noqa: E402

rel = lambda p: os.path.relpath(os.path.abspath(p), REPO).replace(os.sep, "/")
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
find = lambda name: [p for p in glob.glob(os.path.join(REPO, "*", "scripts", name)) if "_internal" not in p][0]
items = R.rerun_list(); steps = R.plan(items)
D66, D67 = os.path.join(RES, "p66_rails_under_load"), os.path.join(RES, "p67_rails_server_config")
harness = [os.path.join(HERE, f) for f in ("p69_clean_rerun.py", "p69_analyze.py", "run_p69.sh", "p66_rails_under_load.py", "p66_gr_server.py", "p66_analyze.py",
                                           "p67_rails_server_config.py", "p67_gr_server.py", "p67_gr_app.py", "p67_analyze.py", "prediction_guard.py")] + [
    sys.modules["p59_nim_value"].__file__, find("p54_engine.py"), os.path.join(REPO, "tools", "g8_gate.py"), os.path.join(REPO, "tools", "overwrite_gate.py"), os.path.join(REPO, "tools", "cell_timeout.py")] + [
    os.path.join(D67, "configs", c, "config.yml") for c in ("default", "mt3", "passthrough")]
fixed = [os.path.join(D66, f) for f in ("levels.jsonl", "events_public.jsonl", "part_d_verdicts.jsonl", "stack.json", "analysis.json")] + [
    os.path.join(D67, f) for f in ("levels.jsonl", "events_public.jsonl", "part_d_verdicts.jsonl", "stack.json", "prediction_p67.json")]
by = {r: sum(1 for x in items if x["run"] == r) for r in ("P66", "P67")}
p = {
 "experiment": "Vol.2, P69 · the P66 and P67 levels that ran with other load on the desktop GPU, measured again in a clean window: Llama 3.1 8B Instruct on NIM 2.0.12 (bf16), NeMo Guardrails 0.23.0 servers as P66 / P67, synthetic chat 200 / 200, non-streaming.",
 "written_at": sys.argv[1],
 "written_before": "the first re-run level. run_p69.sh refuses to start if this file or its .sha256 is missing or changed, or if levels.jsonl exists.",
 "why": ("P66's N, P and R3 arms (morning of 2026-09-27) and P67's first levels (15:32-15:52, and two later levels) ended with the GPU at 3-19% "
         "utilization, where a window with no other load ends at 0% (P66's R1024 arm, 12:52-13:21). The user confirms GPU use on the desktop in those "
         "windows. In P66 the headline ratio R3 / R1024 has its numerator from such a window and its denominator from a clean one. The decision to "
         "re-run is made now, from the contamination, before any clean result is seen: the contamination is the reason, not a number."),
 "rerun_rule": "every level record of P66's and P67's levels.jsonl with gpu_end.util_pct > 2 (warm-up levels included) is repeated with the same arm, server configuration, concurrency, request count and seed",
 "rerun_list": {"cells": len(items), "by_run": by, "items": [{k: x[k] for k in ("run", "label", "concurrency", "warmup", "original_start")} | {"gpu_end_util_pct": x["gpu_end"].get("util_pct")} for x in items],
                "against_the_ticket_list": "the ticket expected 21 (P66) and 10 (P67); the rule gives 21 and 12: it also lists P67's R1024 W4K5 warm-up (16:39, util 3) and P_W1K5 at 64 (17:04, util 5), both after the reported game window. The rule is followed."},
 "plan": {"steps": [list(s) for s in steps], "one_nim_container": True,
          "same_window_ratio": "P66's R3 levels 1, 8, 16, 32 alternate with R1024 at the same levels (R1024 was clean in P66 and is repeated here), so R3 / R1024 at 1-32 has both terms in one window",
          "per_server_start": "P66 cells: P66's server (p66_gr_server.py); P67 cells: P67's server with their W and K. Each start runs its discarded warm-up level (c=8, 100 requests, seed 20260927 + 9000) and its G2 probes (P67 starts: per worker)"},
 "gates": {"G8": f"before every level, warm-ups included: tools/g8_gate.py ({R.G.SOURCE}); util p50 <= 2 % and power p50 <= 45 W over 10 samples at 1 Hz; retry every 60 s up to 15 min, else the cell is null; all samples recorded",
           "G8_positive_control": "once, after NIM is ready: G8 sampled while 4 requests decode on NIM; it must not pass",
           "timeout": "every level: max(3 x the original level's wall-clock duration, 300 s), at most 900 s (tools/cell_timeout.py; positive control: AIPerf against a socket that never answers is stopped at 20 s and reported hung). On a timeout the load generator is stopped, the level is recorded hung with what was in flight, the server is started again and the level is tried once more; a second timeout leaves it hung and the run goes on. P66's R1024 at 1 took 832 s, so its limit (900 s) leaves 8%.",
           "no_overwrite": "after every level: tracked files unchanged and new files only under this run's directory (tools/overwrite_gate.py), else the run stops",
           "carried_over": "P66's G1, G2, G5, G6 and P67's G2 (per worker) and G7, through their analysis programs unchanged"},
 "not_done": ["the contaminated original levels are not changed; contamination_marks.jsonl names them with their fingerprint",
              "Part D is not repeated: a verdict does not depend on speed; the P67 Part D pass that overlapped the reported window is marked in the README",
              "contaminated and clean cells are never mixed in one headline table"],
 "harness_test": "a first harness test (2026-09-27 21:41) stopped progressing at 21:53:59 on P67's R1024 W4K75 at 64 (AIPerf waiting for its last requests, NIM with nothing running or waiting, the four workers idle, 12 connections established on the server port held by the parent process); its state was recorded before it was stopped (hang_evidence_p69_test_20260927T214149.json, beside this file). The per-level timeout was added after it.",
 "predictions": {
   "R1": "the G8 positive control does not pass; G8 passes before every re-run level",
   "R2": "after the re-run, P67's N anchors are within +-5% of P66's N at 32, 64 and 128 (G7 on clean cells on both sides)",
   "R3": "in the clean window R3 / R1024 at 1, 8, 16 and 32 is within 1.5-1.8",
   "R4": "contaminated against clean: reported only; no statement of the form 'the background slowed X by Y%'",
   "reading_of_predictions": "a failed prediction is reported as failed; nothing is re-run to chase a result"},
 "analysis_rules": {"program": f"{rel(os.path.join(HERE, 'p69_analyze.py'))} (9 self-test cases; each of 7 mutations -- the band, the positive-control and G8 conditions, the G2 aggregation, either view's replacement, a ratio's direction -- makes at least one fail); P66's and P67's analysis programs imported unchanged"},
 "harness_sha256": {rel(f): h(f) for f in harness},
 "fixed_inputs_sha256": {rel(f): h(f) for f in fixed},
}
check_prediction(p)
path = os.path.join(RES, "p69_clean_rerun", "prediction_p69.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", rel(path), by, len(steps), "steps")
