#!/usr/bin/env python3
"""Vol.2 · P80 · G6 (six concurrency sweeps) and G5 (Nemotron Nano 9B v2 on vLLM 0.30.0) again, in one clean night, with
the gates P79 found missing. The P78 pre-registrations (prediction_p78_clean_rerun.json, prediction_p78_n2_upstream.json)
stay in force unchanged; the new gates and their references are in prediction_p80_gates.json.

What is reused unchanged (imported, not copied): p78_clean_rerun.SWEEPS (image, env, profile and levels of each sweep) and
its level-duration rule; p78_n2_upstream's ladder, levels, context depths, filler and request function; p53_concurrency_v2's
AIPerf command, level runner and calibration; p50_footprint's container start; G8 (tools/g8_gate.py) before every cell with
its wait and its "a cell whose G8 did not pass is null" rule; the host record; the no-overwrite check.

Added (P80):
  sentinel (G9)  per group, after the warm-up level: a 30 s long-input c=1 probe (TTFT p50) and a 30 s short-input probe at
                 the group's reference level (ITL p50), each <= 2 x the reference (prediction_p80_gates.json, file:line).
                 Fail -> the container is restarted once and probed again; fail again -> the group is null.
                 G5 has no reference (a new engine): its probes are recorded, not judged.
  arm health     before and after every cell: c=1 for 10 s (streamed requests, generation rate median). after / before < 0.8 ->
                 the cell is marked, the container restarted, the cell run once more; still < 0.8 -> the cell is null.
                 Not applied to a cell whose engine died (A1's ceiling at 32 is an engine exit).
  records        nvidia-smi every 500 ms for each container's whole life (paused for each 10 s G8 sample: the logger lifts
                 the idle utilization reading over G8's line, P79), the container's system-memory share, the desktop
                 compositor's commitment and the WSL make_resident count before and after every cell, the Windows GPU
                 counters every 10 s (reduced as p80_postrun.reduce_map: no desktop process names are written). Record only.
  time gate      no new group or cell once the stop time is reached (--stop HH:MM, default 08:00; an extension is a new
                 --stop value, written into run_start with --stop-reason).
  test only     --sentinel-scale X multiplies every sentinel reference by X (refused without --test): the path "sentinel fails,
                 restart, fails again, group null, next group" is exercised with the real command line plus this flag.
usage: p80_rerun.py --aiperf EXE --tokenizer-root DIR [--groups s256_C,...,G5] [--stop HH:MM] [--stop-reason TEXT] [--out DIR] [--test [--sentinel-scale X]]
env: NGC_ENV_FILE (--env-file, never read) · NIM_CACHE_DIR · V_CACHE_DIR
"""
import argparse, json, os, statistics as st, subprocess, sys, threading, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
import p53_concurrency_v2 as C2  # noqa: E402
import p78_clean_rerun as RR  # noqa: E402
import p78_n2_upstream as N2U  # noqa: E402
import p78_engines as E  # noqa: E402
import p78_quality as Q  # noqa: E402
import p78_nim_vs_vllm as G4  # noqa: E402
import g8_gate as G  # noqa: E402
import host_gate as HG  # noqa: E402
import overwrite_gate as O  # noqa: E402
import container_sentinel as CS  # noqa: E402
from p80_postrun import reduce_map  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_OUT = os.path.join(HERE, "..", "results", "p80_rerun")
GROUPS = ["s256_C", "s256_R", "v2_A2_C", "v2_A2_R", "v2_A1_C", "v2_A1_R", "G5"]
P55 = "vol2-nemotron/results/p55_concurrency_a2_256/levels.jsonl"
P53 = "vol2-nemotron/results/p53_concurrency_v2/levels.jsonl"
# sentinel references: the measured (not warm-up) rows of the original main sweeps, file and line
SENTINEL = {
    "s256": {"R1": (157.66, P55 + " line 16"), "short_c": 128, "ITL": (30.7, P55 + " line 9")},
    "v2_A2": {"R1": (144.06, P53 + " line 36"), "short_c": 32, "ITL": (19.4, P53 + " line 30")},
    "v2_A1": {"R1": (318.93, P53 + " line 13"), "short_c": 16, "ITL": (19.69, P53 + " line 6")},
}
HEALTH_PROMPT = "Write a detailed explanation of how a refrigerator moves heat, in about 350 words."
HEALTH_MIN_RATIO = 0.8
SMI_QUERY = "timestamp,clocks.sm,clocks.mem,clocks_throttle_reasons.active,power.draw,utilization.gpu,memory.used"


