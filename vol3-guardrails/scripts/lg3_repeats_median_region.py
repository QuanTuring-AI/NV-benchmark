"""Exploratory, written after the repeat (not part of the rule fixed before it). For each arm on its own: how thin is
the region of the c=1 per-call durations in which the median falls? Reads each arm's committed c=1 per-item file.
A wide p45..p55 span means the p50 moves a lot when a few calls shift; a narrow one means it does not.
No figure here combines two arms."""
import glob, json, math, os


def nr(v, p):
    v = sorted(v); return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


files = sorted(glob.glob("vol3-guardrails/results/p93_judges/J[0-6]/input_c1.jsonl")) + ["vol3-guardrails/results/p102_followup/LG3/input_c1.jsonl",
        "vol3-guardrails/results/lg3_timing_repeats/quiet_run_1/LG3/input_c1.jsonl", "vol3-guardrails/results/lg3_timing_repeats/quiet_run_2/LG3/input_c1.jsonl"]
print("arm (input track, c=1, 200 calls) | p25  p45  p50  p55  p75 ms | p55-p45 as a share of p50 | completion tokens p25/p50/p75")
for f in files:
    rows = jl(f); v = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    t = [r.get("completion_tokens") or 0 for r in rows]
    arm = f.replace("\\", "/").split("/")[-2] + (" " + f.replace("\\", "/").split("/")[-3] if "quiet" in f else "")
    q = {p: nr(v, p) for p in (25, 45, 50, 55, 75)}
    print(f"  {arm:18} | {q[25]:7.1f} {q[45]:7.1f} {q[50]:7.1f} {q[55]:7.1f} {q[75]:7.1f} | {(q[55] - q[45]) / q[50]:6.1%} | {nr(t, 25)}/{nr(t, 50)}/{nr(t, 75)}  n={len(v)}")
