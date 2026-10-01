#!/usr/bin/env python3
"""Vol.2 · P80 · the six re-run sweeps of the P80 night beside their originals, judged by the originals' own rules.

Written after the run (2026-10-01); it adds no rule. Each P80 sweep is passed to the analysis function of the run it
repeats -- p53_concurrency_v2_analyze.analyse for v2_A1_* / v2_A2_*, p55_concurrency_a2_analyze.analyse (cap 256) for
s256_* -- so the preconditions (P1 no failed request at a live level, P2 instrument calibrated, P3 sequence cap) and the
SLO ceilings are the pre-registered ones of those runs. The originals' conclusions are read from their published
analysis.json.

What this file adds to the rows before the call (the adapter, tested below):
  - a P80 row is a measured level of the group: not a warm-up level, not a sentinel probe, not a skipped-levels record;
  - a level run twice (arm-health rule: after / before < 0.8 -> container restarted, the level run again) is taken from
    its second run; a level that the rule made null is left out and listed under "null_levels";
  - the container_start event the analysers expect (arm, profile, container, env, calibration) is built from the P80
    events of the group's first container.
Outside the originals' rules, and marked so: "largest_level_inside_slo_without_p1" is the same SLO test with the P1
precondition set aside. It exists because one P80 sweep (s256_R) had one failed request at c=512, far above its
ceiling, which makes its pre-registered conclusion null.

Also written: per-level throughput beside the original (ratio), the container table (system-memory share of the WSL VM
process during the load and at READY, from the 10 s Windows samples) and the engine-exit ledger of the A1 containers.
usage: p80_slo.py [<repo_root>]   -> <repo_root>/vol2-nemotron/results/p80_rerun/slo_ceilings.json
       p80_slo.py self_test
       p80_slo.py excerpts        -> .../p80_rerun/engine_log_excerpts.json (from the container logs kept on the machine)
       p80_slo.py recompute_check -> .../p80_rerun/recompute_check.txt (judge.json and slo_ceilings.json from the published inputs, with two negative controls)
"""
import datetime as dt, glob, hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import p53_concurrency_v2_analyze as A53  # noqa: E402
import p55_concurrency_a2_analyze as A55  # noqa: E402

RES = "vol2-nemotron/results"
GROUPS = {  # group -> (arm, profile, original run, analyser)
    "s256_C": ("A2", "C", "p55_concurrency_a2_256", "p55"), "s256_R": ("A2", "R", "p55_concurrency_a2_256", "p55"),
    "v2_A2_C": ("A2", "C", "p53_concurrency_v2", "p53"), "v2_A2_R": ("A2", "R", "p53_concurrency_v2", "p53"),
    "v2_A1_C": ("A1", "C", "p53_concurrency_v2", "p53"), "v2_A1_R": ("A1", "R", "p53_concurrency_v2", "p53"),
}
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]  # noqa: E731
T = lambda s: dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")  # noqa: E731


def select_rows(levels, events, group, keep="last", drop_sentinel=True, drop_null=True):
    """The measured rows of one P80 group for the original analyser, and the levels the arm-health rule made null."""
    nulls = sorted(e["concurrency"] for e in events if e.get("kind") == "level_null" and e.get("group") == group)
    by_n = {}
    for r in levels:
        if r.get("group") != group or r.get("warmup") or "skipped_levels" in r or r.get("concurrency") is None:
            continue
        if drop_sentinel and r.get("sentinel"):
            continue
        if keep == "first" and r["concurrency"] in by_n:
            continue
        by_n[r["concurrency"]] = r
    rows = [r for n, r in sorted(by_n.items()) if not (drop_null and n in nulls)]
    skipped = [r for r in levels if r.get("group", r.get("sweep")) == group and "skipped_levels" in r]
    return rows + [dict(s, arm=rows[0]["arm"], profile=rows[0]["profile"], container="main") for s in skipped if rows], nulls


def start_event(events, group, arm, prof):
    cs = next(e for e in events if e.get("kind") == "container_start" and e.get("group") == group)
    cal = next((e["calibration"] for e in events if e.get("kind") == "calibration" and e.get("group") == group), None)
    return {"kind": "container_start", "arm": arm, "profile": prof, "container": "main", "env": cs.get("env") or {}, "calibration": cal}


