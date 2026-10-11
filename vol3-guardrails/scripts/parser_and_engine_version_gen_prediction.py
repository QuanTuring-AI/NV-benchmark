#!/usr/bin/env python3
"""Vol.3 · writes the pre-registration of two follow-up arms (J2P: the reasoning parser on the whole of both tracks;
J6-v010: the Safety Guard model on upstream vLLM 0.10.0) and its .sha256 file. A supplement to the judge study's
pre-registration and to the two that followed it; none of them is changed. Run once, before the first container.
usage: parser_and_engine_version_gen_prediction.py --v010-digest sha256:... [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from p93_common import NIM_N3  # noqa: E402

RES = os.path.join(VOL, "results", "parser_and_engine_version"); OUT = os.path.join(RES, "prediction_parser_and_engine_version.json")
DRAFT = "--draft" in sys.argv
DIGEST = sys.argv[sys.argv.index("--v010-digest") + 1]
if not (DIGEST.startswith("sha256:") and len(DIGEST) == 71):
    sys.exit("give the image digest as sha256:<64 hex>, copied from `docker image inspect`")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def summ(*parts):
    return json.load(open(os.path.join(VOL, "results", *parts, "summary.json"), encoding="utf-8"))


def figures(S, track, group="aegis2"):
    T = S["tracks"][track]; q = T["quality"][group]
    o = {"detection": [q["detection"]["k"], q["detection"]["n"]], "false_alarm": [q["false_alarm"]["k"], q["false_alarm"]["n"]],
         "c1_latency_ms_p50": T["c1"]["latency_ms"]["p50"], "c16_verdicts_per_s": round(T["quality_cell"]["verdicts_per_s"], 2), "no_verdict": q["no_verdict"]}
    if "rail" in q:
        o["rail_blocks"] = {"harmful": [q["rail"]["block_on_harmful"]["k"], q["rail"]["block_on_harmful"]["n"]], "harmless": [q["rail"]["block_on_harmless"]["k"], q["rail"]["block_on_harmless"]["n"]]}
    return o


J2, J6T, J6N = summ("p93_judges", "J2"), summ("safety_guard_nim", "J6-today"), summ("safety_guard_nim", "J6N")
settings = os.path.join(RES, "before_the_run", "engine_settings_from_start_logs.json")
S = json.load(open(settings, encoding="utf-8"))
NEW = ["parser_and_engine_version_run.py"]
USED = ["p93_judge.py", "p93_gr_worker.py", "p93_parse.py", "p93_configs.py", "p93_common.py", "p93_analyze.py", "p93_run.py", "p102_run.py", "p102_cells.py"]
P93 = json.load(open(os.path.join(VOL, "results", "p93_judges", "prediction_p93.json"), encoding="utf-8"))
pred = {
 "what": "Pre-registration of two follow-up arms of the judge study: the reasoning parser on the whole of both tracks, and the Safety Guard model on upstream vLLM 0.10.0",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": f"../{d}/{f}", "sha256": sha(os.path.join(VOL, "results", d, f))} for d, f in (("p93_judges", "prediction_p93.json"), ("p102_followup", "prediction_p102.json"), ("safety_guard_nim", "prediction_safety_guard_nim.json"))],
 "kept_from_the_study": "items, subsets, labels, the precheck's controls and prompts, the answer parser, the definitions of every figure, greedy sampling, the idle-card gate before every container start and every cell, and the scope rule: "
                        "every figure is about one arm, and no per-item result of one arm is read together with a per-item result of another arm",
 "host": {"card": "one RTX 5090 (32 GB), Windows 11 + Docker Desktop (WSL2)", "graphics_driver": "610.88 since 2026-10-06 (the study's cells of 2026-10-02 and 2026-10-03 recorded 591.86)",
          "consequence": "a figure of these arms is set beside figures of 2026-10-06 (J6-today, J6N) for speed. Beside the study's J2 of 2026-10-02 the day and the driver differ as well; for J2P the question is about verdicts and the rail, not about speed."},
 "arms": {
  "J2P": {"served_by": {"image": NIM_N3["image"], "index_digest": NIM_N3["index_digest"], "profile": NIM_N3["profile"], "precision": NIM_N3["precision"], "env": NIM_N3["env"],
                        "added": "NIM_PASSTHROUGH_ARGS=--reasoning-parser nemotron_v3"},
          "asked": "as the study's arm J2: the NeMo Guardrails self-check action with the Vol.1 rail prompts, reasoning on, 1,024 tokens (p93_judge.py --arm J2, unchanged)",
          "cells": "per track: precheck, c=1 on the 200-item subset, c=16 on the whole track (2,423 prompts, 813 responses); in a new container the stability subset again (200 and 100 items)",
          "one_variable_against": "J2 of the study: the parser argument on the server",
          "why": "the study's J2 found that the rail blocks every item when the model's reasoning arrives inline; a follow-up showed on 100 stored prompts that the server-side parser repairs it (45 blocked, 55 allowed). "
                 "A setting an article recommends should have the figures of the whole set.",
          "recorded_beside_the_study_figures": "for each item of the whole-track cell, its rail decision and the verdict the study's parser reads from the same completion; items where the two differ, by id and class"},
  "J6-v010": {"served_by": {"image": "vllm/vllm-openai:v0.10.0", "digest": DIGEST, "model": "nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3 at the study's revision, mounted from the hub cache",
                            "command": "the study's upstream-vLLM start with the image name replaced: --max-model-len 8192, nothing else set"},
              "asked": "as the study's arm J6 (p93_judge.py --arm J6, unchanged)", "cells": "per track: precheck, c=1, c=16; no stability rerun",
              "why": "the model's NIM 1.14.0 gave 19% to 20% fewer verdicts per second than upstream vLLM 0.20.2 the same night, and its engine reports itself as built from vLLM 0.10.0. "
                     "Upstream 0.10.0 with the same model separates the engine version from everything else the NIM brings.",
              "against": {"J6N (NIM 1.14.0)": "the NIM's packaging and settings (same engine version by its own report, as far as a version string says)", "J6-today (upstream 0.20.2)": "the engine version"}}},
 "known_before_the_run": {
  "J2_of_the_study": {"input_aegis2": figures(J2, "input"), "output_aegis2": figures(J2, "output")},
  "the_100_item_follow_up": "results/p102_followup: with the parser the rail blocked 45 and allowed 55 of 100 stored prompts; without it 100 of 100",
  "J6_today_and_J6N": {"J6-today": {"input": figures(J6T, "input"), "output": figures(J6T, "output")}, "J6N": {"input": figures(J6N, "input"), "output": figures(J6N, "output")}},
  "engine_settings_the_two_servers_printed": {"file": "before_the_run/engine_settings_from_start_logs.json", "sha256": sha(settings),
                                              "reading": "both run BF16 with a context of 8,192, prefix caching on and chunked prefill on, the Flash Attention backend, and no sequence limit set by argument. "
                                                         "They differ in the engine version line, in the memory share (0.9 for the NIM, 0.92 for upstream 0.20.2, which also profiles CUDA graph memory), in the KV cache that results "
                                                         "(108,144 and 104,800 tokens) and in the number of CUDA graph sizes captured (67 and 51). Nothing in the list is a setting that would by itself explain a fifth.",
                                              "values": {k: {x: v[x] for x in ("engine_version_line", "gpu_memory_utilization", "max_num_seqs_argument", "chunked_prefill", "max_num_batched_tokens_line",
                                                                              "gpu_kv_cache_tokens", "cudagraph_capture_sizes_count", "attention_backend_line")} for k, v in S.items()}}},
 "serving": {"vllm_0_10_0": {"image": "vllm/vllm-openai:v0.10.0", "digest": DIGEST}, "ready_limit_s": 1800, "cell_limit_s": 1800,
             "containers": "named vol3fu_<step>; one on the card at a time"},
 "plan": ["parser_main", "parser_stability", "v010_main", "summary"],
 "branches_decided_in_advance": {
  "J2P": {"rail and verdict of the same call differ on at most 1% of the items of a track": "the article states the whole-set figures for the recommended setting",
          "on more than 1%": "every such item is listed by id and class, and the figures are written as they are; the configuration is not changed to make them agree",
          "the container does not report ready with the argument": "the start-up lines that mention the argument are the result"},
  "J6-v010": {"within 5% of J6N on verdicts per second (both tracks)": "the difference to upstream 0.20.2 goes with the engine version the NIM carries",
              "within 5% of J6-today": "the difference lies in what the NIM adds or sets, not in the engine version",
              "in between": "both contribute; the three figures are written side by side and the share is not assigned",
              "the image does not start on this card or host": "the first error line is the result and the question stays open"}},
 "expectations": {
  "J2P": "the model generates the same text with and without a parser on the server, so the verdicts stay those of J2: detection and false alarm within 1 point of J2 on each data set. The rail follows the verdict: "
         "it differs on at most 0.5% of the items (answers cut at 1,024 tokens, where there is no verdict and the rail blocks). Verdicts per second within 10% of J2's (9.4 and 8.1), day and driver notwithstanding.",
  "J6-v010": "nearer to J6N than to J6-today: verdicts per second at c=16 between 37 and 42 on prompts (J6N 38.5, J6-today 47.5). The settings the two servers printed do not differ in anything that looks like a fifth, "
             "which leaves the engine version. Verdicts as J6-today's, within the Wilson intervals.",
  "confidence": "moderate for J2P's verdicts and rail; low for J6-v010 (one reading of two logs)"},
 "not_in_this_file": ["any change to earlier figures or files", "the parser for other models", "other vLLM versions between 0.10.0 and 0.20.2", "more than 16 calls in flight"],
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
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT), "| study files unchanged:", all(pred["study_files_unchanged"].values()))
