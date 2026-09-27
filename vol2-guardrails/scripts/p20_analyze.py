#!/usr/bin/env python3
"""P20 · analysis. Rules frozen in prediction_p20.json.

Series (from requests.jsonl):  SN = S-N nim · SO = S-O ollama · CN = C nim · CO = C ollama
Preconditions (any failure -> every conclusion field is null):
  P1  no request errors and every request answered HTTP 200
  P2  isolation held at every request, checked from the snapshot taken just before it:
        S-N  Ollama's /api/ps lists no model
        S-O  `docker ps` lists no container
        C    Ollama's /api/ps lists llama3.1:8b and `docker ps` lists the NIM container
  P3  warm-up: the first request of each series in execution order is dropped -> 49 valid points per series
  P4  every one of the 50 questions has one row in each of SN, SO, CN, CO
Conclusions (on questions valid in both series being compared):
  coresidence_effect   CN vs SN and CO vs SO: ratio of means C / alone, 95% bootstrap CI over questions,
                       and the median of per-question ratios; for ttft_ms, total_latency_ms, tps, tps_usage
  throughput_ratio     NIM / Ollama tps, alone (SN / SO) and co-resident (CN / CO), same statistics
  per_series           n, avg, p50, p95 of every metric (avg and p50 both reported)
  output_length        completion tokens and finish_reason per series (output length is part of the boundary)
  ollama_placement     share of the Ollama model held in GPU memory (size_vram / size) before each S-O and C request
usage: p20_analyze.py <run_dir> | --self-test
"""
import json, os, random, statistics as st, sys

SERIES = {"SN": ("S-N", "nim"), "SO": ("S-O", "ollama"), "CN": ("C", "nim"), "CO": ("C", "ollama")}
METRICS = ("ttft_ms", "total_latency_ms", "tps", "tps_usage")
BOOT, SEED = 2000, 20260917


def tps_usage(r):
    ct, t = r.get("completion_tokens"), r.get("total_latency_ms")
    return round(ct / (t / 1000), 2) if isinstance(ct, (int, float)) and t else None


def named(ps):
    return [m for m in (ps or []) if m.get("name")]


def isolated(r):
    arm = r["arm"]
    if arm == "S-N":
        return not named(r.get("ollama_ps_before"))
    if arm == "S-O":
        return not r.get("docker_ps_before")
    return (any((m.get("name") or "").startswith("llama3.1:8b") for m in named(r.get("ollama_ps_before")))
            and bool(r.get("docker_ps_before")))


def split(rows):
    out = {}
    for k, (arm, eng) in SERIES.items():
        s = [r for r in rows if r.get("arm") == arm and r.get("engine") == eng]
        s.sort(key=lambda r: (r["at"], r["pos"]))
        out[k] = s
    return out


def pct(v, p):
    v = sorted(v)
    if not v:
        return None
    i = (len(v) - 1) * p
    lo = int(i); hi = min(lo + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (i - lo), 2)


def desc(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "avg": round(st.mean(vals), 2), "p50": pct(vals, .5), "p95": pct(vals, .95)}


def value(r, m):
    return tps_usage(r) if m == "tps_usage" else r.get(m)


def paired(a, b, m, seed):
    """ratio of means a/b over questions present in both, bootstrap CI over questions, median per-question ratio."""
    A = {r["question_id"]: value(r, m) for r in a}
    B = {r["question_id"]: value(r, m) for r in b}
    qs = sorted(q for q in A if q in B and isinstance(A[q], (int, float)) and isinstance(B[q], (int, float)) and B[q])
    if not qs:
        return {"n": 0}
    ra = lambda sel: sum(A[q] for q in sel) / sum(B[q] for q in sel)
    rng = random.Random(seed)
    boots = sorted(ra([qs[rng.randrange(len(qs))] for _ in qs]) for _ in range(BOOT))
    return {"n": len(qs), "ratio_of_means": round(ra(qs), 4),
            "ci95": [round(boots[int(.025 * BOOT)], 4), round(boots[int(.975 * BOOT) - 1], 4)],
            "median_per_question_ratio": round(st.median(A[q] / B[q] for q in qs), 4)}


