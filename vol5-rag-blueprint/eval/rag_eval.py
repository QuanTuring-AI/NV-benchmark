#!/usr/bin/env python3
"""Vol.5 · scoring of a question-answering system that retrieves passages and answers with citations.

The scorer knows nothing about the system: it reads a question set, the system's output per question in one neutral
format, and the reference text of the source files, and writes one JSON report. An adapter (a separate program) turns
one system's responses into the neutral format.

Question      {"id", "question", "lang", "answerable": bool, "gold_file_ids": [..],
               "gold_passage_spans": [{"file_id", "start", "end"}, ..], "key_facts": [..]}
              A span is a range in the file's REFERENCE TEXT after normalize() (NFKC, all white space removed), so that
              it does not depend on how any system cuts the file into chunks. span_of() makes one from a quotation.
System output {"id", "retrieved": [{"file_id", "text" | ("start", "end")}, ..]   ranked, best first
               "answer": str, "refused": bool | null, "cited": [index into retrieved, ..] | null,
               "judged_correct": bool | null}                                    an outside judge's verdict, if any
What is reported, each with its count n and a Wilson 95% interval:
  file level     Hit@k: one of the first k retrieved passages comes from a gold file      (found the right document)
  passage level  Hit@k: one of the first k retrieved passages COVERS a gold span whole    (found the answer)
                 The same with "any overlap" is printed as a sensitivity line and is named as such; never a headline.
  conditional    passage-level hit among the questions with a file-level hit
  answer map     for answerable questions, by two gates: is a gold span in the passages the system was given, and did
                 it answer or refuse:   answered_with_passage (split by correctness: correct / wrong / not judged)
                                        refused_with_passage   answered_without_passage   refused_without_passage
  no-answer set  questions the corpus cannot answer, reported apart and never merged: refused / answered
Correctness is a judge's verdict when the output carries one; otherwise the mechanical check "every key fact of the
question occurs in the answer" (after normalize(), case folded), and the report says which of the two was used.

Gates. A report carries figures only if every gate passes; otherwise "figures" is null and the exit code is not 0:
  no-answer set   at least --min-no-answer questions with answerable = false               (default 10)
  train/test      the overlap of the question-id digests with a list of digests of items used for training or
                  prompts must be empty, and a planted digest must be found (control); skipped only with --no-overlap-list
  complete        every question has exactly one output; every gold file id has a reference text
  located         a retrieved passage given as text is placed in its file's reference text in two steps and no third:
                  as given, or after normalize() on both sides. A passage found neither way is "not located" and can
                  hit nothing; the share is reported, and above --max-not-located the report carries no figures
A proportion over fewer than 50 questions is marked "n below 50": not to be quoted on its own.

Paired comparison of two systems on the same questions: compare() gives the exact McNemar test, the difference with a
95% interval, and the smallest imbalance of discordant pairs that the test could have detected.

usage: rag_eval.py score --questions Q.jsonl --outputs O.jsonl --reference-dir DIR --out REPORT.json [--k 1,3,5,10]
                         [--context-k N] [--overlap-list FILE | --no-overlap-list] [--min-no-answer 10]
       rag_eval.py compare --a REPORT_A.json --b REPORT_B.json --out FILE.json [--metric passage_hit@5]
       reference text of file id X: DIR/X.txt (UTF-8). The scorer never writes question, answer or passage text.
"""
import argparse, hashlib, json, math, os, re, sys, unicodedata

Z95 = 1.959963984540054
REFUSAL_PATTERNS = [r"\bi (?:do not|don't|could not|couldn't|cannot|can't) (?:know|find|answer)", r"\bno (?:relevant )?(?:information|answer)\b", r"\bnot (?:mentioned|found|available|provided) in\b",
                    r"\bunable to (?:find|answer)", r"找不到", r"無法回答", r"沒有(?:相關)?(?:資料|資訊|內容)", r"未提及", r"見つかりません", r"回答できません", r"記載(?:が|は)ありません"]


def normalize(text):
    """NFKC, then every white-space character removed. Offsets of spans are offsets into this string."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def wilson(k, n, z=Z95):
    if n == 0:
        return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [max(0.0, (c - h) / d), min(1.0, (c + h) / d)]


def proportion(k, n):
    return {"k": k, "n": n, "rate": (k / n) if n else None, "wilson95": wilson(k, n), "n_below_50": n < 50}


def span_of(reference_text, quotation, file_id):
    """The span of a quotation in a file's reference text; None when it is not there exactly once."""
    ref, q = normalize(reference_text), normalize(quotation)
    if not q or ref.count(q) != 1:
        return None
    s = ref.find(q)
    return {"file_id": file_id, "start": s, "end": s + len(q)}


