#!/usr/bin/env python3
"""Vol.3 · a second, separately pre-registered look at one question of the generic-NIM cell: does the Safety Guard 8B v3
model give the same verdicts when the generic NIM 2.0.12 serves it as when upstream vLLM 0.20.2 does?

Three containers in one session, the NIM between two starts of the upstream server:
  U1   upstream vLLM 0.20.2        the container command of the study's arm J6 (as J6-tonight of 2026-10-08)
  M    the generic NIM 2.0.12      the container command that ran as arm J6M (its second start setting, read from that
                                   cell's pre-registration: nothing is retyped here)
  U2   upstream vLLM 0.20.2        as U1, in a new container
Per arm and track: the precheck, then the whole track at 16 concurrent requests (the cell that gives the verdicts and
the rate). No one-at-a-time cell, no rail cell, no stability subset: the first cell has them.

Every cell is the study's unchanged `p93_judge.py --arm J6`; containers are started and stopped by the frozen functions
of model_free_nim_run.py. This file sets the order, the arm names and the results folder. The idle-card gate runs
before every container and every cell; a session does not start while a game launcher is running or another container
is up. A container that does not report ready is a result: the events file keeps the reason and the error line.

env: NGC_ENV_FILE · NIM_CACHE_DIR · P93_HF_HUB · SG_NIM_RESULTS (default results/safety_guard_recheck) · SG_NIM_BUCKET
usage: safety_guard_recheck_run.py --prediction FILE --gr-py PY [--stop-at HH:MM] [--dry-run]
"""
import argparse, datetime, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
VOL_DIR = os.path.dirname(HERE)
os.environ.setdefault("SG_NIM_RESULTS", os.path.join(VOL_DIR, "results", "safety_guard_recheck"))
os.environ.setdefault("SG_NIM_BUCKET", os.path.join(os.path.dirname(VOL_DIR), "_internal", "hold", "vol3_safety_guard_recheck"))
sys.path.insert(0, HERE)
import model_free_nim_run as X  # noqa: E402  (frozen; reads the two folders set above)
from p93_common import HF_SG8, VLLM, gpu, sh, sha256_file  # noqa: E402
from p93_run import image_ok  # noqa: E402
import p102_run  # noqa: E402
import g8_gate  # noqa: E402

R = X.R
ORDER = [("u1", "U1"), ("m", "M"), ("u2", "U2")]
GAMES = re.compile(r"^(steam|steamwebhelper|epicgameslauncher|battle\.net|riotclientservices|eadesktop|galaxyclient)\.exe", re.I)


def game_processes():
    r = sh(["tasklist", "/FO", "CSV", "/NH"], timeout=60)
    return sorted({l.split(",")[0].strip('"') for l in (r.stdout or "").splitlines() if GAMES.match(l.strip('"'))})


def command(step, G, setting):
    if step == "m":
        return X.generic_command(X.PREFIX + step, G["image"], dict(G["start_settings"][setting]))
    cmd, shown, _ = p102_run.vllm_command(X.PREFIX + step, HF_SG8)
    return cmd, shown


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prediction", required=True); ap.add_argument("--gr-py", required=True); ap.add_argument("--stop-at", default="08:00"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for v in ("NGC_ENV_FILE", "NIM_CACHE_DIR", "P93_HF_HUB"):
        if not os.environ.get(v):
            sys.exit(f"{v} is not set")
    pred = json.load(open(a.prediction, encoding="utf-8"))
    if pred.get("draft") and not a.dry_run:
        sys.exit("refused: the pre-registration is a draft")
    side = os.path.splitext(a.prediction)[0] + ".sha256"
    if not a.dry_run and (not os.path.isfile(side) or open(side, encoding="utf-8").read().split()[0] != sha256_file(a.prediction)):
        sys.exit("refused: the pre-registration does not match its .sha256 file")
    for f, h in pred["harness_sha256"].items():
        if sha256_file(os.path.join(HERE, f)) != h and not a.dry_run:
            sys.exit(f"refused: {f} is not the file the pre-registration binds")
    first = os.path.join(VOL_DIR, *pred["serving"]["taken_from"]["file"].split("/"))
    if sha256_file(first) != pred["serving"]["taken_from"]["sha256"]:
        sys.exit("refused: the first cell's pre-registration is not the file this one names")
    G = json.load(open(first, encoding="utf-8"))["serving"]["generic_nim"]; setting = pred["serving"]["M"]["start_setting"]
    card_path, card_text = R.card_template_text()
    if R.sha256_text(card_text) != pred["prompt_template_sha256"]:
        sys.exit("refused: the model card's template is not the one the pre-registration names")
    if a.dry_run:
        for _, arm in ORDER:
            R.view(arm)
        print(json.dumps({"results": R.RESULTS, "views": "built and checked", "game_processes": game_processes(),
                          "images_present": {"generic": image_ok(G["image"], G["index_digest"]), "vllm": image_ok(VLLM["image"], VLLM["digest"])},
                          "commands": {arm: command(step, G, setting)[1] for step, arm in ORDER}}, indent=1)); return 0
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop_time = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop_time <= t:
        stop_time += datetime.timedelta(days=1)
    deadline = stop_time.timestamp(); t_start = time.time()
    os.makedirs(R.RESULTS, exist_ok=True); logdir = os.path.join(R.BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    R.EV = open(os.path.join(R.RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n"); p102_run.EV = R.EV
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split(); games = game_processes(); first_sample = g8_gate.sample()
    R.event(kind="run_start", prediction_sha256=sha256_file(a.prediction), order=[arm for _, arm in ORDER], stop_at=a.stop_at, gpu=gpu(), other_containers_running=len(others), game_processes=games,
            compute_processes_listed=first_sample["compute_processes_listed"])
    if others or games:
        R.event(kind="run_end", reason="another container or a game launcher is running; nothing was started", rc=2); return 2
    if not (image_ok(G["image"], G["index_digest"]) and image_ok(VLLM["image"], VLLM["digest"])):
        R.event(kind="run_end", reason="a local image does not carry its pinned digest", rc=2); return 2
    stopped = None
    try:
        for step, arm in ORDER:
            if time.time() > deadline:
                stopped = f"time limit reached before {arm}"; break
            cmd, shown = command(step, G, setting)
            ready, L = X.start(step, setting if step == "m" else "upstream vLLM", cmd, shown, logdir, deadline, "sg8_nim" if step == "m" else "sg8_vllm", {"arm": arm})
            if ready is None:
                stopped = L; break
            if ready:
                stopped = R.cells_of(a, step, X.PREFIX + step, arm, card_path, ["c16"], "", deadline)
            else:
                R.event(kind="step_null", step=step, arm=arm, reason=L.get("reason"), first_error_line=L.get("first_error_line"))
            X.stop(step, logdir)
            if stopped:
                break
    finally:
        for n in X.my_containers():
            sh(["docker", "rm", "-f", n], timeout=180)
        time.sleep(10)
        R.event(kind="card_after_the_run", game_processes=game_processes(), **X.card_state())
    R.event(kind="run_end", reason=stopped or "plan complete", rc=0 if not stopped else 5, seconds=round(time.time() - t_start))
    return 0 if not stopped else 5


if __name__ == "__main__":
    sys.exit(main())
