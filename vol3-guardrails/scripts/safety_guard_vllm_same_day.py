#!/usr/bin/env python3
"""Vol.3 · the study's arm J6 once more, on the day of the NIM arms: the same model on upstream vLLM (the pinned image
and model snapshot of the study), the same prompt, items, subsets and program. Written after the NIM arms ran, because
their records showed a second difference from the study's J6 besides the serving package: the graphics driver of the
host had changed between the two days (591.86 on 2026-10-02, 610.88 on 2026-10-06). This arm, J6-today, differs from
J6N in the serving package only, and from the study's J6 in the day and the driver only.

It is not bound by the frozen pre-registration of the NIM arms; its SHA-256 and its expectation (written before the
container starts) are in addendum_same_day_vllm.json and in the events file. Everything it runs is the frozen programs:
the container command of p102_run.py, the cells of safety_guard_nim_run.py (which call p93_judge.py --arm J6).

  cells   per track: precheck, c=1 on the 200-item subset, c=16 on the whole track. No stability rerun.
env: P93_HF_HUB · SG_NIM_BUCKET · NGC_ENV_FILE and NIM_CACHE_DIR (read by the modules it imports; not used here)
usage: safety_guard_vllm_same_day.py --gr-py PY [--stop-at HH:MM]
       safety_guard_vllm_same_day.py --summary       (after the cells: J6-today's summary and a three-line table)
"""
import argparse, datetime, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
from p93_common import HF_SG8, VLLM, gpu, sh, sha256_file  # noqa: E402
from p93_run import docker_logs, gate_until, image_ok, scrub, warm_up  # noqa: E402
import p102_run  # noqa: E402
import safety_guard_nim_run as R  # noqa: E402

ARM = "J6-today"; NAME = "sgnim_vllm_same_day"


def summary():
    """J6-today's summary by the study's analysis program, and one table: the study's J6, J6-today, J6N (summaries only)."""
    import safety_guard_nim_summary as S
    arms = {"J6 (the study, 2026-10-02: upstream vLLM)": json.load(open(os.path.join(S.P93_RESULTS, "J6", "summary.json"), encoding="utf-8")),
            "J6-today (upstream vLLM)": S.direct_summary(ARM), "J6N (the NIM's generic profile)": json.load(open(os.path.join(R.RESULTS, "J6N", "summary.json"), encoding="utf-8"))}
    rows = [S.line(n, x, track, group) for n, x in arms.items() for track, group in (("input", "aegis2"), ("input", "xstest"), ("output", "aegis2"))]
    json.dump({"what": "the same model, prompt, items and program on three servers; built from each arm's summary.json only", "rows": rows},
              open(os.path.join(R.RESULTS, "table_same_day.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    md = ["| Arm | Track · data | Detection | False alarm | c=1 p50 ms | c=16 verdicts/s | c=16 p99 ms |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['arm']} | {r['track']} · {r['group']} | {S.pct(r['detection'])} | {S.pct(r['false_alarm'])} | {S.num(r['c1_latency_ms_p50'])} | {S.num(r['c16_verdicts_per_s'])} | {S.num(r['c16_latency_ms_p99'])} |" for r in rows if r["usable"]]
    open(os.path.join(R.RESULTS, "table_same_day.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--summary" in sys.argv:
        return summary()
    ap = argparse.ArgumentParser(); ap.add_argument("--gr-py", required=True); ap.add_argument("--stop-at", default="10:30"); a = ap.parse_args()
    add = os.path.join(R.RESULTS, "addendum_same_day_vllm.json")
    A = json.load(open(add, encoding="utf-8"))
    if A["program_sha256"] != sha256_file(os.path.abspath(__file__)):
        sys.exit("refused: this program is not the one the addendum names")
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= t:
        stop += datetime.timedelta(days=1)
    deadline = stop.timestamp(); start = time.time()
    logdir = os.path.join(R.BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    R.EV = open(os.path.join(R.RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    R.event(kind="run_start", step="vllm_same_day", addendum_sha256=sha256_file(add), program_sha256=A["program_sha256"], gpu=gpu(), other_containers_running=len(others))
    if others:
        R.event(kind="run_end", step="vllm_same_day", reason="another container is running; nothing was started", rc=2); return 2
    card_path, _ = R.card_template_text()
    stopped = None
    try:
        cmd, shown, snap = p102_run.vllm_command(NAME, HF_SG8)
        if not image_ok(VLLM["image"], VLLM["digest"]) or not os.path.isfile(os.path.join(snap, "config.json")):
            R.event(kind="step_null", step="vllm_same_day", reason="the pinned vLLM image or the model snapshot is not present"); return 2
        ok, g = gate_until(deadline)
        R.event(kind="g8", step="vllm_same_day", before="container start", **{"pass": ok}, gate=g)
        if not ok:
            stopped = "the idle-card gate did not pass"
        else:
            L = p102_run.launch(NAME, cmd, shown, logdir)
            L.pop("startup_log_lines_about_the_argument", None)
            R.event(kind="container_ready", step="vllm_same_day", profile="upstream vLLM", ready=L.get("ready"), seconds=L.get("seconds_to_verdict"), launch=L, gpu=gpu())
            if not L.get("ready"):
                R.event(kind="step_null", step="vllm_same_day", reason=L.get("reason"))
            else:
                R.event(kind="warm_up", step="vllm_same_day", versions=p102_run.server_versions(), **warm_up("sg8_vllm"))
                stopped = R.cells_of(a, "vllm_same_day", NAME, ARM, card_path, ["c1", "c16"], "", deadline)
                open(os.path.join(logdir, f"{NAME}.{int(time.time())}.container.log.txt"), "w", encoding="utf-8", newline="\n").write(scrub(docker_logs(NAME)))
    finally:
        sh(["docker", "rm", "-f", NAME], timeout=180); time.sleep(10)
        R.event(kind="card_after_the_run", step="vllm_same_day", **R.card_state())
    R.event(kind="run_end", step="vllm_same_day", reason=stopped or "plan complete", rc=0 if not stopped else 5, seconds=round(time.time() - start))
    return 0 if not stopped else 5


if __name__ == "__main__":
    sys.exit(main())
