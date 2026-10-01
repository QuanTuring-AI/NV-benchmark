#!/usr/bin/env python3
"""Rename the volume directories to match the volume numbers (2026-09-28). Input: tools/renumber_map.json.

Phases, each run separately and in this order:
  rename   commit 1, moves only. Every tracked file under an old root is re-registered in the index at its new path with
           the same mode and blob id (`git update-index --index-info`), which is what `git mv` does; its bytes on disk are
           moved with it. Ignored and untracked files under the old roots are moved on disk by the same rules (git does
           not move them). Empty old directories are removed. The commit holds renames only.
  docs     commit 2. PATH_MAP.json and PATH_MAP.md generated from commit 1's `git diff -M100% --name-status`; the path
           patterns in .gitignore and .git/info/exclude rewritten; the generated part of .gitattributes regenerated from
           the history-anchored binding list (tools/bound_files.py --history --attributes); in every tracked .md file that
           no pre-registration binds, old paths rewritten and relative links re-pointed. No bound file is touched.
           `docs --no-commit` stages the same set and stops, leaving the message for `git commit -F`.
  verify   no commit. Re-checks what the two commits must hold and writes a report outside the repository.
  tags     annotated tags created locally only (never pushed here); existing tags are left as they are.
The state of the environment before the move (tracked, ignored and untracked files under the old roots) is written to
.git/renumber_before.json by `rename` and read by `verify`.
  move-untracked  no commit. In a working tree whose HEAD already holds the rename (for example the main working tree
           after it checks out the renamed branch), moves the ignored and untracked files still under the old roots by the
           same rules, removes the empty old directories and checks that the ignored set maps one to one. git leaves those
           files where they were on checkout; this is the step that keeps them from staying behind.
  check-old-dirs  no commit. Exit 3 if a directory with an old root name exists on disk (a harness written for the old
           paths, run on the renamed tree, would recreate one silently). verify runs the same gate.
  pathmap  no commit. Regenerates PATH_MAP.json / PATH_MAP.md from the rename commit.
Paths are mapped by renumber_map.json: first `run_codes` (a run's results/ and scripts/ entries go to that run's volume,
whichever old root holds them), then `moves` in order.
Generations (added 2026-09-29): tools/renumber_map.json is the first rename (2026-09-28), tools/renumber_map_2.json the
second (2026-09-29, Vol.2 and Vol.3 swapped). `--gen N` selects the generation a phase works on; the default is the
newest. PATH_MAP follows every path through all generations up to the selected one, and the old-directory gate refuses
the old roots of every generation. A generation's `history_files` (CHANGELOG.md) record past paths on purpose and are
left to be updated by hand.
usage: renumber_dirs.py [--gen N] rename | docs | verify --report FILE [--clones] | tags --target NAME=REV ... | move-untracked
                        | check-old-dirs | pathmap
"""
import argparse, collections, json, os, posixpath, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bound_files as BF  # noqa: E402

MAP_FILES = [f for f in ("renumber_map.json", "renumber_map_2.json") if os.path.exists(os.path.join(HERE, f))]
MAPS = [json.load(open(os.path.join(HERE, f), encoding="utf-8")) for f in MAP_FILES]
GEN = int(sys.argv[sys.argv.index("--gen") + 1]) if "--gen" in sys.argv else len(MAPS)
MAP = MAPS[GEN - 1]
MOVES = [(m["from"], m["to"]) for m in MAP["moves"]]
OLD, NEW = MAP["old_roots"], MAP["new_roots"]
ALL_OLD = [o for m in MAPS for o in m["old_roots"]]          # the gate refuses every generation's old roots
HISTORY_FILES = set(MAP.get("history_files", []))
TRAILER = "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
GITDIR = subprocess.run(["git", "-C", ROOT, "rev-parse", "--absolute-git-dir"], capture_output=True, text=True).stdout.strip()
BEFORE = os.path.join(GITDIR, "renumber_before.json" if GEN == 1 else f"renumber_before_g{GEN}.json")   # .git is a file in a linked worktree
NO_COMMIT = "--no-commit" in sys.argv
SUBJECTS = ["Rename the volume directories to match the volume numbers (moves only)"] + [m["subject"] for m in MAPS[1:]]
RENAME_SUBJECT = SUBJECTS[GEN - 1]
PROTECTED_PREFIX, PROTECTED_FILES = "benchmark/", {"DEPLOYMENT_NOTES.md"}   # the March 2026 publication: never edited
PATH_TOKEN = re.compile(r"(?<![\w.-])(" + "|".join(re.escape(o) for o in sorted(OLD, key=len, reverse=True)) + r")/")
LINK = re.compile(r"(\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")