def without_p1(table):
    """The SLO test alone over the levels that have a value and no failed request (not a pre-registered conclusion)."""
    out = {}
    for name, slo in A53.SLO.items():
        ok = [t["concurrency"] for t in table if not t["engine_dead"] and not (t.get("errors") or 0) and t["ttft_ms"]["p99"] is not None
              and t["itl_ms"]["p99"] is not None and t["ttft_ms"]["p99"] <= slo["ttft_p99_ms"] and t["itl_ms"]["p99"] <= slo["itl_p99_ms"]]
        out[name] = max(ok) if ok else 0
    return out


def one_group(root, group, levels, events):
    arm, prof, orig_run, which = GROUPS[group]
    rows, nulls = select_rows(levels, events, group)
    ev = [start_event(events, group, arm, prof)]
    run_dir = os.path.join(root, RES, "p80_rerun", group)
    a = A55.analyse(rows, ev, 256, run_dir=run_dir) if which == "p55" else A53.analyse(rows, ev)
    s = a["sweeps"]["|".join((arm, prof, "main"))]
    oa = json.load(open(os.path.join(root, RES, orig_run, "analysis.json"), encoding="utf-8"))["sweeps"]["|".join((arm, prof, "main"))]
    o_by = {t["concurrency"]: t for t in oa["levels"]}
    table = []
    for t in s["levels"]:
        o = o_by.get(t["concurrency"]) or {}
        ratio = round(t["output_tps"] / o["output_tps"], 3) if t.get("output_tps") and o.get("output_tps") else None
        table.append({"concurrency": t["concurrency"], "original_tps": o.get("output_tps"), "p80_tps": t.get("output_tps"), "p80_over_original": ratio,
                      "original_ttft_p99_ms": (o.get("ttft_ms") or {}).get("p99"), "p80_ttft_p99_ms": t["ttft_ms"]["p99"],
                      "original_itl_p99_ms": (o.get("itl_ms") or {}).get("p99"), "p80_itl_p99_ms": t["itl_ms"]["p99"],
                      "p80_errors": t.get("errors"), "p80_first_error": t.get("first_error"), "p80_engine_dead": t["engine_dead"],
                      "original_engine_dead": o.get("engine_dead")})
    pick = lambda c: None if c is None else {k: c.get(k) for k in ("max_concurrency_within_server_slo", "max_concurrency_within_interactive_slo", "ceiling", "engine_crash_at")}  # noqa: E731
    return {"arm": arm, "profile": prof, "original_run": orig_run, "analyser": "p55_concurrency_a2_analyze.analyse (cap 256)" if which == "p55" else "p53_concurrency_v2_analyze.analyse",
            "original": {"preconditions_pass": oa["preconditions_pass"], "conclusions": pick(oa["conclusions"])},
            "p80": {"preconditions": {k: v["pass"] for k, v in s["preconditions"].items()}, "p1_bad_levels": s["preconditions"]["P1_levels_clean_below_ceiling"]["bad_levels"],
                    "preconditions_pass": s["preconditions_pass"], "conclusions": pick(s["conclusions"]),
                    "largest_level_inside_slo_without_p1": without_p1(s["levels"]), "null_levels": nulls},
            "levels": table}


def containers(events, win):
    out = []
    for e in events:
        if e.get("kind") != "container_start":
            continue
        t1 = T(e["at"]); t0 = t1 - dt.timedelta(seconds=e["seconds"])
        sel = [x["gib"] for x in win if t0 <= T(x["at"]) <= t1]
        mx = lambda k: max((g.get(k) or 0.0) for g in sel) if sel else None  # noqa: E731
        sa, sb = e["state_after"], e["state_before"]
        out.append({"container": e["name"], "group": e["group"], "load_s": e["seconds"], "samples_in_load": len(sel),
                    "sysmem_gib_max_during_load": mx("vmwp:shared"), "sysmem_gib_at_ready": sa["container_sysmem_gib"], "dedicated_gib_at_ready": sa["container_dedicated_gib"],
                    "compositor_gib_max_during_load": mx("dwm:dedicated"), "other_processes_gib_max_during_load": mx("other_processes:dedicated"),
                    "new_make_resident_failures": sa["make_resident_failures"] - sb["make_resident_failures"]})
    return out


