#!/usr/bin/env python3
"""Vol.1-A revisit (p54_engine.py single) · analysis. Rules frozen in prediction_p54_engine.json.

The rules are p53_answer_analyze.py's (and through it p50_speed_analyze.py's), imported and run unchanged, with arm N in
the place of A1 and arm V in the place of A2:
  P1  no request errors, every request HTTP 200, usage present on every request
  P2  every row's served_model is the model its arm's container served at READY, and exactly one container was up
  P3  each arm has exactly one row per question of the sample (50 each); blocks alternate N, V, N, V
  arm-health gate before any ratio: generation rate = completion_tokens / (total - TTFT), median per arm, x bytes read
  per token (16,060,522,496, both arms: the same files) -> share of 1,792 GB/s; an arm under 10% -> validity false and
  no ratio.
Added here:
  P4  the one container up at each request is the block's own (its name carries the arm and block)
  P5  every row carries the six labels (model, precision, engine, max_model_len, max_num_seqs, max_tokens), none empty
  alignment (reported, not a gate): per block, the engine's own cache_config_info at READY (gpu_memory_utilization,
  num_gpu_blocks, block_size, cache dtype, max_model_len) and the CUDA-graph sizes captured (startup log), and whether
  each is identical across the two arms.
Ratios are V over N (ratio of means over questions, 95% bootstrap CI over questions, median per-question ratio): data,
not a sentence.
usage: p54_single_analyze.py <run_dir> [--out FILE] | --self-test
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p50_speed_analyze as speed  # noqa: E402
import p53_answer_analyze as answer  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BYTES_PER_TOKEN = 16_060_522_496
LABELS = ("model", "precision", "engine", "max_model_len", "max_num_seqs", "max_tokens")
CC_KEYS = ("gpu_memory_utilization", "num_gpu_blocks", "block_size", "kv_cache_dtype", "max_model_len")
REMAP = {"N": "A1", "V": "A2"}


def rename(o):
    """A1 -> N, A2 -> V in every key and string of the imported analysis (the imported rules name their arms A1/A2)."""
    if isinstance(o, dict):
        return {rename(k): rename(v) for k, v in o.items()}
    if isinstance(o, list):
        return [rename(v) for v in o]
    if isinstance(o, str):
        return o.replace("A2_over_A1", "V_over_N").replace("A1", "N").replace("A2", "V") if o in ("A1", "A2", "A2_over_A1") else o
    return o


def analyse(rows, events, n_questions=50):
    starts = [e for e in events if e.get("kind") == "block_start"]
    served = {}
    for e in starts:
        served.setdefault(e["arm"], set()).add(e.get("served_model"))
    speed.MODEL_OF = {REMAP[a]: (sorted(v)[0] if len(v) == 1 else None) for a, v in served.items()}
    mapped = [dict(r, arm=REMAP.get(r.get("arm"), r.get("arm"))) for r in rows]
    bpt = {"A1": BYTES_PER_TOKEN, "A2": BYTES_PER_TOKEN}
    try:
        a = answer.analyse(mapped, bpt, n_questions)
    except TypeError:
        # p53_answer_analyze.analyse cannot run past a failed health gate (it writes into the ratio block, which the gate
        # set to None). The gate's own result is then taken from p50_speed_analyze, which it wraps; no ratio either way.
        a = speed.analyse(mapped, bpt, n_questions)
        a["answer_section_omitted"] = "health gate failed; the imported answer analyser stops there (disclosed defect)"
    bad4 = [(r.get("arm"), r.get("question_id")) for r in rows if (r.get("docker_ps_before") or []) != [f"p54-single-{str(r.get('arm')).lower()}-b{r.get('block')}"]]
    bad5 = [(r.get("arm"), r.get("question_id")) for r in rows if any(r.get(k) in (None, "") for k in LABELS)]
    a["preconditions"]["P4_container_is_the_blocks_own"] = {"violations": len(bad4), "first": bad4[:5], "pass": not bad4}
    a["preconditions"]["P5_labels_present"] = {"violations": len(bad5), "first": bad5[:5], "pass": not bad5}
    a["preconditions_pass"] = all(v["pass"] for v in a["preconditions"].values())
    if not a["preconditions_pass"]:
        a["conclusions"] = None
    cc = {f"{e['arm']}{e['block']}": {k: (e.get("cache_config") or {}).get(k) for k in CC_KEYS} for e in starts}
    by_arm = {}
    for e in starts:
        by_arm.setdefault(e["arm"], []).append(tuple((e.get("cache_config") or {}).get(k) for k in CC_KEYS))
    same = len({t for v in by_arm.values() for t in v}) == 1 if by_arm else None
    diff = sorted({k for i, k in enumerate(CC_KEYS) if len({t[i] for v in by_arm.values() for t in v}) > 1}) if by_arm else None
    cg = {f"{e['arm']}{e['block']}": e.get("captured_graph_sizes") for e in starts}
    a["alignment_at_ready"] = {"per_block": cc, "identical_across_arms_and_blocks": same, "fields_that_differ": diff,
                               "captured_graph_sizes_per_block": cg,
                               "captured_graph_sizes_identical": len({json.dumps(v, sort_keys=True) for v in cg.values()}) == 1 if cg else None}
    a["labels"] = {arm: sorted({json.dumps({k: r.get(k) for k in LABELS}, sort_keys=True) for r in rows if r.get("arm") == arm}) for arm in ("N", "V")}
    out = rename(a)
    if out.get("conclusions"):
        out["conclusions"]["reading"] = ("one model, one set of weight files, one precision, one card; two ways of running the same "
                                         "vLLM build. Ratios are V over N, ratio of means over questions with a CI over questions.")
    return out


def self_test():
    def row(arm, q, b, total=5050.0, ct=400, **kw):
        r = {"arm": arm, "question_id": q, "block": b, "ttft_ms": 50.0, "total_latency_ms": total, "completion_tokens": ct, "http_status": 200,
             "usage_present": True, "finish_reason": "stop", "served_model": "meta/llama-3.1-8b-instruct", "docker_ps_before": [f"p54-single-{arm.lower()}-b{b}"],
             "model": "Llama 3.1 8B Instruct", "precision": "bf16", "engine": "x", "max_model_len": 8192, "max_num_seqs": 256, "max_tokens": 4096,
             "reasoning_channel": "none", "answer_chars": 100, "time_to_first_answer_ms": None}
        r.update(kw); return r

    def rows_ok():
        out = []
        for i in range(50):
            b = 0 if i < 25 else 2
            out.append(row("N", f"q{i:02d}", b, total=5050.0))            # 400 / 5.0 s = 80 tok/s
            out.append(row("V", f"q{i:02d}", b + 1, total=4050.0))        # 400 / 4.0 s = 100 tok/s
        return out
    cc = {"gpu_memory_utilization": "0.92", "num_gpu_blocks": "6083", "block_size": "16", "kv_cache_dtype": "auto", "max_model_len": "8192"}
    ev = [{"kind": "block_start", "arm": a, "block": b, "served_model": "meta/llama-3.1-8b-instruct", "cache_config": dict(cc)} for b, a in enumerate("NVNV")]
    cases = []
    x = analyse(rows_ok(), ev); c = x["conclusions"]
    cases.append(("clean run passes", x["preconditions_pass"] is True))
    cases.append(("health N = 80 x 16.06 GB / 1792 = 0.717", abs(c["arm_health"]["N"]["share_of_peak"] - 0.717) < 0.001))
    cases.append(("ratio V over N generation = 1.25", c["V_over_N"]["generation_rate"]["ratio_of_means"] == 1.25))
    cases.append(("keys renamed", "V_over_N" in c and "N" in c["per_arm"] and "A1" not in json.dumps(c["per_arm"])))
    cases.append(("alignment identical", x["alignment_at_ready"]["identical_across_arms_and_blocks"] is True))
    r = rows_ok(); r[3]["docker_ps_before"] = ["p54-single-n-b0"]           # V row with N's container up
    cases.append(("P4 catches wrong container", analyse(r, ev)["conclusions"] is None))
    r = rows_ok(); r[5]["max_num_seqs"] = None
    cases.append(("P5 catches a missing label", analyse(r, ev)["conclusions"] is None))
    r = rows_ok(); r[7]["served_model"] = "/opt/nim/.cache/whatever"
    cases.append(("P2 catches a wrong served model", analyse(r, ev)["conclusions"] is None))
    r = [dict(x_, total_latency_ms=(4050.0 if x_["arm"] == "N" else 50_050.0)) for x_ in rows_ok()]   # V at 400/50 s = 8 tok/s = 7.2%
    y = analyse(r, ev)["conclusions"]
    cases.append(("health gate: V at 7% -> no ratio", y["validity"] is False and y["V_over_N"] is None))
    ev2 = [dict(e, cache_config=dict(cc, num_gpu_blocks="5000")) if e["arm"] == "V" else e for e in ev]
    z = analyse(rows_ok(), ev2)
    cases.append(("alignment difference named, not a gate", z["alignment_at_ready"]["fields_that_differ"] == ["num_gpu_blocks"] and z["conclusions"] is not None))
    bad = [n for n, ok in cases if not ok]
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if not bad else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    rows = [json.loads(l) for l in open(os.path.join(d, "requests.jsonl"), encoding="utf-8")]
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf-8")]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(d, "analysis.json")
    a = analyse(rows, events, n_questions=len({r["question_id"] for r in rows}) // 1 if "--any-n" in sys.argv else 50)
    json.dump(a, open(out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"preconditions_pass": a["preconditions_pass"], "health": (a.get("conclusions") or {}).get("arm_health"),
                      "alignment": a["alignment_at_ready"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
