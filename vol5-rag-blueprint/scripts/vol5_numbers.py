#!/usr/bin/env python3
"""Vol.5 · the numbers table for the article: every number read from a result file of this volume and printed with its
file and key, so that a row can be checked by opening the file. Nothing is typed by hand; a key that is missing stops
the program. Writes results/NUMBERS.md.
usage: vol5_numbers.py
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE); RES = os.path.join(V5, "results")
rows, sections = [], []


def get(path, key):
    d = json.load(open(os.path.join(RES, path), encoding="utf-8"))
    for k in (key.split("/") if "/" in key else key.split(".")):   # "/" separates keys that themselves hold a dot
        d = d[int(k)] if isinstance(d, list) else d[k]
    return d


def fmt(v, nd):
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def row(what, path, key, nd=4, unit=""):
    rows.append((what, fmt(get(path, key), nd) + unit, f"`results/{path}`", f"`{key}`"))


def section(title):
    rows.append((f"**{title}**", "", "", ""))


section("C1 · HotpotQA whole corpus, the Blueprint's default Elasticsearch index (5,233,329 passages, 7,405 questions)")
row("nDCG@10, default query (k = num_candidates = 100)", "night1/c1_score.json", "metrics.ndcg_cut_10")
row("Recall@100, default query", "night1/c1_score.json", "metrics.recall_100")
row("overlap with the exact top 10 (mean)", "night1/c1_score.json", "overlap_at_10.mean")
row("overlap with the exact top 100 (mean)", "night1/c1_score.json", "overlap_at_100.mean")
row("negative control: overlap at 10 (k 10, num_candidates 10, no rescore)", "night1/c1_negative_score.json", "overlap_at_10.mean")
row("five questions by brute force on the whole index: overlap at 100", "night1/c1_brute5_score.json", "overlap_at_100.mean")
row("validity gate (b1): questions whose ES exact top 100 equals numpy's", "night1/control_b1_gate.json", "passed")
row("index size (bytes)", "night1/c1_index.json", "0/store.size")
row("latency p50, cold start, all questions (ms)", "night3/latency_cold/blueprint_100.json", "settings.blueprint:100.ms.p50", 1)
row("latency p99, cold start (ms)", "night3/latency_cold/blueprint_100.json", "settings.blueprint:100.ms.p99", 1)
section("C1 · num_candidates: quality (day, all questions, on the index after its segment merges) and cold-start latency")
row("baseline for this section: the default query rerun on the same index state, nDCG@10", "day3/nc_blueprint_100_now_score.json", "metrics.ndcg_cut_10")
row("baseline: Recall@100", "day3/nc_blueprint_100_now_score.json", "metrics.recall_100")
row("ES only 200 against that baseline: questions with the identical top 100", "day3/nc_es200_vs_100_now.json", "identical")
for tag, label in (("blueprint_200", "Blueprint knob 200 (k = num_candidates)"), ("blueprint_400", "Blueprint knob 400 (its limit)"),
                   ("es-only_200", "ES only, num_candidates 200 (k 100)"), ("es-only_500", "ES only, 500"), ("es-only_1000", "ES only, 1000")):
    row(f"{label}: nDCG@10", f"day3/nc_{tag}_score.json", "metrics.ndcg_cut_10")
    row(f"{label}: Recall@100", f"day3/nc_{tag}_score.json", "metrics.recall_100")
    st = tag.replace("_", ":", 1)
    row(f"{label}: latency p50, cold start (ms)", f"night3/latency_cold/{tag}.json", f"settings.{st}.ms.p50", 1)
section("C1 · MIRACL zh whole corpus (4,934,368 passages, 393 questions)")
row("nDCG@10, default query", "day3/zh_score.json", "metrics.ndcg_cut_10")
row("Recall@100", "day3/zh_score.json", "metrics.recall_100")
row("overlap with the exact top 100 (mean)", "day3/zh_score.json", "overlap_at_100.mean")
row("validity gate: questions equal on the 100,000-passage slice", "day3/zh_validity_gate.json", "passed")
row("latency p50, cold start (ms)", "night3/latency_cold/zh_blueprint_100.json", "settings.blueprint:100.ms.p50", 1)
section("C2 · answers on HotpotQA (7,405 questions): N no passages, P the Blueprint's path, O the two supporting passages")
row("N contains", "c2/score_n_o.json", "N.contains_rate")
row("P contains", "night3/p_score.json", "score.contains_rate")
row("O contains", "c2/score_n_o.json", "O.contains_rate")
row("P refusals by pattern", "night3/p_score.json", "score.refused_by_pattern")
row("P vs N: only P right", "night3/p_score.json", "paired_P_N.only_a")
row("P vs N: only N right", "night3/p_score.json", "paired_P_N.only_b")
row("P vs O: only O right", "night3/p_score.json", "paired_P_O.only_b")
row("questions whose ten passages hold both supporting passages", "night3/p_score.json", "supporting_passages_among_the_ten.both")
row("N answers that reached the limit without closing the reasoning", "c2/token_and_strip_detail.json", "N.no_close_tag")
row("N reasoning tokens, median", "c2/token_and_strip_detail.json", "N.reasoning_tokens_median_closed", 0)
section("C3 · 200 questions with their supporting passages kept out")
row("refusals by pattern (a lower bound)", "night3/c3_refusals.json", "refused_by_pattern")
row("hand-labelled 50: refusals", "night3/c3_label_check.json", "hand_refusal")
row("hand-labelled 50: agreement with the pattern", "night3/c3_label_check.json", "agree")
row("answers that still contain the gold answer", "night3/c3_contains.json", "C3.contains")
row("the same 200 questions in arm P (passages not kept out): contain", "night3/c3_contains.json", "P_same_questions.contains")
row("only arm P right (paired)", "night3/c3_contains.json", "paired_C3_P.only_b")
section("Cell R · the NIM documentation's reasoning parser (200 questions)")
row("answers with the reasoning separated", "night3/r_vs_p.json", "R.reasoning_separated")
row("answers still above 256 reasoning tokens", "night3/r_vs_p.json", "R.reasoning_tokens_above_256")
section("MIRACL zh P (393 questions)")
row("share with a judged-relevant passage among the ten", "night3/zh_p_judged.json", "share")
row("answers that reached the limit", "night3/zh_p_refusals.json", "finish_reason.length")
section("C4 · one card")
row("positive control: shared peak (MiB)", "c4/c4_summary.json", "pc.shared_peak_mib")
row("configuration 1: shared peak during the answer model's start (MiB)", "c4/c4_summary.json", "c1.shared_peak_mib")
row("configuration 1: shared maximum after ready (MiB)", "c4/c4_summary.json", "c1.peak_after_answer_model_ready_mib")
row("configuration 1: card used at ready (MiB)", "c4/c4_summary.json", "c1.card_used_at_answer_model_ready_mib")
row("configuration 1 (vl embedder): card used about a minute after ready, at the configuration's completion (MiB)",
    "c4/card_used.json", "configurations.c1.at_configuration_complete_mib")
row("configuration 5 (n3 embedder): card used at ready (MiB)", "c4/card_used.json",
    "configurations.ready5.at_answer_model_ready_mib")
row("configuration 5 (n3 embedder): card used about a minute after ready, at the configuration's completion (MiB)",
    "c4/card_used.json", "configurations.ready5.at_configuration_complete_mib")
row("ready cell (n3 embedder): shared maximum after ready (MiB)", "c4/ready1_after_ready.json", "window_max_mib")
row("ready cell: allowance (MiB)", "c4/ready1_after_ready.json", "allowance_mib", 0)
section("C4 · configuration 5 (answer model context 32768, supplement 7): the Blueprint's own request, then all three on the card")
row("answer model alone: max_model_len read back", "c4/ready5_alone_probe.json", "max_model_len.0")
row("answer model alone: arm N's captured request, HTTP status", "c4/ready5_alone_probe.json", "requests.0.status")
row("answer model alone: arm P's captured request, HTTP status", "c4/ready5_alone_probe.json", "requests.1.status")
row("shared maximum after ready (MiB)", "c4/ready5_after_ready.json", "window_max_mib")
row("allowance (MiB)", "c4/ready5_after_ready.json", "allowance_mib", 0)
row("shared maximum over the whole run, the answer model's start included (MiB)", "c4/ready5_after_ready.json", "whole_run_max_mib")
for c in (1, 4):
    row(f"c = {c}: requests answered (of 200)", f"c4/ready5_c{c}.json", "ok")
    row(f"c = {c}: reranker stage p50 (ms)", f"c4/ready5_c{c}.json", "fields.context_reranker_time_ms.p50", 1)
    row(f"c = {c}: the server's time to first token (rag_ttft_ms) p50 (ms)", f"c4/ready5_c{c}.json", "fields.rag_ttft_ms.p50", 1)
    row(f"c = {c}: whole call p50 (ms)", f"c4/ready5_c{c}.json", "fields.client_total_ms.p50", 1)
    row(f"c = {c}: whole call p99 (ms)", f"c4/ready5_c{c}.json", "fields.client_total_ms.p99", 1)
row("alone, reranker (4 calls) p50 (ms)", "c4/not_coresident/rank.json", "fields.rank_ms.p50", 1)
row("alone, answer model first answer text p50 (ms)", "c4/not_coresident/llm.json", "fields.first_answer_ms.p50", 1)
row("alone, answer model done p99 (ms)", "c4/not_coresident/llm.json", "fields.done_ms.p99", 1)
section("Ingestion through the Blueprint's ingestor (100,000 passages)")
row("passages stored without their last token (only the end missing)", "night1/control_b_diagnosis.json", "ingestor_text.only_the_end_missing")
row("passages changed inside (all with non-ASCII text)", "night1/control_b_diagnosis.json", "ingestor_text.changed_inside")

out = ["# Vol.5 · numbers table (generated by `scripts/vol5_numbers.py`; every value read from the file and key shown)", "",
       "| what | value | file | key |", "|---|---|---|---|"] + [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
open(os.path.join(RES, "NUMBERS.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print(f"{sum(1 for r in rows if r[1])} numbers")
