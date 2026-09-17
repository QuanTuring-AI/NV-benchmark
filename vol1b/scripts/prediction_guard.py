#!/usr/bin/env python3
"""Checks every pre-registration generator must run before it writes a file that will be frozen.

Why this exists: two pre-registrations (P17 C/S/R and P28 v1) stored the NIM profile as the display line that
`list-model-profiles` prints -- the 64-hex id followed by " (vllm-bf16-tp1-pp1)". Each generator was written by hand
and pasted that line as a literal; nothing checked it. P28's runner passed the value to NIM verbatim and NIM refused
it as "no matching profile ... in manifest". A check in the runner only stops the run; a check here stops the value
from being frozen in the first place.

In a generator:
    from prediction_guard import check_prediction
    check_prediction(p)          # raises ValueError before anything is written

From the shell, to audit files already frozen (reports, never modifies):
    python vol1b/scripts/prediction_guard.py <prediction.json> ...
"""
import json, re, sys

HEX64 = re.compile(r"[0-9a-f]{64}")


def _stack_profiles(p):
    out = []
    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "profile" and isinstance(v, str):
                    out.append((path + "." + k, v))
                walk(v, path + "." + k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
    walk(p, "")
    return out


def problems(p):
    bad = []
    for path, v in _stack_profiles(p):
        # a profile field is either a NIM profile id (must be bare 64-hex) or a named experiment profile such as "C";
        # anything that starts with 64 hex characters is meant as an id and must be exactly that
        if v[:64] and HEX64.fullmatch(v[:64]) and not HEX64.fullmatch(v):
            bad.append(f"{path}: profile id carries extra characters (len {len(v)}): {v!r}")
    return bad


def check_prediction(p):
    bad = problems(p)
    if bad:
        raise ValueError("pre-registration refused: " + "; ".join(bad))
    return True


def _self_test():
    ok = check_prediction({"stack": {"profile": "0" * 64}})
    try:
        check_prediction({"stack": {"profile": "0" * 64 + " (vllm-bf16-tp1-pp1)"}})
        return False
    except ValueError:
        pass
    return ok and not problems({"shape": {"profile": "C"}})


if __name__ == "__main__":
    if not _self_test():
        print("SELF-TEST FAILED"); raise SystemExit(2)
    rc = 0
    for f in sys.argv[1:]:
        b = problems(json.load(open(f, encoding="utf-8")))
        print(("BAD  " if b else "ok   ") + f + ("" if not b else "  " + " | ".join(b)))
        rc |= bool(b)
    raise SystemExit(rc)
