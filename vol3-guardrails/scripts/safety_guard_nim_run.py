#!/usr/bin/env python3
"""Vol.3 · the Safety Guard 8B v3 model served by its NIM: the runner of the added arms. One container on the card at a
time, the idle-card gate before every start and every cell, each step written to events.jsonl as it happens.

The judge study asked this model through upstream vLLM (arm J6). Here the same items, subsets, prompt, parser and cells
are run against the model's NIM (1.14.0). The study's programs are used as they are, not edited: every cell below is
`p93_judge.py --arm J6` (the request shape of that arm) pointed at another server and another results folder.

  J6N       the NIM's generic profile (vLLM, BF16)                   the study's prompt (the model card's)
  J6N-fp8   an FP8 TensorRT-LLM profile built for RTX PRO 6000       the same prompt; throughput profile first, the
            Blackwell, pinned by id on this RTX 5090                 latency profile if that one does not start
  J6N-tpl   the generic profile                                      the template of the NIM's documentation (the model
                                                                     card's without 23 trailing blanks); c=1 and c=16
  J6G       the generic profile, through the NeMo Guardrails content-safety rail (safety_guard_nim_rail.py)

How the unchanged programs are pointed elsewhere: p93_judge.py reads P93_RESULTS (item table, subsets; it writes below
<P93_RESULTS>/J6/) and P93_BUCKET (texts, raw answers). For each arm this runner builds a small folder outside the
repository that holds copies of the two tables (compared by SHA-256 with the study's) and a directory link named J6 that
points at results/safety_guard_nim/<arm>/, so the arm's files land in its own folder.

Steps (a step that is not in the pre-registration's plan is not run):
  profiles          `list-model-profiles` in the image on this card; the text is kept in the results folder
  download          `download-to-cache --profile <id>` for the profiles of the plan (not timed)
  generic_main      J6N: per track precheck, c=1, c=16 · J6N-tpl: the same · J6G: per track precheck and the rail cell
  generic_stability J6N in a new container: per track precheck, the stability subset again
  fp8_main          J6N-fp8: per track precheck, c=1, c=16
  fp8_stability     J6N-fp8 in a new container: the stability subset again
A container that does not report ready is a result of its step: the reason and the first error line go to the events
file, the whole log to the folder outside the repository, and the runner goes on.
Containers are named sgnim_<step>. The NGC key file is passed by path and never read.

env: NGC_ENV_FILE · NIM_CACHE_DIR · P93_HF_HUB · SG_NIM_BUCKET (folder outside the repository)
usage: safety_guard_nim_run.py --prediction FILE --gr-py PY [--steps a,b,...] [--stop-at HH:MM] [--dry-run]
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
from p93_common import BUCKET as P93_BUCKET, CONTEXT, HF_SG8, RESULTS as P93_RESULTS, VOL, gpu, now, sh, sha256_file, sha256_text  # noqa: E402
from p93_run import docker_logs, gate_until, image_ok, scrub, warm_up  # noqa: E402
import p102_run  # noqa: E402
import g8_gate  # noqa: E402

RESULTS = os.environ.get("SG_NIM_RESULTS") or os.path.join(VOL, "results", "safety_guard_nim")
BUCKET = os.environ.get("SG_NIM_BUCKET") or os.path.join(os.path.dirname(VOL), "_internal", "safety_guard_nim_bucket")
P93_PRED = os.path.join(P93_RESULTS, "prediction_p93.json")
MOUNT = "/opt/nim/.cache"
CELL_TIMEOUT_S = 1800   # one precheck or one cell; a container has 1,800 s to report ready (p102_run.launch)
ORDER = ["profiles", "download", "generic_main", "generic_stability", "fp8_main", "fp8_stability"]
PROFILE_LINES = re.compile(r"profile|tensorrt|trt|vllm|engine|precision|fp8|bf16|compatib|selected|max_model_len|out of memory|CUDA|error", re.I)
EV = None


def event(**k):
    k = {"at": now(), **k}
    EV.write(json.dumps(k, ensure_ascii=False) + "\n"); EV.flush()
    print(json.dumps({x: k[x] for x in k if x in ("at", "kind", "step", "arm", "track", "mode", "pass", "rc", "reason", "ready", "seconds", "profile")}), flush=True)
    return k


def link_dir(target, link):
    """A directory link: a junction on Windows, a symbolic link elsewhere."""
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
    link_dir(arm_dir, os.path.join(v, "J6"))
    probe = os.path.join(v, "J6", ".link_probe"); open(probe, "w").close()
    ok = os.path.isfile(os.path.join(arm_dir, ".link_probe")); os.remove(probe)
    if not ok:
        sys.exit(f"refused: the directory link of {arm} does not point at its results folder")
    return v, b


def card_template_text():
    snap = os.path.join(os.environ["P93_HF_HUB"], "models--" + HF_SG8["repo"].replace("/", "--"), "snapshots", HF_SG8["revision"])
    path = os.path.join(snap, "inference_script.py")
    m = re.search(r'Template\("""(.*?)"""\)', open(path, encoding="utf-8").read(), re.S)
    if not m:
        sys.exit("the prompt template was not found in the model snapshot")
    return path, m.group(1)


def nim_doc_template(pred):
    """The documentation's template, made from the model card's by removing the blank that ends each category line.
    The result must render the two fixed test conversations to the SHA-256 values the pre-registration took from the
    documentation's own code. -> path of a file p93_judge.py can read with --sg8-template."""
    import jinja2
    _, card = card_template_text()
    doc, n = re.subn(r"(?m)^(S\d+: [^\n]*?) $", r"\1", card)
    want = pred["prompt_templates"]["nim_documentation"]
    if n != want["category_lines_changed"]:
        sys.exit(f"refused: {n} category lines end with a blank in the model card's template, {want['category_lines_changed']} expected")
    t = jinja2.Template(doc)
    got = {"input": sha256_text(t.render(query=want["test_query"], response=None)), "output": sha256_text(t.render(query=want["test_query"], response=want["test_response"]))}
    if got != want["rendered_sha256"]:
        sys.exit("refused: the derived template does not render the documentation's prompt")
    path = os.path.join(BUCKET, "nim_documentation_template.py.txt")
    open(path, "w", encoding="utf-8", newline="\n").write('Template("""' + doc + '""")\n')
    return path, sha256_text(doc)


