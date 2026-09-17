#!/usr/bin/env python3
"""P20 · draw the 50-question sample from the Vol.1 E2 question set, and three harness-test questions outside it.

Strata: the four English categories (20 questions each) and, inside `multilingual`, each language
(zh 10 · ja 6 · en 4). Inside a stratum the questions are sorted by text length (ties by id) and every second one is
taken, starting at position 0 or 1 chosen by the seeded generator. That takes exactly half of every stratum and keeps
each stratum's length distribution: 10 + 10 + 10 + 10 + (5 + 3 + 2) = 50.
The harness-test questions are three questions NOT in the sample, drawn by the same generator, so testing the harness
never shows a sampled question's result before the pre-registration is frozen.

usage: p20_sample.py <out sample.json>
"""
import hashlib, json, os, random, re, sys

SEED = 20260917
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
QFILE = os.path.join(REPO, "benchmark", "questions.json")


def lang(text):
    if re.search("[぀-ヿ]", text):
        return "ja"
    if re.search("[一-鿿]", text):
        return "zh"
    return "en"


def draw():
    qs = json.load(open(QFILE, encoding="utf-8"))
    rng = random.Random(SEED)
    strata = {}
    for q in qs:
        key = (q["category"], lang(q["text"]) if q["category"] == "multilingual" else "en")
        strata.setdefault(key, []).append(q)
    sample, log = [], []
    for key in sorted(strata):
        members = sorted(strata[key], key=lambda q: (len(q["text"]), str(q["id"])))
        start = rng.randrange(2)
        picked = members[start::2]
        sample += picked
        log.append({"stratum": list(key), "size": len(members), "start": start, "taken": len(picked),
                    "ids": [q["id"] for q in picked]})
    rest = sorted((q for q in qs if q not in sample), key=lambda q: str(q["id"]))
    test = rng.sample(rest, 3)
    order = sample[:]
    rng.shuffle(order)
    return qs, sample, order, test, log


def main():
    qs, sample, order, test, log = draw()
    assert len(sample) == 50 and len({q["id"] for q in sample}) == 50
    assert not {q["id"] for q in test} & {q["id"] for q in sample}
    out = {"source": "benchmark/questions.json",
           "source_sha256": hashlib.sha256(open(QFILE, "rb").read()).hexdigest(),
           "seed": SEED,
           "method": "strata = the four English categories and, inside multilingual, each language; inside a stratum sort by "
                     "text length (ties by id) and take every second question from a seeded start (0 or 1); then shuffle "
                     "the 50 with the same generator to fix the run order; then draw 3 harness-test questions from the "
                     "remaining 50",
           "strata": log,
           "run_order": [{"id": q["id"], "category": q["category"], "lang": lang(q["text"]), "chars": len(q["text"])} for q in order],
           "harness_test_questions": [{"id": q["id"], "category": q["category"]} for q in test]}
    json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"sample 50 · test {[q['id'] for q in test]} · strata {[(s['stratum'], s['taken']) for s in log]}")


if __name__ == "__main__":
    main()
