#!/usr/bin/env python3
"""Vol.2 answer-completion run · analysis. Rules frozen in prediction_p53_answer.json.

Preconditions and the arm-health gate are those of p50_speed_analyze (imported): P1 no errors, HTTP 200, usage on
every row · P2 served model is the arm's and one container up · P3 50 rows per arm, blocks alternating.
Added here, per arm: time to complete a question (total latency), completion tokens at max_tokens 4096, truncation
rate (finish_reason length), the reasoning channel the image exposed, reasoning vs answer characters when the
channel is known, time to first answer token when reasoning came first, and empty-answer count. A2/A1 ratio of
total latency (paired over questions) beside the generation-rate ratio, so the two are read together.
usage: p53_answer_analyze.py <run_dir> --bytes A1=<int>,A2=<int> [--n N] | --self-test
"""
import json, os, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p50_speed_analyze as base  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def analyse(rows, bytes_per_token, n_questions=50):
    a = base.analyse(rows, bytes_per_token, n_questions)
    if not a["conclusions"]:
        return a
    by = {"A1": [r for r in rows if r.get("arm") == "A1"], "A2": [r for r in rows if r.get("arm") == "A2"]}
    ans = {}
    for arm, v in by.items():
        ch = sorted({r.get("reasoning_channel") for r in v})
        split = [r for r in v if r.get("reasoning_channel") in ("reasoning_content field", "<think> markers")]
        ans[arm] = {"max_tokens": sorted({r.get("max_tokens") for r in v}),
                    "total_latency_ms": base.desc(r.get("total_latency_ms") for r in v),
                    "completion_tokens": base.desc(r.get("completion_tokens") for r in v),
                    "truncated_at_max_tokens": sum(1 for r in v if r.get("finish_reason") == "length"),
                    "finish_reason": {k: sum(1 for r in v if r.get("finish_reason") == k) for k in sorted({r.get("finish_reason") for r in v})},
                    "reasoning_channel": ch,
                    "rows_with_split": len(split),
                    "reasoning_chars": base.desc(r.get("reasoning_chars") for r in split) if split else None,
                    "answer_chars": base.desc(r.get("answer_chars") for r in split) if split else None,
                    "time_to_first_answer_ms": base.desc(r.get("time_to_first_answer_ms") for r in v),
                    "answer_empty": sum(1 for r in v if r.get("answer_empty"))}
    a["conclusions"]["answer"] = ans
    a["conclusions"]["A2_over_A1"]["total_latency_ms"] = base.paired_ratio(by["A1"], by["A2"], lambda r: r.get("total_latency_ms")) if a["conclusions"]["A2_over_A1"] else None
    a["conclusions"]["A2_over_A1"]["completion_tokens"] = base.paired_ratio(by["A1"], by["A2"], lambda r: r.get("completion_tokens")) if a["conclusions"]["A2_over_A1"] else None
    a["conclusions"]["reading"] += (" The total-latency ratio, not the generation-rate ratio, is the answer to 'how much faster is a "
                                    "question answered'; the two differ by the ratio of tokens each model spends per question.")
    return a


def self_test():
    rows = base.base_rows()
    for r in rows:
        r.update({"max_tokens": 4096, "reasoning_channel": "none", "reasoning_chars": 0, "answer_chars": 100,
                  "answer_empty": False, "time_to_first_answer_ms": None, "finish_reason": "stop"})
    rows[1].update({"reasoning_channel": "reasoning_content field", "reasoning_chars": 300, "answer_chars": 50, "time_to_first_answer_ms": 900.0})
    a = analyse(rows, base.BYTES); c = a["conclusions"]
    cases = [("base preconditions pass", a["preconditions_pass"]),
             ("A2 latency ratio = 2050/6050", abs(c["A2_over_A1"]["total_latency_ms"]["ratio_of_means"] - 2050 / 6050) < 1e-3),
             ("truncation counted", c["answer"]["A1"]["truncated_at_max_tokens"] == 0),
             ("split row counted", c["answer"]["A2"]["rows_with_split"] == 1 and c["answer"]["A2"]["reasoning_chars"]["p50"] == 300.0),
             ("channels listed", "reasoning_content field" in c["answer"]["A2"]["reasoning_channel"])]
    rows2 = [dict(r) for r in rows]; rows2[0]["finish_reason"] = "length"
    cases.append(("length row counted as truncated", analyse(rows2, base.BYTES)["conclusions"]["answer"]["A1"]["truncated_at_max_tokens"] == 1))
    rows3 = [dict(r) for r in rows]; rows3[0]["usage_present"] = False
    cases.append(("base gate still applies (usage missing -> null)", analyse(rows3, base.BYTES)["conclusions"] is None))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{sum(ok for _, ok in cases)}/{len(cases)} pass")
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    bpt = {k: int(v) for k, v in (x.split("=") for x in sys.argv[sys.argv.index("--bytes") + 1].split(","))} if "--bytes" in sys.argv else None
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 50
    rows = [json.loads(l) for l in open(os.path.join(d, "requests.jsonl"), encoding="utf-8")]
    a = analyse(rows, bpt, n)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(json.dumps(a["preconditions"], ensure_ascii=False))
    if a["conclusions"]:
        print("answer", json.dumps(a["conclusions"]["answer"], ensure_ascii=False)[:1500]); print("A2/A1", json.dumps(a["conclusions"]["A2_over_A1"]))
    return 0 if a["preconditions_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
