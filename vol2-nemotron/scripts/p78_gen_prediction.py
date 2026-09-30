#!/usr/bin/env python3
"""Vol.1 / Vol.2 · P78 · pre-registrations, one per stage, written before the stage's first GPU cell and frozen by the
caller (scanned first, then the .sha256 sidecar). Each file states the configuration, the gates, what each branch does, the
predictions with their pass conditions, and binds the harness files and inputs by SHA-256.
Paths are derived from this file's location; no volume directory name is written here (the result directories are found
from the harness files that write them).
usage: p78_gen_prediction.py <stage: fp8|quality|nimvllm|rerun|n2up> <written_at>
"""
import glob, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))


def find(name):
    hits = [p for p in glob.glob(os.path.join(REPO, "*", "scripts", name)) + glob.glob(os.path.join(REPO, "tools", name)) if "_internal" not in p]
    assert len(hits) == 1, (name, hits)
    return hits[0]


def find_result(sub):
    hits = [p for p in glob.glob(os.path.join(REPO, "*", "results", sub)) if "_internal" not in p]
    assert len(hits) == 1, (sub, hits)
    return hits[0]


sys.path.insert(0, os.path.dirname(find("prediction_guard.py")))
from prediction_guard import check_prediction  # noqa: E402

rel = lambda p: os.path.relpath(os.path.abspath(p), REPO).replace(os.sep, "/")
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
bind = lambda names: {rel(find(n)): h(find(n)) for n in names}
TOOLS = ["g8_gate.py", "host_gate.py", "overwrite_gate.py", "renumber_dirs.py"]
COMMON = {
    "written_before": "the stage's first GPU cell (run_p78.sh refuses a stage whose prediction or .sha256 is missing or changed, or whose results exist)",
    "window": "the night of 2026-09-29 to 30; the user closes Steam and other heavy host load before the run",
    "gates_every_cell": {
        "G8": "tools/g8_gate.py before every measured cell: median GPU utilization <= 2% and median power <= 45 W over 10 s; retried every 60 s up to 15 min; a cell whose G8 did not pass is null, recorded",
        "host": "tools/host_gate.py: a CPU-work calibration before the run and, per cell, wall time, system CPU busy share, this process's CPU share, children's CPU seconds and a work probe at the cell's end; recorded, not a gate (no measured threshold exists yet)",
        "no_overwrite": "tools/overwrite_gate.py after every cell: tracked files unchanged and new files only under this stage's results directory, else the stage stops (exit 4) and the cell is void",
        "old_directory_gate": "tools/renumber_dirs.py check-old-dirs before every stage: a harness written for old paths must not recreate an old directory",
        "exit_code": "the runner writes each harness's exit code into the stage's results directory",
    },
    "deadline": "08:00: a stage or cell not started by then is not started; finished cells are kept; what is left is listed in the report",
}


