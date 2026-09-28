#!/usr/bin/env python3
"""Vol.2 (directory vol1b/), P67 · post-run: public event file, observed workers, analysis, recompute check.

1. events_public.jsonl: logs/events.jsonl with each isolation record's `gpu_compute_apps` (desktop processes with personal
   paths) replaced by counts.
2. stack.json gains one key, `workers_observed`, taken from events_public.jsonl: per server start, the pid of every worker
   that answered, the config sha256 each of them read at import, and uvicorn's start-up restarts. Every other key must be
   byte for byte the `stack` embedded in prediction_p67.json (checked here; exit 1 if not).
3. analysis.json: p67_analyze.py on the run directory.
4. Recompute check: only the published inputs (levels.jsonl, events_public.jsonl, part_d_verdicts.jsonl, stack.json,
   prediction_p67.json; P66's published files are read by the analyzer from ../p66_rails_under_load) are copied to an empty
   directory and analysed there; analysis.json must be byte-identical. Negative control: one Part D verdict flipped in a
   third copy must change it. Written to recompute_check.txt.
usage: p67_postrun.py <run_dir>
"""
import difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile

d = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__)); AN = os.path.join(HERE, "p67_analyze.py")
ENGINE = re.compile(r"ollama|python|vllm|tritonserver", re.I)
events = []
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
        events.append(e)
        out.write(json.dumps(e, ensure_ascii=False) + "\n")
sp = os.path.join(d, "stack.json"); stack = json.load(open(sp, encoding="utf-8"))
pred = json.load(open(os.path.join(d, "prediction_p67.json"), encoding="utf-8"))
frozen = pred.get("stack") or {}
base = {k: v for k, v in stack.items() if k != "workers_observed"}
if base != frozen:
    sys.exit("stack.json differs from the stack frozen in prediction_p67.json (keys other than workers_observed)")
obs = {}
for e in events:
    if e.get("kind") != "server_start" or e.get("arm") == "N":
        continue
    s = e.get("server") or {}; ans = s.get("workers_answering") or []
    imp = s.get("workers_imported") or {}
    obs[e["label"]] = {"workers": e.get("workers"), "keep_alive_s": e.get("keep_alive_s"), "config": e.get("config"), "config_sha256_expected": e.get("config_sha256"),
                       "workers_answering": {pid: (imp.get(pid) or {}).get("config_sha256") for pid in ans},
                       "g2_pass": (e.get("g2") or {}).get("pass"), "uvicorn_listen_winerror_10022_restarts": s.get("listen_winerror_10022"),
                       "seconds_to_all_workers": s.get("seconds_to_all_workers")}
stack = dict(base, workers_observed={"source": "events_public.jsonl server_start records (P67_WORKER lines printed by each worker at import; pids from the x-p67-worker-pid response header)",
                                     "by_server_start": obs})
json.dump(stack, open(sp, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
run = lambda cwd: subprocess.run([sys.executable, AN, cwd], capture_output=True, text=True, encoding="utf-8")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
PUB = ["levels.jsonl", "events_public.jsonl", "part_d_verdicts.jsonl", "stack.json", "prediction_p67.json"]
r0 = run(d); a0 = os.path.join(d, "analysis.json")
tmp = tempfile.mkdtemp(prefix="p67pub_")
for f in PUB:
    shutil.copyfile(os.path.join(d, f), os.path.join(tmp, f))
r1 = run(tmp); a1 = os.path.join(tmp, "analysis.json")
same = sha(a0) == sha(a1)
diff = "".join(difflib.unified_diff(open(a0, encoding="utf-8").readlines(), open(a1, encoding="utf-8").readlines() if os.path.exists(a1) else [], "run_dir/analysis.json", "public_copy/analysis.json"))
neg = tempfile.mkdtemp(prefix="p67neg_")
for f in PUB:
    shutil.copyfile(os.path.join(d, f), os.path.join(neg, f))
p = os.path.join(neg, "part_d_verdicts.jsonl"); L = open(p, encoding="utf-8").readlines()
if L:
    x = json.loads(L[0]); x["blocked"] = not x["blocked"]; L[0] = json.dumps(x, ensure_ascii=False) + "\n"
open(p, "w", encoding="utf-8", newline="\n").writelines(L)
r2 = run(neg); a2 = os.path.join(neg, "analysis.json"); neg_differs = sha(a2) is not None and sha(a2) != sha(a0)
with open(os.path.join(d, "recompute_check.txt"), "w", encoding="utf-8", newline="\n") as o:
    o.write("recompute check · analysis.json from the published files only\n")
    o.write(f"command: python vol1b/scripts/p67_analyze.py <dir>, run on (a) the run directory, (b) a copy holding only {', '.join(PUB)} "
            f"(P66's analysis.json and part_d_verdicts.jsonl are read from vol1b/results/p66_rails_under_load in both)\n")
    o.write(f"(a) rc {r0.returncode} sha256 {sha(a0)}\n(b) rc {r1.returncode} sha256 {sha(a1)}\nbyte-identical: {same}\n")
    o.write(f"diff output (empty when identical):\n{diff}<end of diff>\n")
    o.write(f"negative control: the first Part D verdict's `blocked` flipped in a third copy -> rc {r2.returncode} sha256 {sha(a2)}; differs from (a): {neg_differs}\n")
shutil.rmtree(tmp); shutil.rmtree(neg)
print("recompute identical:", same, "· negative control differs:", neg_differs)
sys.exit(0 if same and neg_differs else 1)
