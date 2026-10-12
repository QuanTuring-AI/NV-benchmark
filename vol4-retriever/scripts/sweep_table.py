#!/usr/bin/env python3
"""Vol.4 · the tables of the concurrency sweep, from the level records (one small file per level).

Per arm and request shape: one row per level of the first container, and beside it the same level of the second
container where that one ran it. Then, per arm and shape, read by the rules of the pre-registration:
  saturation    the lowest level whose rate is at least 95% of the highest rate of that shape in that container;
                levels with errors and levels marked client-limited are not used
  described     the highest level whose p99 is at most 100 ms, and at most 500 ms (two round numbers; nothing is judged)
  client-limited  a level at which the load-tool container used 85% or more of all the cores it can see
  level held    requests per second times the mean duration of a request is the mean number of requests that were in
                flight. A load tool that cannot keep up sends late, and that product falls below the level it was asked
                to hold; a level whose product is below 90% of the level is listed as not held. (The share of all cores
                alone would miss a tool that is limited by one of its processes.) Not read where a request lasts
                more than 5% of the level's duration: requests still in flight when the level ends are not counted,
                and the product is then too low for that reason alone.
The rows are AIPerf's own figures as sweep_level.py kept them; nothing is recomputed from single requests.

usage: sweep_table.py [RESULTS_DIR]     writes table.json and table.md into the results folder
"""
import hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(VOL, "results", "concurrency_sweep")
SHAPES = ("query", "passage", "passages_100", "passages_10")
CLIENT_LIMIT, SAT, DESCRIBED, HELD, LONG = 0.85, 0.95, (100, 500), 0.90, 0.05


def levels(arm, shape, label):
    d = os.path.join(RES, arm, shape); out = {}
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = re.fullmatch(rf"{label}_c(\d+)\.json", f)
        if m:
            r = json.load(open(os.path.join(d, f), encoding="utf-8")); cpu = r.get("client_cpu") or {}; c = int(m.group(1))
            held = round(r["requests_per_s"] * r["request_ms"]["avg"] / 1000.0, 2) if r.get("requests_per_s") and r.get("request_ms") else None
            out[c] = {"requests_per_s": r.get("requests_per_s"), "items_per_s": r.get("items_per_s"), "request_ms": r.get("request_ms"), "requests": r.get("requests"),
                      "in_flight_by_rate_times_mean_duration": held, "level_held": None if held is None or r["request_ms"]["avg"] / 1000.0 > LONG * (r.get("benchmark_duration_s") or 0) else bool(held >= HELD * c),
                                    "errors": sum(e.get("count", 1) if isinstance(e, dict) else 1 for e in (r.get("errors") or [])), "aiperf_rc": r.get("aiperf_rc"),
                                    "client_share_of_all_cores": cpu.get("share_of_all_cores"), "client_cores_used_mean": cpu.get("cores_used_mean"),
                                    "client_limited": bool(cpu.get("share_of_all_cores") is not None and cpu["share_of_all_cores"] >= CLIENT_LIMIT), "start": r.get("start"), "items_per_request": r.get("items_per_request")}
    return dict(sorted(out.items()))


def per_request(arm):
    """Embedding arms: the duration of one request of 64 passages as each instrument measured it, one in flight, and
    the time per request that the own client's rate implies (which also holds what the client does between requests).
    -> dict or None (a reranking arm's own client keeps no per-request duration)"""
    own, lvl = os.path.join(RES, arm, "calibration_own_client.json"), os.path.join(RES, arm, "passage", "first_c1.json")
    if not (os.path.isfile(own) and os.path.isfile(lvl)):
        return None
    o, a = json.load(open(own, encoding="utf-8")), json.load(open(lvl, encoding="utf-8"))
    if "per_request_seconds" not in o or not a.get("request_ms"):
        return None
    mine, theirs = o["per_request_seconds"]["p50"] * 1000.0, a["request_ms"]["p50"]
    return {"own_client_p50_ms": round(mine, 1), "aiperf_c1_p50_ms": round(theirs, 1), "difference_percent": round((theirs / mine - 1) * 100, 2),
            "own_client_ms_per_request_implied_by_its_rate": round(o["batch"] / o["passages_per_s_median"] * 1000.0, 1), "own_client_requests_timed": o["per_request_seconds"]["count"]}


