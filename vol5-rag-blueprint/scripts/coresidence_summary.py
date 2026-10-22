#!/usr/bin/env python3
"""Vol.5 · one table per co-residence run, from its run log (events.jsonl) and the Windows GPU memory counters logged
beside it (windows_gpu_adapter_memory.csv: the card's 'GPU Adapter Memory' Dedicated Usage and Shared Usage, MiB).

Per step: the card's used memory as nvidia-smi gave it, its change since the step before (card_used_delta_mib), and the
Windows shared value at the first counter sample within 20 s after the step (windows_shared_mib; null when there is
none, e.g. before the counter log started). The change of the card's number from one step to the next is what it says and nothing more: on
this host (Windows, WSL2, Docker Desktop) memory of the card can be paged to system memory, so it is not the memory a
service needs.
usage: coresidence_summary.py <results folder> [<results folder> ...]     writes summary.json in each
"""
import csv, datetime as dt, json, os, sys

WINDOW_S = 20     # the counters were sampled every 15 s: a sample more than 20 s after a step does not belong to it


def counters(folder):
    p = os.path.join(folder, "windows_gpu_adapter_memory.csv")
    if not os.path.isfile(p):
        return []
    rows = []
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        rows.append((dt.datetime.fromisoformat(r["at"][:26] + r["at"][-6:]), int(r["dedicated_mib"]), int(r["shared_mib"])))
    return rows


def summary(folder):
    ev = [json.loads(l) for l in open(os.path.join(folder, "events.jsonl"), encoding="utf-8")]
    cs = counters(folder); steps = []; prev = None
    for r in ev:
        if r["kind"] not in ("set_start", "alone_start", "service_verdict", "set_complete", "requests_done", "all_removed"):
            continue
        at = dt.datetime.strptime(r["at"], "%Y-%m-%dT%H:%M:%S%z")
        after = [c for c in cs if at <= c[0] <= at + dt.timedelta(seconds=WINDOW_S)]
        used = r["card"]["used_mib"]
        steps.append({"at": r["at"], "step": r["kind"], "service": r.get("service"), "up": r.get("up"),
                      "card_used_mib": used, "card_used_delta_mib": None if prev is None or r["kind"] in ("alone_start", "set_start") else used - prev,
                      "windows_dedicated_mib": after[0][1] if after else None, "windows_shared_mib": after[0][2] if after else None,
                      "windows_sample_at": after[0][0].isoformat() if after else None})
        prev = used
    out = {"what": "the steps of one co-residence run: the card's used memory, its change since the step before, and the Windows shared GPU memory",
           "reading": "card_used_delta_mib is the change of nvidia-smi's number between two steps; on this host memory of the card can be paged to system memory, so it is not the memory a service needs",
           "counter_log": "windows_gpu_adapter_memory.csv" if cs else None, "counter_log_first_sample": cs[0][0].isoformat() if cs else None,
           "steps": steps, "program": "scripts/coresidence_summary.py"}
    json.dump(out, open(os.path.join(folder, "summary.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    return out


if __name__ == "__main__":
    for f in sys.argv[1:]:
        s = summary(f)
        for x in s["steps"]:
            print(os.path.basename(f.rstrip("/\\")), x["at"][11:19], x["step"], x["service"] or "", x["card_used_mib"], x["card_used_delta_mib"], x["windows_shared_mib"])
