#!/usr/bin/env python3
"""Vol.2 · P78 G4 · Nemotron 3 Nano served by NIM 2.0.12 and by the upstream vLLM 0.27.1 it contains, on the same NVFP4
files: speed, time to a complete answer, whether the answers are the same text, and concurrency.

Arms, one container at a time, in this order in one session: N3 (NIM 2.0.12, NVFP4 profile, NIM_MAX_MODEL_LEN 16384),
V3B1 (upstream image, model path only: what a user gets without knowing the settings), V3B2 (upstream image with NIM's own
vLLM argument list for N3's configuration, read from `nim-serve --dry-run`; p78_engines.upstream_args_from lists the only
edits). For each upstream start the log's values of mamba_ssm_cache_dtype, the MoE backend, the CUDA-graph mode and
max_num_seqs are recorded (p78_engines.TRAPS), and B2's flags are counted: how many NIM passes that B1 lacks.
Per arm:
  warm   requests until the single-stream rate reaches 220 tok/s (Nemotron 3 Nano's first-minute slow phase, P55) or 300 s
  single the 50 questions of the co-residence sample (p53_answer's request: max_tokens 4096, temperature 0, top_p 0.9,
         streamed with usage, reasoning channel counted; no text stored, response sha256 kept), in fixed order; then the
         first 10 again on the same engine (self-repeat control for the answers-identical comparison)
  conc   p53_concurrency_v2's level runner (AIPerf 0.11.0, profile C, --use-server-token-count, warm-up requests = N),
         a discarded 120 s level at c=1, then 1, 8, 32, 64, 128 at 60 s each, each after G8
A start that fails is a result (its first error line and the trap values are recorded) and that arm's measurements are
skipped. The answers-identical comparison is response sha256 per question across arms. The quality arms run separately
(p78_quality.py --arms V3B1,V3B2, reasoning off x GSM8K, the same settings as N3's cell).
usage: p78_nim_vs_vllm.py --aiperf EXE --tokenizer DIR [--out DIR] [--arms N3,V3B1,V3B2] [--test]
env: NGC_ENV_FILE (NIM only, --env-file, never read) · NIM_CACHE_DIR · V_CACHE_DIR
"""
import argparse, datetime, json, os, statistics as st, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))
import p78_engines as E  # noqa: E402
import p78_quality as Q  # noqa: E402
import p53_answer as A  # noqa: E402
import p53_concurrency_v2 as C2  # noqa: E402
import g8_gate as G  # noqa: E402
import host_gate as HG  # noqa: E402
import overwrite_gate as O  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_OUT = os.path.join(HERE, "..", "results", "p78_nim_vs_vllm")
SAMPLE = next(os.path.join(REPO, d, "results", "p20_coresidence", "sample.json") for d in sorted(os.listdir(REPO))
              if os.path.exists(os.path.join(REPO, d, "results", "p20_coresidence", "sample.json")))   # found, not written: its volume was renamed twice
QFILE = os.path.join(REPO, "benchmark", "questions.json")
LEVELS = [1, 8, 32, 64, 128]
now = Q.now


