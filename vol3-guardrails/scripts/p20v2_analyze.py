#!/usr/bin/env python3
"""P20 v2 · analysis. Rules frozen in prediction_p20v2.json.

Series:  SN = S-N nim · SOL = S-OL ollama (127.0.0.1) · SOH = S-OH ollama (localhost) · CN = C nim · CO = C ollama
Preconditions (any failure -> every conclusion field is null):
  P1  no request errors, every request HTTP 200
  P2  isolation at every request, from the snapshot taken just before it:
        S-N        Ollama /api/ps lists no model AND GPU memory in use >= the recovery floor recorded on the row
        S-OL/S-OH  `docker ps` lists nothing
        C          Ollama lists llama3.1:8b AND `docker ps` lists the NIM container
      and every request went to the address its arm specifies (S-N and C-nim localhost:8000, S-OL and C-ollama
      127.0.0.1:11434, S-OH localhost:11434)
  P3  the first request of each series in execution order is dropped -> 49 valid per series
  P4  every one of the 50 questions has exactly one row in each of the five series
Conclusions (questions valid in both series compared; ratio of means, 95% bootstrap CI over questions, median ratio):
  coresidence_effect   CN / SN and CO / SOL  (the Ollama comparison uses the same address on both sides)
  throughput_ratio     NIM / Ollama tps: SN / SOL (clean), SN / SOH (Vol.1's client path), CN / CO (co-resident)
  address_delay        SOH - SOL per question for ttft_ms and total_latency_ms (mean with bootstrap CI, median), SOH / SOL
                       for tps, and how often the two addresses returned the same text
  per_series · output_length · ollama_placement · s_n_recovery
usage: p20v2_analyze.py <run_dir> | --self-test
"""
import collections, json, os, random, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p20_analyze import desc, named, paired, tps_usage, value  # v1 helpers, unchanged

SERIES = {"SN": ("S-N", "nim"), "SOL": ("S-OL", "ollama"), "SOH": ("S-OH", "ollama"), "CN": ("C", "nim"), "CO": ("C", "ollama")}
BASE = {"SN": "http://localhost:8000", "SOL": "http://127.0.0.1:11434", "SOH": "http://localhost:11434",
        "CN": "http://localhost:8000", "CO": "http://127.0.0.1:11434"}
METRICS = ("ttft_ms", "total_latency_ms", "tps", "tps_usage")
BOOT, SEED = 2000, 20260917


def series_of(r):
    for k, (arm, eng) in SERIES.items():
        if r.get("arm") == arm and r.get("engine") == eng:
            return k
    return None


def isolated(r):
    k = series_of(r)
    if k is None or r.get("base") != BASE[k]:
        return False
    if k == "SN":
        floor = r.get("recovery_floor_mib")
        return (not named(r.get("ollama_ps_before")) and isinstance(floor, (int, float))
                and (r.get("gpu_before") or {}).get("used_mib", -1) >= floor)
    if k in ("SOL", "SOH"):
        return not r.get("docker_ps_before")
    return (any((m.get("name") or "").startswith("llama3.1:8b") for m in named(r.get("ollama_ps_before")))
            and bool(r.get("docker_ps_before")))


def diff(a, b, m, seed):
    A = {r["question_id"]: value(r, m) for r in a}
    B = {r["question_id"]: value(r, m) for r in b}
    qs = sorted(q for q in A if q in B and isinstance(A[q], (int, float)) and isinstance(B[q], (int, float)))
    if not qs:
        return {"n": 0}
    d = [A[q] - B[q] for q in qs]
    rng = random.Random(seed)
    boots = sorted(st.mean(d[rng.randrange(len(d))] for _ in d) for _ in range(BOOT))
    return {"n": len(qs), "mean": round(st.mean(d), 1), "ci95": [round(boots[int(.025 * BOOT)], 1), round(boots[int(.975 * BOOT) - 1], 1)],
            "median": round(st.median(d), 1), "min": round(min(d), 1), "max": round(max(d), 1)}


def order_split(soh, sol):
    """Ollama reuses the previous request's prompt cache, and the repeat of a prompt can return different text, so the
    second of the two address arms on a question is not identical to the first. The design alternates which address goes
    first; this reports the TTFT difference (localhost minus loopback) separately for each order."""
    L = {r["question_id"]: r for r in sol}
    out = {}
    for label, cond in (("localhost_first", lambda h, l: h["at"] < l["at"]), ("loopback_first", lambda h, l: h["at"] > l["at"])):
        d = [h["ttft_ms"] - L[h["question_id"]]["ttft_ms"] for h in soh
             if h["question_id"] in L and cond(h, L[h["question_id"]])
             and isinstance(h.get("ttft_ms"), (int, float)) and isinstance(L[h["question_id"]].get("ttft_ms"), (int, float))]
        out[label] = {"n": len(d), "median_ttft_diff_ms": round(st.median(d), 1) if d else None}
    return out


