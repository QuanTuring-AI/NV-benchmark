#!/usr/bin/env python3
"""Verify the claim-to-evidence tables of the volume READMEs: every row names a file and a key, and the value stored
there must match the number in the row.

A table is any markdown table whose header starts with `| In the post |`. Columns:
  In the post   the sentence or cell the number comes from
  Number        one number, or several separated by " · " (then Key holds {a,b,c} and expands to as many expressions)
  File          a path in backticks, relative to the README's directory
  Key           in backticks; `\\|` is a literal pipe. An expression over JSON paths: + - * / and parentheses. An atom
                is a number or a dotted path (a key may itself contain dots: the longest matching key wins; [i]
                indexes a list); `other/file.json::path` reads another file. For Check = text, Key is a literal that
                must occur in File.
  Check         rounds   |value - number| <= half a unit of the number's last printed digit
                approx   within 5% of the number
                equals   the value equals the Number cell (true / false / null / a quoted string / a number)
                text     the literal occurs in the file
usage: check_claims.py <README.md> [<README.md> ...]     exit code 0 only if every row of every table passes
       check_claims.py self_test
"""
import json, os, re, sys, tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NUM = re.compile(r"[-+−]?\d[\d,]*(?:\.\d+)?")
_cache = {}


def load(path):
    if path not in _cache:
        _cache[path] = json.load(open(path, encoding="utf-8-sig"))
    return _cache[path]


def resolve(obj, path):
    segs = []
    for part in path.split("."):
        m = re.fullmatch(r"(.*?)((?:\[\d+\])*)", part)
        segs.append((m.group(1), [int(x) for x in re.findall(r"\[(\d+)\]", m.group(2))]))

    def rec(o, i):
        if i == len(segs):
            return True, o
        if not isinstance(o, dict):
            return False, None
        for j in range(len(segs), i, -1):  # longest key first: a key may contain dots
            key = ".".join(s[0] + "".join(f"[{n}]" for n in s[1]) for s in segs[i:j - 1] + [(segs[j - 1][0], [])])
            if key in o:
                v = o[key]
                try:
                    for n in segs[j - 1][1]:
                        v = v[n]
                except (IndexError, TypeError, KeyError):
                    continue
                ok, out = rec(v, j)
                if ok:
                    return ok, out
        return False, None
    ok, out = rec(obj, 0)
    if not ok:
        raise KeyError(path)
    return out


def tokenize(expr):
    out, i = [], 0
    while i < len(expr):
        c = expr[i]
        if c.isspace():
            i += 1
        elif c in "()":
            out.append(c); i += 1
        elif c in "+*/" or (c == "-" and i + 1 < len(expr) and expr[i + 1] == " " and out and out[-1] not in ("+", "-", "*", "/", "(")):
            out.append(c); i += 1
        else:  # an atom runs to the next " <operator> " or parenthesis
            j = i
            while j < len(expr) and expr[j] not in "()" and not (expr[j] == " " and j + 2 < len(expr) and expr[j + 1] in "+-*/" and expr[j + 2] == " "):
                j += 1
            out.append(expr[i:j].strip()); i = j
    return out


def evaluate(expr, base, default_file):
    toks = tokenize(expr); pos = [0]

    def atom():
        t = toks[pos[0]]; pos[0] += 1
        if t == "(":
            v = add(); pos[0] += 1
            return v
        if re.fullmatch(r"\d+(?:\.\d+)?", t):
            return float(t)
        f, p = t.split("::", 1) if "::" in t else (default_file, t)
        return resolve(load(os.path.join(base, f)), p)

    def mul():
        v = atom()
        while pos[0] < len(toks) and toks[pos[0]] in ("*", "/"):
            op = toks[pos[0]]; pos[0] += 1; w = atom()
            v = v * w if op == "*" else v / w
        return v

    def add():
        v = mul()
        while pos[0] < len(toks) and toks[pos[0]] in ("+", "-"):
            op = toks[pos[0]]; pos[0] += 1; w = mul()
            v = v + w if op == "+" else v - w
        return v
    return add()


def parse_number(s):
    t = NUM.search(s).group(0).replace(",", "").replace("−", "-")
    return float(t), (len(t.split(".")[1]) if "." in t else 0)


def expand(key):
    m = re.search(r"\{([^{}]*,[^{}]*)\}", key)
    return [key] if not m else [key[:m.start()] + a.strip() + key[m.end():] for a in m.group(1).split(",")]


def split_row(line):
    cells, cur, i = [], "", 0
    line = line.strip()[1:-1]
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur += "\x00"; i += 2
        elif line[i] == "|":
            cells.append(cur.strip()); cur = ""; i += 1
        else:
            cur += line[i]; i += 1
    cells.append(cur.strip())
    return [c.replace("\x00", "|") for c in cells]


