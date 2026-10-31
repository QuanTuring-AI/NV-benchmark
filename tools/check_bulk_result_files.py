#!/usr/bin/env python3
"""A mechanical gate for result files too long to read: per-query score files and per-call timing files.

Such a file has a short head (data set, program, digests, aggregates) and one or more long containers: one entry
per query of a public data set, or one number per call. Nobody reads a hundred thousand lines; this program asserts
what a reader would have checked.

A container with more than --bulk entries is a bulk container. The rule for it:
  a bulk object   every key is an id of a public data set (it matches one of the --id-pattern expressions in full);
                  every value is a number, or an object whose keys are all in the --value-key list and whose
                  values are all numbers
  a bulk list     every item is a number
Any string inside a bulk container, any key that is not an id, any value key outside the list: a violation.
The head (everything outside bulk containers) may hold strings; it is short enough to read, and the program reports
how many strings it has and fails above --max-head-strings or --max-head-string-length.

Control, run for every file on every call: a copy of the parsed file gets a string planted in its first bulk
container (as a key or item, and as a value in place of a number); the same check must report both. If a planted
string is not reported, the result for that file is void and the exit code is 2.

A file without a bulk container is not this gate's kind: it is short enough to read, and the gate says nothing about
it. Such a file is skipped; its name and the reason are printed and it is counted, never passed in silence. A skipped
file can still look like a long file that slipped through: its name is one of the long files' names (--long-name,
default score*.json and latency*.json), it has a key the long files use for their containers (--long-key, default
per_query and call_ms_all), or it holds more than --bulk keys of a distinctive id form spread over small containers
(--piece-id-pattern, default 24 hex digits and digits#digits). The line of such a file names the signs; with
--require-bulk it is a violation. Use --require-bulk whenever the gate decides whether files may be committed.

Defaults: ids of 24 hex digits (HotpotQA), digits#digits (MIRACL queries), digits (BEIR SciFact); value keys
ndcg_cut_10 and recall_100.

usage: check_bulk_result_files.py [--bulk 60] [--id-pattern REGEX ...] [--value-key NAME ...] [--require-bulk]
                                  [--long-name GLOB ...] [--long-key NAME ...] [--piece-id-pattern REGEX ...] FILE [FILE ...]
       check_bulk_result_files.py self_test
exit codes: 0 no checked file has a violation · 1 a violation · 2 a planted control was not reported
"""
import argparse, copy, fnmatch, json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ID_PATTERNS = [r"[0-9a-f]{24}", r"\d+#\d+", r"\d+"]
VALUE_KEYS = ["ndcg_cut_10", "recall_100"]
LONG_NAMES = ["score*.json", "latency*.json"]
LONG_KEYS = ["per_query", "call_ms_all"]
PIECE_ID_PATTERNS = [r"[0-9a-f]{24}", r"\d+#\d+"]


def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check(doc, bulk, id_patterns, value_keys, max_head_strings=120, max_head_string_length=600):
    """-> dict: bulk containers found, their entries, the violations (path and kind, never a value), head strings."""
    ids = [re.compile(p) for p in id_patterns]; vk = set(value_keys)
    out = {"bulk_containers": [], "violations": [], "head_strings": 0, "head_string_characters": 0, "longest_head_string": 0}

    def bad(path, kind):
        if len(out["violations"]) < 20:
            out["violations"].append({"at": path, "kind": kind})
        out["violation_count"] = out.get("violation_count", 0) + 1

    def bulk_dict(o, path):
        matched = {p.pattern: 0 for p in ids}
        for k, v in o.items():
            hit = next((p for p in ids if p.fullmatch(k)), None)
            if hit is None:
                bad(path, "a key that is not an id of the listed forms")
            else:
                matched[hit.pattern] += 1
            if is_number(v):
                continue
            if isinstance(v, dict) and v and all(x in vk for x in v) and all(is_number(y) for y in v.values()):
                continue
            bad(path, "a value that is not a number or an object of listed value keys with numbers")
        out["bulk_containers"].append({"at": path, "kind": "object", "entries": len(o), "keys_by_id_form": {k: n for k, n in matched.items() if n}})

    def bulk_list(o, path):
        n = sum(1 for x in o if not is_number(x))
        for _ in range(n):
            bad(path, "an item that is not a number")
        out["bulk_containers"].append({"at": path, "kind": "list", "entries": len(o)})

    def walk(o, path):
        if isinstance(o, dict):
            if len(o) > bulk:
                bulk_dict(o, path); return
            for k, v in o.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(o, list):
            if len(o) > bulk:
                bulk_list(o, path); return
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
        elif isinstance(o, str):
            out["head_strings"] += 1; out["head_string_characters"] += len(o); out["longest_head_string"] = max(out["longest_head_string"], len(o))

    walk(doc, "")
    if out["head_strings"] > max_head_strings:
        bad("(head)", f"more than {max_head_strings} strings outside the bulk containers")
    if out["longest_head_string"] > max_head_string_length:
        bad("(head)", f"a string of more than {max_head_string_length} characters outside the bulk containers")
    out["violation_count"] = out.get("violation_count", 0); out["pass"] = out["violation_count"] == 0
    return out


