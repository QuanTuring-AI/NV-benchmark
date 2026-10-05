#!/usr/bin/env python3
"""P102 · the runner of the follow-up cells: one container on the card at a time, the idle-card gate before every start
and every cell, each step written to results/p102_followup/events.jsonl as it happens.

Steps, in this order (a step that is not in the pre-registration's plan is not run):
  passthrough_off   Nemotron 3 Nano NIM as in P93 (no extra argument): the 100-item check. This is the control: the rail
                    has to block all 100 again.
  passthrough_on    the same image and profile with NIM_PASSTHROUGH_ARGS="--reasoning-parser nemotron_v3". The start-up
                    log lines that mention the argument are copied into the event, whether the server starts or not.
                    A server that does not start with the argument is a result, not a failure of the run.
  lg3               Llama Guard 3 8B on the pinned upstream vLLM: per track precheck, the c=1 cell, the c=16 cell.
                    If the weights are not in the hub cache the step is recorded as "skipped - license" and nothing is run.
  n2                optional: Nemotron Nano 9B v2 NIM, per track precheck and the c=1 cell.
Before every container start and every cell: tools/g8_gate.py. After every cell one more 10 s sample.
Containers are named p102_<step>. The image that runs is checked against the pinned digest before it is started. The NGC
key file is passed by path and never read; the events file names paths by their variable, not by their value.
Time limit: --hours of wall time or --stop-at HH:MM, checked between cells. On every exit, also after an error, the
containers this runner started are removed and the card's state is written to the events file (memory in use, a 10 s
sample of utilization and power, the number of processes nvidia-smi lists, the containers still running).

env: NGC_ENV_FILE · NIM_CACHE_DIR · P93_HF_HUB
usage: p102_run.py --prediction FILE --gr-py PY [--steps passthrough_off,passthrough_on,lg3,n2] [--hours 5] [--stop-at 08:00] [--dry-run]
"""
import argparse, datetime, json, os, re, subprocess, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
from p93_common import BASE, BUCKET, CONTEXT, NIM_N3, VLLM, gpu, now, sh, sha256_file  # noqa: E402
from p93_run import docker_logs, gate_until, image_ok, scrub, warm_up  # noqa: E402
from p102_cells import RESULTS  # noqa: E402
import g8_gate  # noqa: E402

READY_TIMEOUT_S = 1800
MOUNT = "/opt/nim/.cache"
PASSTHROUGH = "--reasoning-parser nemotron_v3"
ARG_LINES = re.compile(r"passthrough|reasoning[-_ ]parser|nemotron_v3|unrecognized arguments|not allowed|denied|discard|managed by the system|invalid choice", re.I)
ORDER = ["passthrough_off", "passthrough_on", "lg3", "n2"]
EV = None


def event(**k):
    k = {"at": now(), **k}
    EV.write(json.dumps(k, ensure_ascii=False) + "\n"); EV.flush()
    print(json.dumps({x: k[x] for x in k if x in ("at", "kind", "step", "track", "mode", "pass", "rc", "reason", "ready", "seconds")}), flush=True)
    return k


def nim_command(name, serve, extra_env):
    env = {"NIM_MODEL_PROFILE": serve["profile"], **serve["env"], **extra_env} if serve.get("profile") else {**serve["env"], **extra_env}
    cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "127.0.0.1:8000:8000", "--env-file", os.environ["NGC_ENV_FILE"]]
    shown = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "127.0.0.1:8000:8000", "--env-file", "$NGC_ENV_FILE"]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]; shown += ["-e", f"{k}={v}"]
    cmd += ["-v", f"{os.environ['NIM_CACHE_DIR']}:{MOUNT}", serve["image"]]; shown += ["-v", f"$NIM_CACHE_DIR:{MOUNT}", serve["image"]]
    return cmd, shown


def vllm_command(name, hf):
    snap = os.path.join(os.environ["P93_HF_HUB"], "models--" + hf["repo"].replace("/", "--"), "snapshots", hf["revision"])
    env = {"VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1", "HF_HUB_OFFLINE": "1"}
    args = ["--model", "/model", "--served-model-name", hf["served"], "--max-model-len", str(CONTEXT), "--host", "0.0.0.0", "--port", "8000"]
    cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "127.0.0.1:8000:8000"]; shown = list(cmd)
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]; shown += ["-e", f"{k}={v}"]
    cmd += ["-v", f"{snap}:/model:ro", VLLM["image"], *args]
    shown += ["-v", f"$P93_HF_HUB/models--{hf['repo'].replace('/', '--')}/snapshots/{hf['revision']}:/model:ro", VLLM["image"], *args]
    return cmd, shown, snap