def judge(a, arm, template, *args):
    v, b = view(arm)
    env = dict(os.environ, P93_RESULTS=v, P93_BUCKET=b)
    cmd = [sys.executable, os.path.join(HERE, "p93_judge.py"), *args, "--arm", "J6", "--prediction", P93_PRED, "--gr-py", a.gr_py, "--sg8-template", template]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=CELL_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 124, {"note": f"no end within {CELL_TIMEOUT_S} s"}
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        d = json.loads(line)
    except ValueError:
        d = {"note": "no JSON line from the harness", "stderr_tail": (r.stderr or "").strip()[-300:]}
    return r.returncode, d


def rail(a, *args):
    cmd = [sys.executable, os.path.join(HERE, "safety_guard_nim_rail.py"), *args, "--prediction", a.prediction, "--gr-py", a.gr_py]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=CELL_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 124, {"note": f"no end within {CELL_TIMEOUT_S} s"}
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        d = json.loads(line)
    except ValueError:
        d = {"note": "no JSON line from the harness", "stderr_tail": (r.stderr or "").strip()[-300:]}
    return r.returncode, d


def nim_command(name, image, profile):
    env = {"NIM_MODEL_PROFILE": profile, "NIM_MAX_MODEL_LEN": str(CONTEXT)}
    cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "--shm-size=64GB", "-p", "127.0.0.1:8000:8000", "--env-file", os.environ["NGC_ENV_FILE"]]
    shown = ["docker", "run", "-d", "--name", name, "--gpus", "all", "--shm-size=64GB", "-p", "127.0.0.1:8000:8000", "--env-file", "$NGC_ENV_FILE"]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]; shown += ["-e", f"{k}={v}"]
    cmd += ["-v", f"{os.environ['NIM_CACHE_DIR']}:{MOUNT}", image]; shown += ["-v", f"$NIM_CACHE_DIR:{MOUNT}", image]
    return cmd, shown