def read(L):
    ok = {c: r for c, r in L.items() if r["requests_per_s"] and not r["errors"] and not r["client_limited"]}
    if not ok:
        return {"saturation_level": None, "note": "no level without errors and not client-limited"}
    top = max(r["requests_per_s"] for r in ok.values())
    sat = min(c for c, r in ok.items() if r["requests_per_s"] >= SAT * top)
    out = {"highest_requests_per_s": top, "highest_items_per_s": max(r["items_per_s"] for r in ok.values()), "saturation_level": sat,
           "rate_at_one_in_flight": ok.get(1, {}).get("requests_per_s"), "rise_from_one_to_the_highest": round(top / ok[1]["requests_per_s"], 2) if 1 in ok else None}
    for ms in DESCRIBED:
        within = [c for c, r in L.items() if r["request_ms"] and r["request_ms"]["p99"] <= ms and not r["errors"]]
        out[f"highest_level_with_p99_at_most_{ms}_ms"] = max(within) if within else None
    out["levels_with_errors"] = [c for c, r in L.items() if r["errors"]]; out["levels_client_limited"] = [c for c, r in L.items() if r["client_limited"]]
    out["levels_not_held"] = [c for c, r in L.items() if r["level_held"] is False]
    out["lowest_share_of_a_level_held"] = min((round(r["in_flight_by_rate_times_mean_duration"] / c, 3) for c, r in L.items() if r["level_held"] is not None), default=None)
    return out


def main():
    arms = sorted(a for a in os.listdir(RES) if os.path.isdir(os.path.join(RES, a)) and os.path.isfile(os.path.join(RES, a, "payloads.json")))
    T = {"what": "the concurrency sweep of the retrieval NIMs: AIPerf's figures per level", "rules": {"saturation_share": SAT, "client_limit_share_of_cores": CLIENT_LIMIT, "described_p99_ms": list(DESCRIBED)}, "arms": {}}
    md = []
    for arm in arms:
        A = {"model": json.load(open(os.path.join(RES, arm, "payloads.json"), encoding="utf-8"))["model"], "shapes": {}}
        cal = os.path.join(RES, arm, "calibration.json")
        A["calibration"] = json.load(open(cal, encoding="utf-8")) if os.path.isfile(cal) else None
        A["calibration_per_request"] = per_request(arm)
        for shape in SHAPES:
            first, second = levels(arm, shape, "first"), levels(arm, shape, "second")
            if not first:
                continue
            A["shapes"][shape] = {"first_container": first, "second_container": second, "reading_first_container": read(first)}
            md += [f"### {arm} · {A['model']} · {shape}", "", "| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |", "|---|---|---|---|---|---|---|---|---|---|"]
            for c, r in first.items():
                q = r["request_ms"] or {}; s = second.get(c)
                md.append(f"| {c} | {r['requests_per_s']} | {r['items_per_s']} | {q.get('p50')} | {q.get('p90')} | {q.get('p99')} | {r['requests']} | {r['errors']} | {r['client_cores_used_mean']}{' (client-limited)' if r['client_limited'] else ''} | "
                          + (f"{s['requests_per_s']} · {(s['request_ms'] or {}).get('p99')}" if s else "") + " |")
            rd = A["shapes"][shape]["reading_first_container"]
            md += ["", "Read by the rules: " + json.dumps(rd), ""]
        if A["shapes"]:
            T["arms"][arm] = A
    T["program"] = {"file": "sweep_table.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}
    json.dump(T, open(os.path.join(RES, "table.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    open(os.path.join(RES, "table.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    print(json.dumps({a: {s: v["reading_first_container"].get("saturation_level") for s, v in A["shapes"].items()} for a, A in T["arms"].items()}))


if __name__ == "__main__":
    main()
