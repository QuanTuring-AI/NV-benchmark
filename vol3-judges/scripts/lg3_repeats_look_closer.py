"""Written AFTER the comparison showed the first run faster at c=1 than both quiet runs (not part of the rule fixed before
the run; exploratory, and labelled so in the report). One arm, three runs. Looks at where the c=1 difference sits:
card memory, warm-up, prechecks, the shape of the per-call durations and their per-item differences."""
import json, math, os, statistics

RUNS = [("first", "vol3-judges/results/p102_followup"), ("quiet1", "vol3-judges/results/lg3_timing_repeats/quiet_run_1"), ("quiet2", "vol3-judges/results/lg3_timing_repeats/quiet_run_2")]


def nr(v, p):
    v = sorted(v); return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


for name, d in RUNS:
    ev = [e for e in jl(os.path.join(d, "events.jsonl")) if e.get("step") in ("lg3", None)]
    print(f"\n== {name}")
    for e in ev:
        if e["kind"] == "run_start":
            print("  run_start", e["at"], "card", e["gpu"], "| processes listed", e["compute_processes_listed"], "| other containers", e["other_containers_running"])
        if e["kind"] == "container_ready" and e.get("step") == "lg3":
            print("  ready after", e["seconds"], "s | card at ready", e["gpu"])
        if e["kind"] == "warm_up" and e.get("step") == "lg3":
            print("  warm-up ms", [r["ms"] for r in e["five_short_requests"]])
        if e["kind"] == "g8" and e.get("step") == "lg3":
            t = e["gate"]["tries"][-1]
            print("  g8", e["at"][11:19], e.get("track"), e.get("mode"), "attempts", t.get("attempts"), "waited", t.get("waited_s"), "util", t["last"]["util_pct_p50"], "power", round(t["last"]["power_w_p50"], 1))
        if e["kind"] == "cell" and e.get("step") == "lg3":
            print("  cell", e["at"][11:19], e["track"], e["mode"], "rc", e["rc"], "after", {k: e["gpu_after"][k] for k in ("util_pct_p50", "power_w_p50", "pass")})
        if e["kind"] in ("card_after_the_run", "run_end"):
            print(" ", e["kind"], {k: v for k, v in e.items() if k not in ("kind",)})
    for c in jl(os.path.join(d, "LG3", "cells.jsonl")):
        print("  cell record", c["track"], c["mode"], c["start"][11:19], "-", c["end"][11:19], "| used MiB start/end", c["gpu_start"]["used_mib"], c["gpu_end"]["used_mib"], "| power at end", c["gpu_end"]["power_w"], "| wall", c["wall_s"])
    for tr in ("input", "output"):
        p = json.load(open(os.path.join(d, "LG3", f"precheck_{tr}.json"), encoding="utf-8"))
        print("  precheck", tr, "violating ms", p["control_violating"]["latency_ms"], "benign ms", p["control_benign"]["latency_ms"], "discarded warm-up ms", p["run"]["discarded_warm_up_ms"])

print("\n== shape of the per-call durations at c=1 (ms): p5, p25, p50, p75, p95, mean")
rows = {}
for name, d in RUNS:
    for tr in ("input", "output"):
        r = {x["item_id"]: x for x in jl(os.path.join(d, "LG3", f"{tr}_c1.jsonl"))}
        rows[(name, tr)] = r
        v = [x["latency_ms"] for x in r.values()]
        print(f"  {name:7} {tr:6}", [nr(v, q) for q in (5, 25, 50, 75, 95)], round(statistics.mean(v), 1),
              "| completion tokens:", dict(sorted({t: sum(x["completion_tokens"] == t for x in r.values()) for t in {x["completion_tokens"] for x in r.values()}}.items())),
              "| prompt tokens p50:", nr([x["prompt_tokens"] for x in r.values()], 50))
print("\n== per-item difference at c=1, quiet minus first (same items, same arm), ms: p5, p25, p50, p75, p95; share of items slower")
for q in ("quiet1", "quiet2"):
    for tr in ("input", "output"):
        a, b = rows[("first", tr)], rows[(q, tr)]
        dif = [b[i]["latency_ms"] - a[i]["latency_ms"] for i in a]
        print(f"  {q} {tr:6}", [round(nr(dif, p), 1) for p in (5, 25, 50, 75, 95)], "| slower in", sum(x > 0 for x in dif), "of", len(dif))
a, b = rows[("quiet1", "input")], rows[("quiet2", "input")]
dif = [b[i]["latency_ms"] - a[i]["latency_ms"] for i in a]
print("  quiet2 minus quiet1, input", [round(nr(dif, p), 1) for p in (5, 25, 50, 75, 95)], "| slower in", sum(x > 0 for x in dif), "of", len(dif))
print("\n== c=1 duration by output length (3 tokens = safe, 6 = unsafe + one category), p50 ms")
for name, d in RUNS:
    r = rows[(name, "input")]
    print(f"  {name:7}", {t: nr([x["latency_ms"] for x in r.values() if x["completion_tokens"] == t], 50) for t in sorted({x["completion_tokens"] for x in r.values()}) if sum(x["completion_tokens"] == t for x in r.values()) >= 10})
