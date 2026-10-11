#!/usr/bin/env python3
"""Vol.3 · Safety Guard 8B v3: how often two runs of one model give a different verdict on the same item.

Every run of this model that the volume holds is paired with every other, on each track's whole per-item file. Nothing
is judged here: there is no pass, no fail and no threshold. The table sets the pairs "one server against another" beside
the pairs "one server against itself, on another day or in another container", the only yardstick these files offer.

Agreement is counted as criterion C3 of the second look counts it (safety_guard_recheck_summary.agreement): over the
items present in both files, the share with the same verdict field. The direction of a pair is counted over the items
on which both runs gave a verdict.

Per-item files of two arms are read together here, for one model on different servers and days.

usage: safety_guard_agreement.py plan --stamp "$(date +%Y-%m-%dT%H:%M:%S%z)"    before the first computation
       safety_guard_agreement.py run                                              pairs.json and pairs.md, from the plan
SG_AGREE_VOL: the program's own tests point it at a folder of made-up arms.
"""
import argparse, hashlib, itertools, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import safety_guard_recheck_summary as K  # noqa: E402  (verdicts, agreement, mcnemar, flipped: used as they are)

VOL_DIR = os.environ.get("SG_AGREE_VOL") or os.path.dirname(HERE)
OUT = os.path.join(VOL_DIR, "results", "safety_guard_agreement")
PLAN = os.path.join(OUT, "plan.json")
TRACKS = ("input", "output"); TRACK_NAME = {"input": "prompts", "output": "responses"}

# arm -> (folder under the volume, day of the run, server, kind)
ARMS = {
    "J6":          ("results/p93_judges/J6", "2026-10-02", "upstream vLLM 0.20.2", "U"),
    "J6-today":    ("results/safety_guard_nim/J6-today", "2026-10-06", "upstream vLLM 0.20.2", "U"),
    "J6-tonight":  ("results/model_free_nim/J6-tonight", "2026-10-08, night", "upstream vLLM 0.20.2", "U"),
    "U1":          ("results/safety_guard_recheck/U1", "2026-10-08, day", "upstream vLLM 0.20.2", "U"),
    "U2":          ("results/safety_guard_recheck/U2", "2026-10-08, day", "upstream vLLM 0.20.2", "U"),
    "J6M":         ("results/model_free_nim/J6M", "2026-10-08, night", "the generic NIM 2.0.12", "N2"),
    "M":           ("results/safety_guard_recheck/M", "2026-10-08, day", "the generic NIM 2.0.12", "N2"),
    "J6N":         ("results/safety_guard_nim/J6N", "2026-10-06", "the model's own NIM 1.14.0", "N1"),
    "J6N-tonight": ("results/model_free_nim/J6N-tonight", "2026-10-08, night", "the model's own NIM 1.14.0", "N1"),
    "J6-v0271":    ("results/model_free_nim/J6-v0271", "2026-10-08, night", "upstream vLLM 0.27.1", "V027"),
    "J6-v010":     ("results/parser_and_engine_version/J6-v010", "2026-10-06", "upstream vLLM image v0.10.0", "V010"),
}
GROUPS = {"UU": "upstream vLLM 0.20.2 against upstream vLLM 0.20.2 (another day or another container)",
          "N2": "the generic NIM 2.0.12 against upstream vLLM 0.20.2",
          "N1": "the model's own NIM 1.14.0 against upstream vLLM 0.20.2",
          "other": "every other pair (a NIM against itself or the other NIM, another version of upstream vLLM)"}


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def group_of(ka, kb):
    if ka == kb == "U":
        return "UU"
    return {frozenset(("U", "N2")): "N2", frozenset(("U", "N1")): "N1"}.get(frozenset((ka, kb)), "other")


