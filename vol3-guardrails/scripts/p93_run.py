#!/usr/bin/env python3
"""P93 · the runner: one judge container on the card at a time, an idle-card gate before every cell, a precheck before an
arm's cells, every step written to events.jsonl as it happens.

Order (three phases; a container is started for each group of arms that share it, and stopped before the next):
  main        J0, J1 (Llama NIM) -> J2, J3 (Nemotron 3 Nano NIM) -> J4, J5 (Nemotron 3.5 Content Safety, vLLM) -> J6 (Safety Guard 8B, vLLM)
              per arm and track: precheck, then the c=1 cell, then the c=16 cell
  gr_path     J4G, J5G: precheck, then the gr_path cell
  stability   J0 .. J6 again, each in a new container: precheck (tag stability), then the stability cell
A track whose precheck fails is skipped for that arm (its result is null); the run goes on with the next.
Before every cell: tools/g8_gate.py (10 s of nvidia-smi; util p50 <= 2% and power p50 <= 45 W; retried each minute for
15 min). If the gate does not pass, the gate is run again until it passes or the time limit is reached: no cell runs in
a window that did not pass. After every cell one more 10 s sample is recorded.
Time limit: --hours of wall time or --stop-at HH:MM, checked between cells; the run then stops and says what is left.

Containers:
  NIM    docker run --gpus all -p 127.0.0.1:8000:8000 --env-file $NGC_ENV_FILE -e NIM_MODEL_PROFILE=<profile> ... -v $NIM_CACHE_DIR:/opt/nim/.cache <image>
  vLLM   docker run --gpus all -p 127.0.0.1:8000:8000 -v <model snapshot>:/model:ro vllm/vllm-openai:<tag> --model /model --served-model-name <name> --max-model-len 8192
         If the pinned vLLM does not start, the fallback image (--vllm-fallback) is tried once and the arm is marked as
         outside the model card's version range.
The image that runs is checked against the pinned digest before it is started. The NGC key file is passed by path
and never read. events.jsonl names paths by their variable ($NIM_CACHE_DIR, $P93_HF_HUB), not by their value; container
logs go to the process bucket.
Warm-up after READY, discarded: five short requests; for Nemotron 3 Nano, 256-token requests are repeated until one runs
at 220 tok/s or more (its first minute after READY is slower), for at most 180 s.

env: NGC_ENV_FILE · NIM_CACHE_DIR · P93_HF_HUB (the Hugging Face hub cache that holds the two model snapshots)
usage: p93_run.py --prediction FILE --gr-py PY [--phases main,gr_path,stability] [--arms J0,J1,...] [--hours 6] [--stop-at 08:00]
                  [--vllm-fallback vllm/vllm-openai:v0.30.0] [--dry-run]
"""
import argparse, datetime, json, os, re, subprocess, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
from p93_common import ARMS, BASE, BUCKET, CONTAINERS, CONTEXT, RESULTS, VLLM, gpu, now, sh, sha256_file  # noqa: E402
import g8_gate  # noqa: E402

READY_TIMEOUT_S = 1800
MOUNT = "/opt/nim/.cache"
N3_WARM_RATE, N3_WARM_MAX_S = 220.0, 180
PHASES = {"main": (["J0", "J1", "J2", "J3", "J4", "J5", "J6"], ["c1", "c16"], ""), "gr_path": (["J4G", "J5G"], ["gr_path"], ""),
          "stability": (["J0", "J1", "J2", "J3", "J4", "J5", "J6"], ["stability"], "stability")}
EV = None


def event(**k):
    k = {"at": now(), **k}
    EV.write(json.dumps(k, ensure_ascii=False) + "\n"); EV.flush()
    print(json.dumps({x: k[x] for x in k if x in ("at", "kind", "arm", "track", "mode", "group", "phase", "pass", "rc", "reason", "ready", "seconds")}), flush=True)
    return k


def docker_logs(name):
    r = sh(["docker", "logs", name], timeout=120)
    return (r.stdout or "") + (r.stderr or "")


def scrub(text):
    return "\n".join(l for l in (text or "").splitlines() if "nvapi" not in l.lower()) + "\n"


def image_ok(image, digest):
    r = sh(["docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}"], timeout=60)
    return r.returncode == 0 and digest in r.stdout