def check_row(cells, base):
    """One table row -> a list of (passed, message), one entry per number in the row."""
    _post, number, file_cell, key_cell, how = cells[:5]
    f = re.search(r"`([^`]+)`", file_cell).group(1)
    key = re.search(r"`(.+)`", key_cell).group(1)
    how = how.strip().split()[0]
    if how == "text":
        ok = key in open(os.path.join(base, f), encoding="utf-8", errors="replace").read()
        return [(ok, f"text {'found' if ok else 'NOT FOUND'}: {key[:60]}")]
    keys = expand(key)
    if how == "equals":
        v = evaluate(keys[0], base, f); want = number.strip().strip("*")
        lit = {"true": True, "false": False, "null": None}.get(want, want.strip('"'))
        if isinstance(v, (int, float)) and not isinstance(v, bool) and not isinstance(lit, (bool, type(None))):
            lit = parse_number(want)[0]
        return [(v == lit, f"{v!r} vs {lit!r}")]
    nums = [n for n in re.split(r"\s+·\s+", number.strip().strip("*")) if n]
    if len(nums) != len(keys):
        return [(False, f"{len(nums)} numbers but {len(keys)} keys")]
    out = []
    for n, k in zip(nums, keys):
        v = evaluate(k, base, f); want, d = parse_number(n)
        tol = 0.05 * abs(want) if how == "approx" else 0.5 * 10 ** (-d) + 1e-6
        out.append((isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v - want) <= tol, f"{n} vs {v:.6g} (tolerance {tol:.3g})"))
    return out


def check_readme(path):
    lines = open(path, encoding="utf-8").read().splitlines(); base = os.path.dirname(os.path.abspath(path))
    checks = bad = 0; in_table = False
    for i, line in enumerate(lines):
        if line.startswith("| In the post |"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                in_table = False; continue
            if re.fullmatch(r"\|[-:| ]+\|", line.strip()):
                continue
            cells = split_row(line)
            try:
                res = check_row(cells, base)
            except Exception as e:  # noqa: BLE001  a missing file or key is a failed row, not a crash
                res = [(False, f"{type(e).__name__}: {e}")]
            for ok, msg in res:
                checks += 1
                if not ok:
                    bad += 1; print(f"  FAIL {path} line {i + 1}: {cells[0][:50]} | {msg}")
    print(f"{path}: checks {checks}, failed {bad}")
    return checks, bad


def self_test():
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want; ok = ok and good
        print(("  PASS " if good else "  FAIL ") + f"{name}: {got} (want {want})")
    o = {"a": {"b.c": {"d|e": [1.0, 7.365]}}, "x": 5457.87, "y": 741.05, "t": True}
    check("a key that contains dots, and a list index", resolve(o, "a.b.c.d|e[1]"), 7.365)
    d = tempfile.mkdtemp(); json.dump(o, open(os.path.join(d, "f.json"), "w"))
    row = lambda number, key, how: check_row(["p", number, "`f.json`", f"`{key}`", how], d)  # noqa: E731
    check("a ratio that rounds to 7.4", row("7.4×", "x / y", "rounds")[0][0], True)
    check("a wrong number is caught (7.5)", row("7.5×", "x / y", "rounds")[0][0], False)
    check("parentheses and a literal", row("4.7", "(x - y) / 1000", "rounds")[0][0], True)
    check("brace expansion, two numbers", [r[0] for r in row("5,458 · 741", "{x,y}", "rounds")], [True, True])
    check("two numbers, one key: fails", row("5,458 · 741", "x", "rounds")[0][0], False)
    check("approx within 5%", row("~5,300", "x", "approx")[0][0], True)
    check("approx outside 5%", row("~5,000", "x", "approx")[0][0], False)
    check("equals true", row("true", "t", "equals")[0][0], True)
    check("equals, wrong value", row("false", "t", "equals")[0][0], False)
    check("the minus sign U+2212", parse_number("−1.52")[0], -1.52)
    try:
        row("1", "nope", "rounds"); got = "no error"
    except KeyError:
        got = "KeyError"
    check("a key that does not exist raises (check_readme counts it as a failed row)", got, "KeyError")
    open(os.path.join(d, "t.md"), "w", encoding="utf-8").write("abc UVA is not available xyz")
    check("text found", check_row(["p", "", "`t.md`", "`UVA is not available`", "text"], d)[0][0], True)
    check("text missing", check_row(["p", "", "`t.md`", "`no such text`", "text"], d)[0][0], False)
    check("an escaped pipe inside a cell", split_row("| a | 1 | `f` | `k\\|m` | rounds |")[3], "`k|m`")
    # a whole README: one good row and one wrong row -> exactly one failure, and an empty README has no checks
    md = os.path.join(d, "README.md")
    open(md, "w", encoding="utf-8").write("| In the post | Number | File | Key | Check |\n|---|---|---|---|---|\n| good | 7.4× | `f.json` | `x / y` | rounds |\n| wrong | 9.9× | `f.json` | `x / y` | rounds |\n")
    check("a README with one wrong row: (checks, failed)", check_readme(md), (2, 1))
    open(md, "w", encoding="utf-8").write("no table here\n")
    check("a README without a table: (checks, failed)", check_readme(md), (0, 0))
    print("SELF-TEST " + ("PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    if sys.argv[1:] == ["self_test"]:
        sys.exit(0 if self_test() else 1)
    if not sys.argv[1:]:
        print(__doc__); sys.exit(2)
    totals = [check_readme(p) for p in sys.argv[1:]]
    passed = all(bad == 0 and checks > 0 for checks, bad in totals)  # a README with no table is not a pass
    print("RESULT", "PASS" if passed else "FAIL", "· checks", sum(c for c, _ in totals), "· failed", sum(b for _, b in totals))
    sys.exit(0 if passed else 1)
