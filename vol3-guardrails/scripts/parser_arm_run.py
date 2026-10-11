#!/usr/bin/env python3
"""Vol.3 · the parser arm (J2P) run under the addendum to its pre-registration.

Why this file exists. The first run of J2P started two containers and ran no cell: the study's precheck for an arm
with reasoning on requires that at least 9 of 10 harmless answers show their reasoning in what the NeMo Guardrails
action returns. With `--reasoning-parser nemotron_v3` on the server the reasoning is moved out of the answer, which is
the change this arm is about, so that rule cannot pass here (0 of 10), while the two controls did what they should
(the violating control blocked, the harmless one allowed). The bound runner treats a failed precheck as "no cell".

What is different here, and only this (addendum_parser_arm_precheck.json, frozen before the first container of this
program):
  * the study's precheck still runs and is kept as it is written; of its verdict this program uses `controls_pass`
  * the reasoning switch is checked on the server instead: the study's ten harmless prompts are sent directly with
    enable_thinking true; at least 9 of 10 answers must carry a non-empty reasoning field in the message (`reasoning`
    or `reasoning_content`, whichever the server uses) and none may carry a think tag in its content
    (server_check_<track>[_stability].json)
  * a track is usable when the study's controls pass, the server check passes, and the whole-track cell is complete
Everything else is the first plan: the same container start, `p93_judge.py --arm J2` for every cell, the study's
definitions for every figure (the functions of p93_analyze.py are called; its `main` is not, because it reads the
study's precheck verdict), one arm's files only.

Steps: parser_main (per track: precheck, server check, c=1, c=16) · parser_stability (a new container: per track
precheck, server check, the stability subset) · summary (no container: J2P/summary.json, rail_beside_verdict.json and
the table with the arms already measured).
usage: parser_arm_run.py --prediction FILE --addendum FILE --gr-py PY [--steps a,b] [--stop-at HH:MM] [--dry-run]
"""
import argparse, datetime, json, os, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
import parser_and_engine_version_run as base  # noqa: E402
import p93_analyze as study  # noqa: E402
import p102_run  # noqa: E402
import g8_gate  # noqa: E402
from p93_common import BASE, NIM_N3, RESULTS as P93_RESULTS, TEMPERATURE, gpu, now, read_jsonl, sh, sha256_file  # noqa: E402
from p93_run import docker_logs, gate_until, image_ok, scrub, warm_up  # noqa: E402

ARM, SHAPE = "J2P", "J2"
RESULTS = base.RESULTS; ARM_DIR = os.path.join(RESULTS, ARM)
ORDER = ["parser_main", "parser_stability", "summary"]
MIN_WITH_REASONING = 9