def stage_fp8():
    out = os.path.join(os.path.dirname(find("p78_fp8_clean.py")), "..", "results", "p78_fp8_clean")
    p70 = json.load(open(os.path.join(find_result("p70_clean_recheck"), "analysis.json"), encoding="utf-8"))
    oq4, nb = p70["cells"]["O-Q4|128"]["total_tps"], p70["cells"]["N-BF16|128"]["total_tps"]
    p59 = json.load(open(os.path.join(find_result("p59_nim_value"), "analysis.json"), encoding="utf-8"))
    f59, b59 = p59["levels"]["N-FP8|C|main"]["128"]["total_tps"], p59["levels"]["N-BF16|C|main"]["128"]["total_tps"]
    return out, "prediction_p78_fp8.json", {
        "experiment": "P78 G1 · Vol.1 · NIM's own FP8 choice at 1, 32 and 128 concurrent requests in a clean window, with a prefix-cache detector that tells warm-up from a cache hit",
        "why": "P70's FP8 arm was refused by P59's detector (two different prompts, ratio 0.535): the first request after a start is slow for reasons that are not a cache. P59's and P70's pre-registrations are not changed.",
        "arms": {"N-FP8": {"levels": [1, 32, 128]}, "N-BF16": {"levels": [128], "role": "anchor in the same window"}},
        "unchanged_from_p70": "image, profiles, context 8192, isolation check, discarded 120 s warm-up level, calibration, AIPerf command (profile C, streaming, --use-legacy-max-tokens, client token counts), 60 s per level, seed 20260925 + c",
        "detector": {"steps": ["one discarded fresh prompt", "five pairs of two different fresh prompts, the first-sent alternating between pairs; r_k = TTFT(second)/TTFT(first)",
                               "positive control: one fresh prompt twice; r_s = TTFT(second)/TTFT(first)"],
                     "threshold": "T = 0.8 x min(r_1..r_5), from this container's five pairs", "fired": "r_s < T", "pass": "fired",
                     "branch": "positive control does not fire -> that arm is null, reported as it is; the threshold is not changed and the arm is not re-run tonight",
                     "self_test": "four synthetic sequences through the same function (same-prompt cache only: pass; no cache: fail; cross-prompt hits: fail; P70's slow first pair after warm-up: pass), recorded in events.jsonl before the first container"},
        "denominators": {"O-Q4_at_128_tok_s": round(oq4, 2), "source": "P70 analysis.json cells.O-Q4|128.total_tps (clean window)",
                         "N-BF16_at_128_P70_tok_s": round(nb, 2), "P59_N-FP8_at_128_tok_s": round(f59, 2), "P59_N-BF16_at_128_tok_s": round(b59, 2)},
        "predictions": {
            "R1": {"what": "N-FP8 total tok/s at 128 / 780.24 (P70's clean O-Q4)", "pass_if": "in [10.5, 13.5]", "p59_value": round(f59 / oq4, 3)},
            "R2": {"what": "N-FP8 / N-BF16 total tok/s at 128, same window", "pass_if": "in [1.45, 1.75]", "p59_value": round(f59 / b59, 3)},
            "R3": {"what": "N-BF16 at 128 against P70's clean value", "pass_if": "within +-5% of " + str(round(nb, 1))},
            "record": "N-FP8 at 1 and 32; the detector's five pair ratios, threshold and positive-control ratio per arm"},
        "harness_sha256": bind(["p78_fp8_clean.py", "p70_clean_recheck.py", "p59_nim_value.py", "p54_engine.py", "p50_footprint.py", "p53_concurrency.py", "run_p78.sh", *TOOLS]),
        **COMMON}


