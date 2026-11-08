"""Vol.5 · scoring of answers to HotpotQA questions, and the fixed samples of the volume. Importable; nothing here calls
a model or a server.

Answer scores (decided before any answer exists):
  contains   (main)  the normalized gold answer occurs in the normalized answer as a whole run of tokens. For a gold
                     answer "yes" or "no", the answer counts only if its first normalized token is that word (a long
                     sentence holds "no" for many reasons).
  f1         (second) the official HotpotQA token F1 (hotpot_evaluate_v1.py), with its rule that a yes/no/noanswer on
                     either side scores 0 unless both are equal.
  em         (listed only) the official exact match. The Blueprint answers in sentences, so EM is near zero by design.
normalize_answer is the official one: lower case, punctuation removed, the articles a/an/the removed, white space
collapsed.

Refusal: rag_eval.refused_by_pattern (the volume's three-language list); the C3 cell checks it against 50 answers
labelled by hand before its figure is used.

Statistics: Wilson 95% intervals and the exact two-sided McNemar test, both from rag_eval (imported, not copied).
Samples: c3_sample(ids) draws the 200 questions of the cell with a fixed seed from the sorted id list.
"""
import collections, os, random, re, string, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_eval import binom_two_sided, refused_by_pattern, wilson  # noqa: E402

C3_SEED, C3_N = 20261018, 200


def normalize_answer(s):
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def em(prediction, gold):
    return normalize_answer(prediction) == normalize_answer(gold)


def f1(prediction, gold):
    p, g = normalize_answer(prediction), normalize_answer(gold)
    if (p in ("yes", "no", "noanswer") or g in ("yes", "no", "noanswer")) and p != g:
        return 0.0
    pt, gt = p.split(), g.split()
    same = sum((collections.Counter(pt) & collections.Counter(gt)).values())
    if same == 0:
        return 0.0
    precision, recall = same / len(pt), same / len(gt)
    return 2 * precision * recall / (precision + recall)


def contains(prediction, gold):
    p, g = normalize_answer(prediction), normalize_answer(gold)
    if not g:
        return False
    if g in ("yes", "no"):
        return p.split()[:1] == [g]
    return f" {g} " in f" {p} "


def score_answers(rows):
    """rows: dicts with query_id, answer (text or None when the call failed), gold. -> summary with counts and intervals."""
    n = len(rows); ok = [r for r in rows if r.get("answer") is not None]
    c = sum(contains(r["answer"], r["gold"]) for r in ok)
    refused = sum(refused_by_pattern(r["answer"]) for r in ok)
    lo, hi = wilson(c, n)
    return {"questions": n, "answered_calls": len(ok), "failed_calls": n - len(ok),
            "contains": c, "contains_rate": c / n if n else None, "contains_wilson95": [lo, hi],
            "f1_mean": sum(f1(r["answer"], r["gold"]) for r in ok) / n if n else None,
            "em": sum(em(r["answer"], r["gold"]) for r in ok), "refused_by_pattern": refused}


def paired(rows_a, rows_b):
    """Same questions, two arms: discordant pairs on 'contains' and the exact McNemar p."""
    a = {r["query_id"]: r for r in rows_a}; b = {r["query_id"]: r for r in rows_b}
    if set(a) != set(b):
        raise ValueError("the two arms do not hold the same questions")
    hit = lambda r: r.get("answer") is not None and contains(r["answer"], r["gold"])
    only_a = sum(1 for q in a if hit(a[q]) and not hit(b[q])); only_b = sum(1 for q in a if hit(b[q]) and not hit(a[q]))
    return {"questions": len(a), "only_a": only_a, "only_b": only_b, "mcnemar_exact_p": binom_two_sided(only_a, only_b)}


def c3_sample(ids, seed=C3_SEED, n=C3_N):
    return sorted(random.Random(seed).sample(sorted(ids), n))
