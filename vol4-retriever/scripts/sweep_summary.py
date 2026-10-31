#!/usr/bin/env python3
"""Vol.4 · three numbers the text states about the concurrency sweep, summed from the two tables they come from, so that
the claim rows can read numbers instead of sentences:
  - the levels run on both nights with the same request bodies and without errors, and the largest difference of the
    second night's rate from the first's on them (results/concurrency_sweep_second_night/two_nights.json);
  - the largest difference between the two runs of the load tool against the server that answers at once
    (results/tool_ceiling/table.json).
A level counts for the two nights when both nights have it, the request bodies are the same, neither night has an error,
and its NIM was swept on both nights: the 300m embedder was swept on the second night only (on the first, its sweep
stopped after the calibration level), so its one level with a first-night record is not counted.
The difference between the tool's two runs is |second - first| divided by the lower of the two, per level.
usage: sweep_summary.py [--two-nights FILE] [--tool-table FILE] [--out FILE]
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__)); V4 = os.path.dirname(HERE)


def two_nights_summary(d):
    levels, diffs, per_arm = [], [], {}
    for arm, ad in d["arms"].items():
        all_levels = [ld for sd in ad["shapes"].values() for ld in sd.values() if isinstance(ld, dict)]
        both_nights = bool(all_levels) and all(ld.get("first_night") and ld.get("second_night") for ld in all_levels)
        per_arm[arm] = {"swept_on_both_nights": both_nights, "levels": 0}
        if not both_nights:
            continue
        for shape, sd in ad["shapes"].items():
            for lvl, ld in sd.items():
                f, s = ld["first_night"], ld["second_night"]
                if ld.get("same_request_bodies") and f["errors"] == 0 and s["errors"] == 0:
                    levels.append(f"{arm}/{shape}/{lvl}"); diffs.append(abs(ld["difference_percent"]["requests_per_s"]))
                    per_arm[arm]["levels"] += 1
    return {"levels_on_both_nights_same_bodies_no_errors": len(levels), "largest_rate_difference_percent": max(diffs) if diffs else None,
            "levels": levels, "per_arm": per_arm}


def tool_summary(t):
    rows = []
    for shape, sd in t["shapes"].items():
        for lvl, ld in sd["levels"].items():
            a, b = ld["tool"]["first"]["requests_per_s"], ld["tool"]["second"]["requests_per_s"]
            rows.append({"shape": shape, "level": lvl, "difference_of_the_two_runs_percent": round(abs(b - a) / min(a, b) * 100, 2)})
    worst = max(rows, key=lambda r: r["difference_of_the_two_runs_percent"])
    return {"levels": len(rows), "largest_difference_of_the_two_runs_percent": worst["difference_of_the_two_runs_percent"], "at": {"shape": worst["shape"], "level": worst["level"]},
            "levels_more_than_15_percent_apart": sum(1 for r in rows if r["difference_of_the_two_runs_percent"] > 15), "per_level": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--two-nights", default=os.path.join(V4, "results", "concurrency_sweep_second_night", "two_nights.json"))
    ap.add_argument("--tool-table", default=os.path.join(V4, "results", "tool_ceiling", "table.json"))
    ap.add_argument("--out", default=os.path.join(V4, "results", "sweep_summary", "summary.json"))
    a = ap.parse_args()
    out = {"what": "three numbers of the text about the concurrency sweep, summed from the two tables they come from",
           "sources": {"two_nights": "concurrency_sweep_second_night/two_nights.json", "tool_ceiling": "tool_ceiling/table.json"},
           "two_nights": two_nights_summary(json.load(open(a.two_nights, encoding="utf-8"))),
           "tool_ceiling": tool_summary(json.load(open(a.tool_table, encoding="utf-8"))),
           "program": "scripts/sweep_summary.py"}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(out["two_nights"]["levels_on_both_nights_same_bodies_no_errors"], out["two_nights"]["largest_rate_difference_percent"], out["tool_ceiling"]["largest_difference_of_the_two_runs_percent"])


if __name__ == "__main__":
    main()