def launch(name, cmd, shown, logdir):
    sh(["docker", "rm", "-f", name], timeout=120)
    t0 = time.time(); r = sh(cmd, timeout=300)
    rec = {"name": name, "command": shown}
    if r.returncode != 0:
        rec.update({"ready": False, "reason": "docker run failed", "detail": (r.stderr or "").strip()[-300:]}); return rec
    ready, reason = False, None
    while time.time() - t0 < READY_TIMEOUT_S:
        L = docker_logs(name)
        if re.search(r"Uvicorn running|Application startup complete", L):
            try:
                if requests.get(BASE + "/v1/models", timeout=10).status_code == 200:
                    ready = True; break
            except Exception:
                pass
        if not sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=60).stdout.strip():
            reason = "container exited"; break
        time.sleep(5)
    L = scrub(docker_logs(name))
    open(os.path.join(logdir, f"{name}.{int(t0)}.startup.log.txt"), "w", encoding="utf-8", newline="\n").write(L)
    err = re.search(r"^\s*(?:\(\w+ pid=\d+\)\s*)?[\w.]*(?:Error|Exception): .*$", L, re.M)
    ver = re.findall(r"vLLM API server version (\S+)", L)
    rec.update({"ready": ready, "seconds_to_verdict": round(time.time() - t0, 1), "reason": None if ready else (reason or f"not ready within {READY_TIMEOUT_S} s"),
                "first_error_line": None if ready else (err.group(0).strip()[:300] if err else None), "vllm_version_in_log": ver[-1] if ver else None,
                "startup_log_lines_about_the_argument": [l.strip()[:400] for l in L.splitlines() if ARG_LINES.search(l)][:40]})
    return rec


def server_versions():
    out = {}
    for path in ("/version", "/v1/version", "/v1/metadata"):
        try:
            r = requests.get(BASE + path, timeout=10)
            if r.status_code == 200:
                out[path] = r.json()
        except Exception:
            pass
    return out


def cells(a, *args):
    cmd = [sys.executable, os.path.join(HERE, "p102_cells.py"), *args, "--prediction", a.prediction, "--gr-py", a.gr_py]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        d = json.loads(line)
    except ValueError:
        d = {"note": "no JSON line from the harness"}
    return r.returncode, d


