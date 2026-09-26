#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q2-Q4 · post-run public event file (as P59's post-run, step 1).

events_public.jsonl = events.jsonl with each isolation record's `gpu_compute_apps` replaced by counts (the raw list names
desktop processes with personal paths and is not published). The run's analyser reads only `isolation.pass` from it, so
the analyser run on a copy holding events_public.jsonl in place of events.jsonl must reproduce analysis.json byte for byte.
Also e2e_per_user.json (as P59's post-run, step 2): AIPerf's end-to-end output throughput per user (output tokens / request
latency, queue and prefill included) per arm, profile, container and level, read from each level's profile_export_aiperf.json;
the analyser's per-user figure is AIPerf's output_token_throughput_per_user = 1 / inter-token latency.
usage: p62_speed_postrun.py <run_dir> <analyser.py> [extra analyser args...]
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

d, an, extra = sys.argv[1], sys.argv[2], sys.argv[3:]
ENGINE = re.compile(r"ollama|python|vllm|tritonserver", re.I)
with open(os.path.join(d, "events_public.jsonl"), "w", encoding="utf-8", newline="\n") as out:
    for line in open(os.path.join(d, "events.jsonl"), encoding="utf-8"):
        e = json.loads(line); iso = e.get("isolation")
        if isinstance(iso, dict) and "gpu_compute_apps" in iso:
            raw = iso["gpu_compute_apps"]
            rows = [r for r in raw.splitlines() if r.strip()] if isinstance(raw, str) and raw != "(none listed)" else []
            names = [(r.split(",")[1].strip() if r.count(",") >= 2 else "") for r in rows]
            e = dict(e, isolation=dict(iso, gpu_compute_apps={"listed_processes": len(rows),
                     "inference_engine_names_listed": sum(1 for n in names if ENGINE.search(os.path.basename(n.replace("\\", "/")))),
                     "note": "raw list withheld (desktop processes with personal paths); counts only"}))
        out.write(json.dumps(e, ensure_ascii=False) + "\n")
tmp = tempfile.mkdtemp(prefix="p62spub_")
for f in os.listdir(d):
    if f.endswith(".jsonl") and f not in ("events.jsonl", "events_public.jsonl"):
        shutil.copyfile(os.path.join(d, f), os.path.join(tmp, f))
shutil.copyfile(os.path.join(d, "events_public.jsonl"), os.path.join(tmp, "events.jsonl"))
subprocess.run([sys.executable, an, tmp, *extra], capture_output=True, text=True)
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
same = sha(os.path.join(tmp, "analysis.json")) == sha(os.path.join(d, "analysis.json"))
shutil.rmtree(tmp)
e2e = {}
for arm_dir in sorted(os.listdir(d)):
    m = re.fullmatch(r"(O-Q4|O-Q4-def|O-FP16|N-BF16|N-FP8)_([CR])_(main|fresh)", arm_dir)
    if not m:
        continue
    for lv in sorted(os.listdir(os.path.join(d, arm_dir))):
        f = os.path.join(d, arm_dir, lv, "profile_export_aiperf.json")
        if re.fullmatch(r"c\d{4}", lv) and os.path.exists(f):
            s_ = json.load(open(f, encoding="utf-8"))
            e2e.setdefault("|".join(m.groups()), {})[int(lv[1:])] = {"e2e_output_token_throughput_per_user_avg": (s_.get("e2e_output_token_throughput") or {}).get("avg"),
                                                                     "output_token_throughput_per_user_avg": (s_.get("output_token_throughput_per_user") or {}).get("avg")}
json.dump({"definition": "AIPerf e2e_output_token_throughput = output tokens / request latency (queue and prefill included), per request, averaged; output_token_throughput_per_user = 1 / inter-token latency",
           "levels": e2e}, open(os.path.join(d, "e2e_per_user.json"), "w", encoding="utf-8", newline=chr(10)), indent=1, ensure_ascii=False)
print("events_public -> analysis identical:", same, "· e2e levels", sum(len(v) for v in e2e.values()))
sys.exit(0 if same else 1)
