#!/usr/bin/env python3
"""Vol.4 · the concurrency sweep on a second night: the calibration by the duration of a request, and the table that
sets two nights side by side.

  calibration ARM_DIR
        The load tool at one request in flight beside this volume's own client, read two ways from the same two files:
          by duration   p50 of one request: the own client's (embed_cell.py times every request of its passes;
                        rerank_latency.py every call) against AIPerf's at one in flight. The rule of the second
                        night: more than 20% apart (the difference rounded to two decimals) stops the arm.
          by rate       items per second, the rule of the first night, kept in the record and reported as it was.
        The own client's rate is items divided by the wall time of a pass, and that wall time also holds what the
        client does between two requests; the duration of a request does not. Writes ARM_DIR/calibration_per_request.json.
        exit codes: 0 within 20% by duration · 1 outside · 2 not computable
  table NIGHT1_DIR NIGHT2_DIR
        Every level the second night ran in a first container, beside the same level of the first night's first
        container where that exists: date, graphics driver, requests and items per second, p50 and p99 of a request,
        and the difference in percent. The driver is the one the run log of that night recorded last before the level
        started; the date is the level's start in the time zone of that run log. A pair whose request bodies differ (SHA-256 in the level records) is marked and not compared.
        Also the calibration of every arm on both nights, by both readings. Writes NIGHT2_DIR/two_nights.json and
        two_nights.md. Nothing is judged: the table says how far apart two nights are.
"""
import datetime, hashlib, json, os, re, sys

LIMIT = 20.0
SHAPES = ("query", "passage", "passages_100", "passages_10")
HELD, LONG = 0.90, 0.05          # as sweep_table.py: a level is held if rate x mean duration >= 90% of it; not read for long requests


def load(path):
    return json.load(open(path, encoding="utf-8"))


