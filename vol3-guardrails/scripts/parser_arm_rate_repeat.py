#!/usr/bin/env python3
"""Vol.3 · the whole-track cell at 16 in flight, once more for the parser arm in a new container (J2P-repeat), and the
same cell for the study's arm J2 on the same day (J2-today: the same NIM start without the parser argument).

Why. In the parser arm's run the whole-track cells gave 4.8 and 4.4 verdicts per second, half of the study's J2 (9.4
and 8.1, measured four days earlier with another graphics driver), while the same setting in the run's second
container judged the stability subsets at J2's rate, and the cells with one call at a time took as long as J2's. One
container's cells cannot say whether that is the parser, the day, or that container. These two arms can.

Cells: per arm one container; per track the precheck of that arm (J2P-repeat: as in addendum_parser_arm_precheck.json,
the study's controls and the server check; J2-today: the study's precheck unchanged) and the cell `p93_judge.py --arm
J2 cell --mode c16`. No cell with one call at a time, no stability rerun. Then a summary of each arm from its own
files with the study's functions, and one table of rates.
usage: parser_arm_rate_repeat.py --prediction FILE --addendum FILE --gr-py PY [--stop-at HH:MM] [--dry-run]
       --addendum: addendum_rate_repeat.json (frozen before the first container of this program)
"""
import argparse, datetime, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
import parser_and_engine_version_run as base  # noqa: E402
import parser_arm_run as pa  # noqa: E402
import p93_analyze as study  # noqa: E402
import p102_run  # noqa: E402
from p93_common import NIM_N3, RESULTS as P93_RESULTS, gpu, read_jsonl, sh, sha256_file  # noqa: E402
from p93_run import docker_logs, gate_until, image_ok, scrub, warm_up  # noqa: E402

RESULTS = base.RESULTS
ARMS = {"J2P-repeat": {"env": {"NIM_PASSTHROUGH_ARGS": p102_run.PASSTHROUGH}, "precheck": "addendum"}, "J2-today": {"env": {}, "precheck": "study"}}
for _arm in ARMS:
    base.SHAPE[_arm] = "J2"


def usable(arm, track):
    d = os.path.join(RESULTS, arm); p = os.path.join(d, f"precheck_{track}.json")
    if not os.path.isfile(p):
        return False, {"missing": True}
    pre = json.load(open(p, encoding="utf-8")); rec = {"study_precheck": {k: pre.get(k) for k in ("controls_pass", "reasoning_switch", "pass", "at")}}
    if ARMS[arm]["precheck"] == "study":
        return bool(pre.get("pass")), rec
    s = os.path.join(d, f"server_check_{track}.json")
    if not os.path.isfile(s):
        return False, rec
    sc = json.load(open(s, encoding="utf-8")); rec["server_check"] = {k: sc.get(k) for k in ("answers_with_reasoning_content", "answers_with_a_think_tag_in_the_content", "of", "pass", "at")}
    return bool(pre.get("controls_pass")) and bool(sc.get("pass")), rec


def cells_of(a, step, name, arm, deadline):
    for track in ("input", "output"):
        rc, d = base.run_study_program("p93_judge.py", arm, a.gr_py, "precheck", "--track", track)
        base.event(kind="precheck", step=step, arm=arm, track=track, rc=rc, controls_pass=d.get("controls_pass"), study_verdict=d.get("pass"), result=d)
        if ARMS[arm]["precheck"] == "addendum":
            pa.ARM, pa.ARM_DIR = arm, os.path.join(RESULTS, arm)
            sc = pa.server_check(track, "")
            base.event(kind="server_check", step=step, arm=arm, track=track, **{"pass": sc["pass"]}, with_reasoning_field=sc["answers_with_reasoning_content"], think_tags=sc["answers_with_a_think_tag_in_the_content"])
        ok, _ = usable(arm, track)
        if not ok:
            base.event(kind="arm_track_null", step=step, arm=arm, track=track, reason="the precheck of this arm did not pass"); continue
        if time.time() > deadline:
            return f"time limit reached before {arm}/{track}"
        g_ok, g = gate_until(deadline)
        base.event(kind="g8", step=step, arm=arm, track=track, mode="c16", before="cell", **{"pass": g_ok}, gate=g)
        if not g_ok:
            return f"the idle-card gate did not pass before {arm}/{track}"
        before = gpu()
        rc, d2 = base.run_study_program("p93_judge.py", arm, a.gr_py, "cell", "--track", track, "--mode", "c16")
        base.event(kind="cell", step=step, arm=arm, track=track, mode="c16", rc=rc, result=d2, gpu_before=before, gpu_after=gpu(),
                   container_alive=bool(sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=60).stdout.strip()))
    return None