def locate(passage_text, normalized_reference, raw_reference=None):
    """Where a retrieved passage lies in the reference text: ((start, end), how) or (None, None). Two steps and no
    third: the passage as given occurs in the reference text as stored (how = "exact"); or it occurs after
    normalize() on both sides (how = "normalized"). A passage that is found neither way is not located; nothing
    approximate counts. The offsets are those of the normalized reference text in both cases."""
    p = normalize(passage_text)
    if not p:
        return None, None
    s = normalized_reference.find(p)
    if s < 0:
        return None, None
    how = "exact" if raw_reference is not None and passage_text.strip() and passage_text.strip() in raw_reference else "normalized"
    return (s, s + len(p)), how


def covers(passage, span):
    return passage[0] <= span["start"] and passage[1] >= span["end"]


def overlaps(passage, span):
    return passage[0] < span["end"] and span["start"] < passage[1]


def refused_by_pattern(answer):
    a = (answer or "").strip()
    return (not a) or any(re.search(p, a, re.I) for p in REFUSAL_PATTERNS)


def key_facts_present(answer, key_facts):
    a = normalize(answer or "").casefold()
    return all(normalize(f).casefold() in a for f in key_facts)


def read_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def overlap_gate(questions, overlap_list):
    """Question digests against digests of items used for training or prompts. The control: one digest of the
    question set is planted into a copy of the list and must be reported."""
    mine = {digest(normalize(q["question"]).casefold()) for q in questions}
    theirs = {l.split()[0] for l in open(overlap_list, encoding="utf-8") if l.strip()}
    planted = len(mine & (theirs | {sorted(mine)[0]})) >= 1 if mine else False
    return {"digests_in_the_list": len(theirs), "overlap": len(mine & theirs), "planted_control_found": planted, "pass": planted and not (mine & theirs)}


