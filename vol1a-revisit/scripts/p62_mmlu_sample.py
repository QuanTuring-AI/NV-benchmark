#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q1 · the MMLU sample: 50 test items from each of the 57 mmlu_llama subjects (2,850), drawn with
random.Random(SEED).sample(range(n_subject), 50) per subject in sorted subject order, ids sorted. Written once, before
the pre-registration, which binds this file by sha256. Uses lm-eval's own task objects, so the ids index the same
test split that lm-eval iterates.
usage: p62_mmlu_sample.py <out.json>"""
import json, os, random, sys

SEED, PER = 20260926, 50
out = sys.argv[1]
if os.path.exists(out):
    sys.exit("exists -- written once")
from lm_eval.tasks import TaskManager, get_task_dict
tm = TaskManager()
td = get_task_dict(["mmlu_llama"], tm)


def leaves(d):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from leaves(v)
        else:
            yield (k if isinstance(k, str) else k.group), v


ids, sizes = {}, {}
for name, task in sorted(leaves(td), key=lambda x: x[0]):
    n = len(list(task.test_docs()))
    sizes[name] = n
    ids[name] = sorted(random.Random(f"{SEED}:{name}").sample(range(n), PER))
assert len(ids) == 57, len(ids)
json.dump({"seed": SEED, "per_subject": PER, "rule": "random.Random(f'{seed}:{subject}').sample(range(n_test_items), 50), sorted",
           "subjects": len(ids), "items": sum(len(v) for v in ids.values()), "test_sizes": sizes, "ids": ids},
          open(out, "w", encoding="utf-8", newline="\n"), indent=1, sort_keys=True)
print("written", out, len(ids), sum(len(v) for v in ids.values()), "min subject size", min(sizes.values()))
