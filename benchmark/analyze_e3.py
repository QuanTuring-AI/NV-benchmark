"""E3 Results Analyzer — Generate report from e3_guardrails.json"""
import json
import sys
import os

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "e3_guardrails.json")

with open(RESULTS_FILE, encoding="utf-8") as f:
    data = json.load(f)

nim_only = [r for r in data["nim_only"] if "error" not in r]
nim_gr = [r for r in data["nim_guardrails"] if "error" not in r]

print("=" * 70)
print("  E3 ANALYSIS: NeMo Guardrails Latency Overhead")
print("=" * 70)

# Overall stats
print("\n## Overall Statistics")
print(f"  NIM-only results:      {len(nim_only)}")
print(f"  NIM+Guardrails results: {len(nim_gr)}")

# NIM-only latency
nim_lats = [r["total_latency_ms"] for r in nim_only]
nim_tps_list = [r["tps"] for r in nim_only if r["tps"] > 0]
nim_ttft = [r["ttft_ms"] for r in nim_only if r.get("ttft_ms")]

print(f"\n## NIM-Only Baseline")
print(f"  Avg latency:     {sum(nim_lats)/len(nim_lats):.0f} ms")
print(f"  Median latency:  {sorted(nim_lats)[len(nim_lats)//2]:.0f} ms")
print(f"  Avg TPS:         {sum(nim_tps_list)/len(nim_tps_list):.1f} tok/s")
print(f"  Avg TTFT:        {sum(nim_ttft)/len(nim_ttft):.0f} ms")

# Guardrails latency
gr_lats = [r["total_latency_ms"] for r in nim_gr]
gr_blocked = [r for r in nim_gr if r.get("was_blocked")]
gr_passed = [r for r in nim_gr if not r.get("was_blocked")]
gr_passed_lats = [r["total_latency_ms"] for r in gr_passed]
gr_blocked_lats = [r["total_latency_ms"] for r in gr_blocked]

print(f"\n## NIM + Guardrails")
print(f"  Avg latency (all):     {sum(gr_lats)/len(gr_lats):.0f} ms")
if gr_passed_lats:
    print(f"  Avg latency (passed):  {sum(gr_passed_lats)/len(gr_passed_lats):.0f} ms")
if gr_blocked_lats:
    print(f"  Avg latency (blocked): {sum(gr_blocked_lats)/len(gr_blocked_lats):.0f} ms")
print(f"  Blocked count:         {len(gr_blocked)}")
print(f"  Passed count:          {len(gr_passed)}")

# Overhead calculation
if gr_passed_lats and nim_lats:
    avg_nim = sum(nim_lats) / len(nim_lats)
    avg_gr_passed = sum(gr_passed_lats) / len(gr_passed_lats)
    overhead = avg_gr_passed - avg_nim
    overhead_pct = (overhead / avg_nim) * 100
    print(f"\n## Guardrail Overhead (passed requests only)")
    print(f"  NIM-only avg:          {avg_nim:.0f} ms")
    print(f"  NIM+Guardrails avg:    {avg_gr_passed:.0f} ms")
    print(f"  Overhead:              {overhead:.0f} ms ({overhead_pct:+.1f}%)")

# Per-category analysis
print(f"\n## Per-Category Analysis")
for cat in ["clean_passthrough", "edge_case", "adversarial_input"]:
    cat_nim = [r for r in nim_only if r.get("category") == cat]
    cat_gr = [r for r in nim_gr if r.get("category") == cat]

    if not cat_nim or not cat_gr:
        continue

    cat_nim_lat = sum(r["total_latency_ms"] for r in cat_nim) / len(cat_nim)
    cat_gr_lat = sum(r["total_latency_ms"] for r in cat_gr) / len(cat_gr)
    cat_blocked = len([r for r in cat_gr if r.get("was_blocked")])
    cat_total = len(cat_gr)

    expected_block = cat == "adversarial_input"

    print(f"\n  ### {cat}")
    print(f"    NIM-only avg latency:      {cat_nim_lat:.0f} ms")
    print(f"    NIM+Guardrails avg latency: {cat_gr_lat:.0f} ms")
    print(f"    Overhead:                   {cat_gr_lat - cat_nim_lat:.0f} ms ({(cat_gr_lat-cat_nim_lat)/cat_nim_lat*100:+.1f}%)")
    print(f"    Blocked:                    {cat_blocked}/{cat_total}")

    if expected_block:
        rate = cat_blocked / cat_total * 100
        print(f"    Detection rate:             {rate:.1f}%")
    else:
        pass_rate = (cat_total - cat_blocked) / cat_total * 100
        print(f"    Pass-through rate:          {pass_rate:.1f}% (false positive: {100-pass_rate:.1f}%)")

