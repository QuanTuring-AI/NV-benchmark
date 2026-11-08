#!/usr/bin/env python3
"""Vol.5 · start and stop one NIM container for a smoke test while another container of this repository's work keeps the
card busy, and write what happened to an events file as it happens. Nothing here is a timing.

Differences from the session steps of Vol.4 (vol4-retriever/scripts/run_step.py): the host port is an argument (the other
container holds 8000), there is no idle-card gate (the card is shared on purpose and every record says so), and before
a start the free card memory is compared with what the caller says the container needs plus a margin.

  start   docker run -d --gpus all -p 127.0.0.1:<port>:8000 --shm-size=16GB --env-file <key file> [-e ...] [-v ...] IMAGE,
          wait for GET /v1/health/ready, record seconds, the card before and once ready, the image digest, and — when
          the container is not ready — its last log lines. The whole log goes to the folder outside the repository.
  stop    save the log, remove the container, record the card.
  note    one free-text event.
  rate    the seconds of the last pieces of a whole-corpus encoding (a checkpoints.jsonl of encode_corpus_resumable.py),
          to see whether a smoke test slowed that run down.

The NGC key file is passed to docker by path and never read. env: NGC_ENV_FILE · VOL5_LOGS (folder outside the repository)
usage: smoke_step.py start --name NAME --image IMAGE --port 8010 --needs-mib 6000 --events FILE [--env K=V ...]
                           [--volume HOST:CONTAINER ...] [--docker-arg ARG ...] [--wait 600] [--margin-mib 4096]
       smoke_step.py stop --name NAME --events FILE
       smoke_step.py note --events FILE --label L --text T
       smoke_step.py rate --checkpoints FILE --events FILE --label L [--last 6]
"""
import argparse, json, os, re, subprocess, sys, time

import requests


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sh(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env={**os.environ, "MSYS_NO_PATHCONV": "1"})


