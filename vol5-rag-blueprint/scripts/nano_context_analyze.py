#!/usr/bin/env python3
"""Vol.5 preparation: the analysis of the context footprint sweeps, with the rules of Vol.2's footprint analysis
(vol2-nemotron/scripts/p50_footprint_analyze.py, imported and not modified; only the arm names are added).
Writes analysis.json into each sweep's folder and prints one table of both.
Written after the pre-registration of the session was frozen, as that file says.
usage: nano_context_analyze.py <results/preparation>
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "vol2-nemotron", "scripts"))
import p50_footprint_analyze as an  # noqa: E402

ARM = {8192: "A2S32C8K", 16384: "A2S32C16K"}
an.ARMS = list(ARM.values())
root = sys.argv[1]
sys.stdout.reconfigure(encoding="utf-8")
print("| Context | Starts | Default budget: card memory once ready, MiB (KV cache tokens) | Smallest budget that started and answered | Card memory at that budget, MiB (KV cache tokens) | First budget that failed |")
print("|---|---|---|---|---|---|")
for ctx, arm in ARM.items():
    d = os.path.join(root, f"nano_context_{ctx}")
    if not os.path.isfile(os.path.join(d, "configs.jsonl")):
        print(f"| {ctx:,} | not run | | | | |"); continue
    rows = [json.loads(l) for l in open(os.path.join(d, "configs.jsonl"), encoding="utf-8")]
    a = an.analyse(rows)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    if not a["conclusions"]:
        print(f"| {ctx:,} | {len(rows)} | preconditions not met: {json.dumps(a['preconditions'])[:200]} | | | |"); continue
    c = a["conclusions"]["per_arm"][arm]; dl, mv = c["default_level"] or {}, c["min_viable"] or {}
    print(f"| {ctx:,} | {len(rows)} | {dl.get('ready_used_mib')} ({dl.get('kv_tokens')}) | {mv.get('kvcache_percent')} of the card = {mv.get('budget_mib')} MiB{'' if c['bound_reached'] else ' (no smaller budget failed: not a lower bound)'} "
          f"| {mv.get('ready_used_mib')} ({mv.get('kv_tokens')}) | {c['first_failure']} |")
