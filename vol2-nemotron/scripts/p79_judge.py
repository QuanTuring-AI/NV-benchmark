#!/usr/bin/env python3
"""Vol.2 · P79 · classify each measured cell and each container as normal / abnormal / grey against the P55 references.

References (vol2-nemotron/results/p55_concurrency_a2_256/levels.jsonl, container "main"):
  R c=1  TTFT p50 156 ms    line 15, 2026-09-23T18:41:31 (156.2 ms; that row is the discarded 120 s warm-up level; the
                            measured R c=1 row, line 16, 18:44:15, reads 157.7 ms. The ticket's value is used as written.)
  C c=128 ITL p50 30.7 ms   line 9,  2026-09-23T18:06:14
  C c=1  ITL p50 3.2 ms     line 2,  2026-09-23T17:55:56 (3.15 ms)
Rules (ticket section 2): normal = within 2x the reference (2x allows for day-to-day drift); abnormal = R c=1 TTFT p50
>= 1,000 ms or C c=128 ITL p50 >= 120 ms (about a third of this morning's values, so this morning's state falls inside);
anything between is grey. C c=1 has no abnormal line in the ticket: it is normal within 2x, otherwise grey.
A container is normal when both R c=1 and C c=128 are normal, abnormal when either is abnormal, otherwise grey.
usage: p79_judge.py self_test | p79_judge.py <levels.jsonl>
"""
import json, sys

REF = {"R1_ttft_p50_ms": 156.0, "C128_itl_p50_ms": 30.7, "C1_itl_p50_ms": 3.2}
ABNORMAL = {"R1_ttft_p50_ms": 1000.0, "C128_itl_p50_ms": 120.0}
NORMAL_FACTOR = 2.0


def cell(key, value, ref=REF, abnormal=ABNORMAL, factor=NORMAL_FACTOR):
    if value is None:
        return "missing"
    if value <= factor * ref[key]:
        return "normal"
    if key in abnormal and value >= abnormal[key]:
        return "abnormal"
    return "grey"


def container(r1, c128):
    if "abnormal" in (r1, c128):
        return "abnormal"
    if r1 == c128 == "normal":
        return "normal"
    return "grey"


def value_of(rec):
    s = rec.get("summary") or {}
    pick = lambda k: (s.get(k) or {}).get("p50")  # noqa: E731
    key = {("R", 1): ("R1_ttft_p50_ms", "time_to_first_token"), ("C", 128): ("C128_itl_p50_ms", "inter_token_latency"),
           ("C", 1): ("C1_itl_p50_ms", "inter_token_latency")}.get((rec.get("profile"), rec.get("concurrency")))
    return (key[0], pick(key[1])) if key else (None, None)


def judge_file(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    by_container = {}
    for r in rows:
        if r.get("warmup") or "summary" not in r and "rc" not in r:
            continue
        k, v = value_of(r)
        if k is None:
            continue
        verdict = cell(k, v)
        by_container.setdefault((r.get("phase"), r.get("container_seq"), r.get("setting")), {})[k] = {"value": v, "verdict": verdict}
    out = []
    for (phase, seq, setting), cells in sorted(by_container.items(), key=lambda x: (str(x[0][0]), x[0][1] or 0)):
        v = container(cells.get("R1_ttft_p50_ms", {}).get("verdict", "missing"), cells.get("C128_itl_p50_ms", {}).get("verdict", "missing"))
        out.append({"phase": phase, "container_seq": seq, "setting": setting, "cells": cells, "container_verdict": v})
    return out


def self_test():
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want; ok &= good
        print(f"  {'PASS' if good else 'FAIL'} {name}: {got} (want {want})")
    # positive control: this morning's s256_R c=1 (p78_clean_rerun levels.jsonl line 13) must be abnormal
    check("positive control, s256_R c=1 TTFT p50 3356.9 ms", cell("R1_ttft_p50_ms", 3356.8525), "abnormal")
    check("this morning s256_C c=128 ITL p50 195.6 ms", cell("C128_itl_p50_ms", 195.6), "abnormal")
    check("P55 R c=1 157.7 ms", cell("R1_ttft_p50_ms", 157.7), "normal")
    check("P55 C c=128 30.7 ms", cell("C128_itl_p50_ms", 30.7), "normal")
    check("edge 2x (312.0 ms)", cell("R1_ttft_p50_ms", 312.0), "normal")
    check("grey 500 ms", cell("R1_ttft_p50_ms", 500.0), "grey")
    check("grey C c=128 90 ms", cell("C128_itl_p50_ms", 90.0), "grey")
    check("C c=1 has no abnormal line: 50 ms", cell("C1_itl_p50_ms", 50.0), "grey")
    check("container abnormal if either", container("normal", "abnormal"), "abnormal")
    check("container normal needs both", container("normal", "grey"), "grey")
    check("missing cell", cell("R1_ttft_p50_ms", None), "missing")
    # mutation tests: a broken rule must make the positive control fail
    mut1 = cell("R1_ttft_p50_ms", 3356.8525, abnormal={**ABNORMAL, "R1_ttft_p50_ms": 5000.0})
    check("mutation: abnormal line raised to 5,000 ms -> positive control no longer abnormal", mut1 != "abnormal", True)
    mut2 = cell("R1_ttft_p50_ms", 3356.8525, factor=50.0)
    check("mutation: normal factor 50x -> positive control no longer abnormal", mut2 != "abnormal", True)
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "self_test":
        raise SystemExit(self_test())
    print(json.dumps(judge_file(sys.argv[1]), ensure_ascii=False, indent=1))
