#!/usr/bin/env python3
"""Vol.5 · cell C4: the spill verdict of one configuration, with spill_judge.py's rule (unchanged, imported).

  alone   from the event file: for the embedder and the reranker, their alone run (service_verdict of the `alone` step):
          S_i = spill_judge.steady_shared(the alone run's shared samples, its ready sample), D_i = its card_delta_mib.
          The answer model has no alone run: S = 0 and D = 0 (supplement 5: condition (1) is then stricter by the
          model's own shared use, and condition (2) is decided by the two services that have an alone run)
  steps   the configuration's service_verdict events in start order: card_delta_mib and at_sample
  shared  the configuration's Windows counter log (shared_mib column), the same samples the steps point into
Writes the verdict with its inputs; the shared peak and how far above the allowance.
usage: c4_judge.py --events FILE --csv FILE --config NAME --out FILE
"""
import argparse, csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import spill_judge as J  # noqa: E402


def shared_col(path):
    return [int(r["shared_mib"]) for r in csv.DictReader(open(path, encoding="utf-8-sig"))]


def main():
    ap = argparse.ArgumentParser()
    for x in ("--events", "--csv", "--config", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    ev = [json.loads(l) for l in open(a.events, encoding="utf-8") if l.strip()]
    res = os.path.dirname(a.csv); alone = {"llm": {"shared_mib": 0, "card_delta_mib": 0, "note": "no alone run (supplement 5)"}}
    current = None
    for e in ev:
        if e["kind"] == "alone_start":
            current = e["service"]
        elif e["kind"] == "service_verdict" and current and e.get("service") == current and e.get("up"):
            sh = shared_col(os.path.join(res, f"alone_{current}_windows_gpu_adapter_memory.csv"))
            alone[current] = {"shared_mib": J.steady_shared(sh, e["ready_sample"]), "card_delta_mib": e["card_delta_mib"]}
        elif e["kind"] in ("alone_end", "config_start"):
            current = None
    if not {"embed", "rank"} <= set(alone):
        raise SystemExit("refused: an alone run (embed or rank) is missing or did not come up")
    steps, inside = [], False
    for e in ev:
        if e["kind"] == "config_start":
            inside = e.get("name") == a.config; steps = [] if inside else steps
        elif e["kind"] == "config_complete" and inside:
            break
        elif inside and e["kind"] == "service_verdict":
            steps.append({"service": e["service"], "card_delta_mib": e["card_delta_mib"], "at_sample": e["at_sample"], "up": e["up"]})
    shared = shared_col(a.csv)
    v = J.judge(alone, [{k: s[k] for k in ("service", "card_delta_mib", "at_sample")} for s in steps], shared)
    total_allowed = sum(alone[s["service"]]["shared_mib"] for s in steps) + J.MARGIN_MIB
    rec = {"configuration": a.config, "alone": alone, "steps": steps, "all_services_up": all(s["up"] for s in steps) and len(steps) == 3,
           "shared_peak_mib": max(shared) if shared else None, "allowance_at_end_mib": total_allowed,
           "peak_above_allowance_mib": (max(shared) - total_allowed) if shared else None, **v}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: rec[k] for k in ("configuration", "all_services_up", "shared_peak_mib", "allowance_at_end_mib", "spilled")}))


if __name__ == "__main__":
    main()