def analyze(rows, n_questions=50):
    ser = split(rows)
    pre = {}
    errs = [r for r in rows if r.get("error") or r.get("http_status") != 200]
    pre["P1_no_errors"] = {"errors": len(errs), "pass": not errs}
    bad = [(r["arm"], r["engine"], r["question_id"]) for r in rows if not isolated(r)]
    pre["P2_isolation_every_request"] = {"violations": len(bad), "first": bad[:5], "pass": not bad}
    valid = {k: s[1:] for k, s in ser.items()}
    dropped = {k: (s[0]["question_id"] if s else None) for k, s in ser.items()}
    pre["P3_first_request_dropped"] = {"dropped": dropped, "valid": {k: len(v) for k, v in valid.items()},
                                       "pass": all(len(v) == n_questions - 1 for v in valid.values())}
    counts = {k: len({r["question_id"] for r in s}) for k, s in ser.items()}
    rowsn = {k: len(s) for k, s in ser.items()}
    pre["P4_complete"] = {"questions_per_series": counts, "rows_per_series": rowsn,
                          "pass": all(counts[k] == n_questions and rowsn[k] == n_questions for k in ser)}
    ok = all(p["pass"] for p in pre.values())
    res = {"preconditions": pre, "preconditions_pass": ok, "conclusions": None}
    if not ok:
        return res
    c = {"per_series": {k: {m: desc(value(r, m) for r in v) for m in METRICS} for k, v in valid.items()},
         "coresidence_effect": {
             "nim_C_over_alone": {m: paired(valid["CN"], valid["SN"], m, SEED) for m in METRICS},
             "ollama_C_over_alone": {m: paired(valid["CO"], valid["SO"], m, SEED + 1) for m in METRICS}},
         "throughput_ratio_nim_over_ollama": {
             "alone": {m: paired(valid["SN"], valid["SO"], m, SEED + 2) for m in ("tps", "tps_usage")},
             "co_resident": {m: paired(valid["CN"], valid["CO"], m, SEED + 3) for m in ("tps", "tps_usage")}},
         "output_length": {k: {"completion_tokens": desc(r.get("completion_tokens") for r in v),
                               "finish_reason": dict(sorted(__import__("collections").Counter(
                                   str(r.get("finish_reason")) for r in v).items()))} for k, v in valid.items()},
         "ollama_placement_gpu_share": {k: desc(
             [m["size_vram"] / m["size"] for r in valid[k] for m in named(r.get("ollama_ps_before"))
              if m.get("size")]) for k in ("SO", "CO")},
         "reading": "ratios are C / alone and NIM / Ollama as ratio of means over the questions valid in both series; the "
                    "CI resamples questions. They describe this machine on this day and are not a replication of the "
                    "Vol.1 figures, whose stack differs."}
    res["conclusions"] = c
    return res


