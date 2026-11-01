#!/usr/bin/env python3
"""Vol.5 · the state of the two Elasticsearch indexes when each result was taken: minutes after the bulk load, the
segment listing of the HotpotQA index on 2026-10-20 and on 2026-11-01, and what the second query of each index
returned. Read from the result files of this folder; written to results/index_state.json.

  hotpotqa   loaded and first queried (night 1); the segment listings of day 3 and of 2026-11-01 compared row by row
             (every column but the container's IP address); the first query against the settled one (top 100 per
             question); the default query's scores on the settled index (day 3)
  miracl_zh  loaded and first queried (day 3); the second query, inside night 3's window; the two compared; the second
             query's scores. The index was deleted on 2026-10-22, so no later state exists
  cold_latency_files   (--stat-latency-files only) the modification times of the cold-start latency files on the host
             that measured them. The latency runs printed their times to a console that was not kept; a fresh clone
             has the checkout time instead, so this block is written only on that host

usage: index_state.py [--stat-latency-files]
"""
import argparse, datetime as dt, json, os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(HERE, "results")


def events(path):
    return [json.loads(l) for l in open(os.path.join(R, path), encoding="utf-8") if l.strip()]


def at(evs, kind, **match):
    hits = [e for e in evs if e["kind"] == kind and all(e.get(k) == v for k, v in match.items())]
    if len(hits) != 1:
        raise ValueError(f"expected one event {kind} {match}, found {len(hits)}")
    return hits[0]


def t(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def minutes(a, b):
    return round((t(b) - t(a)).total_seconds() / 60, 1)


def segments(path):
    rows = [l.split() for l in open(os.path.join(R, path), encoding="utf-8") if l.strip()]
    head = rows[0]; ip = head.index("ip")
    return head, [[c for i, c in enumerate(r) if i != ip] for r in rows[1:]]


def load(path):
    return json.load(open(os.path.join(R, path), encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stat-latency-files", action="store_true"); a = ap.parse_args()
    n1, d3, n3 = events("night1/events.jsonl"), events("day3/events.jsonl"), events("night3/events.jsonl")
    loaded, first_done = at(n1, "c1_loaded")["at"], at(n1, "c1_done")["at"]
    h1, s1 = segments("day3/hotpotqa_whole_segments.txt"); h2, s2 = segments("day3/hotpotqa_whole_segments_20261101.txt")
    if h1 != h2:
        raise ValueError("the two segment listings do not have the same columns")
    first_vs_settled = load("night3/c1_clean_vs_first.json"); settled = load("day3/nc_blueprint_100_now_score.json")["metrics"]
    clean_start, clean_end = at(n3, "step_start", step="clean window")["at"], at(n3, "clean_done")["at"]
    zl, zd = at(d3, "zh_loaded")["at"], at(d3, "zh_done")["at"]
    zh_vs = load("night3/zh_clean_vs_day.json"); zh2 = load("night3/zh_clean_score.json")
    rec = {
        "hotpotqa": {
            "bulk_load_finished": loaded, "first_query_step_finished": first_done,
            "first_query_minutes_after_the_load": [0, minutes(loaded, first_done)],
            "segments_2026_10_20": {"recorded_at": at(d3, "nc_start")["at"], "segments": at(d3, "nc_start")["segments"], "file": "results/day3/hotpotqa_whole_segments.txt"},
            "segments_2026_11_01": {"recorded_at": "2026-11-01T16:58:57+0800", "segments": len(s2), "file": "results/day3/hotpotqa_whole_segments_20261101.txt"},
            "segment_listings_equal_but_the_ip_column": s1 == s2, "segment_rows_compared": len(s1),
            "first_query_against_the_settled_index": {"questions": first_vs_settled["questions"], "different_top_100": first_vs_settled["different_sets"],
                                                      "share": first_vs_settled["different_sets"] / first_vs_settled["questions"], "file": "results/night3/c1_clean_vs_first.json"},
            "default_query_on_the_settled_index": {"ndcg_cut_10": settled["ndcg_cut_10"], "recall_100": settled["recall_100"], "file": "results/day3/nc_blueprint_100_now_score.json"}},
        "miracl_zh": {
            "bulk_load_finished": zl, "first_query_step_finished": zd, "first_query_minutes_after_the_load": [0, minutes(zl, zd)],
            "second_query_window": [clean_start, clean_end], "second_query_minutes_after_the_load": [minutes(zl, clean_start), minutes(zl, clean_end)],
            "first_against_second": {"questions": zh_vs["questions"], "different_top_100": zh_vs["different_sets"], "share": zh_vs["different_sets"] / zh_vs["questions"],
                                     "file": "results/night3/zh_clean_vs_day.json"},
            "second_query_scores": {"ndcg_cut_10": zh2["metrics"]["ndcg_cut_10"], "recall_100": zh2["metrics"]["recall_100"], "file": "results/night3/zh_clean_score.json"},
            "segments_at_load": {"file": "results/day3/zh_segments.txt"},
            "later_state": "none: the index was deleted on 2026-10-22"}}
    if a.stat_latency_files:
        d = os.path.join(R, "night3", "latency_cold")
        files = {f: dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(d, f))).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z") for f in sorted(os.listdir(d))}
        rec["cold_latency_files"] = {"what": "modification times on the measuring host (each file is written when its run ends)", "files": files,
                                     "zh_hours_after_the_load": round((t(files["zh_blueprint_100.json"]) - t(zl)).total_seconds() / 3600, 1),
                                     "hotpotqa_first_after_the_2026_10_20_segment_listing_hours": round((min(t(v) for k, v in files.items() if not k.startswith("zh")) - t(at(d3, "nc_start")["at"])).total_seconds() / 3600, 1)}
    json.dump(rec, open(os.path.join(R, "index_state.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(rec)[:1500])


if __name__ == "__main__":
    main()