def launch(group, arms, logdir, fallback):
    """-> record. The command is logged with path variables, not path values."""
    A = ARMS[arms[0]]; name = f"p93-{group}".replace("_", "-")
    sh(["docker", "rm", "-f", name], timeout=120)
    attempts = []
    images = [None] if A["engine"] == "nim" else [VLLM["image"]] + ([fallback] if fallback else [])
    for img in images:
        if A["engine"] == "nim":
            S = A["serve"]
            if not image_ok(S["image"], S["index_digest"]):
                return {"ready": False, "reason": "the local image does not carry the pinned digest", "image": S["image"]}
            env = {"NIM_MODEL_PROFILE": S["profile"], **S["env"]}
            cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "127.0.0.1:8000:8000", "--env-file", os.environ["NGC_ENV_FILE"]]
            shown = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "127.0.0.1:8000:8000", "--env-file", "$NGC_ENV_FILE"]
            for k, v in env.items():
                cmd += ["-e", f"{k}={v}"]; shown += ["-e", f"{k}={v}"]
            cmd += ["-v", f"{os.environ['NIM_CACHE_DIR']}:{MOUNT}", S["image"]]; shown += ["-v", f"$NIM_CACHE_DIR:{MOUNT}", S["image"]]
            image, in_range = S["image"], None
        else:
            S = A["serve"]
            if img == VLLM["image"] and not image_ok(img, VLLM["digest"]):
                return {"ready": False, "reason": "the local vLLM image does not carry the pinned digest", "image": img}
            snap = os.path.join(os.environ["P93_HF_HUB"], "models--" + S["repo"].replace("/", "--"), "snapshots", S["revision"])
            if not os.path.isfile(os.path.join(snap, "config.json")):
                return {"ready": False, "reason": "the model snapshot is not in the hub cache", "repo": S["repo"], "revision": S["revision"]}
            env = {"VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1", "HF_HUB_OFFLINE": "1"}
            args = ["--model", "/model", "--served-model-name", S["served"], "--max-model-len", str(CONTEXT), "--host", "0.0.0.0", "--port", "8000"]
            cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "127.0.0.1:8000:8000"]; shown = list(cmd)
            for k, v in env.items():
                cmd += ["-e", f"{k}={v}"]; shown += ["-e", f"{k}={v}"]
            cmd += ["-v", f"{snap}:/model:ro", img, *args]
            shown += ["-v", f"$P93_HF_HUB/models--{S['repo'].replace('/', '--')}/snapshots/{S['revision']}:/model:ro", img, *args]
            image, in_range = img, img == VLLM["image"]
        t0 = time.time(); r = sh(cmd, timeout=300)
        rec = {"image": image, "command": shown, "in_model_card_version_range": in_range, "name": name}
        if r.returncode != 0:
            rec.update({"ready": False, "reason": "docker run failed", "detail": (r.stderr or "").strip()[-300:]}); attempts.append(rec); continue
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
        L = docker_logs(name)
        open(os.path.join(logdir, f"{name}.{int(t0)}.startup.log.txt"), "w", encoding="utf-8", newline="\n").write(scrub(L))
        ver = re.findall(r"vLLM API server version (\S+)", L)
        err = re.search(r"^\s*(?:\(\w+ pid=\d+\)\s*)?[\w.]*(?:Error|Exception): .*$", L, re.M)
        rec.update({"ready": ready, "seconds_to_verdict": round(time.time() - t0, 1), "vllm_version_in_log": ver[-1] if ver else None,
                    "reason": None if ready else (reason or f"not ready within {READY_TIMEOUT_S} s"), "first_error_line": None if ready else (err.group(0).strip()[:300] if err else None)})
        attempts.append(rec)
        if ready:
            break
        sh(["docker", "rm", "-f", name], timeout=120); time.sleep(5)
    out = dict(attempts[-1]); out["attempts"] = len(attempts)
    if len(attempts) > 1:
        out["earlier_attempts"] = attempts[:-1]
    return out


def warm_up(group):
    model = requests.get(BASE + "/v1/models", timeout=60).json()["data"][0]["id"]
    rows = []
    for _ in range(5):
        t = time.perf_counter()
        r = requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Say hello."}], "max_tokens": 16, "temperature": 0.0}, timeout=300)
        rows.append({"status": r.status_code, "ms": round((time.perf_counter() - t) * 1000)})
    rec = {"model": model, "five_short_requests": rows}
    if group == "n3_nim":
        t0 = time.time(); rates = []
        while time.time() - t0 < N3_WARM_MAX_S:
            t = time.perf_counter()
            r = requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Count from 1 to 200, separated by spaces."}], "max_tokens": 256, "temperature": 0.0}, timeout=300)
            n = (r.json().get("usage") or {}).get("completion_tokens") or 0
            rates.append(round(n / (time.perf_counter() - t), 1))
            if rates[-1] >= N3_WARM_RATE:
                break
        rec["n3_rates_tok_s"] = rates; rec["n3_reached"] = bool(rates and rates[-1] >= N3_WARM_RATE)
    return rec


