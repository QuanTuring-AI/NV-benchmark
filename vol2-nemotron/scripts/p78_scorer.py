#!/usr/bin/env python3
"""Vol.2 · P78 answer scorer for reasoning models (GSM8K and MMLU).

A reasoning model writes its answer after a long stretch of reasoning, and the reasoning may state intermediate or
wrong answers in the same format. The scorer therefore reads the WHOLE output (the reasoning channel first, if the server
returns one, then the content) and takes the LAST match of the answer format:
  GSM8K  "final answer is" (any case), then optional ':' / '*' / '$' / spaces, then a number; the number is normalised the
         way lm-eval's gsm8k_cot_llama does (',' and '$' removed, a trailing '.' removed) and compared as a string with the
         gold answer (the text after '####').
  MMLU   "best answer is" (any case), then optional ':' / '*' / '(' / spaces, then one letter A-D.
No match -> the item is wrong and counted as `no_answer`. An output that stopped at the token cap is still scored from
whatever it holds (a cap is the model's behaviour, not a measurement fault; its share is reported beside the accuracy).
usage: python p78_scorer.py --self-test    (positive, negative and mutation controls; exit 0 only if all hold)
"""
import re, sys

GSM_PAT = re.compile(r"final answer is[\s:*$]*(-?[0-9][0-9,]*(?:\.[0-9]+)?)", re.I)
MMLU_PAT = re.compile(r"best answer is[\s:*(]*([A-D])\b", re.I)


def full_text(content, reasoning=None):
    return (reasoning or "") + "\n" + (content or "")


def _norm_num(s):
    s = s.replace(",", "").replace("$", "").strip()
    return s[:-1] if s.endswith(".") else s


def gold_gsm8k(answer_field):
    return _norm_num(answer_field.split("####")[-1].strip())


def extract_gsm8k(text, pick=-1):
    m = GSM_PAT.findall(text or "")
    return _norm_num(m[pick]) if m else None


def extract_mmlu(text, pick=-1):
    m = MMLU_PAT.findall(text or "")
    return m[pick].upper() if m else None


def score(task, content, reasoning, gold, pick=-1):
    t = full_text(content, reasoning)
    got = extract_gsm8k(t, pick) if task == "gsm8k" else extract_mmlu(t, pick)
    return {"extracted": got, "correct": int(got is not None and got == gold), "no_answer": int(got is None)}


CONTROLS = [
    # (name, task, content, reasoning, gold, expected_correct, expected_no_answer)
    ("gsm_wrong_intermediate_then_right", "gsm8k",
     "First try: 12 + 3 = 15, so the final answer is 15. Wait, the question asks for the difference: 12 - 3 = 9. The final answer is 9",
     None, "9", 1, 0),
    ("gsm_well_formed_but_wrong", "gsm8k", "12 - 3 = 8. The final answer is 8", None, "9", 0, 0),
    ("gsm_markdown_and_thousands", "gsm8k", "Total cost: **The final answer is: $1,234.**", None, "1234", 1, 0),
    ("gsm_reasoning_channel_then_content", "gsm8k", "The final answer is 42", "maybe the final answer is 41", "42", 1, 0),
    ("gsm_answer_only_in_reasoning", "gsm8k", "", "so the final answer is 42", "42", 1, 0),
    ("gsm_cut_at_cap_no_answer", "gsm8k", None, "Let me think step by step about the trees", "6", 0, 1),
    ("gsm_decimal_not_equal", "gsm8k", "The final answer is 6.5", None, "6", 0, 0),
    ("mmlu_changes_mind_last_wins", "mmlu", "The best answer is B. Hmm, reconsider: option D fits. The best answer is D", None, "D", 1, 0),
    ("mmlu_well_formed_but_wrong", "mmlu", "The best answer is C", None, "D", 0, 0),
    ("mmlu_parenthesis_bold", "mmlu", "**The best answer is (A)**", None, "A", 1, 0),
    ("mmlu_no_format", "mmlu", "I think it is A.", None, "A", 0, 1),
]


def self_test(pick=-1, quiet=False):
    fails = []
    for name, task, content, reasoning, gold, exp_c, exp_n in CONTROLS:
        r = score(task, content, reasoning, gold, pick)
        ok = r["correct"] == exp_c and r["no_answer"] == exp_n
        if not ok:
            fails.append(name)
        if not quiet:
            print(f"{'PASS' if ok else 'FAIL'} {name}: extracted={r['extracted']!r} correct={r['correct']} (want {exp_c}) no_answer={r['no_answer']} (want {exp_n})")
    assert gold_gsm8k("Natalia sold 48/2 = 24 clips in May.\n#### 72") == "72"
    return fails


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        fails = self_test()
        # mutation: the rule under guard is "the LAST match wins"; with the first match instead, the controls that
        # guard it must fail, or the self-test would pass whatever the rule is
        mut = self_test(pick=0, quiet=True)
        guard = {"gsm_wrong_intermediate_then_right", "gsm_reasoning_channel_then_content", "mmlu_changes_mind_last_wins"}
        mutation_caught = guard <= set(mut)
        print(f"controls: {len(CONTROLS) - len(fails)}/{len(CONTROLS)} pass · mutation 'first match wins' fails {sorted(mut)} · caught={mutation_caught}")
        sys.exit(0 if not fails and mutation_caught else 1)