def stage_quality():
    out = find_result("p78_quality") if glob.glob(os.path.join(REPO, "*", "results", "p78_quality")) else os.path.join(HERE, "..", "results", "p78_quality")
    import p78_quality as Q
    ids = Q.MMLU_IDS
    return out, "prediction_p78_quality.json", {
        "experiment": "P78 G2 / G3 (and G4's quality arms) · answer quality of Nemotron 3 Nano (NIM 2.0.12, NVFP4) and Nemotron Nano 9B v2 (NIM 1.12.2, bf16), reasoning on and off",
        "tasks": {"gsm8k": "gsm8k_cot_llama, all 1,319 test items, 8-shot multi-turn", "mmlu": "mmlu_llama restricted to P62's 50 x 57 sample (2,850 items), 5-shot"},
        "lm_eval": "0.4.13 (pinned venv), local-chat-completions, --apply_chat_template, --fewshot_as_multiturn, temperature 0, in chunks of 110 GSM8K items / 5 MMLU subjects, each chunk in its own process",
        "request_changes_by_the_proxy": [
            "stop removed", "mmlu_llama's trailing assistant 'The best answer is' removed, with continue_final_message and add_generation_prompt",
            "max_tokens 8192 with reasoning on, 1024 with reasoning off",
            "reasoning off: Nemotron 3 Nano and the upstream arms on its weights: chat_template_kwargs {enable_thinking: false}; Nemotron Nano 9B v2: system message '/no_think'",
            "content null from the server -> '' passed to lm-eval, recorded"],
        "engines": {"N3": "NIM 2.0.12, NVFP4 profile, NIM_MAX_MODEL_LEN 16384, max_num_seqs image default (256), concurrency 16",
                    "N2": "NIM 1.12.2, bf16 profile, NIM_MAX_MODEL_LEN 16384, NIM_MAX_NUM_SEQS 32, concurrency 16 (the engine exits when concurrency reaches the cap)",
                    "V3B1 / V3B2": "G4's upstream arms, reasoning off x GSM8K only (see prediction_p78_nim_vs_vllm.json)"},
        "cells": {k: [list(c) for c in v] for k, v in Q.PLAN.items()},
        "scoring": "p78_scorer.py on the whole output (reasoning channel, then content): the LAST match of 'final answer is <number>' (GSM8K, normalised as lm-eval does) or 'best answer is <A-D>' (MMLU); no match -> wrong and counted as no_answer; an output that hit the cap is scored from what it holds. Its self-test (11 controls) and mutation test ('first match wins' must fail) passed before this file was written.",
        "arm_health": "single-stream generation rate x bytes read per token (N3 3,590,938,272; N2 17,776,454,656; p50_speed analysis.json) / 1,792 GB/s; below 10% -> the arm is null. Warm-up: until 220 tok/s (N3, P55) or 300 s",
        "gates_and_branches": {
            "truncation": "any HTTP 400 from the engine in a cell -> that cell is null (the measurement is broken)",
            "cap": "an item that hit max_tokens is the model's behaviour: scored as it is, its share reported beside the accuracy",
            "engine_exit": "log tail kept, container started again, the cell resumes at the chunk that failed; a second exit in the same cell -> that cell null; the number of exits is reported",
            "hung_chunk": "timeout = max(600 s, 3 x the cell's mean seconds per item x items) (first chunk: every item at the cap at the single-stream rate per stream); stopped and retried once",
            "self_consistency": "per model: on x GSM8K run 1 vs run 2, paired difference over items, 95% CI (mean +- 1.96 sd / sqrt n); if the CI is not inside [-2, +2] pp, every equivalence verdict of that model is null (differences still reported)",
            "reasoning_really_off": "per model and task: median completion tokens with reasoning off <= 50% of reasoning on; else that model's off cells are null",
            "join": "every item joined to one proxy record by the sha256 of the messages lm-eval sent; unjoined items reported, a chunk with unjoined items is retried"},
        "statistics": "accuracy per cell; paired differences on the same items with 95% CI (mean +- 1.96 sd / sqrt n); completion-token distribution, cap share, no-answer share, seconds per item, total tok/s",
        "predictions": {
            "Q1_N3_gsm8k_on": "accuracy >= 88%", "Q1_N2_gsm8k_on": "accuracy >= 85%",
            "Q1_N3_mmlu_on": "accuracy >= 75%", "Q1_N2_mmlu_on": "accuracy >= 70%",
            "Q2_gsm8k_on_minus_off": "> 0 with the 95% CI above 0, for both models",
            "Q2_mmlu_on_minus_off": "within [-2, +6] pp, for both models",
            "Q2_tokens": "median completion tokens off <= 25% of on (GSM8K), for both models",
            "Q2_cap_share_on": "N3 <= 5%, N2 <= 10% of items at the 8,192 cap",
            "C1_concurrency": "N3 off x GSM8K first 200 items at c=1 vs the same items at c=16: accuracy difference within +-3 pp; share of byte-identical outputs recorded"},
        "inputs_sha256": {rel(ids): h(ids)},
        "harness_sha256": bind(["p78_quality.py", "p78_lmeval_chunk.py", "p78_scorer.py", "p78_engines.py", "p50_footprint.py", "run_p78.sh", *TOOLS]),
        **COMMON}


