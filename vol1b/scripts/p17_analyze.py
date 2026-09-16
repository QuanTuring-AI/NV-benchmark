"""P17 · analysis of one profile sweep (rules frozen in the profile's prediction file before the run).
usage: p17_analyze.py <profile_dir> --calibration <calibration_verdict.json> [--fresh <dir> ...]  |  --self-test

Per level (preconditions first; if any fails the level's SLO fields are null):
  L1 AIPerf exited 0 and wrote its summary · L2 zero request errors · L3 instrument check passed
SLO (MLPerf Inference v5.1, judged on p99, AIPerf definitions: ITL excludes the first token):
  server:      TTFT p99 <= 2000 ms and ITL p99 <= 100 ms
  interactive: TTFT p99 <=  500 ms and ITL p99 <=  30 ms
N_x = the largest measured concurrency such that it and every lower measured level pass SLO x (0 if level 1 fails).
Also reported: the largest passing level when a lower level fails (non-monotonic).
Throughput saturation point: the first level whose total output token throughput rises < 10% over the previous level.
Queue / memory indicators from the server's /metrics during the level (warm-up included in that window):
  batch cap reached = running max == max_num_seqs · memory ceiling = preemptions > 0, or waiting max > 0 while running max < level
  and running max < max_num_seqs."""
import json, os, sys

SLO = {"server": (2000.0, 100.0), "interactive": (500.0, 30.0)}
MAX_NUM_SEQS = 256


def level_record(art):
    s = json.load(open(os.path.join(art, "profile_export_aiperf.json"), encoding="utf-8"))
    g = lambda k, st: (s.get(k) or {}).get(st)
    errors = (g("error_request_count", "avg") or 0) + sum((e.get("count") or 0) for e in (s.get("error_summary") or []))
    rec = {"completed": g("request_count", "avg"), "errors": errors,
           "ttft_ms": {st: g("time_to_first_token", st) for st in ("avg", "p50", "p90", "p99")},
           "itl_ms": {st: g("inter_token_latency", st) for st in ("avg", "p50", "p90", "p99")},
           "e2e_ms": {st: g("request_latency", st) for st in ("avg", "p50", "p90", "p99")},
           "total_output_tps": g("output_token_throughput", "avg"), "tps_per_user": {st: g("output_token_throughput_per_user", st) for st in ("avg", "p50")},
           "rps": g("request_throughput", "avg"), "isl": {st: g("input_sequence_length", st) for st in ("avg", "p50", "p99")},
           "osl": {st: g("output_sequence_length", st) for st in ("avg", "p50", "p99")}, "duration_s": g("benchmark_duration", "avg")}
    sm_path = os.path.join(art, "server_metrics_export.json")
    if os.path.exists(sm_path):
        m = json.load(open(sm_path, encoding="utf-8")).get("metrics", {})
        def stat(name, key, reason=None):
            for ser in (m.get(name) or {}).get("series", []):
                if reason is None or (ser.get("labels") or {}).get("reason") == reason:
                    return (ser.get("stats") or {}).get(key)
        rec["server"] = {"running_max": stat("vllm:num_requests_running", "max"), "running_p50": stat("vllm:num_requests_running", "p50"),
                         "waiting_max": stat("vllm:num_requests_waiting", "max"), "waiting_p50": stat("vllm:num_requests_waiting", "p50"),
                         "kv_usage_max": stat("vllm:kv_cache_usage_perc", "max"), "preemptions": stat("vllm:num_preemptions", "total"),
                         "prefix_cache_hits": stat("vllm:prefix_cache_hits", "total"), "prefix_cache_queries": stat("vllm:prefix_cache_queries", "total")}
    return rec


def judge(levels, calibration_pass):
    out = []
    for lv in levels:
        r = dict(lv)
        pre = {"L1_summary": r.get("summary_ok", False), "L2_zero_errors": r.get("errors") == 0, "L3_instrument_check": bool(calibration_pass)}
        r["preconditions"] = pre
        ok = all(pre.values())
        for name, (t, i) in SLO.items():
            if not ok or r["ttft_ms"]["p99"] is None or r["itl_ms"]["p99"] is None:
                r[f"slo_{name}"] = None
            else:
                r[f"slo_{name}"] = r["ttft_ms"]["p99"] <= t and r["itl_ms"]["p99"] <= i
        sv = r.get("server") or {}
        rm, wm = sv.get("running_max"), sv.get("waiting_max")
        r["batch_cap_reached"] = None if rm is None else rm >= MAX_NUM_SEQS
        r["memory_ceiling"] = None if rm is None else bool((sv.get("preemptions") or 0) > 0 or ((wm or 0) > 0 and rm < r["concurrency"] and rm < MAX_NUM_SEQS))
        out.append(r)
    table = {}
    for name in SLO:
        contiguous, largest, broken = 0, 0, False
        for r in out:
            v = r[f"slo_{name}"]
            if v is None:
                broken = True
                continue
            if v:
                largest = r["concurrency"]
                if not broken:
                    contiguous = r["concurrency"]
            else:
                broken = True
        null_levels = [r["concurrency"] for r in out if r[f"slo_{name}"] is None]
        tps = next((r["total_output_tps"] for r in out if r["concurrency"] == contiguous), None)
        table[name] = {"N": contiguous, "total_output_tps_at_N": tps, "largest_passing_level": largest,
                       "non_monotonic": largest != contiguous, "levels_with_null_verdict": null_levels}
    sat = None
    for prev, cur in zip(out, out[1:]):
        if prev["total_output_tps"] and cur["total_output_tps"] is not None and cur["total_output_tps"] < 1.10 * prev["total_output_tps"]:
            sat = {"level": cur["concurrency"], "total_output_tps": cur["total_output_tps"], "previous_level_tps": prev["total_output_tps"]}
            break
    mem = next(({"level": r["concurrency"], "server": r.get("server")} for r in out if r["memory_ceiling"]), None)
    cap = next((r["concurrency"] for r in out if r["batch_cap_reached"]), None)
    return out, {"slo": table, "throughput_saturation": sat or "not reached within the measured levels",
                 "memory_ceiling_first_level": mem or "not observed", "batch_cap_first_level": cap or "not reached", "max_num_seqs": MAX_NUM_SEQS}