def card():
    o = sh(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,power.draw,driver_version", "--format=csv,noheader,nounits"]).stdout.strip().splitlines()[0]
    u, t, util, p, drv = [x.strip() for x in o.split(",")]
    return {"used_mib": int(u), "total_mib": int(t), "util_pct": int(util), "power_w": float(p), "driver": drv}


def event(path, **kw):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    rec = {"at": now(), "gpu_contended": True, **kw}
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def running():
    return [n for n in sh(["docker", "ps", "--format", "{{.Names}}"]).stdout.split() if n]


def save_log(name, suffix):
    log = sh(["docker", "logs", name], timeout=120)
    text = re.sub(r"nvapi-[A-Za-z0-9_\-]+", "<key>", (log.stdout or "") + (log.stderr or ""))
    d = os.environ["VOL5_LOGS"]; os.makedirs(d, exist_ok=True)
    open(os.path.join(d, f"{name}.{int(time.time())}.{suffix}.log.txt"), "w", encoding="utf-8").write(text)
    return text


def cmd_start(a):
    before = card(); free = before["total_mib"] - before["used_mib"]
    if free < a.needs_mib + a.margin_mib:
        event(a.events, kind="start_refused", name=a.name, image=a.image, card=before, free_mib=free, needs_mib=a.needs_mib, margin_mib=a.margin_mib,
              rule="free card memory must be at least what the container needs plus the margin")
        print(json.dumps({"start_refused": a.name, "free_mib": free})); return 4
    cmd = ["docker", "run", "-d", "--name", a.name, "--gpus", "all", "-p", f"127.0.0.1:{a.port}:8000", "--shm-size=16GB", "--env-file", os.environ["NGC_ENV_FILE"]]
    shown = cmd[:-1] + ["$NGC_ENV_FILE"]
    for x in a.docker_arg or []:
        cmd.append(x); shown.append(x)
    for kv in a.env or []:
        cmd += ["-e", kv]; shown += ["-e", kv]
    for v in a.volume or []:
        host, target = v.rsplit(":", 1)
        os.makedirs(host, exist_ok=True)
        cmd += ["-v", v]; shown += ["-v", f"<folder outside the repository>:{target}"]
    cmd.append(a.image); shown.append(a.image)
    digest = sh(["docker", "image", "inspect", a.image, "--format", "{{index .RepoDigests 0}}"]).stdout.strip()
    t0 = time.time(); r = sh(cmd)
    if r.returncode != 0:
        event(a.events, kind="start_failed", name=a.name, image=a.image, command=shown, stderr=r.stderr.strip()[-600:]); print(r.stderr[-300:]); return 5
    ready, reason = False, None
    while time.time() - t0 < a.wait:
        if a.name not in running():
            reason = "the container exited"; break
        try:
            if requests.get(f"http://127.0.0.1:{a.port}/v1/health/ready", timeout=5).status_code == 200:
                ready = True; break
        except Exception:
            pass
        time.sleep(3)
    secs = round(time.time() - t0, 1)
    text = save_log(a.name, "startup")
    after = card()
    rec = event(a.events, kind="ready" if ready else "not_ready", name=a.name, image=a.image, image_digest=digest, command=shown, host_port=a.port, seconds_to_verdict=secs,
                reason=reason or (None if ready else "no ready answer within the wait"), card_before=before, card=after, card_memory_added_mib=after["used_mib"] - before["used_mib"],
                other_containers_running=[n for n in running() if n != a.name], startup_log_lines=len(text.splitlines()),
                last_log_lines=None if ready else [re.sub(r"\s+", " ", l.strip())[:300] for l in text.splitlines()[-14:]])
    print(json.dumps({k: rec[k] for k in ("kind", "name", "seconds_to_verdict", "reason", "card_memory_added_mib")}))
    return 0 if ready else 6


def cmd_stop(a):
    text = save_log(a.name, "container") if a.name in sh(["docker", "ps", "-a", "--format", "{{.Names}}"]).stdout.split() else ""
    before = card()
    sh(["docker", "rm", "-f", a.name], timeout=120); time.sleep(4)
    rec = event(a.events, kind="stopped", name=a.name, card_before_stop=before, card=card(), log_lines=len(text.splitlines()), containers_running=running())
    print(json.dumps({k: rec[k] for k in ("kind", "name", "containers_running")})); return 0


def cmd_rate(a):
    pieces = [json.loads(l) for l in open(a.checkpoints, encoding="utf-8") if l.strip()]
    pieces = [p for p in pieces if p.get("kind") == "piece" and p.get("closed_because") == "full piece"]
    last = pieces[-a.last:]
    rec = event(a.events, kind="encoder_rate", label=a.label, pieces_on_record=len(pieces),
                last_pieces=[{"piece": p["piece"], "passages": p["passages"], "seconds": p["seconds"], "end": p["end"]} for p in last])
    print(json.dumps({"label": a.label, "pieces": len(pieces), "seconds_of_the_last": [p["seconds"] for p in last]})); return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("--name", required=True); s.add_argument("--image", required=True); s.add_argument("--port", type=int, required=True)
    s.add_argument("--needs-mib", type=int, required=True); s.add_argument("--margin-mib", type=int, default=4096); s.add_argument("--events", required=True)
    s.add_argument("--env", action="append"); s.add_argument("--volume", action="append"); s.add_argument("--docker-arg", action="append"); s.add_argument("--wait", type=int, default=600)
    t = sub.add_parser("stop"); t.add_argument("--name", required=True); t.add_argument("--events", required=True)
    n = sub.add_parser("note"); n.add_argument("--events", required=True); n.add_argument("--label", required=True); n.add_argument("--text", required=True)
    r = sub.add_parser("rate"); r.add_argument("--checkpoints", required=True); r.add_argument("--events", required=True); r.add_argument("--label", required=True); r.add_argument("--last", type=int, default=6)
    a = ap.parse_args()
    if a.cmd == "note":
        event(a.events, kind="note", label=a.label, text=a.text, card=card()); return 0
    return {"start": cmd_start, "stop": cmd_stop, "rate": cmd_rate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