def stage_nimvllm():
    out = os.path.join(HERE, "..", "results", "p78_nim_vs_vllm")
    import p78_nim_vs_vllm as G4
    return out, "prediction_p78_nim_vs_vllm.json", {
        "experiment": "P78 G4 · Nemotron 3 Nano NVFP4 served by NIM 2.0.12 and by upstream vLLM 0.27.1 (the version inside it) on the same files",
        "arms": {"N3": "NIM 2.0.12, NVFP4 profile, NIM_MAX_MODEL_LEN 16384",
                 "V3B1": "vllm/vllm-openai:v0.27.1, the snapshot path only (bare)",
                 "V3B2": "the same image with NIM's own vLLM argument list for N3's configuration from `nim-serve --dry-run` (edits: model path, backend port, host, NIM middleware only)"},
        "order": "N3 -> V3B1 -> V3B2 in one session; then the quality arms V3B1, V3B2 (reasoning off x GSM8K, as N3's cell)",
        "per_arm": {"warm": "until 220 tok/s or 300 s", "single": "50 co-residence questions, p53_answer's request (max_tokens 4096, temperature 0, top_p 0.9, streamed), response sha256 kept, no text",
                    "concurrency": "profile C, discarded 120 s at c=1, then 1, 8, 32, 64, 128 at 60 s, G8 before each; SLO judged as p53_concurrency (MLPerf server: p99 TTFT <= 2 s and p99 TPOT <= 100 ms)"},
        "recorded_for_every_upstream_start": "mamba_ssm_cache_dtype, MoE backend, CUDA-graph mode, max_num_seqs (from the start log); first error line if it fails; B2's flags counted",
        "branches": {"B1_fails_to_start": "the error is recorded as a result (one answer to 'what does a user get without NIM'); B2 is run",
                     "B2_dry_run_gives_no_arguments": "V3B2 null"},
        "predictions": {
            "P1": "record, not a prediction: whether V3B1 starts and serves, and its values of the silent settings beside V3B2's. Disclosed before freezing: in the harness test (2026-09-29 20:31-20:56, 3 questions, one 20 s level per arm) both upstream arms started and their logs showed the same values (mamba_ssm_cache_dtype float32 set by vLLM itself for NemotronH, MoE backend FLASHINFER_CUTLASS, CUDA graphs FULL_AND_PIECEWISE, attention FLASHINFER, KV cache float8_e4m3fn); NIM's own log at its default level prints none of them",
            "P2": "V3B2 / N3 single-stream generation rate (median over the 50 questions) in [0.95, 1.05]",
            "P3": "V3B2 and N3 write byte-identical responses on >= 45 of 50 questions. Interpreted only if each of the two arms repeats its own text on >= 9 of the 10 self-repeat questions; otherwise the cross-arm count is recorded as not interpretable (the first harness test gave 0 of 3 identical between every pair of arms, with identical prompt token counts and divergent completion lengths; the second, 21:25-21:47, gave 0 of 2 in each arm's own self-repeat)",
            "P4": "V3B2 / N3 total tok/s within +-10% at every concurrency level both complete",
            "P5": "if V3B1's mamba_ssm_cache_dtype is not float32 while V3B2's is: V3B1's reasoning-off GSM8K accuracy is below V3B2's (direction only; the size is recorded)"},
        "inputs_sha256": {rel(G4.SAMPLE): h(G4.SAMPLE), "benchmark/questions.json": h(G4.QFILE)},
        "harness_sha256": bind(["p78_nim_vs_vllm.py", "p78_quality.py", "p78_engines.py", "p53_answer.py", "p53_concurrency_v2.py", "p53_concurrency.py", "p50_footprint.py", "run_p78.sh", *TOOLS]),
        **COMMON}


