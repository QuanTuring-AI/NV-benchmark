#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q1 · gate G1: the scorer's positive and negative controls, run through lm-eval's own pipeline
(the pinned version, the same task configurations, filters and metrics) with a stand-in model that returns chosen text
instead of calling a server. No GPU, no model.

  GSM8K  positive: "The final answer is <reference number>" for every item          -> strict-match must be 100%
         negative: the reference numbers permuted across items (fixed seed)          -> near chance (reported)
  MMLU   positive: " <reference letter>" after the task's assistant prefix, sample  -> 100%
         negative: the reference letters permuted across the sample                 -> near 25% (reported)
  IFEval has no reference response. positive: for every prompt that carries exactly one instruction of a type whose
         satisfying text can be written mechanically from the instruction's own arguments (listed in CONSTRUCT), that
         text -> prompt-level strict must be 100%. negative 1: an empty response for all 541 prompts; negative 2: the
         constructed responses permuted across the eligible prompts (reported).
usage: p62_scorer_controls.py <out.json> <mmlu_sample_ids.json>
"""
import json, os, random, sys

from lm_eval import simple_evaluate
from lm_eval.api.model import LM

SEED = 20260926
out_path, ids_path = sys.argv[1], sys.argv[2]
IDS = json.load(open(ids_path, encoding="utf-8"))["ids"]


class Stand(LM):
    def __init__(self, fn):
        super().__init__(); self.fn = fn; self.calls = 0

    def generate_until(self, requests, disable_tqdm=False):
        self.calls += len(requests)
        return [self.fn(r.task_name, r.doc_id, r.doc) for r in requests]

    def loglikelihood(self, requests, disable_tqdm=False):
        raise NotImplementedError

    def loglikelihood_rolling(self, requests, disable_tqdm=False):
        raise NotImplementedError


def run(tasks, fn, samples=None):
    lm = Stand(fn)
    r = simple_evaluate(model=lm, tasks=tasks, samples=samples, apply_chat_template=False, fewshot_as_multiturn=False, log_samples=True, bootstrap_iters=0)
    return r, lm.calls


def perm(xs):
    p = list(xs); random.Random(SEED).shuffle(p); return p


res = {"lm_eval_version": __import__("lm_eval").__version__, "seed": SEED}

# ---- GSM8K
gold = {}
def g_pos(t, i, d):
    g = d["answer"].split("####")[-1].strip(); gold[i] = g; return f"The final answer is {g}"
r, n = run(["gsm8k_cot_llama"], g_pos)
res["gsm8k_positive"] = {"items": n, "strict_match": r["results"]["gsm8k_cot_llama"]["exact_match,strict-match"],
                        "flexible_extract": r["results"]["gsm8k_cot_llama"]["exact_match,flexible-extract"]}
keys = sorted(gold); pm = dict(zip(keys, perm([gold[k] for k in keys])))
r, n = run(["gsm8k_cot_llama"], lambda t, i, d: f"The final answer is {pm[i]}")
res["gsm8k_negative"] = {"items": n, "strict_match": r["results"]["gsm8k_cot_llama"]["exact_match,strict-match"],
                        "coincidental_equal_references": sum(1 for k in keys if pm[k] == gold[k])}

# ---- MMLU (the pre-registered sample)
L = "ABCD"
mg = {}
def m_pos(t, i, d):
    mg[(t, i)] = L[d["answer"]]; return " " + L[d["answer"]]
r, n = run(["mmlu_llama"], m_pos, IDS)
res["mmlu_positive"] = {"items": n, "exact_match": r["results"]["mmlu_llama"]["exact_match,strict_match"]}
mk = sorted(mg); mp = dict(zip(mk, perm([mg[k] for k in mk])))
r, n = run(["mmlu_llama"], lambda t, i, d: " " + mp[(t, i)], IDS)
res["mmlu_negative"] = {"items": n, "exact_match": r["results"]["mmlu_llama"]["exact_match,strict_match"],
                        "coincidental_equal_references": sum(1 for k in mk if mp[k] == mg[k])}

# ---- IFEval
FILL = "The committee reviewed the proposal carefully and agreed that the plan should move forward next month after the budget review"
CONSTRUCT = {
    "punctuation:no_comma": lambda kw: FILL + ".",
    "change_case:english_lowercase": lambda kw: FILL.lower() + ".",
    "change_case:english_capital": lambda kw: FILL.upper() + ".",
    "startend:end_checker": lambda kw: FILL + ". " + kw["end_phrase"],
    "startend:quotation": lambda kw: '"' + FILL + '."',
    "detectable_format:title": lambda kw: "<<Plan Review>>\n" + FILL + ".",
    "detectable_format:json_format": lambda kw: '{"summary": "' + FILL + '"}',
    "detectable_content:postscript": lambda kw: FILL + ".\n" + kw["postscript_marker"] + " " + FILL + ".",
    "keywords:existence": lambda kw: FILL + ". " + " ".join(kw["keywords"]) + ".",
}
eligible, resp = [], {}
def i_probe(t, i, d):
    ins = d["instruction_id_list"]
    if len(ins) == 1 and ins[0] in CONSTRUCT:
        kw = {k: v for k, v in d["kwargs"][0].items() if v is not None}
        eligible.append(i); resp[i] = CONSTRUCT[ins[0]](kw); return resp[i]
    return ""
r, n = run(["ifeval"], i_probe)
res["ifeval_negative_empty"] = {"items": n, "prompt_level_strict": r["results"]["ifeval"]["prompt_level_strict_acc,none"],
                                "note": "all prompts answered with an empty string except the eligible ones in this same pass; the eligible ones are scored separately below"}
el = sorted(set(eligible))
samp = {s["doc_id"]: s for s in r["samples"]["ifeval"]}
empty_only = [samp[k]["prompt_level_strict_acc"] for k in samp if k not in set(el)]
res["ifeval_negative_empty"]["prompt_level_strict_non_eligible"] = sum(empty_only) / len(empty_only)
res["ifeval_negative_empty"]["non_eligible_items"] = len(empty_only)
pos = [samp[k]["prompt_level_strict_acc"] for k in el]
by_type = {}
for k in el:
    t = samp[k]["doc"]["instruction_id_list"][0]; by_type.setdefault(t, []).append(samp[k]["prompt_level_strict_acc"])
res["ifeval_positive_constructed"] = {"items": len(el), "prompt_level_strict": sum(pos) / len(pos) if pos else None,
                                      "by_instruction_type": {t: [sum(v), len(v)] for t, v in sorted(by_type.items())}}
pr = dict(zip(el, perm([resp[k] for k in el])))
r, n = run(["ifeval"], lambda t, i, d: pr.get(i, ""), {"ifeval": el})
res["ifeval_negative_permuted"] = {"items": n, "prompt_level_strict": r["results"]["ifeval"]["prompt_level_strict_acc,none"]}
json.dump(res, open(out_path, "w", encoding="utf-8", newline="\n"), indent=1, sort_keys=True)
print(json.dumps(res, indent=1, sort_keys=True))
