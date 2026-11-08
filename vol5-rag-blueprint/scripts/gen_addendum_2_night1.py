#!/usr/bin/env python3
"""Vol.5 · writes supplement 2 to the night-1 pre-registration: control (b) replaced by an exact-against-exact pair,
(b1) with a pass line and joined to the validity gate, (b2) reported without one. With its .sha256 file. Run once,
before the gate's first search; the frozen pre-registration and supplement 1 stay as they are.
usage: gen_addendum_2_night1.py [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE)
RES = os.path.join(V5, "results", "night1"); OUT = os.path.join(RES, "addendum_2_control_b_exact.json"); DRAFT = "--draft" in sys.argv


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


diag = json.load(open(os.path.join(RES, "control_b_diagnosis.json"), encoding="utf-8"))
ov = diag["overlaps"]
rec = {
 "what": "supplement 2 to the night-1 pre-registration: control (b) as frozen could not measure what it was for; it is replaced by two exact-against-exact comparisons on the same 100,000-passage slice",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": "prediction_v5_night1.json", "sha256": sha(os.path.join(RES, "prediction_v5_night1.json"))},
                 {"file": "addendum_1_control_a_program.json", "sha256": sha(os.path.join(RES, "addendum_1_control_a_program.json"))}],
 "authorised_by": "the second supplement of 2026-10-18 to the Vol.5 design ticket",
 "what_happened": "control (b) compared the top 100 of two approximate (bbq_hnsw) indexes and set a line of 0.99 for their mean overlap. It ran on 2026-10-18 and gave 0.8946; the night stopped there as frozen. Each approximate index alone keeps only about nine in ten of its own exact top 100, and two such indexes built in a different order do not lose the same passages, so the line could not be reached even with identical vectors. The design was wrong, not the loader.",
 "seen_before_this_supplement": {"note": "this supplement is written after the diagnosis; these figures were known when its rules were set",
                                 "file": "results/night1/control_b_diagnosis.json", "program": "scripts/control_b_diagnosis.py",
                                 "overlaps_on_100_questions": ov, "ingestor_text": diag["ingestor_text"]},
 "b1": {"what": "Elasticsearch's exact search (script_score cosine) on the index written by es_bulk_load.py with the mapping read from the ingestor's index, against numpy's exact search over the same Vol.4 vectors",
        "questions": "the 200 questions of the validity gate (the first 200 ids of the HotpotQA id table, sorted); the first 100 of them are the questions already seen",
        "rule": "for every one of the 200 questions the two top-100 sets are equal once equal-score swaps at the 100th place are set aside (a score within 5e-5 of that side's 100th score); every swap is listed; pass line 1.0 (all 200). Not passed: no figure of the store is reported (the ticket's second stop)",
        "program": "scripts/exact_equal_check.py", "joins": "the validity gate of C1 (the frozen rule asked for the same thing in words; this makes it a program)"},
 "b2": {"what": "Elasticsearch's exact search on the index written by the Blueprint's ingestor against the same search on the index written by es_bulk_load.py",
        "questions": "the same 200", "rule": "none; reported as it is (overlap at 10 and at 100: mean, lowest, questions under 0.9), with the classes of stored text of the diagnosis",
        "why_no_line": "it measures what the Blueprint's ingestion does to a passage's text (and so to its vector), not this volume's loader"},
 "unchanged": "C1 as frozen (load, memory, disk, overlap against Vol.4's exact search, quality, latency, negative control, branches, expectations)",
 "not_in_this_supplement": "the arms N and O of C2 (answers without passages, and with the two supporting passages) are pre-registered in supplement 3, frozen before the answer model's container",
 "harness_sha256": {f: sha(os.path.join(V5, f)) for f in ("scripts/exact_equal_check.py", "scripts/control_b_diagnosis.py", "scripts/es_ann_vs_exact.py", "scripts/slice_exact.py")},
 "generator": "scripts/gen_addendum_2_night1.py",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen supplement 2 exists")
json.dump(rec, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + rec["written_at"], sha(OUT))