def card_state():
    s = g8_gate.sample()   # on this desktop nvidia-smi lists the desktop's own processes too; their number is recorded, their names are not
    mine = sh(["docker", "ps", "-a", "--filter", "name=p102_", "--format", "{{.Names}}"], timeout=60).stdout.split()
    running = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    return {"gpu": gpu(), "ten_second_sample": {k: s[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")}, "p102_containers_left": mine, "containers_running": len(running)}


def main():
    global EV
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prediction", required=True); ap.add_argument("--gr-py", required=True); ap.add_argument("--steps", default="")
    ap.add_argument("--hours", type=float, default=5.0); ap.add_argument("--stop-at", default="08:00"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for v in ("NGC_ENV_FILE", "NIM_CACHE_DIR", "P93_HF_HUB"):
        if not os.environ.get(v):
            sys.exit(f"{v} is not set")
    pred = json.load(open(a.prediction, encoding="utf-8"))
    if pred.get("draft") and not a.dry_run:
        sys.exit("refused: the pre-registration is a draft")
    side = os.path.splitext(a.prediction)[0] + ".sha256"
    if not os.path.isfile(side) or open(side, encoding="utf-8").read().split()[0] != sha256_file(a.prediction):
        sys.exit("refused: the pre-registration does not match its .sha256 file")
    for f, h in pred["harness_sha256"].items():
        if sha256_file(os.path.join(HERE, f)) != h:
            sys.exit(f"refused: {f} is not the file the pre-registration binds")
    want = [x for x in a.steps.split(",") if x] or pred["plan"]
    plan = [s for s in ORDER if s in want and s in pred["plan"]]
    lg3 = pred["serving"]["lg3_weights"]; n2 = pred["serving"].get("n2_nim")
    if a.dry_run:
        print(json.dumps({"plan": plan, "n2": bool(n2)})); return 0
    start = time.time(); deadline = start + a.hours * 3600
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= t:
        stop += datetime.timedelta(days=1)
    deadline = min(deadline, stop.timestamp())
    os.makedirs(RESULTS, exist_ok=True); logdir = os.path.join(BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    EV = open(os.path.join(RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    first = g8_gate.sample()
    event(kind="run_start", prediction_sha256=sha256_file(a.prediction), plan=plan, time_limit={"hours": a.hours, "stop_at": a.stop_at}, gpu=gpu(), other_containers_running=len(others),
          compute_processes_listed=first["compute_processes_listed"], guardrails_python=os.path.basename(os.path.dirname(os.path.dirname(a.gr_py))))
    if others:
        event(kind="run_end", reason="another container is running; nothing was started", rc=2); return 2
    stopped = None; name = None
    try:
        for step in plan:
            if time.time() > deadline:
                stopped = f"time limit reached before {step}"; break
            name = f"p102_{step}"
            if step.startswith("passthrough"):
                extra = {"NIM_PASSTHROUGH_ARGS": PASSTHROUGH} if step.endswith("_on") else {}
                if not image_ok(NIM_N3["image"], NIM_N3["index_digest"]):
                    event(kind="step_null", step=step, reason="the local image does not carry the pinned digest"); continue
                cmd, shown = nim_command(name, NIM_N3, extra); group = "n3_nim"
            elif step == "lg3":
                cmd, shown, snap = vllm_command(name, lg3); group = "lg3_vllm"
                if not os.path.isfile(os.path.join(snap, "config.json")):
                    event(kind="step_skipped", step=step, reason="skipped - license: the weights are not in the hub cache (the model is behind a licence gate)"); continue
                if not image_ok(VLLM["image"], VLLM["digest"]):
                    event(kind="step_null", step=step, reason="the local vLLM image does not carry the pinned digest"); continue
            else:
                if not n2:
                    continue
                if not image_ok(n2["image"], n2["index_digest"]):
                    event(kind="step_skipped", step=step, reason="the image is not present with the pinned digest"); continue
                cmd, shown = nim_command(name, n2, {}); group = "n2_nim"
            ok, g = gate_until(deadline)
            event(kind="g8", step=step, before="container start", **{"pass": ok}, gate=g)
            if not ok:
                stopped = f"the idle-card gate did not pass before {step}"; break
            L = launch(name, cmd, shown, logdir)
            event(kind="container_ready", step=step, ready=L.get("ready"), seconds=L.get("seconds_to_verdict"), launch=L, gpu=gpu())
            if not L.get("ready"):
                event(kind="step_null", step=step, reason=L.get("reason"), a_result_for_this_step=step == "passthrough_on")
                sh(["docker", "rm", "-f", name], timeout=120); time.sleep(10); continue
            event(kind="warm_up", step=step, versions=server_versions(), **warm_up(group))
            if step.startswith("passthrough"):
                todo = [(None, None, ["passthrough", "--label", step.split("_")[1]])]
            else:
                sub = "lg3" if step == "lg3" else "n2"; modes = ["c1", "c16"] if step == "lg3" else ["c1"]
                todo = [(track, mode, [sub, "--mode", mode, "--track", track]) for track in ("input", "output") for mode in ["precheck"] + modes]
            failed_track = set()
            for track, mode, args in todo:
                if track in failed_track:
                    continue
                if mode == "precheck":
                    rc, d = cells(a, *args)
                    event(kind="precheck", step=step, track=track, rc=rc, **{"pass": rc == 0}, result=d)
                    if rc != 0:
                        failed_track.add(track); event(kind="track_null", step=step, track=track, reason="precheck failed")
                    continue
                if time.time() > deadline:
                    stopped = f"time limit reached before {step}/{track}/{mode}"; break
                ok, g = gate_until(deadline)
                event(kind="g8", step=step, track=track, mode=mode, before="cell", **{"pass": ok}, gate=g)
                if not ok:
                    stopped = f"the idle-card gate did not pass before {step}/{track}/{mode}"; break
                rc, d = cells(a, *args)
                after = g8_gate.sample()
                event(kind="cell", step=step, track=track, mode=mode, rc=rc, result=d, gpu_after={k: after[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")},
                      container_alive=bool(sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=60).stdout.strip()))
            open(os.path.join(logdir, f"{name}.{int(time.time())}.container.log.txt"), "w", encoding="utf-8", newline="\n").write(scrub(docker_logs(name)))
            sh(["docker", "rm", "-f", name], timeout=180); time.sleep(10)
            event(kind="container_stopped", step=step, gpu=gpu())
            if stopped:
                break
    finally:
        for n in sh(["docker", "ps", "-a", "--filter", "name=p102_", "--format", "{{.Names}}"], timeout=60).stdout.split():
            sh(["docker", "rm", "-f", n], timeout=180)
        time.sleep(10)
        event(kind="card_after_the_run", **card_state())
    event(kind="run_end", reason=stopped or "plan complete", rc=0 if not stopped else 5, seconds=round(time.time() - start))
    return 0 if not stopped else 5


if __name__ == "__main__":
    sys.exit(main())
