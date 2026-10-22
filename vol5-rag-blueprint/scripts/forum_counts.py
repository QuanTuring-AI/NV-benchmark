#!/usr/bin/env python3
"""Vol.5 · counts the forum post states that no other result file holds, written to results/forum_counts.json so the
README's claim table can read them:
  settings_rows   the setting rows of BLUEPRINT_SETTINGS.md (lines that start with "| `")
  ingestor_log    results/night1/control_b_ingest.jsonl: uploads, files, the sum of the per-upload seconds, and the time
                  that rate gives for the whole HotpotQA corpus (an estimate: the 5.2M passages were never ingested)
  vdb_top_k_cap   the upper bound of the request field vdb_top_k in the Blueprint's rag-server, read from a clone
  upstream_prs    the two NeMo-Retriever pull requests behind the ingestor's dropped last token (gh pr view)

usage: forum_counts.py --blueprint DIR [--no-gh]
"""
import argparse, json, os, re, subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOTPOTQA_PASSAGES = 5233329


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--blueprint", required=True); ap.add_argument("--no-gh", action="store_true")
    a = ap.parse_args()
    rows = sum(1 for l in open(os.path.join(HERE, "BLUEPRINT_SETTINGS.md"), encoding="utf-8") if l.startswith("| `"))
    log = [json.loads(l) for l in open(os.path.join(HERE, "results", "night1", "control_b_ingest.jsonl"), encoding="utf-8")]
    up = [e for e in log if "batch" in e]
    secs = sum(e["seconds"] for e in up); files = sum(e["files"] for e in up)
    rel = "src/nvidia_rag/rag_server/server.py"
    src = open(os.path.join(a.blueprint, rel), encoding="utf-8").read().splitlines()
    caps = []
    for i, l in enumerate(src):
        if re.match(r"\s*vdb_top_k: int = Field\(", l):
            for j in range(i, min(i + 12, len(src))):
                m = re.search(r"\ble=(\d+)", src[j])
                if m:
                    caps.append({"field_line": i + 1, "le_line": j + 1, "le": int(m.group(1)), "text": src[j].strip()}); break
    head = subprocess.run(["git", "-C", a.blueprint, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    out = {"what": "counts the Vol.5 forum post states that no other result file holds (scripts/forum_counts.py)",
           "settings_rows": rows,
           "ingestor_log": {"uploads": len(up), "files": files, "all_finished": all(e["state"] == "FINISHED" for e in up),
                            "seconds_total": round(secs, 1), "seconds_per_100000_passages": round(secs / files * 100000, 1),
                            "estimate_hours_for_the_whole_hotpotqa_corpus": round(secs / files * HOTPOTQA_PASSAGES / 3600, 1),
                            "hotpotqa_passages": HOTPOTQA_PASSAGES},
           "vdb_top_k_cap": {"repository": "NVIDIA-AI-Blueprints/rag", "commit": head, "file": rel, "fields": caps,
                             "le": sorted({c["le"] for c in caps})}}
    if not a.no_gh:
        prs = []
        for n in (497, 485):
            r = subprocess.run(["gh", "pr", "view", str(n), "-R", "NVIDIA/NeMo-Retriever", "--json", "number,title,mergedAt,url"], capture_output=True, text=True)
            prs.append(json.loads(r.stdout) if r.returncode == 0 else {"number": n, "error": r.stderr.strip()[:200]})
        out["upstream_prs"] = prs
    json.dump(out, open(os.path.join(HERE, "results", "forum_counts.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(out)[:900])


if __name__ == "__main__":
    main()
