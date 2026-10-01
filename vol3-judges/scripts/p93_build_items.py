#!/usr/bin/env python3
"""P93 · build the item tables from the pinned test sets. No text is printed and none is written under results/.

Inputs (process bucket, P93_BUCKET/datasets/, fetched at the pinned revisions in p93_common.DATASETS):
  aegis2_test.json     Aegis AI Content Safety Dataset 2.0, test split (1,964 rows)
  xstest_prompts.csv   XSTest (450 prompts: 250 safe, 200 unsafe)
and, from this repository, benchmark/e3_questions.json (the 45 Vol.1 questions, used as an anchor only).

Outputs:
  <bucket>/items_text.jsonl          item_id, prompt, response   (text; stays in the bucket)
  results/p93_judges/items.jsonl     item_id, dataset, tracks, labels, strata, SHA-256 and length of each text (no text)
  results/p93_judges/subsets.json    the fixed subsets, as item ids
  results/p93_judges/items_summary.json   counts, exclusions and the reasons, the pinned inputs

Tracks and labels (fixed here, before any judge is run):
  input track   the judge sees the user's text alone. Gold label: Aegis `prompt_label`, XSTest `label`, and for the Vol.1
                questions unsafe = category adversarial_input, safe = the other two categories.
  output track  the judge sees the user's text and the response. Aegis rows only, where a response exists. Gold label:
                Aegis `response_label`.
  Aegis labels are binary in the test split (safe / unsafe) and are used as given. The 156 prompts whose only listed
  category is "Needs Caution" carry the label safe in this release, so they count as safe; they are flagged
  (needs_caution_only) so that a judge's false alarms on them can be reported as their own stratum.
Exclusions (counted in items_summary.json):
  - Aegis rows whose prompt is redacted in the release (the text is not in the file): out of both tracks;
  - Aegis rows that carry a response label but an empty response: out of the output track.

Subsets (seed 93; order = SHA-256 of "93:" + item id; allocation proportional to the strata, largest remainders first):
  c1_input    200 input-track items from Aegis + XSTest, stratified by data set x gold label
  c1_output   200 output-track items, stratified by gold label x label source
  stability   c1_input plus 100 of c1_output (stratified the same way): 300 items judged a second time
  gr_path     100 of c1_input and 100 of c1_output: the items that are also judged through the Guardrails rail
usage: p93_build_items.py [--check]      --check rebuilds in memory and compares with the files on disk
"""
import collections, csv, hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p93_common import BUCKET, DATASETS, REPO, RESULTS, SEED, sha256_file, sha256_text  # noqa: E402


def order_key(item_id):
    return hashlib.sha256(f"{SEED}:{item_id}".encode()).hexdigest()


def stratified(items, n, key):
    """n items, allocated to the strata in proportion (largest remainders), taken in seeded order inside each stratum."""
    groups = collections.defaultdict(list)
    for it in items:
        groups[key(it)].append(it)
    total = len(items)
    quota = {g: n * len(v) / total for g, v in groups.items()}
    take = {g: int(q) for g, q in quota.items()}
    for g in sorted(groups, key=lambda g: (-(quota[g] - take[g]), str(g)))[: n - sum(take.values())]:
        take[g] += 1
    out = []
    for g in sorted(groups, key=str):
        out += sorted(groups[g], key=lambda it: order_key(it["item_id"]))[: take[g]]
    return sorted(out, key=lambda it: order_key(it["item_id"])), {str(g): take[g] for g in sorted(groups, key=str)}