def plan(stamp):
    if os.path.exists(PLAN):
        sys.exit("refused: a plan exists")
    os.makedirs(OUT, exist_ok=True)
    P = {"what": "Llama 3.1 Nemotron Safety Guard 8B v3: item-by-item agreement of every pair of runs the volume holds. Descriptive: no pass, no fail, no threshold.",
         "written": stamp, "written_before": "the first computation of the pairs below, except the four named under already_seen",
         "arms": {a: {"folder": f, "day": d, "server": s, "kind": k} for a, (f, d, s, k) in ARMS.items()},
         "files": "per arm and track, the whole per-item file of the 16-concurrent cell: input_c16.jsonl (prompts) and output_c16.jsonl (responses)",
         "pairs": "every two of the arms, none left out; an arm whose file is missing is listed as missing and its pairs are not computed",
         "groups": GROUPS,
         "counted": {"agreement": "as criterion C3 of the second look: over the items present in both files, the share with the same verdict field",
                     "differing": "items present in both files minus those with the same verdict field",
                     "direction": "over the items on which both runs gave a verdict: unsafe only in the first, unsafe only in the second"},
         "reported": "every pair; per group and track the smallest and the largest share and the smallest and the largest number of differing items",
         "reading_decided_beforehand": {"N2's range on each track lies inside UU's or overlaps it": "the article says the NIM disagreed with upstream about as often as upstream disagreed with itself",
                                        "N2's whole range on a track lies below UU's smallest share": "the figures are given as they are, the track is named, and the article says so in other words",
                                        "an arm of N1 has no per-item file": "its pairs are listed as missing"},
         "already_seen": {"pairs": [["J6M", "J6-tonight"], ["M", "U1"], ["M", "U2"], ["U1", "U2"]],
                          "where": ["results/model_free_nim/criteria.json", "results/safety_guard_recheck/criteria.json"],
                          "note": "these four were computed as parts of two pre-registered cells; the other pairs had not been computed when this was written"},
         "program": {"file": "scripts/safety_guard_agreement.py", "sha256": sha(os.path.abspath(__file__))},
         "uses": {"file": "scripts/safety_guard_recheck_summary.py", "sha256": sha(K.__file__)}}
    open(PLAN, "w", encoding="utf-8", newline="\n").write(json.dumps(P, indent=1, ensure_ascii=False) + "\n")
    open(os.path.splitext(PLAN)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(PLAN)} *{os.path.basename(PLAN)}\n")
    print(json.dumps({"plan": PLAN, "sha256": sha(PLAN), "written": stamp}))


def one(A, B):
    ag = K.agreement(A, B); mc = K.mcnemar(A, B, sorted(set(A) & set(B)))
    return {"items_in_both": ag["items_in_both"], "items_only_in_one": ag["items_only_in_one"], "same_verdict": ag["same_verdict"], "differing": ag["items_in_both"] - ag["same_verdict"], "share": ag["share"],
            "unsafe_only_in_the_first": mc["unsafe_only_in_the_first"], "unsafe_only_in_the_second": mc["unsafe_only_in_the_second"], "without_a_verdict_on_one_side": mc["without_a_verdict_on_one_side"]}


def controls(A):
    """Checks on copies of one file with known changes. -> record with "pass"."""
    ids = sorted(A); same = one(A, A)
    fl, done = K.flipped(A, ids, 7); f = one(A, fl)
    short = {i: A[i] for i in ids[1:]}; s = one(A, short)
    out = {"a file against itself": {"differing": same["differing"], "share": same["share"], "expected": [0, 1.0]},
           "against a copy with 7 unsafe verdicts set to safe": {"differing": f["differing"], "unsafe_only_in_the_first": f["unsafe_only_in_the_first"], "unsafe_only_in_the_second": f["unsafe_only_in_the_second"], "expected": [7, 7, 0]},
           "against a copy without its first item": {"items_only_in_one": s["items_only_in_one"], "differing": s["differing"], "expected": [1, 0]}}
    out["pass"] = (same["differing"], same["share"]) == (0, 1.0) and (len(done), f["differing"], f["unsafe_only_in_the_first"], f["unsafe_only_in_the_second"]) == (7, 7, 7, 0) and (s["items_only_in_one"], s["differing"]) == (1, 0)
    return out


def pct(x):
    return f"{x * 100:.2f}"