def long_file_signs(doc, name, bulk, long_names=LONG_NAMES, long_keys=LONG_KEYS, piece_id_patterns=PIECE_ID_PATTERNS):
    """For a file without a bulk container: the signs that it is a long file all the same. -> list of short texts."""
    forms = [re.compile(p) for p in piece_id_patterns]; lk = set(long_keys); seen = set(); pieces = 0

    def walk(o):
        nonlocal pieces
        if isinstance(o, dict):
            for k, v in o.items():
                if k in lk:
                    seen.add(k)
                if any(p.fullmatch(k) for p in forms):
                    pieces += 1
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(doc); signs = []; base = os.path.basename(name)
    hit = next((g for g in long_names if fnmatch.fnmatch(base, g)), None)
    if hit:
        signs.append(f"its name matches {hit}")
    if seen:
        signs.append("it has the key " + ", ".join(sorted(seen)))
    if pieces > bulk:
        signs.append(f"{pieces} keys of an id form in containers of at most {bulk}")
    return signs


def judge(doc, name, bulk, id_patterns, value_keys, require_bulk=False, long_names=LONG_NAMES, long_keys=LONG_KEYS, piece_id_patterns=PIECE_ID_PATTERNS):
    """-> (status, check result, planted-control result or None, signs). status: PASS, FAIL, SKIP or VOID (control not reported)."""
    r = check(doc, bulk, id_patterns, value_keys)
    if not r["bulk_containers"]:
        signs = long_file_signs(doc, name, bulk, long_names, long_keys, piece_id_patterns)
        return ("FAIL" if signs and require_bulk else "SKIP"), r, None, signs
    control = planted(doc, r["bulk_containers"][0], bulk, id_patterns, value_keys)
    if not all(control.values()):
        return "VOID", r, control, []
    return ("PASS" if r["pass"] else "FAIL"), r, control, []


def get(doc, path):
    o = doc
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        o = o[int(part[1:-1])] if part.startswith("[") else o[part]
    return o


def planted(doc, first, bulk, id_patterns, value_keys):
    """Two copies of the file with one string planted in the first bulk container; both must be reported."""
    res = {}
    a = copy.deepcopy(doc); c = get(a, first["at"])
    if first["kind"] == "object":
        c["planted text that is not an id"] = 1.0
    else:
        c.append("planted text")
    res["a string as a key or an item"] = not check(a, bulk, id_patterns, value_keys)["pass"]
    b = copy.deepcopy(doc); c = get(b, first["at"])
    if first["kind"] == "object":
        k = next(iter(c)); c[k] = "planted text"
    else:
        c[0] = "planted text"
    res["a string in place of a number"] = not check(b, bulk, id_patterns, value_keys)["pass"]
    return res