def calibration(arm_dir):
    """-> (record, exit code)"""
    try:
        own = load(os.path.join(arm_dir, "calibration_own_client.json"))
        if "per_request_seconds" in own:                     # embed_cell.py throughput
            shape, mine_ms, mine_rate, n = "passage", own["per_request_seconds"]["p50"] * 1000.0, own["passages_per_s_median"], own["per_request_seconds"]["count"]
        else:                                                # rerank_latency.py
            p = own["passes"][0]; shape, mine_ms, mine_rate, n = "passages_100", p["call_ms"]["p50"], p["pairs_per_s"], p["call_ms"]["calls"]
        lvl = load(os.path.join(arm_dir, shape, "first_c1.json"))
        theirs_ms, theirs_rate = lvl["request_ms"]["p50"], lvl["items_per_s"]
        d_ms, d_rate = (theirs_ms / mine_ms - 1) * 100, (theirs_rate / mine_rate - 1) * 100
    except Exception as e:  # noqa: BLE001  (a missing file or key: the calibration cannot be computed, and that is the record)
        return {"calibration": "not computable", "why": repr(e)[:200]}, 2
    rec = {"what": "AIPerf at one request in flight beside this volume's own client, from the same two files read two ways",
           "shape": shape, "sources": {"own_client": "calibration_own_client.json", "aiperf": f"{shape}/first_c1.json"},
           "by_duration": {"own_client_p50_ms": round(mine_ms, 2), "own_client_requests_timed": n, "aiperf_c1_p50_ms": round(theirs_ms, 2), "difference_percent": round(d_ms, 2),
                           "limit_percent": LIMIT, "within": bool(abs(round(d_ms, 2)) <= LIMIT), "rule_of": "the second night (supplementary pre-registration)"},
           "by_rate": {"own_client_items_per_s": mine_rate, "aiperf_c1_items_per_s": theirs_rate, "difference_percent": round(d_rate, 2), "limit_percent": LIMIT, "within": bool(abs(round(d_rate, 2)) <= LIMIT),
                       "rule_of": "the first night; reported as it was, it does not stop an arm on the second night"},
           "own_client_ms_per_request_implied_by_its_rate": round(lvl["items_per_request"] / mine_rate * 1000.0, 1),
           "program": {"file": "sweep_two_nights.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}}
    return rec, 0 if rec["by_duration"]["within"] else 1


def when(text):
    """A time of a run log or of a level record, with its offset. -> aware datetime"""
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z")


def drivers(night_dir):
    """Every time the run log of a night recorded the graphics driver. -> [(datetime, driver)], oldest first"""
    out = []
    f = os.path.join(night_dir, "events.jsonl")
    for line in open(f, encoding="utf-8") if os.path.isfile(f) else []:
        e = json.loads(line) if line.strip() else {}
        d = (e.get("card") or {}).get("driver"); at = e.get("at") or e.get("end")
        if d and at:
            out.append((when(at), d))
    return sorted(out)


def driver_at(log, start):
    """The driver recorded last before a level started; None if the log has no entry before it."""
    before = [d for t, d in log if t <= start]
    return before[-1] if before else None


def levels(night_dir, arm, shape, log):
    d = os.path.join(night_dir, arm, shape); out = {}
    for f in os.listdir(d) if os.path.isdir(d) else []:
        m = re.fullmatch(r"first_c(\d+)\.json", f)
        if m:
            r = load(os.path.join(d, f)); c = int(m.group(1)); start = when(r["start"]); q = r.get("request_ms") or {}
            held = round(r["requests_per_s"] * q["avg"] / 1000.0, 2) if r.get("requests_per_s") and q else None
            out[c] = {"date": start.astimezone(log[0][0].tzinfo if log else start.tzinfo).strftime("%Y-%m-%d"), "driver": driver_at(log, start), "requests_per_s": r.get("requests_per_s"), "items_per_s": r.get("items_per_s"),
                      "p50_ms": q.get("p50"), "p99_ms": q.get("p99"), "requests": r.get("requests"), "errors": sum(e.get("count", 1) if isinstance(e, dict) else 1 for e in (r.get("errors") or [])),
                      "level_held": None if held is None or q["avg"] / 1000.0 > LONG * (r.get("benchmark_duration_s") or 0) else bool(held >= HELD * c),
                      "inputs_sha256": (r.get("inputs") or {}).get("sha256"), "image_or_url": r.get("url"), "source": f"{arm}/{shape}/{f}"}
    return dict(sorted(out.items()))


def pct(new, old):
    return None if not new or not old else round((new / old - 1) * 100, 2)


def table(n1, n2):
    log1, log2 = drivers(n1), drivers(n2)
    arms = sorted(a for a in os.listdir(n2) if os.path.isdir(os.path.join(n2, a)) and any(os.path.isdir(os.path.join(n2, a, s)) for s in SHAPES))
    T = {"what": "the concurrency sweep on two nights: every first-container level of the second night beside the same level of the first night",
         "nights": {"first": os.path.basename(os.path.normpath(n1)), "second": os.path.basename(os.path.normpath(n2))},
         "drivers_recorded": {"first": sorted({d for _, d in log1}), "second": sorted({d for _, d in log2})}, "arms": {}, "calibration": {}}
    md = ["| NIM | Shape | In flight | Night | Date | Driver | Requests/s | Items/s | p50 ms | p99 ms | Second night against first: rate · p50 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        pay = os.path.join(n2, arm, "payloads.json"); model = load(pay)["model"] if os.path.isfile(pay) else arm
        A = {"model": model, "shapes": {}}
        for shape in SHAPES:
            b = levels(n2, arm, shape, log2)
            if not b:
                continue
            a = levels(n1, arm, shape, log1); rows = {}
            for c, y in b.items():
                x = a.get(c); same = bool(x and x["inputs_sha256"] == y["inputs_sha256"]); usable = bool(same and not x["errors"] and not y["errors"])
                rows[c] = {"first_night": x, "second_night": y, "same_request_bodies": same if x else None,
                           "difference_percent": {"requests_per_s": pct(y["requests_per_s"], x["requests_per_s"]), "p50_ms": pct(y["p50_ms"], x["p50_ms"])} if usable else None}
                for night, r in (("first", x), ("second", y)):
                    if r:
                        diff = rows[c]["difference_percent"]
                        tail = "" if night == "first" else ("no first-night level" if not x else "other request bodies: not compared" if not same else "errors: not compared" if not diff
                                                                 else f"{diff['requests_per_s']:+.1f}% · {diff['p50_ms']:+.1f}%")
                        md.append(f"| {model} | {shape} | {c} | {night} | {r['date']} | {r['driver']} | {r['requests_per_s']} | {r['items_per_s']} | {r['p50_ms']} | {r['p99_ms']} | {tail} |")
            A["shapes"][shape] = rows
        T["arms"][arm] = A
        T["calibration"][arm] = {"first_night": calibration(os.path.join(n1, arm))[0], "second_night": calibration(os.path.join(n2, arm))[0]}
    md += ["", "| NIM | Night | By duration: own client p50 ms · AIPerf p50 ms · difference | By rate: own client · AIPerf items/s · difference |", "|---|---|---|---|"]
    for arm, C in T["calibration"].items():
        for night in ("first_night", "second_night"):
            r = C[night]
            if "by_duration" in r:
                d, q = r["by_duration"], r["by_rate"]
                md.append(f"| {T['arms'][arm]['model']} | {night.split('_')[0]} | {d['own_client_p50_ms']} · {d['aiperf_c1_p50_ms']} · {d['difference_percent']:+.1f}%{'' if d['within'] else ' (outside 20%)'} | "
                          f"{q['own_client_items_per_s']} · {q['aiperf_c1_items_per_s']} · {q['difference_percent']:+.1f}%{'' if q['within'] else ' (outside 20%)'} |")
            else:
                md.append(f"| {T['arms'][arm]['model']} | {night.split('_')[0]} | not computable | |")
    T["program"] = {"file": "sweep_two_nights.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}
    json.dump(T, open(os.path.join(n2, "two_nights.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    open(os.path.join(n2, "two_nights.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    return T


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "calibration":
        rec, rc = calibration(sys.argv[2])
        if rc != 2:
            json.dump(rec, open(os.path.join(sys.argv[2], "calibration_per_request.json"), "w", encoding="utf-8", newline="\n"), indent=1)
        print(json.dumps({k: rec[k] for k in ("by_duration", "by_rate") if k in rec} or rec)); return rc
    if len(sys.argv) == 4 and sys.argv[1] == "table":
        T = table(sys.argv[2], sys.argv[3])
        print(json.dumps({a: {s: sorted(r) for s, r in A["shapes"].items()} for a, A in T["arms"].items()})); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main())