def self_test():
    def row(arm, eng, q, pos, at, ttft=50.0, tot=4000.0, tps=80.0, ct=450, ps=None, dk=None, err=None):
        r = {"arm": arm, "engine": eng, "question_id": q, "pos": pos, "at": at, "ttft_ms": ttft,
             "total_latency_ms": tot, "tps": tps, "completion_tokens": ct, "http_status": 200, "finish_reason": "stop",
             "ollama_ps_before": ps if ps is not None else [], "docker_ps_before": dk if dk is not None else []}
        if err:
            r["error"] = err
        return r
    loaded = [{"name": "llama3.1:8b", "size": 100, "size_vram": 40}]
    def build(n=4, **mut):
        rows = []
        for i in range(n):
            q = f"q{i}"; t = f"2026-01-01T00:{i:02d}"
            rows.append(row("S-O", "ollama", q, i, t + ":00", ttft=30, tot=3000, tps=150, ps=loaded))
            rows.append(row("S-N", "nim", q, i, t + ":10", dk=["nim-p20"]))
            rows.append(row("C", "nim", q, i, t + ":20", ttft=200, tot=4400, tps=70, ps=loaded, dk=["nim-p20"]))
            rows.append(row("C", "ollama", q, i, t + ":30", ttft=900, tot=30000, tps=12, ps=loaded, dk=["nim-p20"]))
        for f in mut.values():
            f(rows)
        return rows
    cases = []
    def safe(fn):
        try:
            return fn()
        except Exception as e:
            print("EXC", type(e).__name__, e)
            return False
    r = analyze(build(), 4)
    cases.append(("clean synthetic run passes", r["preconditions_pass"]))
    cases.append(("C/alone nim ttft = 4.0", safe(lambda: r["conclusions"]["coresidence_effect"]["nim_C_over_alone"]["ttft_ms"]["ratio_of_means"] == 4.0)))
    cases.append(("NIM/Ollama tps alone = 80/150", safe(lambda: abs(r["conclusions"]["throughput_ratio_nim_over_ollama"]["alone"]["tps"]["ratio_of_means"] - 80 / 150) < 1e-3)))
    cases.append(("tps_usage = 450 tokens / 4.0 s = 112.5", safe(lambda: r["conclusions"]["per_series"]["SN"]["tps_usage"]["avg"] == 112.5)))
    cases.append(("3 valid per series after dropping the first", r["preconditions"]["P3_first_request_dropped"]["valid"] == {"SN": 3, "SO": 3, "CN": 3, "CO": 3}))
    def leak_sn(rows):
        for x in rows:
            if x["arm"] == "S-N" and x["question_id"] == "q2":
                x["ollama_ps_before"] = loaded
    cases.append(("Ollama loaded during S-N -> P2 fails", not analyze(build(m=leak_sn), 4)["preconditions"]["P2_isolation_every_request"]["pass"]))
    def leak_so(rows):
        for x in rows:
            if x["arm"] == "S-O":
                x["docker_ps_before"] = ["nim-p20"]
    cases.append(("NIM up during S-O -> P2 fails", not analyze(build(m=leak_so), 4)["preconditions"]["P2_isolation_every_request"]["pass"]))
    def unloaded_c(rows):
        for x in rows:
            if x["arm"] == "C" and x["question_id"] == "q1":
                x["ollama_ps_before"] = []
    cases.append(("Ollama not loaded during C -> P2 fails", not analyze(build(m=unloaded_c), 4)["preconditions"]["P2_isolation_every_request"]["pass"]))
    def nim_down_c(rows):
        for x in rows:
            if x["arm"] == "C" and x["question_id"] == "q3":
                x["docker_ps_before"] = []
    cases.append(("NIM not up during C -> P2 fails", not analyze(build(m=nim_down_c), 4)["preconditions"]["P2_isolation_every_request"]["pass"]))
    def error(rows):
        rows[5]["error"] = "timeout"
    cases.append(("an error -> P1 fails, conclusions null", analyze(build(m=error), 4)["conclusions"] is None))
    def missing(rows):
        rows.pop()
    cases.append(("a missing row -> P4 fails", not analyze(build(m=missing), 4)["preconditions"]["P4_complete"]["pass"]))
    def dup(rows):
        rows.append(dict(rows[1]))
    cases.append(("a duplicate row -> P4 fails", not analyze(build(m=dup), 4)["preconditions"]["P4_complete"]["pass"]))
    def first_slow(rows):
        rows[1]["ttft_ms"] = 99999.0
    r2 = analyze(build(m=first_slow), 4)
    cases.append(("the dropped first request never reaches a ratio", safe(lambda: r2["conclusions"]["coresidence_effect"]["nim_C_over_alone"]["ttft_ms"]["ratio_of_means"] == 4.0)))
    bad = [n for n, ok in cases if not ok]
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if not bad else 1


def main():
    if sys.argv[1] == "--self-test":
        return self_test()
    d = sys.argv[1]
    rows = [json.loads(l) for l in open(os.path.join(d, "requests.jsonl"), encoding="utf-8") if l.strip()]
    for r in rows:
        r["tps_usage"] = tps_usage(r)
    res = analyze(rows)
    res["rows"] = len(rows)
    json.dump(res, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"preconditions_pass": res["preconditions_pass"], "preconditions": res["preconditions"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
