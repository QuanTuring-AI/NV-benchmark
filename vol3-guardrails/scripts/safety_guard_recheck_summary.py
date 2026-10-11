#!/usr/bin/env python3
"""Vol.3 · the second pre-registered look at the Safety Guard verdicts on two servers: summaries, criteria, disposition.
No container is started here.

Arms: U1 and U2 (upstream vLLM 0.20.2, two containers of one session) and M (the generic NIM 2.0.12) between them.

  rates       the four Aegis 2.0 rates of an arm, from its own summary: detection and false alarm on prompts and on
              responses
  T           the allowance per rate: the larger of D_hist (the largest difference between any two of the three
              earlier runs of the upstream arm, fixed in the pre-registration) and |U1 - U2| of this session
  C1          every rate of M is within T of the mean of U1 and U2
  C2          McNemar's exact two-sided test on the Aegis items of each track, M against U1 and M against U2: among
              the items where the two servers' verdicts differ, is one direction more frequent than chance? Four
              p-values, each at least alpha / 4. XSTest is tested the same way and reported, not judged.
  C3          the same verdict on at least 99% of the items of each track's whole file, M against U1 and against U2
  sanity      U1 against U2 through C2 and C3: if two containers of one server do not pass, the session cannot judge M
  validity    U1 and U2 each within 5% of the upstream arm's rate of 2026-10-08 on both tracks
If sanity or validity fails, the outcome is "invalid_night" and no pass or fail is written for C1 to C3.

A verdict is "unsafe" or not; an item on which one of the two servers gave no verdict is left out of C2 and counted.
Per-item files of two arms are read together here, for one model on two servers: that is the question of the cell.

usage: safety_guard_recheck_summary.py --prediction FILE          after the session
       safety_guard_recheck_summary.py controls OUT.json          before the freeze: the checks on files that exist
"""
import argparse, json, math, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOL_DIR = os.path.dirname(HERE)
os.environ.setdefault("SG_NIM_RESULTS", os.path.join(VOL_DIR, "results", "safety_guard_recheck"))
os.environ.setdefault("SG_NIM_BUCKET", os.path.join(os.path.dirname(VOL_DIR), "_internal", "hold", "vol3_safety_guard_recheck"))
sys.path.insert(0, HERE)
from p93_common import RESULTS as P93_RESULTS, read_jsonl, sha256_file  # noqa: E402
import safety_guard_nim_run as R  # noqa: E402
import safety_guard_nim_summary as S  # noqa: E402

ARMS = ("U1", "M", "U2"); STEP_OF = {"U1": "u1", "M": "m", "U2": "u2"}
TRACKS = ("input", "output"); RATES = [(t, k) for t in TRACKS for k in ("detection", "false_alarm")]
INVALID = "invalid_night"
EARLIER = {"J6 (2026-10-02)": "results/p93_judges/J6/summary.json", "J6-today (2026-10-06)": "results/safety_guard_nim/J6-today/summary.json", "J6-tonight (2026-10-08)": "results/model_free_nim/J6-tonight/summary.json"}


def rate_key(t, k):
    return f"tracks.{t}.quality.aegis2.{k}.rate"


def rates_of(summary):
    return {f"{t}.{k}": summary["tracks"][t]["quality"]["aegis2"][k]["rate"] for t, k in RATES}


def d_hist():
    """Per rate: the largest absolute difference between any two of the earlier runs of the upstream arm. -> record"""
    S3 = {n: json.load(open(os.path.join(VOL_DIR, *f.split("/")), encoding="utf-8")) for n, f in EARLIER.items()}
    names = list(S3); out = {}
    for t, k in RATES:
        vals = {n: S3[n]["tracks"][t]["quality"]["aegis2"][k] for n in names}
        pairs = {f"{a} and {b}": abs(vals[a]["rate"] - vals[b]["rate"]) for i, a in enumerate(names) for b in names[i + 1:]}
        out[f"{t}.{k}"] = {"key": rate_key(t, k), "flagged_of": {n: [vals[n]["k"], vals[n]["n"]] for n in names}, "pairs": pairs, "D_hist": max(pairs.values())}
    return {"runs": EARLIER, "rates": out}


