#!/usr/bin/env python3
"""Vol.2, P69 · post-run: public event file, analysis, recompute check.
1. events_public.jsonl: logs/events.jsonl with each isolation record's `gpu_compute_apps` (desktop processes with personal
   paths) replaced by counts.
2. analysis.json: p69_analyze.py on the run directory.
3. Recompute check: levels.jsonl, events_public.jsonl and contamination_marks.jsonl only are copied to an empty directory
   and analysed there (P66's and P67's published files are read from their own results directories in both);
   analysis.json must be byte-identical. Negative control: the G8 positive control's record flipped in a third copy must
   change it. Written to recompute_check.txt.
usage: p69_postrun.py <run_dir>
"""
import difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile

d = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__)); AN = os.path.join(HERE, "p69_analyze.py")
ENGINE = re.compile(r"ollama|python|vllm|tritonserver", re.I)
with open(os.path.join(d, "events_public.jsonl"), "w", encoding="utf-8", newline="\n") as out:
    for line in open(os.path.join(d, "logs", "events.jsonl"), encoding="utf-8"):
        e = json.loads(line); iso = e.get("isolation")
        if isinstance(iso, dict) and "gpu_compute_apps" in iso:
            raw = iso["gpu_compute_apps"]
            rows = [r for r in raw.splitlines() if r.strip()] if isinstance(raw, str) and raw != "(none listed)" else []
            names = [(r.split(",")[1].strip() if r.count(",") >= 2 else "") for r in rows]
            e = dict(e, isolation=dict(iso, gpu_compute_apps={"listed_processes": len(rows),
                     "inference_engine_names_listed": sum(1 for n in names if ENGINE.search(os.path.basename(n.replace("\\", "/")))),
                     "note": "raw list withheld (desktop processes with personal paths); counts only"}))
        out.write(json.dumps(e, ensure_ascii=False) + "\n")
run = lambda cwd: subprocess.run([sys.executable, AN, cwd], capture_output=True, text=True, encoding="utf-8")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
PUB = ["levels.jsonl", "events_public.jsonl", "contamination_marks.jsonl"]
r0 = run(d); a0 = os.path.join(d, "analysis.json")
tmp = tempfile.mkdtemp(prefix="p69pub_")
for f in PUB:
    shutil.copyfile(os.path.join(d, f), os.path.join(tmp, f))
r1 = run(tmp); a1 = os.path.join(tmp, "analysis.json"); same = sha(a0) == sha(a1)
diff = "".join(difflib.unified_diff(open(a0, encoding="utf-8").readlines(), open(a1, encoding="utf-8").readlines() if os.path.exists(a1) else [], "run_dir/analysis.json", "public_copy/analysis.json"))
neg = tempfile.mkdtemp(prefix="p69neg_")
for f in PUB:
    shutil.copyfile(os.path.join(d, f), os.path.join(neg, f))
p = os.path.join(neg, "events_public.jsonl"); L = open(p, encoding="utf-8").readlines()
for i, l in enumerate(L):
    e = json.loads(l)
    if e.get("kind") == "g8_positive_control":
        e["control_fired"] = not e.get("control_fired"); L[i] = json.dumps(e, ensure_ascii=False) + "\n"; break
open(p, "w", encoding="utf-8", newline="\n").writelines(L)
r2 = run(neg); a2 = os.path.join(neg, "analysis.json"); neg_differs = sha(a2) is not None and sha(a2) != sha(a0)
with open(os.path.join(d, "recompute_check.txt"), "w", encoding="utf-8", newline="\n") as o:
    o.write("recompute check · analysis.json from the published files only\n")
    o.write(f"command: python <this volume>/scripts/p69_analyze.py <dir>, run on (a) the run directory, (b) a copy holding only {', '.join(PUB)} (P66's and P67's published files read from their own results directories in both)\n")
    o.write(f"(a) rc {r0.returncode} sha256 {sha(a0)}\n(b) rc {r1.returncode} sha256 {sha(a1)}\nbyte-identical: {same}\n")
    o.write(f"diff output (empty when identical):\n{diff}<end of diff>\n")
    o.write(f"negative control: the G8 positive control's control_fired flipped in a third copy -> rc {r2.returncode} sha256 {sha(a2)}; differs from (a): {neg_differs}\n")
shutil.rmtree(tmp); shutil.rmtree(neg)
print("recompute identical:", same, "· negative control differs:", neg_differs)
sys.exit(0 if same and neg_differs else 1)
