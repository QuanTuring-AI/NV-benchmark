#!/usr/bin/env python3
"""Vol.3 · the generic-NIM cell, one more arm set by an addendum before the first serving container:

  J6-v0271   the Safety Guard 8B v3 weights on the upstream vLLM image of the version the generic NIM 2.0.12 ships
             (0.27.1): the container command of the study's arm J6 with the image tag changed and nothing else.
             J6M against this arm is the same engine version with and without the NIM around it.

Cells as J6-tonight: per track precheck, c=1 on the 200-item subset, c=16 on the whole track. No stability rerun, no
rail cell. The start settings of the addendum are tried in their order until one reports ready; a setting that does not
is an event with its error line as it is. If none does, the arm is skipped and the night goes on.
Everything it runs is the frozen programs of the cell (model_free_nim_run.py and what that file imports); this file
adds the image and the order. Events go to the cell's events.jsonl. The container is named mfnim_vllm_0271.

env: P93_HF_HUB · SG_NIM_RESULTS · SG_NIM_BUCKET (as for model_free_nim_run.py; NGC_ENV_FILE and NIM_CACHE_DIR are read by
the modules it imports and are not used by this arm)
usage: model_free_nim_addendum_run.py --addendum FILE --gr-py PY [--stop-at HH:MM] [--dry-run]
"""
import argparse, datetime, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_free_nim_run as X  # noqa: E402  (sets the default results and bucket folders before the study's modules load)
from p93_common import HF_SG8, VLLM, gpu, sh, sha256_file  # noqa: E402
from p93_run import image_ok  # noqa: E402
import p102_run  # noqa: E402
import g8_gate  # noqa: E402

R = X.R
ARM = "J6-v0271"; STEP = "vllm_0271"


def command(name, image, env):
    """The container command of the study's arm J6 with another image; extra settings go in front of the mount."""
    cmd, shown, _ = p102_run.vllm_command(name, HF_SG8)
    out = []
    for c in (cmd, shown):
        c = [image if x == VLLM["image"] else x for x in c]
        i = c.index("-v")
        out.append(c[:i] + [y for k, v in env.items() for y in ("-e", f"{k}={v}")] + c[i:])
    if out[0].count(image) != 1:
        sys.exit("refused: the image was not placed in the container command exactly once")
    return out[0], out[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--addendum", required=True); ap.add_argument("--gr-py", required=True); ap.add_argument("--stop-at", default="08:00"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    A = json.load(open(a.addendum, encoding="utf-8"))
    if A.get("draft") and not a.dry_run:
        sys.exit("refused: the addendum is a draft")
    side = os.path.splitext(a.addendum)[0] + ".sha256"
    if not a.dry_run and (not os.path.isfile(side) or open(side, encoding="utf-8").read().split()[0] != sha256_file(a.addendum)):
        sys.exit("refused: the addendum does not match its .sha256 file")
    for f, h in A["harness_sha256"].items():
        if sha256_file(os.path.join(HERE, f)) != h and not a.dry_run:
            sys.exit(f"refused: {f} is not the file the addendum binds")
    S = A["arm_J6-v0271"]["serving"]; attempts = [(k, dict(S["start_settings"][k])) for k in S["order_of_the_start_settings"]]
    card_path, card_text = R.card_template_text()
    if a.dry_run:
        R.view(ARM)
        print(json.dumps({"arm": ARM, "view": "built and checked", "image_present": image_ok(S["image"], S["digest"]), "commands": {k: command(X.PREFIX + STEP, S["image"], env)[1] for k, env in attempts}}, indent=1)); return 0
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop_time = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop_time <= t:
        stop_time += datetime.timedelta(days=1)
    deadline = stop_time.timestamp(); t_start = time.time()
    os.makedirs(R.RESULTS, exist_ok=True); logdir = os.path.join(R.BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    R.EV = open(os.path.join(R.RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n"); p102_run.EV = R.EV
    a.prediction = a.addendum
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split(); first = g8_gate.sample()
    R.event(kind="run_start", step=STEP, addendum_sha256=sha256_file(a.addendum), stop_at=a.stop_at, gpu=gpu(), other_containers_running=len(others), compute_processes_listed=first["compute_processes_listed"])
    if others:
        R.event(kind="run_end", step=STEP, reason="another container is running; nothing was started", rc=2); return 2
    if not image_ok(S["image"], S["digest"]):
        R.event(kind="step_null", step=STEP, reason="the local image does not carry the digest the addendum names; the arm is skipped")
        R.event(kind="run_end", step=STEP, reason="arm skipped", rc=0); return 0
    stopped = None
    try:
        ready = False
        for key, env in attempts:
            cmd, shown = command(X.PREFIX + STEP, S["image"], env)
            ready, L = X.start(STEP, key, cmd, shown, logdir, deadline, "sg8_vllm", {"start_setting": env})
            if ready is None:
                stopped = L; break
            if ready:
                break
            R.event(kind="start_setting_null", step=STEP, profile=key, reason=L.get("reason"), first_error_line=L.get("first_error_line"), a_result_for_this_step=True)
            sh(["docker", "rm", "-f", X.PREFIX + STEP], timeout=120); time.sleep(10)
        if ready:
            stopped = R.cells_of(a, STEP, X.PREFIX + STEP, ARM, card_path, ["c1", "c16"], "", deadline)
            X.stop(STEP, logdir)
        elif not stopped:
            R.event(kind="step_null", step=STEP, reason="no start setting of the addendum reported ready; the arm is skipped")
    finally:
        for n in X.my_containers():
            sh(["docker", "rm", "-f", n], timeout=180)
        time.sleep(10)
        R.event(kind="card_after_the_run", step=STEP, **X.card_state())
    R.event(kind="run_end", step=STEP, reason=stopped or "plan complete", rc=0 if not stopped else 5, seconds=round(time.time() - t_start))
    return 0 if not stopped else 5


if __name__ == "__main__":
    sys.exit(main())
