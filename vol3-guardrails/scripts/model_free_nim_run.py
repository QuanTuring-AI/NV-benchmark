#!/usr/bin/env python3
"""Vol.3 · the Safety Guard 8B v3 weights in the generic NIM container of the 2.x line ("model-free NIM"), with two
partners measured the same night. One container on the card at a time, the idle-card gate before every start and
every cell, each step written to events.jsonl as it happens.

The question: the model's own NIM (1.14.0) gave about a fifth fewer verdicts per second than upstream vLLM 0.20.2 on
this card, and upstream vLLM 0.10.0 came within 4% of the NIM, so the gap follows the engine the 1.14.0 image ships.
Does the same weight directory, served by the generic NIM 2.0.12 (a newer vLLM inside), give upstream's rate and the
same verdicts?

  J6M           the generic NIM image, NIM_MODEL_PATH = the local model directory of the study's arm J6 (mounted
                read-only; nothing is fetched)
  J6-tonight    upstream vLLM 0.20.2 on the same directory: the container command of the study's arm J6
  J6N-tonight   the model's NIM 1.14.0, generic profile, pinned by id: the container command of arm J6N
  J6M-rail      J6M through the NeMo Guardrails content-safety rail, 100 items per track (as arm J6G)

Every cell is the study's unchanged program (`p93_judge.py --arm J6`, or safety_guard_nim_rail.py for the rail),
pointed at another server and another results folder through the views safety_guard_nim_run.py builds.

Steps (in the order of the pre-registration's plan):
  weights        no container: SHA-256 of every weight file in the local model directory and in the NIM 1.14.0 cache
  profiles       the generic image's `list-model-profiles` for the local directory; the text is kept
  j6m_main       J6M: the start settings of the pre-registration are tried in their order until one reports ready; per
                 track precheck, c=1 on the 200-item subset, c=16 on the whole track; then the rail cell
  vllm_tonight   J6-tonight: per track precheck, c=1, c=16
  nim_tonight    J6N-tonight: the same
  j6m_stability  J6M in a new container: the stability subset again
A container that does not report ready is a result of its step: the reason, the first error line and the last lines of
its log go to the events file as they are, the whole log to the folder outside the repository, and the runner goes on.
Containers are named mfnim_<step>. The NGC key file is passed by path and never read.

env: NGC_ENV_FILE · NIM_CACHE_DIR · P93_HF_HUB · SG_NIM_RESULTS (default results/model_free_nim) · SG_NIM_BUCKET
usage: model_free_nim_run.py --prediction FILE --gr-py PY [--steps a,b,...] [--stop-at HH:MM] [--dry-run]
"""
import argparse, datetime, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
VOL_DIR = os.path.dirname(HERE)
os.environ.setdefault("SG_NIM_RESULTS", os.path.join(VOL_DIR, "results", "model_free_nim"))
os.environ.setdefault("SG_NIM_BUCKET", os.path.join(os.path.dirname(VOL_DIR), "_internal", "hold", "vol3_model_free_nim"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(VOL_DIR), "tools"))
from p93_common import CONTEXT, HF_SG8, VLLM, gpu, sh, sha256_file  # noqa: E402
from p93_run import docker_logs, gate_until, image_ok, scrub, warm_up  # noqa: E402
import p102_run  # noqa: E402
import g8_gate  # noqa: E402
import safety_guard_nim_run as R  # noqa: E402

ORDER = ["weights", "profiles", "j6m_main", "vllm_tonight", "nim_tonight", "j6m_stability"]
MOUNT = "/opt/nim/.cache"; MODEL_AT = "/model"
PREFIX = "mfnim_"


def snapshot_dir():
    return os.path.join(os.environ["P93_HF_HUB"], "models--" + HF_SG8["repo"].replace("/", "--"), "snapshots", HF_SG8["revision"])


