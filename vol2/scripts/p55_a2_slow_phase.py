#!/usr/bin/env python3
"""Vol.2 · A2's slow first phase after READY, from records already on disk (no GPU). P55 G4.

For every A2 container in the long-context runs (p53_longctx, p53_longctx_addendum) and, when present locally, their
harness tests: the requests in the order sent (the discarded first request of p53_longctx included, from its event),
the number of leading requests whose generation rate is below 220 tok/s (the threshold the addendum's warm-up used:
every slow-phase rate seen was <= 209 tok/s, every steady rate >= 256), the seconds from the first request to the first
request at or above it, whether the slow phase ended before the container was stopped, and the position of the
container among the A2 containers of its run. From the container's full log, where saved: the latest timestamped engine
line and the FlashInfer autotune duration (both printed before READY). Output: slow_phase.json in the results dir.
usage: p55_a2_slow_phase.py --out vol2/results/p55_a2_slow_phase
"""
import argparse, datetime as dt, glob, json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FAST = 220.0
TS = re.compile(r"(20\d\d-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)")


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.exists(p) else []


def parse_local(s):
    return dt.datetime.fromisoformat(s[:19])


def log_facts(path):
    if not os.path.exists(path):
        return {"container_log": "not saved"}
    L = open(path, encoding="utf-8", errors="replace").read().splitlines()
    ts = [dt.datetime.fromisoformat(m.group(1) + " " + m.group(2)) for l in L for m in [TS.search(l)] if m]
    gemm2 = re.findall(r"Tuning trtllm::fused_moe::gemm2: 100%[^\[]*\[(\d\d):(\d\d)<", "\n".join(L))
    return {"container_log": os.path.relpath(path, REPO).replace(os.sep, "/"), "lines": len(L),
            "latest_timestamped_line_utc": max(ts).isoformat() if ts else None,
            "autotune_gemm2_seconds": max(int(a) * 60 + int(b) for a, b in gemm2) if gemm2 else None,
            "autotune_configs_saved": re.findall(r"Saved (\d+) configs", "\n".join(L))[-1:] or None}


def container_rows(run, arm="A2"):
    rows = jl(os.path.join(run, "requests.jsonl")); ev = jl(os.path.join(run, "events.jsonl"))
    starts = [e for e in ev if e.get("kind") == "depth_start" and e.get("arm") == arm]
    out = []
    for pos, e in enumerate(starts, 1):
        d = e["depth"]
        rs = [r for r in rows if r.get("arm") == arm and r.get("depth_target") == d]
        seq = []
        fr = e.get("first_request_discarded")
        if fr and fr.get("generation_tps") is not None:
            seq.append({"at": e["at"], "kind": "discarded (1k prompt)", "generation_tps": fr.get("generation_tps"), "ttft_ms": fr.get("ttft_ms")})
        seq += [{"at": r["at"], "kind": "warm-up" if r.get("warmup") else "measured", "generation_tps": r.get("generation_tps"), "ttft_ms": r.get("ttft_ms")} for r in rs]
        lead = 0
        for s in seq:
            if (s["generation_tps"] or 0) < FAST:
                lead += 1
            else:
                break
        ended = lead < len(seq)
        secs = (parse_local(seq[lead]["at"]) - parse_local(seq[0]["at"])).total_seconds() if ended and lead else (0.0 if ended else None)
        name = f"p53-ctx{'add' if 'addendum' in run else ''}-{arm.lower()}-{d}"
        logp = os.path.join(run, "logs", f"{name}.container.log.txt")
        out.append({"run": os.path.relpath(run, REPO).replace(os.sep, "/"), "depth": d, "position_among_A2_containers": pos, "ready_at_local": e["at"],
                    "seconds_to_ready": e.get("seconds_to_ready"), "requests": len(seq), "leading_slow_requests": lead, "slow_phase_ended": ended,
                    "seconds_first_request_to_first_fast": secs, "rates": [s["generation_tps"] for s in seq][:12], "ttft_ms": [s["ttft_ms"] for s in seq][:12],
                    **log_facts(logp)})
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
    runs = [os.path.join(REPO, "vol2", "results", "p53_longctx"), os.path.join(REPO, "vol2", "results", "p53_longctx_addendum")]
    runs += sorted(glob.glob(os.path.join(REPO, "vol2", "results", "p53_longctx_addendum", "harness_test", "p53ctxadd_*")))
    table = [c for r in runs for c in container_rows(r)]
    os.makedirs(a.out, exist_ok=True)
    res = {"threshold_tok_s": FAST, "containers": table,
           "summary": {"containers": len(table), "with_slow_phase": sum(1 for c in table if c["leading_slow_requests"]),
                       "max_leading_slow_requests_ended": max([c["leading_slow_requests"] for c in table if c["slow_phase_ended"]] or [0]),
                       "max_seconds_to_first_fast": max([c["seconds_first_request_to_first_fast"] or 0 for c in table if c["slow_phase_ended"]] or [0]),
                       "not_ended_before_stop": [(c["run"].split("/")[-1], c["depth"], c["requests"]) for c in table if not c["slow_phase_ended"]]}}
    json.dump(res, open(os.path.join(a.out, "slow_phase.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    for c in table:
        print(f"{c['run'].split('/')[-1]:28s} d={c['depth']:6d} pos={c['position_among_A2_containers']} slow={c['leading_slow_requests']:2d}/{c['requests']:2d} ended={c['slow_phase_ended']} secs={c['seconds_first_request_to_first_fast']} autotune_gemm2={c.get('autotune_gemm2_seconds')} last_log_utc={c.get('latest_timestamped_line_utc')} ready={c['ready_at_local']}")
    print(json.dumps(res["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
