#!/usr/bin/env python3
"""Vol.1-A revisit, P59 · post-run files (written after the run, disclosed in the README; the frozen analysis is unchanged).

1. events_public.jsonl: events.jsonl with the isolation record's `gpu_compute_apps` field replaced by counts. On Windows,
   `nvidia-smi --query-compute-apps` lists every desktop process that holds a GPU context (browsers, chat clients, the
   shell), with full paths; the list is personal, carries no measurement, and is not published. Kept: how many processes
   were listed and how many reported a memory figure (none did: all "[N/A]"), and whether any listed name was an inference
   engine (ollama, python, vllm, tritonserver). The frozen analyser reads only `isolation.pass`, so its output from
   events_public.jsonl must equal analysis.json byte for byte (checked below).
2. e2e_per_user.json: AIPerf's end-to-end output throughput per user (output tokens / request latency, queue and prefill
   included), per arm, profile, container and level, read from each level's profile_export_aiperf.json. The pre-registered
   per-user metric is AIPerf's output_token_throughput_per_user = 1 / inter-token latency: decode speed once a request is
   generating, which leaves out time spent waiting in a queue. Both are reported; the crossings of the frozen analysis
   use the pre-registered one.
3. truncation_evidence.json: AIPerf did not request usage from the servers (no --use-server-token-count), so the level
   check "server prompt tokens >= 98% of the client count" had no server count to read on any arm ("truncation
   unverified" on every level). The harness's own calibration requests did carry usage: per arm and profile, the ratio
   server / client prompt tokens over its 20 measured requests.
usage: p59_postrun.py <run_dir>
"""
import json, os, re, subprocess, sys

d = sys.argv[1]
ENGINE = re.compile(r"ollama|python|vllm|tritonserver", re.I)
out = open(os.path.join(d, "events_public.jsonl"), "w", encoding="utf-8", newline="\n")
events = []
for line in open(os.path.join(d, "events.jsonl"), encoding="utf-8"):
    e = json.loads(line); events.append(e)
    iso = e.get("isolation")
    if isinstance(iso, dict) and "gpu_compute_apps" in iso:
        raw = iso["gpu_compute_apps"]
        rows = [r for r in raw.splitlines() if r.strip()] if isinstance(raw, str) and raw != "(none listed)" else []
        names = [(r.split(",")[1].strip() if r.count(",") >= 2 else "") for r in rows]
        mems = [(r.split(",")[-1].strip() if r.count(",") >= 2 else "") for r in rows]
        iso = dict(iso)
        iso["gpu_compute_apps"] = {"listed_processes": len(rows), "with_memory_figure": sum(1 for m in mems if m and m != "[N/A]"),
                                   "inference_engine_names_listed": sum(1 for n in names if ENGINE.search(os.path.basename(n.replace("\\", "/")))),
                                   "note": "raw list withheld (desktop processes with personal paths); counts only"}
        e = dict(e, isolation=iso)
    out.write(json.dumps(e, ensure_ascii=False) + "\n")
out.close()

e2e = {}
for arm_dir in sorted(os.listdir(d)):
    m = re.fullmatch(r"(O-Q4|O-Q4-def|O-FP16|N-BF16|N-FP8)_([CR])_(main|fresh)", arm_dir)
    if not m:
        continue
    for lv in sorted(os.listdir(os.path.join(d, arm_dir))):
        f = os.path.join(d, arm_dir, lv, "profile_export_aiperf.json")
        if not re.fullmatch(r"c\d{4}", lv) or not os.path.exists(f):
            continue
        s = json.load(open(f, encoding="utf-8"))
        e2e.setdefault("|".join(m.groups()), {})[int(lv[1:])] = {
            "e2e_output_token_throughput_per_user_avg": (s.get("e2e_output_token_throughput") or {}).get("avg"),
            "output_token_throughput_per_user_avg": (s.get("output_token_throughput_per_user") or {}).get("avg"),
            "time_to_first_token_p50": (s.get("time_to_first_token") or {}).get("p50")}
json.dump({"definition": "AIPerf e2e_output_token_throughput = output tokens / request latency (queue and prefill included), per request, averaged; output_token_throughput_per_user = 1 / inter-token latency (the pre-registered per-user metric)",
           "levels": e2e}, open(os.path.join(d, "e2e_per_user.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)

trunc = {}
for e in events:
    if e.get("kind") == "profile_start" and e.get("calibration"):
        rows = [r for r in e["calibration"]["rows"] if not r.get("warmup")]
        rat = [r["server_prompt_tokens"] / r["client_prompt_tokens"] for r in rows if r.get("server_prompt_tokens") and r.get("client_prompt_tokens")]
        trunc[f"{e['arm']}|{e['profile']}"] = {"measured_requests": len(rows), "with_server_count": len(rat),
                                               "client_prompt_tokens_p50": e["calibration"].get("client_prompt_tokens_p50"),
                                               "server_over_client_min": round(min(rat), 4) if rat else None, "server_over_client_max": round(max(rat), 4) if rat else None,
                                               "below_0.98": sum(1 for x in rat if x < 0.98)}
json.dump({"source": "the harness's own calibration requests (stream with usage), 20 per arm and profile; the chat template makes the server count exceed the client count",
           "per_arm_profile": trunc}, open(os.path.join(d, "truncation_evidence.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)

# the frozen analyser on events_public.jsonl must reproduce analysis.json byte for byte
import shutil, tempfile, hashlib
tmp = tempfile.mkdtemp(prefix="p59pub_")
shutil.copyfile(os.path.join(d, "levels.jsonl"), os.path.join(tmp, "levels.jsonl"))
shutil.copyfile(os.path.join(d, "events_public.jsonl"), os.path.join(tmp, "events.jsonl"))
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run([sys.executable, os.path.join(here, "p59_analyze.py"), tmp], capture_output=True, text=True)
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
same = sha(os.path.join(tmp, "analysis.json")) == sha(os.path.join(d, "analysis.json"))
shutil.rmtree(tmp)
print("events_public -> analysis identical:", same, "· e2e levels", sum(len(v) for v in e2e.values()), "· truncation rows", len(trunc))
sys.exit(0 if same else 1)