def nim_cache_weights(pred):
    return os.path.join(os.environ["NIM_CACHE_DIR"], *pred["weights"]["nim_cache_folder_below_the_cache"].split("/"))


def resolve(path):
    """-> (the file a directory entry stands for, how it was found). The NIM cache is written from inside a Linux
    container: its snapshot folder holds links into ../../blobs/ that Windows does not follow by itself."""
    if os.path.isfile(path):
        return path, "a file"
    if os.path.lexists(path):
        try:
            r = subprocess.run(["readlink", path.replace("\\", "/")], capture_output=True, text=True, timeout=30)
            target = r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            target = ""
        real = os.path.normpath(os.path.join(os.path.dirname(path), *target.split("/"))) if target else None
        if real and os.path.isfile(real):
            return real, "a link, read with readlink: " + target
    return None, "not found"


def weight_table(pred):
    """SHA-256 of every *.safetensors of the two directories, file by file. -> record"""
    a, b = snapshot_dir(), nim_cache_weights(pred)
    names = sorted({f for d in (a, b) if os.path.isdir(d) for f in os.listdir(d) if f.endswith(".safetensors")})
    rows = []
    for n in names:
        (pa, ha), (pb, hb) = resolve(os.path.join(a, n)), resolve(os.path.join(b, n))
        ra = {"sha256": sha256_file(pa), "bytes": os.path.getsize(pa), "entry_is": ha} if pa else None
        rb = {"sha256": sha256_file(pb), "bytes": os.path.getsize(pb), "entry_is": hb} if pb else None
        rows.append({"file": n, "local_model_directory": ra, "nim_1_14_0_cache": rb, "same_bytes": bool(ra and rb and (ra["sha256"], ra["bytes"]) == (rb["sha256"], rb["bytes"]))})
    return {"what": "the weight files of the three arms: J6M and J6-tonight read the local model directory (one path, mounted read-only); J6N-tonight reads the NIM's own cache",
            "local_model_directory": "$P93_HF_HUB/models--" + HF_SG8["repo"].replace("/", "--") + "/snapshots/" + HF_SG8["revision"],
            "nim_cache_folder": "$NIM_CACHE_DIR/" + pred["weights"]["nim_cache_folder_below_the_cache"],
            "files": rows, "files_compared": len(rows), "all_same_bytes": bool(rows) and all(r["same_bytes"] for r in rows)}


def generic_command(name, image, env):
    snap = snapshot_dir()
    cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "--shm-size=64GB", "-p", "127.0.0.1:8000:8000", "--env-file", os.environ["NGC_ENV_FILE"]]
    shown = ["docker", "run", "-d", "--name", name, "--gpus", "all", "--shm-size=64GB", "-p", "127.0.0.1:8000:8000", "--env-file", "$NGC_ENV_FILE"]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]; shown += ["-e", f"{k}={v}"]
    cmd += ["-v", f"{snap}:{MODEL_AT}:ro", "-v", f"{os.environ['NIM_CACHE_DIR']}:{MOUNT}", image]
    shown += ["-v", f"$P93_HF_HUB/models--{HF_SG8['repo'].replace('/', '--')}/snapshots/{HF_SG8['revision']}:{MODEL_AT}:ro", "-v", f"$NIM_CACHE_DIR:{MOUNT}", image]
    return cmd, shown