class Smi:
    """nvidia-smi every 500 ms into one CSV per container; paused around each G8 sample."""
    def __init__(self, path):
        self.path = path; self.p = None; self.f = None

    def resume(self):
        if self.p is None:
            self.f = open(self.path, "a", encoding="utf-8", newline="\n")
            self.p = subprocess.Popen(["nvidia-smi", f"--query-gpu={SMI_QUERY}", "--format=csv,noheader", "-lms", "500"], stdout=self.f, stderr=subprocess.STDOUT)

    def pause(self):
        if self.p is not None:
            self.p.terminate(); self.p.wait(timeout=30); self.f.close(); self.p = None


class Sampler(threading.Thread):
    """The Windows GPU counters every 10 s, reduced (no desktop process names), until stopped."""
    def __init__(self, path):
        super().__init__(daemon=True); self.path = path; self.stop_ev = threading.Event()

    def run(self):
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            while not self.stop_ev.is_set():
                try:
                    f.write(json.dumps({"at": now(), "gib": reduce_map(CS.windows_gpu_memory())}) + "\n"); f.flush()
                except Exception as e:  # noqa: BLE001
                    f.write(json.dumps({"at": now(), "error": str(e)[:200]}) + "\n"); f.flush()
                self.stop_ev.wait(10)


def state():
    """The record-only signals (P79): container system-memory share, compositor commitment, make_resident count."""
    s = CS.snapshot()
    return {k: s[k] for k in ("container_sysmem_gib", "container_dedicated_gib", "make_resident_failures", "wsl_vm_uptime_s")} | {"windows": reduce_map(s["windows"])}


def arm_health(model, seconds):
    """c=1 for `seconds`: streamed requests (p78_n2_upstream.one), generation-rate median."""
    rates, t0 = [], time.time()
    while time.time() - t0 < seconds:
        r = N2U.one(model, HEALTH_PROMPT, 400)
        if r.get("gen_rate"):
            rates.append(r["gen_rate"])
        elif r.get("error") or r.get("http_status") != 200:
            break
    return {"rates": rates, "rate_median": st.median(rates) if rates else None, "seconds": round(time.time() - t0, 1)}


def originals():
    """Original total tok/s per (sweep label, level) from the main sweeps the P78 G6 pre-registration names."""
    out = {}
    for path, labels in ((P55, ("s256_C", "s256_R")), (P53, ("v2_A2_C", "v2_A2_R", "v2_A1_C", "v2_A1_R"))):
        for l in open(os.path.join(REPO, path), encoding="utf-8"):
            e = json.loads(l)
            if e.get("warmup") or e.get("container") != "main" or not e.get("summary"):
                continue
            for lab in labels:
                s = RR.SWEEPS[lab]
                if s["arm"] == e.get("arm") and s["profile"] == e.get("profile"):
                    out[(lab, e["concurrency"])] = (e["summary"].get("output_token_throughput") or {}).get("avg")
    return out