def git(*a, input=None, check=True, raw=False):
    r = subprocess.run(["git", "-C", ROOT, "-c", "core.quotepath=off", *a], capture_output=True, input=input)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(a)} failed: {r.stderr.decode('utf-8', 'replace')}")
    return r.stdout if raw else r.stdout.decode("utf-8")


RUN_CODES = MAP.get("run_codes", {})
RUN_CODE = re.compile(r"^(" + "|".join(re.escape(o) for o in OLD) + r")/(results|scripts)/((?:run_)?(p\d+)(?:[_./]|$).*)$")


def map_path(p):
    m = RUN_CODE.match(p)
    if m and m.group(4) in RUN_CODES:   # a run's own results and scripts go to its volume, whichever old root holds them
        return f"{RUN_CODES[m.group(4)]}/{m.group(2)}/{m.group(3)}"
    for f, t in MOVES:
        if p.startswith(f):
            return t + p[len(f):]
    return None


def under_old(p):
    return any(p == o or p.startswith(o + "/") for o in OLD)


def z(out):
    return [x for x in out.split("\0") if x]


def environment():
    tracked = z(git("ls-files", "-z"))
    ignored = z(git("ls-files", "-z", "--others", "--ignored", "--exclude-standard"))
    untracked = z(git("ls-files", "-z", "--others", "--exclude-standard"))
    return tracked, ignored, untracked


def disk_files(root_rel):
    out = []
    for dp, dn, fn in os.walk(os.path.join(ROOT, root_rel)):
        out += [os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, "/") for f in fn]
    return out


# --- phase 1 ---------------------------------------------------------------------------------------------------------

def phase_rename():
    if git("diff", "--cached", "--name-only").strip():
        sys.exit("refused: the index has staged changes")
    dirty = [l for l in git("status", "--porcelain", "-uno").splitlines() if under_old(l[3:])]
    if dirty:
        sys.exit(f"refused: tracked changes under the old roots: {dirty[:5]}")
    if any(os.path.exists(os.path.join(ROOT, n)) for n in NEW):
        sys.exit(f"refused: a new root already exists: {[n for n in NEW if os.path.exists(os.path.join(ROOT, n))]}")
    tracked, ignored, untracked = environment()
    mv_t = [p for p in tracked if under_old(p)]
    mv_i = [p for p in ignored if under_old(p)]
    mv_u = [p for p in untracked if under_old(p)]
    if any(map_path(p) is None for p in mv_t + mv_i + mv_u):
        sys.exit("refused: a path under an old root matches no rule")
    json.dump({"head": git("rev-parse", "HEAD").strip(), "tracked_moved": mv_t, "ignored": mv_i, "untracked": mv_u,
               "ignored_total": len(ignored), "untracked_total": len(untracked)},
              open(BEFORE, "w", encoding="utf-8"), indent=0)
    idx = {}
    for rec in z(git("ls-files", "-s", "-z")):
        meta, path = rec.split("\t", 1); mode, sha, stage = meta.split()
        if stage != "0":
            sys.exit(f"refused: unmerged entry {path}")
        idx[path] = (mode, sha)
    info = []
    for p in mv_t:
        mode, sha = idx[p]
        info.append(f"0 {'0' * 40}\t{p}"); info.append(f"{mode} {sha}\t{map_path(p)}")
    git("update-index", "-z", "--index-info", input=("\0".join(info) + "\0").encode("utf-8"))
    failed = []
    for p in mv_t + mv_i + mv_u:
        src, dst = os.path.join(ROOT, p), os.path.join(ROOT, map_path(p))
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True); os.replace(src, dst)
        except OSError as e:
            failed.append({"path": p, "error": str(e)})
    for o in OLD:
        for dp, dn, fn in sorted(os.walk(os.path.join(ROOT, o)), key=lambda x: -len(x[0])):
            if not fn and not os.listdir(dp):
                os.rmdir(dp)
    left = {o: disk_files(o) for o in OLD if os.path.exists(os.path.join(ROOT, o))}
    body = MAP.get("commit_body", "vol1a-revisit/ -> vol1-nim/ (Vol.1, renewed), vol1b/ -> vol2-guardrails/ (Vol.2), vol2/ -> vol3-nemotron/ (Vol.3); "
                                  "P54 (a Vol.1 run kept in vol2/) -> vol1-nim/.")
    msg = (f"{RENAME_SUBJECT}\n\n"
           f"{body} {len(mv_t)} tracked files, each with its blob unchanged. "
           f"Generated by tools/renumber_dirs.py from tools/{MAP_FILES[GEN - 1]}; paths are mapped in PATH_MAP.md (next commit)." + TRAILER)
    git("commit", "-q", "-m", msg)
    ns = git("diff", "-M100%", "--name-status", "HEAD~1", "HEAD").splitlines()
    kinds = collections.Counter(l.split("\t")[0] for l in ns)
    print(json.dumps({"commit": git("rev-parse", "HEAD").strip(), "tracked_moved": len(mv_t), "ignored_moved": len(mv_i), "untracked_moved": len(mv_u),
                      "name_status": dict(kinds), "move_failures": failed, "files_left_under_old_roots": {k: len(v) for k, v in left.items()}}, indent=1))
    return 0 if not failed and not left and set(kinds) == {"R100"} and kinds["R100"] == len(mv_t) else 1