def questions(test=False):
    """p50_speed's order: the sample's run_order (harness_test_questions in a test), questions from benchmark/questions.json."""
    s = json.load(open(SAMPLE, encoding="utf-8")); bank = {q["id"]: q for q in json.load(open(QFILE, encoding="utf-8"))}
    return [bank[x["id"]] for x in (s["harness_test_questions"] if test else s["run_order"])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aiperf", required=True); ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--out", default=DEFAULT_OUT); ap.add_argument("--arms", default="N3,V3B1,V3B2"); ap.add_argument("--test", action="store_true")
    a = ap.parse_args(); a.out = os.path.abspath(a.out); a.tokenizer_root = None
    os.makedirs(a.out, exist_ok=True); logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    O.SCOPES = O.SCOPES + sorted(d for d in os.listdir(REPO) if d.startswith("vol") and d not in O.SCOPES)
    snap = O.snapshot(REPO, [os.path.relpath(a.out.split(os.sep + "harness_test")[0], REPO).replace(os.sep, "/")])   # the stage's results directory (its logs/ and harness_test/ included)
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    event = lambda **kw: (ev.write(json.dumps({**kw, "at": now()}, ensure_ascii=False) + "\n"), ev.flush())
    lv = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    rq = open(os.path.join(a.out, "requests.jsonl"), "a", encoding="utf-8", newline="\n")
    event(kind="run_start", arms=a.arms, test=a.test, sample=os.path.relpath(SAMPLE, REPO).replace(os.sep, "/"), host_calibration=HG.calibrate(),
          engines_self_test=E.self_test()["pass"])
    if E.sh(["docker", "ps", "-q"], 30).stdout.strip():
        sys.exit("refused: a container is running")
    # p53_concurrency_v2's AIPerf command, flag for flag, with one tokenizer directory for every arm (all three serve the
    # same files); run_level looks the name up in its module at call time
    C2.aiperf_cmd = lambda a_, model, arm, prof, n, dur, art: [
        a.aiperf, "profile", "-m", model, "--endpoint-type", "chat", "--streaming", "-u", E.BASE,
        "--tokenizer", a.tokenizer, *C2.PROFILE_ARGS[prof], "--extra-inputs", "temperature:0",
        "--concurrency", str(n), "--warmup-request-count", str(n), "--benchmark-duration", str(dur),
        "--benchmark-grace-period", "0", "--use-server-token-count", "--no-gpu-telemetry", "--ui-type", "none",
        "--random-seed", str(20260921 + n), "--artifact-dir", art]
    qs = questions(a.test)
    b2_args = None
    for arm in a.arms.split(","):
        print(f"##### arm {arm} {now()}", flush=True)
        args = []
        if arm == "V3B2":
            d = E.dryrun("N3", {"NIM_MAX_MODEL_LEN": Q.MAX_MODEL_LEN}, os.path.join(logdir, "dryrun_N3.txt"))
            args, edits = E.upstream_args_from(d["backend_args"] or [], E.IMAGES["V3B2"]["snapshot"]); b2_args = args
            event(kind="dryrun", selected_profile=d.get("selected_profile"), resolved_config=d.get("resolved_config"), backend_args=d.get("backend_args"),
                  upstream_args=args, edits=edits, flags_added_over_bare=len([t for t in args if t.startswith("--")]), rc=d.get("rc"))
            if not d.get("backend_args"):
                event(kind="arm_null", arm=arm, reason="the NIM dry-run gave no argument list"); continue
        name = f"p78g4-{arm.lower()}"
        st_ = E.launch(arm, name, logdir, env={"NIM_MAX_MODEL_LEN": Q.MAX_MODEL_LEN} if arm == "N3" else None, args=args)
        event(kind="engine_start", arm=arm, start={k: v for k, v in st_.items() if k != "log_lines"}, log_lines=st_.get("log_lines"))
        print(f"  {arm}: ready={st_['ready']} traps={st_.get('traps')} {st_.get('first_error_line') or ''}", flush=True)
        if not st_["ready"]:
            E.save_logs(name, logdir); E.stop(name); continue
        model = E.served_model()
        health = Q.warm_and_health(arm, model)
        event(kind="health", arm=arm, model=model, **health)
        if not health["pass"]:
            event(kind="arm_null", arm=arm, reason="arm health below 10% of peak bandwidth"); E.save_logs(name, logdir); E.stop(name); continue
        # single stream, 50 questions
        g8 = G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S); event(kind="g8", arm=arm, cell="single", **g8)
        if g8["pass"]:
            hg = HG.cell_start()
            # the 50 questions, then the first 10 again on the same engine: the self-repeat control. If the same engine does
            # not repeat its own text, a difference between engines is not evidence of an engine difference.
            for rep, part in ((0, qs), (1, qs[: (2 if a.test else 10)])):
                for i, q in enumerate(part):
                    r = A.request(model, q["text"]); r.update({"arm": arm, "repeat": rep, "position": i, "question_id": q["id"], "at": now()})
                    rq.write(json.dumps(r, ensure_ascii=False) + "\n"); rq.flush()
                    time.sleep(2)
            event(kind="host_cell", arm=arm, cell="single", **HG.cell_end(hg))
        else:
            event(kind="cell_null", arm=arm, cell="single", reason="G8 did not pass within the wait limit")
        # concurrency
        warm = C2.run_level(a, model, arm, "C", 1, 20 if a.test else 120, os.path.join(a.out, f"{arm}_C", "warmup", "c0001"), "main", lv, {"warmup": True})
        for n in ([1] if a.test else LEVELS):
            if warm.get("engine_dead"):
                break
            g8 = G.gate(max_wait_s=120 if a.test else G.MAX_WAIT_S); event(kind="g8", arm=arm, cell=f"c{n}", **g8)
            if not g8["pass"]:
                event(kind="cell_null", arm=arm, cell=f"c{n}", reason="G8 did not pass within the wait limit"); continue
            hg = HG.cell_start()
            rec = C2.run_level(a, model, arm, "C", n, 20 if a.test else 60, os.path.join(a.out, f"{arm}_C", f"c{n:04d}"), "main", lv, {"g8_waited_s": g8["waited_s"]})
            event(kind="host_cell", arm=arm, cell=f"c{n}", **HG.cell_end(hg))
            ov = O.check(snap); event(kind="overwrite_check", arm=arm, cell=f"c{n}", **ov)
            if not ov["pass"]:
                print(f"  NO-OVERWRITE GATE FAILED after {arm} c={n}", flush=True); E.save_logs(name, logdir); E.stop(name); return 4
            if rec["engine_dead"]:
                break
        E.save_logs(name, logdir); E.stop(name)
        event(kind="engine_end", arm=arm, gpu_after_stop=E.gpu())
    # answers-identical table (response sha256 per question across arms)
    rows = [json.loads(l) for l in open(os.path.join(a.out, "requests.jsonl"), encoding="utf-8")]
    by, rep = {}, {}
    for r in rows:
        (by if not r.get("repeat") else rep).setdefault(r["question_id"], {})[r["arm"]] = r.get("response_sha256")
    arms = a.arms.split(",")
    same = {f"{x}=={y}": sum(1 for v in by.values() if v.get(x) and v.get(x) == v.get(y)) for i, x in enumerate(arms) for y in arms[i + 1:]}
    self_same = {x: {"repeated": sum(1 for q in rep if rep[q].get(x)), "identical": sum(1 for q in rep if rep[q].get(x) and rep[q][x] == (by.get(q) or {}).get(x))} for x in arms}
    event(kind="answers_identical", questions=len(by), pairs=same, self_repeat=self_same, b2_args=b2_args)
    print("answers identical:", same, "self-repeat:", self_same, flush=True)
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
