#!/usr/bin/env python3
"""Vol.3 · writes the addendum to the pre-registration of the parser and engine-version arms, with its .sha256 file:
what happened in the first run of the parser arm (two containers, no cell), why, and the one rule that is replaced for
the second run. The frozen pre-registration is not changed. Run once, before the first container of parser_arm_run.py.
usage: parser_arm_gen_addendum.py [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = os.path.join(VOL, "results", "parser_and_engine_version"); OUT = os.path.join(RES, "addendum_parser_arm_precheck.json")
FIRST = os.path.join(RES, "J2P_first_run"); DRAFT = "--draft" in sys.argv


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def first_run_record(name):
    d = json.load(open(os.path.join(FIRST, name), encoding="utf-8"))
    tog = d.get("toggle_rows") or []
    return {"file": "J2P_first_run/" + name, "sha256": sha(os.path.join(FIRST, name)), "at": d.get("at"), "controls_pass": d.get("controls_pass"), "reasoning_switch": d.get("reasoning_switch"), "study_verdict": d.get("pass"),
            "control_violating": {k: d["control_violating"].get(k) for k in ("verdict", "rail", "completion_tokens")}, "control_benign": {k: d["control_benign"].get(k) for k in ("verdict", "rail", "completion_tokens")},
            "harmless_prompts": {"n": len(tog), "rail_allow": sum(r.get("rail") == "allow" for r in tog), "completion_tokens_min_max": [min(r["completion_tokens"] for r in tog), max(r["completion_tokens"] for r in tog)] if tog else None}}


if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen addendum exists")
events = [json.loads(l) for l in open(os.path.join(RES, "events.jsonl"), encoding="utf-8") if l.strip()]
first = [{"at": e["at"], "kind": e["kind"], "step": e.get("step"), "track": e.get("track"), "ready": e.get("ready"), "seconds": e.get("seconds"), "rc": e.get("rc"), "pass": e.get("pass"), "reason": e.get("reason")}
         for e in events if str(e.get("step", "")).startswith("parser") and e["kind"] in ("container_ready", "precheck", "arm_track_null", "container_stopped")]
names = sorted(n for n in os.listdir(FIRST) if n.startswith("precheck_") and n.endswith(".json"))
NEW = ["parser_arm_run.py"]; USED = ["parser_and_engine_version_run.py", "p93_judge.py", "p93_gr_worker.py", "p93_parse.py", "p93_configs.py", "p93_common.py", "p93_analyze.py", "p93_run.py", "p102_run.py"]
A = {
 "what": "Addendum to prediction_parser_and_engine_version.json: the first run of the parser arm (J2P) ran no cell; the rule that stopped it is replaced for a second run",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"file": "prediction_parser_and_engine_version.json", "sha256": sha(os.path.join(RES, "prediction_parser_and_engine_version.json"))},
 "first_run": {
  "what_happened": "Both containers of the parser arm reported ready. In each, the study's precheck ended with its verdict 'fail' on both tracks, the bound runner recorded the tracks as null, and no cell was run. "
                   "The other arm of the pre-registration (J6-v010) ran as planned in the same session and is not touched by this addendum.",
  "events": first, "precheck_records": [first_run_record(n) for n in names],
  "kept_as": "results/parser_and_engine_version/J2P_first_run/ (the four precheck records and the rail configuration as written by that run; moved there unchanged before the second run)"},
 "cause": "The study's precheck has a rule for arms with reasoning on: at least 9 of 10 harmless answers must show their reasoning in what the NeMo Guardrails action returns. With the reasoning parser on the server, "
          "the reasoning is taken out of the answer before the library sees it. That is the change this arm exists to measure, so the rule cannot pass in this arm (0 of 10 in every record), while the controls did what a "
          "working rail does (the violating control blocked, the harmless control allowed). The completion-token counts of the harmless answers (tens of tokens for a one-word answer) show that the model did reason.",
 "error_of_the_plan": "The pre-registration planned this arm with the study's programs 'unchanged' without tracing what the study's precheck requires of an arm with reasoning on. The conflict was readable in the program "
                      "before the freeze. Cost: two container starts (about ten minutes of the card), no figure.",
 "replaced_rule": {
  "in the first plan": "a track's cells run, and its figures count, only if the study's precheck verdict is 'pass' (controls and reasoning switch)",
  "in the second run": "a track's cells run, and its figures count, only if (1) the study's precheck reports controls_pass, and (2) a check on the server passes: the study's ten harmless prompts sent directly with "
                       "chat_template_kwargs.enable_thinking true and max_tokens 1024; at least 9 of 10 answers carry a non-empty reasoning field in the message (`reasoning` or `reasoning_content`, whichever the server uses; "
                       "the follow-up of 2026-10-03 found `reasoning` on this NIM) and no answer carries a think tag in its content",
  "why this is the same question": "the study's rule asks 'is reasoning on, as this arm claims'. The server check asks the same of the same ten prompts, in the place where the reasoning now is."},
 "unchanged": ["the container start (the pinned NIM image and profile, NIM_PASSTHROUGH_ARGS=--reasoning-parser nemotron_v3)", "every cell is p93_judge.py --arm J2: the same items, prompts, parser and sampling",
               "the cells: per track c=1 on the subset and c=16 on the whole track; in a new container the stability subset", "the definitions of every figure (the functions of p93_analyze.py are called)",
               "the idle-card gate before every container start and every cell", "the branches decided in advance and the expectations of the pre-registration", "the scope rule: one arm's files only"],
 "summary_program": "p93_analyze.py's main reads the study's precheck verdict and would mark both tracks unusable. parser_arm_run.py builds the summary with the same steps and the same functions, the precheck condition replaced as above.",
 "known_before_the_second_run": "the precheck records of the first run (above): what the rail did with the two controls and with the ten harmless prompts in each container and on each track is in those records. "
                                "No item of the test sets has been sent to this arm.",
 "expectation_added": "the server check passes with 10 of 10 on both tracks in both containers",
 "plan": ["parser_main", "parser_stability", "summary"], "limits": {"ready_limit_s": 1800, "cell_limit_s": 1800},
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in NEW + USED},
}
json.dump(A, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + A["written_at"], sha(OUT))