def self_test():
    ok = True

    def t(name, got, want):
        nonlocal ok
        good = got == want; ok = ok and good; print(("ok   " if good else "FAIL ") + name + ("" if good else f": got {got!r}, want {want!r}"))

    q = {f"{i:024x}": {"ndcg_cut_10": 0.5, "recall_100": 1.0} for i in range(100)}; m = {f"{i}#0": {"ndcg_cut_10": 0.1, "recall_100": 0.2} for i in range(100)}
    base = {"dataset": "x", "metrics": {"ndcg_cut_10": 0.5}, "per_query": q, "passes": [{"call_ms_all": [1.5] * 100, "p50": 2}]}
    r = check(base, 60, ID_PATTERNS, VALUE_KEYS)
    t("a clean file passes", r["pass"], True); t("two bulk containers found", len(r["bulk_containers"]), 2); t("head strings counted", r["head_strings"], 1)
    t("MIRACL-style ids pass", check({"per_query": m}, 60, ID_PATTERNS, VALUE_KEYS)["pass"], True)
    for name, change in (("a key that is free text", lambda d: d["per_query"].__setitem__("how do I do this", {"ndcg_cut_10": 0.0, "recall_100": 0.0})),
                         ("a string value", lambda d: d["per_query"].__setitem__(next(iter(d["per_query"])), "text")),
                         ("a value key outside the list", lambda d: d["per_query"].__setitem__(next(iter(d["per_query"])), {"ndcg_cut_10": 0.1, "answer": 1.0})),
                         ("a string under a listed value key", lambda d: d["per_query"].__setitem__(next(iter(d["per_query"])), {"ndcg_cut_10": "text", "recall_100": 1.0})),
                         ("a string in a bulk list", lambda d: d["passes"][0]["call_ms_all"].__setitem__(5, "text")),
                         ("a nested object in a bulk list", lambda d: d["passes"][0]["call_ms_all"].__setitem__(5, {"t": 1})),
                         ("true in place of a number", lambda d: d["passes"][0]["call_ms_all"].__setitem__(5, True)),
                         ("an id with a trailing word", lambda d: d["per_query"].__setitem__("5a70eee85542994082a3e3f0 extra", {"ndcg_cut_10": 0.0, "recall_100": 0.0})),
                         ("a long string in the head", lambda d: d.__setitem__("note", "x" * 601))):
        d = copy.deepcopy(base); change(d); t("refused: " + name, check(d, 60, ID_PATTERNS, VALUE_KEYS)["pass"], False)
    t("refused: too many strings in the head", check({"h": {str(i): "s" for i in range(50)}, "g": {str(i): "s" for i in range(50)}, "f": {str(i): "s" for i in range(50)}, "per_query": q}, 60, ID_PATTERNS, VALUE_KEYS)["pass"], False)
    t("the planted controls are reported on a clean file", planted(base, r["bulk_containers"][0], 60, ID_PATTERNS, VALUE_KEYS), {"a string as a key or an item": True, "a string in place of a number": True})
    t("with no id form given, every key is refused", check({"per_query": q}, 60, [], VALUE_KEYS)["pass"], False)
    t("a file without a bulk container has none", check({"a": "b", "c": [1, 2]}, 60, ID_PATTERNS, VALUE_KEYS)["bulk_containers"], [])
    J = lambda d, n, rb=False: judge(d, n, 60, ID_PATTERNS, VALUE_KEYS, require_bulk=rb)
    short = {"dataset": "x", "note": "y" * 700, "levels": {"1": 2.0, "16": 3.0}, "list": [1, 2, 3]}
    t("a short file is skipped, not passed", J(short, "summary.json")[0], "SKIP"); t("a short file is skipped with --require-bulk too", J(short, "summary.json", True)[0], "SKIP")
    t("a short file shows no sign of a long file", J(short, "summary.json")[3], [])
    t("a long file is checked, never skipped", J(base, "summary.json")[0], "PASS"); t("a long file with a violation fails", J(dict(base, per_query=dict(q, text=1.0)), "x.json")[0], "FAIL")
    few = {"per_query": dict(list(q.items())[:40])}
    pieces = {"parts": [dict(list(q.items())[i:i + 50]) for i in (0, 50)]}; pieces_m = {"parts": [dict(list(m.items())[i:i + 50]) for i in (0, 50)]}
    for name, d, n in (("named like a long file", short, "results/a/score_after.json"), ("named like a timing file", short, "latency_container.json"), ("with a key of the long files", few, "summary.json"),
                       ("with the per-call key", {"passes": [{"call_ms_all": [1.0] * 40}]}, "summary.json"), ("cut into small containers (24 hex digits)", pieces, "summary.json"), ("cut into small containers (digits#digits)", pieces_m, "summary.json")):
        t("a file without a bulk container " + name + " fails with --require-bulk", J(d, n, True)[0], "FAIL")
        t("the same file is skipped without the option, and the sign is named", (J(d, n)[0], len(J(d, n)[3]) >= 1), ("SKIP", True))
    t("60 id keys in small containers are not a sign, 61 are", (long_file_signs({"a": dict(list(q.items())[:30]), "b": dict(list(q.items())[30:60])}, "s.json", 60), len(long_file_signs({"a": dict(list(q.items())[:30]), "b": dict(list(q.items())[30:61])}, "s.json", 60))), ([], 1))
    t("plain numbers as keys are not counted as pieces", long_file_signs({str(i): {str(j): 1.0 for j in range(50)} for i in range(5)}, "s.json", 60), [])
    t("the name is compared without its directory", long_file_signs(short, "score_files/summary.json", 60), [])
    keep = globals()["planted"]; globals()["planted"] = lambda doc, first, bulk, ids, vk: {"a string as a key or an item": True, "a string in place of a number": False}
    t("a control that is not reported voids the file", J(base, "x.json")[0], "VOID"); globals()["planted"] = keep
    print("SELF TEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    if sys.argv[1:] == ["self_test"]:
        return self_test()
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+"); ap.add_argument("--bulk", type=int, default=60); ap.add_argument("--id-pattern", action="append"); ap.add_argument("--value-key", action="append")
    ap.add_argument("--require-bulk", action="store_true", help="a file without a bulk container that looks like a long file is a violation")
    ap.add_argument("--long-name", action="append"); ap.add_argument("--long-key", action="append"); ap.add_argument("--piece-id-pattern", action="append")
    a = ap.parse_args()
    ids = a.id_pattern or ID_PATTERNS; vk = a.value_key or VALUE_KEYS; worst = 0
    totals = {"files": 0, "PASS": 0, "FAIL": 0, "VOID": 0, "SKIP": 0, "bulk_entries": 0, "checked_failing": 0, "looking_long": 0}
    for f in a.files:
        doc = json.load(open(f, encoding="utf-8"))
        status, r, control, signs = judge(doc, f, a.bulk, ids, vk, a.require_bulk, a.long_name or LONG_NAMES, a.long_key or LONG_KEYS, a.piece_id_pattern or PIECE_ID_PATTERNS)
        totals["files"] += 1; totals[status] += 1; worst = max(worst, {"PASS": 0, "SKIP": 0, "FAIL": 1, "VOID": 2}[status])
        if control is None:                                      # no bulk container: not a file of this gate's kind
            totals["looking_long"] += bool(signs)
            why = f"no container of more than {a.bulk} entries: not a file of this gate's kind"
            if signs:
                why += " · BUT IT LOOKS LIKE A LONG FILE: " + "; ".join(signs) + (" (a violation with --require-bulk)" if status == "FAIL" else " (not a violation without --require-bulk)")
            print(f"{status} {f} · {why}")
            continue
        totals["checked_failing"] += status == "FAIL"
        entries = sum(c["entries"] for c in r["bulk_containers"]); totals["bulk_entries"] += entries
        forms = {}
        for c in r["bulk_containers"]:
            for k, n in (c.get("keys_by_id_form") or {}).items():
                forms[k] = forms.get(k, 0) + n
        print(f"{status} {f} · bulk containers {len(r['bulk_containers'])} · entries {entries:,} · ids by form {forms} · head strings {r['head_strings']} ({r['head_string_characters']} characters, longest {r['longest_head_string']})"
              f" · planted controls {'reported' if all(control.values()) else 'NOT REPORTED'}")
        for v in r["violations"][:10]:
            print(f"     {v['kind']} at {v['at'] or '(top)'}")
        if r["violation_count"] > 10:
            print(f"     ... {r['violation_count']} violations in all")
    print(f"RESULT {'PASS' if worst == 0 else 'FAIL'} · files {totals['files']} · checked {totals['PASS'] + totals['checked_failing'] + totals['VOID']} (passing {totals['PASS']}, failing {totals['checked_failing']}, control not reported {totals['VOID']})"
          f" · entries in bulk containers {totals['bulk_entries']:,} · skipped as not of this kind {totals['SKIP']}"
          f" · without a bulk container but looking like a long file {totals['looking_long']}{' (violations)' if a.require_bulk and totals['looking_long'] else ''}")
    return worst

if __name__ == "__main__":
    sys.exit(main())
