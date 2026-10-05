#!/usr/bin/env python3
"""Ollama CPU control · analysis. Rules frozen in prediction_ollama_cpu_control.json.

Preconditions (any failure -> every conclusion field is null, exit 1):
  P1  no request errors, every request HTTP 200
  P2  placement at every request, from /api/ps before AND after it: CPU size_vram == 0; G size_vram == size;
      and `docker ps` empty before every request
  P3  complete: G has one row for each of its planned questions, CPU one row for each of the 50 (3 and 50)
Per series (no request is dropped; each arm had an unmeasured warm-up that loaded the model in its placement):
  generation_tps_client  tokens / (total - ttft), tokens counted as in Vol.1 (whitespace words), per request
  generation_tps_engine  eval_count / eval_duration, per request
  ttft_ms, total_latency_ms, tps (Vol.1 formula), prompt_eval_duration_ms, completion_tokens
Conclusions:
  R1  median generation_tps_client of CPU within [5, 40]  (recorded, not a gate)
  ratio_g_over_cpu  median G / median CPU for both generation rates, on the G questions only
usage: ollama_cpu_control_analyze.py <run_dir> [--plan-g N] | --self-test
"""
import json, os, statistics as st, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R1_BAND = (5.0, 40.0)
MODEL = "llama3.1:8b"


def share(ps):
    m = [x for x in (ps or []) if (x.get("name") or "").startswith(MODEL)]
    if len(m) != 1 or not isinstance(m[0].get("size"), int) or not isinstance(m[0].get("size_vram"), int):
        return None
    return m[0]["size_vram"] / m[0]["size"]


def placed(r):
    want = 0.0 if r["arm"] == "CPU" else 1.0
    return (share(r.get("ollama_ps_before")) == want and share(r.get("ollama_ps_after")) == want
            and not r.get("docker_ps_before"))


def gen_client(r):
    t, tot, n = r.get("ttft_ms"), r.get("total_latency_ms"), r.get("tokens")
    if not all(isinstance(x, (int, float)) for x in (t, tot, n)) or tot <= t:
        return None
    return n / ((tot - t) / 1000)


def gen_engine(r):
    c, d = r.get("completion_tokens"), r.get("eval_duration_ms")
    if not isinstance(c, int) or not isinstance(d, (int, float)) or d <= 0:
        return None
    return c / (d / 1000)


def desc(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "avg": round(sum(xs) / len(xs), 2), "p50": round(st.median(xs), 2),
            "min": round(xs[0], 2), "max": round(xs[-1], 2)}


def analyse(rows, plan_g=3, plan_cpu=50):
    by = {"G": [r for r in rows if r.get("arm") == "G"], "CPU": [r for r in rows if r.get("arm") == "CPU"]}
    errs = [r for r in rows if r.get("error") or r.get("http_status") != 200]
    bad = [(r.get("arm"), r.get("question_id")) for r in rows if not placed(r)]
    counts = {k: len({r["question_id"] for r in v}) for k, v in by.items()}
    rowsn = {k: len(v) for k, v in by.items()}
    pre = {"P1_no_errors": {"errors": len(errs), "pass": not errs},
           "P2_placement_every_request": {"violations": len(bad), "first": bad[:5], "pass": not bad},
           "P3_complete": {"questions": counts, "rows": rowsn,
                           "pass": counts == {"G": plan_g, "CPU": plan_cpu} and rowsn == counts}}
    ok = all(v["pass"] for v in pre.values())
    out = {"preconditions": pre, "preconditions_pass": ok, "conclusions": None, "rows": len(rows)}
    if not ok:
        return out
    ser = {}
    for k, v in by.items():
        ser[k] = {"generation_tps_client": desc(gen_client(r) for r in v),
                  "generation_tps_engine": desc(gen_engine(r) for r in v),
                  "ttft_ms": desc(r.get("ttft_ms") for r in v),
                  "total_latency_ms": desc(r.get("total_latency_ms") for r in v),
                  "tps_vol1_formula": desc(r.get("tps") for r in v),
                  "prompt_eval_duration_ms": desc(r.get("prompt_eval_duration_ms") for r in v),
                  "completion_tokens": desc(r.get("completion_tokens") for r in v)}
    gq = {r["question_id"] for r in by["G"]}
    cpu_g = [r for r in by["CPU"] if r["question_id"] in gq]
    ratio = {}
    for name, f in (("generation_tps_client", gen_client), ("generation_tps_engine", gen_engine)):
        g, c = st.median(f(r) for r in by["G"]), st.median(f(r) for r in cpu_g)
        ratio[name] = round(g / c, 2)
    m = ser["CPU"]["generation_tps_client"]["p50"]
    out["conclusions"] = {
        "per_series": ser,
        "ratio_g_over_cpu_same_questions": {"questions": sorted(gq), **ratio},
        "R1": {"statistic": "median generation_tps_client, CPU", "value": m, "band": list(R1_BAND),
               "held": R1_BAND[0] <= m <= R1_BAND[1]},
        "reading": "one run on this machine; generation rates exclude the time to first token. Not a reproduction of "
                   "any earlier configuration."}
    return out