def analyze(rows, n_questions=50):
    ser = {k: sorted([r for r in rows if series_of(r) == k], key=lambda r: (r["at"], r["pos"])) for k in SERIES}
    pre = {}
    errs = [r for r in rows if r.get("error") or r.get("http_status") != 200]
    pre["P1_no_errors"] = {"errors": len(errs), "pass": not errs}
    bad = [(r.get("arm"), r.get("engine"), r.get("question_id")) for r in rows if not isolated(r)]
    pre["P2_isolation_and_address_every_request"] = {"violations": len(bad), "first": bad[:5], "pass": not bad}
    valid = {k: s[1:] for k, s in ser.items()}
    pre["P3_first_request_dropped"] = {"dropped": {k: (s[0]["question_id"] if s else None) for k, s in ser.items()},
                                       "valid": {k: len(v) for k, v in valid.items()},
                                       "pass": all(len(v) == n_questions - 1 for v in valid.values())}
    qn = {k: len({r["question_id"] for r in s}) for k, s in ser.items()}
    rn = {k: len(s) for k, s in ser.items()}
    pre["P4_complete"] = {"questions_per_series": qn, "rows_per_series": rn,
                          "pass": all(qn[k] == n_questions and rn[k] == n_questions for k in SERIES)}
    ok = all(p["pass"] for p in pre.values())
    res = {"preconditions": pre, "preconditions_pass": ok, "conclusions": None}
    if not ok:
        return res
    same = sum(1 for r in valid["SOH"] for x in valid["SOL"]
               if x["question_id"] == r["question_id"] and x.get("response_sha256") == r.get("response_sha256"))
    sn_used = [r["gpu_before"]["used_mib"] for r in valid["SN"]]
    res["conclusions"] = {
        "per_series": {k: {m: desc(value(r, m) for r in v) for m in METRICS} for k, v in valid.items()},
        "coresidence_effect": {
            "nim_C_over_alone": {m: paired(valid["CN"], valid["SN"], m, SEED) for m in METRICS},
            "ollama_C_over_alone_loopback": {m: paired(valid["CO"], valid["SOL"], m, SEED + 1) for m in METRICS}},
        "throughput_ratio_nim_over_ollama": {
            "alone_loopback": {m: paired(valid["SN"], valid["SOL"], m, SEED + 2) for m in ("tps", "tps_usage")},
            "alone_localhost_vol1_path": {m: paired(valid["SN"], valid["SOH"], m, SEED + 3) for m in ("tps", "tps_usage")},
            "co_resident": {m: paired(valid["CN"], valid["CO"], m, SEED + 4) for m in ("tps", "tps_usage")}},
        "address_delay_ollama_localhost_minus_loopback": {
            "ttft_ms": diff(valid["SOH"], valid["SOL"], "ttft_ms", SEED + 5),
            "total_latency_ms": diff(valid["SOH"], valid["SOL"], "total_latency_ms", SEED + 6),
            "tps_ratio_localhost_over_loopback": paired(valid["SOH"], valid["SOL"], "tps", SEED + 7),
            "same_text_both_addresses": f"{same}/{len(valid['SOH'])}",
            "by_order": order_split(valid["SOH"], valid["SOL"])},
        "output_length": {k: {"completion_tokens": desc(r.get("completion_tokens") for r in v),
                              "finish_reason": dict(sorted(collections.Counter(str(r.get("finish_reason")) for r in v).items()))}
                          for k, v in valid.items()},
        "ollama_placement_gpu_share": {k: desc([m["size_vram"] / m["size"] for r in valid[k]
                                                for m in named(r.get("ollama_ps_before")) if m.get("size")])
                                       for k in ("SOL", "SOH", "CO")},
        "s_n_recovery": {"gpu_used_before_mib": desc(sn_used),
                         "floor_mib": valid["SN"][0].get("recovery_floor_mib"),
                         "nim_alone_used_mib": valid["SN"][0].get("nim_alone_used_mib")},
        "reading": "ratios are ratio of means over the questions valid in both series; the CI resamples questions. They "
                   "describe this machine on this day and are not a replication of the Vol.1 figures, whose stack differs."}
    return res


