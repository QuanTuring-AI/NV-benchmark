#!/usr/bin/env python3
"""Enumerate every SHA-256 binding in this repository and, on request, print the .gitattributes lines that keep the
bound files stored byte for byte.

A binding is any place where a frozen pre-registration (prediction*.json) or a .sha256 sidecar records a digest.
Enumeration does not use a list of known key names: every JSON key whose name contains "sha256" (any case, any
depth) is a binding class, and each class is reported with its count so that a class that was never walked is
visible as absent rather than as a pass.

  dict value                         each entry  path -> 64-hex digest  binds that path
  64-hex string, sibling "file"      binds the named file
  64-hex string, sibling "text"      binds the text itself (verified against the text, no file)
  64-hex string, no path             recorded as opaque: counted, cannot be verified here
  "<path> sha256 <hex>" in a string  binds that path
  *.sha256 sidecar                   each "<hex> *<name>" line binds that name

Resolution of a bound name, in this order (the first rule that yields exactly one file wins):
  1. the name as given, from the repository root
  2. the name relative to each ancestor directory of the binding file, nearest first
  3. a unique file of that name anywhere below the nearest ancestor directory that has one (a pre-registration in
     C/ may name a file kept in the sibling directory calibration/)
No match -> unresolved. More than one match under rule 3 -> ambiguous; both are reported, never skipped.

History-anchored mode (--history; added 2026-09-28, when the volume directories were renamed). The default mode
resolves a bound name in today's working tree, so a file that has only moved no longer resolves. The history mode
resolves every binding in the commit whose tree holds its pre-registration's or sidecar's current bytes (the latest
commit that added or changed that file, following renames and skipping pure renames), with the same three rules applied
to that commit's tree, and hashes that commit's blob. A binding therefore verifies the file as it stood beside the
pre-registration, whatever the directories are called today. (Why not the first commit that added the pre-registration:
some bound files entered history with their line endings converted and were restored byte for byte in a later commit
together with their pre-registrations; `--anchor first-add` reports that variant.) When the anchor commit's blob does not
match, the later commits on the same file's history are searched, oldest first; a match is reported as ok_later with
the commit that holds the bound bytes, one by one and never merged into ok. No match anywhere is a mismatch.
For each resolved binding it then reports two more facts: whether the file at its current path (the anchored path carried through every later rename) is the same blob, and whether the bytes on disk
at that path hash to the digest (this is where .gitattributes matters). Only tracked files are enumerated.

usage: bound_files.py                report classes, counts and every binding (today's working tree)
       bound_files.py --attributes   print `<path> -text` for every resolved bound file (for .gitattributes)
       bound_files.py --history [--attributes] [--anchor first-add]   the same, history-anchored; --attributes prints
                                                 current paths
       bound_files.py --self-test-history        planted controls in a throw-away repository: a renamed path must
                                                 resolve, a wrong digest must fail
"""
import glob, hashlib, json, os, re, subprocess, sys, tempfile

HEX = re.compile(r"^[0-9a-f]{64}$")
INLINE = re.compile(r"([\w][\w./-]*\.(?:json|jsonl|py|sh|ps1|txt|yml|yaml|md)) sha256 ([0-9a-f]{64})")
SKIP_DIRS = (".git", "_internal")


def sha_of_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_of_path(path):
    """Binary read, so line endings are hashed as stored; never goes through a text-mode layer."""
    with open(path, "rb") as f:
        return sha_of_bytes(f.read())


def _norm(p):
    return p.replace(os.sep, "/")


def walk_json(obj, source):
    """Yield bindings found in one parsed JSON document. `source` is the path of that document (for resolution)."""
    def rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if "sha256" in k.lower():
                    if isinstance(v, dict):
                        for name, dg in v.items():
                            if isinstance(dg, str) and HEX.match(dg):
                                yield {"kind": "file", "source": source, "class": k, "name": name, "digest": dg}
                    elif isinstance(v, str) and HEX.match(v):
                        if isinstance(o.get("file"), str):
                            yield {"kind": "file", "source": source, "class": k, "name": o["file"], "digest": v}
                        elif isinstance(o.get("text"), str):
                            yield {"kind": "text", "source": source, "class": k, "name": "<text>", "digest": v,
                                   "text": o["text"]}
                        else:
                            yield {"kind": "opaque", "source": source, "class": k, "name": "<none>", "digest": v}
                elif isinstance(v, str):
                    for m in INLINE.finditer(v):
                        yield {"kind": "file", "source": source, "class": f"inline:{k}", "name": m.group(1),
                               "digest": m.group(2)}
                yield from rec(v)
        elif isinstance(o, list):
            for x in o:
                yield from rec(x)
    yield from rec(obj)