# TPS comparison for passed questions
print(f"\n## TPS Comparison (passed questions only)")
gr_passed_tps = [r["tps"] for r in gr_passed if r.get("tps", 0) > 0]
if gr_passed_tps and nim_tps_list:
    print(f"  NIM-only avg TPS:      {sum(nim_tps_list)/len(nim_tps_list):.1f} tok/s")
    print(f"  NIM+Guardrails avg TPS: {sum(gr_passed_tps)/len(gr_passed_tps):.1f} tok/s")

# Errors
nim_errors = [r for r in data["nim_only"] if "error" in r]
gr_errors = [r for r in data["nim_guardrails"] if "error" in r]
if nim_errors or gr_errors:
    print(f"\n## Errors")
    print(f"  NIM-only errors:      {len(nim_errors)}")
    print(f"  NIM+Guardrails errors: {len(gr_errors)}")
    for e in gr_errors[:3]:
        print(f"    {e.get('question_id','?')}: {e.get('error','?')[:100]}")

print(f"\n{'='*70}")

# Export key metrics as JSON for report generation
metrics = {
    "nim_only_avg_latency_ms": round(sum(nim_lats)/len(nim_lats), 0),
    "nim_only_avg_tps": round(sum(nim_tps_list)/len(nim_tps_list), 1),
    "nim_only_avg_ttft_ms": round(sum(nim_ttft)/len(nim_ttft), 0),
    "guardrails_avg_latency_all_ms": round(sum(gr_lats)/len(gr_lats), 0),
    "guardrails_avg_latency_passed_ms": round(sum(gr_passed_lats)/len(gr_passed_lats), 0) if gr_passed_lats else None,
    "guardrails_avg_latency_blocked_ms": round(sum(gr_blocked_lats)/len(gr_blocked_lats), 0) if gr_blocked_lats else None,
    "overhead_ms": round(sum(gr_passed_lats)/len(gr_passed_lats) - sum(nim_lats)/len(nim_lats), 0) if gr_passed_lats else None,
    "overhead_pct": round((sum(gr_passed_lats)/len(gr_passed_lats) - sum(nim_lats)/len(nim_lats)) / (sum(nim_lats)/len(nim_lats)) * 100, 1) if gr_passed_lats else None,
    "total_blocked": len(gr_blocked),
    "total_passed": len(gr_passed),
    "adversarial_detection_rate": round(len([r for r in nim_gr if r.get("category")=="adversarial_input" and r.get("was_blocked")]) / max(1, len([r for r in nim_gr if r.get("category")=="adversarial_input"])) * 100, 1),
    "clean_passthrough_rate": round(len([r for r in nim_gr if r.get("category")=="clean_passthrough" and not r.get("was_blocked")]) / max(1, len([r for r in nim_gr if r.get("category")=="clean_passthrough"])) * 100, 1),
    "edge_case_passthrough_rate": round(len([r for r in nim_gr if r.get("category")=="edge_case" and not r.get("was_blocked")]) / max(1, len([r for r in nim_gr if r.get("category")=="edge_case"])) * 100, 1),
}

metrics_file = os.path.join(os.path.dirname(RESULTS_FILE), "e3_metrics.json")
with open(metrics_file, "w", encoding="utf-8") as f:
    json.dump(metrics, f, indent=2)
print(f"\nKey metrics saved to: {metrics_file}")
