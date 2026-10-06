#!/usr/bin/env python3
"""Vol.3 · two follow-up arms of the judge study, run with the study's unchanged programs against another server:

  J2P       Nemotron 3 Nano on NIM 2.0.12 (NVFP4), reasoning on, through the NeMo Guardrails self-check action, as the
            study's arm J2 — with one change on the server: NIM_PASSTHROUGH_ARGS="--reasoning-parser nemotron_v3".
            The study found that without the parser the rail blocks every item; the follow-up of 2026-10-03 showed on
            100 items that the parser repairs it. This arm runs the whole of both tracks with the parser.
  J6-v010   Llama 3.1 Nemotron Safety Guard 8B v3 on upstream vLLM 0.10.0, asked as the study's arm J6. The model's NIM
            (1.14.0) reports an engine built from vLLM 0.10.0 and gave about a fifth fewer verdicts per second than
            upstream vLLM 0.20.2; this arm separates the engine version from the rest of the NIM.

Every cell is `p93_judge.py --arm J2` or `--arm J6` (the request shape) with P93_RESULTS / P93_BUCKET pointed at a
small folder outside the repository: copies of the study's item table and subsets (compared by SHA-256) and a directory
link named after the request shape that points at results/parser_and_engine_version/<arm>/.

Steps (in the order of the pre-registration's plan):
  parser_main       J2P: per track precheck, c=1 on the 200-item subset, c=16 on the whole track
  parser_stability  J2P in a new container: per track precheck, the stability subset again
  v010_main         J6-v010: per track precheck, c=1, c=16
  summary           no container: each arm's summary by the study's analysis program, for J2P how often the rail's
                    decision and the verdict of the same call differ (by class and item id), and one table
One container on the card at a time; the idle-card gate before every start and every cell; every step is written to
events.jsonl as it happens. Containers are named vol3fu_<step>. The NGC key file is passed by path and never read.

env: NGC_ENV_FILE · NIM_CACHE_DIR · P93_HF_HUB · VOL3_FOLLOWUP_BUCKET (folder outside the repository)
usage: parser_and_engine_version_run.py --prediction FILE --gr-py PY [--steps a,b,...] [--stop-at HH:MM] [--dry-run]
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
from p93_common import BUCKET as P93_BUCKET, CONTEXT, HF_SG8, NIM_N3, RESULTS as P93_RESULTS, VOL, gpu, now, percentile, read_jsonl, sh, sha256_file  # noqa: E402
from p93_run import docker_logs, gate_until, image_ok, scrub, warm_up  # noqa: E402
import p102_run  # noqa: E402
import g8_gate  # noqa: E402

RESULTS = os.environ.get("VOL3_FOLLOWUP_RESULTS") or os.path.join(VOL, "results", "parser_and_engine_version")
BUCKET = os.environ.get("VOL3_FOLLOWUP_BUCKET") or os.path.join(os.path.dirname(VOL), "_internal", "parser_and_engine_version_bucket")
P93_PRED = os.path.join(P93_RESULTS, "prediction_p93.json")
ORDER = ["parser_main", "parser_stability", "v010_main", "summary"]
SHAPE = {"J2P": "J2", "J6-v010": "J6"}
CELL_TIMEOUT_S = 1800
EV = None


def event(**k):
    k = {"at": now(), **k}
    EV.write(json.dumps(k, ensure_ascii=False) + "\n"); EV.flush()
    print(json.dumps({x: k[x] for x in k if x in ("at", "kind", "step", "arm", "track", "mode", "pass", "rc", "reason", "ready", "seconds")}), flush=True)
    return k


def link_dir(target, link):
    if os.path.lexists(link):
        return
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(os.path.abspath(target), os.path.abspath(link))
    else:
        os.symlink(os.path.abspath(target), link, target_is_directory=True)


def view(arm):
    """-> (results view, bucket) of one arm, both outside the repository; the arm's result files go to RESULTS/<arm>/."""
    arm_dir = os.path.join(RESULTS, arm); os.makedirs(arm_dir, exist_ok=True)
    v = os.path.join(BUCKET, "views", arm); b = os.path.join(BUCKET, "bucket_" + arm)
    os.makedirs(v, exist_ok=True); os.makedirs(b, exist_ok=True)
    for name, src_dir, dst_dir in (("items.jsonl", P93_RESULTS, v), ("subsets.json", P93_RESULTS, v), ("items_text.jsonl", P93_BUCKET, b)):
        src, dst = os.path.join(src_dir, name), os.path.join(dst_dir, name)
        if not os.path.isfile(dst):
            shutil.copyfile(src, dst)
        if sha256_file(src) != sha256_file(dst):
            sys.exit(f"refused: {name} in the view of {arm} is not the study's file")
    link_dir(arm_dir, os.path.join(v, SHAPE[arm]))
    probe = os.path.join(v, SHAPE[arm], ".link_probe"); open(probe, "w").close()
    ok = os.path.isfile(os.path.join(arm_dir, ".link_probe")); os.remove(probe)
    if not ok:
        sys.exit(f"refused: the directory link of {arm} does not point at its results folder")
    return v, b