def score(questions, outputs, reference, ks, context_k, min_no_answer, overlap_list, max_not_located, reference_raw=None):
    out_by_id = {}
    for o in outputs:
        out_by_id.setdefault(o["id"], []).append(o)
    gates = {}
    missing = [q["id"] for q in questions if len(out_by_id.get(q["id"], [])) != 1]
    no_ref = sorted({f for q in questions for f in q["gold_file_ids"] if f not in reference})
    bad_span = [q["id"] for q in questions for s in q["gold_passage_spans"] if s["file_id"] not in q["gold_file_ids"] or not (0 <= s["start"] < s["end"] <= len(reference.get(s["file_id"], "")))]
    bad_form = [q["id"] for q in questions if q["answerable"] != bool(q["gold_file_ids"]) or (q["answerable"] and not q["gold_passage_spans"])]
    gates["complete"] = {"questions_without_exactly_one_output": len(missing), "gold_files_without_reference_text": len(no_ref), "spans_outside_their_file": len(bad_span),
                         "questions_whose_answerable_flag_contradicts_their_gold": len(bad_form), "pass": not (missing or no_ref or bad_span or bad_form)}
    n_no = sum(1 for q in questions if not q["answerable"])
    gates["no_answer_set"] = {"questions": n_no, "required": min_no_answer, "pass": n_no >= min_no_answer}
    gates["train_test_overlap"] = overlap_gate(questions, overlap_list) if overlap_list else {"skipped": "no list was given (--no-overlap-list)", "pass": True}
    rows = []; given = not_located = 0; how_count = {"exact": 0, "normalized": 0}; reference_raw = reference_raw or {}
    if gates["complete"]["pass"]:
        for q in questions:
            o = out_by_id[q["id"]][0]; passages = []
            for r in o.get("retrieved") or []:
                if "start" in r and "end" in r:
                    passages.append((r["file_id"], (r["start"], r["end"])))
                else:
                    given += 1
                    where, how = locate(r.get("text", ""), reference[r["file_id"]], reference_raw.get(r["file_id"])) if r["file_id"] in reference else (None, None)
                    not_located += where is None; passages.append((r["file_id"], where))
                    if how:
                        how_count[how] += 1
            def hit(k, rule):
                top = passages[:k]
                if rule == "file":
                    return any(f in q["gold_file_ids"] for f, _ in top)
                test = covers if rule == "covers" else overlaps
                return any(w is not None and f == s["file_id"] and test(w, s) for f, w in top for s in q["gold_passage_spans"])
            refused = o["refused"] if o.get("refused") is not None else refused_by_pattern(o.get("answer"))
            if o.get("judged_correct") is not None:
                correct, how = bool(o["judged_correct"]), "judge"
            elif q["key_facts"]:
                correct, how = key_facts_present(o.get("answer"), q["key_facts"]), "key facts"
            else:
                correct, how = None, "none"
            ck = context_k or len(passages)
            rows.append({"id": q["id"], "lang": q.get("lang"), "answerable": q["answerable"], "retrieved": len(passages),
                         "file_hit": {str(k): hit(k, "file") for k in ks}, "passage_hit": {str(k): hit(k, "covers") for k in ks}, "passage_overlap": {str(k): hit(k, "overlaps") for k in ks},
                         "passage_in_context": hit(ck, "covers") if q["answerable"] else None, "refused": bool(refused), "refusal_from": "output" if o.get("refused") is not None else "pattern",
                         "correct": None if refused else correct, "correct_from": how, "citations": None if o.get("cited") is None else len(o["cited"])})
    share = (not_located / given) if given else 0.0
    gates["located"] = {"passages_given_as_text": given, "located_exactly_as_given": how_count["exact"], "located_after_normalization": how_count["normalized"], "not_located": not_located,
                        "share_not_located": round(share, 4), "allowed": max_not_located, "rule": "exact, then exact after normalization; nothing approximate", "pass": share <= max_not_located}
    report = {"what": "one system on one question set; file level and passage level side by side, the no-answer set apart",
              "hit_rule": {"passage level": "a retrieved passage covers a gold span whole", "sensitivity line": "any overlap with a gold span; named wherever printed", "file level": "a retrieved passage comes from a gold file"},
              "gates": gates, "all_gates_pass": all(g["pass"] for g in gates.values()), "figures": None, "per_question": None}
    if not report["all_gates_pass"]:
        return report
    ans = [r for r in rows if r["answerable"]]; no = [r for r in rows if not r["answerable"]]

    def block(sel):
        b = {"questions": len(sel), "file_level": {}, "passage_level": {}, "passage_given_file": {}, "sensitivity_any_overlap": {}}
        for k in ks:
            k = str(k); fh = [r for r in sel if r["file_hit"][k]]
            b["file_level"]["hit@" + k] = proportion(len(fh), len(sel)); b["passage_level"]["hit@" + k] = proportion(sum(r["passage_hit"][k] for r in sel), len(sel))
            b["passage_given_file"]["hit@" + k] = proportion(sum(r["passage_hit"][k] for r in fh), len(fh))
            b["sensitivity_any_overlap"]["hit@" + k] = proportion(sum(r["passage_overlap"][k] for r in sel), len(sel))
        return b

    def answer_map(sel):
        n = len(sel); cell = lambda f: sum(1 for r in sel if f(r))
        awp = [r for r in sel if r["passage_in_context"] and not r["refused"]]
        return {"questions": n, "context": "the first %s retrieved passages" % (context_k or "all"),
                "answered_with_passage": proportion(len(awp), n),
                "answered_with_passage_correct": proportion(sum(1 for r in awp if r["correct"] is True), n),
                "answered_with_passage_wrong": proportion(sum(1 for r in awp if r["correct"] is False), n),
                "answered_with_passage_not_judged": proportion(sum(1 for r in awp if r["correct"] is None), n),
                "refused_with_passage": proportion(cell(lambda r: r["passage_in_context"] and r["refused"]), n),
                "answered_without_passage": proportion(cell(lambda r: not r["passage_in_context"] and not r["refused"]), n),
                "refused_without_passage": proportion(cell(lambda r: not r["passage_in_context"] and r["refused"]), n),
                "correctness_from": sorted({r["correct_from"] for r in awp}), "refusal_from": sorted({r["refusal_from"] for r in sel})}

    langs = sorted({r["lang"] for r in ans if r["lang"]})
    report["figures"] = {"answerable": block(ans), "by_language": {l: block([r for r in ans if r["lang"] == l]) for l in langs}, "answer_map": answer_map(ans),
                         "no_answer_set": {"questions": len(no), "refused": proportion(sum(r["refused"] for r in no), len(no)), "answered": proportion(sum(not r["refused"] for r in no), len(no)),
                                           "answered_with_citations": proportion(sum(1 for r in no if not r["refused"] and (r["citations"] or 0) > 0), len(no)),
                                           "note": "reported apart; not part of any figure above"}}
    report["per_question"] = rows
    return report


