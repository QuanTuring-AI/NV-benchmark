#!/usr/bin/env python3
"""Vol.1-A revisit, P62 Q1 · post-run join correction (written after the run started, disclosed; the harness, analyser and
post-run programs bound in prediction_p62_quality.json are not changed).

Why: the harness joins lm-eval's samples to the proxy's records by the sha256 of the request messages. The MMLU sample
holds pairs of items whose prompts are byte-identical (the same question appears twice in a subject's test split), so
one messages sha maps to two proxy records. The harness took the last record for both items; where the two answers
differed, one item carried the other's output fields (O-Q4 MMLU: 2 ambiguous, 1 text mismatch).
Rule (the pre-registered join rule, applied correctly): among the records with the item's messages sha, the item gets
the record whose output sha256 equals the sha256 of lm-eval's own response for that item; each record is used once.
Only the proxy-derived fields change (output sha and length, token counts, finish_reason, request sha); correctness and
the extracted answer come from lm-eval and are unchanged.

Steps: (1) rebuild items/<arm>__<task>__<run>.jsonl from raw/ (local) with this rule; (2) rewrite events_public.jsonl
(events.jsonl with the desktop process list reduced to counts, as p62_quality_postrun.py) with each task_run's `join`
recomputed and the harness's own figures kept as `join_as_run`; (3) run the analyser; (4) the recompute check of
p62_quality_postrun.py (published files only -> byte-identical analysis.json; one flipped item -> different), written to
recompute_check.txt; (5) join_corrections.json lists every item whose fields changed.
usage: p62_quality_rejoin.py <run_dir>
"""
import difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile

d = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p62_quality as Q  # noqa: E402  (canon, sha, public_items)

AN = os.path.join(HERE, "p62_quality_analyze.py")
sha = lambda b: hashlib.sha256(b).hexdigest()
fsha = lambda p: sha(open(p, "rb").read())


def rejoin(task_key, samples_by_task, rows):
    """public_items with per-item assignment among records that share a messages sha."""
    by_msg = {}
    for r in rows:
        if r.get("status") == 200 and "messages_sha" in r:
            by_msg.setdefault(r["messages_sha"], []).append(r)
    items, _ = Q.public_items(task_key, samples_by_task, rows)
    resp_sha = {}
    for sub, rs in samples_by_task.items():
        for s in rs:
            resp = s["resps"][0][0] if s.get("resps") else ""
            resp_sha[(sub, s["doc_id"])] = sha(resp.encode("utf-8"))
    used, changes, unjoined, mismatch, shared = set(), [], 0, 0, 0
    for it in items:
        cands = by_msg.get(it["messages_sha"], [])
        if len(cands) > 1:
            shared += 1
        want = resp_sha[(it["task"], it["doc_id"])]
        pick = next((c for c in cands if c.get("output_sha") == want and id(c) not in used), None)
        if pick is None:
            unjoined += 0 if cands else 1; mismatch += 1 if cands else 0
            continue
        used.add(id(pick))
        new = {"request_sha": pick.get("request_sha"), "output_sha": pick.get("output_sha"), "output_chars": pick.get("output_chars"),
               "prompt_tokens": (pick.get("usage") or {}).get("prompt_tokens"), "completion_tokens": (pick.get("usage") or {}).get("completion_tokens"),
               "finish_reason": pick.get("finish_reason")}
        diff = {k: [it.get(k), v] for k, v in new.items() if it.get(k) != v}
        if diff:
            changes.append({"task": it["task"], "doc_id": it["doc_id"], "changed": diff})
        it.update(new)
    return items, {"items": len(items), "unjoined": unjoined, "items_sharing_a_prompt": shared, "resp_vs_proxy_text_mismatch": mismatch}, changes


