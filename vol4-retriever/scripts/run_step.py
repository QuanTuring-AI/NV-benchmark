#!/usr/bin/env python3
"""Vol.4 · the steps of a measurement session on one card, one step per call, each written to events.jsonl as it
happens. A session is driven step by step so that a timed step can be the only thing running on the host.

  gate        the idle-card gate (tools/g8_gate.py) plus three things it does not look at: the memory the desktop holds
              on the card, a count of game-launcher processes, and the containers that are running. The desktop's memory
              is compared with the first gate of the session: 512 MiB more is flagged in the record (recorded, not a stop).
  nim-start   start one NIM container on the Docker network of the session, wait until it reports ready, record the image
              digest, the seconds to ready, the card's memory at ready and the log lines that name a precision, engine,
              kernel or profile. The whole start-up log goes to the folder outside the repository.
  nim-stop    save the container's log, remove the container, record the card.
  client      run embed_cell.py or rerank_cell.py in the client container on the same Docker network (no host port in
              between), with the data sets and the scripts mounted read-only.
  note        append one free-text event (for example the reason a cell was not run).

Containers are named p109_<tag>. The NGC key file is passed to docker by path and never read; events name folders by
their variable, not by their value.

env: NGC_ENV_FILE · VOL4_HOLD (folder outside the repository for vectors, rankings, logs) · VOL4_DATASETS
usage: run_step.py gate --label TEXT [--timed]
       run_step.py nim-start --tag TAG --image IMAGE [--env K=V ...] [--weights DIR] [--cache DIR] [--kind 2x|1x] [--wait 1800]
       run_step.py nim-stop --tag TAG
       run_step.py client --tag TAG --program embed_cell.py -- <arguments of the program; /data, /out, /work are the mounts>
       run_step.py note --text TEXT
"""
import argparse, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
VOL = os.path.dirname(HERE); REPO = os.path.dirname(VOL)
sys.path.insert(0, os.path.join(REPO, "tools"))
import g8_gate  # noqa: E402

RESULTS = os.environ.get("VOL4_RESULTS") or os.path.join(VOL, "results", "first_batch")
EVENTS = os.path.join(RESULTS, "events.jsonl")
NET, PREFIX, CLIENT_IMAGE = "p109net", "p109_", "vol4-client:py312"
LAUNCHERS = ("steam", "epicgameslauncher", "battle.net", "riotclient", "galaxyclient", "upc.exe", "eadesktop")
LOG_LINES = re.compile(r"precision|fp16|fp8|nvfp4|bf16|tensorrt|onnx|engine|kernel|profile|compute capab|fallback|max.?seq|batch|error|denied|403|unsupported", re.I)
FLAG_MIB = 512


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sh(cmd, timeout=600, env=None):
    e = dict(os.environ); e["MSYS_NO_PATHCONV"] = "1"; e.update(env or {})
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=e)


