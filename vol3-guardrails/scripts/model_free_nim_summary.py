#!/usr/bin/env python3
"""Vol.3 · the generic-NIM cell: one summary per arm, the four criteria of the pre-registration, and the branch they
select. No container is started here.

  per arm      J6M, J6-tonight, J6N-tonight: the study's own analysis program, unchanged (`p93_analyze.py --arm J6`
               through the arm's view). A label is added to each summary: driver, image, engine version as the server
               reported it, profile, and the card at the end of each timed cell.
  J6M-rail     the rail program's own summary (safety_guard_nim_summary.rail_summary), run on the rail cell's folder
  criteria     criteria.json: each criterion with its numbers and pass / fail, the validity gate of the night, and the
               branch (A, B or C) the pre-registration ties to them
  table        table.json / table.md: the three arms' figures side by side. If the validity gate fails, every absolute
               figure of the night is written as the text "invalid_night" and only the ratios between the three arms
               of the night remain.

The second criterion sets two arms' per-item verdicts side by side: J6M and J6-tonight are one model, one weight
directory, one prompt and one program on two servers, and the question of the cell is whether the server changes a
verdict. Nothing else in this volume compares per-item verdicts of two arms, and no other pair is compared here.

usage: model_free_nim_summary.py --prediction FILE
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOL_DIR = os.path.dirname(HERE)
os.environ.setdefault("SG_NIM_RESULTS", os.path.join(VOL_DIR, "results", "model_free_nim"))
os.environ.setdefault("SG_NIM_BUCKET", os.path.join(os.path.dirname(VOL_DIR), "_internal", "hold", "vol3_model_free_nim"))
sys.path.insert(0, HERE)
from p93_common import read_jsonl, sha256_file  # noqa: E402
import safety_guard_nim_run as R  # noqa: E402
import safety_guard_nim_summary as S  # noqa: E402

ARMS = ("J6M", "J6-tonight", "J6N-tonight")
STEP_OF = {"J6M": "j6m_main", "J6-tonight": "vllm_tonight", "J6N-tonight": "nim_tonight"}
TRACKS = ("input", "output")
INVALID = "invalid_night"


def label(arm, events):
    ready = [e for e in events if e.get("kind") == "container_ready" and e.get("step") == STEP_OF[arm] and e.get("ready")]
    warm = [e for e in events if e.get("kind") == "warm_up" and e.get("step") == STEP_OF[arm]]
    cells = read_jsonl(os.path.join(R.RESULTS, arm, "cells.jsonl")) if os.path.isfile(os.path.join(R.RESULTS, arm, "cells.jsonl")) else []
    L = ready[-1]["launch"] if ready else {}
    versions = warm[-1].get("versions", {}) if warm else {}
    meta = (versions.get("/v1/metadata") or {})
    return {"driver": sorted({c["gpu_end"]["driver"] for c in cells if c.get("gpu_end")}), "container_command": L.get("command"), "image": (L.get("command") or [None])[-1] if arm != "J6-tonight" else next((x for x in L.get("command", []) if x.startswith("vllm/")), None),
            "start_setting": ready[-1].get("profile") if ready else None, "vllm_version_in_the_start_log": L.get("vllm_version_in_log"), "server_version_endpoints": {k: v for k, v in versions.items() if k != "/v1/metadata"},
            "nim_version": meta.get("version"), "selected_profile_id": meta.get("selectedModelProfileId"), "container_started_at": ready[-1].get("started_at_as_docker_reports") if ready else None,
            "gpu_end_of_each_cell": [{"track": c.get("track"), "mode": c.get("mode"), **c["gpu_end"]} for c in cells if c.get("gpu_end")]}


def rail_summary():
    v = os.path.join(R.BUCKET, "views", "rail")
    if not os.path.isfile(os.path.join(R.RESULTS, "J6M-rail", "cells.jsonl")):
        return None
    r = subprocess.run([sys.executable, "-c", "import safety_guard_nim_summary as S; S.rail_summary()"], cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, SG_NIM_RESULTS=v, SG_NIM_BUCKET=os.path.join(R.BUCKET, "rail")))
    if r.returncode != 0:
        sys.exit(f"the rail summary ended with {r.returncode}: {r.stderr[-300:]}")
    p = os.path.join(R.RESULTS, "J6M-rail", "summary.json"); D = json.load(open(p, encoding="utf-8"))
    D["arm_of_this_folder"] = "J6M-rail"; D["request_shape_of"] = "J6G"
    json.dump(D, open(p, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return D


def rate_of(Sm, track):
    T = (Sm or {}).get("tracks", {}).get(track, {})
    return (T.get("quality_cell") or {}).get("verdicts_per_s") if T.get("usable") else None


def pct_diff(a, b):
    return None if a is None or b is None else (a / b - 1) * 100


def per_item(arm_a, arm_b, track):
    """Verdicts of the whole-track cell, item by item, of one model on two servers. Counts only."""
    pa, pb = (os.path.join(R.RESULTS, x, f"{track}_c16.jsonl") for x in (arm_a, arm_b))
    if not (os.path.isfile(pa) and os.path.isfile(pb)):
        return None
    A = {r["item_id"]: r.get("verdict") for r in read_jsonl(pa)}; B = {r["item_id"]: r.get("verdict") for r in read_jsonl(pb)}
    both = sorted(set(A) & set(B)); classes = {}
    for i in both:
        k = "same" if A[i] == B[i] else f"{A[i]} on {arm_a}, {B[i]} on {arm_b}"
        classes[k] = classes.get(k, 0) + 1
    same = classes.get("same", 0)
    return {"items_in_both": len(both), "items_only_in_one": len(set(A) ^ set(B)), "same_verdict": same, "share": same / len(both) if both else None, "classes": classes,
            "files": {arm_a: sha256_file(pa), arm_b: sha256_file(pb)}}


def criteria(pred, sums, rail, today, events):
    C = pred["criteria"]; out = {}
    lim = C["speed"]["within_percent"]
    sp = {t: pct_diff(rate_of(sums.get("J6M"), t), rate_of(sums.get("J6-tonight"), t)) for t in TRACKS}
    out["speed"] = {"rule": C["speed"]["rule"], "J6M_against_J6-tonight_percent": sp, "limit_percent": lim, "pass": all(v is not None and abs(v) <= lim for v in sp.values())}
    pi = {t: per_item("J6M", "J6-tonight", t) for t in TRACKS}; dq = {}
    for t in TRACKS:
        qa = ((sums.get("J6M") or {}).get("tracks", {}).get(t, {}).get("quality") or {}).get("aegis2"); qb = ((sums.get("J6-tonight") or {}).get("tracks", {}).get(t, {}).get("quality") or {}).get("aegis2")
        dq[t] = None if not (qa and qb) else {k: abs(qa[k]["rate"] - qb[k]["rate"]) * 100 for k in ("detection", "false_alarm")}
    v = C["verdicts"]
    out["verdicts"] = {"rule": v["rule"], "per_item": pi, "aegis2_difference_in_points": dq, "limit_share": v["same_verdict_share_at_least"], "limit_points": v["rate_difference_at_most_points"],
                       "pass": all(pi[t] and pi[t]["share"] is not None and pi[t]["share"] >= v["same_verdict_share_at_least"] and dq[t] and max(dq[t].values()) <= v["rate_difference_at_most_points"] for t in TRACKS)}
    ag = [((rail or {}).get("tracks", {}).get(t, {}).get("rail_beside_verdict_of_the_same_call") or {}).get("agree") for t in TRACKS]
    k = sum(a["k"] for a in ag if a); n = sum(a["n"] for a in ag if a)
    out["rail"] = {"rule": C["rail"]["rule"], "agree": k, "calls": n, "limit": C["rail"]["agree_at_least"], "of": C["rail"]["calls"], "pass": n == C["rail"]["calls"] and k >= C["rail"]["agree_at_least"]}
    g = C["validity_of_the_night"]; nv = {t: pct_diff(rate_of(sums.get("J6-tonight"), t), rate_of(today, t)) for t in TRACKS}
    out["validity_of_the_night"] = {"rule": g["rule"], "J6-tonight_against_J6-today_percent": nv, "limit_percent": g["within_percent"], "pass": all(x is not None and abs(x) <= g["within_percent"] for x in nv.values())}
    started = any(e.get("kind") == "container_ready" and e.get("step") == "j6m_main" and e.get("ready") for e in events)
    out["J6M_reported_ready"] = started
    out["branch"] = "C" if not started else ("A" if out["speed"]["pass"] and out["verdicts"]["pass"] and out["rail"]["pass"] else "B")
    out["absolute_figures_of_the_night"] = "valid" if out["validity_of_the_night"]["pass"] else INVALID
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("--prediction", required=True); a = ap.parse_args()
    pred = json.load(open(a.prediction, encoding="utf-8"))
    ev = os.path.join(R.RESULTS, "events.jsonl"); events = read_jsonl(ev) if os.path.isfile(ev) else []
    sums = {}
    for arm in ARMS:
        D = S.direct_summary(arm)
        if D:
            D["label"] = label(arm, events); p = os.path.join(R.RESULTS, arm, "summary.json")
            json.dump(D, open(p, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False); sums[arm] = D
    rail = rail_summary()
    today = json.load(open(os.path.join(VOL_DIR, *pred["criteria"]["validity_of_the_night"]["reference_summary"].split("/")), encoding="utf-8"))
    C = criteria(pred, sums, rail, today, events); C["prediction_sha256"] = sha256_file(a.prediction)
    json.dump(C, open(os.path.join(R.RESULTS, "criteria.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    valid = C["validity_of_the_night"]["pass"]; rows = []
    for arm in ARMS:
        for track, group in (("input", "aegis2"), ("input", "xstest"), ("output", "aegis2")):
            r = S.line(arm, sums.get(arm), track, group)
            if r.get("usable"):
                r["c16_against_J6-tonight_percent"] = pct_diff(r["c16_verdicts_per_s"], rate_of(sums.get("J6-tonight"), track))
                if not valid:
                    for k in ("c1_latency_ms_p50", "c1_latency_ms_p99", "c16_verdicts_per_s", "c16_latency_ms_p99"):
                        r[k] = INVALID
            rows.append(r)
    json.dump({"what": "one line per arm, track and data set, each built from that arm's summary.json; the last column is that arm's rate against J6-tonight's on the same track",
               "absolute_figures_of_the_night": C["absolute_figures_of_the_night"], "rows": rows}, open(os.path.join(R.RESULTS, "table.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    f = lambda x, s="{:.1f}": "—" if x is None else (x if isinstance(x, str) else s.format(x))
    md = ["| Arm | Track · data | Detection | False alarm | c=1 p50 ms | c=16 verdicts/s | c=16 p99 ms | c=16 against J6-tonight |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['arm']} | {r['track']} · {r['group']} | {S.pct(r['detection'])} | {S.pct(r['false_alarm'])} | {f(r['c1_latency_ms_p50'])} | {f(r['c16_verdicts_per_s'])} | {f(r['c16_latency_ms_p99'])} | {f(r['c16_against_J6-tonight_percent'], '{:+.1f}%')} |"
           for r in rows if r.get("usable")]
    open(os.path.join(R.RESULTS, "table.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    print("\n".join(md)); print(json.dumps({k: (v["pass"] if isinstance(v, dict) and "pass" in v else v) for k, v in C.items() if k != "prediction_sha256"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
