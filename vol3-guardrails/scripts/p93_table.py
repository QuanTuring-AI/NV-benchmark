#!/usr/bin/env python3
"""P93 · the arms side by side. This program reads only the summary.json of each arm (aggregates written by
p93_analyze.py). It opens no per-item file, and it computes nothing across arms: every cell of the table is one arm's own
figure with its own interval, placed next to the others.

usage: p93_table.py      -> results/p93_judges/table.md and table.json
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p93_common import ARMS, RESULTS, sha256_file  # noqa: E402

ORDER = ["J0", "J1", "J2", "J3", "J4", "J5", "J6", "J4G", "J5G"]


def pct(r):
    if not r or r.get("rate") is None:
        return "-"
    lo, hi = r["wilson95"]
    return f"{100 * r['rate']:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}] ({r['k']}/{r['n']})"


def num(x, fmt="{:.0f}"):
    return "-" if x is None else fmt.format(x)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    S, read = {}, []
    for arm in ORDER:
        p = os.path.join(RESULTS, arm, "summary.json")
        if os.path.basename(p) != "summary.json":
            sys.exit("refused: only summary.json files are read here")
        if os.path.isfile(p):
            S[arm] = json.load(open(p, encoding="utf-8")); read.append({"file": f"{arm}/summary.json", "sha256": sha256_file(p)})
    lines = ["# P93 · each judge's own figures, side by side", "",
             "Every cell is one arm's figure with its own Wilson 95% interval. Nothing here is computed across arms.", ""]
    groups = [("input", "aegis2", "Aegis 2.0 prompts"), ("input", "xstest", "XSTest prompts"), ("input", "xstest_harmless_only", "XSTest, the 250 harmless prompts"),
              ("input", "aegis2_needs_caution_only", "Aegis 2.0 prompts whose only category is Needs Caution (labelled safe)"), ("input", "vol1", "Vol.1 questions (anchor)"), ("output", "aegis2", "Aegis 2.0 responses")]
    for track, g, title in groups:
        lines += [f"## {title} ({track} track)", "", "| Arm | Judge | Detection | False alarm | No verdict | F1 (unsafe) | Accuracy | Items |", "|---|---|---|---|---|---|---|---|"]
        for arm, s in S.items():
            T = s["tracks"].get(track, {})
            if not T.get("usable"):
                lines.append(f"| {arm} | {s['judge']} | null ({T.get('why_not')}) | | | | | |"); continue
            q = T["quality"].get(g)
            if not q:
                continue
            lines.append(f"| {arm} | {s['judge']} | {pct(q['detection'])} | {pct(q['false_alarm'])} | {100 * q['no_verdict']['share']:.1f}% | {num(q['f1_unsafe_over_items_with_verdict'], '{:.3f}')} | "
                         f"{num(q['accuracy_over_items_with_verdict'], '{:.3f}')} | {q['items']} |")
        lines.append("")
    lines += ["## Cost of a verdict", "", "| Arm | Track | c=1 p50 ms | c=1 p99 ms | c=16 verdicts/s | c=16 p99 ms | Output tokens p50 | p99 | Calls with reasoning | Same outcome on the rerun |", "|---|---|---|---|---|---|---|---|---|---|"]
    for arm, s in S.items():
        for track in ("input", "output"):
            T = s["tracks"].get(track, {})
            if not T.get("usable"):
                continue
            c1 = T.get("c1") or {}; qc = T["quality_cell"]
            lines.append(f"| {arm} | {track} | {num((c1.get('latency_ms') or {}).get('p50'))} | {num((c1.get('latency_ms') or {}).get('p99'))} | "
                         f"{num(qc.get('verdicts_per_s'), '{:.1f}') if qc.get('concurrency') == 16 else '-'} | {num(qc['latency_ms']['p99']) if qc.get('concurrency') == 16 else '-'} | "
                         f"{num(qc['completion_tokens']['p50'])} | {num(qc['completion_tokens']['p99'])} | {qc['calls_with_reasoning']}/{qc['calls']} | {pct(T.get('stability'))} |")
    lines.append("")
    open(os.path.join(RESULTS, "table.md"), "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    json.dump({"what": "the arms' summaries, as read; nothing is computed across arms", "files_read": read, "arms": S}, open(os.path.join(RESULTS, "table.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