def build():
    ds = os.path.join(BUCKET, "datasets")
    pins = {}
    for name in ("aegis2", "xstest"):
        p = os.path.join(ds, DATASETS[name]["local"]); got = sha256_file(p)
        if got != DATASETS[name]["sha256"]:
            sys.exit(f"{name}: the file in the bucket is not the pinned one ({got[:16]} != {DATASETS[name]['sha256'][:16]})")
        pins[name] = {k: DATASETS[name][k] for k in ("hf", "revision", "file", "sha256", "license")}
    v1 = os.path.join(REPO, DATASETS["vol1"]["file"])
    if sha256_file(v1) != DATASETS["vol1"]["sha256"]:
        sys.exit("benchmark/e3_questions.json is not the pinned file")
    pins["vol1"] = DATASETS["vol1"]

    items, texts, excl = [], [], collections.Counter()
    aegis = json.load(open(os.path.join(ds, DATASETS["aegis2"]["local"]), encoding="utf-8"))
    for r in aegis:
        prompt = r.get("prompt") or ""; resp = r.get("response") or ""
        if r.get("reconstruction_id_if_redacted") is not None or prompt.strip().upper() == "REDACTED":
            excl["aegis2: prompt redacted in the release"] += 1; continue
        if not prompt.strip():
            excl["aegis2: empty prompt"] += 1; continue
        cats = [c.strip() for c in (r.get("violated_categories") or "").split(",") if c.strip()]
        it = {"item_id": f"aegis2:{r['id']}", "dataset": "aegis2", "tracks": ["input"], "gold_input": r["prompt_label"],
              "prompt_sha256": sha256_text(prompt), "prompt_chars": len(prompt), "needs_caution_only": cats == ["Needs Caution"],
              "n_categories": len(cats)}
        if r.get("response_label") in ("safe", "unsafe"):
            if resp.strip():
                it["tracks"].append("output"); it["gold_output"] = r["response_label"]; it["output_label_source"] = r.get("response_label_source")
                it["response_sha256"] = sha256_text(resp); it["response_chars"] = len(resp)
            else:
                excl["aegis2: response label present, response empty (output track only)"] += 1
        if it["gold_input"] not in ("safe", "unsafe"):
            sys.exit("aegis2: a prompt label that is neither safe nor unsafe")
        items.append(it); texts.append({"item_id": it["item_id"], "prompt": prompt, "response": resp if "output" in it["tracks"] else ""})
    for r in csv.DictReader(open(os.path.join(ds, DATASETS["xstest"]["local"]), encoding="utf-8", newline="")):
        prompt = r["prompt"]
        it = {"item_id": f"xstest:{int(r['id']):03d}", "dataset": "xstest", "tracks": ["input"], "gold_input": r["label"], "xstest_type": r["type"],
              "prompt_sha256": sha256_text(prompt), "prompt_chars": len(prompt)}
        if it["gold_input"] not in ("safe", "unsafe"):
            sys.exit("xstest: a label that is neither safe nor unsafe")
        items.append(it); texts.append({"item_id": it["item_id"], "prompt": prompt, "response": ""})
    for r in json.load(open(v1, encoding="utf-8")):
        it = {"item_id": f"vol1:{r['id']}", "dataset": "vol1", "tracks": ["input"], "gold_input": "unsafe" if r["category"] == "adversarial_input" else "safe",
              "vol1_category": r["category"], "prompt_sha256": sha256_text(r["text"]), "prompt_chars": len(r["text"])}
        items.append(it); texts.append({"item_id": it["item_id"], "prompt": r["text"], "response": ""})
    if len({it["item_id"] for it in items}) != len(items):
        sys.exit("duplicate item ids")

    main_in = [it for it in items if it["dataset"] in ("aegis2", "xstest")]
    outs = [it for it in items if "output" in it["tracks"]]
    c1_in, a_in = stratified(main_in, 200, lambda it: (it["dataset"], it["gold_input"]))
    c1_out, a_out = stratified(outs, 200, lambda it: (it["gold_output"], it["output_label_source"]))
    st_out, a_st = stratified(c1_out, 100, lambda it: (it["gold_output"], it["output_label_source"]))
    gr_in, a_gi = stratified(c1_in, 100, lambda it: (it["dataset"], it["gold_input"]))
    gr_out, a_go = stratified(c1_out, 100, lambda it: (it["gold_output"], it["output_label_source"]))
    ids = lambda xs: [it["item_id"] for it in xs]  # noqa: E731
    subsets = {"seed": SEED, "order": "sha256('93:' + item_id)", "allocation": "proportional to the strata, largest remainders first",
               "c1_input": {"items": ids(c1_in), "strata": a_in}, "c1_output": {"items": ids(c1_out), "strata": a_out},
               "stability": {"input": ids(c1_in), "output": ids(st_out), "output_strata": a_st},
               "gr_path": {"input": ids(gr_in), "output": ids(gr_out), "input_strata": a_gi, "output_strata": a_go}}
    cnt = lambda xs, f: dict(sorted(collections.Counter(f(x) for x in xs).items(), key=lambda kv: str(kv[0])))  # noqa: E731
    summary = {"pinned_inputs": pins, "items": len(items),
               "input_track": {"n": len(items), "by_dataset_and_gold": {f"{k[0]}|{k[1]}": v for k, v in cnt(items, lambda it: (it["dataset"], it["gold_input"])).items()}},
               "output_track": {"n": len(outs), "by_gold_and_source": {f"{k[0]}|{k[1]}": v for k, v in cnt(outs, lambda it: (it["gold_output"], it["output_label_source"])).items()}},
               "aegis2_needs_caution_only_by_gold": cnt([it for it in items if it.get("needs_caution_only")], lambda it: it["gold_input"]),
               "exclusions": dict(excl), "text_lengths_chars": {"prompt_max": max(it["prompt_chars"] for it in items), "response_max": max(it.get("response_chars", 0) for it in items)},
               "subset_sizes": {"c1_input": len(c1_in), "c1_output": len(c1_out), "stability": len(c1_in) + len(st_out), "gr_path": len(gr_in) + len(gr_out)}}
    return items, texts, subsets, summary


def dumps_jsonl(rows):
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    items, texts, subsets, summary = build()
    files = {os.path.join(RESULTS, "items.jsonl"): dumps_jsonl(items), os.path.join(RESULTS, "subsets.json"): json.dumps(subsets, indent=1) + "\n",
             os.path.join(RESULTS, "items_summary.json"): json.dumps(summary, indent=1, ensure_ascii=False) + "\n",
             os.path.join(BUCKET, "items_text.jsonl"): dumps_jsonl(texts)}
    if "--check" in sys.argv:
        bad = [p for p, s in files.items() if not os.path.isfile(p) or open(p, encoding="utf-8", newline="").read() != s]
        print("check:", "identical to the files on disk" if not bad else f"DIFFERENT: {[os.path.basename(p) for p in bad]}")
        return 1 if bad else 0
    os.makedirs(RESULTS, exist_ok=True)
    for p, s in files.items():
        open(p, "w", encoding="utf-8", newline="").write(s)
    print(json.dumps({k: summary[k] for k in ("items", "input_track", "output_track", "exclusions", "subset_sizes", "aegis2_needs_caution_only_by_gold", "text_lengths_chars")}, indent=1, ensure_ascii=False))
    print("subset strata:", json.dumps({k: v.get("strata") or {kk: vv for kk, vv in v.items() if kk.endswith("strata")} for k, v in subsets.items() if isinstance(v, dict)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
