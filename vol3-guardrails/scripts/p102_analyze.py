#!/usr/bin/env python3
"""P102 · analysis of ONE follow-up arm, or of the passthrough check. The definitions are the ones of the judge study
(p93_analyze.py, imported): detection, false alarm, no-verdict share, accuracy and F1 over the items with a verdict,
per-call duration, output tokens.

Scope rule, unchanged: every figure is about one arm. This program takes one --arm and reads per-item files only below
results/p102_followup/<arm>/. The passthrough check has two server settings of one judge; each setting is counted on
its own and no item of one setting is compared with the same item of the other.

  --arm LG3   quality from the c=16 cell (whole track), duration from the c=1 cell (200-item subset) and the c=16 cell
  --arm N2R   quality from the c=1 cell (whole track; there is no c=16 cell for this judge), duration at c=1 on the rows
              of the same 200-item subset the other arms use
  --passthrough   per server setting: what the rail decided on the 100 items, what the answers read as, what the three
                  shape requests showed. `control_reproduced` is true when the setting without the argument blocked all
                  100; when it is false the check has no conclusion.
  --table     results/p102_followup/table.md from the summary files (aggregates only)
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p93_common import RESULTS as P93, read_jsonl, sha256_file  # noqa: E402
from p93_analyze import outcome, quality, rate, timing  # noqa: E402
from p102_cells import RESULTS  # noqa: E402

ARMS = {"LG3": {"judge": "Llama Guard 3 8B", "served_by": "upstream vLLM (reference arm, not a NIM)", "quality_mode": "c16"},
        "N2R": {"judge": "Nemotron Nano 9B v2", "served_by": "NIM", "quality_mode": "c1"}}


def arm(name):
    arm_dir = os.path.join(RESULTS, name); A = ARMS[name]
    items = read_jsonl(os.path.join(P93, "items.jsonl")); subsets = json.load(open(os.path.join(P93, "subsets.json"), encoding="utf-8"))
    cells = read_jsonl(os.path.join(arm_dir, "cells.jsonl")) if os.path.isfile(os.path.join(arm_dir, "cells.jsonl")) else []
    cell = {(c["track"], c["mode"]): c for c in cells}; read_files = []

    def rows_of(track, mode):
        p = os.path.join(arm_dir, f"{track}_{mode}.jsonl")
        if not os.path.isfile(p):
            return None
        read_files.append({"file": os.path.basename(p), "sha256": sha256_file(p)})
        return read_jsonl(p)

    S = {"arm": name, **A, "tracks": {}}; pre = {}
    for track in ("input", "output"):
        p = os.path.join(arm_dir, f"precheck_{track}.json")
        if os.path.isfile(p):
            d = json.load(open(p, encoding="utf-8")); pre[track] = {k: d.get(k) for k in ("pass", "reasoning_switch", "at")}
    S["precheck"] = pre; qm = A["quality_mode"]
    for track in ("input", "output"):
        T = {}; full = rows_of(track, qm)
        usable = bool(pre.get(track, {}).get("pass")) and full is not None and bool(cell.get((track, qm), {}).get("complete"))
        T["usable"] = usable
        T["why_not"] = None if usable else ("precheck failed or missing" if not pre.get(track, {}).get("pass") else "the quality cell is missing or incomplete")
        if usable:
            gold_key = "gold_input" if track == "input" else "gold_output"
            pool = [it for it in items if track in it["tracks"]]; groups = {}
            for ds in sorted({it["dataset"] for it in pool}):
                groups[ds] = {it["item_id"]: it[gold_key] for it in pool if it["dataset"] == ds}
            if track == "input":
                groups["xstest_harmless_only"] = {it["item_id"]: "safe" for it in pool if it["dataset"] == "xstest" and it["gold_input"] == "safe"}
                groups["aegis2_needs_caution_only"] = {it["item_id"]: it["gold_input"] for it in pool if it.get("needs_caution_only")}
            T["quality"] = {g: quality(full, gold) for g, gold in groups.items() if gold}
            T["quality_cell"] = {"mode": qm, **timing(full, cell.get((track, qm)))}
            sub = set(subsets[f"c1_{track}"]["items"])
            if qm == "c1":
                T["c1"] = {"rows": "the 200-item subset, taken from the whole-track c=1 cell", **timing([r for r in full if r["item_id"] in sub], None)}
            else:
                c1 = rows_of(track, "c1")
                if c1 is not None and cell.get((track, "c1"), {}).get("complete"):
                    T["c1"] = timing(c1, cell.get((track, "c1")))
                    first = {r["item_id"]: outcome(r) for r in full}; both = [r for r in c1 if r["item_id"] in first]
                    T["same_outcome_at_c1_and_c16"] = rate(sum(outcome(r) == first[r["item_id"]] for r in both), len(both))
        S["tracks"][track] = T
    S["files_read"] = read_files; S["per_item_files_read_from"] = os.path.relpath(arm_dir, RESULTS).replace(os.sep, "/")
    json.dump(S, open(os.path.join(arm_dir, "summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    for track, T in S["tracks"].items():
        if not T["usable"]:
            print(f"{name} {track}: null ({T['why_not']})"); continue
        for g, q in T["quality"].items():
            d, f = q["detection"], q["false_alarm"]
            fmt = lambda x: "-" if x["rate"] is None else f"{x['k']}/{x['n']} = {x['rate']:.3f} [{x['wilson95'][0]:.3f}, {x['wilson95'][1]:.3f}]"  # noqa: E731
            print(f"{name} {track} {g}: detection {fmt(d)} · false alarm {fmt(f)} · no verdict {q['no_verdict']['share']:.3f}")


def passthrough():
    base = os.path.join(RESULTS, "passthrough"); S = {"settings": {}}
    for label in ("off", "on"):
        p = os.path.join(base, label, "passthrough.json")
        if not os.path.isfile(p):
            S["settings"][label] = None; continue
        d = json.load(open(p, encoding="utf-8")); rows = read_jsonl(os.path.join(base, label, d["result_file"])) if d.get("result_sha256") else []
        blocked = sum(str(r.get("rail", "")).startswith("block") for r in rows)
        S["settings"][label] = {"n": d["n"], "complete": d["complete"], "rail": d["rail"], "rail_blocked": blocked, "verdict_read_from_the_answer": d["verdict"],
                                "answers_with_reasoning": d["answers_with_reasoning"],
                                "answers_whose_content_still_carries_closing_think": d["answers_whose_content_still_carries_closing_think"],
                                "answers_with_reasoning_moved_out_of_the_content": d["answers_with_reasoning_moved_out_of_the_content"],
                                "malformed_think_log_lines": d["run"].get("malformed_think_log_lines"), "request_shapes": d["request_shapes"],
                                "window": [d["start"], d["end"]], "result_sha256": d.get("result_sha256")}
    off = S["settings"].get("off")
    S["control_reproduced"] = bool(off and off["complete"] and off["rail_blocked"] == off["n"])
    S["conclusion"] = None if not S["control_reproduced"] else ("see settings.on" if S["settings"].get("on") else "the server did not start with the argument; see events.jsonl")
    json.dump(S, open(os.path.join(base, "summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"control_reproduced": S["control_reproduced"], **{k: (v and {"rail": v["rail"], "verdict": v["verdict_read_from_the_answer"]}) for k, v in S["settings"].items()}}))


def table():
    pct = lambda x: "-" if not x or x["rate"] is None else f"{100 * x['rate']:.1f}% [{100 * x['wilson95'][0]:.1f}, {100 * x['wilson95'][1]:.1f}] ({x['k']}/{x['n']})"  # noqa: E731
    L = ["# P102 · follow-up arms, each on its own line with its own interval", "",
         "| Arm | Judge | Track · group | Detection (Wilson 95%) | False alarm (Wilson 95%) | No verdict | c=1 p50 / p99, ms | c=16 verdicts/s | Output tokens p50 |", "|---|---|---|---|---|---|---|---|---|"]
    for name in ARMS:
        p = os.path.join(RESULTS, name, "summary.json")
        if not os.path.isfile(p):
            continue
        S = json.load(open(p, encoding="utf-8"))
        for track, T in S["tracks"].items():
            if not T["usable"]:
                L.append(f"| {name} | {S['judge']} | {track} | null: {T['why_not']} | | | | | |"); continue
            c1 = T.get("c1") or {}; qc = T["quality_cell"]
            lat = f"{c1['latency_ms']['p50']:.0f} / {c1['latency_ms']['p99']:.0f}" if c1.get("latency_ms", {}).get("p50") is not None else "-"
            vps = f"{qc['verdicts_per_s']:.1f}" if qc.get("concurrency") == 16 else "not run"
            for g, q in T["quality"].items():
                L.append(f"| {name} | {S['judge']} | {track} · {g} | {pct(q['detection'])} | {pct(q['false_alarm'])} | {100 * q['no_verdict']['share']:.1f}% | {lat} | {vps} | {qc['completion_tokens']['p50']} |")
    open(os.path.join(RESULTS, "table.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print("\n".join(L))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("--arm", choices=sorted(ARMS)); ap.add_argument("--passthrough", action="store_true"); ap.add_argument("--table", action="store_true")
    a = ap.parse_args()
    if a.arm:
        arm(a.arm)
    if a.passthrough:
        passthrough()
    if a.table:
        table()
    return 0


if __name__ == "__main__":
    sys.exit(main())
