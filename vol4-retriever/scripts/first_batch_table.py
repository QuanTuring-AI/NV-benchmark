#!/usr/bin/env python3
"""Vol.4 · the tables of the first GPU session, built from its result files (nothing is typed in).
Every cell stands for one encoder on one data set; a cell that has no file is shown as "not run".
usage: first_batch_table.py [--results DIR] > table.md
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument("--results", default=os.path.join(os.path.dirname(HERE), "results", "first_batch")); a = ap.parse_args()
R = a.results
DATA = ["beir-scifact", "miracl-hn-zh", "miracl-hn-ja"]
TARGET = {"miracl-hn-zh": 0.64244, "miracl-hn-ja": 0.74194}


def load(*parts):
    p = os.path.join(R, *parts)
    return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else None


events = [json.loads(l) for l in open(os.path.join(R, "events.jsonl"), encoding="utf-8")] if os.path.isfile(os.path.join(R, "events.jsonl")) else []
arms = sorted(d for d in os.listdir(R) if os.path.isdir(os.path.join(R, d)) and (d.startswith("nim_") or d.startswith("reference_")) and "rerank" not in d)
rerank = sorted(d for d in os.listdir(R) if os.path.isdir(os.path.join(R, d)) and "rerank" in d)
sys.stdout.reconfigure(encoding="utf-8")
print("## Embedding cells: nDCG@10 · Recall@100 · passages per second (median of three timed passes)\n")
print("| Encoder | " + " | ".join(DATA) + " |"); print("|---|" + "---|" * len(DATA))
for arm in arms:
    cells = []
    for d in DATA:
        s, t = load(arm, d, "score.json"), load(arm, d, "throughput.json")
        if not s and not t:
            cells.append("not run"); continue
        q = f"{s['metrics']['ndcg_cut_10']:.5f} · {s['metrics']['recall_100']:.5f}" if s else "no score"
        sp = f"{t['passages_per_s_median']:.1f} ({t['passages_per_s_min']:.1f}–{t['passages_per_s_max']:.1f})" if t else "no timed passes"
        cells.append(f"{q} · {sp}")
    print(f"| `{arm}` | " + " | ".join(cells) + " |")
print("\nPublished values for the open weights of `nemotron-3-embed-1b` (MTEB results, nDCG@10): " + ", ".join(f"{d} {v}" for d, v in TARGET.items()) + ".\n")
print("## Containers\n")
print("| Tag | Image | Seconds to ready | Card memory at ready, MiB (before the start) | Outcome |"); print("|---|---|---|---|---|")
for e in events:
    if e.get("kind") in ("nim_ready", "nim_not_ready", "nim_start_failed"):
        print(f"| `{e['tag']}` | `{e.get('image', '')}` | {e.get('seconds_to_verdict', '')} | {(e.get('card') or {}).get('used_mib', '')} ({(e.get('card_before') or {}).get('used_mib', '')}) | {e['kind'].replace('nim_', '')}{': ' + str(e.get('reason')) if e.get('reason') else ''} |")
if rerank:
    print("\n## Reranking the first 100 results of `nim_nemotron-3-embed-1b_auto`: nDCG@10 before → after · pairs per second\n")
    print("| Reranker | " + " | ".join(DATA) + " |"); print("|---|" + "---|" * len(DATA))
    for arm in rerank:
        cells = []
        for d in DATA:
            before, after, t = load("nim_nemotron-3-embed-1b_auto", d, "score.json"), load(arm, d, "score_after.json"), load(arm, d, "throughput.json")
            if not after and not t:
                cells.append("not run"); continue
            q = f"{before['metrics']['ndcg_cut_10']:.5f} → {after['metrics']['ndcg_cut_10']:.5f}" if before and after else "no score"
            sp = f"{t['pairs_per_s_median']:.1f} ({t['pairs_per_s_min']:.1f}–{t['pairs_per_s_max']:.1f})" if t else "no timed passes"
            cells.append(f"{q} · {sp}")
        print(f"| `{arm}` | " + " | ".join(cells) + " |")
m = os.path.join(R, "method_host_vs_container")
if os.path.isdir(m):
    print("\n## Method cell: the same requests to the same NIM from two places\n")
    print("| Client | Connection | Passages per request | Passages per second | Request ms p10 / p50 / p90 / p99 | Requests more than 10 ms above p10 |"); print("|---|---|---|---|---|---|")
    for f in sorted(os.listdir(m)):
        r = json.load(open(os.path.join(m, f), encoding="utf-8")); q = r["request_ms"]
        print(f"| {r['where']} | {r['connection']} | {r['batch']} | {r['passages_per_s_median']} | {q['p10']} / {q['p50']} / {q['p90']} / {q['p99']} | {q['more_than_10_ms_above_p10']} of {q['count']} |")
gates = [e for e in events if e.get("kind") == "gate"]
if gates:
    print(f"\n## Gates\n\n{len(gates)} gates, {sum(bool(e['pass']) for e in gates)} passed on utilization and power; {sum(bool(e.get('desktop_flag')) for e in gates)} flagged for desktop memory; "
          f"launcher processes seen at {sum(1 for e in gates if e.get('launcher_processes'))} gates; other containers at {sum(1 for e in gates if e.get('other_containers_running'))} gates. "
          f"Desktop memory at the first gate: {next((e['desktop_mib'] for e in gates if e.get('desktop_mib') is not None), None)} MiB; range over the gates without a container of the session: "
          f"{min(e['desktop_mib'] for e in gates if e.get('desktop_mib') is not None)}–{max(e['desktop_mib'] for e in gates if e.get('desktop_mib') is not None)} MiB.")