def card_template():
    snap = os.path.join(os.environ["P93_HF_HUB"], "models--" + HF_SG8["repo"].replace("/", "--"), "snapshots", HF_SG8["revision"])
    return os.path.join(snap, "inference_script.py"), snap


def run_study_program(program, arm, gr_py, *args):
    v, b = view(arm)
    cmd = [sys.executable, os.path.join(HERE, program), *args, "--arm", SHAPE[arm]]
    if program == "p93_judge.py":
        cmd += ["--prediction", P93_PRED, "--gr-py", gr_py, "--sg8-template", card_template()[0]]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=dict(os.environ, P93_RESULTS=v, P93_BUCKET=b), timeout=CELL_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 124, {"note": f"no end within {CELL_TIMEOUT_S} s"}
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        d = json.loads(line)
    except ValueError:
        d = {"note": "no JSON line from the program", "stdout_tail": line[:200], "stderr_tail": (r.stderr or "").strip()[-300:]}
    return r.returncode, d


def vllm_command(name, image):
    """The study's upstream-vLLM start (p102_run.vllm_command) with another image."""
    cmd, shown, snap = p102_run.vllm_command(name, HF_SG8)
    old = p102_run.VLLM["image"]
    if cmd.count(old) != 1 or shown.count(old) != 1:
        sys.exit("the study's vLLM command does not name its image exactly once")
    return [image if x == old else x for x in cmd], [image if x == old else x for x in shown], snap


