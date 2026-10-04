"""Compares the Llama Guard 3 cells of three runs: the first run (committed results) and the two quiet repeats.
Written before the repeats ran; the reading rule is the one in BEFORE_THE_RUN.md.
One arm only. Reads each run's LG3/summary.json (made by p102_analyze.py --arm LG3) and the c=16 per-item files.
usage: compare_runs.py            (run from the repository root)
"""
import json, os, sys

FIRST = "vol3-judges/results/p102_followup"
QUIET = sys.argv[1:3] if len(sys.argv) >= 3 else ["vol3-judges/results/lg3_timing_repeats/quiet_run_1", "vol3-judges/results/lg3_timing_repeats/quiet_run_2"]   # two arguments: a test of this program on planted folders


def summary(d):
    return json.load(open(os.path.join(d, "LG3", "summary.json"), encoding="utf-8"))


def metrics(s, track):
    t = s["tracks"][track]
    return {"c1_p50_ms": t["c1"]["latency_ms"]["p50"], "c1_p99_ms": t["c1"]["latency_ms"]["p99"],
            "c16_verdicts_per_s": round(t["quality_cell"]["verdicts_per_s"], 1),
            "c16_p50_ms": t["quality_cell"]["latency_ms"]["p50"], "c16_p99_ms": t["quality_cell"]["latency_ms"]["p99"],
            "c1_verdicts_per_s": round(t["c1"]["verdicts_per_s"], 1)}


def read(first, quiet):
    lo, hi = min(quiet), max(quiet)
    if lo <= first <= hi:
        return "inside the two quiet runs"
    end = lo if first < lo else hi
    if abs(first - end) <= 0.05 * end:
        return "within 5% of the nearer quiet run"
    return "outside the two quiet runs, " + ("below" if first < lo else "above")


def outcomes(d, name):
    rows = {}
    for line in open(os.path.join(d, "LG3", name), encoding="utf-8"):
        r = json.loads(line); rows[r["item_id"]] = (r.get("verdict"), r.get("status"))
    return rows


runs = [FIRST] + [q for q in QUIET if os.path.isfile(os.path.join(q, "LG3", "summary.json"))]
if len(runs) < 3:
    print("fewer than two quiet runs have a summary; comparing what is there:", runs[1:])
S = [summary(d) for d in runs]
out = {"runs": ["first run (host not left alone)"] + [f"quiet run {i}" for i in range(1, len(runs))], "tracks": {}}
for track in ("input", "output"):
    M = [metrics(s, track) for s in S]
    print(f"\n{track} track")
    print("  metric".ljust(24) + "".join(n.ljust(16) for n in ["first", "quiet 1", "quiet 2"][: len(runs)]) + "reading")
    rows = {}
    for k in ("c1_p50_ms", "c1_p99_ms", "c16_verdicts_per_s", "c16_p50_ms", "c16_p99_ms"):
        vals = [m[k] for m in M]
        reading = read(vals[0], vals[1:]) if len(vals) == 3 else "one quiet run only: no spread"
        rows[k] = {"first": vals[0], "quiet": vals[1:], "reading": reading}
        print("  " + k.ljust(22) + "".join(str(v).ljust(16) for v in vals) + reading)
    # positive control of the comparison: c=16 must be several times the c=1 rate in every run
    ratios = [round(m["c16_verdicts_per_s"] / m["c1_verdicts_per_s"], 2) for m in M]
    rows["control_c16_over_c1_rate"] = {"ratios": ratios, "pass": all(r >= 3 for r in ratios)}
    print("  control: c=16 rate / c=1 rate per run:", ratios, "->", "pass" if all(r >= 3 for r in ratios) else "FAIL")
    # the same arm judged again: per-item outcomes of each quiet c=16 cell against the first run's c=16 cell
    base = outcomes(FIRST, f"{track}_c16.jsonl"); same = []
    for d in runs[1:]:
        o = outcomes(d, f"{track}_c16.jsonl")
        assert set(o) == set(base), "the item sets differ"
        same.append({"same_outcome": sum(o[i] == base[i] for i in base), "of": len(base)})
    rows["same_outcome_as_first_run_c16"] = same
    print("  same outcome as the first run's c=16 cell:", [f"{x['same_outcome']} of {x['of']}" for x in same])
    # quality figures of each run, to see that the repeat judged the same thing
    q = [{g: (s["tracks"][track]["quality"][g]["detection"] or {}).get("k") for g in s["tracks"][track]["quality"]} for s in S]
    rows["detection_counts_per_group"] = q
    print("  detection counts per group, per run:", q)
    out["tracks"][track] = rows
json.dump(out, open("vol3-judges/results/lg3_timing_repeats/comparison.json", "w", encoding="utf-8", newline="\n"), indent=1)
print("\nwritten: vol3-judges/results/lg3_timing_repeats/comparison.json")
