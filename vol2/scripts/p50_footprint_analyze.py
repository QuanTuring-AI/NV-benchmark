#!/usr/bin/env python3
"""Vol.2 footprint decomposition · analysis. Rules frozen in prediction_p50_footprint.json.

Per arm, from configs.jsonl:
  default_level        memory in use at READY with no budget override, and the engine's effective gpu_memory_utilization
                       and KV tokens  -> the "level after the engine fills its default budget", not a footprint
  min_viable           the smallest NIM_KVCACHE_PERCENT whose start reached READY and whose probe passed; its memory at
                       READY, KV tokens, and budget = pct x card total
  bound_reached        True only if a smaller budget was tried and failed (a sweep with no failure gives no lower bound)
  weights_log          the engine's own "model loading took" line, when present (recorded, not derived)
  delta_ready_mib      memory at READY minus memory before launch, for default and for min_viable
Preconditions (any failure -> conclusions null): P1 every arm has a default row; P2 every row that reached READY has a
gpu_ready reading and a probe with three rows; P3 the probe questions are the three pre-registered ids in every row.
usage: p50_footprint_analyze.py <run_dir> | --self-test
"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PROBE_IDS = ["q001", "q004", "q011"]
ARMS = ["A1", "A2", "A2FP8"]


def analyse(rows):
    by = {a: [r for r in rows if r.get("arm") == a] for a in ARMS}
    p1 = {a: any(r.get("label") == "default" for r in v) for a, v in by.items() if v}
    bad2 = [(r.get("arm"), r.get("label")) for r in rows if r.get("start", {}).get("ready")
            and (not r.get("gpu_ready") or len(r.get("probe") or []) != 3)]
    bad3 = [(r.get("arm"), r.get("label")) for r in rows if r.get("probe")
            and [p.get("question_id") for p in r["probe"]] != PROBE_IDS]
    pre = {"P1_default_row_per_arm": {"arms": p1, "pass": bool(p1) and all(p1.values())},
           "P2_ready_rows_complete": {"violations": bad2, "pass": not bad2},
           "P3_probe_ids": {"violations": bad3, "pass": not bad3}}
    out = {"preconditions": pre, "preconditions_pass": all(v["pass"] for v in pre.values()), "rows": len(rows),
           "conclusions": None}
    if not out["preconditions_pass"]:
        return out
    con = {}
    for a, v in by.items():
        if not v:
            continue
        total = v[0]["gpu_before"]["total_mib"]
        d = next(r for r in v if r["label"] == "default")
        passing = [r for r in v if r.get("kvcache_percent") is not None and r.get("viable")]
        failing = [r for r in v if r.get("kvcache_percent") is not None and not r.get("viable")]
        mv = min(passing, key=lambda r: r["kvcache_percent"]) if passing else None
        bound = mv is not None and any(r["kvcache_percent"] < mv["kvcache_percent"] for r in failing)

        def level(r):
            if not r or not r.get("start", {}).get("ready"):
                return None
            cc = r.get("cache_config") or {}
            return {"ready_used_mib": r["gpu_ready"]["used_mib"], "before_used_mib": r["gpu_before"]["used_mib"],
                    "delta_ready_mib": r["gpu_ready"]["used_mib"] - r["gpu_before"]["used_mib"],
                    "gpu_memory_utilization_effective": cc.get("gpu_memory_utilization"),
                    "kv_tokens": cc.get("kv_tokens"), "num_gpu_blocks": cc.get("num_gpu_blocks"),
                    "kvcache_percent": r.get("kvcache_percent"),
                    "budget_mib": round(r["kvcache_percent"] * total) if r.get("kvcache_percent") else None,
                    "weights_log": (r["start"].get("log_lines") or {}).get("model_loading"),
                    "clamp_log": (r["start"].get("log_lines") or {}).get("clamp"),
                    "gmu_log": (r["start"].get("log_lines") or {}).get("gmu"),
                    "kv_tokens_source": cc.get("kv_tokens_source"),
                    "kv_log": (r["start"].get("log_lines") or {}).get("kv_cache_size")}
        con[a] = {"image": v[0]["image"], "profile": v[0]["profile"], "precision": v[0]["precision"],
                  "card_total_mib": total, "starts": len(v),
                  "default_started": bool(d.get("start", {}).get("ready")), "default_viable": d.get("viable"),
                  "default_level": level(d),
                  "default_failure": None if d.get("start", {}).get("ready") else d.get("start", {}).get("reason"),
                  "min_viable": level(mv), "bound_reached": bound,
                  "first_failure": (min(failing, key=lambda r: -r["kvcache_percent"])["kvcache_percent"] if failing else None),
                  "first_failure_reason": (min(failing, key=lambda r: -r["kvcache_percent"]).get("start", {}).get("reason")
                                           or "probe failed" if failing else None),
                  "sweep": [{"pct": r["kvcache_percent"], "ready": r["start"]["ready"], "viable": r["viable"],
                             "ready_used_mib": (r.get("gpu_ready") or {}).get("used_mib"),
                             "kv_tokens": (r.get("cache_config") or {}).get("kv_tokens")}
                            for r in sorted(v, key=lambda r: -(r["kvcache_percent"] or 9))]}
    out["conclusions"] = {"per_arm": con,
                          "reading": "budget_mib is the engine's allowed share of the card; delta_ready_mib is what nvidia-smi "
                                     "saw the container add. The minimum requirement of a model at this context length lies "
                                     "between the smallest passing budget and the largest failing one; it is not a single number."}
    return out


def mk(arm, label, pct, ready=True, viable=True, before=2900, used=None, kv=40000, total=32607, reason=None, fr="stop"):
    r = {"arm": arm, "image": "img", "profile": "p", "precision": "x", "label": label, "kvcache_percent": pct,
         "gpu_before": {"used_mib": before, "total_mib": total}, "start": {"ready": ready, "log_lines": {}, "reason": reason},
         "viable": viable and ready}
    if ready:
        r["gpu_ready"] = {"used_mib": used if used is not None else before + 20000}
        r["cache_config"] = {"gpu_memory_utilization": str(pct or 0.92), "kv_tokens": kv, "num_gpu_blocks": kv // 16}
        r["probe"] = [{"question_id": q, "http_status": 200, "finish_reason": fr} for q in PROBE_IDS]
    return r


def self_test():
    base = [mk("A1", "default", None, used=30500), mk("A1", "pct0.85", 0.85), mk("A1", "pct0.80", 0.80),
            mk("A1", "pct0.75", 0.75, ready=False, reason="engine refused"), mk("A1", "pct0.775", 0.775, ready=False, reason="engine refused"),
            mk("A2", "default", None, used=31700), mk("A2", "pct0.85", 0.85), mk("A2", "pct0.80", 0.80, ready=False, reason="engine refused")]
    cases = []
    a = analyse(base); c = a["conclusions"]["per_arm"]
    cases.append(("clean run passes", a["preconditions_pass"]))
    cases.append(("A1 min viable is 0.80", c["A1"]["min_viable"]["kvcache_percent"] == 0.80))
    cases.append(("A1 bound reached (0.775 failed below 0.80)", c["A1"]["bound_reached"] is True))
    cases.append(("A1 budget = 0.80 x 32607", c["A1"]["min_viable"]["budget_mib"] == round(0.80 * 32607)))
    cases.append(("A1 default delta = 30500-2900", c["A1"]["default_level"]["delta_ready_mib"] == 27600))
    cases.append(("A2 first failure at 0.80", c["A2"]["first_failure"] == 0.80))
    rows = [r for r in base if not (r["arm"] == "A1" and r["kvcache_percent"] in (0.75, 0.775))]
    cases.append(("no failure below -> bound not reached", analyse(rows)["conclusions"]["per_arm"]["A1"]["bound_reached"] is False))
    rows = [r for r in base if not (r["arm"] == "A1" and r["label"] == "default")]
    cases.append(("missing default row -> null", analyse(rows)["conclusions"] is None))
    rows = [dict(r) for r in base]; rows[1] = mk("A1", "pct0.85", 0.85); rows[1]["probe"] = rows[1]["probe"][:2]
    cases.append(("probe with two rows -> null", analyse(rows)["conclusions"] is None))
    rows = [dict(r) for r in base]; rows[1] = mk("A1", "pct0.85", 0.85); rows[1]["probe"][0]["question_id"] = "q999"
    cases.append(("wrong probe id -> null", analyse(rows)["conclusions"] is None))
    rows = [dict(r) for r in base]; rows[2] = mk("A1", "pct0.80", 0.80, fr="length")
    rows[2]["viable"] = False
    cases.append(("probe truncated at 0.80 -> min viable 0.85", analyse(rows)["conclusions"]["per_arm"]["A1"]["min_viable"]["kvcache_percent"] == 0.85))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{sum(ok for _, ok in cases)}/{len(cases)} pass")
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    rows = [json.loads(l) for l in open(os.path.join(d, "configs.jsonl"), encoding="utf-8")]
    a = analyse(rows)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(json.dumps(a["preconditions"], ensure_ascii=False))
    if a["conclusions"]:
        for arm, c in a["conclusions"]["per_arm"].items():
            print(arm, "default:", (c["default_level"] or {}).get("ready_used_mib"), "min_viable:", (c["min_viable"] or {}).get("kvcache_percent"),
                  "budget", (c["min_viable"] or {}).get("budget_mib"), "bound", c["bound_reached"], "fail@", c["first_failure"])
    return 0 if a["preconditions_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
