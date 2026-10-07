#!/usr/bin/env python3
"""Vol.3 · writes the pre-registration of the generic-NIM cell and its .sha256 file. A supplement to the
pre-registrations of the judge study (results/p93_judges/prediction_p93.json) and of the NIM arms
(results/safety_guard_nim/prediction_safety_guard_nim.json), which are not changed: items, subsets, labels, the prompt,
the answer parser, the metrics and the rail configuration are those files'. Run once, before the first serving container.
env: P93_HF_HUB · usage: model_free_nim_gen_prediction.py [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from p93_common import CONTEXT, HF_SG8, VLLM, sha256_text  # noqa: E402
from safety_guard_nim_run import card_template_text  # noqa: E402

RES = os.path.join(VOL, "results", "model_free_nim"); OUT = os.path.join(RES, "prediction_model_free_nim.json")
DRAFT = "--draft" in sys.argv
NEW = ["model_free_nim_run.py", "model_free_nim_summary.py"]
USED = ["safety_guard_nim_run.py", "safety_guard_nim_rail.py", "safety_guard_nim_summary.py", "p93_judge.py", "p93_parse.py", "p93_common.py", "p93_run.py", "p102_run.py", "p93_analyze.py", "p93_gr_worker.py", "p93_configs.py"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def rates(rel):
    S = json.load(open(os.path.join(VOL, *rel.split("/")), encoding="utf-8"))
    return {t: {"verdicts_per_s_at_16": S["tracks"][t]["quality_cell"]["verdicts_per_s"], "detection": S["tracks"][t]["quality"]["aegis2"]["detection"]["rate"],
                "false_alarm": S["tracks"][t]["quality"]["aegis2"]["false_alarm"]["rate"]} for t in ("input", "output")}


P117 = json.load(open(os.path.join(VOL, "results", "safety_guard_nim", "prediction_safety_guard_nim.json"), encoding="utf-8"))
facts = os.path.join(RES, "before_the_run", "facts_read_before_the_run.json"); F = json.load(open(facts, encoding="utf-8"))
served = HF_SG8["served"]; base = {"NIM_MODEL_PATH": "/model", "NIM_SERVED_MODEL_NAME": served, "NIM_MAX_MODEL_LEN": str(CONTEXT)}
TODAY = "results/safety_guard_nim/J6-today/summary.json"
pred = {
 "what": "pre-registration of one cell of the Vol.3 judge study: the Safety Guard 8B v3 weights served by the generic NIM container of the 2.x line, with two partners measured the same night",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"results/p93_judges/prediction_p93.json": sha(os.path.join(VOL, "results", "p93_judges", "prediction_p93.json")),
                 "results/safety_guard_nim/prediction_safety_guard_nim.json": sha(os.path.join(VOL, "results", "safety_guard_nim", "prediction_safety_guard_nim.json"))},
 "question": "The model's own NIM (1.14.0) gave about a fifth fewer verdicts per second than upstream vLLM 0.20.2 on this card, and upstream vLLM 0.10.0 came within 4% of the NIM: the gap follows the engine version the 1.14.0 image ships. "
             "Served by the generic NIM 2.0.12 from the same weight directory, does the model give upstream's rate and the same verdicts?",
 "known_before_the_run": {"file": "before_the_run/facts_read_before_the_run.json", "sha256": sha(facts), "generic_image_tags_on_the_registry": F["registry"]["tags_that_exist"],
                          "engine_in_the_generic_image": F["image"]["vllm_version"], "engine_of_the_upstream_arm": VLLM["image"],
                          "note": "the engine inside the generic image is newer than the upstream arm's, so the generic NIM may come out above upstream as well as below; the first criterion is two-sided",
                          "an_inspection_container_ran_before_this_file": "one container of the generic image without a GPU, to print the engine version (named p121_inspect_no_gpu, " + F["image"]["inspected_at"] + "); no serving container ran before this file"},
 "serving": {
  "generic_nim": {"image": F["image"]["name"], "index_digest": F["image"]["digest"], "why_this_tag": "the tag of the other 2.x NIM images of this volume; the registry also holds a later one",
                  "model": "the local directory of the study's arm J6 (the model snapshot named in results/p93_judges/prediction_p93.json), mounted read-only at /model; nothing is fetched",
                  "start": "docker run --gpus all --shm-size=64GB, port 8000 on 127.0.0.1, the NIM cache mounted, the settings below",
                  "start_settings": {"as_documented": dict(base), "with_the_v1_model_runner": {**base, "VLLM_USE_V2_MODEL_RUNNER": "0"}},
                  "order_of_the_start_settings": ["as_documented", "with_the_v1_model_runner"],
                  "why_a_second_setting": "the Llama 3.1 8B NIM of the same version needed VLLM_USE_V2_MODEL_RUNNER=0 on this host (Vol.1); it is tried only if the first setting does not report ready, and the arm's label says which one ran",
                  "not_tried": ["another tag", "an hf:// path", "a chat template or any other file added to the model directory", "a profile pinned by hand"]},
  "upstream": {"image": VLLM["image"], "digest": VLLM["digest"], "start": "the container command of the study's arm J6 (p102_run.vllm_command), unchanged"},
  "model_nim": {"image": P117["serving"]["image"], "index_digest": P117["serving"]["index_digest"], "profile": P117["serving"]["profiles"]["generic"], "start": "the container command of arm J6N (safety_guard_nim_run.nim_command), unchanged"},
  "ready_limit_s": 1800, "cell_limit_s": 1800},
 "weights": {"nim_cache_folder_below_the_cache": "ngc/hub/models--nim--nvidia--llama-3.1-nemotron-safety-guard-8b-v3/snapshots/1.2-checksum-jet",
             "rule": "SHA-256 of every *.safetensors file of the local model directory and of the NIM 1.14.0 cache, file by file, before the first container; a difference is written down as it is and nothing is changed"},
 "prompt_template_sha256": sha256_text(card_template_text()[1]),
 "arms": {
  "J6M": {"served_by": "the generic NIM image", "asked": "as the study's arm J6: the model card's prompt in one user message, max_tokens 100, temperature 0.0, the study's parser",
          "cells": "per track: precheck, c=1 on the 200-item subset, c=16 on the whole track; in a new container the stability subset again"},
  "J6-tonight": {"served_by": "upstream vLLM 0.20.2", "asked": "as J6M", "cells": "per track: precheck, c=1, c=16; no stability rerun"},
  "J6N-tonight": {"served_by": "the model's NIM 1.14.0, generic profile pinned by id", "asked": "as J6M", "cells": "per track: precheck, c=1, c=16; no stability rerun"},
  "J6M-rail": {"served_by": "the J6M container", "asked": "through the NeMo Guardrails content-safety rail as arm J6G: the library's tutorial configuration, 100 items per track, one call at a time"}},
 "one_variable": "the container (and with it the engine version). The weight directory is one path for J6M and J6-tonight; the items, the prompt, the request parameters, the client program and the order of the cells are the same for the three arms. "
                 "Every setting that differs between the three start commands is listed per arm in the results; a setting that cannot be made equal is named as a variable.",
 "guardrails": P117["guardrails"],
 "plan": ["weights", "profiles", "j6m_main", "vllm_tonight", "nim_tonight", "j6m_stability"],
 "criteria": {
  "speed": {"rule": "J6M's verdicts per second at 16 concurrent requests are within 5% of J6-tonight's on both tracks (above or below)", "within_percent": 5.0},
  "verdicts": {"rule": "on each track the whole-track verdicts of J6M and J6-tonight are the same on at least 99% of the items, and the Aegis 2.0 detection and false-alarm rates differ by at most 0.5 points",
               "same_verdict_share_at_least": 0.99, "rate_difference_at_most_points": 0.5},
  "rail": {"rule": "through the content-safety rail, the rail's decision and the verdict of the same call agree on at least 199 of the 200 calls", "agree_at_least": 199, "calls": 200},
  "validity_of_the_night": {"rule": "J6-tonight's verdicts per second at 16 concurrent requests are within 5% of J6-today's (2026-10-06) on both tracks; if not, every absolute figure of the night is written as 'invalid_night' and only the ratios between the three arms of the night are reported",
                            "within_percent": 5.0, "reference_summary": TODAY}},
 "reference_figures": {"J6-today (2026-10-06, upstream vLLM 0.20.2)": rates(TODAY), "J6N (2026-10-06, the model's NIM)": rates("results/safety_guard_nim/J6N/summary.json")},
 "expectations": {
  "start": "the first start setting does not report ready (about 60%) and the second does; that neither does: about 15%",
  "speed": "J6M comes out between 3% below and 8% above J6-tonight; the criterion passes with about 55%",
  "verdicts": "the same verdict on more than 99.5% of the items of each track; rate differences at most 0.3 points; the criterion passes with about 85%",
  "rail": "200 of 200, as arm J6G",
  "validity_of_the_night": "passes (about 85%): J6-today came within 3.4% of the study's J6 across four days and a driver change",
  "J6N-tonight": "within 5% of J6N of 2026-10-06, and 15% to 22% below J6-tonight",
  "weights": "the four files have the same bytes in the two directories (about 80%)",
  "confidence": "low for the start and for the speed: the generic image has not been run on this card before"},
 "branches_decided_in_advance": {
  "A": "speed, verdicts and rail all pass: the NIM stays in the volume; the J6N point of the two figures is replaced by J6M with the same outline; J6M's figures are added to the claim table",
  "B": "J6M reports ready, and the speed or the verdicts criterion fails: the NIM arm leaves the article's main text; the J6N point and the NIM half of the outline's legend line are removed from the figures; the three arms' figures and what differs between their servers stay in the repository",
  "C": "no start setting reports ready: as B, with the error text of every attempt as it is; the model directory is not changed and no chat template is written",
  "the validity gate fails": "the branch is still chosen by the criteria (they are ratios of the same night); the results say that the absolute figures of the night are not valid",
  "a precheck fails": "that arm and track is null, as in the study; a criterion that needs it does not pass"},
 "not_in_this_file": ["NIM for LLMs 3.0", "more than one card", "more than 16 calls in flight", "a second night", "upstream vLLM at the generic image's engine version (it would tell the engine from the NIM wrapper; not asked for here)"],
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in NEW + USED},
 "programs_written_after_the_freeze": "none planned; if one is needed, its SHA-256 is written to the events file before its first use",
}
os.makedirs(RES, exist_ok=True)
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