def engine_exits(levels, events):
    """One line per A1 container: where its engine was found dead (from cell_end and levels.jsonl)."""
    starts = [e for e in events if e.get("kind") == "container_start" and e["group"].startswith("v2_A1")]
    out = []
    for i, c in enumerate(starts):
        t0 = T(c["at"]); nxt = [T(x["at"]) for x in events if x.get("kind") in ("container_start", "group_end") and T(x["at"]) > t0]
        t1 = min(nxt) if nxt else None
        cells = [e for e in events if e.get("kind") == "cell_end" and e.get("group") == c["group"] and T(e["at"]) > t0 and (t1 is None or T(e["at"]) <= t1)]
        found = None
        for e in cells:
            if e.get("engine_dead"):
                found = {"level": e["concurrency"], "when": "during the level (no result)"}; break
            if not (e.get("health_after") or {}).get("rate_median"):
                found = {"level": e["concurrency"], "when": "after the level completed (the c=1 health probe that follows got no answer)"}; break
        out.append({"container": c["name"], "levels_run": [e["concurrency"] for e in cells], "engine_exit": found})
    body = sorted({(r.get("engine_after") or {}).get("body_head") for r in levels if r.get("engine_dead") and r.get("group", "").startswith("v2_A1")} - {None})
    return {"containers": out, "error_bodies_seen": body}


def build(root):
    d = os.path.join(root, RES, "p80_rerun")
    levels, events = jl(os.path.join(d, "levels.jsonl")), jl(os.path.join(d, "events.jsonl"))
    win = jl(os.path.join(d, "windows_gpu_memory_public.jsonl"))
    g5 = [{"concurrency": r["concurrency"], "tps": A53.pct(r.get("summary"), "output_token_throughput", "avg"), "ttft_p99_ms": A53.pct(r.get("summary"), "time_to_first_token", "p99"),
           "itl_p99_ms": A53.pct(r.get("summary"), "inter_token_latency", "p99"), "errors": (r.get("summary") or {}).get("error_request_count", {}).get("avg") if isinstance((r.get("summary") or {}).get("error_request_count"), dict) else None,
           "engine_dead": bool(r.get("engine_dead"))} for r in levels if r.get("group") == "G5" and not r.get("warmup") and not r.get("sentinel") and r.get("concurrency")]
    return {"what": "the P80 night's six re-run sweeps judged by the analysis functions of the runs they repeat; written after the run, no new rule",
            "slo": A53.SLO, "groups": {g: one_group(root, g, levels, events) for g in GROUPS},
            "G5_levels": g5, "containers": containers(events, win), "a1_engine_exits": engine_exits(levels, events)}


PATTERNS = [("fallback", r"Falling back to V0 Engine"), ("engine_init", r"Initializing a V[01] LLM engine"), ("mamba_cache_frame", r"mamba_cache\.py\", line \d+, in current_run_tensors"),
            ("pop_frame", r"constant_size_cache\.py\", line \d+, in _assign_seq_id_to_cache_index"), ("error", r"^IndexError: pop from empty list"),
            ("engine_dead", r"Engine loop is not running.*IndexError\('pop from empty list'\)")]