# --- phase 2 ---------------------------------------------------------------------------------------------------------

def rename_commit(g=None):
    """The commit made by phase 1 of generation g: the newest commit whose message holds that generation's subject."""
    c = git("log", "-1", "--format=%H", "--fixed-strings", f"--grep={SUBJECTS[(g or GEN) - 1]}").strip()
    if not c:
        sys.exit(f"no rename commit found for generation {g or GEN}")
    return c


def path_map(c):
    rows = []
    parts = z(git("diff", "-M100%", "--name-status", "-z", f"{c}~1", c))
    i = 0
    while i < len(parts):
        st = parts[i]
        if st.startswith("R"):
            rows.append((st, parts[i + 1], parts[i + 2])); i += 3
        else:
            rows.append((st, parts[i + 1], None)); i += 2
    return rows


def path_map_files(c):
    """PATH_MAP.json / PATH_MAP.md. Generation 1 keeps its original form byte for byte; from generation 2 on, every path
    is followed through all rename commits up to the selected generation (one column per state)."""
    if GEN >= 2:
        return path_map_files_chain()
    rows = path_map(c)
    tree = git("rev-parse", f"{c}^{{tree}}").strip()
    js = {"generated_by": "tools/renumber_dirs.py docs (from `git diff -M100% --name-status` of the rename commit)",
          "rename_commit_subject": RENAME_SUBJECT, "rename_commit_tree": tree,
          "rows": len(rows), "status_counts": dict(collections.Counter(r[0] for r in rows)),
          "map": [{"old": o, "new": n} for s, o, n in rows]}
    md = ["# Path map", "",
          "Directories were renamed on 2026-09-28 to match the volume numbers. Files written before that date, including frozen "
          "pre-registrations, refer to the old paths; this file maps every one. To reproduce a run byte for byte, check out the "
          "tag listed for its volume. Check out a tag or the tip of the branch; the pure-rename commit alone is not a supported "
          "checkout (its .gitattributes still names the old paths).", "",
          "| Volume | Directory | Reproduce with |", "|---|---|---|",
          "| Vol.1 | `vol1-nim/` | `git checkout vol1-nim-published` |",
          "| Vol.2 | `vol2-guardrails/` | `git checkout vol2-guardrails-published` |",
          "| Vol.3 | `vol3-nemotron/` | `git checkout vol3-nemotron-published` |", "",
          f"Generated by `tools/renumber_dirs.py` from `git diff -M100% --name-status` of the rename commit (subject \"{RENAME_SUBJECT}\", "
          f"tree `{tree[:12]}`): "
          f"{len(rows)} rows, every one a pure move (`R100`). `PATH_MAP.json` holds the same rows.", "",
          "| Old path | New path |", "|---|---|"]
    md += [f"| `{o}` | `{n}` |" for s, o, n in rows]
    return json.dumps(js, indent=1, ensure_ascii=False) + "\n", "\n".join(md) + "\n", rows