def utility(image, args, timeout, log_name, logdir):
    """One of the image's own utilities in a container that is removed afterwards. -> (rc, text without key lines)"""
    cmd = ["docker", "run", "--rm", "--gpus", "all", "--env-file", os.environ["NGC_ENV_FILE"], "-v", f"{os.environ['NIM_CACHE_DIR']}:{MOUNT}", image, *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        rc, text = r.returncode, scrub((r.stdout or "") + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        rc, text = 124, f"no end within {timeout} s\n"
    open(os.path.join(logdir, log_name), "w", encoding="utf-8", newline="\n").write(text)
    return rc, text


def card_state():
    s = g8_gate.sample()
    mine = sh(["docker", "ps", "-a", "--filter", "name=sgnim_", "--format", "{{.Names}}"], timeout=60).stdout.split()
    running = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    return {"gpu": gpu(), "ten_second_sample": {k: s[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")}, "sgnim_containers_left": mine, "containers_running": len(running)}


def cells_of(a, step, name, arm, template, modes, tag, deadline):
    """Per track: precheck, then each mode behind the gate. -> reason to stop the run, or None."""
    for track in ("input", "output"):
        rc, d = judge(a, arm, template, "precheck", "--track", track, *(["--tag", tag] if tag else []))
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
            rc, d = judge(a, arm, template, "cell", "--track", track, "--mode", mode)
            after = g8_gate.sample()
            event(kind="cell", step=step, arm=arm, track=track, mode=mode, rc=rc, result=d, gpu_after={k: after[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")},
                  container_alive=bool(sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=60).stdout.strip()))
    return None


def main():
    global EV
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prediction", required=True); ap.add_argument("--gr-py", required=True); ap.add_argument("--steps", default="")
    ap.add_argument("--stop-at", default="10:30"); ap.add_argument("--dry-run", action="store_true")
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
    S = pred["serving"]; image = S["image"]; P = S["profiles"]
    card_path, card_text = card_template_text()
    if sha256_text(card_text) != pred["prompt_templates"]["model_card"]["sha256"]:
        sys.exit("refused: the model card's template is not the one the pre-registration names")
    doc_path, doc_sha = nim_doc_template(pred)
    if a.dry_run:
        for arm in ("J6N", "J6N-fp8", "J6N-tpl"):
            view(arm)
        print(json.dumps({"plan": plan, "card_template_sha256": sha256_text(card_text), "nim_documentation_template_sha256": doc_sha, "views": "built and checked"})); return 0
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= t:
        stop += datetime.timedelta(days=1)
    deadline = stop.timestamp(); start = time.time()
    os.makedirs(RESULTS, exist_ok=True); logdir = os.path.join(BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    EV = open(os.path.join(RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    p102_run.EV = EV
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    first = g8_gate.sample()
    event(kind="run_start", prediction_sha256=sha256_file(a.prediction), plan=plan, stop_at=a.stop_at, gpu=gpu(), other_containers_running=len(others),
          compute_processes_listed=first["compute_processes_listed"], templates={"model_card_sha256": sha256_text(card_text), "nim_documentation_sha256": doc_sha})
    if others:
        event(kind="run_end", reason="another container is running; nothing was started", rc=2); return 2
    if not image_ok(image, S["index_digest"]):
        event(kind="run_end", reason="the local image does not carry the pinned digest", rc=2); return 2
    stopped = None
    try:
        for step in plan:
            if time.time() > deadline:
                stopped = f"time limit reached before {step}"; break
            if step == "profiles":
                rc, text = utility(image, ["list-model-profiles"], 900, "list_model_profiles.log.txt", logdir)
                open(os.path.join(RESULTS, "list_model_profiles.txt"), "w", encoding="utf-8", newline="\n").write(text)
                ids = {k: (v in text) for k, v in P.items()}
                event(kind="profiles", step=step, rc=rc, lines=len(text.splitlines()), profile_ids_in_the_listing=ids, text_sha256=sha256_text(text)); continue
            if step == "download":
                for key in pred["download"]:
                    t0 = time.time(); rc, text = utility(image, ["download-to-cache", "--profile", P[key]], 5400, f"download_{key}.log.txt", logdir)
                    event(kind="download", step=step, profile=key, rc=rc, seconds=round(time.time() - t0), last_line=(text.strip().splitlines() or [""])[-1][:300])
                continue
            kind, phase = step.split("_")
            keys = ["generic"] if kind == "generic" else pred["fp8_order"]
            arm = "J6N" if kind == "generic" else "J6N-fp8"
            name = f"sgnim_{step}"; L = None; used = None
            if kind == "fp8" and phase == "stability":
                done = [json.loads(l) for l in open(os.path.join(RESULTS, "events.jsonl"), encoding="utf-8") if l.strip()]
                ok_keys = [e["profile"] for e in done if e.get("kind") == "container_ready" and e.get("step") == "fp8_main" and e.get("ready")]
                if not ok_keys:
                    event(kind="step_null", step=step, reason="no FP8 profile became ready in fp8_main"); continue
                keys = [ok_keys[-1]]
            for key in keys:
                ok, g = gate_until(deadline)
                event(kind="g8", step=step, profile=key, before="container start", **{"pass": ok}, gate=g)
                if not ok:
                    stopped = f"the idle-card gate did not pass before {step}"; break
                cmd, shown = nim_command(name, image, P[key])
                L = p102_run.launch(name, cmd, shown, logdir)
                log = scrub(docker_logs(name))
                L["startup_log_lines_about_the_profile"] = [l.strip()[:300] for l in log.splitlines() if PROFILE_LINES.search(l)][:60]
                L.pop("startup_log_lines_about_the_argument", None)
                event(kind="container_ready", step=step, profile=key, profile_id=P[key], ready=L.get("ready"), seconds=L.get("seconds_to_verdict"), launch=L, gpu=gpu())
                if L.get("ready"):
                    used = key; break
                event(kind="profile_null", step=step, profile=key, reason=L.get("reason"), first_error_line=L.get("first_error_line"), a_result_for_this_step=True)
                sh(["docker", "rm", "-f", name], timeout=120); time.sleep(10)
            if stopped:
                break
            if not used:
                event(kind="step_null", step=step, reason="no profile of this step became ready"); continue
            event(kind="warm_up", step=step, versions=p102_run.server_versions(), **warm_up("sg8_nim"))
            if phase == "main":
                stopped = cells_of(a, step, name, arm, card_path, ["c1", "c16"], "", deadline)
                if not stopped and kind == "generic" and "J6N-tpl" in pred["arms"]:
                    stopped = cells_of(a, step, name, "J6N-tpl", doc_path, ["c1", "c16"], "", deadline)
                if not stopped and kind == "generic" and "J6G" in pred["arms"]:
                    for track in ("input", "output"):
                        rc, d = rail(a, "precheck", "--track", track)
                        event(kind="precheck", step=step, arm="J6G", track=track, rc=rc, **{"pass": rc == 0}, result=d)
                        if rc != 0:
                            event(kind="arm_track_null", step=step, arm="J6G", track=track, reason="precheck failed"); continue
                        ok, g = gate_until(deadline)
                        event(kind="g8", step=step, arm="J6G", track=track, mode="rail", before="cell", **{"pass": ok}, gate=g)
                        if not ok:
                            stopped = "the idle-card gate did not pass before J6G"; break
                        rc, d = rail(a, "cell", "--track", track)
                        after = g8_gate.sample()
                        event(kind="cell", step=step, arm="J6G", track=track, mode="rail", rc=rc, result=d, gpu_after={k: after[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")},
                              container_alive=bool(sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=60).stdout.strip()))
            else:
                stopped = cells_of(a, step, name, arm, card_path, ["stability"], "stability", deadline)
            open(os.path.join(logdir, f"{name}.{int(time.time())}.container.log.txt"), "w", encoding="utf-8", newline="\n").write(scrub(docker_logs(name)))
            sh(["docker", "rm", "-f", name], timeout=180); time.sleep(10)
            event(kind="container_stopped", step=step, gpu=gpu())
            if stopped:
                break
    finally:
        for n in sh(["docker", "ps", "-a", "--filter", "name=sgnim_", "--format", "{{.Names}}"], timeout=60).stdout.split():
            sh(["docker", "rm", "-f", n], timeout=180)
        time.sleep(10)
        event(kind="card_after_the_run", **card_state())
    event(kind="run_end", reason=stopped or "plan complete", rc=0 if not stopped else 5, seconds=round(time.time() - start))
    return 0 if not stopped else 5


if __name__ == "__main__":
    sys.exit(main())
