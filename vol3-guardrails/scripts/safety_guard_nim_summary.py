#!/usr/bin/env python3
"""Vol.3 · the Safety Guard 8B v3 NIM arms: one summary per arm, then one table of the summaries.

Scope rule of the study, kept here: every figure is about one arm. A per-item file of one arm is never read together
with a per-item file of another arm. The table is built from summary files only (aggregates).

  J6N, J6N-fp8, J6N-tpl   the study's own analysis program, unchanged: `p93_analyze.py --arm J6` run on the arm's folder
                          (through the view safety_guard_nim_run.py builds). It writes <arm>/summary.json.
  J6G                     written here: per track and data set, the rail's block share on harmful and on harmless
                          items, the verdict figures of the same completions (the study's `quality`), the duration of a
                          call, and how many items have a rail decision that differs from their own verdict, by class.
  table                   table.json / table.md: the arms that have a summary, and beside them the study's arm J6
                          (the same model on upstream vLLM), read from its summary.json.

usage: safety_guard_nim_summary.py [--arms J6N,J6N-fp8,J6N-tpl,J6G]
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from p93_common import RESULTS as P93_RESULTS, percentile, read_jsonl, sha256_file  # noqa: E402
from p93_analyze import quality, rate  # noqa: E402
from safety_guard_nim_run import RESULTS, view  # noqa: E402

DIRECT = ("J6N", "J6N-fp8", "J6N-tpl")


def direct_summary(arm):
    if not os.path.isfile(os.path.join(RESULTS, arm, "cells.jsonl")):
        return None
    v, b = view(arm)
    r = subprocess.run([sys.executable, os.path.join(HERE, "p93_analyze.py"), "--arm", "J6"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=dict(os.environ, P93_RESULTS=v, P93_BUCKET=b))
    if r.returncode != 0:
        sys.exit(f"{arm}: the analysis program ended with {r.returncode}: {r.stderr[-300:]}")
    p = os.path.join(RESULTS, arm, "summary.json")
    S = json.load(open(p, encoding="utf-8")); S["arm_of_this_folder"] = arm; S["request_shape_of"] = "J6"
    json.dump(S, open(p, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return S


def rail_summary():
    arm_dir = os.path.join(RESULTS, "J6G")
    if not os.path.isfile(os.path.join(arm_dir, "cells.jsonl")):
        return None
    items = read_jsonl(os.path.join(P93_RESULTS, "items.jsonl")); subsets = json.load(open(os.path.join(P93_RESULTS, "subsets.json"), encoding="utf-8"))
    cells = {c["track"]: c for c in read_jsonl(os.path.join(arm_dir, "cells.jsonl"))}
    S = {"arm": "J6G", "judge": "Llama 3.1 Nemotron Safety Guard 8B v3", "path": "guardrails_content_safety", "max_tokens": 50, "tracks": {}, "files_read": []}
    for track in ("input", "output"):
        T = {}; pre = os.path.join(arm_dir, f"precheck_{track}.json"); p = os.path.join(arm_dir, f"{track}_rail.jsonl")
        ok = os.path.isfile(pre) and json.load(open(pre, encoding="utf-8")).get("pass")
        T["usable"] = bool(ok and os.path.isfile(p) and cells.get(track, {}).get("complete"))
        T["why_not"] = None if T["usable"] else ("precheck failed or missing" if not ok else "the cell is missing or incomplete")
        if T["usable"]:
            rows = read_jsonl(p); S["files_read"].append({"file": os.path.basename(p), "sha256": sha256_file(p)})
            keep = set(subsets["gr_path"][track]); pool = [it for it in items if it["item_id"] in keep and track in it["tracks"]]
            gold_key = "gold_input" if track == "input" else "gold_output"
            groups = {ds: {it["item_id"]: it[gold_key] for it in pool if it["dataset"] == ds} for ds in sorted({it["dataset"] for it in pool})}
            groups["all_items_of_the_subset"] = {it["item_id"]: it[gold_key] for it in pool}
            T["quality"] = {g: quality(rows, gold) for g, gold in groups.items() if gold}
            lat = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]; tok = [r["completion_tokens"] for r in rows if r.get("completion_tokens") is not None]
            T["calls"] = {"n": len(rows), "latency_ms": {"p50": percentile(lat, 50), "p99": percentile(lat, 99)}, "completion_tokens": {"p50": percentile(tok, 50), "p99": percentile(tok, 99), "max": max(tok) if tok else None},
                          "finish_reason_length": sum(r.get("finish_reason") == "length" for r in rows), "wall_s": cells[track].get("wall_s")}
            classes = {}
            for r in rows:
                classes[r["same_call"]] = classes.get(r["same_call"], 0) + 1
            T["rail_beside_verdict_of_the_same_call"] = {"classes": classes, "agree": rate(classes.get("agree", 0), len(rows)),
                                                         "items_that_differ": sorted([{"item_id": r["item_id"], "class": r["same_call"], "finish_reason": r.get("finish_reason"), "completion_tokens": r.get("completion_tokens")}
                                                                                      for r in rows if r["same_call"] != "agree"], key=lambda x: x["item_id"])}
        S["tracks"][track] = T
    json.dump(S, open(os.path.join(arm_dir, "summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return S


def line(name, S, track, group):
    T = (S or {}).get("tracks", {}).get(track, {})
    if not T.get("usable"):
        return {"arm": name, "track": track, "usable": False, "why_not": T.get("why_not")}
    q = T["quality"].get(group)
    if q is None:
        return {"arm": name, "track": track, "usable": False, "why_not": f"no group {group}"}
    qc = T.get("quality_cell") or {}; c1 = T.get("c1") or {}; calls = T.get("calls") or {}
    out = {"arm": name, "track": track, "group": group, "usable": True, "items": q["items"], "harmful": q["harmful"], "harmless": q["harmless"],
           "detection": q["detection"], "false_alarm": q["false_alarm"], "f1_unsafe": q["f1_unsafe_over_items_with_verdict"], "no_verdict": q["no_verdict"],
           "c1_latency_ms_p50": (c1.get("latency_ms") or calls.get("latency_ms") or {}).get("p50"), "c1_latency_ms_p99": (c1.get("latency_ms") or calls.get("latency_ms") or {}).get("p99"),
           "c16_verdicts_per_s": qc.get("verdicts_per_s"), "c16_latency_ms_p99": (qc.get("latency_ms") or {}).get("p99"),
           "completion_tokens_p50": (qc.get("completion_tokens") or calls.get("completion_tokens") or {}).get("p50"),
           "stability": (T.get("stability") or {}).get("rate"), "same_outcome_at_c1_and_c16": (T.get("same_outcome_at_c1_and_c16") or {}).get("rate")}
    if "rail" in q:
        out["rail"] = q["rail"]; out["rail_agrees_with_own_verdict"] = T["rail_beside_verdict_of_the_same_call"]["agree"]
    return out


def pct(r):
    return "—" if not r or r.get("rate") is None else f"{100 * r['rate']:.1f}% ({r['k']}/{r['n']}) [{100 * r['wilson95'][0]:.1f}, {100 * r['wilson95'][1]:.1f}]"


def num(x, f="{:.1f}"):
    return "—" if x is None else f.format(x)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("--arms", default="J6N,J6N-fp8,J6N-tpl,J6G"); a = ap.parse_args()
    arms = [x for x in a.arms.split(",") if x]
    summaries = {"J6 (the study: upstream vLLM)": json.load(open(os.path.join(P93_RESULTS, "J6", "summary.json"), encoding="utf-8"))}
    for arm in arms:
        S = direct_summary(arm) if arm in DIRECT else rail_summary()
        if S:
            summaries[arm] = S
    rows = []
    for name, S in summaries.items():
        for track, group in (("input", "aegis2"), ("input", "xstest"), ("input", "vol1"), ("output", "aegis2")):
            rows.append(line(name, S, track, group))
    table = {"what": "one line per arm, track and data set; every line is built from that arm's summary.json only", "arms": list(summaries), "rows": rows,
             "sources": {name: {"file": ("../p93_judges/J6/summary.json" if name.startswith("J6 (") else f"{name}/summary.json")} for name in summaries}}
    json.dump(table, open(os.path.join(RESULTS, "table.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    md = ["| Arm | Track · data | Items | Detection (Wilson 95%) | False alarm (Wilson 95%) | F1 | No verdict | c=1 p50 ms | c=16 verdicts/s | c=16 p99 ms | Tokens p50 | Stability |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r["usable"]:
            md.append(f"| {r['arm']} | {r['track']} | — | not usable: {r['why_not']} | | | | | | | | |"); continue
        nv = r["no_verdict"]; nov = nv["unreadable"] + nv["truncated"] + nv["error"]
        md.append(f"| {r['arm']} | {r['track']} · {r['group']} | {r['items']} | {pct(r['detection'])} | {pct(r['false_alarm'])} | {num(r['f1_unsafe'], '{:.3f}')} | {nov} | {num(r['c1_latency_ms_p50'])} | {num(r['c16_verdicts_per_s'])} | "
                  f"{num(r['c16_latency_ms_p99'])} | {num(r['completion_tokens_p50'], '{:.0f}')} | {num(None if r['stability'] is None else 100 * r['stability'], '{:.1f}%')} |")
    open(os.path.join(RESULTS, "table.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