joins, all_changes = {}, {}
for arm in sorted(os.listdir(os.path.join(d, "raw"))):
    for tr in sorted(os.listdir(os.path.join(d, "raw", arm))):
        task_key, run = tr.split("_", 1)
        rd = os.path.join(d, "raw", arm, tr)
        if not os.path.exists(os.path.join(rd, "samples.json")):
            continue
        samples = json.load(open(os.path.join(rd, "samples.json"), encoding="utf-8"))
        rows = [json.loads(l) for l in open(os.path.join(rd, "proxy.jsonl"), encoding="utf-8")]
        items, j, ch = rejoin(task_key, samples, rows)
        with open(os.path.join(d, "items", f"{arm}__{task_key}__{run}.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n")
        joins[(arm, task_key, run)] = j
        if ch:
            all_changes[f"{arm}|{task_key}|{run}"] = ch
json.dump({"rule": "per item, the proxy record with the item's messages sha whose output sha equals lm-eval's response; each record used once",
           "changed_items": all_changes}, open(os.path.join(d, "join_corrections.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)

ENGINE = re.compile(r"ollama|python|vllm|tritonserver", re.I)
with open(os.path.join(d, "events_public.jsonl"), "w", encoding="utf-8", newline="\n") as out:
    for line in open(os.path.join(d, "events.jsonl"), encoding="utf-8"):
        e = json.loads(line); iso = e.get("isolation")
        if isinstance(iso, dict) and "gpu_compute_apps" in iso:
            raw = iso["gpu_compute_apps"]
            rws = [r for r in raw.splitlines() if r.strip()] if isinstance(raw, str) and raw != "(none listed)" else []
            names = [(r.split(",")[1].strip() if r.count(",") >= 2 else "") for r in rws]
            e = dict(e, isolation=dict(iso, gpu_compute_apps={"listed_processes": len(rws),
                     "inference_engine_names_listed": sum(1 for n in names if ENGINE.search(os.path.basename(n.replace("\\", "/")))),
                     "note": "raw list withheld (desktop processes with personal paths); counts only"}))
        if e.get("kind") == "task_run" and (e["arm"], e["task"], e["run"]) in joins:
            e = dict(e, join_as_run=e.get("join"), join=joins[(e["arm"], e["task"], e["run"])])
        out.write(json.dumps(e, ensure_ascii=False) + "\n")

run = lambda cwd: subprocess.run([sys.executable, AN, cwd], capture_output=True, text=True, encoding="utf-8")
r0 = run(d); a0 = os.path.join(d, "analysis.json")
PUB = ["events_public.jsonl", "g1_scorer_controls.json", "mmlu_sample_ids.json"]


def copy_public(dst):
    for f in PUB:
        shutil.copyfile(os.path.join(d, f), os.path.join(dst, f))
    shutil.copytree(os.path.join(d, "items"), os.path.join(dst, "items"))


tmp = tempfile.mkdtemp(prefix="p62pub_"); copy_public(tmp); r1 = run(tmp); a1 = os.path.join(tmp, "analysis.json")
same = os.path.exists(a1) and fsha(a0) == fsha(a1)
diff = "".join(difflib.unified_diff(open(a0, encoding="utf-8").readlines(), open(a1, encoding="utf-8").readlines() if os.path.exists(a1) else [], "run_dir/analysis.json", "public_copy/analysis.json"))
neg = tempfile.mkdtemp(prefix="p62neg_"); copy_public(neg)
f0 = sorted(os.listdir(os.path.join(neg, "items")))[0]; p = os.path.join(neg, "items", f0)
L = open(p, encoding="utf-8").readlines(); it = json.loads(L[0]); it["correct"] = 1 - it["correct"]; L[0] = json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n"
open(p, "w", encoding="utf-8", newline="\n").writelines(L)
r2 = run(neg); a2 = os.path.join(neg, "analysis.json"); neg_differs = os.path.exists(a2) and fsha(a2) != fsha(a0)
with open(os.path.join(d, "recompute_check.txt"), "w", encoding="utf-8", newline="\n") as o:
    o.write("recompute check · analysis.json from the published files only (after the join correction, p62_quality_rejoin.py)\n")
    o.write(f"command: python vol1a-revisit/scripts/p62_quality_analyze.py <dir>, run on (a) the run directory, (b) a copy holding only {', '.join(PUB)} and items/\n")
    o.write(f"(a) rc {r0.returncode} sha256 {fsha(a0)}\n(b) rc {r1.returncode} sha256 {fsha(a1) if os.path.exists(a1) else None}\n")
    o.write(f"byte-identical: {same}\ndiff output (empty when identical):\n{diff}<end of diff>\n")
    o.write(f"negative control: {f0} first item's `correct` flipped in a third copy -> rc {r2.returncode} sha256 {fsha(a2) if os.path.exists(a2) else None}; differs from (a): {neg_differs}\n")
shutil.rmtree(tmp); shutil.rmtree(neg)
print("joins", {"|".join(k): v for k, v in joins.items()})
print("changed items", {k: len(v) for k, v in all_changes.items()})
print("recompute identical:", same, "· negative control differs:", neg_differs)
sys.exit(0 if same and neg_differs else 1)
