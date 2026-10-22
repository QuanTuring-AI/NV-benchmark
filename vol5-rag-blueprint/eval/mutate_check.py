"""Mutation check of the Vol.5 HotpotQA modules: each single-rule mutation below is applied to a copy of the module, the
module's tests run against the copy, and every mutation must make at least one test fail. A mutation that survives
means a rule no test watches.
usage: python mutate_check.py      (exit 1 if a mutation survives or a mutation does not apply)
"""
import os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MUTATIONS = {
 "hotpot_scoring.py": [
  ('s = s.lower()', 's = s'),
  ('s = re.sub(r"\\b(a|an|the)\\b", " ", s)', 's = re.sub(r"\\b(a|an)\\b", " ", s)'),
  ('if ch not in set(string.punctuation)', 'if ch not in set(",.")'),
  ('return " ".join(s.split())', 'return s'),
  ('if (p in ("yes", "no", "noanswer") or g in ("yes", "no", "noanswer")) and p != g:', 'if False:'),
  ('return 2 * precision * recall / (precision + recall)', 'return precision'),
  ('return p.split()[:1] == [g]', 'return g in p.split()'),
  ('return f" {g} " in f" {p} "', 'return g in p'),
  ('c = sum(contains(r["answer"], r["gold"]) for r in ok)', 'c = sum(em(r["answer"], r["gold"]) for r in ok)'),
  ('"contains_rate": c / n if n else None', '"contains_rate": c / len(ok) if ok else None'),
  ('if set(a) != set(b):', 'if False:'),
  ('only_b = sum(1 for q in a if hit(b[q]) and not hit(a[q]))', 'only_b = sum(1 for q in a if hit(b[q]))'),
  ('return sorted(random.Random(seed).sample(sorted(ids), n))', 'return sorted(random.Random(seed).sample(list(ids), n))'),
 ],
 "hotpotqa_set.py": [
  ('if b["answer"] is not None and b["answer"] != s["answer"]:', 'if False:'),
  ('if b["facts"] and b["facts"] != s["facts"]:', 'if False:'),
  ('if len(hit) != 1:', 'if len(hit) == 0:'),
  ('if set(ids) != qrels[q]:', 'if not set(ids) <= qrels[q]:'),
  ('"in_beir_not_in_source": sorted(set(queries) - set(src))[:20]', '"in_beir_not_in_source": []'),
  ('check["all_matched"] = all(n == 0 for n in check["counts"].values()) and len(rows) == len(queries) == len(src)', 'check["all_matched"] = len(rows) == len(queries)'),
 ],
}
TESTS = {"hotpot_scoring.py": "test_hotpot_scoring.py", "hotpotqa_set.py": "test_hotpotqa_set.py"}

failed = 0
for module, muts in MUTATIONS.items():
    src = open(os.path.join(HERE, module), encoding="utf-8").read()
    for i, (a, b) in enumerate(muts, 1):
        if src.count(a) != 1:
            print(f"DOES NOT APPLY {module} #{i}: {a[:60]}"); failed += 1; continue
        d = tempfile.mkdtemp(); shutil.copytree(HERE, os.path.join(d, "eval"), ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        open(os.path.join(d, "eval", module), "w", encoding="utf-8").write(src.replace(a, b))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", os.path.join(d, "eval", "tests", TESTS[module])], capture_output=True, text=True)
        caught = r.returncode != 0
        print(f"{'caught  ' if caught else 'SURVIVED'} {module} #{i}: {a[:70]}")
        failed += not caught
        shutil.rmtree(d, ignore_errors=True)
print(f"mutations: {sum(len(m) for m in MUTATIONS.values())} · not caught or not applied: {failed}")
sys.exit(1 if failed else 0)