def path_map_files_chain():
    gens = []
    for g in range(1, GEN + 1):
        cg = rename_commit(g)
        gens.append({"gen": g, "date": MAPS[g - 1]["date"], "subject": SUBJECTS[g - 1],
                     "tree": git("rev-parse", f"{cg}^{{tree}}").strip(), "rows": path_map(cg)})
    chain = [[o, n] for s, o, n in gens[0]["rows"]]
    for k, G in enumerate(gens[1:], start=2):
        nxt = {o: n for s, o, n in G["rows"]}
        seen = set()
        for row in chain:
            seen.add(row[-1]); row.append(nxt.get(row[-1], row[-1]))
        chain += [[None] * (k - 1) + [o, n] for s, o, n in G["rows"] if o not in seen]
    cols = [f"Before {gens[0]['date']}"] + [G["date"] for G in gens[:-1]] + [f"Since {gens[-1]['date']}"]
    js = {"generated_by": "tools/renumber_dirs.py docs (from `git diff -M100% --name-status` of each rename commit)",
          "generations": [{"date": G["date"], "rename_commit_subject": G["subject"], "rename_commit_tree": G["tree"],
                           "rows": len(G["rows"]), "status_counts": dict(collections.Counter(r[0] for r in G["rows"]))} for G in gens],
          "columns": cols, "rows": len(chain), "chain": [dict(zip(cols, r)) for r in chain]}
    md = ["# Path map", "", MAP["path_map_intro"], "",
          "| Volume | Directory | Reproduce with |", "|---|---|---|"]
    md += [f"| {v} | `{d}` | `git checkout {t}` |" for v, d, t in MAP["volume_table"]]
    md += ["", "Generated by `tools/renumber_dirs.py` from `git diff -M100% --name-status` of each rename commit ("
           + "; ".join(f"{G['date']}: subject \"{G['subject']}\", tree `{G['tree'][:12]}`, {len(G['rows'])} rows" for G in gens)
           + f"). Every row of every rename is a pure move (`R100`). {len(chain)} paths; `PATH_MAP.json` holds the same rows.", "",
           "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(f"`{x}`" if x else "—" for x in r) + " |" for r in chain]
    return json.dumps(js, indent=1, ensure_ascii=False) + "\n", "\n".join(md) + "\n", gens[-1]["rows"]


def rewrite_tokens(text):
    out, last = [], 0
    for m in PATH_TOKEN.finditer(text):
        tail = text[m.start():]
        new = map_path(tail[:200])
        if new is None:
            continue
        f = next(f for f, t in MOVES if tail.startswith(f))
        out.append(text[last:m.start()]); out.append(map_path(f)); last = m.start() + len(f)
    out.append(text[last:])
    return "".join(out)


def rewrite_links(text, old_md, new_md, exists):
    def fix(m):
        tgt = m.group(2)
        if re.match(r"^[a-z]+:|^#|^/", tgt):
            return m.group(0)
        path, frag = (tgt.split("#", 1) + [""])[:2]
        if not path:
            return m.group(0)
        slash = path.endswith("/")
        old_abs = posixpath.normpath(posixpath.join(posixpath.dirname(old_md), path))
        if old_abs.startswith(".."):
            return m.group(0)
        new_abs = map_path(old_abs + "/")[:-1] if map_path(old_abs + "/") else old_abs
        new_abs = map_path(old_abs) or new_abs
        rel = posixpath.relpath(new_abs, posixpath.dirname(new_md) or ".") + ("/" if slash else "")
        new_tgt = rel + (("#" + frag) if frag else "")
        return m.group(1) + (new_tgt if new_tgt != tgt and exists(new_abs) else tgt) + m.group(3)
    return LINK.sub(fix, text)


def gitattributes(bound_lines):
    cur = open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8").read().splitlines()
    head = []
    for l in cur:
        if l.startswith("# generated by tools/bound_files.py"):
            head.append(f"# generated by tools/bound_files.py --history --attributes ({MAP['date']}, after the directory rename)")
            break
        head.append(rewrite_tokens(l))
    return "\n".join(head + bound_lines) + "\n", cur


def phase_docs():
    c = rename_commit()
    if git("rev-parse", "HEAD").strip() != c:
        sys.exit("refused: HEAD is not the rename commit (phase docs runs right after phase rename)")
    js, md, rows = path_map_files(c)
    new_of_old = {o: n for s, o, n in rows}; old_of_new = {n: o for s, o, n in rows}
    open(os.path.join(ROOT, "PATH_MAP.json"), "w", encoding="utf-8", newline="\n").write(js)
    open(os.path.join(ROOT, "PATH_MAP.md"), "w", encoding="utf-8", newline="\n").write(md)
    changed = ["PATH_MAP.json", "PATH_MAP.md"]
    report = {}
    excl = subprocess.run(["git", "-C", ROOT, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"], capture_output=True, text=True).stdout.strip()
    for f in (".gitignore", excl):
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            continue
        a = open(p, encoding="utf-8").read(); b = rewrite_tokens(a)
        report[".gitignore" if f == ".gitignore" else "info/exclude"] = [(x, y) for x, y in zip(a.splitlines(), b.splitlines()) if x != y]
        if a != b:
            open(p, "w", encoding="utf-8", newline="\n").write(b)
            if f == ".gitignore":
                changed.append(".gitignore")
    bs, h = BF.enumerate_bindings_history(ROOT)
    bound = sorted({b["target"] for b in bs if b["kind"] == "file" and b["status"] == "ok"})
    old_ga = open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8").read().splitlines()
    gen_at = next(i for i, l in enumerate(old_ga) if l.startswith("# generated by tools/bound_files.py"))
    old_generated = [l for l in old_ga[gen_at + 1:] if l.endswith(" -text")]
    mapped_old = sorted(rewrite_tokens(l) for l in old_generated)
    new_set = {f"{t} -text" for t in bound}
    kept = sorted(set(mapped_old) - new_set)   # bound but not tracked (ignored): kept so that no protection is lost
    ga, _ = gitattributes(sorted(new_set | set(kept)))
    report[".gitattributes"] = {"old_generated_lines": len(old_generated), "history_anchored_bound_tracked": len(bound),
                                "kept_from_the_old_list_not_tracked": kept, "only_in_new": sorted(new_set - set(mapped_old)),
                                "new_generated_lines": len(new_set | set(kept))}
    open(os.path.join(ROOT, ".gitattributes"), "w", encoding="utf-8", newline="\n").write(ga)
    changed.append(".gitattributes")
    tree = set(z(git("ls-files", "-z"))) | {"PATH_MAP.json", "PATH_MAP.md"}
    dirs = {posixpath.dirname(p) for p in tree}
    alld = set()
    for d in dirs:
        while d:
            alld.add(d); d = posixpath.dirname(d)
    exists = lambda p: p in tree or p in alld
    md_changed, md_skipped_bound = [], []
    for p in sorted(x for x in tree if x.endswith(".md") and x not in ("PATH_MAP.md",)):
        if p in bound or p.startswith(PROTECTED_PREFIX) or p in PROTECTED_FILES or p in HISTORY_FILES:
            md_skipped_bound.append(p); continue
        a = open(os.path.join(ROOT, p), encoding="utf-8", newline="").read()
        b = rewrite_tokens(rewrite_links(a, old_of_new.get(p, p), p, exists))
        if a != b:
            open(os.path.join(ROOT, p), "w", encoding="utf-8", newline="").write(b); md_changed.append(p)
    changed += md_changed
    for f in changed:
        git("add", "--", f)
    staged = sorted(z(git("diff", "--cached", "--name-only", "-z")))
    if sorted(set(changed)) != staged:
        sys.exit(f"refused: staged set differs from the intended set: {sorted(set(staged) ^ set(changed))}")
    msg = (f"{MAP.get('docs_label', 'Directory rename')}, part 2: PATH_MAP.md / PATH_MAP.json ({len(rows)} rows), .gitignore patterns, .gitattributes regenerated "
           f"(history-anchored bindings, {len(bound)} files), old paths and relative links in {len(md_changed)} unbound .md files\n\n"
           f"No file bound by a pre-registration or sidecar is changed. Generated by tools/renumber_dirs.py docs." + TRAILER)
    if NO_COMMIT:   # stage only; the message is left in the git dir for `git commit -F`, after the staged scan
        open(os.path.join(GITDIR, "renumber_docs_msg.txt"), "w", encoding="utf-8", newline="\n").write(msg)
        print(json.dumps({"staged_only": staged, "message_file": os.path.join(GITDIR, "renumber_docs_msg.txt")}, indent=1)); return 0
    git("commit", "-q", "-m", msg)
    print(json.dumps({"commit": git("rev-parse", "HEAD").strip(), "path_map_rows": len(rows), "md_changed": md_changed,
                      "md_skipped_bound": md_skipped_bound, "rewrites": report}, indent=1, ensure_ascii=False))
    return 0


# --- phase 3 ---------------------------------------------------------------------------------------------------------

def bindings_summary(root):
    bs, h = BF.enumerate_bindings_history(root)
    v = BF.verify_history(bs, h, root)
    return {"enumerated": len(bs), "classes": BF.class_counts(bs), **{k: len(v[k]) for k in v},
            "ok_later_commits": dict(collections.Counter(b["verified_at"][0][:12] for b in v["ok_later"])),
            "mismatch": [f"{b['source']} [{b['class']}] {b['name']}" for b in v["mismatch"]],
            "unresolved": [f"{b['source']} [{b['class']}] {b['name']}" for b in v["unresolved"]],
            "disk_mismatch": [b["target"] for b in v["disk_mismatch"]], "disk_missing": [b["target"] for b in v["disk_missing"]]}, bs


def phase_verify(a):
    c = rename_commit(); head = git("rev-parse", "HEAD").strip()
    rep = {"head": head, "rename_commit": c}
    ns = path_map(c)
    before = json.load(open(BEFORE, encoding="utf-8")) if os.path.exists(BEFORE) else None
    kinds = collections.Counter(s for s, o, n in ns)
    rep["1_rename_commit_pure_moves"] = {"name_status": dict(kinds), "tracked_moved_before": before and len(before["tracked_moved"]),
                                         "pass": set(kinds) == {"R100"} and before is not None and kinds["R100"] == len(before["tracked_moved"])}
    summ, bs = bindings_summary(ROOT)
    rep["2_3_bindings_history_anchored"] = summ
    rep["4_planted_controls"] = subprocess.run([sys.executable, os.path.join(HERE, "bound_files.py"), "--self-test-history"], capture_output=True, text=True).stdout.splitlines()
    if a.clones:
        out = {}
        for crlf in ("true", "false"):
            t = tempfile.mkdtemp(prefix=f"renum_{crlf}_")
            subprocess.run(["git", "-c", f"core.autocrlf={crlf}", "clone", "-q", "--no-local", "--branch", git("rev-parse", "--abbrev-ref", "HEAD").strip(), ROOT, t], check=True)
            subprocess.run(["git", "-C", t, "config", "core.autocrlf", crlf], check=True)
            s, _ = bindings_summary(t)
            out[f"autocrlf={crlf}"] = {k: s[k] for k in ("enumerated", "ok", "ok_later", "mismatch", "unresolved", "current_same", "disk_ok", "disk_mismatch", "disk_missing")}
            out[f"autocrlf={crlf}"]["disk_mismatch_files"] = s["disk_mismatch"]
            shutil.rmtree(t, ignore_errors=True)
        rep["5_clones"] = out
    tracked, ignored, untracked = environment()
    if before:
        want = sorted(map_path(p) for p in before["ignored"]); got = sorted(p for p in ignored if any(p.startswith(n + "/") for n in NEW))
        rep["6_process_files"] = {"ignored_before": len(before["ignored"]), "ignored_after_under_new_roots": len(got), "ignored_mapped_equal": want == got,
                                  "ignored_only_before_mapped": sorted(set(want) - set(got))[:20], "ignored_only_after": sorted(set(got) - set(want))[:20],
                                  "untracked_total_before": before["untracked_total"], "untracked_total_after": len(untracked),
                                  "files_on_disk_under_old_roots": {o: len(disk_files(o)) for o in OLD if os.path.exists(os.path.join(ROOT, o))}}
    js, md, rows = path_map_files(c)
    rep["7_path_map"] = {"rows": len(rows), "r100": kinds["R100"], "regenerated_identical_json": open(os.path.join(ROOT, "PATH_MAP.json"), encoding="utf-8").read() == js,
                         "regenerated_identical_md": open(os.path.join(ROOT, "PATH_MAP.md"), encoding="utf-8").read() == md}
    bound = sorted({b["target"] for b in bs if b["kind"] == "file" and b["status"] == "ok"})
    d2 = z(git("diff", "--name-only", "-z", c, head))
    base = git("rev-parse", f"{c}~1").strip()
    prot = z(git("diff", "--name-only", "-z", base, head, "--", PROTECTED_PREFIX, *PROTECTED_FILES))
    rep["8_bound_files_changed_after_rename"] = {"bound_files": len(bound), "changed_in_later_commits": sorted(set(d2) & set(bound)),
                                                 "protected_changed_since_before_rename": prot, "files_changed_after_rename": sorted(d2)}
    hits = z(git("grep", "-l", "-z", "-E", "(^|[^A-Za-z0-9_.-])(" + "|".join(sorted(set(ALL_OLD), key=len, reverse=True)) + ")/", check=False))
    protected_hits = sorted(p for p in hits if p.startswith(PROTECTED_PREFIX) or p in PROTECTED_FILES)
    unb = sorted(set(hits) - set(bound) - {"PATH_MAP.md", "PATH_MAP.json"} - HISTORY_FILES - set(protected_hits))
    unb_md = [p for p in unb if p.endswith(".md")]
    rep["9_old_names_in_unbound_files"] = {"definition": "unbound .md files: 0 hits required; every other unbound file keeps the paths it recorded and is covered by PATH_MAP.md and the volume tags",
                                          "pass": not unb_md, "unbound_md": unb_md, "hits_total": len(hits), "in_bound_files": len(set(hits) & set(bound)),
                                          "in_protected_files": protected_hits, "unbound_other_covered_by_path_map": len(unb) - len(unb_md),
                                          "unbound_by_extension": dict(collections.Counter(posixpath.splitext(p)[1] or posixpath.basename(p) for p in unb)), "unbound_list": unb}
    gate = old_dirs_on_disk()
    rep["old_directory_gate"] = {"rule": f"after the rename no directory named {', '.join(ALL_OLD)} may exist on disk at the repository root (tracked, ignored or untracked content alike)",
                                 "present": gate, "pass": not gate}
    rep["10_tags_and_remote"] = {"local_tags": git("tag", "-l").split(), "remote_tags": sorted(set(l.split("\t")[1].replace("^{}", "") for l in git("ls-remote", "--tags", "origin", check=False).splitlines() if "\t" in l)),
                                 "main_equals_origin_main": (git("rev-parse", "--verify", "-q", "refs/heads/main", check=False).strip() or None,
                                                             git("rev-parse", "--verify", "-q", "refs/remotes/origin/main", check=False).strip() or None),
                                 "branch_upstream": subprocess.run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "@{u}"], capture_output=True, text=True).returncode == 0}
    cross = []
    for p in sorted(x for x in tracked if x.endswith(".py") and any(x.startswith(n + "/") for n in NEW)):
        s = open(os.path.join(ROOT, p), encoding="utf-8", errors="replace").read()
        mods = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_0-9]+)", s, re.M))
        for m in sorted(mods):
            hits_ = [t for t in tracked if t.endswith(f"/scripts/{m}.py") and any(t.startswith(n + "/") for n in NEW)]
            for t in hits_:
                if t.split("/")[0] != p.split("/")[0]:
                    cross.append({"from": p, "imports": t})
    rep["cross_volume_imports"] = cross
    json.dump(rep, open(a.report, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk not in ("unbound_list", "files_changed_after_rename")}) for k, v in rep.items() if k != "cross_volume_imports"}, indent=1, ensure_ascii=False)[:6000])
    print("cross-volume imports:", len(cross))
    if gate:
        print(f"OLD DIRECTORY GATE FAILED: {gate}")
        return 3
    return 0 if rep["9_old_names_in_unbound_files"]["pass"] and rep["1_rename_commit_pure_moves"]["pass"] else 1


