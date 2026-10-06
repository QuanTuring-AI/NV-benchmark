#!/usr/bin/env python3
"""Vol.3 · writes the second addendum to the pre-registration of the parser and engine-version arms, with its .sha256
file: the whole-track cell at 16 in flight once more for the parser arm, and the study's arm J2 on the same day.
Run once, before the first container of parser_arm_rate_repeat.py. usage: parser_arm_gen_addendum_rate_repeat.py [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = os.path.join(VOL, "results", "parser_and_engine_version"); OUT = os.path.join(RES, "addendum_rate_repeat.json"); DRAFT = "--draft" in sys.argv


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def cells(path):
    out = {}
    for l in open(path, encoding="utf-8"):
        c = json.loads(l)
        if not c.get("limit"):
            out[f"{c['track']}_{c['mode']}"] = {"calls": c["n"], "wall_s": c["wall_s"], "verdicts_per_s": round(c["n"] / c["wall_s"], 2), "start": c["start"],
                                               "card_mib_at_start_and_end": [(c.get("gpu_start") or {}).get("used_mib"), (c.get("gpu_end") or {}).get("used_mib")]}
    return out


if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen addendum exists")
J2 = cells(os.path.join(VOL, "results", "p93_judges", "J2", "cells.jsonl")); J2P = cells(os.path.join(RES, "J2P", "cells.jsonl"))
NEW = ["parser_arm_rate_repeat.py"]; USED = ["parser_arm_run.py", "parser_and_engine_version_run.py", "p93_judge.py", "p93_gr_worker.py", "p93_parse.py", "p93_configs.py", "p93_common.py", "p93_analyze.py", "p93_run.py", "p102_run.py"]
A = {
 "what": "Second addendum to prediction_parser_and_engine_version.json: the whole-track cell at 16 in flight once more for the parser arm (J2P-repeat), and the study's arm J2 on the same day (J2-today)",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"file": "prediction_parser_and_engine_version.json", "sha256": sha(os.path.join(RES, "prediction_parser_and_engine_version.json"))},
 "after": {"file": "addendum_parser_arm_precheck.json", "sha256": sha(os.path.join(RES, "addendum_parser_arm_precheck.json"))},
 "what_was_seen": {
  "J2P (2026-10-06, this pre-registration)": J2P, "J2 (the study, 2026-10-02, graphics driver 591.86)": J2,
  "reading": "In the parser arm's first container the two whole-track cells at 16 in flight ran at about half the rate of the study's J2. In its second container the stability subsets (200 and 100 items, also 16 in flight) "
             "ran at J2's rate, and the cells with one call at a time took about as long as J2's. The answers have the same length in both arms (median 112 and 152 to 154 completion tokens)."},
 "the_expectation_this_concerns": "the pre-registration expected the parser arm's verdicts per second within 10% of J2's. On the whole-track cells that did not hold (4.8 and 4.4 against 9.4 and 8.1). "
                                  "That result stands as measured; this addendum asks what it is a property of.",
 "why_one_run_cannot_say": "the parser arm differs from the study's J2 in the parser argument, in the day and the graphics driver (610.88 against 591.86), and in the container. The slow cells all lie in one container.",
 "arms": {
  "J2P-repeat": "the parser arm's container start once more (a new container); per track the precheck of addendum_parser_arm_precheck.json and the whole-track cell at 16 in flight",
  "J2-today": "the same start without the parser argument, as the study's J2; per track the study's precheck unchanged and the whole-track cell at 16 in flight"},
 "not_run": "cells with one call at a time, stability reruns",
 "branches_decided_in_advance": {
  "both arms within 10% of the study's J2 on both tracks": "the half rate belongs to the first container of the parser arm's run (or to the host while it ran), not to the parser and not to the day; the article gives the rate of the repeat and names the slow run",
  "J2P-repeat at about half again, J2-today within 10% of J2": "the parser costs about half the rate on a whole track at 16 in flight; that is written beside the recommendation",
  "both at about half": "the day (driver or host) and not the parser; the rates of 2026-10-06 are set beside each other only",
  "anything else": "the four figures are written side by side and no cause is named"},
 "expectation": "the first branch: the second container of the parser arm already ran at J2's rate. Verdicts of J2P-repeat within the range the arm showed against itself (its stability cells repeated 95% and 87% of outcomes). Confidence: moderate.",
 "use_of_the_verdicts": "the repeat's verdict counts are reported beside the first run's as a second run of the same arm; the figures of the parser arm stay those of its pre-registered run",
 "limits": {"ready_limit_s": 1800, "cell_limit_s": 1800},
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in NEW + USED},
}
json.dump(A, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + A["written_at"], sha(OUT))