def walk_sidecar(text, source):
    for m in re.finditer(r"([0-9a-f]{64})\s+\*?(\S+)", text):
        yield {"kind": "file", "source": source, "class": "sidecar", "name": m.group(2), "digest": m.group(1)}


def resolve(root, binder, name):
    """Return (status, target): status in ok / unresolved / ambiguous."""
    name = _norm(name)
    c = os.path.join(root, name)
    if os.path.isfile(c):
        return "ok", name
    d = _norm(os.path.dirname(binder))
    ancestors = []
    while d:
        ancestors.append(d)
        d = os.path.dirname(d)
    for a in ancestors:
        c = f"{a}/{name}"
        if os.path.isfile(os.path.join(root, c)):
            return "ok", c
    for a in ancestors:
        hits = [_norm(h) for h in glob.glob(os.path.join(root, a, "**", name), recursive=True)
                if os.path.isfile(h) and not any(s in _norm(h).split("/") for s in SKIP_DIRS)]
        hits = sorted(set(os.path.relpath(h, root).replace(os.sep, "/") for h in hits))
        if len(hits) == 1:
            return "ok", hits[0]
        if len(hits) > 1:
            return "ambiguous", hits
    return "unresolved", None


def enumerate_bindings(root="."):
    out = []
    for pf in sorted(glob.glob(os.path.join(root, "**", "prediction*.json"), recursive=True)):
        rel = _norm(os.path.relpath(pf, root))
        if any(s in rel.split("/") for s in SKIP_DIRS):
            continue
        try:
            doc = json.load(open(pf, encoding="utf-8-sig"))
        except Exception as e:
            out.append({"kind": "unreadable", "source": rel, "class": "-", "name": str(e), "digest": ""})
            continue
        out.extend(walk_json(doc, rel))
    for sc in sorted(glob.glob(os.path.join(root, "**", "*.sha256"), recursive=True)):
        rel = _norm(os.path.relpath(sc, root))
        if any(s in rel.split("/") for s in SKIP_DIRS):
            continue
        out.extend(walk_sidecar(open(sc, encoding="utf-8").read(), rel))
    for b in out:
        if b["kind"] == "file":
            b["status"], b["target"] = resolve(root, b["source"], b["name"])
    return out


def class_counts(bindings):
    c = {}
    for b in bindings:
        c[b["class"]] = c.get(b["class"], 0) + 1
    return dict(sorted(c.items()))


def attribute_lines(bindings):
    targets = sorted({b["target"] for b in bindings if b["kind"] == "file" and b["status"] == "ok"})
    return [f"{t} -text" for t in targets]


# --- history-anchored mode ------------------------------------------------------------------------------------------

def _git(root, *args):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


