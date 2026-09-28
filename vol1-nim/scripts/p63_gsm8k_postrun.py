#!/usr/bin/env python3
"""Vol.1-A revisit, P63 · post-run (P62's post-run with the P63 analyser and file set): public event file, analysis,
and the recompute check.

1. events_public.jsonl: events.jsonl with each isolation record's `gpu_compute_apps` replaced by counts (the raw list
   names desktop processes with personal paths; P59's post-run did the same).
2. analysis.json: p63_gsm8k_analyze.py on the run directory.
3. Recompute check (positive control of publishability): only the files that are published -- items/*.jsonl,
   events_public.jsonl, g1_scorer_controls.json -- are copied to an empty directory, the analyser
   is run there, and its analysis.json must equal the run directory's byte for byte. A negative control flips one item's
   `correct` in a second copy; its analysis.json must differ. Commands, hashes and the diff output are written to
   recompute_check.txt.
usage: p63_gsm8k_postrun.py <run_dir>
"""
import difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile

d = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__)); AN = os.path.join(HERE, "p63_gsm8k_analyze.py")
ENGINE = re.compile(r"ollama|python|vllm|tritonserver", re.I)
with open(os.path.join(d, "events_public.jsonl"), "w", encoding="utf-8", newline="\n") as out:
    for line in open(os.path.join(d, "events.jsonl"), encoding="utf-8"):
        e = json.loads(line); iso = e.get("isolation")
        if isinstance(iso, dict) and "gpu_compute_apps" in iso:
            raw = iso["gpu_compute_apps"]
            rows = [r for r in raw.splitlines() if r.strip()] if isinstance(raw, str) and raw != "(none listed)" else []
            names = [(r.split(",")[1].strip() if r.count(",") >= 2 else "") for r in rows]
            iso = dict(iso, gpu_compute_apps={"listed_processes": len(rows),
                                              "inference_engine_names_listed": sum(1 for n in names if ENGINE.search(os.path.basename(n.replace("\\", "/")))),
                                              "note": "raw list withheld (desktop processes with personal paths); counts only"})
            e = dict(e, isolation=iso)
        out.write(json.dumps(e, ensure_ascii=False) + "\n")

run = lambda cwd: subprocess.run([sys.executable, AN, cwd], capture_output=True, text=True, encoding="utf-8")
r0 = run(d)
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
PUB = ["events_public.jsonl", "g1_scorer_controls.json"]


def copy_public(dst):
    for f in PUB:
        shutil.copyfile(os.path.join(d, f), os.path.join(dst, f))
    shutil.copytree(os.path.join(d, "items"), os.path.join(dst, "items"))


tmp = tempfile.mkdtemp(prefix="p62pub_"); copy_public(tmp)
r1 = run(tmp)
a0, a1 = os.path.join(d, "analysis.json"), os.path.join(tmp, "analysis.json")
same = os.path.exists(a1) and sha(a0) == sha(a1)
diff = "".join(difflib.unified_diff(open(a0, encoding="utf-8").readlines(), open(a1, encoding="utf-8").readlines() if os.path.exists(a1) else [], "run_dir/analysis.json", "public_copy/analysis.json"))
neg = tempfile.mkdtemp(prefix="p62neg_"); copy_public(neg)
f = sorted(os.listdir(os.path.join(neg, "items")))[0]; p = os.path.join(neg, "items", f)
L = open(p, encoding="utf-8").readlines(); it = json.loads(L[0]); it["correct"] = 1 - it["correct"]; L[0] = json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n"
open(p, "w", encoding="utf-8", newline="\n").writelines(L)
r2 = run(neg); a2 = os.path.join(neg, "analysis.json")
neg_differs = os.path.exists(a2) and sha(a2) != sha(a0)
with open(os.path.join(d, "recompute_check.txt"), "w", encoding="utf-8", newline="\n") as o:
    o.write("recompute check · analysis.json from the published files only\n")
    o.write(f"command: python vol1a-revisit/scripts/p63_gsm8k_analyze.py <dir>, run on (a) the run directory, (b) a copy holding only {', '.join(PUB)} and items/\n")
    o.write(f"(a) rc {r0.returncode} sha256 {sha(a0)}\n(b) rc {r1.returncode} sha256 {sha(a1) if os.path.exists(a1) else None}\n")
    o.write(f"byte-identical: {same}\ndiff output (empty when identical):\n{diff}<end of diff>\n")
    o.write(f"negative control: {f} first item's `correct` flipped in a third copy -> rc {r2.returncode} sha256 {sha(a2) if os.path.exists(a2) else None}; differs from (a): {neg_differs}\n")
shutil.rmtree(tmp); shutil.rmtree(neg)
print("recompute identical:", same, "· negative control differs:", neg_differs)
sys.exit(0 if same and neg_differs else 1)