def binom_two_sided(b, c):
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def smallest_detectable(discordant, alpha=0.05):
    """The smallest |b - c| among `discordant` pairs for which the exact test gives p < alpha; None if none does."""
    for d in range(discordant % 2, discordant + 1, 2):
        b = (discordant + d) // 2
        if binom_two_sided(b, discordant - b) < alpha:
            return d
    return None


def compare(rows_a, rows_b, metric):
    name, k = metric.split("@"); A = {r["id"]: r for r in rows_a if r["answerable"]}; B = {r["id"]: r for r in rows_b if r["answerable"]}
    if set(A) != set(B):
        return {"pass": False, "why": "the two reports are not about the same questions", "figures": None}
    b = sum(1 for i in A if A[i][name][k] and not B[i][name][k]); c = sum(1 for i in A if not A[i][name][k] and B[i][name][k]); n = len(A)
    d = (b - c) / n if n else None; se = math.sqrt(max(b + c - (b - c) ** 2 / n, 0.0)) / n if n else None
    return {"pass": True, "figures": {"metric": metric, "questions": n, "a_only": b, "b_only": c, "both": sum(1 for i in A if A[i][name][k] and B[i][name][k]),
                                      "neither": sum(1 for i in A if not A[i][name][k] and not B[i][name][k]), "difference_a_minus_b": d,
                                      "difference_wald95": None if d is None else [d - Z95 * se, d + Z95 * se], "mcnemar_exact_p": binom_two_sided(b, c),
                                      "smallest_detectable_imbalance_at_this_number_of_discordant_pairs": smallest_detectable(b + c),
                                      "reading": "a p above 0.05 is 'no difference could be measured with these questions', not 'there is no difference'"}}


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score"); s.add_argument("--questions", required=True); s.add_argument("--outputs", required=True); s.add_argument("--reference-dir", required=True); s.add_argument("--out", required=True)
    s.add_argument("--k", default="1,3,5,10"); s.add_argument("--context-k", type=int, default=0); s.add_argument("--min-no-answer", type=int, default=10); s.add_argument("--max-not-located", type=float, default=0.05)
    g = s.add_mutually_exclusive_group(required=True); g.add_argument("--overlap-list"); g.add_argument("--no-overlap-list", action="store_true")
    c = sub.add_parser("compare"); c.add_argument("--a", required=True); c.add_argument("--b", required=True); c.add_argument("--out", required=True); c.add_argument("--metric", default="passage_hit@5")
    a = ap.parse_args()
    if a.cmd == "score":
        questions = read_jsonl(a.questions); ref = {}; raw = {}
        for name in os.listdir(a.reference_dir):
            if name.endswith(".txt"):
                raw[name[:-4]] = open(os.path.join(a.reference_dir, name), encoding="utf-8").read(); ref[name[:-4]] = normalize(raw[name[:-4]])
        rep = score(questions, read_jsonl(a.outputs), ref, [int(x) for x in a.k.split(",")], a.context_k, a.min_no_answer, a.overlap_list, a.max_not_located, reference_raw=raw)
        rep["inputs"] = {"questions": {"file": os.path.basename(a.questions), "sha256": hashlib.sha256(open(a.questions, "rb").read()).hexdigest(), "n": len(questions)},
                         "outputs": {"file": os.path.basename(a.outputs), "sha256": hashlib.sha256(open(a.outputs, "rb").read()).hexdigest()}, "k": a.k, "context_k": a.context_k or "all"}
        json.dump(rep, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
        print(json.dumps({"all_gates_pass": rep["all_gates_pass"], "gates": {k: v["pass"] for k, v in rep["gates"].items()}}))
        return 0 if rep["all_gates_pass"] else 3
    A, B = json.load(open(a.a, encoding="utf-8")), json.load(open(a.b, encoding="utf-8"))
    if not (A.get("all_gates_pass") and B.get("all_gates_pass")):
        res = {"pass": False, "why": "a report whose gates did not pass has no figures to compare", "figures": None}
    elif A["inputs"]["questions"]["sha256"] != B["inputs"]["questions"]["sha256"]:
        res = {"pass": False, "why": "the two reports were scored on different question files", "figures": None}
    else:
        res = compare(A["per_question"], B["per_question"], a.metric)
    json.dump(res, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"pass": res["pass"], "why": res.get("why")}))
    return 0 if res["pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