class History:
    """Read-only access to one repository's history, cached per commit."""
    def __init__(self, root, rev="HEAD"):
        self.root, self.rev = root, _git(root, "rev-parse", rev).decode().strip()
        self._trees, self._fwd = {}, {}

    def tree(self, commit):
        if commit not in self._trees:
            out = _git(self.root, "-c", "core.quotepath=off", "ls-tree", "-r", "-z", "--name-only", commit)
            self._trees[commit] = set(x for x in out.decode("utf-8").split("\0") if x)
        return self._trees[commit]

    def blob(self, commit, path):
        r = subprocess.run(["git", "-C", self.root, "cat-file", "blob", f"{commit}:{path}"], capture_output=True)
        return r.stdout if r.returncode == 0 else None

    def blob_id(self, commit, path):
        r = subprocess.run(["git", "-C", self.root, "rev-parse", "--verify", "-q", f"{commit}:{path}"], capture_output=True)
        return r.stdout.decode().strip() if r.returncode == 0 else None

    def anchor(self, path, rule="current-bytes"):
        """(commit, path at that commit, number of commits that added it). rule current-bytes: the latest commit that
        added or changed the content of `path` (pure renames excluded), i.e. the commit whose tree holds the binder's
        current bytes. rule first-add: the first commit that added it. Both follow renames."""
        out = _git(self.root, "-c", "core.quotepath=off", "log", "--follow", "--diff-filter=AM", "--name-status", "--format=@%H",
                   self.rev, "--", path).decode("utf-8")
        hits, cur = [], None
        for line in out.splitlines():
            if line.startswith("@"):
                cur = line[1:]
            elif line[:2] in ("A\t", "M\t") and cur:
                hits.append((cur, line[2:], line[0]))
        adds = [x for x in hits if x[2] == "A"]
        if not hits:
            return None, None, 0
        c, p, _ = hits[0] if rule == "current-bytes" else (adds[-1] if adds else hits[-1])
        return c, p, len(adds)

    def later_match(self, commit, current_path, digest):
        """(commit, path) of the oldest commit after `commit` on the same file's history (following renames back from
        its current path) whose blob hashes to `digest`; None if there is none."""
        out = _git(self.root, "-c", "core.quotepath=off", "log", "--follow", "--name-status", "--format=@%H", self.rev, "--", current_path).decode("utf-8")
        seq, cur = [], None
        for line in out.splitlines():
            if line.startswith("@"):
                cur = line[1:]
            elif line and cur and line[0] in "AMR":
                seq.append((cur, line.split("\t")[-1]))
        for c, p in reversed(seq):   # oldest first
            if c == commit or subprocess.run(["git", "-C", self.root, "merge-base", "--is-ancestor", commit, c]).returncode != 0:
                continue
            data = self.blob(c, p)
            if data is not None and sha_of_bytes(data) == digest:
                return c, p
        return None

    def forward(self, commit, path):
        """The path of `commit:path` at self.rev, carried through every rename after `commit` (oldest first)."""
        if commit not in self._fwd:
            out = _git(self.root, "-c", "core.quotepath=off", "log", "--reverse", "-M", "--diff-filter=R", "--name-status", "--format=@%H",
                       f"{commit}..{self.rev}").decode("utf-8")
            self._fwd[commit] = [tuple(l.split("\t")[1:3]) for l in out.splitlines() if l.startswith("R")]
        for old, new in self._fwd[commit]:
            if path == old:
                path = new
        return path


def resolve_in(paths, binder, name):
    """The three resolution rules of `resolve`, applied to a set of tracked paths instead of the working tree."""
    name = _norm(name)
    if name in paths:
        return "ok", name
    d = _norm(os.path.dirname(binder)); ancestors = []
    while d:
        ancestors.append(d); d = os.path.dirname(d)
    for a in ancestors:
        if f"{a}/{name}" in paths:
            return "ok", f"{a}/{name}"
    for a in ancestors:
        pre = a + "/"
        hits = sorted(p for p in paths if p.startswith(pre) and (p[len(pre):] == name or p[len(pre):].endswith("/" + name))
                      and not any(s in p.split("/") for s in SKIP_DIRS))
        if len(hits) == 1:
            return "ok", hits[0]
        if len(hits) > 1:
            return "ambiguous", hits
    return "unresolved", None


