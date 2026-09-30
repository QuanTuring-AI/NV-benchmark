#!/usr/bin/env python3
"""Vol.2 · P80 · post-run for the P78 / P79 publication set: public event files, the P79 judge files and sentinel replay,
and the recompute checks.

1. events_public.jsonl beside every published events.jsonl, with desktop information reduced:
   - an isolation record's gpu_compute_apps (the desktop's GPU processes with their paths) -> counts only (as P70);
   - every per-process GPU-memory map (keys gpu_memory_windows*: GiB per "<process>:dedicated|shared", read from the
     Windows counters) -> reduce_map(): the WSL VM process (vmwp, the containers), the desktop compositor (dwm) and the
     adapter totals are kept; every other process is summed into "other_processes:dedicated|shared" with a count.
   windows_gpu_memory_public.jsonl is the same reduction of P79's 10 s samples. events.jsonl and
   windows_gpu_memory.jsonl stay on the machine.
2. P79: judge.json per phase (p79_judge.py on levels.jsonl) and sentinel_replay.json (tools/container_sentinel.py over
   events_public.jsonl and levels.jsonl of T1 and T2, with its triggered tests).
3. Recompute checks, written to vol2-nemotron/results/p78_quality/recompute_check.txt: a scratch root holding only the
   published inputs must reproduce the repository's analysis.json (G1, quality, G4), durations.json, judge.json and
   sentinel_replay.json byte for byte. Negative controls in a second root: one quality cell's G8 record set to failed
   (analysis.json must change) and +5000 ms on one P79 R c=1 TTFT p50 (judge.json must change).
usage: p80_postrun.py [--check-only]
"""
import glob, hashlib, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
RUNS_EVENTS = ["vol1-nim/results/p78_fp8_clean", "vol2-nemotron/results/p78_quality", "vol2-nemotron/results/p78_nim_vs_vllm",
               "vol2-nemotron/results/p79_host_state/T1", "vol2-nemotron/results/p79_host_state/T2"]
P79 = "vol2-nemotron/results/p79_host_state"
KEEP = ("vmwp:", "dwm:", "adapter:")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None  # noqa: E731


def reduce_map(m):
    if not isinstance(m, dict) or not any(":" in k for k in m):
        return m
    out = {k: v for k, v in m.items() if k.startswith(KEEP)}
    other = {k: v for k, v in m.items() if not k.startswith(KEEP)}
    for kind in ("dedicated", "shared"):
        out[f"other_processes:{kind}"] = round(sum(v for k, v in other.items() if k.endswith(":" + kind)), 3)
    out["other_processes:count"] = len({k.rsplit(":", 1)[0] for k in other})
    return out


def redact(e):
    e = dict(e)
    iso = e.get("isolation")
    if isinstance(iso, dict) and "gpu_compute_apps" in iso:
        raw = iso["gpu_compute_apps"]
        rows = [r for r in raw.splitlines() if r.strip()] if isinstance(raw, str) and raw != "(none listed)" else []
        e["isolation"] = dict(iso, gpu_compute_apps={"listed_processes": len(rows), "note": "raw list withheld (desktop processes with personal paths); counts only"})
    for k in list(e):
        if k.startswith("gpu_memory_windows"):
            e[k] = reduce_map(e[k])
    return e


def write_public(src, dst, fn=redact):
    with open(dst, "w", encoding="utf-8", newline="\n") as out:
        for line in open(src, encoding="utf-8"):
            if line.strip():
                out.write(json.dumps(fn(json.loads(line)), ensure_ascii=False) + "\n")