def card_state():
    s = g8_gate.sample()
    mine = sh(["docker", "ps", "-a", "--filter", "name=vol3fu_", "--format", "{{.Names}}"], timeout=60).stdout.split()
    running = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    return {"gpu": gpu(), "ten_second_sample": {k: s[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")}, "vol3fu_containers_left": mine, "containers_running": len(running)}


def cells_of(a, step, name, arm, modes, tag, deadline):
    for track in ("input", "output"):
        rc, d = run_study_program("p93_judge.py", arm, a.gr_py, "precheck", "--track", track, *(["--tag", tag] if tag else []))
        event(kind="precheck", step=step, arm=arm, track=track, rc=rc, **{"pass": rc == 0}, result=d)
        if rc != 0:
            event(kind="arm_track_null", step=step, arm=arm, track=track, reason="precheck failed"); continue
        for mode in modes:
            if time.time() > deadline:
                return f"time limit reached before {arm}/{track}/{mode}"
            ok, g = gate_until(deadline)
            event(kind="g8", step=step, arm=arm, track=track, mode=mode, before="cell", **{"pass": ok}, gate=g)
            if not ok:
                return f"the idle-card gate did not pass before {arm}/{track}/{mode}"
            rc, d = run_study_program("p93_judge.py", arm, a.gr_py, "cell", "--track", track, "--mode", mode)
            after = g8_gate.sample()
            event(kind="cell", step=step, arm=arm, track=track, mode=mode, rc=rc, result=d, gpu_after={k: after[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")},
                  container_alive=bool(sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=60).stdout.strip()))
    return None


def same_call(rail, verdict, status):
    r = "block" if str(rail).startswith("block") else "allow" if str(rail).startswith("allow") else "raise" if str(rail).startswith("raise") else "other"
    if verdict in ("safe", "unsafe"):
        return "agree" if r in ("block", "allow") and (r == "block") == (verdict == "unsafe") else f"{r}_but_verdict_{verdict}"
    return f"{r}_and_no_verdict_{status}"


def rail_beside_verdict(arm):
    """J2P: per track, each item of the whole-track cell classed by its own rail decision and its own verdict."""
    out = {}
    for track in ("input", "output"):
        p = os.path.join(RESULTS, arm, f"{track}_c16.jsonl")
        if not os.path.isfile(p):
            continue
        rows = read_jsonl(p); classes = {}
        for r in rows:
            c = same_call(r.get("rail"), r.get("verdict"), r.get("status")); classes[c] = classes.get(c, 0) + 1
        differ = sorted([{"item_id": r["item_id"], "class": same_call(r.get("rail"), r.get("verdict"), r.get("status")), "finish_reason": r.get("finish_reason"),
                          "completion_tokens": r.get("completion_tokens")} for r in rows if same_call(r.get("rail"), r.get("verdict"), r.get("status")) != "agree"], key=lambda x: x["item_id"])
        out[track] = {"file": os.path.basename(p), "sha256": sha256_file(p), "items": len(rows), "classes": classes, "agree": classes.get("agree", 0),
                      "share_that_differ": (len(differ) / len(rows)) if rows else None, "items_that_differ": differ}
    return out


def line(name, path, track, group):
    if not os.path.isfile(path):
        return None
    S = json.load(open(path, encoding="utf-8")); T = S["tracks"].get(track, {})
    if not T.get("usable"):
        return {"arm": name, "track": track, "usable": False, "why_not": T.get("why_not")}
    q = T["quality"][group]; qc = T["quality_cell"]; c1 = T.get("c1") or {}
    o = {"arm": name, "track": track, "group": group, "usable": True, "detection": q["detection"], "false_alarm": q["false_alarm"], "f1_unsafe": q["f1_unsafe_over_items_with_verdict"],
         "no_verdict": q["no_verdict"], "c1_latency_ms_p50": (c1.get("latency_ms") or {}).get("p50"), "c16_verdicts_per_s": qc.get("verdicts_per_s"), "c16_latency_ms_p99": qc["latency_ms"]["p99"],
         "completion_tokens_p50": qc["completion_tokens"]["p50"], "stability": (T.get("stability") or {}).get("rate")}
    if "rail" in q:
        o["rail"] = q["rail"]
    return o


def pct(r):
    return "—" if not r or r.get("rate") is None else f"{100 * r['rate']:.1f}% ({r['k']}/{r['n']})"


def num(x, f="{:.1f}"):
    return "—" if x is None else f.format(x)


def summary(a):
    out = {}
    for arm in SHAPE:
        if os.path.isfile(os.path.join(RESULTS, arm, "cells.jsonl")):
            rc, d = run_study_program("p93_analyze.py", arm, a.gr_py)
            if rc != 0:
                sys.exit(f"{arm}: the analysis program ended with {rc}: {d}")
            p = os.path.join(RESULTS, arm, "summary.json"); S = json.load(open(p, encoding="utf-8")); S["arm_of_this_folder"] = arm; S["request_shape_of"] = SHAPE[arm]
            json.dump(S, open(p, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False); out[arm] = True
    if out.get("J2P"):
        json.dump(rail_beside_verdict("J2P"), open(os.path.join(RESULTS, "J2P", "rail_beside_verdict.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    sg = os.path.join(VOL, "results", "safety_guard_nim")
    arms = [("J2 (the study, no parser on the server)", os.path.join(P93_RESULTS, "J2", "summary.json")), ("J2P (the same with the reasoning parser)", os.path.join(RESULTS, "J2P", "summary.json")),
            ("J6-today (upstream vLLM 0.20.2)", os.path.join(sg, "J6-today", "summary.json")), ("J6-v010 (upstream vLLM 0.10.0)", os.path.join(RESULTS, "J6-v010", "summary.json")),
            ("J6N (NIM 1.14.0, generic profile)", os.path.join(sg, "J6N", "summary.json"))]
    rows = [x for n, p in arms for t, g in (("input", "aegis2"), ("input", "xstest"), ("output", "aegis2")) for x in [line(n, p, t, g)] if x]
    json.dump({"what": "one line per arm, track and data set; every line is built from that arm's summary.json only", "rows": rows}, open(os.path.join(RESULTS, "table.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    md = ["| Arm | Track · data | Detection | False alarm | Rail blocks harmful · harmless | F1 | No verdict | c=1 p50 ms | c=16 verdicts/s | c=16 p99 ms | Stability |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r["usable"]:
            md.append(f"| {r['arm']} | {r['track']} | not usable: {r['why_not']} | | | | | | | | |"); continue
        nv = r["no_verdict"]; rail = r.get("rail")
        md.append(f"| {r['arm']} | {r['track']} · {r['group']} | {pct(r['detection'])} | {pct(r['false_alarm'])} | " + (f"{pct(rail['block_on_harmful'])} · {pct(rail['block_on_harmless'])}" if rail else "—") +
                  f" | {num(r['f1_unsafe'], '{:.3f}')} | {nv['unreadable'] + nv['truncated'] + nv['error']} | {num(r['c1_latency_ms_p50'])} | {num(r['c16_verdicts_per_s'])} | {num(r['c16_latency_ms_p99'])} | "
                  f"{num(None if r['stability'] is None else 100 * r['stability'], '{:.1f}%')} |")
    open(os.path.join(RESULTS, "table.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


def main():
    global EV
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prediction", required=True); ap.add_argument("--gr-py", required=True); ap.add_argument("--steps", default="")
    ap.add_argument("--stop-at", default="08:00"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for v in ("NGC_ENV_FILE", "NIM_CACHE_DIR", "P93_HF_HUB"):
        if not os.environ.get(v):
            sys.exit(f"{v} is not set")
    pred = json.load(open(a.prediction, encoding="utf-8"))
    side = os.path.splitext(a.prediction)[0] + ".sha256"
    if not a.dry_run:
        if pred.get("draft"):
            sys.exit("refused: the pre-registration is a draft")
        if not os.path.isfile(side) or open(side, encoding="utf-8").read().split()[0] != sha256_file(a.prediction):
            sys.exit("refused: the pre-registration does not match its .sha256 file")
        for f, h in pred["harness_sha256"].items():
            if sha256_file(os.path.join(HERE, f)) != h:
                sys.exit(f"refused: {f} is not the file the pre-registration binds")
    want = [x for x in a.steps.split(",") if x] or pred["plan"]
    plan = [s for s in ORDER if s in want and s in pred["plan"]]
    V010 = pred["serving"]["vllm_0_10_0"]
    if a.dry_run:
        for arm in SHAPE:
            view(arm)
        print(json.dumps({"plan": plan, "views": "built and checked", "v010_image_present": image_ok(V010["image"], V010["digest"]), "n3_image_present": image_ok(NIM_N3["image"], NIM_N3["index_digest"])})); return 0
    if plan == ["summary"]:
        return summary(a)
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= t:
        stop += datetime.timedelta(days=1)
    deadline = stop.timestamp(); start = time.time()
    os.makedirs(RESULTS, exist_ok=True); logdir = os.path.join(BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    EV = open(os.path.join(RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    first = g8_gate.sample()
    event(kind="run_start", prediction_sha256=sha256_file(a.prediction), plan=plan, stop_at=a.stop_at, gpu=gpu(), other_containers_running=len(others), compute_processes_listed=first["compute_processes_listed"])
    if others:
        event(kind="run_end", reason="another container is running; nothing was started", rc=2); return 2
    stopped = None
    try:
        for step in plan:
            if step == "summary":
                continue
            if time.time() > deadline:
                stopped = f"time limit reached before {step}"; break
            name = f"vol3fu_{step}"
            if step.startswith("parser"):
                if not image_ok(NIM_N3["image"], NIM_N3["index_digest"]):
                    event(kind="step_null", step=step, reason="the local NIM image does not carry the pinned digest"); continue
                cmd, shown = p102_run.nim_command(name, NIM_N3, {"NIM_PASSTHROUGH_ARGS": p102_run.PASSTHROUGH}); group = "n3_nim"; arm = "J2P"
            else:
                if not image_ok(V010["image"], V010["digest"]):
                    event(kind="step_null", step=step, reason="the local vLLM 0.10.0 image does not carry the pinned digest"); continue
                cmd, shown, snap = vllm_command(name, V010["image"]); group = "sg8_vllm"; arm = "J6-v010"
                if not os.path.isfile(os.path.join(snap, "config.json")):
                    event(kind="step_null", step=step, reason="the model snapshot is not in the hub cache"); continue
            ok, g = gate_until(deadline)
            event(kind="g8", step=step, before="container start", **{"pass": ok}, gate=g)
            if not ok:
                stopped = f"the idle-card gate did not pass before {step}"; break
            L = p102_run.launch(name, cmd, shown, logdir)
            event(kind="container_ready", step=step, arm=arm, ready=L.get("ready"), seconds=L.get("seconds_to_verdict"), launch=L, gpu=gpu())
            if not L.get("ready"):
                event(kind="step_null", step=step, reason=L.get("reason"), first_error_line=L.get("first_error_line"), a_result_for_this_step=True)
                sh(["docker", "rm", "-f", name], timeout=120); time.sleep(10); continue
            event(kind="warm_up", step=step, versions=p102_run.server_versions(), **warm_up(group))
            stopped = cells_of(a, step, name, arm, ["stability"], "stability", deadline) if step.endswith("stability") else cells_of(a, step, name, arm, ["c1", "c16"], "", deadline)
            open(os.path.join(logdir, f"{name}.{int(time.time())}.container.log.txt"), "w", encoding="utf-8", newline="\n").write(scrub(docker_logs(name)))
            sh(["docker", "rm", "-f", name], timeout=180); time.sleep(10)
            event(kind="container_stopped", step=step, gpu=gpu())
            if stopped:
                break
    finally:
        for n in sh(["docker", "ps", "-a", "--filter", "name=vol3fu_", "--format", "{{.Names}}"], timeout=60).stdout.split():
            sh(["docker", "rm", "-f", n], timeout=180)
        time.sleep(10)
        event(kind="card_after_the_run", **card_state())
    event(kind="run_end", reason=stopped or "plan complete", rc=0 if not stopped else 5, seconds=round(time.time() - start))
    if not stopped and "summary" in plan:
        summary(a)
    return 0 if not stopped else 5


if __name__ == "__main__":
    sys.exit(main())
