#!/usr/bin/env python3
"""Vol.1-A revisit (p54_engine.py conc) · analysis. Rules frozen in prediction_p54_engine.json.

The rules are p55_concurrency_a2_analyze.py's (which are p53_concurrency_v2_analyze.py's plus the per-level pools),
imported and run unchanged on both arms, with one function replaced: P3's "the container ran at the intended sequence
cap" reads arm V's engine arguments as well as arm N's NIM variables. For both arms the intended cap is vLLM's default
on this card (256, no override): P3 passes when neither the NIM variables nor V's argument list set --max-num-seqs
(or they set exactly the intended value) AND the engine's own running gauge never exceeds it at any level.
Added: a side-by-side table per profile and container (same levels, both arms) of the pre-registered SLO fields.
usage: p54_conc_analyze.py <run_dir> --seqs N [--out FILE] | --self-test
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p55_concurrency_a2_analyze as base  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def env_ok(env, seqs):
    pa = (env.get("NIM_PASSTHROUGH_ARGS") or "") + " " + (env.get("VLLM_ARGS") or "")
    if "--max-num-seqs" in pa or "NIM_MAX_NUM_SEQS" in env:
        return f"--max-num-seqs {seqs}" in pa or env.get("NIM_MAX_NUM_SEQS") == str(seqs)
    return seqs == base.IMAGE_DEFAULT_SEQS


base.env_ok = env_ok


def side_by_side(a):
    out = {}
    for k, s in a["sweeps"].items():
        arm, prof, cont = s["arm"], s["profile"], s["container"]
        slot = out.setdefault(f"{prof}|{cont}", {})
        slot[arm] = {"preconditions_pass": s["preconditions_pass"], "conclusions": s["conclusions"],
                     "levels": {t["concurrency"]: {"output_tps": t["output_tps"], "ttft_p99": t["ttft_ms"]["p99"], "itl_p99": t["itl_ms"]["p99"],
                                                   "binding": t["binding"]} for t in s["levels"]}}
    return out


def analyse(levels, events, seqs, run_dir=None, gauge_fn=None):
    a = base.analyse(levels, events, seqs, run_dir, gauge_fn)
    a["side_by_side"] = side_by_side(a)
    return a


def self_test():
    cases = []
    cases.append(("N default env -> ok", env_ok({"NIM_MAX_MODEL_LEN": "8192", "VLLM_USE_V2_MODEL_RUNNER": "0"}, 256)))
    cases.append(("V args without cap -> ok", env_ok({"VLLM_ARGS": "--served-model-name m --max-model-len 8192"}, 256)))
    cases.append(("V args with a different cap -> not ok", not env_ok({"VLLM_ARGS": "--max-num-seqs 128 --max-model-len 8192"}, 256)))
    cases.append(("V args with the same cap -> ok", env_ok({"VLLM_ARGS": "--max-num-seqs 256"}, 256)))
    cases.append(("NIM_MAX_NUM_SEQS 32 -> not ok", not env_ok({"NIM_MAX_NUM_SEQS": "32"}, 256)))
    cases.append(("no override but an intended cap other than the default -> not ok", not env_ok({"VLLM_ARGS": "--max-model-len 8192"}, 128)))

    def mk(arm, n, tps, t99=100.0, i99=10.0):
        return {"arm": arm, "profile": "C", "container": "main", "concurrency": n, "duration_s": 60, "rc": 0, "completed": 5 * n, "completed_ge_3N": True,
                "engine_dead": False, "summary": {"time_to_first_token": {"p50": 30.0, "p90": t99, "p99": t99}, "inter_token_latency": {"p50": 9.0, "p90": i99, "p99": i99},
                                                  "output_token_throughput": {"avg": tps}, "output_token_throughput_per_user": {"avg": 100.0},
                                                  "input_sequence_length": {"avg": 200}, "output_sequence_length": {"avg": 200}, "error_request_count": {"avg": 0}}}
    lv = [mk(a, n, 100.0 * n) for a in ("N", "V") for n in (1, 2, 4)]
    cal = {"ttft_ms_p50": 30.0, "itl_ms_p50": 9.0, "n_ok": 10, "prompt_tokens_p50": 200}
    ev = [{"kind": "container_start", "arm": "N", "profile": "C", "container": "main", "env": {"NIM_MAX_MODEL_LEN": "8192"}, "calibration": cal},
          {"kind": "container_start", "arm": "V", "profile": "C", "container": "main", "env": {"VLLM_ARGS": "--max-model-len 8192"}, "calibration": cal}]
    g = lambda arm, prof, cont, n: {"running_max": n, "running_p50": n, "waiting_max": 0, "waiting_max_by_reason": {}, "kv_usage_max": 0.1, "kv_usage_p50": 0.1, "preemptions": 0}
    x = analyse(lv, ev, 256, gauge_fn=g)
    cases.append(("both arms pass", x["all_preconditions_pass"] is True and set(x["side_by_side"]["C|main"]) == {"N", "V"}))
    ev2 = [dict(ev[0]), dict(ev[1], env={"VLLM_ARGS": "--max-num-seqs 64"})]
    y = analyse(lv, ev2, 256, gauge_fn=g)
    cases.append(("V with a cap override fails P3", y["sweeps"]["V|C|main"]["preconditions"]["P3_sequence_cap"]["pass"] is False and y["sweeps"]["N|C|main"]["preconditions_pass"] is True))
    g2 = lambda arm, prof, cont, n: dict(g(arm, prof, cont, n), running_max=300)
    z = analyse(lv, ev, 256, gauge_fn=g2)
    cases.append(("running gauge above the cap fails P3", z["all_preconditions_pass"] is False))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    seqs = int(sys.argv[sys.argv.index("--seqs") + 1])
    levels = [json.loads(l) for l in open(os.path.join(d, "levels.jsonl"), encoding="utf-8")]
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf-8")]
    a = analyse(levels, events, seqs, run_dir=d)
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(d, "analysis.json")
    json.dump(a, open(out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    for k, s in a["sweeps"].items():
        print(k, "pre", s["preconditions_pass"], json.dumps({x: (s["conclusions"] or {}).get(x) for x in ("max_concurrency_within_server_slo", "max_concurrency_within_interactive_slo", "throughput_max", "ceiling", "binding_at_top_level")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