def gate_until(deadline):
    """Run the idle-card gate until it passes or the time limit is reached. -> (passed, record)"""
    tries = []
    while True:
        g = g8_gate.gate(); tries.append({"pass": g["pass"], "waited_s": g["waited_s"], "last": {k: g["attempts"][-1][k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed")}, "attempts": len(g["attempts"])})
        if g["pass"] or time.time() > deadline:
            return g["pass"], {"rule": g["rule"], "tries": tries}


def judge(a, *args):
    cmd = [sys.executable, os.path.join(HERE, "p93_judge.py"), *args, "--prediction", a.prediction, "--gr-py", a.gr_py, "--sg8-template", a.sg8_template]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        d = json.loads(line)
    except ValueError:
        d = {"stderr_tail_sha256": None, "note": "no JSON line from the harness"}
    return r.returncode, d


def main():
    global EV
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prediction", required=True); ap.add_argument("--gr-py", required=True)
    ap.add_argument("--phases", default="main,gr_path,stability"); ap.add_argument("--arms", default="")
    ap.add_argument("--hours", type=float, default=6.0); ap.add_argument("--stop-at", default="08:00")
    ap.add_argument("--vllm-fallback", default="vllm/vllm-openai:v0.30.0"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for v in ("NGC_ENV_FILE", "NIM_CACHE_DIR", "P93_HF_HUB"):
        if not os.environ.get(v):
            sys.exit(f"{v} is not set")
    sg8 = ARMS["J6"]["serve"]
    a.sg8_template = os.path.join(os.environ["P93_HF_HUB"], "models--" + sg8["repo"].replace("/", "--"), "snapshots", sg8["revision"], "inference_script.py")
    pred = json.load(open(a.prediction, encoding="utf-8"))
    if pred.get("draft"):
        sys.exit("refused: the pre-registration is a draft")
    for f, h in pred["harness_sha256"].items():
        if sha256_file(os.path.join(HERE, f)) != h:
            sys.exit(f"refused: {f} is not the file the pre-registration binds")
    only = [x for x in a.arms.split(",") if x]
    start = time.time(); deadline = start + a.hours * 3600
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= t:
        stop += datetime.timedelta(days=1)
    deadline = min(deadline, stop.timestamp())
    plan = []
    for ph in a.phases.split(","):
        arms, modes, tag = PHASES[ph]
        for group, garms in CONTAINERS:
            todo = [x for x in garms if x in arms and (not only or x in only)]
            if todo:
                plan.append((ph, group, todo, modes, tag))
    if a.dry_run:
        for p in plan:
            print(p)
        return 0
    os.makedirs(RESULTS, exist_ok=True); logdir = os.path.join(BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    EV = open(os.path.join(RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    event(kind="run_start", prediction_sha256=sha256_file(a.prediction), plan=[[p[0], p[1], p[2], p[3]] for p in plan], time_limit={"hours": a.hours, "stop_at": a.stop_at},
          gpu=gpu(), other_containers_running=len(others), guardrails_python=os.path.basename(os.path.dirname(os.path.dirname(a.gr_py))))
    if others:
        event(kind="run_end", reason="another container is running; nothing was started", rc=2); return 2
    stopped_early = None
    for ph, group, arms, modes, tag in plan:
        if time.time() > deadline:
            stopped_early = f"time limit reached before {ph}/{group}"; break
        ok, g = gate_until(deadline)
        event(kind="g8", phase=ph, group=group, before="container start", **{"pass": ok}, gate=g)
        if not ok:
            stopped_early = f"the idle-card gate did not pass before {ph}/{group}"; break
        L = launch(group, arms, logdir, a.vllm_fallback)
        event(kind="container_ready", phase=ph, group=group, ready=L.get("ready"), seconds=L.get("seconds_to_verdict"), launch=L, gpu=gpu())
        name = f"p93-{group}".replace("_", "-")
        if not L.get("ready"):
            event(kind="group_null", phase=ph, group=group, arms=arms, reason=L.get("reason")); sh(["docker", "rm", "-f", name], timeout=120); continue
        event(kind="warm_up", phase=ph, group=group, **warm_up(group))
        for arm in arms:
            for track in ("input", "output"):
                rc, d = judge(a, "precheck", "--arm", arm, "--track", track, *(["--tag", tag] if tag else []))
                event(kind="precheck", phase=ph, arm=arm, track=track, rc=rc, **{"pass": rc == 0}, result=d)
                if rc != 0:
                    event(kind="arm_track_null", phase=ph, arm=arm, track=track, reason="precheck failed"); continue
                for mode in modes:
                    if time.time() > deadline:
                        stopped_early = f"time limit reached before {arm}/{track}/{mode}"; break
                    ok, g = gate_until(deadline)
                    event(kind="g8", phase=ph, arm=arm, track=track, mode=mode, before="cell", **{"pass": ok}, gate=g)
                    if not ok:
                        stopped_early = f"the idle-card gate did not pass before {arm}/{track}/{mode}"; break
                    rc, d = judge(a, "cell", "--arm", arm, "--track", track, "--mode", mode)
                    after = g8_gate.sample()
                    event(kind="cell", phase=ph, arm=arm, track=track, mode=mode, rc=rc, result=d,
                          gpu_after={k: after[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")}, container_alive=bool(sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=60).stdout.strip()))
                if stopped_early:
                    break
            if stopped_early:
                break
        open(os.path.join(logdir, f"{name}.{int(time.time())}.container.log.txt"), "w", encoding="utf-8", newline="\n").write(scrub(docker_logs(name)))
        sh(["docker", "rm", "-f", name], timeout=180); time.sleep(10)
        event(kind="container_stopped", phase=ph, group=group, gpu=gpu())
        if stopped_early:
            break
    event(kind="run_end", reason=stopped_early or "plan complete", rc=0 if not stopped_early else 5, seconds=round(time.time() - start))
    return 0 if not stopped_early else 5


if __name__ == "__main__":
    sys.exit(main())
