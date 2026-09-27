#!/usr/bin/env python3
"""No-overwrite gate: a new run may add files only under its own results directory.

snapshot(root, allowed) records, before the run: the tracked files that already differ from HEAD (with the sha256 of their
bytes on disk), and every untracked or ignored file under the repository's result and script directories with its size
and modification time. check(snap) compares the working tree with it after each cell:
  - a tracked file that did not differ before and differs now, or one that differed and whose bytes changed -> violation
  - an untracked or ignored file outside the allowed prefixes that is new, gone, or has a new size or mtime -> violation
Files under the allowed prefixes are free to appear and change. A violation makes the caller stop (exit != 0) and void the
cell. Only standard git plumbing is used; nothing is written to the repository.
"""
import hashlib, os, subprocess

SCOPES = ["benchmark", "roadmap-e456", "tools", "scripts", "vol1a-revisit", "vol1b", "vol2", "vol1-nim", "vol2-guardrails", "vol3-nemotron"]


def _git(root, *a):
    return subprocess.run(["git", "-C", root, "-c", "core.quotepath=off", *a], capture_output=True).stdout.decode("utf-8")


def _z(s):
    return [x for x in s.split("\0") if x]


def _modified(root):
    out = {}
    for p in _z(_git(root, "diff", "--name-only", "-z", "HEAD")):
        f = os.path.join(root, p)
        out[p] = hashlib.sha256(open(f, "rb").read()).hexdigest() if os.path.isfile(f) else None
    return out


def _others(root):
    scopes = [s for s in SCOPES if os.path.exists(os.path.join(root, s))]
    paths = set(_z(_git(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *scopes)))
    paths |= set(_z(_git(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", *scopes)))
    out = {}
    for p in paths:
        try:
            s = os.stat(os.path.join(root, p)); out[p] = [s.st_size, int(s.st_mtime)]
        except OSError:
            pass
    return out


def snapshot(root, allowed):
    return {"root": root, "allowed": [a.rstrip("/") + "/" for a in allowed], "modified": _modified(root), "others": _others(root)}


def check(snap):
    root, allowed = snap["root"], snap["allowed"]
    ok = lambda p: any(p.startswith(a) for a in allowed)
    v = []
    now_mod = _modified(root)
    for p, h in now_mod.items():
        if p not in snap["modified"]:
            v.append({"path": p, "what": "tracked file now differs from HEAD"})
        elif snap["modified"][p] != h:
            v.append({"path": p, "what": "tracked file's bytes changed during the run"})
    now = _others(root)
    for p in set(now) | set(snap["others"]):
        if ok(p):
            continue
        a, b = snap["others"].get(p), now.get(p)
        if a is None:
            v.append({"path": p, "what": "new file outside the allowed directory"})
        elif b is None:
            v.append({"path": p, "what": "file removed"})
        elif a != b:
            v.append({"path": p, "what": "size or mtime changed"})
    return {"violations": v[:50], "violation_count": len(v), "pass": not v,
            "tracked_differing_before": len(snap["modified"]), "untracked_or_ignored_watched": len(snap["others"])}