def run():
    line = open(os.path.splitext(PLAN)[0] + ".sha256", encoding="utf-8").read().split()
    if line[0] != sha(PLAN):
        sys.exit("refused: plan.json does not match its .sha256")
    P = json.load(open(PLAN, encoding="utf-8"))
    if P["program"]["sha256"] != sha(os.path.abspath(__file__)) or P["uses"]["sha256"] != sha(K.__file__):
        sys.exit("refused: a program is not the one the plan names")
    V, files, missing = {}, {}, []
    for a, rec in P["arms"].items():
        for t in TRACKS:
            rel = f"{rec['folder']}/{t}_c16.jsonl"; p = os.path.join(VOL_DIR, *rel.split("/"))
            if not os.path.isfile(p):
                missing.append(rel); continue
            v = K.verdicts(p); V.setdefault(a, {})[t] = v
            files.setdefault(a, {})[t] = {"file": rel, "sha256": sha(p), "items": len(v), "without_a_verdict": sum(1 for x in v.values() if x not in ("safe", "unsafe"))}
    first = next(iter(P["arms"])); ctl = {t: controls(V[first][t]) for t in TRACKS}
    if not all(c["pass"] for c in ctl.values()):
        sys.exit("refused: a check on a copy with known changes did not give the known answer; no table is written")
    pairs, not_computed = [], []
    for a, b in itertools.combinations(P["arms"], 2):
        g = group_of(P["arms"][a]["kind"], P["arms"][b]["kind"])
        if any(t not in V.get(x, {}) for x in (a, b) for t in TRACKS):
            not_computed.append({"first": a, "second": b, "group": g}); continue
        pairs.append({"first": a, "second": b, "group": g, **{t: one(V[a][t], V[b][t]) for t in TRACKS}})
    groups = {}
    for g in P["groups"]:
        ps = [p for p in pairs if p["group"] == g]
        groups[g] = {"pairs": len(ps), "pairs_not_computed": sum(1 for p in not_computed if p["group"] == g),
                     **{t: ({"share_min": min(p[t]["share"] for p in ps), "share_max": max(p[t]["share"] for p in ps), "differing_min": min(p[t]["differing"] for p in ps), "differing_max": max(p[t]["differing"] for p in ps)} if ps else None) for t in TRACKS}}
    reading = {g: {t: (None if not (groups[g][t] and groups["UU"][t]) else
                       {"entirely_below_UU": groups[g][t]["share_max"] < groups["UU"][t]["share_min"], "entirely_above_UU": groups[g][t]["share_min"] > groups["UU"][t]["share_max"],
                        "inside_UU": groups["UU"][t]["share_min"] <= groups[g][t]["share_min"] and groups[g][t]["share_max"] <= groups["UU"][t]["share_max"]}) for t in TRACKS} for g in ("N2", "N1")}
    for g in reading:
        for t in TRACKS:
            if reading[g][t]:
                reading[g][t]["overlaps_UU"] = not (reading[g][t]["entirely_below_UU"] or reading[g][t]["entirely_above_UU"])

    def ph(g):
        return "—" if not groups[g]["pairs"] else " / ".join(f"{pct(groups[g][t]['share_min'])}–{pct(groups[g][t]['share_max'])}%" for t in TRACKS)
    R = {"plan": {"file": "results/safety_guard_agreement/plan.json", "sha256": sha(PLAN), "written": P["written"]}, "files": files, "files_missing": missing,
         "checks_on_copies_with_known_changes": {"file_used": files[first], "per_track": ctl}, "pairs": pairs, "pairs_not_computed": not_computed, "groups": groups,
         "against_UU": reading, "as_the_article_writes_them": {"prompts / responses": {g: ph(g) for g in ("UU", "N1", "N2")}}}
    open(os.path.join(OUT, "pairs.json"), "w", encoding="utf-8", newline="\n").write(json.dumps(R, indent=1, ensure_ascii=False) + "\n")
    L = ["| Group | Pairs | Prompts: same verdict, smallest to largest | Prompts: differing items | Responses: same verdict, smallest to largest | Responses: differing items |", "|---|---|---|---|---|---|"]
    for g, text in P["groups"].items():
        G = groups[g]
        L.append(f"| {g}: {text} | {G['pairs']} | " + " | ".join(("— | —" if not G[t] else f"{pct(G[t]['share_min'])}% to {pct(G[t]['share_max'])}% | {G[t]['differing_min']} to {G[t]['differing_max']}") for t in TRACKS) + " |")
    L += ["", "| Group | First | Second | Prompts: items | same | differing | unsafe only in first : second | Responses: items | same | differing | unsafe only in first : second |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in P["groups"]:
        for p in pairs:
            if p["group"] == g:
                L.append(f"| {g} | {p['first']} | {p['second']} | " + " | ".join(f"{p[t]['items_in_both']:,} | {p[t]['same_verdict']:,} ({pct(p[t]['share'])}%) | {p[t]['differing']} | {p[t]['unsafe_only_in_the_first']} : {p[t]['unsafe_only_in_the_second']}" for t in TRACKS) + " |")
    open(os.path.join(OUT, "pairs.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print(json.dumps({"pairs": len(pairs), "not_computed": len(not_computed), "files_missing": missing, "as_the_article_writes_them": R["as_the_article_writes_them"], "against_UU": reading}))   # ASCII on the console; the files carry the dashes


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("what", choices=("plan", "run")); ap.add_argument("--stamp")
    a = ap.parse_args()
    if a.what == "plan":
        if not a.stamp:
            sys.exit("plan needs --stamp")
        plan(a.stamp)
    else:
        run()


if __name__ == "__main__":
    main()
