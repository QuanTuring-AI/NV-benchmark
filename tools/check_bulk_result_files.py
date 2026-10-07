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

Defaults: ids of 24 hex digits (HotpotQA), digits#digits (MIRACL queries), digits (BEIR SciFact); value keys
ndcg_cut_10 and recall_100.

usage: check_bulk_result_files.py [--bulk 60] [--id-pattern REGEX ...] [--value-key NAME ...] [--require-bulk] FILE [FILE ...]
       check_bulk_result_files.py self_test
exit codes: 0 every file passes · 1 a violation · 2 a planted control was not reported
"""
import argparse, copy, json, re, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ID_PATTERNS = [r"[0-9a-f]{24}", r"\d+#\d+", r"\d+"]
VALUE_KEYS = ["ndcg_cut_10", "recall_100"]


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
    print("SELF TEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    if sys.argv[1:] == ["self_test"]:
        return self_test()
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+"); ap.add_argument("--bulk", type=int, default=60); ap.add_argument("--id-pattern", action="append"); ap.add_argument("--value-key", action="append")
    ap.add_argument("--require-bulk", action="store_true", help="a file without a bulk container is a violation")
    a = ap.parse_args()
    ids = a.id_pattern or ID_PATTERNS; vk = a.value_key or VALUE_KEYS; worst = 0; totals = {"files": 0, "pass": 0, "bulk_entries": 0, "without_bulk": 0}
    for f in a.files:
        doc = json.load(open(f, encoding="utf-8")); r = check(doc, a.bulk, ids, vk); totals["files"] += 1
        entries = sum(c["entries"] for c in r["bulk_containers"]); totals["bulk_entries"] += entries
        if not r["bulk_containers"]:
            totals["without_bulk"] += 1
            if a.require_bulk:
                r["pass"] = False; r["violations"].append({"at": "", "kind": "no bulk container"})
            control = None
        else:
            control = planted(doc, r["bulk_containers"][0], a.bulk, ids, vk)
            if not all(control.values()):
                worst = 2
        if not r["pass"]:
            worst = max(worst, 1)
        totals["pass"] += r["pass"] and (control is None or all(control.values()))
        forms = {}
        for c in r["bulk_containers"]:
            for k, n in (c.get("keys_by_id_form") or {}).items():
                forms[k] = forms.get(k, 0) + n
        print(f"{'PASS' if r['pass'] else 'FAIL'} {f} · bulk containers {len(r['bulk_containers'])} · entries {entries:,} · ids by form {forms} · head strings {r['head_strings']} ({r['head_string_characters']} characters, longest {r['longest_head_string']})"
              f" · planted controls {'reported' if control and all(control.values()) else ('NOT REPORTED' if control else 'none (no bulk container)')}")
        for v in r["violations"][:10]:
            print(f"     {v['kind']} at {v['at'] or '(top)'}")
        if r["violation_count"] > 10:
            print(f"     ... {r['violation_count']} violations in all")
    print(f"RESULT {'PASS' if worst == 0 else 'FAIL'} · files {totals['files']} · passing {totals['pass']} · entries in bulk containers {totals['bulk_entries']:,} · files without a bulk container {totals['without_bulk']}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