def old_dirs_on_disk():
    """Old root names of every generation that exist on disk (as a file or a directory, whatever is inside)."""
    return {o: len(disk_files(o)) if os.path.isdir(os.path.join(ROOT, o)) else "file" for o in ALL_OLD if os.path.lexists(os.path.join(ROOT, o))}


def phase_check_old_dirs():
    g = old_dirs_on_disk()
    print(json.dumps({"old_directories_on_disk": g, "pass": not g}))
    return 3 if g else 0


def phase_pathmap():
    """Regenerate PATH_MAP.json / PATH_MAP.md from the rename commit (no commit)."""
    js, md, rows = path_map_files(rename_commit())
    open(os.path.join(ROOT, "PATH_MAP.json"), "w", encoding="utf-8", newline="\n").write(js)
    open(os.path.join(ROOT, "PATH_MAP.md"), "w", encoding="utf-8", newline="\n").write(md)
    print("PATH_MAP rows of this generation", len(rows), "· generation", GEN)
    return 0


def phase_tags(a):
    made = []
    for spec in a.target:
        name, rev = spec.split("=", 1)
        if subprocess.run(["git", "-C", ROOT, "rev-parse", "-q", "--verify", f"refs/tags/{name}"], capture_output=True).returncode == 0:
            made.append({name: "exists, left as it is"}); continue
        vol = MAP["tags"]["new"][name]
        git("tag", "-a", name, rev, "-m", f"{vol}: " + MAP.get("tag_message", "the last commit before the directory rename that holds this volume's runs at the paths their pre-registrations name"))
        made.append({name: git("rev-parse", f"{name}^{{}}").strip()})
    print(json.dumps(made, indent=1))
    return 0