def ps(size, vram):
    return [{"name": MODEL, "size": size, "size_vram": vram}]


def mk(arm, qid, ttft=100.0, total=10100.0, tokens=100, ct=120, ed=10000.0, vram=None, err=None, status=200,
       docker=None, after_vram=None):
    v = (0 if arm == "CPU" else 7000) if vram is None else vram
    av = v if after_vram is None else after_vram
    r = {"arm": arm, "question_id": qid, "ttft_ms": ttft, "total_latency_ms": total, "tokens": tokens,
         "tps": round(tokens / total * 1000, 1), "completion_tokens": ct, "eval_duration_ms": ed,
         "prompt_eval_duration_ms": 50.0, "http_status": status, "docker_ps_before": docker or [],
         "ollama_ps_before": ps(7000, v), "ollama_ps_after": ps(7000, av)}
    if err:
        r["error"] = err
    return r


def base_rows():
    rows = [mk("G", f"q{i}", total=1100.0, ed=500.0) for i in range(3)]
    return rows + [mk("CPU", f"q{i}") for i in range(50)]


def self_test():
    cases = []
    a = analyse(base_rows()); c = a["conclusions"]
    cases.append(("clean run passes", a["preconditions_pass"]))
    cases.append(("client rate = tokens/(total-ttft): CPU 100/10 s = 10.0",
                  c["per_series"]["CPU"]["generation_tps_client"]["p50"] == 10.0))
    cases.append(("engine rate = eval_count/eval_duration: CPU 120/10 s = 12.0",
                  c["per_series"]["CPU"]["generation_tps_engine"]["p50"] == 12.0))
    cases.append(("R1 held at 10.0", c["R1"]["held"] is True))
    cases.append(("ratio on G questions: client 100/1 s over 10 = 10.0", c["ratio_g_over_cpu_same_questions"]
                  ["generation_tps_client"] == 10.0))
    rows = base_rows(); rows[10] = mk("CPU", "q7", vram=3500)
    cases.append(("CPU row partly on GPU -> null", analyse(rows)["conclusions"] is None))
    rows = base_rows(); rows[10] = mk("CPU", "q7", after_vram=7000)
    cases.append(("CPU placement changed after request -> null", analyse(rows)["conclusions"] is None))
    rows = base_rows(); rows[0] = mk("G", "q0", vram=0, total=1100.0, ed=500.0)
    cases.append(("G row not on GPU -> null", analyse(rows)["conclusions"] is None))
    rows = base_rows(); rows[5] = mk("CPU", "q2", docker=["nim"])
    cases.append(("container running -> null", analyse(rows)["conclusions"] is None))
    rows = base_rows(); rows[5] = mk("CPU", "q2", status=500)
    cases.append(("HTTP 500 -> null", analyse(rows)["conclusions"] is None))
    rows = base_rows()[:-1]
    cases.append(("49 CPU rows -> null", analyse(rows)["conclusions"] is None))
    rows = base_rows() + [mk("CPU", "q49")]
    cases.append(("duplicate CPU row -> null", analyse(rows)["conclusions"] is None))
    rows = base_rows()
    rows[3:] = [mk("CPU", f"q{i}", total=2100.0, ed=1000.0) for i in range(50)]
    cases.append(("CPU at 50 tok/s -> R1 not held", analyse(rows)["conclusions"]["R1"]["held"] is False))
    rows = base_rows()
    rows[3:] = [mk("CPU", f"q{i}", total=40100.0, ed=40000.0) for i in range(50)]
    cases.append(("CPU at 2.5 tok/s -> R1 not held", analyse(rows)["conclusions"]["R1"]["held"] is False))
    fails = [n for n, ok in cases if not ok]
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{len(cases) - len(fails)}/{len(cases)} pass")
    return 1 if fails else 0


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    plan_g = int(sys.argv[sys.argv.index("--plan-g") + 1]) if "--plan-g" in sys.argv else 3
    plan_cpu = int(sys.argv[sys.argv.index("--plan-cpu") + 1]) if "--plan-cpu" in sys.argv else 50
    rows = [json.loads(l) for l in open(os.path.join(d, "requests.jsonl"), encoding="utf-8")]
    a = analyse(rows, plan_g, plan_cpu)
    json.dump(a, open(os.path.join(d, "analysis.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(json.dumps(a, ensure_ascii=False, indent=1))
    return 0 if a["preconditions_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
