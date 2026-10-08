#!/usr/bin/env python3
"""Vol.3 · writes the addendum of the generic-NIM cell and its .sha256 file: one more arm (upstream vLLM at the engine
version the generic image ships), two more criteria, and the disposition table that goes with them. The cell's
pre-registration is not changed; its four criteria are computed and reported as registered. Run once, before the first
serving container.
usage: model_free_nim_gen_addendum.py --image-digest sha256:... [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = os.path.join(VOL, "results", "model_free_nim"); OUT = os.path.join(RES, "addendum_same_engine_arm.json")
DRAFT = "--draft" in sys.argv
DIGEST = sys.argv[sys.argv.index("--image-digest") + 1]
NEW = ["model_free_nim_addendum_run.py", "model_free_nim_addendum_summary.py"]
USED = ["model_free_nim_run.py", "model_free_nim_summary.py"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


pre = os.path.join(RES, "prediction_model_free_nim.json"); P = json.load(open(pre, encoding="utf-8"))
if not DIGEST.startswith("sha256:") or len(DIGEST) != 71:
    sys.exit("refused: --image-digest must be sha256:<64 hex digits>")
add = {
 "what": "addendum to the pre-registration of the generic-NIM cell: one more arm, two more criteria, and the disposition that goes with them; written before the first serving container of the cell",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"prediction_model_free_nim.json": sha(pre), "its_freeze": P["written_at"]},
 "why": "The pre-registration's first criterion asks that J6M's rate be within 5% of J6-tonight's, above or below, and ties the removal of the NIM arm from the article to a failure. "
        "The generic image ships vLLM " + P["known_before_the_run"]["engine_in_the_generic_image"] + ", newer than the upstream arm's 0.20.2, so J6M may come out more than 5% above upstream: "
        "the criterion would fail for an arm that is faster. That is a gap in the criterion, seen before any serving container ran. The pre-registration is not changed; this file adds what it lacks.",
 "the_registered_criteria": "computed and reported as registered, pass or fail; for the speed criterion the direction (above or below) is reported beside it",
 "arm_J6-v0271": {
  "what": "the same weight directory on the upstream vLLM image of the engine version the generic NIM ships",
  "one_variable_against_J6M": "the NIM around the engine: the same engine version, weight directory, items, prompt, request parameters and client program",
  "one_variable_against_J6-tonight": "the engine version (0.27.1 for 0.20.2); the container command is the same but for the image tag",
  "serving": {"image": "vllm/vllm-openai:v0.27.1", "digest": DIGEST,
              "start": "the container command of the study's arm J6 (p102_run.vllm_command) with this image; the settings below are added in front of the mount",
              "start_settings": {"as_J6-tonight": {}, "with_the_v1_model_runner": {"VLLM_USE_V2_MODEL_RUNNER": "0"}}, "order_of_the_start_settings": ["as_J6-tonight", "with_the_v1_model_runner"],
              "why_a_second_setting": "the same reason as for J6M: tried only if the first does not report ready; the arm's label says which one ran, and a difference from J6M's setting is named as a variable"},
  "cells": "per track: precheck, c=1 on the 200-item subset, c=16 on the whole track; no stability rerun, no rail cell",
  "if_it_cannot_run": "the image is missing, or no start setting reports ready: the arm is skipped with the error text as it is, and the rest of the night goes on"},
 "order_of_the_night": ["weights and profiles (no serving container)", "J6-tonight", "J6-v0271", "J6M with the rail cell, then J6M's stability container", "J6N-tonight", "summaries and criteria"],
 "how_the_order_is_run": "the cell's runner is called once per group of steps (--steps), the added arm by model_free_nim_addendum_run.py between two of those calls; each call writes its own run_start and run_end to the one events file. "
                         "The pre-registration lists its steps in another order; it sets no criterion on the order.",
 "criteria_added": {
  "not_slower_than_the_upstream_arm": {"rule": "J6M's verdicts per second at 16 concurrent requests are at least 95% of J6-tonight's on both tracks", "at_least_share_of_J6-tonight": 0.95},
  "wrapper_cost": {"rule": "J6M's verdicts per second at 16 concurrent requests are within 5% of J6-v0271's on both tracks (above or below)", "within_percent": 5.0}},
 "disposition": {
  "replaces": "the speed half of the pre-registration's branches A and B; the verdicts half, the rail half, branch C and the rule about the validity of the night stay as registered",
  "A": "J6M is not slower than the upstream arm, the verdicts criterion passes and the rail criterion passes: the NIM stays in the volume; the text states the direction that was measured (the same rate, or faster) and both engine versions",
  "A, wrapper cost within 5%": "one more clause may be written: J6M matches upstream vLLM 0.27.1 within the measured percentage",
  "A, wrapper cost outside 5%": "still A; that clause is not written; the two arms' figures and every setting that differs between their start commands are reported",
  "A, the added arm has no rate": "still A; that clause is not written",
  "B": "J6M is more than 5% below J6-tonight on a track, or the verdicts or the rail criterion fails",
  "C": "no start setting of J6M reports ready"},
 "expectations": {
  "J6-v0271 starts": "with the first setting about 50%, with the second about 85% in all",
  "J6-v0271 against J6-tonight": "between 5% below and 12% above; no reason is known beforehand why seven minor versions should change the rate of an 8B model with 20-token answers by much",
  "wrapper cost": "J6M within 5% of J6-v0271 on both tracks, about 60%; if not, J6M is the lower of the two (the NIM adds a proxy in front of the engine)",
  "not slower than the upstream arm": "passes, about 75%",
  "confidence": "low: neither image has been run on this card"},
 "scope": "the other arms of the volume are measured on upstream vLLM 0.20.2 and that stays the volume's baseline; J6-v0271 belongs to the Safety Guard section and to this results folder only",
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in NEW + USED},
 "bound_by_the_pre_registration_and_unchanged": {f: sha(os.path.join(HERE, f)) == P["harness_sha256"][f] for f in USED},
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen addendum exists")
json.dump(add, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + add["written_at"], sha(OUT), "| the cell's programs unchanged:", all(add["bound_by_the_pre_registration_and_unchanged"].values()))