def verdicts(path):
    return {r["item_id"]: r.get("verdict") for r in read_jsonl(path)}


def datasets():
    return {it["item_id"]: it["dataset"] for it in read_jsonl(os.path.join(P93_RESULTS, "items.jsonl"))}


def binom_two_sided(b, c):
    """Exact two-sided p for b against c under equal chances (McNemar's exact test); 1.0 when nothing differs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def mcnemar(A, B, ids):
    """A, B: item -> verdict. Over ids: b = unsafe in A and not in B, c = the other way. -> record"""
    b = c = same = left_out = 0
    for i in ids:
        x, y = A.get(i), B.get(i)
        if x not in ("safe", "unsafe") or y not in ("safe", "unsafe"):
            left_out += 1; continue
        if x == y:
            same += 1
        elif x == "unsafe":
            b += 1
        else:
            c += 1
    return {"items": len(ids), "same": same, "unsafe_only_in_the_first": b, "unsafe_only_in_the_second": c, "without_a_verdict_on_one_side": left_out, "p": binom_two_sided(b, c)}


def agreement(A, B):
    both = sorted(set(A) & set(B)); same = sum(1 for i in both if A[i] == B[i])
    return {"items_in_both": len(both), "items_only_in_one": len(set(A) ^ set(B)), "same_verdict": same, "share": same / len(both) if both else None}


def pair(A, B, track, DS):
    ids = {ds: sorted(i for i in set(A) & set(B) if DS.get(i) == ds) for ds in ("aegis2", "xstest")}
    out = {"mcnemar_aegis2": mcnemar(A, B, ids["aegis2"]), "agreement_whole_file": agreement(A, B)}
    if track == "input":
        out["mcnemar_xstest_reported_not_judged"] = mcnemar(A, B, ids["xstest"])
    return out


def flipped(V, ids, n):
    """A copy of V with the first n of ids (in sorted order) whose verdict is unsafe set to safe."""
    out = dict(V); done = []
    for i in sorted(ids):
        if out.get(i) == "unsafe":
            out[i] = "safe"; done.append(i)
            if len(done) == n:
                break
    return out, done


def controls(out_path):
    """The checks that must fail and the one that may pass, on files that exist before the session."""
    base = os.path.join(VOL_DIR, "results", "model_free_nim"); DS = datasets(); alpha4 = 0.05 / 4
    items = {it["item_id"]: it for it in read_jsonl(os.path.join(P93_RESULTS, "items.jsonl"))}
    T = d_hist()["rates"]; rec = {"what": "checks run before the freeze on files of the first cell, with the functions the criteria use", "alpha_over_4": alpha4, "C2_must_fail": {}, "C2_on_two_real_upstream_arms": {}}
    for t in TRACKS:
        V = verdicts(os.path.join(base, "J6-tonight", f"{t}_c16.jsonl")); aeg = [i for i in V if DS.get(i) == "aegis2"]
        F, done = flipped(V, aeg, 10); m = mcnemar(F, V, sorted(aeg))
        rec["C2_must_fail"][t] = {"file": f"results/model_free_nim/J6-tonight/{t}_c16.jsonl", "change": "10 Aegis items with the verdict unsafe set to safe, one direction", "items_changed": len(done), **m, "fails_as_it_must": m["p"] < alpha4}
        W = verdicts(os.path.join(base, "J6-v0271", f"{t}_c16.jsonl"))
        rec["C2_on_two_real_upstream_arms"][t] = {"first": "J6-tonight (upstream vLLM 0.20.2)", "second": "J6-v0271 (upstream vLLM 0.27.1)", **pair(V, W, t, DS)}
    V = verdicts(os.path.join(base, "J6-tonight", "output_c16.jsonl"))
    harmful = sorted(i for i in V if DS.get(i) == "aegis2" and items[i]["gold_output"] == "unsafe")
    k0 = sum(1 for i in harmful if V[i] == "unsafe"); F, done = flipped(V, harmful, 8); k1 = sum(1 for i in harmful if F[i] == "unsafe")
    own = json.load(open(os.path.join(base, "J6-tonight", "summary.json"), encoding="utf-8"))["tracks"]["output"]["quality"]["aegis2"]["detection"]
    diff = abs(k1 - k0) / len(harmful); t_r = T["output.detection"]["D_hist"]
    rec["C1_must_fail"] = {"file": "results/model_free_nim/J6-tonight/output_c16.jsonl", "change": "8 harmful Aegis responses with the verdict unsafe set to safe", "harmful_items": len(harmful), "flagged_before": k0, "flagged_after": k1,
                           "the_count_read_here_equals_the_summary": [k0, len(harmful)] == [own["k"], own["n"]], "rate_difference": diff, "allowance_D_hist": t_r, "fails_as_it_must": diff > t_r}
    rec["all_as_required"] = all(v["fails_as_it_must"] for v in rec["C2_must_fail"].values()) and rec["C1_must_fail"]["fails_as_it_must"] and rec["C1_must_fail"]["the_count_read_here_equals_the_summary"]
    json.dump(rec, open(out_path, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"C2_must_fail_p": {t: v["p"] for t, v in rec["C2_must_fail"].items()}, "C1_must_fail": [diff, t_r], "real_arms_p": {t: v["mcnemar_aegis2"]["p"] for t, v in rec["C2_on_two_real_upstream_arms"].items()}, "all_as_required": rec["all_as_required"]}))
    return 0 if rec["all_as_required"] else 1


def label(arm, events, results):
    """What the server said about itself once ready, and what the cell records hold."""
    step = STEP_OF[arm]
    ready = [e for e in events if e.get("kind") == "container_ready" and e.get("step") == step and e.get("ready")]
    warm = [e for e in events if e.get("kind") == "warm_up" and e.get("step") == step]
    cells_path = os.path.join(results, arm, "cells.jsonl"); cells = read_jsonl(cells_path) if os.path.isfile(cells_path) else []
    cmd = (ready[-1]["launch"].get("command") if ready else None) or []
    v = warm[-1].get("versions", {}) if warm else {}; meta = v.get("/v1/metadata") or {}; nim = (v.get("/v1/version") or {}).get("release") or (meta.get("version") if isinstance(meta.get("version"), str) else None)
    pinned = next((x.split("=", 1)[1] for x in cmd if x.startswith("NIM_MODEL_PROFILE=")), None)
    return {"driver": sorted({c["gpu_end"]["driver"] for c in cells if c.get("gpu_end")}), "image": next((x for x in cmd if x.startswith(("vllm/", "nvcr.io/"))), None),
            "vllm_version_from_the_server": (v.get("/version") or {}).get("version"), "nim_version_from_the_server": nim,
            "profile_id": meta.get("profile_id") or meta.get("selectedModelProfileId") or pinned, "profile_name": meta.get("profile_name"), "profile_from": "/v1/metadata" if (meta.get("profile_id") or meta.get("selectedModelProfileId")) else ("the container command" if pinned else None),
            "start_setting": ready[-1].get("profile") if ready else None, "container_started_at": ready[-1].get("started_at_as_docker_reports") if ready else None, "container_command": cmd or None,
            "gpu_end_of_each_cell": [{"track": c.get("track"), "mode": c.get("mode"), **c["gpu_end"]} for c in cells if c.get("gpu_end")]}


def rate(Sm, t):
    T = (Sm or {}).get("tracks", {}).get(t, {})
    return (T.get("quality_cell") or {}).get("verdicts_per_s") if T.get("usable") else None


def judge(pred, sums, results, ref):
    C = pred["criteria"]; alpha4 = C["C2"]["each_p_at_least"]; out = {}; DS = datasets()
    V = {arm: {t: verdicts(os.path.join(results, arm, f"{t}_c16.jsonl")) for t in TRACKS if os.path.isfile(os.path.join(results, arm, f"{t}_c16.jsonl"))} for arm in ARMS}
    complete = all(arm in sums and all(rate(sums[arm], t) is not None and t in V[arm] for t in TRACKS) for arm in ARMS)
    out["arms_complete"] = {arm: bool(arm in sums and all(rate(sums[arm], t) is not None for t in TRACKS)) for arm in ARMS}
    lim = C["validity"]["within_percent"]
    gate = {arm: {t: (None if rate(sums.get(arm), t) is None else (rate(sums[arm], t) / rate(ref, t) - 1) * 100) for t in TRACKS} for arm in ("U1", "U2")}
    out["validity"] = {"rule": C["validity"]["rule"], "percent_against_the_reference": gate, "limit_percent": lim, "pass": all(v is not None and abs(v) <= lim for g in gate.values() for v in g.values())}
    if not complete:
        out["outcome"] = "M did not run" if not out["arms_complete"]["M"] and out["arms_complete"]["U1"] else INVALID
        out["why"] = "an arm has no complete cell on a track"; out["disposition"] = pred["disposition"].get(out["outcome"]); return out
    uu = {t: pair(V["U1"][t], V["U2"][t], t, DS) for t in TRACKS}
    out["sanity_U1_against_U2"] = {"rule": C["sanity"]["rule"], "per_track": uu, "pass": all(uu[t]["mcnemar_aegis2"]["p"] >= alpha4 and uu[t]["agreement_whole_file"]["share"] >= C["C3"]["share_at_least"] for t in TRACKS)}
    r = {arm: rates_of(sums[arm]) for arm in ARMS}; c1 = {}
    for t, k in RATES:
        key = f"{t}.{k}"; dh = pred["allowance"]["D_hist"][key]["D_hist"]; uud = abs(r["U1"][key] - r["U2"][key]); T = max(dh, uud)
        d = abs(r["M"][key] - (r["U1"][key] + r["U2"][key]) / 2)
        c1[key] = {"U1": r["U1"][key], "M": r["M"][key], "U2": r["U2"][key], "D_hist": dh, "U1_against_U2": uud, "T": T, "T_is": "D_hist" if dh >= uud else "|U1 - U2|", "M_against_the_mean_of_U1_and_U2": d,
                   "M_is": "above" if r["M"][key] > (r["U1"][key] + r["U2"][key]) / 2 else "below", "within": d <= T}
    mu = {u: {t: pair(V["M"][t], V[u][t], t, DS) for t in TRACKS} for u in ("U1", "U2")}
    valid = out["validity"]["pass"] and out["sanity_U1_against_U2"]["pass"]
    p4 = {f"M against {u}, {t}": mu[u][t]["mcnemar_aegis2"]["p"] for u in ("U1", "U2") for t in TRACKS}
    s4 = {f"M against {u}, {t}": mu[u][t]["agreement_whole_file"]["share"] for u in ("U1", "U2") for t in TRACKS}
    out["C1"] = {"rule": C["C1"]["rule"], "per_rate": c1, "pass": all(x["within"] for x in c1.values()) if valid else None}
    out["C2"] = {"rule": C["C2"]["rule"], "each_p_at_least": alpha4, "p": p4, "per_pair": {u: {t: mu[u][t]["mcnemar_aegis2"] for t in TRACKS} for u in mu}, "xstest_reported_not_judged": {u: mu[u]["input"]["mcnemar_xstest_reported_not_judged"] for u in mu},
                 "pass": all(p >= alpha4 for p in p4.values()) if valid else None}
    out["C3"] = {"rule": C["C3"]["rule"], "share_at_least": C["C3"]["share_at_least"], "share": s4, "per_pair": {u: {t: mu[u][t]["agreement_whole_file"] for t in TRACKS} for u in mu}, "pass": all(s >= C["C3"]["share_at_least"] for s in s4.values()) if valid else None}
    if not valid:
        out["outcome"] = INVALID; out["why"] = "the validity gate did not pass" if not out["validity"]["pass"] else "two containers of the upstream server did not pass the sanity check"
        out["note"] = "C1 to C3 carry their numbers and no pass or fail"
    else:
        out["outcome"] = "all pass" if out["C1"]["pass"] and out["C2"]["pass"] and out["C3"]["pass"] else "C1 or C2 does not pass" if not (out["C1"]["pass"] and out["C2"]["pass"]) else "C3 does not pass"
    out["disposition"] = pred["disposition"].get(out["outcome"], pred["disposition"].get("any other outcome"))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:2] == ["controls"]:
        return controls(sys.argv[2])
    ap = argparse.ArgumentParser(); ap.add_argument("--prediction", required=True); a = ap.parse_args()
    pred = json.load(open(a.prediction, encoding="utf-8")); results = R.RESULTS
    ev = os.path.join(results, "events.jsonl"); events = read_jsonl(ev) if os.path.isfile(ev) else []
    sums = {}
    for arm in ARMS:
        D = S.direct_summary(arm)
        if D:
            D["label"] = label(arm, events, results)
            json.dump(D, open(os.path.join(results, arm, "summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False); sums[arm] = D
    ref = json.load(open(os.path.join(VOL_DIR, *pred["criteria"]["validity"]["reference_summary"].split("/")), encoding="utf-8"))
    C = judge(pred, sums, results, ref); C["prediction_sha256"] = sha256_file(a.prediction)
    json.dump(C, open(os.path.join(results, "criteria.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    hide = C["outcome"] == INVALID
    rows = []
    for arm in ARMS:
        for t in TRACKS:
            if arm in sums and sums[arm]["tracks"][t].get("usable"):
                q = sums[arm]["tracks"][t]["quality"]["aegis2"]; c = sums[arm]["tracks"][t]["quality_cell"]
                rows.append({"arm": arm, "track": t, "detection": q["detection"], "false_alarm": q["false_alarm"], "c16_verdicts_per_s": INVALID if hide else c["verdicts_per_s"], "c16_latency_ms_p99": INVALID if hide else c["latency_ms"]["p99"],
                             "completion_tokens_p50": c["completion_tokens"]["p50"], "against_the_reference_percent": (c["verdicts_per_s"] / rate(ref, t) - 1) * 100})
    json.dump({"what": "one line per arm and track, each from that arm's summary.json", "outcome": C["outcome"], "rows": rows}, open(os.path.join(results, "table.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    f = lambda x, s="{:.1f}": "—" if x is None else (x if isinstance(x, str) else s.format(x))
    md = ["| Arm | Track | Detection | False alarm | Verdicts per second at 16 | p99 ms at 16 | Rate against J6-tonight (2026-10-08) |", "|---|---|---|---|---|---|---|"]
    md += [f"| {x['arm']} | {x['track']} | {S.pct(x['detection'])} | {S.pct(x['false_alarm'])} | {f(x['c16_verdicts_per_s'])} | {f(x['c16_latency_ms_p99'])} | {f(x['against_the_reference_percent'], '{:+.1f}%')} |" for x in rows]
    open(os.path.join(results, "table.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    print("\n".join(md))
    print(json.dumps({"outcome": C["outcome"], "validity": C["validity"]["pass"], "sanity": (C.get("sanity_U1_against_U2") or {}).get("pass"), "C1": (C.get("C1") or {}).get("pass"), "C2": (C.get("C2") or {}).get("pass"), "C3": (C.get("C3") or {}).get("pass")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
