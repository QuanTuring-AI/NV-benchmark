#!/usr/bin/env python3
"""Vol.3 · writes the pre-registration of the Safety Guard 8B v3 NIM arms and its .sha256 file. A supplement to the
pre-registration of the judge study (results/p93_judges/prediction_p93.json), which is not changed: items, subsets,
labels, the answer parser, the metrics and the scope rule are that file's. Run once, before the first serving container.
env: P93_HF_HUB · usage: safety_guard_nim_gen_prediction.py [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from p93_common import CONTEXT, sha256_text  # noqa: E402
from safety_guard_nim_run import card_template_text  # noqa: E402

RES = os.path.join(VOL, "results", "safety_guard_nim"); OUT = os.path.join(RES, "prediction_safety_guard_nim.json")
DRAFT = "--draft" in sys.argv


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def before(name):
    return {"file": "before_the_run/" + name, "sha256": sha(os.path.join(RES, "before_the_run", name))}


p93 = os.path.join(VOL, "results", "p93_judges", "prediction_p93.json"); P93 = json.load(open(p93, encoding="utf-8"))
p102 = os.path.join(VOL, "results", "p102_followup", "prediction_p102.json")
J6 = json.load(open(os.path.join(VOL, "results", "p93_judges", "J6", "summary.json"), encoding="utf-8"))
cmp_ = json.load(open(os.path.join(RES, "before_the_run", "prompt_template_comparison.json"), encoding="utf-8"))
listing = open(os.path.join(RES, "before_the_run", "list_model_profiles.txt"), encoding="utf-8").read()
_, card = card_template_text()
if sha256_text(card) != cmp_["model_card"]["template_sha256"]:
    sys.exit("the model card's template is not the one of the comparison file")
PROFILES = {"generic": "47804570e8db67fdc60d9cb518b0f60316ac4eb0f3a55af81aafefe124505a8f",
            "fp8_throughput": "b5938999f25208fbf5ef64ad1ce0d3978ac52d5b18d32f9b7e1551cbc97737db",
            "fp8_latency": "9325fdaeebf47da133de2bffcbfdcfb7537de5f0cf72adb091fb5bb8429047ad"}


def listed(pid):
    """The section of the listing the profile id stands in."""
    head = None
    for l in listing.splitlines():
        if l.startswith("- ") and l.rstrip().endswith(":"):
            head = l[2:].rstrip(":").strip()
        if pid in l and l.lstrip().startswith("- " + pid):
            return {"section": head, "name": l.split("(", 1)[1].rstrip(")").strip() if "(" in l else None}
    return {"section": None, "name": None}


def j6(track, group="aegis2"):
    T = J6["tracks"][track]; q = T["quality"][group]
    return {"detection": q["detection"], "false_alarm": q["false_alarm"], "c1_latency_ms_p50": T["c1"]["latency_ms"]["p50"], "c16_verdicts_per_s": round(T["quality_cell"]["verdicts_per_s"], 1),
            "completion_tokens_p50": T["quality_cell"]["completion_tokens"]["p50"], "completion_tokens_p99": T["quality_cell"]["completion_tokens"]["p99"]}


NEW = ["safety_guard_nim_run.py", "safety_guard_nim_rail.py", "safety_guard_nim_summary.py", "guardrails_safety_guard/prompts.yml"]
USED = ["p93_judge.py", "p93_gr_worker.py", "p93_parse.py", "p93_configs.py", "p93_common.py", "p93_analyze.py", "p93_run.py", "p102_run.py", "p102_cells.py"]
pred = {
 "what": "Pre-registration of the arms that serve Llama 3.1 Nemotron Safety Guard 8B v3 through its NIM; a supplement to the judge study's pre-registration",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": "../p93_judges/prediction_p93.json", "sha256": sha(p93)}, {"file": "../p102_followup/prediction_p102.json", "sha256": sha(p102)}],
 "kept_from_the_study": "the items and the subsets (results/p93_judges/items.jsonl, subsets.json), the labels, the two synthetic controls and the ten harmless prompts of the precheck, the answer parser, the definitions of every "
                        "figure, greedy sampling, a new connection per direct call, the idle-card gate before every container start and every cell, and the scope rule: every figure is about one arm, and no per-item result "
                        "of one arm is read together with a per-item result of another arm",
 "why": {"what_the_study_did": "arm J6 served this model with upstream vLLM 0.20.2 and called it 'not a NIM'. The NIM was not tried: the first sentence of its support matrix says the model requires 48 GB of GPU memory, and that sentence was taken as the answer.",
         "what_was_not_read_then": "the same support matrix lists a generic profile (vLLM, BF16, one GPU, 14.97 GB) that is not tied to a card model",
         "question": "does the model's NIM serve on this 32 GB card, and if it does, do the study's figures for this model change when only the serving package changes"},
 "known_before_the_run": {
  "documentation": {"pages": "https://docs.nvidia.com/nim/llama-3-1-nemotron-safety-guard-8b/latest/ (getting-started, support-matrix, release-notes, integrate-guardrails), read 2026-10-06",
                    "release": "NIM 1.14.0, built on NIM for LLMs 1.14.0",
                    "generic_profile": "BF16, vLLM, 1 GPU, 14.97 GB", "fp8_profiles": "for RTX PRO 6000 Blackwell Server Edition: FP8, TensorRT-LLM, 23.56 GB, one tuned for latency and one for throughput",
                    "known_issue": "TensorRT-LLM profiles can have lower throughput under high load than the generic vLLM profile; for high concurrency and long sequences the release notes suggest the generic profile",
                    "official_parser": "the example program reads the answer as JSON; an answer that does not parse is counted as unsafe"},
  "listing_on_this_card": dict(before("list_model_profiles.txt"), what="`list-model-profiles` of the image on this RTX 5090, before any server was started",
                               profiles={k: {"id": v, **listed(v)} for k, v in PROFILES.items()},
                               reading="the image calls the generic profile compatible with this system and runnable, and both FP8 profiles incompatible with it; their names carry the device id 2bb5:10de, this card reports 2b85:10de",
                               also_printed="for every profile a warning that it does not support LoRA while LoRA is enabled; what that means for a start is not known before the run"),
  "prompt": dict(before("prompt_template_comparison.json"), reading="the study's prompt for this model (the model card's template) and the template of the NIM's documentation differ in one thing: each of the 23 category lines ends "
                 "with a blank in the model card's and not in the documentation's. Nothing else differs on the conversations tested.", difference=cmp_["difference"], request_parameters=cmp_["request_parameters"]),
  "guardrails": {"version": "NeMo Guardrails 0.24.1 (the environment of the study)",
                 "found_without_a_server": "the configuration of the library's tutorial for a local NIM names the model twice (`model` and `parameters.model_name`); the library at the same tag refuses it: "
                                           "'Model name must be specified in exactly one place'. With the name given once it is accepted, with engine `nim` as in the tutorial.",
                 "tutorial_prompts_equal_the_example_file": True}},
 "serving": {"image": "nvcr.io/nim/nvidia/llama-3.1-nemotron-safety-guard-8b-v3:1.14.0", "index_digest": "sha256:c3499d38650b942132affdcf37bf6ca89223655cbe227ddbf11254d383615356",
             "linux_amd64_manifest": "sha256:68a9ba7fa0197d77478487ba861d58846e874a581882f9c935bdf7cf9b0c6122", "image_size_bytes_as_docker_reports": 15062781048,
             "profiles": PROFILES, "start": f"docker run --gpus all --shm-size=64GB (the documentation's value), NIM_MODEL_PROFILE=<id>, NIM_MAX_MODEL_LEN={CONTEXT} (the context of the study's arm J6), port 8000 on 127.0.0.1, the NIM cache mounted",
             "not_set": "the documentation's `-u $(id -u)` and `--runtime=nvidia` (the earlier NIM containers of this repository ran without them on this host)",
             "ready_limit_s": 1800, "cell_limit_s": 1800},
 "download": {"done_before_this_file": ["generic", "fp8_throughput", "fp8_latency"], "how": "`download-to-cache --profile <id>` in the image; not timed; what each call ended with is in the README of the results folder"},
 "prompt_templates": {"model_card": {"sha256": cmp_["model_card"]["template_sha256"], "used_by": ["J6N", "J6N-fp8"]},
                      "nim_documentation": {"made_how": "the model card's template with the blank removed from the end of each category line", "category_lines_changed": 23,
                                            "test_query": cmp_["test_query"], "test_response": cmp_["test_response"],
                                            "rendered_sha256": {k: cmp_["rendered"]["nim_documentation"][k]["sha256"] for k in ("input", "output")},
                                            "check": "the runner refuses to start unless the template it derives renders the two test conversations to these values, which come from the documentation's own code",
                                            "used_by": ["J6N-tpl"]}},
 "arms": {
  "J6N": {"served_by": "the generic profile", "asked": "as the study's arm J6: the model card's prompt in one user message, max_tokens 100, temperature 0.0, parsed by the study's parser",
          "cells": "per track: precheck, c=1 on the 200-item subset, c=16 on the whole track; in a new container the stability subset again (200 and 100 items)",
          "one_variable_against": "J6 of the study: the serving package (the NIM's vLLM instead of upstream vLLM 0.20.2). The program that asks and reads is the same file."},
  "J6N-fp8": {"served_by": "an FP8 TensorRT-LLM profile built for RTX PRO 6000 Blackwell, pinned by id: the throughput profile first, the latency profile if that one does not report ready",
              "asked": "as J6N", "cells": "as J6N",
              "against": "J6N, and two things differ at once: the precision (FP8 for BF16) and the engine (TensorRT-LLM for vLLM). They are named as two and not told apart by this arm."},
  "J6N-tpl": {"served_by": "the generic profile, the same container as J6N", "asked": "as J6N with the documentation's template (23 blanks fewer)", "cells": "per track: precheck, c=1, c=16; no stability rerun",
              "one_variable_against": "J6N: the prompt template", "why_all_items": "the work order asks for the 200-item subset; the whole track costs under a minute per track and lets the study's analysis program run unchanged"},
  "J6G": {"served_by": "the generic profile, the same container as J6N", "asked": "through the NeMo Guardrails content-safety rail, one call at a time, on the study's subset for the Guardrails path (100 items per track)",
          "configuration": "the library's tutorial for this model at tag v0.24.1 (engine nim, model type content_safety, the two content-safety flows) with its prompts file byte for byte: max_tokens 50, parsers nemoguard_parse_*",
          "changes_from_the_tutorial": ["the base URL is the local server's", "the model name is given once", "the main model points at the same server and is never called (no answer is generated in this study)"],
          "recorded": "per item the rail's decision and, apart from it, the verdict the study's parser reads from the same completion; each item is classed by its own two readings (no other arm is read)"}},
 "guardrails": {"prompts_file": "scripts/guardrails_safety_guard/prompts.yml", "prompts_sha256": sha(os.path.join(HERE, "guardrails_safety_guard", "prompts.yml")),
                "source": "examples/configs/content_safety_multilingual/prompts.yml of NVIDIA/NeMo-Guardrails at tag v0.24.1; equal to the prompts block of the tutorial docs/getting-started/tutorials/nemotron-safety-guard-deployment.mdx at the same tag"},
 "plan": ["generic_main", "generic_stability", "fp8_main", "fp8_stability"], "fp8_order": ["fp8_throughput", "fp8_latency"],
 "reference_figures_of_the_study_arm_J6": {"input_aegis2": j6("input"), "output_aegis2": j6("output"), "served_by": "upstream vLLM 0.20.2, BF16; 30.3 GiB of the card in use once ready"},
 "expectations": {
  "from_the_work_order": {"J6N": "starts; detection and false alarm inside the Wilson intervals of J6; verdicts per second at c=16 within 15% of J6",
                          "J6N-fp8": "an even chance that it does not start; if it starts, detection within 2 points of J6N"},
  "added_here": {"J6N": "c=1 p50 within 15% of J6's (204.1 ms input, 295.4 ms output); stability at least 98%",
                 "J6N-fp8": "does not report ready (about 70%): the image itself lists both FP8 profiles as incompatible with this system, by device id",
                 "J6N-tpl": "detection and false alarm within 1 point of J6N on every data set: the prompts differ by 23 blanks",
                 "J6G": "the rail blocks both violating controls and allows both harmless ones. Among the 100 items of a track a few (0 to 10) are blocked although the study's parser reads their completion as safe: "
                        "the prompts file sets max_tokens 50, J6's answers reach more than that on some items (p99 of its output tokens is in the reference figures), a cut JSON object does not parse, and the library's parser counts that as unsafe",
                 "confidence": "moderate for J6N; low for the others"}},
 "branches_decided_in_advance": {
  "J6N reports ready": "its figures stand beside J6's; whether it replaces J6 in the main table and the figures is decided by the people who write the article",
  "J6N does not report ready": "the reason, the first error line and the profile listing are the result; J6 stays as it is",
  "J6N-fp8 reports ready": "one more line, labelled 'FP8 TensorRT-LLM profile built for RTX PRO 6000 Blackwell, pinned on an RTX 5090', with both differences named",
  "J6N-fp8 does not report ready": "one sentence and the error text",
  "J6G's rail decision differs from the verdict of the same completion": "each such item is listed by id and class (answer cut, answer unreadable, library raised); the configuration is not changed to make them agree",
  "a precheck fails": "that arm and track is null, as in the study"},
 "not_in_this_file": ["any change to the study's figures or files", "the documentation example's request parameters (max_tokens 2048, top_p 1) as an arm of their own", "more than 16 calls in flight", "another card"],
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in NEW + USED},
 "study_files_unchanged": {f: sha(os.path.join(HERE, f)) == P93["harness_sha256"].get(f) for f in USED if f in P93["harness_sha256"]},
 "programs_written_after_the_freeze": "none planned; if one is needed, its SHA-256 is written to the events file before its first use",
}
os.makedirs(RES, exist_ok=True)
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT), "| study files unchanged:", all(pred["study_files_unchanged"].values()), "| listing:", {k: v["section"] for k, v in pred["known_before_the_run"]["listing_on_this_card"]["profiles"].items()})