def generic_utility(image, env, args, timeout, log_path):
    cmd = ["docker", "run", "--rm", "--name", PREFIX + "utility", "--gpus", "all", "--env-file", os.environ["NGC_ENV_FILE"]]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += ["-v", f"{snapshot_dir()}:{MODEL_AT}:ro", "-v", f"{os.environ['NIM_CACHE_DIR']}:{MOUNT}", image, *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        rc, text = r.returncode, scrub((r.stdout or "") + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        rc, text = 124, f"no end within {timeout} s\n"
    open(log_path, "w", encoding="utf-8", newline="\n").write(text)
    return rc, text


def rail_view():
    """The rail program writes to <results>/J6G/: a view whose J6G is a link to results/model_free_nim/J6M-rail/."""
    target = os.path.join(R.RESULTS, "J6M-rail"); os.makedirs(target, exist_ok=True)
    v = os.path.join(R.BUCKET, "views", "rail"); os.makedirs(v, exist_ok=True)
    R.link_dir(target, os.path.join(v, "J6G"))
    probe = os.path.join(v, "J6G", ".link_probe"); open(probe, "w").close()
    ok = os.path.isfile(os.path.join(target, ".link_probe")); os.remove(probe)
    if not ok:
        sys.exit("refused: the directory link of the rail cell does not point at its results folder")
    return v


def rail(a, *args):
    env = dict(os.environ, SG_NIM_RESULTS=rail_view(), SG_NIM_BUCKET=os.path.join(R.BUCKET, "rail"))
    cmd = [sys.executable, os.path.join(HERE, "safety_guard_nim_rail.py"), *args, "--prediction", a.prediction, "--gr-py", a.gr_py]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=R.CELL_TIMEOUT_S, env=env)
    except subprocess.TimeoutExpired:
        return 124, {"note": f"no end within {R.CELL_TIMEOUT_S} s"}
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        d = json.loads(line)
    except ValueError:
        d = {"note": "no JSON line from the harness", "stderr_tail": (r.stderr or "").strip()[-300:]}
    return r.returncode, d


def my_containers():
    return sh(["docker", "ps", "-a", "--filter", f"name={PREFIX}", "--format", "{{.Names}}"], timeout=60).stdout.split()


def card_state():
    s = g8_gate.sample()
    return {"gpu": gpu(), "ten_second_sample": {k: s[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")}, "containers_of_this_run_left": my_containers(),
            "containers_running": len(sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split())}


def start(step, key, cmd, shown, logdir, deadline, group, extra=None):
    """Gate, launch, record. -> (ready, launch record) or (None, reason) when the gate did not pass."""
    ok, g = gate_until(deadline)
    R.event(kind="g8", step=step, profile=key, before="container start", **{"pass": ok}, gate=g)
    if not ok:
        return None, "the idle-card gate did not pass before " + step
    name = PREFIX + step
    L = p102_run.launch(name, cmd, shown, logdir)
    log = scrub(docker_logs(name)); L.pop("startup_log_lines_about_the_argument", None)
    L["startup_log_lines_about_the_engine"] = [l.strip()[:300] for l in log.splitlines() if R.PROFILE_LINES.search(l)][:60]
    if not L.get("ready"):
        L["last_log_lines_as_they_are"] = [l[:400] for l in log.strip().splitlines()[-25:]]
    inspect = sh(["docker", "inspect", "--format", "{{.State.StartedAt}}", name], timeout=60).stdout.strip()
    R.event(kind="container_ready", step=step, profile=key, ready=L.get("ready"), seconds=L.get("seconds_to_verdict"), started_at_as_docker_reports=inspect, launch=L, gpu=gpu(), **(extra or {}))
    if L.get("ready"):
        R.event(kind="warm_up", step=step, versions=p102_run.server_versions(), **warm_up(group))
    return bool(L.get("ready")), L


def stop(step, logdir):
    name = PREFIX + step
    open(os.path.join(logdir, f"{name}.{int(time.time())}.container.log.txt"), "w", encoding="utf-8", newline="\n").write(scrub(docker_logs(name)))
    sh(["docker", "rm", "-f", name], timeout=180); time.sleep(10)
    R.event(kind="container_stopped", step=step, gpu=gpu())


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prediction", required=True); ap.add_argument("--gr-py", required=True); ap.add_argument("--steps", default="")
    ap.add_argument("--stop-at", default="08:00"); ap.add_argument("--dry-run", action="store_true")
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
    want = [x for x in a.steps.split(",") if x] or pred["plan"]
    plan = [s for s in ORDER if s in want and s in pred["plan"]]
    G = pred["serving"]["generic_nim"]; N = pred["serving"]["model_nim"]
    card_path, card_text = R.card_template_text()
    if R.sha256_text(card_text) != pred["prompt_template_sha256"]:
        sys.exit("refused: the model card's template is not the one the pre-registration names")
    if not os.path.isfile(os.path.join(snapshot_dir(), "config.json")):
        sys.exit("refused: the local model directory is not present")
    attempts = [(k, dict(G["start_settings"][k])) for k in G["order_of_the_start_settings"]]
    if a.dry_run:
        for arm in ("J6M", "J6-tonight", "J6N-tonight"):
            R.view(arm)
        rail_view()
        shown = {"J6M " + k: generic_command(PREFIX + "j6m_main", G["image"], env)[1] for k, env in attempts}
        shown["J6-tonight"] = p102_run.vllm_command(PREFIX + "vllm_tonight", HF_SG8)[1]
        shown["J6N-tonight"] = R.nim_command(PREFIX + "nim_tonight", N["image"], N["profile"])[1]
        print(json.dumps({"plan": plan, "views": "built and checked", "results": R.RESULTS, "commands": shown,
                          "images_present": {"generic": image_ok(G["image"], G["index_digest"]), "model_nim": image_ok(N["image"], N["index_digest"]), "vllm": image_ok(VLLM["image"], VLLM["digest"])},
                          "nim_cache_weights_present": os.path.isdir(nim_cache_weights(pred))}, indent=1)); return 0
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop_time = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop_time <= t:
        stop_time += datetime.timedelta(days=1)
    deadline = stop_time.timestamp(); t_start = time.time()
    os.makedirs(R.RESULTS, exist_ok=True); logdir = os.path.join(R.BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    R.EV = open(os.path.join(R.RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n"); p102_run.EV = R.EV
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split(); first = g8_gate.sample()
    R.event(kind="run_start", prediction_sha256=sha256_file(a.prediction), plan=plan, stop_at=a.stop_at, gpu=gpu(), other_containers_running=len(others), compute_processes_listed=first["compute_processes_listed"])
    if others:
        R.event(kind="run_end", reason="another container is running; nothing was started", rc=2); return 2
    for label, image, digest in (("generic", G["image"], G["index_digest"]), ("model_nim", N["image"], N["index_digest"]), ("vllm", VLLM["image"], VLLM["digest"])):
        if not image_ok(image, digest):
            R.event(kind="run_end", reason=f"the local {label} image does not carry the pinned digest", rc=2); return 2
    stopped = None; used_setting = None
    try:
        for step in plan:
            if time.time() > deadline:
                stopped = f"time limit reached before {step}"; break
            if step == "weights":
                t0 = time.time(); W = weight_table(pred)
                json.dump(W, open(os.path.join(R.RESULTS, "weights_sha256.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
                R.event(kind="weights", step=step, files_compared=W["files_compared"], all_same_bytes=W["all_same_bytes"], seconds=round(time.time() - t0)); continue
            if step == "profiles":
                rc, text = generic_utility(G["image"], attempts[0][1], ["list-model-profiles"], 900, os.path.join(logdir, "list_model_profiles.log.txt"))
                open(os.path.join(R.RESULTS, "list_model_profiles.txt"), "w", encoding="utf-8", newline="\n").write(text)
                R.event(kind="profiles", step=step, rc=rc, lines=len(text.splitlines()), text_sha256=R.sha256_text(text)); continue
            if step in ("j6m_main", "j6m_stability"):
                keys = attempts if step == "j6m_main" else [x for x in attempts if x[0] == used_setting]
                if step == "j6m_stability" and not keys:
                    done = [json.loads(l) for l in open(os.path.join(R.RESULTS, "events.jsonl"), encoding="utf-8") if l.strip()]
                    ok_keys = [e["profile"] for e in done if e.get("kind") == "container_ready" and e.get("step") == "j6m_main" and e.get("ready")]
                    keys = [x for x in attempts if ok_keys and x[0] == ok_keys[-1]]
                    if not keys:
                        R.event(kind="step_null", step=step, reason="no start setting became ready in j6m_main"); continue
                ready = False
                for key, env in keys:
                    cmd, shown = generic_command(PREFIX + step, G["image"], env)
                    ready, L = start(step, key, cmd, shown, logdir, deadline, "sg8_nim", {"start_setting": env})
                    if ready is None:
                        stopped = L; break
                    if ready:
                        used_setting = key; break
                    R.event(kind="start_setting_null", step=step, profile=key, reason=L.get("reason"), first_error_line=L.get("first_error_line"), a_result_for_this_step=True)
                    sh(["docker", "rm", "-f", PREFIX + step], timeout=120); time.sleep(10)
                if stopped:
                    break
                if not ready:
                    R.event(kind="step_null", step=step, reason="no start setting of the pre-registration reported ready"); continue
                if step == "j6m_main":
                    stopped = R.cells_of(a, step, PREFIX + step, "J6M", card_path, ["c1", "c16"], "", deadline)
                    if not stopped:
                        for track in ("input", "output"):
                            rc, d = rail(a, "precheck", "--track", track)
                            R.event(kind="precheck", step=step, arm="J6M-rail", track=track, rc=rc, **{"pass": rc == 0}, result=d)
                            if rc != 0:
                                R.event(kind="arm_track_null", step=step, arm="J6M-rail", track=track, reason="precheck failed"); continue
                            ok, g = gate_until(deadline)
                            R.event(kind="g8", step=step, arm="J6M-rail", track=track, mode="rail", before="cell", **{"pass": ok}, gate=g)
                            if not ok:
                                stopped = "the idle-card gate did not pass before the rail cell"; break
                            rc, d = rail(a, "cell", "--track", track)
                            after = g8_gate.sample()
                            R.event(kind="cell", step=step, arm="J6M-rail", track=track, mode="rail", rc=rc, result=d, gpu_after={k: after[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")})
                else:
                    stopped = R.cells_of(a, step, PREFIX + step, "J6M", card_path, ["stability"], "stability", deadline)
                stop(step, logdir)
            elif step == "vllm_tonight":
                cmd, shown, _ = p102_run.vllm_command(PREFIX + step, HF_SG8)
                ready, L = start(step, "upstream vLLM", cmd, shown, logdir, deadline, "sg8_vllm")
                if ready is None:
                    stopped = L; break
                if ready:
                    stopped = R.cells_of(a, step, PREFIX + step, "J6-tonight", card_path, ["c1", "c16"], "", deadline)
                else:
                    R.event(kind="step_null", step=step, reason=L.get("reason"), first_error_line=L.get("first_error_line"))
                stop(step, logdir)
            elif step == "nim_tonight":
                cmd, shown = R.nim_command(PREFIX + step, N["image"], N["profile"])
                ready, L = start(step, "generic profile of the model's NIM", cmd, shown, logdir, deadline, "sg8_nim")
                if ready is None:
                    stopped = L; break
                if ready:
                    stopped = R.cells_of(a, step, PREFIX + step, "J6N-tonight", card_path, ["c1", "c16"], "", deadline)
                else:
                    R.event(kind="step_null", step=step, reason=L.get("reason"), first_error_line=L.get("first_error_line"))
                stop(step, logdir)
            if stopped:
                break
    finally:
        for n in my_containers():
            sh(["docker", "rm", "-f", n], timeout=180)
        time.sleep(10)
        R.event(kind="card_after_the_run", **card_state())
    R.event(kind="run_end", reason=stopped or "plan complete", rc=0 if not stopped else 5, seconds=round(time.time() - t_start))
    return 0 if not stopped else 5


if __name__ == "__main__":
    sys.exit(main())
