#!/usr/bin/env python3
"""Vol.2 (directory of this file's parent), P69 · the P66 and P67 cells that ran with other load on the desktop GPU,
measured again in a clean window.

The re-run list is derived, not remembered: every level record of P66's and P67's levels.jsonl whose `gpu_end.util_pct`
is above 2 (a window with no other load ends at 0; tools/g8_gate.py). Each listed cell is repeated with the same arm,
server configuration (W, K), concurrency, request count and seed, through the same harness function that ran it
(p66_rails_under_load.py / p67_rails_server_config.py, imported unchanged), on one NIM container in one session:
  P66 cells: P66's server (p66_gr_server.py, one process, keep-alive 5 s); P67 cells: P67's server with their W and K.
  P66's R3 levels 1, 8, 16, 32 alternate with R1024 at the same levels (R1024 was clean in P66; it is repeated here so
  that R3 / R1024 has both terms in one window). Each server start runs its discarded warm-up level and its G2 probes.
Before every level, warm-ups included: G8 (tools/g8_gate.py). A G8 positive control runs once, while the NIM container
decodes. After every level: the no-overwrite check (tools/overwrite_gate.py), else the run stops (exit 4).
Every level has a wall-clock timeout (tools/cell_timeout.py: max(3 x the original level's duration, 300 s), at most 900 s). On
a timeout the load generator is stopped, the level is recorded `hung` with what was still in flight, the server is
started again, and the level is tried once more; a second timeout leaves it `hung` and the run goes on.
The original cells are not changed; contamination_marks.jsonl beside this run's results names them with their fingerprint.
Part D is not repeated. Paths are derived from this file's location; no volume directory name is written here.
usage: p69_clean_rerun.py --aiperf EXE --tokenizer DIR --grpy PYTHON [--out DIR] [--test] [--list-only]
env: NGC_ENV_FILE (--env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, shutil, sys, threading, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
RES = os.path.abspath(os.path.join(HERE, "..", "results"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))
import p66_rails_under_load as M  # noqa: E402
import p67_rails_server_config as Q  # noqa: E402
import g8_gate as G  # noqa: E402
import overwrite_gate as O  # noqa: E402
import cell_timeout as T  # noqa: E402
H = M.H

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_OUT = os.path.join(RES, "p69_clean_rerun")
SOURCES = {"P66": os.path.join(RES, "p66_rails_under_load", "levels.jsonl"), "P67": os.path.join(RES, "p67_rails_server_config", "levels.jsonl")}
UTIL_FLAG = 2
USER_WINDOWS = {"P66": "the user reports GPU use on the desktop (a Steam game) during P66's morning arms, 2026-09-27 before about 12:00",
                "P67": "the user reports a Steam game from about 15:00 to 16:00 on 2026-09-27, with the Steam client open until later"}


def rerun_list():
    out = []
    for run, path in SOURCES.items():
        for r in (json.loads(l) for l in open(path, encoding="utf-8")):
            ge = r.get("gpu_end") or {}
            if (ge.get("util_pct") or 0) > UTIL_FLAG:
                lab = r.get("label") or r["arm"]
                out.append({"run": run, "label": lab, "arm": r["arm"], "workers": r.get("workers"), "keep_alive_s": r.get("keep_alive_s"),
                            "concurrency": r["concurrency"], "requests": r["requests"], "seed": r["seed"], "warmup": bool(r.get("warmup")),
                            "original_start": r["start"], "gpu_end": ge})
    return out


def plan(items):
    """Server starts in order. P66: N, P, then R3 and R1024 alternating by level, then R3's 64 and 128. P67: its labels."""
    p66 = [x for x in items if x["run"] == "P66"]; p67 = [x for x in items if x["run"] == "P67"]
    lv = lambda arm: sorted({x["concurrency"] for x in p66 if x["arm"] == arm and not x["warmup"]})
    steps = [("P66", "N", None, None, lv("N")), ("P66", "P", None, None, lv("P"))]
    r3 = lv("R3")
    for n in [1, 8, 16, 32]:
        if n in r3:
            steps.append(("P66", "R3", None, None, [n])); steps.append(("P66", "R1024", None, None, [n]))
    rest = [n for n in r3 if n not in (1, 8, 16, 32)]
    if rest:
        steps.append(("P66", "R3", None, None, rest))
    labels = []
    for x in p67:
        if x["label"] not in labels:
            labels.append(x["label"])
    for lab in labels:
        xs = [x for x in p67 if x["label"] == lab]
        steps.append(("P67", xs[0]["arm"], xs[0]["workers"], xs[0]["keep_alive_s"], sorted({x["concurrency"] for x in xs if not x["warmup"]})))
    return steps


