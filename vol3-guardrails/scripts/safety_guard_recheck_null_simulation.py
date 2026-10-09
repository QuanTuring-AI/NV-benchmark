#!/usr/bin/env python3
"""Vol.3 · before the freeze of the second look: how often would its criteria fail if M were nothing but one more run
of the upstream server?

Model (stated so that it can be argued with): a run gives each item its usual verdict, except that with a small
probability q the verdict comes out the other way, independently per item and per run. q is taken from two real runs of
the upstream arm on two nights (J6-today of 2026-10-06 and J6-tonight of 2026-10-08): the share of Aegis items on which
they differ is d, and two runs that each flip with probability q differ on about 2q of the items, so q = d / 2, per
track. The usual verdict of an item is J6-tonight's.
A simulated session draws three runs (U1, M, U2) from that model and applies the criteria as the summary program does:
C1 with the allowance T = max(D_hist, |U1 - U2|) and D_hist as fixed in the pre-registration, C2 with McNemar's exact
test on the Aegis items, and the sanity check of U1 against U2. C3 is not simulated (its limit is far from q).
What is reported: the share of sessions in which each fails although nothing differs between the servers.
This is a model, not a measurement; its one input from data is d.

usage: safety_guard_recheck_null_simulation.py OUT.json [--sessions 20000] [--seed 20261008]
"""
import json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import safety_guard_recheck_summary as SM  # noqa: E402
from p93_common import RESULTS as P93_RESULTS, read_jsonl  # noqa: E402


def main():
    out_path = sys.argv[1]
    n_s = int(sys.argv[sys.argv.index("--sessions") + 1]) if "--sessions" in sys.argv else 20000
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 20261008
    rng = np.random.default_rng(seed); alpha4 = 0.05 / 4
    items = {it["item_id"]: it for it in read_jsonl(os.path.join(P93_RESULTS, "items.jsonl"))}
    D = SM.d_hist()["rates"]; rec = {"what": "how often the criteria of the second look fail when M is one more run of the upstream server, under the stated model", "sessions": n_s, "seed": seed, "per_track": {}}
    c1_ok = np.ones(n_s, bool); c2_ok = np.ones(n_s, bool); sanity_ok = np.ones(n_s, bool)
    for t, gold in (("input", "gold_input"), ("output", "gold_output")):
        A = SM.verdicts(os.path.join(VOL, "results", "model_free_nim", "J6-tonight", f"{t}_c16.jsonl")); B = SM.verdicts(os.path.join(VOL, "results", "safety_guard_nim", "J6-today", f"{t}_c16.jsonl"))
        ids = sorted(i for i in A if i in B and items[i]["dataset"] == "aegis2")
        d = sum(1 for i in ids if A[i] != B[i]) / len(ids); q = d / 2
        base = np.array([A[i] == "unsafe" for i in ids]); harmful = np.array([items[i][gold] == "unsafe" for i in ids])
        runs = {}
        for name in ("U1", "M", "U2"):
            flip = rng.random((n_s, len(ids))) < q
            runs[name] = base[None, :] ^ flip
        for kind, mask in (("detection", harmful), ("false_alarm", ~harmful)):
            r = {name: v[:, mask].mean(axis=1) for name, v in runs.items()}
            T = np.maximum(D[f"{t}.{kind}"]["D_hist"], np.abs(r["U1"] - r["U2"]))
            ok = np.abs(r["M"] - (r["U1"] + r["U2"]) / 2) <= T + 1e-12
            rec["per_track"].setdefault(t, {})[f"C1_{kind}_fails"] = float(1 - ok.mean()); c1_ok &= ok
        ptab = {}

        def p_of(b, c):
            key = (int(b), int(c))
            if key not in ptab:
                ptab[key] = SM.binom_two_sided(*key)
            return ptab[key]

        for u in ("U1", "U2"):
            b = (runs["M"] & ~runs[u]).sum(axis=1); c = (~runs["M"] & runs[u]).sum(axis=1)
            c2_ok &= np.array([p_of(x, y) >= alpha4 for x, y in zip(b, c)])
        b = (runs["U1"] & ~runs["U2"]).sum(axis=1); c = (~runs["U1"] & runs["U2"]).sum(axis=1)
        sanity_ok &= np.array([p_of(x, y) >= alpha4 for x, y in zip(b, c)])
        rec["per_track"][t].update({"aegis2_items": len(ids), "share_on_which_the_two_real_runs_differ": d, "q": q})
    rec["share_of_sessions"] = {"C1_fails": float(1 - c1_ok.mean()), "C2_fails": float(1 - c2_ok.mean()), "sanity_test_fails": float(1 - sanity_ok.mean()), "C1_or_C2_fails": float(1 - (c1_ok & c2_ok).mean())}
    json.dump(rec, open(out_path, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"q": {t: rec["per_track"][t]["q"] for t in rec["per_track"]}, **rec["share_of_sessions"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