def phase_move_untracked():
    if any(p for p in z(git("ls-files", "-z")) if under_old(p)):
        sys.exit("refused: tracked files are still under an old root (HEAD does not hold the rename)")
    tracked, ignored, untracked = environment()
    mv_i = [p for p in ignored if under_old(p)]; mv_u = [p for p in untracked if under_old(p)]
    clash = [map_path(p) for p in mv_i + mv_u if os.path.exists(os.path.join(ROOT, map_path(p)))]
    if clash:
        sys.exit(f"refused: {len(clash)} destinations exist already, e.g. {clash[:3]}")
    failed = []
    for p in mv_i + mv_u:
        src, dst = os.path.join(ROOT, p), os.path.join(ROOT, map_path(p))
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True); os.replace(src, dst)
        except OSError as e:
            failed.append({"path": p, "error": str(e)})
    for o in OLD:
        for dp, dn, fn in sorted(os.walk(os.path.join(ROOT, o)), key=lambda x: -len(x[0])):
            if not fn and not os.listdir(dp):
                os.rmdir(dp)
    t2, i2, u2 = environment()
    want = sorted(map_path(p) for p in mv_i); got = sorted(p for p in i2 if p in set(want))
    print(json.dumps({"ignored_moved": len(mv_i), "untracked_moved": len(mv_u), "failures": failed, "ignored_mapped_all_still_ignored": want == got,
                      "untracked_total_before_after": [len(untracked), len(u2)],
                      "files_left_under_old_roots": {o: len(disk_files(o)) for o in OLD if os.path.exists(os.path.join(ROOT, o))}}, indent=1))
    return 0 if not failed and want == got else 1


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("phase", choices=["rename", "docs", "verify", "tags", "move-untracked", "check-old-dirs", "pathmap"])
    ap.add_argument("--report"); ap.add_argument("--clones", action="store_true"); ap.add_argument("--no-commit", action="store_true"); ap.add_argument("--target", action="append", default=[])
    ap.add_argument("--gen", type=int)   # read at import time (module constants); declared here so argparse accepts it
    a = ap.parse_args()
    return {"rename": phase_rename, "docs": phase_docs, "verify": lambda: phase_verify(a), "tags": lambda: phase_tags(a), "move-untracked": phase_move_untracked,
            "check-old-dirs": phase_check_old_dirs, "pathmap": phase_pathmap}[a.phase]()


if __name__ == "__main__":
    raise SystemExit(main())