def enumerate_bindings_history(root=".", rev="HEAD", rule="current-bytes"):
    """Bindings of every tracked pre-registration and sidecar at `rev`, each resolved in its anchor commit."""
    h = History(root, rev)
    now = h.tree(h.rev); out = []
    for rel in sorted(now):
        base = rel.split("/")[-1]
        if any(s in rel.split("/") for s in SKIP_DIRS):
            continue
        if re.fullmatch(r"prediction.*\.json", base):
            try:
                doc = json.loads(h.blob(h.rev, rel).decode("utf-8-sig"))
            except Exception as e:
                out.append({"kind": "unreadable", "source": rel, "class": "-", "name": str(e), "digest": ""}); continue
            out.extend(walk_json(doc, rel))
        elif base.endswith(".sha256"):
            out.extend(walk_sidecar(h.blob(h.rev, rel).decode("utf-8"), rel))
    anchors = {}
    for b in out:
        if b["kind"] != "file":
            continue
        if b["source"] not in anchors:
            anchors[b["source"]] = h.anchor(b["source"], rule)
        c, src, n_adds = anchors[b["source"]]
        b.update(anchor_commit=c, anchor_source=src, anchor_adds=n_adds, anchor_rule=rule)
        if c is None:
            b["status"], b["target"], b["anchor_target"] = "unresolved", None, None; continue
        st, tgt = resolve_in(h.tree(c), src, b["name"])
        b["status"], b["anchor_target"] = st, tgt
        b["target"] = h.forward(c, tgt) if st == "ok" else None
    return out, h


def verify_history(bindings, h, disk_root=None):
    """ok / mismatch on the anchored blob; for resolved bindings also current blob = anchored blob, and the bytes on
    disk at the current path (when disk_root is a working tree of h.rev)."""
    v = {k: [] for k in ("ok", "ok_later", "mismatch", "unresolved", "ambiguous", "text_ok", "text_bad", "opaque", "unreadable",
                         "current_same", "current_differs", "current_missing", "disk_ok", "disk_mismatch", "disk_missing")}
    for b in bindings:
        k = b["kind"]
        if k == "text":
            (v["text_ok"] if sha_of_bytes(b["text"].encode("utf-8")) == b["digest"] else v["text_bad"]).append(b); continue
        if k in ("opaque", "unreadable"):
            v[k].append(b); continue
        if b["status"] != "ok":
            v[b["status"]].append(b); continue
        data = h.blob(b["anchor_commit"], b["anchor_target"])
        a_id = h.blob_id(b["anchor_commit"], b["anchor_target"])
        if data is not None and sha_of_bytes(data) == b["digest"]:
            v["ok"].append(b)
        else:
            later = h.later_match(b["anchor_commit"], b["target"], b["digest"])
            if later:
                b["verified_at"] = later; v["ok_later"].append(b)
                a_id = h.blob_id(*later)
            else:
                v["mismatch"].append(b)
        c_id = h.blob_id(h.rev, b["target"])
        v["current_missing" if c_id is None else "current_same" if c_id == a_id else "current_differs"].append(b)
        if disk_root:
            p = os.path.join(disk_root, b["target"])
            if not os.path.isfile(p):
                v["disk_missing"].append(b)
            else:
                v["disk_ok" if sha_of_path(p) == b["digest"] else "disk_mismatch"].append(b)
    return v


def self_test_history():
    """A throw-away repository: a pre-registration binds a/data.txt (right digest), a/other.txt (wrong digest) and
    a/fixed.txt (digest of bytes committed only after the freeze, as a line-ending repair would); then `git mv a b`.
    History mode must resolve all three to b/, verify data.txt at the anchor, fixed.txt later (naming the repair commit)
    and fail other.txt; today's-tree mode must leave all three unresolved (the reason this mode exists)."""
    with tempfile.TemporaryDirectory() as t:
        g = lambda *a: _git(t, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *a)
        g("init", "-q")
        os.makedirs(os.path.join(t, "a", "pred"))
        open(os.path.join(t, "a", "data.txt"), "wb").write(b"hello\n")
        open(os.path.join(t, "a", "other.txt"), "wb").write(b"other\n")
        open(os.path.join(t, "a", "fixed.txt"), "wb").write(b"lf\n")
        doc = {"harness_sha256": {"a/data.txt": sha_of_bytes(b"hello\n"), "a/other.txt": "0" * 64, "a/fixed.txt": sha_of_bytes(b"lf\r\n")}}
        open(os.path.join(t, "a", "pred", "prediction_x.json"), "w", encoding="utf-8", newline="\n").write(json.dumps(doc))
        g("add", "-A"); g("commit", "-q", "-m", "freeze")
        open(os.path.join(t, "a", "fixed.txt"), "wb").write(b"lf\r\n")
        g("add", "a/fixed.txt"); g("commit", "-q", "-m", "restore bytes")
        restored = _git(t, "rev-parse", "HEAD").decode().strip()
        g("mv", "a", "b"); g("commit", "-q", "-m", "rename")
        bs, h = enumerate_bindings_history(t)
        v = verify_history(bs, h, t)
        today = enumerate_bindings(t)
        got = {"renamed path resolves in its anchor commit": [b["target"] for b in v["ok"]] == ["b/data.txt"],
               "bytes restored after the freeze -> ok_later, with that commit": [b["target"] for b in v["ok_later"]] == ["b/fixed.txt"]
               and v["ok_later"][0]["verified_at"] == (restored, "a/fixed.txt"),
               "wrong digest fails": [b["target"] for b in v["mismatch"]] == ["b/other.txt"],
               "current blob = verified blob for all three": len(v["current_same"]) == 3,
               "disk bytes verify for the right digests only": sorted(b["target"] for b in v["disk_ok"]) == ["b/data.txt", "b/fixed.txt"],
               "today's-tree mode leaves all three unresolved": sorted(b["status"] for b in today if b["kind"] == "file") == ["unresolved"] * 3}
    for k, ok in got.items():
        print(("PASS " if ok else "FAIL ") + k)
    return 0 if all(got.values()) else 1