def excerpts():
    d = os.path.join(REPO, RES, "p80_rerun"); out = {"what": "the first line matching each pattern in each container log of the P80 night; the logs themselves stay on the machine (their SHA-256 is given)",
                                                     "patterns": {k: v for k, v in PATTERNS}, "logs": {}}
    for f in sorted(glob.glob(os.path.join(d, "logs", "p80-*.container.log.txt"))):
        raw = open(f, "rb").read(); lines = raw.decode("utf-8", "replace").splitlines(); hit = {}
        for key, pat in PATTERNS:
            rx = re.compile(pat)
            m = next(((i + 1, l) for i, l in enumerate(lines) if rx.search(l)), None)
            n = sum(1 for l in lines if rx.search(l))
            hit[key] = {"line": m[0], "text": re.sub(r"with config: .*", "with config: ...", m[1].strip())[:200], "matching_lines": n} if m else None
        out["logs"][os.path.basename(f)] = {"sha256": hashlib.sha256(raw).hexdigest(), "lines": len(lines), "first_match": hit}
    json.dump(out, open(os.path.join(d, "engine_log_excerpts.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print("written engine_log_excerpts.json for", len(out["logs"]), "logs")


PUBLISHED_INPUTS = ["p80_rerun/levels.jsonl", "p80_rerun/events.jsonl", "p80_rerun/windows_gpu_memory_public.jsonl",
                    "p53_concurrency_v2/analysis.json", "p55_concurrency_a2_256/analysis.json"]


def recompute_check():
    """A scratch root holding only published inputs must reproduce judge.json and slo_ceilings.json byte for byte; two
    negative controls must change them. Writes p80_rerun/recompute_check.txt."""
    import shutil, subprocess, tempfile
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
    src = os.path.join(REPO, RES); lines = []

    def root(mut=None):
        t = tempfile.mkdtemp(prefix="p80slo_"); dst = os.path.join(t, RES)
        files = list(PUBLISHED_INPUTS) + [os.path.relpath(f, src).replace(os.sep, "/") for f in glob.glob(os.path.join(src, "p80_rerun", "smi_*.csv"))
                                         + glob.glob(os.path.join(src, "p80_rerun", "s256_*", "*", "c*", "server_metrics_export.json"))]
        for f in files:
            os.makedirs(os.path.dirname(os.path.join(dst, f)), exist_ok=True); shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
        if mut:
            p = os.path.join(dst, "p80_rerun", "levels.jsonl"); rows = jl(p); mut(rows)
            open(p, "w", encoding="utf-8", newline="\n").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        subprocess.run([sys.executable, os.path.join(HERE, "p80_judge.py"), os.path.join(dst, "p80_rerun")], capture_output=True, text=True)
        json.dump(build(t), open(os.path.join(dst, "p80_rerun", "slo_ceilings.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
        out = {n: sha(os.path.join(dst, "p80_rerun", n)) for n in ("judge.json", "slo_ceilings.json")}
        shutil.rmtree(t, ignore_errors=True)
        return out, len(files)
    repo = {n: sha(os.path.join(src, "p80_rerun", n)) for n in ("judge.json", "slo_ceilings.json")}
    got, n = root()
    ok = got == repo
    lines.append(f"recompute from the published inputs only ({n} files copied to a scratch root): " + ", ".join(f"{k} {'identical' if got[k] == repo[k] else 'DIFFERENT'} ({repo[k][:16]})" for k in repo))

    def half(rows):  # negative control 1: one measured level at half its throughput
        r = next(x for x in rows if x.get("group") == "v2_A2_C" and x.get("concurrency") == 8 and not x.get("warmup") and not x.get("sentinel"))
        r["summary"]["output_token_throughput"]["avg"] *= 0.4

    def slow(rows):  # negative control 2: +5,000 ms on one level's p99 TTFT
        r = next(x for x in rows if x.get("group") == "v2_A2_R" and x.get("concurrency") == 8 and not x.get("warmup") and not x.get("sentinel"))
        r["summary"]["time_to_first_token"]["p99"] += 5000.0
    n1, _ = root(half); n2, _ = root(slow)
    c1 = n1["judge.json"] != repo["judge.json"]; c2 = n2["slo_ceilings.json"] != repo["slo_ceilings.json"]
    lines.append(f"negative control 1 (v2_A2_C c=8 throughput x 0.4): judge.json {'changes' if c1 else 'DOES NOT CHANGE'}")
    lines.append(f"negative control 2 (v2_A2_R c=8 p99 TTFT + 5,000 ms): slo_ceilings.json {'changes' if c2 else 'DOES NOT CHANGE'}")
    ok = ok and c1 and c2
    lines.append("RESULT " + ("PASS" if ok else "FAIL"))
    open(os.path.join(src, "p80_rerun", "recompute_check.txt"), "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return ok


def self_test():
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want; ok = ok and good
        print(("  PASS " if good else "  FAIL ") + f"{name}: {got} (want {want})")
    row = lambda n, tps, **k: dict({"group": "g", "arm": "A2", "profile": "C", "container": "main", "concurrency": n, "summary": {"output_token_throughput": {"avg": tps}}}, **k)  # noqa: E731
    lv = [row(1, 10.0, warmup=True), row(1, 100.0, sentinel=True), row(1, 300.0), row(16, 500.0), row(16, 700.0), row(32, 900.0), row(32, 950.0),
          {"sweep": "g", "skipped_levels": [64], "reason": "engine dead"}]
    ev = [{"kind": "level_null", "group": "g", "concurrency": 32}]
    rows, nulls = select_rows(lv, ev, "g")
    tps = {r["concurrency"]: r["summary"]["output_token_throughput"]["avg"] for r in rows if "concurrency" in r}
    check("warm-up and sentinel rows are not levels; c=1 is the measured row", tps.get(1), 300.0)
    check("a level run twice is taken from its second run", tps.get(16), 700.0)
    check("a null level is left out", 32 in tps, False)
    check("the null level is reported", nulls, [32])
    check("the skipped-levels record is passed on with the sweep's key", [r.get("container") for r in rows if "skipped_levels" in r], ["main"])
    # mutation tests: each rule switched off must change the result
    m1 = {r["concurrency"]: r["summary"]["output_token_throughput"]["avg"] for r in select_rows(lv, ev, "g", keep="first")[0] if "concurrency" in r}
    check("mutation: keep the first run -> c=16 reads the first value", m1.get(16), 500.0)
    m2 = {r["concurrency"]: r["summary"]["output_token_throughput"]["avg"] for r in select_rows(lv, ev, "g", drop_sentinel=False, keep="first")[0] if "concurrency" in r}
    check("mutation: sentinel rows kept -> c=1 reads the probe", m2.get(1), 100.0)
    m3 = [r["concurrency"] for r in select_rows(lv, ev, "g", drop_null=False)[0] if "concurrency" in r]
    check("mutation: null levels kept -> c=32 is back", 32 in m3, True)
    t = lambda n, ttft, itl, err=0, dead=False: {"concurrency": n, "ttft_ms": {"p99": ttft}, "itl_ms": {"p99": itl}, "errors": err, "engine_dead": dead}  # noqa: E731
    tb = [t(1, 100, 5), t(8, 900, 9), t(16, 2100, 14), t(512, 1500, 20, err=1), t(64, None, None, dead=True)]
    check("without P1: server 8, interactive 1 (a level with a failed request does not count)", without_p1(tb), {"server": 8, "interactive": 1})
    tb2 = [dict(x, errors=0) for x in tb]
    check("mutation: the failed request removed -> server ceiling moves to 512", without_p1(tb2)["server"], 512)
    # positive control on the published originals: the analysers reproduce their own published ceilings from levels.jsonl
    for run, key, seqs in (("p53_concurrency_v2", "A2|R|main", None), ("p55_concurrency_a2_256", "A2|C|main", 256)):
        d = os.path.join(REPO, RES, run)
        lvo, evo = jl(os.path.join(d, "levels.jsonl")), jl(os.path.join(d, "events.jsonl"))
        a = A55.analyse(lvo, evo, seqs, run_dir=d) if seqs else A53.analyse(lvo, evo)
        pub = json.load(open(os.path.join(d, "analysis.json"), encoding="utf-8"))["sweeps"][key]["conclusions"]
        got = a["sweeps"][key]["conclusions"] or {}
        check(f"positive control: {run} {key} server / interactive ceilings recomputed = published",
              [got.get("max_concurrency_within_server_slo"), got.get("max_concurrency_within_interactive_slo")],
              [pub["max_concurrency_within_server_slo"], pub["max_concurrency_within_interactive_slo"]])
    print("SELF-TEST " + ("PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "self_test":
        sys.exit(0 if self_test() else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "excerpts":
        excerpts(); sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "recompute_check":
        sys.exit(0 if recompute_check() else 1)
    root = sys.argv[1] if len(sys.argv) > 1 else REPO
    out = build(root)
    p = os.path.join(root, RES, "p80_rerun", "slo_ceilings.json")
    json.dump(out, open(p, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    for g, v in out["groups"].items():
        c = v["p80"]["conclusions"] or {}; o = v["original"]["conclusions"] or {}
        print(f"{g:8s} original {o.get('max_concurrency_within_server_slo')}/{o.get('max_concurrency_within_interactive_slo')}  P80 {c.get('max_concurrency_within_server_slo')}/{c.get('max_concurrency_within_interactive_slo')}"
              f"  preconditions {v['p80']['preconditions']}  without P1 {v['p80']['largest_level_inside_slo_without_p1']}  null {v['p80']['null_levels']}")