def p79_outputs(root):
    """judge.json per phase and sentinel_replay.json, from levels.jsonl and events_public.jsonl under root."""
    import container_sentinel as CS
    d = os.path.join(root, P79)
    for ph in ("T1", "T2"):
        r = subprocess.run([sys.executable, os.path.join(HERE, "p79_judge.py"), os.path.join(d, ph, "levels.jsonl")], capture_output=True, text=True)
        open(os.path.join(d, ph, "judge.json"), "w", encoding="utf-8", newline="\n").write(r.stdout)
    out = {"what": "P79 acceptance item 9: tools/container_sentinel.py replayed on the P79 T1 and T2 records (no GPU), plus triggered tests with a fake reference",
           "references": {"R_c1_ttft_p50_ms": "156.0, p55_concurrency_a2_256/levels.jsonl line 15", "C_c128_itl_p50_ms": "30.7, same file line 9"},
           "containers": [], "triggered_tests": {}}
    for ph in ("T1", "T2"):
        ev = [json.loads(l) for l in open(os.path.join(d, ph, "events_public.jsonl"), encoding="utf-8")]
        lv = [json.loads(l) for l in open(os.path.join(d, ph, "levels.jsonl"), encoding="utf-8")]
        prev = None
        for e in ev:
            w = (e.get("wsl") or {}).get("docker-desktop", {}); g = e.get("gpu_memory_windows") or {}
            snap = {"container_sysmem_gib": g.get("vmwp:shared", 0.0) or 0.0, "other_dedicated_gib": 0.0,
                    "make_resident_failures": int(w.get("make_resident_failures") or 0), "wsl_vm_uptime_s": float((w.get("proc_uptime") or "0").split()[0])}
            if e["kind"] in ("run_start", "container_before_stop") and w:
                prev = dict(snap, container_sysmem_gib=0.0 if e["kind"] == "container_before_stop" else snap["container_sysmem_gib"])
            if e["kind"] == "container_ready":
                b = CS._judge_birth(prev, snap); seq = e["container_seq"]
                r1 = next(x for x in lv if x.get("container_seq") == seq and x["profile"] == "R" and x["concurrency"] == 1 and not x.get("warmup"))
                c128 = next(x for x in lv if x.get("container_seq") == seq and x["profile"] == "C" and x["concurrency"] == 128)
                v1 = r1["summary"]["time_to_first_token"]["p50"]; v2 = c128["summary"]["inter_token_latency"]["p50"]
                out["containers"].append({"phase": ph, "seq": seq, "setting": e["setting"], "birth_record_only": {"flag": not b["pass"], "reasons": b["reasons"]},
                                          "speed_R1": {"value": round(v1, 1), "pass": CS.speed_check(v1, 156.0)["pass"]},
                                          "speed_C128": {"value": round(v2, 2), "pass": CS.speed_check(v2, 30.7)["pass"]}})
    import datetime as dt
    c = out["containers"][0]
    out["triggered_tests"] = {"fake_reference_10ms_on_T1_container1_R1_passes": CS.speed_check(c["speed_R1"]["value"], 10.0)["pass"],
                              "this_mornings_s256_R_c1_3356.9ms_passes": CS.speed_check(3356.9, 156.0)["pass"],
                              "time_gate_08:00_open_at_08:03": CS.time_gate("08:00", dt.datetime(2026, 9, 30, 8, 3)),
                              "time_gate_08:00_open_at_07:59": CS.time_gate("08:00", dt.datetime(2026, 9, 30, 7, 59))}
    json.dump(out, open(os.path.join(d, "sentinel_replay.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)


PUBLISHED_INPUTS = {  # what each recompute reads, relative to the repository root (the published copies only)
    "vol1-nim/results/p78_fp8_clean": ["levels.jsonl", "events_public.jsonl", "prediction_p78_fp8.json"],
    "vol2-nemotron/results/p78_quality": ["items.jsonl", "events_public.jsonl"],
    "vol2-nemotron/results/p78_nim_vs_vllm": ["levels.jsonl", "events_public.jsonl", "requests.jsonl"],
    P79 + "/T1": ["levels.jsonl", "events_public.jsonl"], P79 + "/T2": ["levels.jsonl", "events_public.jsonl"],
}
OUTPUTS = ["vol1-nim/results/p78_fp8_clean/analysis.json", "vol2-nemotron/results/p78_quality/analysis.json",
           "vol2-nemotron/results/p78_quality/durations.json", "vol2-nemotron/results/p78_nim_vs_vllm/analysis.json",
           P79 + "/T1/judge.json", P79 + "/T2/judge.json", P79 + "/sentinel_replay.json"]


def scratch_root():
    t = tempfile.mkdtemp(prefix="p80pub_")
    for run, fs in PUBLISHED_INPUTS.items():
        for f in fs:
            os.makedirs(os.path.join(t, run), exist_ok=True); shutil.copyfile(os.path.join(REPO, run, f), os.path.join(t, run, f))
    return t


def recompute(root):
    subprocess.run([sys.executable, os.path.join(HERE, "p78_analyze.py"), root], capture_output=True, text=True)
    p79_outputs(root)
    return {o: sha(os.path.join(root, o)) for o in OUTPUTS}


def main():
    if "--check-only" not in sys.argv:
        for run in RUNS_EVENTS:
            write_public(os.path.join(REPO, run, "events.jsonl"), os.path.join(REPO, run, "events_public.jsonl"))
        for ph in ("T1", "T2"):
            write_public(os.path.join(REPO, P79, ph, "windows_gpu_memory.jsonl"), os.path.join(REPO, P79, ph, "windows_gpu_memory_public.jsonl"),
                         fn=lambda e: dict(e, gib=reduce_map(e.get("gib"))))
        p79_outputs(REPO)
    repo = {o: sha(os.path.join(REPO, o)) for o in OUTPUTS}
    t = scratch_root(); pub = recompute(t)
    n = scratch_root()
    q = os.path.join(n, "vol2-nemotron/results/p78_quality/events_public.jsonl"); L = open(q, encoding="utf-8").readlines()
    for i, l in enumerate(L):
        e = json.loads(l)
        if e.get("kind") == "g8":
            e["pass"] = False; L[i] = json.dumps(e, ensure_ascii=False) + "\n"; break
    open(q, "w", encoding="utf-8", newline="\n").writelines(L)
    p = os.path.join(n, P79, "T1", "levels.jsonl"); L = open(p, encoding="utf-8").readlines()
    for i, l in enumerate(L):
        e = json.loads(l)
        if e.get("profile") == "R" and e.get("concurrency") == 1 and not e.get("warmup"):
            e["summary"]["time_to_first_token"]["p50"] += 5000.0; L[i] = json.dumps(e, ensure_ascii=False) + "\n"; break
    open(p, "w", encoding="utf-8", newline="\n").writelines(L)
    neg = recompute(n)
    same = {o: repo[o] == pub[o] and repo[o] is not None for o in OUTPUTS}
    neg_q = neg["vol2-nemotron/results/p78_quality/analysis.json"] != repo["vol2-nemotron/results/p78_quality/analysis.json"]
    neg_j = neg[P79 + "/T1/judge.json"] != repo[P79 + "/T1/judge.json"]
    with open(os.path.join(REPO, "vol2-nemotron/results/p78_quality/recompute_check.txt"), "w", encoding="utf-8", newline="\n") as o:
        o.write("recompute check (P80) · outputs from the published inputs only, in an empty scratch root\n")
        o.write("inputs: " + "; ".join(f"{r}: {', '.join(fs)}" for r, fs in PUBLISHED_INPUTS.items()) + "\n")
        for k in OUTPUTS:
            o.write(f"{k}: repository {repo[k]} · recomputed {pub[k]} · identical {same[k]}\n")
        o.write(f"negative control 1 (the first quality G8 record set to failed): p78_quality/analysis.json changes: {neg_q}\n")
        o.write(f"negative control 2 (+5000 ms on T1 container 1 R c=1 TTFT p50): T1/judge.json changes: {neg_j}\n")
    shutil.rmtree(t); shutil.rmtree(n)
    ok = all(same.values()) and neg_q and neg_j
    print("identical:", same, "· negative controls change:", neg_q, neg_j, "·", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
