#!/usr/bin/env python3
"""Vol.3 · the generic-NIM cell: what the addendum adds to the summary. No container is started here.

  first        the cell's own summary program runs unchanged (model_free_nim_summary.py): the three arms' summaries,
               the four criteria of the pre-registration and its branch, as registered
  J6-v0271     the added arm's summary by the study's analysis program, with the same label as the other arms
  directions   for the registered speed criterion: on each track, whether J6M is above or below J6-tonight
  added        two criteria of the addendum: J6M is not slower than the volume's upstream arm (at least 95% of
               J6-tonight's rate on both tracks); J6M is within 5% of J6-v0271 on both tracks (the same engine
               version with and without the NIM around it)
  disposition  the addendum's table: which of A, B, C applies, and whether the sentence about the same engine version
               may be written
Written to criteria_addendum.json and table_addendum.json / .md; criteria.json and table.json stay as the cell's own
program wrote them.

usage: model_free_nim_addendum_summary.py --prediction FILE --addendum FILE
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_free_nim_summary as MS  # noqa: E402  (sets the default results and bucket folders)
from p93_common import read_jsonl, sha256_file  # noqa: E402

R, S = MS.R, MS.S
ARM = "J6-v0271"; STEP = "vllm_0271"; TRACKS = MS.TRACKS


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("--prediction", required=True); ap.add_argument("--addendum", required=True); a = ap.parse_args()
    A = json.load(open(a.addendum, encoding="utf-8"))
    r = subprocess.run([sys.executable, os.path.join(HERE, "model_free_nim_summary.py"), "--prediction", a.prediction], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"the cell's summary program ended with {r.returncode}: {r.stderr[-400:]}")
    C = json.load(open(os.path.join(R.RESULTS, "criteria.json"), encoding="utf-8"))
    ev = os.path.join(R.RESULTS, "events.jsonl"); events = read_jsonl(ev) if os.path.isfile(ev) else []
    sums = {arm: json.load(open(os.path.join(R.RESULTS, arm, "summary.json"), encoding="utf-8")) for arm in MS.ARMS if os.path.isfile(os.path.join(R.RESULTS, arm, "summary.json"))}
    D = S.direct_summary(ARM)
    if D:
        MS.STEP_OF[ARM] = STEP; L = MS.label(ARM, events)
        L["image"] = next((x for x in (L.get("container_command") or []) if x.startswith("vllm/")), None)
        D["label"] = L; json.dump(D, open(os.path.join(R.RESULTS, ARM, "summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    rate = MS.rate_of; K = A["criteria_added"]
    sp = C["speed"]["J6M_against_J6-tonight_percent"]
    out = {"what": "the addendum's additions to criteria.json; the registered criteria are in that file, unchanged", "addendum_sha256": sha256_file(a.addendum), "prediction_sha256": sha256_file(a.prediction),
           "registered_criteria_as_computed": {k: C[k]["pass"] for k in ("speed", "verdicts", "rail", "validity_of_the_night")}, "registered_branch": C["branch"],
           "direction_of_the_registered_speed_criterion": {t: (None if sp[t] is None else {"J6M_against_J6-tonight_percent": sp[t], "J6M_is": "above" if sp[t] > 0 else ("below" if sp[t] < 0 else "equal to") + ""}) for t in TRACKS}}
    floor = K["not_slower_than_the_upstream_arm"]["at_least_share_of_J6-tonight"]
    ns = {t: (None if rate(sums.get("J6M"), t) is None or rate(sums.get("J6-tonight"), t) is None else rate(sums["J6M"], t) / rate(sums["J6-tonight"], t)) for t in TRACKS}
    out["not_slower_than_the_upstream_arm"] = {"rule": K["not_slower_than_the_upstream_arm"]["rule"], "J6M_as_a_share_of_J6-tonight": ns, "at_least": floor, "pass": all(v is not None and v >= floor for v in ns.values())}
    lim = K["wrapper_cost"]["within_percent"]
    wc = {t: MS.pct_diff(rate(sums.get("J6M"), t), rate(D, t)) for t in TRACKS}
    measured = all(v is not None for v in wc.values())
    out["wrapper_cost"] = {"rule": K["wrapper_cost"]["rule"], "J6M_against_J6-v0271_percent": wc, "limit_percent": lim, "measured": measured, "pass": measured and all(abs(v) <= lim for v in wc.values()),
                           "direction": {t: (None if wc[t] is None else ("above" if wc[t] > 0 else "below" if wc[t] < 0 else "equal")) for t in TRACKS}}
    ready = C.get("J6M_reported_ready")
    keep = bool(ready) and out["not_slower_than_the_upstream_arm"]["pass"] and C["verdicts"]["pass"] and C["rail"]["pass"]
    out["disposition"] = {"branch": "C" if not ready else ("A" if keep else "B"),
                          "sentence_about_the_same_engine_version": ("not applicable" if not keep else ("not measured: the added arm has no rate" if not measured else ("may be written" if out["wrapper_cost"]["pass"] else "not written: outside the limit"))),
                          "largest_absolute_wrapper_difference_percent": max((abs(v) for v in wc.values() if v is not None), default=None),
                          "absolute_figures_of_the_night": C["absolute_figures_of_the_night"]}
    json.dump(out, open(os.path.join(R.RESULTS, "criteria_addendum.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    valid = C["validity_of_the_night"]["pass"]; rows = []
    all_sums = dict(sums); all_sums[ARM] = D
    for arm in ("J6-tonight", ARM, "J6M", "J6N-tonight"):
        for track, group in (("input", "aegis2"), ("input", "xstest"), ("output", "aegis2")):
            x = S.line(arm, all_sums.get(arm), track, group)
            if x.get("usable"):
                x["c16_against_J6-tonight_percent"] = MS.pct_diff(x["c16_verdicts_per_s"], rate(sums.get("J6-tonight"), track))
                x["c16_against_J6-v0271_percent"] = MS.pct_diff(x["c16_verdicts_per_s"], rate(D, track))
                if not valid:
                    for k in ("c1_latency_ms_p50", "c1_latency_ms_p99", "c16_verdicts_per_s", "c16_latency_ms_p99"):
                        x[k] = MS.INVALID
            rows.append(x)
    json.dump({"what": "the four arms of the night, one line per arm, track and data set, each built from that arm's summary.json; the last two columns are that arm's rate against J6-tonight's and against J6-v0271's on the same track",
               "absolute_figures_of_the_night": C["absolute_figures_of_the_night"], "rows": rows}, open(os.path.join(R.RESULTS, "table_addendum.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    f = lambda v, s="{:.1f}": "—" if v is None else (v if isinstance(v, str) else s.format(v))
    md = ["| Arm | Track · data | Detection | False alarm | c=1 p50 ms | c=16 verdicts/s | c=16 p99 ms | against J6-tonight | against J6-v0271 |", "|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {x['arm']} | {x['track']} · {x['group']} | {S.pct(x['detection'])} | {S.pct(x['false_alarm'])} | {f(x['c1_latency_ms_p50'])} | {f(x['c16_verdicts_per_s'])} | {f(x['c16_latency_ms_p99'])} | "
           f"{f(x['c16_against_J6-tonight_percent'], '{:+.1f}%')} | {f(x['c16_against_J6-v0271_percent'], '{:+.1f}%')} |" for x in rows if x.get("usable")]
    open(os.path.join(R.RESULTS, "table_addendum.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    print("\n".join(md))
    print(json.dumps({"registered": out["registered_criteria_as_computed"], "registered_branch": out["registered_branch"], "not_slower": out["not_slower_than_the_upstream_arm"]["pass"], "wrapper_cost": out["wrapper_cost"]["pass"], **out["disposition"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