def card():
    o = sh(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version", "--format=csv,noheader,nounits"]).stdout.strip().splitlines()[0]
    u, t, util, temp, p, drv = [x.strip() for x in o.split(",")]
    return {"used_mib": int(u), "total_mib": int(t), "util_pct": int(util), "temp_c": int(temp), "power_w": float(p), "driver": drv}


def events():
    if not os.path.isfile(EVENTS):
        return []
    return [json.loads(l) for l in open(EVENTS, encoding="utf-8") if l.strip()]


def event(**kw):
    os.makedirs(RESULTS, exist_ok=True)
    rec = {"at": now(), **kw}
    with open(EVENTS, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def running():
    return [n for n in sh(["docker", "ps", "--format", "{{.Names}}"]).stdout.split() if n]


def launchers():
    out = sh(["tasklist", "/FO", "CSV", "/NH"]).stdout.lower()
    return sum(1 for line in out.splitlines() if any(x in line.split(",")[0] for x in LAUNCHERS))


def cmd_gate(a):
    names = running(); ours = [n for n in names if n.startswith(PREFIX)]; others = [n for n in names if not n.startswith(PREFIX)]
    g = g8_gate.gate(); c = card(); n_launch = launchers()
    prev = events()
    rec = {"kind": "gate", "label": a.label, "before_a_timed_step": bool(a.timed), "pass": g["pass"], "waited_s": g["waited_s"], "attempts": len(g["attempts"]),
           "last": {k: g["attempts"][-1][k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed")}, "rule": g["rule"],
           "card": c, "containers_of_this_session": len(ours), "other_containers_running": len(others), "launcher_processes": n_launch}
    if not ours:                                   # nothing of ours on the card: what is in use is the desktop's
        first = next((e for e in prev if e.get("kind") == "gate" and e.get("desktop_mib") is not None), None)
        rec["desktop_mib"] = c["used_mib"]; rec["first_gate_desktop_mib"] = first["desktop_mib"] if first else c["used_mib"]
        rec["desktop_flag"] = bool(first and c["used_mib"] > first["desktop_mib"] + FLAG_MIB)
    else:                                          # a container of ours holds memory: growth since it reported ready is what can be seen
        ready = next((e for e in reversed(prev) if e.get("kind") == "nim_ready"), None)
        rec["used_minus_at_ready_mib"] = (c["used_mib"] - ready["card"]["used_mib"]) if ready else None
        rec["desktop_flag"] = bool(ready and c["used_mib"] > ready["card"]["used_mib"] + FLAG_MIB)
    rec["start_allowed"] = bool(g["pass"] and not others and (n_launch == 0 or not a.timed))
    event(**rec)
    print(json.dumps({k: rec[k] for k in ("label", "pass", "start_allowed", "last", "launcher_processes", "other_containers_running", "desktop_flag", "card")}))
    return 0 if rec["start_allowed"] else 4


def cmd_nim_start(a):
    name = PREFIX + a.tag
    if sh(["docker", "network", "inspect", NET]).returncode != 0:
        sh(["docker", "network", "create", NET])
    hold = os.environ["VOL4_HOLD"]; logs = os.path.join(hold, "container_logs"); os.makedirs(logs, exist_ok=True)
    cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "--network", NET, "-p", "127.0.0.1:8000:8000", "--shm-size=16GB", "--env-file", os.environ["NGC_ENV_FILE"]]
    shown = ["docker", "run", "-d", "--name", name, "--gpus", "all", "--network", NET, "-p", "127.0.0.1:8000:8000", "--shm-size=16GB", "--env-file", "$NGC_ENV_FILE"]
    if a.kind == "2x":
        cmd += ["-e", "NIM_ENGINE_MODEL_DOWNLOAD_PROVIDER=ngc"]; shown += ["-e", "NIM_ENGINE_MODEL_DOWNLOAD_PROVIDER=ngc"]
    for kv in a.env or []:
        cmd += ["-e", kv]; shown += ["-e", kv]
    if a.weights:
        cmd += ["-v", f"{a.weights}:/model"]; shown += ["-v", "<weights folder>:/model"]
    if a.cache:
        os.makedirs(a.cache, exist_ok=True)
        target = "/opt/cache" if a.kind == "2x" else "/opt/nim/.cache"
        cmd += ["-v", f"{a.cache}:{target}"]; shown += ["-v", f"<cache folder>:{target}"]
    cmd.append(a.image); shown.append(a.image)
    digest = sh(["docker", "image", "inspect", a.image, "--format", "{{index .RepoDigests 0}}"]).stdout.strip()
    before = card(); t0 = time.time()
    r = sh(cmd)
    if r.returncode != 0:
        event(kind="nim_start_failed", tag=a.tag, image=a.image, command=shown, stderr=r.stderr.strip()[-600:]); print(r.stderr[-400:]); return 5
    ready, status = False, None
    import requests
    while time.time() - t0 < a.wait:
        if name not in running():
            status = "the container exited"; break
        try:
            x = requests.get("http://127.0.0.1:8000/v1/health/ready", timeout=5)
            if x.status_code == 200:
                ready = True; break
        except Exception:
            pass
        time.sleep(5)
    secs = round(time.time() - t0, 1)
    log = sh(["docker", "logs", name], timeout=120); text = (log.stdout or "") + (log.stderr or "")
    text = re.sub(r"nvapi-[A-Za-z0-9_\-]+", "<key>", text)
    path = os.path.join(logs, f"{name}.{int(t0)}.startup.log.txt"); open(path, "w", encoding="utf-8").write(text)
    picked = []
    for line in text.splitlines():
        if LOG_LINES.search(line) and len(picked) < 60:
            picked.append(re.sub(r"\s+", " ", line.strip())[:300])
    models = None
    if ready:
        try:
            models = requests.get("http://127.0.0.1:8000/v1/models", timeout=10).json()
        except Exception as e:
            models = {"error": str(e)[:200]}
    rec = event(kind="nim_ready" if ready else "nim_not_ready", tag=a.tag, image=a.image, image_digest=digest, command=shown, seconds_to_verdict=secs, reason=status or (None if ready else "no ready answer within the wait"),
                card_before=before, card=card(), models=models, startup_log_lines=len(text.splitlines()), log_lines_picked=picked, last_log_lines=[l[:300] for l in text.splitlines()[-12:]] if not ready else None)
    print(json.dumps({k: rec[k] for k in ("kind", "tag", "seconds_to_verdict", "reason", "card")}))
    return 0 if ready else 6


def cmd_nim_stop(a):
    name = PREFIX + a.tag; hold = os.environ["VOL4_HOLD"]; logs = os.path.join(hold, "container_logs"); os.makedirs(logs, exist_ok=True)
    log = sh(["docker", "logs", name], timeout=120); text = re.sub(r"nvapi-[A-Za-z0-9_\-]+", "<key>", (log.stdout or "") + (log.stderr or ""))
    open(os.path.join(logs, f"{name}.{int(time.time())}.container.log.txt"), "w", encoding="utf-8").write(text)
    used = card()
    sh(["docker", "rm", "-f", name], timeout=120); time.sleep(5)
    rec = event(kind="nim_stopped", tag=a.tag, card_before_stop=used, card=card(), log_lines=len(text.splitlines()), containers_of_this_session_left=[n for n in running() if n.startswith(PREFIX)])
    print(json.dumps({k: rec[k] for k in ("kind", "tag", "card")})); return 0


def cmd_client(a):
    hold = os.environ["VOL4_HOLD"]; data = os.environ["VOL4_DATASETS"]; os.makedirs(RESULTS, exist_ok=True); os.makedirs(hold, exist_ok=True)
    cmd = ["docker", "run", "--rm", "--name", PREFIX + "client_" + a.tag, "--network", NET, "-v", f"{VOL}:/work:ro", "-v", f"{data}:/data:ro", "-v", f"{RESULTS}:/out", "-v", f"{hold}:/hold",
           CLIENT_IMAGE, "python", f"/work/scripts/{a.program}", *a.rest]
    start = now(); t0 = time.time()
    r = subprocess.run(cmd, env={**os.environ, "MSYS_NO_PATHCONV": "1"}, capture_output=True, text=True, encoding="utf-8", errors="replace")
    rec = event(kind="client", tag=a.tag, program=a.program, arguments=a.rest, start=start, end=now(), seconds=round(time.time() - t0, 1), rc=r.returncode,
                stdout_tail=r.stdout.strip().splitlines()[-3:], stderr_tail=[l[:300] for l in r.stderr.strip().splitlines()[-6:]] if r.returncode else None)
    print(json.dumps({k: rec[k] for k in ("tag", "program", "rc", "seconds", "stdout_tail", "stderr_tail")})[:1500])
    return r.returncode


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate"); g.add_argument("--label", required=True); g.add_argument("--timed", action="store_true")
    s = sub.add_parser("nim-start"); s.add_argument("--tag", required=True); s.add_argument("--image", required=True); s.add_argument("--env", action="append")
    s.add_argument("--weights"); s.add_argument("--cache"); s.add_argument("--kind", choices=["2x", "1x"], default="2x"); s.add_argument("--wait", type=int, default=1800)
    t = sub.add_parser("nim-stop"); t.add_argument("--tag", required=True)
    c = sub.add_parser("client"); c.add_argument("--tag", required=True); c.add_argument("--program", default="embed_cell.py"); c.add_argument("rest", nargs=argparse.REMAINDER)
    n = sub.add_parser("note"); n.add_argument("--text", required=True); n.add_argument("--label", default="note")
    a = ap.parse_args()
    if a.cmd == "client" and a.rest and a.rest[0] == "--":
        a.rest = a.rest[1:]
    if a.cmd == "note":
        event(kind="note", label=a.label, text=a.text, card=card()); return 0
    return {"gate": cmd_gate, "nim-start": cmd_nim_start, "nim-stop": cmd_nim_stop, "client": cmd_client}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