def self_test():
    loaded = [{"name": "llama3.1:8b", "size": 100, "size_vram": 100}]
    def row(k, q, pos, at, ttft, tot, tps, ct=400, **kw):
        arm, eng = SERIES[k]
        r = {"arm": arm, "engine": eng, "base": BASE[k], "question_id": q, "pos": pos, "at": at, "ttft_ms": ttft,
             "total_latency_ms": tot, "tps": tps, "completion_tokens": ct, "http_status": 200, "finish_reason": "stop",
             "response_sha256": "h" + q, "ollama_ps_before": [], "docker_ps_before": [], "gpu_before": {"used_mib": 30000}}
        if k in ("CO", "CN"):
            r["ollama_ps_before"] = loaded; r["docker_ps_before"] = ["nim-p20v2"]
        if k in ("SN",):
            r["docker_ps_before"] = ["nim-p20v2"]; r["recovery_floor_mib"] = 29000; r["nim_alone_used_mib"] = 30000
        if k in ("SOL", "SOH"):
            r["ollama_ps_before"] = loaded
        r.update(kw)
        return r
    def build(n=4, *muts):
        rows = []
        for i in range(n):
            q = f"q{i}"; t = f"2026-01-01T00:{i:02d}"
            rows += [row("SOL", q, i, t + ":00", 60, 2000, 200), row("SOH", q, i, t + ":01", 2110, 4050, 100),
                     row("SN", q, i, t + ":10", 40, 5000, 90), row("CN", q, i, t + ":20", 600, 5500, 80),
                     row("CO", q, i, t + ":30", 700, 3000, 130)]
        for m in muts:
            m(rows)
        return rows
    def safe(f):
        try:
            return f()
        except Exception as e:
            print("EXC", type(e).__name__, e); return False
    cases = []
    r = analyze(build(), 4)
    c = r["conclusions"]
    cases.append(("clean synthetic run passes", r["preconditions_pass"]))
    cases.append(("address delay ttft mean = 2050", safe(lambda: c["address_delay_ollama_localhost_minus_loopback"]["ttft_ms"]["mean"] == 2050)))
    cases.append(("SN/SOL tps = 90/200", safe(lambda: abs(c["throughput_ratio_nim_over_ollama"]["alone_loopback"]["tps"]["ratio_of_means"] - 0.45) < 1e-3)))
    cases.append(("SN/SOH tps = 90/100", safe(lambda: abs(c["throughput_ratio_nim_over_ollama"]["alone_localhost_vol1_path"]["tps"]["ratio_of_means"] - 0.9) < 1e-3)))
    cases.append(("CO/SOL ttft = 700/60", safe(lambda: abs(c["coresidence_effect"]["ollama_C_over_alone_loopback"]["ttft_ms"]["ratio_of_means"] - 700 / 60) < 1e-3)))
    cases.append(("order split: 3 loopback-first, 0 localhost-first", safe(lambda: c["address_delay_ollama_localhost_minus_loopback"]["by_order"]["loopback_first"]["n"] == 3 and c["address_delay_ollama_localhost_minus_loopback"]["by_order"]["localhost_first"]["n"] == 0)))
    cases.append(("same text 3/3", safe(lambda: c["address_delay_ollama_localhost_minus_loopback"]["same_text_both_addresses"] == "3/3")))
    def m_low(rows):
        next(x for x in rows if x["arm"] == "S-N" and x["question_id"] == "q2")["gpu_before"] = {"used_mib": 25000}
    cases.append(("S-N below recovery floor -> P2 fails", not analyze(build(4, m_low), 4)["preconditions_pass"]))
    def m_nofloor(rows):
        next(x for x in rows if x["arm"] == "S-N" and x["question_id"] == "q1").pop("recovery_floor_mib")
    cases.append(("S-N without a recorded floor -> P2 fails", not analyze(build(4, m_nofloor), 4)["preconditions_pass"]))
    def m_addr(rows):
        next(x for x in rows if x["arm"] == "S-OH" and x["question_id"] == "q3")["base"] = "http://127.0.0.1:11434"
    cases.append(("S-OH sent to 127.0.0.1 -> P2 fails", not analyze(build(4, m_addr), 4)["preconditions_pass"]))
    def m_leak(rows):
        next(x for x in rows if x["arm"] == "S-N" and x["question_id"] == "q1")["ollama_ps_before"] = loaded
    cases.append(("Ollama loaded during S-N -> P2 fails", not analyze(build(4, m_leak), 4)["preconditions_pass"]))
    def m_nim_up(rows):
        next(x for x in rows if x["arm"] == "S-OL" and x["question_id"] == "q1")["docker_ps_before"] = ["nim"]
    cases.append(("NIM up during S-OL -> P2 fails", not analyze(build(4, m_nim_up), 4)["preconditions_pass"]))
    def m_c(rows):
        next(x for x in rows if x["arm"] == "C" and x["engine"] == "ollama" and x["question_id"] == "q2")["docker_ps_before"] = []
    cases.append(("NIM down during C -> P2 fails", not analyze(build(4, m_c), 4)["preconditions_pass"]))
    def m_err(rows):
        rows[3]["error"] = "x"
    cases.append(("an error -> conclusions null", analyze(build(4, m_err), 4)["conclusions"] is None))
    def m_miss(rows):
        rows.pop()
    cases.append(("a missing row -> P4 fails", not analyze(build(4, m_miss), 4)["preconditions"]["P4_complete"]["pass"]))
    def m_first(rows):
        rows[1]["ttft_ms"] = 99999
    cases.append(("dropped first request never reaches a figure", safe(
        lambda: analyze(build(4, m_first), 4)["conclusions"]["address_delay_ollama_localhost_minus_loopback"]["ttft_ms"]["max"] == 2050)))
    for name, okk in cases:
        print(("PASS " if okk else "FAIL ") + name)
    return 0 if all(okk for _, okk in cases) else 1


def main():
    if sys.argv[1] == "--self-test":
        return self_test()
    d = sys.argv[1]
    rows = [json.loads(l) for l in open(os.path.join(d, "requests.jsonl"), encoding="utf-8") if l.strip()]
    res = analyze(rows)
    res["rows"] = len(rows)
    json.dump(res, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(json.dumps({"preconditions_pass": res["preconditions_pass"], "preconditions": res["preconditions"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