class Run:
    def __init__(self, a):
        self.a = a; self.out = a.out; self.logdir = os.path.join(a.out, "logs"); os.makedirs(self.logdir, exist_ok=True)
        self.ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
        self.lv = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
        O.SCOPES = O.SCOPES + sorted(d for d in os.listdir(REPO) if d.startswith("vol") and d not in O.SCOPES)
        self.snap = O.snapshot(REPO, [os.path.relpath(a.out.split(os.sep + "harness_test")[0], REPO).replace(os.sep, "/")])
        self.smi = None; self.name = None; self.aiperf_orig = C2.aiperf_cmd

    def event(self, **kw):
        self.ev.write(json.dumps({**kw, "at": now()}, ensure_ascii=False) + "\n"); self.ev.flush()

    def open_gate(self):
        return CS.time_gate(self.a.stop)

    def g8(self, **tag):
        if self.smi:
            self.smi.pause()
        g = G.gate(max_wait_s=120 if self.a.test else G.MAX_WAIT_S)
        if self.smi:
            self.smi.resume()
        self.event(kind="g8", **tag, **g)
        return g

    def ow(self, **tag):
        ov = O.check(self.snap); self.event(kind="overwrite_check", **tag, **ov)
        return ov["pass"]

    # ------------------------------------------------------------------ containers
    def up(self, label, attempt, launch):
        """Start a container with `launch(name)` -> start dict; the smi log and the birth record around it."""
        self.name = f"p80-{label.lower().replace('_', '-')}-{attempt}"
        self.smi = Smi(os.path.join(self.out, f"smi_{self.name}.csv")); self.smi.resume()
        before = state(); st_ = launch(self.name); after = state()
        birth = CS._judge_birth({**before, "other_dedicated_gib": 0.0}, {**after, "other_dedicated_gib": 0.0})
        self.event(kind="container_start", group=label, attempt=attempt, name=self.name, ready=st_.get("ready"), reason=st_.get("reason"),
                   env=st_.get("env"), args=st_.get("args"), traps=st_.get("traps"), seconds=st_.get("seconds_to_ready") or st_.get("seconds_to_verdict"),
                   birth_record_only={"flag": not birth["pass"], "reasons": birth["reasons"]}, state_before=before, state_after=after, gpu=gpu())
        return st_

    def down(self, save=C2.save_logs, stopper=stop):
        if self.name:
            save(self.name, self.logdir); stopper(self.name)
            self.event(kind="container_end", name=self.name, gpu_after_stop=gpu(), state=state())
        if self.smi:
            self.smi.pause()
        self.name = None; self.smi = None

    # ------------------------------------------------------------------ one cell with arm health
    def cell(self, label, arm, prof, model, n, dur, art, restart, extra):
        g = self.g8(group=label, concurrency=n)
        if not g["pass"]:
            self.event(kind="level_null", group=label, concurrency=n, reason="G8 did not pass within the wait limit"); return None
        hsecs = 3 if self.a.test else 10
        for attempt in (1, 2):
            hb = arm_health(model, hsecs); s0 = state(); hg = HG.cell_start()
            rec = C2.run_level(self.a, model, arm, prof, n, dur, art + ("" if attempt == 1 else "_rerun"), "main", self.lv,
                               {"group": label, "cell_attempt": attempt, "g8_waited_s": g["waited_s"], **extra})
            host = HG.cell_end(hg); s1 = state()
            if rec["engine_dead"]:
                self.event(kind="cell_end", group=label, concurrency=n, cell_attempt=attempt, engine_dead=True, health_before=hb, state_before=s0, state_after=s1, host=host)
                return rec
            ha = arm_health(model, hsecs)
            ratio = (ha["rate_median"] / hb["rate_median"]) if ha["rate_median"] and hb["rate_median"] else None
            self.event(kind="cell_end", group=label, concurrency=n, cell_attempt=attempt, engine_dead=False, health_before=hb, health_after=ha,
                       health_ratio=round(ratio, 3) if ratio else None, watch=CS.watch({**s0, "other_dedicated_gib": 0.0}, {**s1, "other_dedicated_gib": 0.0}),
                       state_before=s0, state_after=s1, host=host)
            if not self.ow(group=label, concurrency=n):
                raise SystemExit(4)
            if ratio is not None and ratio >= HEALTH_MIN_RATIO:
                return rec
            self.event(kind="cell_marked" if attempt == 1 else "level_null", group=label, concurrency=n, health_ratio=ratio,
                       reason=f"arm health after / before < {HEALTH_MIN_RATIO}" + ("; container restarted, cell run again" if attempt == 1 else " again"))
            if attempt == 1:
                model = restart()
                if model is None:
                    return None
        return None

    # ------------------------------------------------------------------ sentinel
    def sentinel(self, label, arm, model, ref, art):
        r = C2.run_level(self.a, model, arm, "R", 1, 10 if self.a.test else 30, os.path.join(art, "R_c0001"), "main", self.lv, {"group": label, "sentinel": True})
        c = (ref or {}).get("short_c", 16)
        s = C2.run_level(self.a, model, arm, "C", c, 10 if self.a.test else 30, os.path.join(art, f"C_c{c:04d}"), "main", self.lv, {"group": label, "sentinel": True})
        v1 = ((r.get("summary") or {}).get("time_to_first_token") or {}).get("p50")
        v2 = ((s.get("summary") or {}).get("inter_token_latency") or {}).get("p50")
        if ref is None:
            out = {"judged": False, "reason": "no reference for this configuration (a new engine)", "R1_ttft_p50_ms": v1, f"C{c}_itl_p50_ms": v2, "pass": True}
        else:
            a1 = CS.speed_check(v1, ref["R1"][0], what="R c=1 TTFT p50 ms", source=ref["R1"][1])
            a2 = CS.speed_check(v2, ref["ITL"][0], what=f"C c={c} ITL p50 ms", source=ref["ITL"][1])
            out = {"judged": True, "R1": a1, "short": a2, "pass": a1["pass"] and a2["pass"]}
        self.event(kind="sentinel", group=label, **out)
        return out["pass"]

    # ------------------------------------------------------------------ G6 sweep
    def g6(self, label):
        s = RR.SWEEPS[label]; arm, prof = s["arm"], s["profile"]
        levels = s["levels"][:1] if self.a.test else s["levels"]
        ref = SENTINEL[label.rsplit("_", 1)[0]]
        if self.a.sentinel_scale != 1.0:
            k = self.a.sentinel_scale
            ref = dict(ref, R1=(ref["R1"][0] * k, ref["R1"][1] + f" x {k} (test)"), ITL=(ref["ITL"][0] * k, ref["ITL"][1] + f" x {k} (test)"))
        ARMS[arm] = dict(ARMS[arm], env=s["env"])
        C2.aiperf_cmd = self.aiperf_orig

        def boot(attempt):
            st_ = self.up(label, attempt, lambda nm: start(arm, nm, None, self.logdir))
            if not st_["ready"]:
                self.down(); return None
            time.sleep(5)
            model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
            requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 16, "stream": False}, timeout=120)
            warm = C2.run_level(self.a, model, arm, prof, 1, 20 if self.a.test else 120, os.path.join(self.out, label, f"{arm}_{prof}_main", f"warmup_{attempt}", "c0001"), "main", self.lv,
                                {"warmup": True, "group": label, "container_attempt": attempt})
            if warm["engine_dead"]:
                self.down(); return None
            self.event(kind="calibration", group=label, attempt=attempt, calibration=C2.calibrate(model, prof), cache_config=metrics_cache_config())
            return model

        model = None
        for attempt in (1, 2):
            model = boot(attempt)
            if model is None:
                self.event(kind="container_failed", group=label, attempt=attempt); continue
            if self.sentinel(label, arm, model, ref, os.path.join(self.out, label, f"sentinel_{attempt}")):
                break
            self.down(); model = None
        if model is None:
            self.event(kind="group_null", group=label, reason="sentinel did not pass after one restart (or the container did not start)"); return
        restarts = [0]

        def restart():
            self.down(); restarts[0] += 1
            return boot(10 + restarts[0])

        prev = None
        for n in levels:
            if not self.open_gate():
                self.event(kind="level_not_started", group=label, concurrency=n, reason=f"stop time {self.a.stop} reached"); break
            dur = (20 if self.a.test else 60) if prev is None else int(min(600, max(60, 4 * (prev["request_latency_p99_ms"] / 1000 * n / prev["concurrency"]))))
            rec = self.cell(label, arm, prof, model, n, dur, os.path.join(self.out, label, f"{arm}_{prof}_main", f"c{n:04d}"), restart, {"sweep": label})
            if rec is None:
                continue
            if rec["engine_dead"]:
                self.lv.write(json.dumps({"sweep": label, "arm": arm, "profile": prof, "skipped_levels": levels[levels.index(n) + 1:], "reason": f"engine dead after c={n}", "at": now()}) + "\n"); self.lv.flush()
                break
            prev = rec if rec.get("request_latency_p99_ms") else prev
        self.down()

    # ------------------------------------------------------------------ G5 (p78_n2_upstream's steps, gated)
    def g5(self):
        a = self.a; label = "G5"
        tok = os.path.join(a.tokenizer_root, "a1")
        C2.aiperf_cmd = lambda a_, model, arm, prof, n, dur, art: [
            a.aiperf, "profile", "-m", model, "--endpoint-type", "chat", "--streaming", "-u", E.BASE,
            "--tokenizer", tok, *C2.PROFILE_ARGS[prof], "--extra-inputs", "temperature:0",
            "--concurrency", str(n), "--warmup-request-count", str(n), "--benchmark-duration", str(dur),
            "--benchmark-grace-period", "0", "--use-server-token-count", "--no-gpu-telemetry", "--ui-type", "none",
            "--random-seed", str(20260921 + n), "--artifact-dir", art]
        self.event(kind="g5_image", image=E.IMAGES["V2N"]["image"],
                   image_id=E.sh(["docker", "image", "inspect", E.IMAGES["V2N"]["image"], "--format", "{{.Id}} {{json .RepoDigests}}"], 30).stdout.strip())
        model = None; flags = None
        for k, args in enumerate(N2U.LADDER):
            st_ = self.up(label, k, lambda nm: E.launch("V2N", nm, self.logdir, args=args))
            pr = None
            if st_["ready"]:
                time.sleep(5); model = E.served_model(); pr = N2U.one(model, "What is 2 + 2? Answer with one number.", 16)
            self.event(kind="attempt", step=k, flags=args, ready=st_["ready"], probe=pr, traps=st_.get("traps"), first_error_line=st_.get("first_error_line"), reason=st_.get("reason"))
            if st_["ready"] and pr and pr.get("http_status") == 200:
                flags = args; break
            self.down(save=E.save_logs, stopper=E.stop); model = None
        if model is None:
            self.event(kind="arm_null", group=label, reason="no ladder step started and served"); return
        health = Q.warm_and_health("V2N", model); self.event(kind="health", group=label, **health)
        if not health["pass"]:
            self.down(save=E.save_logs, stopper=E.stop); return
        self.sentinel(label, "V2N", model, None, os.path.join(self.out, "V2N_C", "sentinel"))

        def restart():
            self.down(save=E.save_logs, stopper=E.stop)
            st_ = self.up(label, 20, lambda nm: E.launch("V2N", nm, self.logdir, args=flags))
            if not st_["ready"]:
                return None
            time.sleep(5); m = E.served_model(); Q.warm_and_health("V2N", m)
            return m

        if self.open_gate():
            g = self.g8(group=label, cell="single")
            if g["pass"]:
                qs = G4.questions(a.test)[:10]
                rows = [dict(N2U.one(model, q["text"], 500), question_id=q["id"]) for q in qs]
                self.event(kind="single", rows=rows, gen_rate_median=st.median([r["gen_rate"] for r in rows if r.get("gen_rate")]) if any(r.get("gen_rate") for r in rows) else None)
        warm = C2.run_level(a, model, "V2N", "C", 1, 20 if a.test else 120, os.path.join(self.out, "V2N_C", "warmup", "c0001"), "main", self.lv, {"warmup": True, "group": label})
        for n in ([16] if a.test else N2U.LEVELS):
            if warm.get("engine_dead") or not self.open_gate():
                self.event(kind="level_not_started", group=label, concurrency=n, reason="engine dead" if warm.get("engine_dead") else f"stop time {a.stop} reached"); break
            rec = self.cell(label, "V2N", "C", model, n, 20 if a.test else 60, os.path.join(self.out, "V2N_C", f"c{n:04d}"), restart, {})
            if rec is not None and rec["engine_dead"]:
                self.event(kind="engine_exit", group=label, concurrency=n, log_tail=E.save_logs(self.name, self.logdir)[-1500:]); break
        if self.name and E.alive(model):
            for lab, depth in N2U.DEPTHS.items():
                if not self.open_gate():
                    self.event(kind="context_not_started", depth=lab, reason=f"stop time {a.stop} reached"); break
                g = self.g8(group=label, cell=f"context_{lab}")
                if not g["pass"]:
                    continue
                body = lambda tag: f"[{tag}] " + " ".join([N2U.FILLER] * int(depth / 10.7)) + "\nDescribe this text and what a reader would notice about it, in about 200 words."  # noqa: E731
                N2U.one(model, body(f"discard-{lab}"), 256)
                rows = [N2U.one(model, body(f"{lab}-{i}"), 256) for i in range(1 if a.test else 3)]
                self.event(kind="context", depth=lab, rows=rows)
            self.ow(group=label)
        self.down(save=E.save_logs, stopper=E.stop)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer-root", required=True); ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--groups", default=",".join(GROUPS)); ap.add_argument("--stop", default="08:00"); ap.add_argument("--stop-reason", default="")
    ap.add_argument("--test", action="store_true"); ap.add_argument("--sentinel-scale", type=float, default=1.0)
    a = ap.parse_args(); a.out = os.path.abspath(a.out)
    if a.sentinel_scale != 1.0 and not a.test:
        sys.exit("refused: --sentinel-scale is for --test runs only")
    os.makedirs(a.out, exist_ok=True)
    R = Run(a)
    boot = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('s')"], capture_output=True, text=True, encoding="mbcs", errors="replace").stdout.strip()
    tasks = subprocess.run(["tasklist"], capture_output=True, text=True, encoding="mbcs", errors="replace").stdout.lower()
    running = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=30).stdout.split()
    sw = Sampler(os.path.join(a.out, "windows_gpu_memory_public.jsonl")); sw.start()
    R.event(kind="run_start", groups=a.groups, test=a.test, sentinel_scale=a.sentinel_scale, stop=a.stop, stop_reason=a.stop_reason, windows_boot=boot, steam_lines=tasks.count("steam"),
            containers_running=len(running), other_lane_containers=sum(1 for n in running if n.startswith("d3")), host_calibration=HG.calibrate(), state=state())
    if running:
        R.event(kind="refused", reason="a container is running"); return 3
    orig = originals()
    R.event(kind="originals", tok_s={f"{k[0]}|{k[1]}": v for k, v in sorted(orig.items())})
    for label in a.groups.split(","):
        if not R.open_gate():
            R.event(kind="group_not_started", group=label, reason=f"stop time {a.stop} reached"); continue
        R.event(kind="group_start", group=label)
        try:
            R.g5() if label == "G5" else R.g6(label)
        finally:
            if R.name:
                R.down()
        R.event(kind="group_end", group=label)
    sw.stop_ev.set(); sw.join(timeout=30)
    R.event(kind="run_end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