def main_history(root):
    rule = "first-add" if "first-add" in sys.argv else "current-bytes"
    bs, h = enumerate_bindings_history(root, rule=rule)
    v = verify_history(bs, h, root)
    if "--attributes" in sys.argv:
        print("\n".join(f"{t} -text" for t in sorted({b["target"] for b in bs if b["kind"] == "file" and b["status"] == "ok"})))
        return 0
    print(f"BINDINGS enumerated {len(bs)} · classes {class_counts(bs)} · rev {h.rev[:12]} · history-anchored, anchor rule {rule}")
    print("anchored blob: " + " · ".join(f"{k} {len(v[k])}" for k in ("ok", "ok_later", "mismatch", "unresolved", "ambiguous", "text_ok", "text_bad", "opaque", "unreadable")))
    later = {}
    for b in v["ok_later"]:
        later[b["verified_at"][0]] = later.get(b["verified_at"][0], 0) + 1
    print("ok_later by the commit that holds the bound bytes:", {c[:12]: n for c, n in sorted(later.items())})
    print("current path blob = anchored blob: " + " · ".join(f"{k.split('_')[1]} {len(v[k])}" for k in ("current_same", "current_differs", "current_missing")))
    print("disk bytes at current path = digest: " + " · ".join(f"{k.split('_')[1]} {len(v[k])}" for k in ("disk_ok", "disk_mismatch", "disk_missing")))
    print("anchor commits:", len({b.get("anchor_commit") for b in bs if b.get("anchor_commit")}),
          "· binders added more than once:", sorted({b["source"] for b in bs if b.get("anchor_adds", 0) > 1}))
    for key in ("ok_later", "mismatch", "unresolved", "ambiguous", "text_bad", "unreadable", "current_differs", "current_missing", "disk_mismatch", "disk_missing"):
        for b in v[key]:
            print(f"  {key}: {b['source']} [{b['class']}] {b['name']} -> anchor {str(b.get('anchor_commit'))[:12]}:{b.get('anchor_target')} -> now {b.get('target')}")
    return 0


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "--self-test-history" in sys.argv:
        return self_test_history()
    if "--history" in sys.argv:
        return main_history(root)
    bs = enumerate_bindings(root)
    if "--attributes" in sys.argv:
        print("\n".join(attribute_lines(bs)))
        return 0
    print("binding classes:", class_counts(bs))
    kinds = {}
    for b in bs:
        kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
    print("kinds:", kinds, "· file bindings by status:",
          {s: sum(1 for b in bs if b["kind"] == "file" and b["status"] == s) for s in ("ok", "unresolved", "ambiguous")})
    for b in bs:
        if b["kind"] == "file" and b["status"] != "ok":
            print(f"  {b['status']}: {b['source']} [{b['class']}] {b['name']} -> {b.get('target')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