def stage_rerun():
    out = os.path.join(HERE, "..", "results", "p78_clean_rerun")
    import p78_clean_rerun as R
    s256 = [json.loads(l) for l in open(os.path.join(find_result("p55_concurrency_a2_256"), "levels.jsonl"), encoding="utf-8")]
    ref = {str(x["concurrency"]): round(x["summary"]["output_token_throughput"]["avg"], 1) for x in s256
           if x.get("profile") == "C" and x.get("container") == "main" and not x.get("warmup") and x.get("summary")}
    return out, "prediction_p78_clean_rerun.json", {
        "experiment": "P78 G6 · Vol.2 concurrency sweeps whose levels ended with other GPU load (Z3 audit, clean-window fingerprint: utilization 0%, 26-42 W at level end) and that feed a Vol.2 number, repeated with the GPU idle",
        "sweeps_in_priority_order": {k: {kk: vv for kk, vv in v.items()} for k, v in R.SWEEPS.items()},
        "unchanged": "image, profile id, environment of the original run; p53_concurrency_v2's calibration and level runner imported unchanged; level durations by its rule",
        "added": "G8 before every level; host record per level; no-overwrite check after every level",
        "original_results": "not changed; each sweep writes under its own directory",
        "predictions": {
            "P1": "s256_C: the largest level inside the MLPerf server SLO is 128, as in the original",
            "P2": "s256_C: total tok/s at every level >= 0.95 x the original's (other load can only have slowed the original)",
            "record": "every other sweep that runs: its levels beside the original's"},
        "s256_C_original_total_tok_s": ref,
        "harness_sha256": bind(["p78_clean_rerun.py", "p53_concurrency_v2.py", "p53_concurrency.py", "p50_footprint.py", "run_p78.sh", *TOOLS]),
        **COMMON}


def stage_n2up():
    out = os.path.join(HERE, "..", "results", "p78_n2_upstream")
    import p78_n2_upstream as G5
    return out, "prediction_p78_n2_upstream.json", {
        "experiment": "P78 G5 · Nemotron Nano 9B v2 bf16 on vllm/vllm-openai:v0.30.0 (newest stable upstream on 2026-09-29), as another deployment option; Z2 found no NIM image newer than 1.12.2",
        "ladder": G5.LADDER, "levels": G5.LEVELS, "depths_tokens": G5.DEPTHS,
        "context_prompts": "each request starts with its own tag so that no prefix is reused (the harness test's 16k TTFT of 114 ms was a prefix-cache hit); about 200 words asked, max_tokens 256",
        "disclosed_from_the_harness_test": "harness tests 2026-09-29 21:12-21:23 and 21:47-21:58: step 0 (model path only) started and served; c=16 (20 s) completed without an engine exit; single-stream rate 73.6-74.1 tok/s (3 questions); context, one request per depth in the second test: ~4k tokens 73.7 tok/s (TTFT 353 ms), ~16k tokens 73.1 tok/s (TTFT 1,356 ms). P3 is therefore written knowing one request per depth",
        "predictions": {"P1": "a ladder step <= 2 starts and serves", "P2": "no engine exit at 16, 32 or 64 concurrent requests",
                        "P3": "generation rate at ~16k tokens >= 80% of the rate at ~4k (NIM 1.12.2 lost 38% past ~8k)"},
        "harness_sha256": bind(["p78_n2_upstream.py", "p78_engines.py", "p78_quality.py", "p78_nim_vs_vllm.py", "p53_concurrency_v2.py", "run_p78.sh", *TOOLS]),
        **COMMON}


STAGES = {"fp8": stage_fp8, "quality": stage_quality, "nimvllm": stage_nimvllm, "rerun": stage_rerun, "n2up": stage_n2up}

if __name__ == "__main__":
    stage, written_at = sys.argv[1], sys.argv[2]
    out, fname, p = STAGES[stage]()
    p = {"written_at": written_at, **p}
    check_prediction(p)
    out = os.path.abspath(out); path = os.path.join(out, fname)
    if os.path.exists(path):
        sys.exit("prediction exists -- a pre-registration is written once")
    os.makedirs(out, exist_ok=True)
    json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
    print("written", rel(path), "binds", len(p["harness_sha256"]), "files")
