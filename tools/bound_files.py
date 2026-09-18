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

usage: bound_files.py            report classes, counts and every binding
       bound_files.py --attributes   print `<path> -text` for every resolved bound file (for .gitattributes)
"""
import glob, hashlib, json, os, re, sys

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


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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