def summarize():
    items = read_jsonl(os.path.join(P93_RESULTS, "items.jsonl")); rows_out = []
    for arm in ARMS:
        d = os.path.join(RESULTS, arm); cp = os.path.join(d, "cells.jsonl")
        cells = {(c["track"], c["mode"]): c for c in (read_jsonl(cp) if os.path.isfile(cp) else []) if not c.get("limit")}
        S = {"arm": arm, "request_shape_of": "J2", "server": ("NIM_PASSTHROUGH_ARGS=" + p102_run.PASSTHROUGH) if ARMS[arm]["env"] else "no extra argument", "precheck_rule": ARMS[arm]["precheck"], "tracks": {}, "files_read": []}
        for track in ("input", "output"):
            ok, rec = usable(arm, track); p = os.path.join(d, f"{track}_c16.jsonl"); c = cells.get((track, "c16"), {}); T = {"precheck": rec}
            T["usable"] = ok and os.path.isfile(p) and bool(c.get("complete"))
            if T["usable"]:
                rows = read_jsonl(p); S["files_read"].append({"file": os.path.basename(p), "sha256": sha256_file(p)})
                gold_key = "gold_input" if track == "input" else "gold_output"
                gold = {it["item_id"]: it[gold_key] for it in items if track in it["tracks"] and it["dataset"] == "aegis2"}
                T["quality"] = {"aegis2": study.quality(rows, gold)}; T["quality_cell"] = {"mode": "c16", **study.timing(rows, c)}
                T["card_mib_at_start_and_end"] = [(c.get("gpu_start") or {}).get("used_mib"), (c.get("gpu_end") or {}).get("used_mib")]
                q = T["quality"]["aegis2"]; t = T["quality_cell"]
                rows_out.append({"arm": arm, "track": track, "calls": t["calls"], "wall_s": t["wall_s"], "verdicts_per_s": t["verdicts_per_s"], "completion_tokens_per_s": t["completion_tokens_per_s"],
                                 "completion_tokens_p50": t["completion_tokens"]["p50"], "latency_ms_p99": t["latency_ms"]["p99"], "window": t["window"], "card_mib": T["card_mib_at_start_and_end"],
                                 "detection": q["detection"], "false_alarm": q["false_alarm"], "rail": q.get("rail"), "no_verdict": q["no_verdict"]})
            S["tracks"][track] = T
        if os.path.isdir(d):
            json.dump(S, open(os.path.join(d, "summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    json.dump({"what": "the whole-track cell at 16 in flight of two arms measured on 2026-10-06; one line per arm and track, each from that arm's own files", "rows": rows_out},
              open(os.path.join(RESULTS, "rate_repeat.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    for r in rows_out:
        print(f"{r['arm']} {r['track']}: {r['verdicts_per_s']:.2f} verdicts/s · {r['completion_tokens_per_s']:.0f} tokens/s · wall {r['wall_s']:.0f} s · detection {r['detection']['k']}/{r['detection']['n']} · "
              f"false alarm {r['false_alarm']['k']}/{r['false_alarm']['n']} · card {r['card_mib']}")
    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prediction", required=True); ap.add_argument("--addendum", required=True); ap.add_argument("--gr-py", required=True)
    ap.add_argument("--stop-at", default="08:00"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--summary-only", action="store_true")
    a = ap.parse_args()
    for v in ("NGC_ENV_FILE", "NIM_CACHE_DIR", "P93_HF_HUB"):
        if not os.environ.get(v):
            sys.exit(f"{v} is not set")
    add = json.load(open(a.addendum, encoding="utf-8"))
    for path in (a.prediction, a.addendum):
        side = os.path.splitext(path)[0] + ".sha256"
        if not os.path.isfile(side) or open(side, encoding="utf-8").read().split()[0] != sha256_file(path):
            sys.exit(f"refused: {os.path.basename(path)} does not match its .sha256 file")
    if add["supplements"]["sha256"] != sha256_file(a.prediction):
        sys.exit("refused: the addendum does not belong to this pre-registration")
    if a.dry_run:
        for arm in ARMS:
            base.view(arm)
        print(json.dumps({"arms": list(ARMS), "views": "built and checked", "n3_image_present": image_ok(NIM_N3["image"], NIM_N3["index_digest"])})); return 0
    for f, h in add["harness_sha256"].items():
        if sha256_file(os.path.join(HERE, f)) != h:
            sys.exit(f"refused: {f} is not the file the addendum binds")
    if a.summary_only:
        return summarize()
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= t:
        stop += datetime.timedelta(days=1)
    deadline = stop.timestamp(); start = time.time()
    logdir = os.path.join(base.BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    base.EV = open(os.path.join(RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    base.event(kind="run_start", program=os.path.basename(__file__), addendum_sha256=sha256_file(a.addendum), plan=list(ARMS), stop_at=a.stop_at, gpu=gpu(), other_containers_running=len(others))
    if others:
        base.event(kind="run_end", reason="another container is running; nothing was started", rc=2); return 2
    stopped = None
    try:
        for arm, spec in ARMS.items():
            if time.time() > deadline:
                stopped = f"time limit reached before {arm}"; break
            step = "rate_" + arm.lower().replace("-", "_"); name = f"vol3fu_{step}"
            cmd, shown = p102_run.nim_command(name, NIM_N3, spec["env"])
            ok, g = gate_until(deadline)
            base.event(kind="g8", step=step, before="container start", **{"pass": ok}, gate=g)
            if not ok:
                stopped = f"the idle-card gate did not pass before {arm}"; break
            L = p102_run.launch(name, cmd, shown, logdir)
            base.event(kind="container_ready", step=step, arm=arm, ready=L.get("ready"), seconds=L.get("seconds_to_verdict"), launch=L, gpu=gpu())
            if not L.get("ready"):
                base.event(kind="step_null", step=step, reason=L.get("reason"), first_error_line=L.get("first_error_line"))
                sh(["docker", "rm", "-f", name], timeout=120); time.sleep(10); continue
            base.event(kind="warm_up", step=step, versions=p102_run.server_versions(), **warm_up("n3_nim"))
            stopped = cells_of(a, step, name, arm, deadline)
            open(os.path.join(logdir, f"{name}.{int(time.time())}.container.log.txt"), "w", encoding="utf-8", newline="\n").write(scrub(docker_logs(name)))
            sh(["docker", "rm", "-f", name], timeout=180); time.sleep(10)
            base.event(kind="container_stopped", step=step, gpu=gpu())
            if stopped:
                break
    finally:
        for n in sh(["docker", "ps", "-a", "--filter", "name=vol3fu_", "--format", "{{.Names}}"], timeout=60).stdout.split():
            sh(["docker", "rm", "-f", n], timeout=180)
        time.sleep(10)
        base.event(kind="card_after_the_run", **base.card_state())
    base.event(kind="run_end", reason=stopped or "plan complete", rc=0 if not stopped else 5, seconds=round(time.time() - start))
    if not stopped:
        summarize()
    return 0 if not stopped else 5


if __name__ == "__main__":
    sys.exit(main())