def server_check(track, tag):
    """The reasoning switch, seen on the server: the study's ten harmless prompts, sent directly."""
    prompts = json.load(open(base.P93_PRED, encoding="utf-8"))["toggle_prompts"]
    model = requests.get(BASE + "/v1/models", timeout=60).json()["data"][0]["id"]; rows = []
    for i, prompt in enumerate(prompts, 1):
        try:
            r = requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1024, "temperature": TEMPERATURE,
                                                                  "chat_template_kwargs": {"enable_thinking": True}}, timeout=600)
            d = r.json() if r.status_code == 200 else {}
        except requests.RequestException as e:
            rows.append({"prompt": i, "http": None, "error": type(e).__name__}); continue
        ch = (d.get("choices") or [{}])[0]; msg = ch.get("message") or {}; content = msg.get("content") or ""; rc = msg.get("reasoning_content") or msg.get("reasoning") or ""
        rows.append({"prompt": i, "http": r.status_code, "message_keys": sorted(msg.keys()), "reasoning_field": "reasoning_content" if msg.get("reasoning_content") else "reasoning" if msg.get("reasoning") else None,
                     "reasoning_content_chars": len(rc), "content_chars": len(content),
                     "content_has_think_tag": "</think>" in content or "<think>" in content, "finish_reason": ch.get("finish_reason"), "completion_tokens": (d.get("usage") or {}).get("completion_tokens")})
    with_r = sum(1 for x in rows if x.get("reasoning_content_chars", 0) > 0); tags = sum(1 for x in rows if x.get("content_has_think_tag"))
    rec = {"arm": ARM, "track": track, "at": now(), "model": model, "request": "one user turn, max_tokens 1024, temperature 0, chat_template_kwargs.enable_thinking true; the study's ten harmless prompts",
           "answers_with_reasoning_content": with_r, "answers_with_a_think_tag_in_the_content": tags, "of": len(rows),
           "rule": f"at least {MIN_WITH_REASONING} of {len(rows)} with a non-empty reasoning field of the message (`reasoning` or `reasoning_content`), none with a think tag in the content", "rows": rows,
           "pass": len(rows) == len(prompts) and with_r >= MIN_WITH_REASONING and tags == 0}
    json.dump(rec, open(os.path.join(ARM_DIR, f"server_check_{track}{'_' + tag if tag else ''}.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return rec


def cells_of(a, step, name, modes, tag, deadline):
    for track in ("input", "output"):
        rc, d = base.run_study_program("p93_judge.py", ARM, a.gr_py, "precheck", "--track", track, *(["--tag", tag] if tag else []))
        base.event(kind="precheck", step=step, arm=ARM, track=track, rc=rc, controls_pass=d.get("controls_pass"), study_verdict=d.get("pass"), result=d)
        sc = server_check(track, tag)
        base.event(kind="server_check", step=step, arm=ARM, track=track, **{"pass": sc["pass"]}, with_reasoning_content=sc["answers_with_reasoning_content"], think_tags=sc["answers_with_a_think_tag_in_the_content"])
        if not (d.get("controls_pass") and sc["pass"]):
            base.event(kind="arm_track_null", step=step, arm=ARM, track=track, reason="the controls or the server check did not pass"); continue
        for mode in modes:
            if time.time() > deadline:
                return f"time limit reached before {ARM}/{track}/{mode}"
            ok, g = gate_until(deadline)
            base.event(kind="g8", step=step, arm=ARM, track=track, mode=mode, before="cell", **{"pass": ok}, gate=g)
            if not ok:
                return f"the idle-card gate did not pass before {ARM}/{track}/{mode}"
            rc, d2 = base.run_study_program("p93_judge.py", ARM, a.gr_py, "cell", "--track", track, "--mode", mode)
            after = g8_gate.sample()
            base.event(kind="cell", step=step, arm=ARM, track=track, mode=mode, rc=rc, result=d2, gpu_after={k: after[k] for k in ("util_pct_p50", "power_w_p50", "compute_processes_listed", "pass")},
                       container_alive=bool(sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=60).stdout.strip()))
    return None


def checks(track, tag=""):
    """-> (usable under the addendum, record) from the study's precheck file and the server check of one container."""
    suffix = "_" + tag if tag else ""
    pp, sp = os.path.join(ARM_DIR, f"precheck_{track}{suffix}.json"), os.path.join(ARM_DIR, f"server_check_{track}{suffix}.json")
    if not (os.path.isfile(pp) and os.path.isfile(sp)):
        return False, {"missing": True}
    p, s = json.load(open(pp, encoding="utf-8")), json.load(open(sp, encoding="utf-8"))
    rec = {"study_precheck": {k: p.get(k) for k in ("controls_pass", "reasoning_switch", "pass", "at")},
           "server_check": {k: s.get(k) for k in ("answers_with_reasoning_content", "answers_with_a_think_tag_in_the_content", "of", "rule", "pass", "at")}}
    rec["usable_under_the_addendum"] = bool(p.get("controls_pass")) and bool(s.get("pass"))
    return rec["usable_under_the_addendum"], rec


def summarize():
    """The study's summary of one arm (p93_analyze.main, line for line) with one condition replaced: the precheck."""
    from p93_common import ARMS
    items = read_jsonl(os.path.join(P93_RESULTS, "items.jsonl"))
    cells = read_jsonl(os.path.join(ARM_DIR, "cells.jsonl")) if os.path.isfile(os.path.join(ARM_DIR, "cells.jsonl")) else []
    cell = {(c["track"], c["mode"]): c for c in cells if not c.get("limit")}; read_files = []

    def rows_of(track, mode):
        p = os.path.join(ARM_DIR, f"{track}_{mode}.jsonl")
        if not os.path.isfile(p):
            return None
        read_files.append({"file": os.path.basename(p), "sha256": sha256_file(p)})
        return read_jsonl(p)

    S = {"arm": ARM, "arm_of_this_folder": ARM, "request_shape_of": SHAPE, "judge": ARMS[SHAPE]["judge"], "path": ARMS[SHAPE]["path"], "thinking": ARMS[SHAPE]["thinking"], "max_tokens": ARMS[SHAPE]["max_tokens"],
         "server": "NIM_PASSTHROUGH_ARGS=" + p102_run.PASSTHROUGH, "precheck_rule": "addendum_parser_arm_precheck.json: the study's controls and the server check", "precheck": {}, "tracks": {}}
    for track in ("input", "output"):
        ok, rec = checks(track); S["precheck"][track] = rec; T = {}
        full = rows_of(track, "c16")
        usable = ok and full is not None and bool(cell.get((track, "c16"), {}).get("complete"))
        T["usable"] = usable
        T["why_not"] = None if usable else ("the controls or the server check did not pass, or a record is missing" if not ok else "the quality cell is missing or incomplete")
        if usable:
            gold_key = "gold_input" if track == "input" else "gold_output"
            pool = [it for it in items if track in it["tracks"]]; groups = {}
            for ds in sorted({it["dataset"] for it in pool}):
                groups[ds] = {it["item_id"]: it[gold_key] for it in pool if it["dataset"] == ds}
            if track == "input":
                groups["xstest_harmless_only"] = {it["item_id"]: "safe" for it in pool if it["dataset"] == "xstest" and it["gold_input"] == "safe"}
                groups["aegis2_needs_caution_only"] = {it["item_id"]: it["gold_input"] for it in pool if it.get("needs_caution_only")}
            T["quality"] = {g: study.quality(full, gold) for g, gold in groups.items() if gold}
            T["quality_cell"] = {"mode": "c16", **study.timing(full, cell.get((track, "c16")))}
            c1 = rows_of(track, "c1")
            if c1 is not None and cell.get((track, "c1"), {}).get("complete"):
                T["c1"] = study.timing(c1, cell.get((track, "c1")))
                first = {r["item_id"]: study.outcome(r) for r in full}; both = [r for r in c1 if r["item_id"] in first]
                T["same_outcome_at_c1_and_c16"] = study.rate(sum(study.outcome(r) == first[r["item_id"]] for r in both), len(both))
            st = rows_of(track, "stability"); st_ok, st_rec = checks(track, "stability")
            T["stability_checks"] = st_rec
            if st is not None and st_ok and cell.get((track, "stability"), {}).get("complete"):
                first = {r["item_id"]: study.outcome(r) for r in full}; both = [r for r in st if r["item_id"] in first]
                T["stability"] = study.rate(sum(study.outcome(r) == first[r["item_id"]] for r in both), len(both))
        S["tracks"][track] = T
    S["files_read"] = read_files; S["per_item_files_read_from"] = ARM
    json.dump(S, open(os.path.join(ARM_DIR, "summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    json.dump(base.rail_beside_verdict(ARM), open(os.path.join(ARM_DIR, "rail_beside_verdict.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    sg = os.path.join(base.VOL, "results", "safety_guard_nim")
    arms = [("J2 (the study, no parser on the server)", os.path.join(P93_RESULTS, "J2", "summary.json")), ("J2P (the same with the reasoning parser)", os.path.join(ARM_DIR, "summary.json")),
            ("J6-today (upstream vLLM 0.20.2)", os.path.join(sg, "J6-today", "summary.json")), ("J6-v010 (upstream vLLM 0.10.0)", os.path.join(RESULTS, "J6-v010", "summary.json")),
            ("J6N (NIM 1.14.0, generic profile)", os.path.join(sg, "J6N", "summary.json"))]
    rows = [x for n, p in arms for t, g in (("input", "aegis2"), ("input", "xstest"), ("output", "aegis2")) for x in [base.line(n, p, t, g)] if x]
    json.dump({"what": "one line per arm, track and data set; every line is built from that arm's summary.json only", "rows": rows}, open(os.path.join(RESULTS, "table.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    md = ["| Arm | Track · data | Detection | False alarm | Rail blocks harmful · harmless | F1 | No verdict | c=1 p50 ms | c=16 verdicts/s | c=16 p99 ms | Stability |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r["usable"]:
            md.append(f"| {r['arm']} | {r['track']} | not usable: {r['why_not']} | | | | | | | | |"); continue
        nv = r["no_verdict"]; rail = r.get("rail")
        md.append(f"| {r['arm']} | {r['track']} · {r['group']} | {base.pct(r['detection'])} | {base.pct(r['false_alarm'])} | " + (f"{base.pct(rail['block_on_harmful'])} · {base.pct(rail['block_on_harmless'])}" if rail else "—") +
                  f" | {base.num(r['f1_unsafe'], '{:.3f}')} | {nv['unreadable'] + nv['truncated'] + nv['error']} | {base.num(r['c1_latency_ms_p50'])} | {base.num(r['c16_verdicts_per_s'])} | {base.num(r['c16_latency_ms_p99'])} | "
                  f"{base.num(None if r['stability'] is None else 100 * r['stability'], '{:.1f}%')} |")
    open(os.path.join(RESULTS, "table.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    print("\n".join(md)); rb = json.load(open(os.path.join(ARM_DIR, "rail_beside_verdict.json"), encoding="utf-8"))
    print(json.dumps({t: {"items": v["items"], "classes": v["classes"], "share_that_differ": v["share_that_differ"]} for t, v in rb.items()}))
    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prediction", required=True); ap.add_argument("--addendum", required=True); ap.add_argument("--gr-py", required=True); ap.add_argument("--steps", default="")
    ap.add_argument("--stop-at", default="08:00"); ap.add_argument("--dry-run", action="store_true")
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
    if not a.dry_run:
        for f, h in add["harness_sha256"].items():
            if sha256_file(os.path.join(HERE, f)) != h:
                sys.exit(f"refused: {f} is not the file the addendum binds")
    plan = [s for s in ORDER if s in ([x for x in a.steps.split(",") if x] or ORDER)]
    if a.dry_run:
        base.view(ARM); print(json.dumps({"plan": plan, "view": "built and checked", "n3_image_present": image_ok(NIM_N3["image"], NIM_N3["index_digest"]),
                                          "toggle_prompts": len(json.load(open(base.P93_PRED, encoding="utf-8"))["toggle_prompts"]), "files_in_the_arm_folder": sorted(os.listdir(ARM_DIR))})); return 0
    if plan == ["summary"]:
        return summarize()
    hh, mm = [int(x) for x in a.stop_at.split(":")]
    t = datetime.datetime.now(); stop = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= t:
        stop += datetime.timedelta(days=1)
    deadline = stop.timestamp(); start = time.time()
    logdir = os.path.join(base.BUCKET, "container_logs"); os.makedirs(logdir, exist_ok=True)
    base.EV = open(os.path.join(RESULTS, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    others = sh(["docker", "ps", "--format", "{{.Names}}"], timeout=60).stdout.split()
    base.event(kind="run_start", program=os.path.basename(__file__), addendum_sha256=sha256_file(a.addendum), prediction_sha256=sha256_file(a.prediction), plan=plan, stop_at=a.stop_at, gpu=gpu(), other_containers_running=len(others))
    if others:
        base.event(kind="run_end", reason="another container is running; nothing was started", rc=2); return 2
    stopped = None
    try:
        for step in plan:
            if step == "summary":
                continue
            if time.time() > deadline:
                stopped = f"time limit reached before {step}"; break
            name = f"vol3fu_{step}"
            cmd, shown = p102_run.nim_command(name, NIM_N3, {"NIM_PASSTHROUGH_ARGS": p102_run.PASSTHROUGH})
            ok, g = gate_until(deadline)
            base.event(kind="g8", step=step, before="container start", **{"pass": ok}, gate=g)
            if not ok:
                stopped = f"the idle-card gate did not pass before {step}"; break
            L = p102_run.launch(name, cmd, shown, logdir)
            base.event(kind="container_ready", step=step, arm=ARM, ready=L.get("ready"), seconds=L.get("seconds_to_verdict"), launch=L, gpu=gpu())
            if not L.get("ready"):
                base.event(kind="step_null", step=step, reason=L.get("reason"), first_error_line=L.get("first_error_line"))
                sh(["docker", "rm", "-f", name], timeout=120); time.sleep(10); continue
            base.event(kind="warm_up", step=step, versions=p102_run.server_versions(), **warm_up("n3_nim"))
            stopped = cells_of(a, step, name, ["stability"], "stability", deadline) if step.endswith("stability") else cells_of(a, step, name, ["c1", "c16"], "", deadline)
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
    if not stopped and "summary" in plan:
        summarize()
    return 0 if not stopped else 5


if __name__ == "__main__":
    sys.exit(main())