def load_dir(d):
    levels = []
    for line in open(os.path.join(d, "levels.jsonl"), encoding="utf-8"):
        meta = json.loads(line)
        art = os.path.join(d, f"c{meta['concurrency']:04d}")
        rec = {"concurrency": meta["concurrency"], "duration_s_set": meta["duration_s"], "rc": meta["rc"], "start": meta["start"], "end": meta["end"],
               "ctx_start": meta.get("ctx_start"), "ctx_end": meta.get("ctx_end"), "completed_ge_3N": meta.get("completed_ge_3N")}
        if meta["rc"] == 0 and os.path.exists(os.path.join(art, "profile_export_aiperf.json")):
            rec.update(level_record(art)); rec["summary_ok"] = True
        else:
            rec.update({"summary_ok": False, "errors": None, "ttft_ms": {"p99": None}, "itl_ms": {"p99": None}, "total_output_tps": None})
        levels.append(rec)
    seen = [r["concurrency"] for r in levels]
    if len(seen) != len(set(seen)):
        raise SystemExit(f"levels.jsonl in {d} lists a concurrency more than once: {seen} — not analysed")
    return levels


def self_test():
    mk = lambda n, ttft, itl, tps, err=0, ok=True, run=None, wait=0, pre=0: {"concurrency": n, "summary_ok": ok, "errors": err,
          "ttft_ms": {"p99": ttft}, "itl_ms": {"p99": itl}, "total_output_tps": tps,
          "server": {"running_max": run if run is not None else n, "waiting_max": wait, "preemptions": pre}}
    cases = []
    lv, t = judge([mk(1, 100, 10, 100), mk(4, 400, 25, 380), mk(16, 900, 40, 1200), mk(32, 2500, 60, 1250)], True)
    cases.append(("server N=16, interactive N=4", t["slo"]["server"]["N"] == 16 and t["slo"]["interactive"]["N"] == 4))
    cases.append(("saturation at 32 (<10% rise)", isinstance(t["throughput_saturation"], dict) and t["throughput_saturation"]["level"] == 32))
    lv, t = judge([mk(16, 100, 10, 100, run=16, wait=5)], True)
    cases.append(("waiting while running == level is not a memory ceiling", lv[0]["memory_ceiling"] is False))
    lv, t = judge([mk(1, 600, 10, 100), mk(4, 700, 12, 380)], True)
    cases.append(("interactive fails at c=1 -> N_i = 0", t["slo"]["interactive"]["N"] == 0 and t["slo"]["server"]["N"] == 4))
    lv, t = judge([mk(1, 100, 10, 100), mk(4, 100, 10, 380, err=1), mk(16, 100, 10, 1200)], True)
    cases.append(("errors -> null verdict, N stops before it", lv[1]["slo_server"] is None and t["slo"]["server"]["N"] == 1 and t["slo"]["server"]["largest_passing_level"] == 16))
    lv, t = judge([mk(1, 100, 10, 100)], False)
    cases.append(("instrument check failed -> all null", lv[0]["slo_server"] is None and t["slo"]["server"]["N"] == 0))
    lv, t = judge([mk(1, 100, 10, 100), mk(4, 2100, 10, 380), mk(16, 100, 10, 1200)], True)
    cases.append(("non-monotonic flagged", t["slo"]["server"]["non_monotonic"] and t["slo"]["server"]["N"] == 1))
    lv, t = judge([mk(16, 100, 10, 100), mk(32, 100, 10, 200, run=20, wait=12), mk(512, 100, 10, 300, run=256, wait=200)], True)
    cases.append(("memory ceiling at 32, batch cap at 512", t["memory_ceiling_first_level"]["level"] == 32 and t["batch_cap_first_level"] == 512))
    lv, t = judge([mk(1, 2000, 100, 100)], True)
    cases.append(("thresholds inclusive (<=)", t["slo"]["server"]["N"] == 1))
    bad = [c for c in cases if not c[1]]
    for c in cases:
        print(("PASS " if c[1] else "FAIL ") + c[0])
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1] == "--self-test":
        sys.exit(self_test())
    d = sys.argv[1]
    cal = json.load(open(sys.argv[sys.argv.index("--calibration") + 1], encoding="utf-8"))
    fresh = [sys.argv[i + 1] for i, x in enumerate(sys.argv) if x == "--fresh"]
    levels, table = judge(load_dir(d), cal.get("pass"))
    result = {"profile_dir": d, "calibration_pass": cal.get("pass"), "levels": levels, "table": table, "fresh_container_runs": {}}
    for f in fresh:
        lv, _ = judge(load_dir(f), cal.get("pass"))
        result["fresh_container_runs"][f] = lv
    json.dump(result, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(table, ensure_ascii=False, indent=1))