def original_durations():
    """Wall-clock seconds each original level took (end - start), keyed like the re-run list; used for the timeout."""
    import datetime as dt
    out = {}
    for run, path in SOURCES.items():
        for r in (json.loads(l) for l in open(path, encoding="utf-8")):
            try:
                d = (dt.datetime.strptime(r["end"], "%Y-%m-%dT%H:%M:%S%z") - dt.datetime.strptime(r["start"], "%Y-%m-%dT%H:%M:%S%z")).total_seconds()
            except Exception:
                continue
            out[(run, r.get("label") or r["arm"], r["concurrency"], bool(r.get("warmup")))] = d
    return out


def g8_positive_control(model):
    stop = threading.Event()
    def load():
        while not stop.is_set():
            try:
                requests.post(H.BASE["nim"] + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Write a long story about a lighthouse."}],
                                                                             "max_tokens": 400, "temperature": 0.0}, timeout=120)
            except Exception:
                pass
    ts = [threading.Thread(target=load, daemon=True) for _ in range(4)]
    for t in ts:
        t.start()
    time.sleep(3); s = G.sample(); stop.set()
    for t in ts:
        t.join(150)
    return {"what": "G8 sampled while 4 requests decode on NIM", "sample": s, "gate_passed": s["pass"], "control_fired": not s["pass"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT); ap.add_argument("--aiperf"); ap.add_argument("--tokenizer"); ap.add_argument("--grpy")
    ap.add_argument("--test", action="store_true"); ap.add_argument("--list-only", action="store_true")
    a = ap.parse_args(); a.out = os.path.abspath(a.out)
    items = rerun_list(); steps = plan(items)
    if a.test:   # one step of each kind: P66 NIM-direct, P66 rails (one process), P67 four workers, a warm-up-only start
        pick = [next(s for s in steps if s[0] == "P66" and s[1] == "N"), next(s for s in steps if s[0] == "P66" and s[1] == "R3"),
                next(s for s in steps if s[0] == "P67" and s[2] == 4 and s[4]), next((s for s in steps if s[0] == "P67" and not s[4]), None)]
        steps = [s for s in pick if s]
    if a.list_only:
        for x in items:
            print(x["run"], x["label"], x["concurrency"], "warm-up" if x["warmup"] else "", x["gpu_end"].get("util_pct"), x["original_start"])
        print("cells", len(items), {r: sum(1 for x in items if x["run"] == r) for r in SOURCES})
        for s in steps:
            print("step", s)
        return 0
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    if not os.path.exists(os.path.join(a.out, "configs")):
        shutil.copytree(os.path.join(RES, "p67_rails_server_config", "configs"), os.path.join(a.out, "configs"))
    allowed = os.path.relpath(DEFAULT_OUT, REPO).replace(os.sep, "/")
    snap = O.snapshot(REPO, [allowed])
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(logdir, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": H.now()}, ensure_ascii=False) + "\n"), ev.flush())
    with open(os.path.join(a.out, "contamination_marks.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for x in items:
            f.write(json.dumps({**{k: x[k] for k in ("run", "label", "concurrency", "warmup", "original_start", "gpu_end")},
                                "desktop_gpu_load": "suspected", "fingerprint": f"gpu_end.util_pct {x['gpu_end'].get('util_pct')} > {UTIL_FLAG}",
                                "user_report": USER_WINDOWS[x["run"]]}, ensure_ascii=False) + "\n")
    event(kind="rerun_list", cells=len(items), by_run={r: sum(1 for x in items if x["run"] == r) for r in SOURCES}, steps=[list(s) for s in steps],
          overwrite_allowed=snap["allowed"], watched=len(snap["others"]))
    if H.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    if Q.listeners(M.GR_PORT):
        sys.exit(f"refused: port {M.GR_PORT} has a listener")
    qs = json.load(open(os.path.join(REPO, "benchmark", "e3_questions.json"), encoding="utf-8"))
    shas = {cid: __import__("hashlib").sha256(open(os.path.join(a.out, "configs", cid, "config.yml"), "rb").read()).hexdigest() for cid in set(M.CONFIG.values())}
    tok = H.tokenizer(a.tokenizer)
    st_ = H.start_nim("N-BF16", "p69-nim", logdir)
    if not st_["ready"]:
        event(kind="nim_failed", reason=st_.get("reason")); H.save_logs("p69-nim", logdir); H.stop("p69-nim"); return 1
    time.sleep(5)
    model = requests.get(H.BASE["nim"] + "/v1/models", timeout=30).json()["data"][0]["id"]
    cal = H.calibrate("nim", model, "C", tok)
    rate = 1000.0 / cal["itl_ms_p50"] if cal.get("itl_ms_p50") else None
    share = rate * 16060522496 / 1792e9 if rate else None
    event(kind="nim_start", model=model, image=H.NIM_IMAGE, env=st_["env"], seconds_to_ready=st_["seconds_to_verdict"], captured_graph_sizes=st_.get("captured_graph_sizes"),
          health={"decode_rate_c1_tok_s": rate and round(rate, 2), "share_of_peak": share and round(share, 4), "gate": 0.60, "pass": bool(share and share >= 0.60)}, calibration_n_ok=cal["n_ok"])
    pc = g8_positive_control(model); event(kind="g8_positive_control", **pc)
    print(f"NIM ready · health {share and round(share, 3)} · G8 positive control fired={pc['control_fired']} ({pc['sample']['util_pct_p50']} %, {pc['sample']['power_w_p50']} W)", flush=True)
    by = {(x["run"], x["label"], x["concurrency"], x["warmup"]): x for x in items}
    expected = original_durations()

    def in_flight(ctx):
        """What is still open when a level is stopped for its timeout."""
        m = M.nim_counters()
        run_wait = {}
        try:
            t = requests.get(H.BASE["nim"] + "/metrics", timeout=10).text
            for l in t.splitlines():
                for k_ in ("vllm:num_requests_running", "vllm:num_requests_waiting"):
                    if l.startswith(k_ + "{") or l.startswith(k_ + " "):
                        run_wait[k_] = run_wait.get(k_, 0) + float(l.split()[-1])
        except Exception as e:
            run_wait = {"error": str(e)[:100]}
        tree = Q.tree(ctx["proc"].pid) if ctx.get("proc") else []
        conns = [c for c in __import__("psutil").net_connections("tcp") if c.laddr and c.laddr.port == M.GR_PORT and c.status == "ESTABLISHED"]
        return {"nim": run_wait, "nim_request_success_total": m.get("vllm:request_success"), "server_processes_alive": [q.pid for q in tree],
                "established_on_server_port": len(conns), "established_by_owner_pid": {str(pid): sum(1 for c in conns if c.pid == pid) for pid in {c.pid for c in conns}}}

    def gated(ctx, n, warm, fn, art):
        run, lab = ctx["run"], ctx["lab"]
        for attempt in (1, 2):
            g8 = G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S)
            event(kind="g8", run=run, label=lab, concurrency=n, warmup=warm, attempt=attempt, **g8)
            print(f"  [{run}] {lab} c={n}{' warm-up' if warm else ''} G8 pass={g8['pass']} waited={g8['waited_s']} s ({g8['attempts'][-1]['util_pct_p50']} %, {g8['attempts'][-1]['power_w_p50']} W)", flush=True)
            if not g8["pass"]:
                event(kind="cell_null", run=run, label=lab, concurrency=n, warmup=warm, reason="G8 did not pass within the wait limit"); return None
            exp = expected.get((run, lab, n, warm))
            tmo = T.timeout_for(exp) if not a.test else 300
            ex = {"source_run": run, "rerun_of": (by.get((run, lab, n, warm)) or {}).get("original_start"), "g8_pass": True, "g8_waited_s": g8["waited_s"],
                  "timeout_s": tmo, "expected_s": exp, "attempt": attempt, **({"warmup": True} if warm else {})}
            rec, info = T.run(lambda: fn(ctx, ex), tmo, art)
            ov = O.check(snap); event(kind="overwrite_check", run=run, label=lab, concurrency=n, warmup=warm, attempt=attempt, **ov)
            if not ov["pass"]:
                print(f"  NO-OVERWRITE GATE FAILED: {ov['violations'][:3]}", flush=True); raise SystemExit(4)
            if not info["hung"]:
                return rec
            fl = in_flight(ctx)
            event(kind="cell_hung", run=run, label=lab, concurrency=n, warmup=warm, attempt=attempt, timeout=info, in_flight=fl, final=attempt == 2)
            print(f"  HUNG {lab} c={n} attempt {attempt} after {info['elapsed_s']} s · in flight {fl}", flush=True)
            restart(ctx)
        return None

    def start(ctx):
        run, arm, w, k, lab = ctx["run"], ctx["arm"], ctx["w"], ctx["k"], ctx["lab"]
        if run == "P66":
            p, secs = (None, 0) if arm == "N" else M.gr_start(arm, a, logdir)
            if arm != "N" and p is None:
                event(kind="gr_failed", run=run, label=lab); return False
            g2 = M.g2_probe(arm, model, qs)
            ctx.update(proc=p, slog=None, info={})
            event(kind="arm_start", run=run, arm=arm, label=lab, config=M.CONFIG.get(arm), gr_seconds_to_ready=secs, gr_pid=p and p.pid, g2=g2, levels=ctx["lvls"])
        else:
            if arm == "N":
                proc, info, slog = None, {}, None; g2 = M.g2_probe(arm, model, qs)
            else:
                proc, info = Q.gr_start(arm, w, k, a, logdir)
                slog = Q.ServerLog(os.path.join(logdir, f"gr_server_{lab}.log.txt"))
                if proc is None or not info.get("all_workers_answering"):
                    event(kind="gr_failed", run=run, label=lab, info=info); Q.gr_stop(proc); return False
                g2 = Q.g2_workers(arm, model, qs, info["workers_answering"], shas[M.CONFIG[arm]])
            ctx.update(proc=proc, slog=slog, info=info)
            event(kind="server_start", run=run, label=lab, arm=arm, workers=w, keep_alive_s=k, config=M.CONFIG.get(arm), config_sha256=shas.get(M.CONFIG.get(arm)), server=info, g2=g2, levels=ctx["lvls"])
        print(f"  {run}_{lab}: g2 pass={g2['pass']} workers={ctx['info'].get('workers_answering')}", flush=True)
        return True

    def stop(ctx):
        if ctx["run"] == "P66":
            M.gr_stop(ctx.get("proc")); return {"stopped": bool(ctx.get("proc"))}
        return Q.gr_stop(ctx.get("proc"))

    def restart(ctx):
        """After a hung level: the server is cleared and started again (a new G2) before the next attempt or level."""
        event(kind="server_restart_after_hang", run=ctx["run"], label=ctx["lab"], stop=stop(ctx))
        time.sleep(5); start(ctx)

    def lvl66(ctx, ex, n, reqs_, seed, art):
        return M.level(a, ctx["arm"], model, n, reqs_, seed, art, log, ctx["proc"] and ctx["proc"].pid, dict(ex, label=ctx["lab"]))

    def lvl67(ctx, ex, n, reqs_, seed, art):
        return Q.level(a, ctx["arm"], ctx["w"], ctx["k"], model, n, reqs_, seed, art, log, ctx["proc"], ctx["slog"], ex)

    for run, arm, w, k, lvls in steps:
        lab = arm if w is None else f"{arm}_W{w}K{k}"
        tag = f"{run}_{lab}"
        print(f"##### {tag} {lvls} {H.now()}", flush=True)
        if lvls == [] and not any(x["run"] == run and x["label"] == lab and x["warmup"] for x in items):
            continue
        if a.test:
            lvls = lvls[:1]
        reqs = lambda n: 2 * n if a.test else max(10 * n, 200)
        ctx = {"run": run, "arm": arm, "w": w, "k": k, "lab": lab, "lvls": lvls}
        if not start(ctx):
            continue
        f = lvl66 if run == "P66" else lvl67
        art = os.path.join(a.out, tag, "warmup")
        gated(ctx, 8, True, lambda c, ex, art=art: f(c, ex, 8, 50 if a.test else 100, M.SEED0 + 9000, art), art)
        for n in lvls:
            art = os.path.join(a.out, tag, f"c{n:04d}")
            gated(ctx, n, False, lambda c, ex, n=n, art=art: f(c, ex, n, reqs(n), M.SEED0 + n, art), art)
        event(kind="server_end", run=run, label=lab, stop=stop(ctx))
        time.sleep(5 if a.test else 20)
    H.save_logs("p69-nim", logdir); H.stop("p69-nim")
    event(kind="nim_end", gpu_after_stop=H.gpu())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
