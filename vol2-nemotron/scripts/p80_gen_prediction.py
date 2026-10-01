#!/usr/bin/env python3
"""Vol.2 · P80 · write prediction_p80_gates.json: the gates added to the G6 / G5 re-run and their references (file:line).
The P78 pre-registrations (prediction_p78_clean_rerun.json, prediction_p78_n2_upstream.json) are not changed and stay in
force. Frozen before the first container; the freeze step scans the file before its .sha256 sidecar is written.
usage: p80_gen_prediction.py "<$(date +%FT%T%z)>" "<windows boot time>"   -> vol2-nemotron/results/p80_rerun/prediction_p80_gates.json
"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "..", "results", "p80_rerun"); os.makedirs(OUT, exist_ok=True)
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
rel = lambda p: os.path.relpath(p, REPO).replace(os.sep, "/")  # noqa: E731
BOUND = [os.path.join(HERE, f) for f in ("p80_rerun.py", "p80_judge.py", "p80_gen_prediction.py", "p80_postrun.py", "p78_clean_rerun.py", "p78_n2_upstream.py",
                                          "p78_engines.py", "p78_quality.py", "p78_nim_vs_vllm.py", "p53_concurrency_v2.py", "p50_footprint.py")] + \
        [os.path.join(REPO, "tools", f) for f in ("g8_gate.py", "host_gate.py", "overwrite_gate.py", "container_sentinel.py", "renumber_dirs.py")]
P55 = "vol2-nemotron/results/p55_concurrency_a2_256/levels.jsonl"
P53 = "vol2-nemotron/results/p53_concurrency_v2/levels.jsonl"

p = {
    "ticket": "P80", "written_at": sys.argv[1], "written_before": "the first container of the P80 night (p80_rerun.py, real run)",
    "scope": "the gates added to the P78 G6 and G5 runs; the P78 pre-registrations of those runs (prediction_p78_clean_rerun.json, prediction_p78_n2_upstream.json) stay in force unchanged",
    "order": ["s256_C", "s256_R", "v2_A2_C", "v2_A2_R", "v2_A1_C", "v2_A1_R", "G5"],
    "results": "vol2-nemotron/results/p80_rerun/ (a new directory; the stopped P78 G6 data in p78_clean_rerun/ are not touched)",
    "host": {"windows_boot": sys.argv[2], "note": "the host was rebooted at 13:28 on 2026-09-30 for P79 T2 and not again before this night (the owner's decision); P79 found no effect of uptime (T1 at day 7 and T2 after the reboot, 18/18 normal)"},
    "sentinel_G9": {
        "when": "per group, after the discarded 120 s warm-up level and the calibration, before the first measured level",
        "probes": "two 30 s AIPerf levels with p53_concurrency_v2's command: long input (profile R) at c=1, TTFT p50; short input (profile C) at the group's reference level, ITL p50",
        "rule": "each value <= 2 x its reference (tools/container_sentinel.py speed_check)",
        "fail": "the container is restarted once and probed again; a second failure makes the group null (reported, the next group runs)",
        "references": {
            "s256_C, s256_R": {"R_c1_ttft_p50_ms": [157.66, P55 + " line 16"], "short_level": 128, "C_c128_itl_p50_ms": [30.7, P55 + " line 9"]},
            "v2_A2_C, v2_A2_R": {"R_c1_ttft_p50_ms": [144.06, P53 + " line 36"], "short_level": 32, "C_c32_itl_p50_ms": [19.4, P53 + " line 30"],
                                 "why_32": "the sweep's max_num_seqs is 32; its original was measured there"},
            "v2_A1_C, v2_A1_R": {"R_c1_ttft_p50_ms": [318.93, P53 + " line 13"], "short_level": 16, "C_c16_itl_p50_ms": [19.69, P53 + " line 6"],
                                 "why_16": "this engine exits at 32 (P53); 16 is its highest level with a measured original"},
            "G5": "no reference (a new engine on this model): the two probes are recorded and not judged",
        },
        "reference_rows": "the measured rows of the original main sweeps, not their discarded warm-up rows (P79 used the warm-up row's 156 ms as its ticket wrote; this file uses the measured row)",
        "layer_1": "make_resident failures and the container's system-memory share at READY: recorded only (P79: present at every one of 7 normal loads)",
    },
    "arm_health": {
        "when": "before and after every measured cell",
        "probe": "c=1 for 10 s: streamed requests (p78_n2_upstream.one, max_tokens 400, one fixed prompt), generation-rate median",
        "rule": "after / before < 0.8 -> the cell is marked, the container restarted (warm-up level and calibration again) and the cell run once more; still < 0.8 -> the cell is null; the next cell runs",
        "not_applied": "a cell whose engine died (A1's engine exit at 32 is its ceiling, as in P53)",
    },
    "records_only": ["nvidia-smi every 500 ms (timestamp, SM and memory clocks, active throttle reasons, power, utilization, memory used) for each container's whole life, paused for each 10 s G8 sample",
                     "before and after every cell: the container's system-memory share, the desktop compositor's commitment, the WSL make_resident count (tools/container_sentinel.py)",
                     "the Windows GPU counters every 10 s, reduced (p80_postrun.reduce_map): no desktop process names are written"],
    "g8": "unchanged from P78 (before every cell, retried up to 15 min, a cell whose G8 did not pass is null). The 500 ms logger is paused during each 10 s G8 sample: it lifts the idle utilization reading from 2.0% to 2.5% (P79, 09:55), over G8's 2% line",
    "time_gate": "no new group, cell or context step once the stop time (--stop, default 08:00, before noon) is reached; an extension is a new --stop value written into run_start with --stop-reason",
    "judge": {
        "program": "vol2-nemotron/scripts/p80_judge.py (self_test: the positive control and two mutation tests)",
        "cell": "speed_ratio = total tok/s / the original main sweep at the same level; abnormal <= 0.5, normal >= 0.8, grey between; no original -> 'no original'",
        "shape": "the morning shape of 2026-09-30: utilization median >= 95% and power median <= 200 W over the cell's nvidia-smi rows, and speed_ratio <= 0.5 -> flagged; the cell is run to its end and recorded (P80 section 2)",
        "positive_control": "this morning's s256_R c=1 (99.8 vs 273.5 tok/s) and s256_C c=128 (543.3 vs 3,902.1 tok/s), vol2-nemotron/results/p78_clean_rerun/levels.jsonl lines 13 and 9, must be abnormal",
        "p78_predictions_judged": "s256_C P1 and P2 (prediction_p78_clean_rerun.json); G5 P1-P3 (prediction_p78_n2_upstream.json); every other sweep is recorded beside its original",
    },
    "branches": {"all_seven_normal": "the Vol.2 concurrency numbers are taken from this night; the dirty P53 / P55 cells are marked in the README as replaced by P80",
                 "sentinel_fails_twice": "that group null, reported, the next group runs",
                 "morning_shape_again": "the cell runs to its end; its full clock and memory curves are attached to the report",
                 "g5_fails_to_start": "what was tried and where it stopped is written; no other version is tried"},
    "refrozen": "an earlier freeze (2026-09-30T19:46:38, sidecar 3cee6f4e...) is kept under logs/superseded_*; p80_rerun.py then gained one test-only flag, --sentinel-scale (refused without --test), so that the path 'sentinel fails, restart, fails again, group null, next group' could be run with the real command line; nothing else changed and no real container had started",
    "harness_sha256": {rel(f): h(f) for f in BOUND},
}
path = os.path.join(OUT, "prediction_p80_gates.json")
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
print("written", rel(path), "binds", len(p["harness_sha256"]), "files")
