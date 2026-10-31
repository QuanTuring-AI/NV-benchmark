#!/usr/bin/env python3
"""Vol.4 · one summary of the fp16 store: per corpus and over the three corpora, read from the files fp16_store.py wrote
(pieces.jsonl, verify.json, search.json). Nothing is measured or recomputed from vectors here; the totals are sums of
the per-piece lines.
usage: fp16_store_summary.py [RESULTS_DIR]      writes RESULTS_DIR/summary.json (default results/fp16_store)
"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(VOL, "results", "fp16_store")
CORPORA = ("miracl-zh", "miracl-ja", "beir-hotpotqa")


def corpus(d):
    rows = [json.loads(l) for l in open(os.path.join(RES, d, "pieces.jsonl"), encoding="utf-8") if l.strip()]
    pieces = [r for r in rows if r.get("kind") == "piece"]; done = [r for r in rows if r.get("kind") == "finished"]
    v = json.load(open(os.path.join(RES, d, "verify.json"), encoding="utf-8")); s = json.load(open(os.path.join(RES, d, "search.json"), encoding="utf-8"))
    c = s["against_the_32_bit_ranking"]
    return {"pieces": len(pieces), "passages": sum(r["rows"] for r in pieces), "bytes_of_the_32_bit_files": sum(r["bytes_of_the_32_bit_file"] for r in pieces),
            "bytes_of_the_16_bit_files": sum(r["bytes_of_the_16_bit_file"] for r in pieces), "conversion_finished": len(done) == 1,
            "pieces_with_every_value_equal_read_back_from_disk": sum(1 for r in pieces if r["values_equal_read_back_from_disk"]),
            "pieces_whose_rebuilt_32_bit_file_has_the_recorded_sha256": sum(1 for r in pieces if r["rebuilt_32_bit_file_has_the_recorded_sha256"]),
            "verified_from_the_16_bit_folder_alone": bool(v.get("verified_from_the_16_bit_folder_alone")), "queries": c["queries"],
            "queries_with_the_same_passages_in_the_same_order": c["queries_with_the_same_passages_in_the_same_order"], "same_metrics": s["same_metrics"], "identical": s["identical"]}


def main():
    per = {d: corpus(d) for d in CORPORA}
    keys = ("pieces", "passages", "bytes_of_the_32_bit_files", "bytes_of_the_16_bit_files", "pieces_with_every_value_equal_read_back_from_disk", "pieces_whose_rebuilt_32_bit_file_has_the_recorded_sha256", "queries", "queries_with_the_same_passages_in_the_same_order")
    total = {k: sum(p[k] for p in per.values()) for k in keys}
    total["every_corpus_identical"] = all(p["identical"] for p in per.values())
    out = {"what": "the fp16 store of the three whole corpora, summed from the per-piece lists", "corpora": per, "total": total,
           "program": {"file": "fp16_store_summary.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}}
    json.dump(out, open(os.path.join(RES, "summary.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(total))


if __name__ == "__main__":
    main()
