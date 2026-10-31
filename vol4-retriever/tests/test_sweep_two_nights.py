"""sweep_two_nights.py: the calibration read by duration and by rate, the driver of a level from the run log, and the
table of two nights. Small made-up folders with known answers; no server and no card."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import sweep_two_nights as W  # noqa: E402


def put(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))


def level(c, rps, p50, start, sha="a" * 64, avg=None, errors=(), items=64, seconds=40.0):
    return {"start": start, "requests_per_s": rps, "items_per_s": rps * items, "items_per_request": items, "benchmark_duration_s": seconds, "requests": int(rps * seconds),
            "request_ms": {"p50": p50, "p90": p50 * 1.1, "p99": p50 * 1.2, "avg": avg if avg is not None else p50}, "errors": list(errors), "inputs": {"sha256": sha}, "url": "http://x:8000", "concurrency": c}


def embedding_arm(d, own_p50_s, own_rate, tool_p50_ms, tool_rps):
    put(os.path.join(d, "calibration_own_client.json"), {"per_request_seconds": {"count": 196, "p50": own_p50_s, "p99": own_p50_s * 2}, "passages_per_s_median": own_rate, "batch": 64})
    put(os.path.join(d, "passage", "first_c1.json"), level(1, tool_rps, tool_p50_ms, "2026-10-11T22:00:00+0000"))


def test_durations_agree_while_rates_do_not(tmp_path):
    d = str(tmp_path / "arm"); embedding_arm(d, 0.050, 800.0, 52.0, 18.0)          # 18 requests/s x 64 = 1,152 items/s against 800
    rec, rc = W.calibration(d)
    assert rc == 0 and rec["by_duration"]["within"] and abs(rec["by_duration"]["difference_percent"] - 4.0) < 1e-9
    assert not rec["by_rate"]["within"] and abs(rec["by_rate"]["difference_percent"] - 44.0) < 1e-9
    assert rec["own_client_ms_per_request_implied_by_its_rate"] == 80.0 and rec["shape"] == "passage"


def test_a_slower_tool_is_outside_too(tmp_path):
    d = str(tmp_path / "arm"); embedding_arm(d, 0.100, 600.0, 75.0, 12.0)          # the tool's request 25% shorter
    rec, rc = W.calibration(d)
    assert rc == 1 and not rec["by_duration"]["within"] and rec["by_duration"]["difference_percent"] == -25.0


def test_exactly_twenty_percent_is_within(tmp_path):
    d = str(tmp_path / "arm"); embedding_arm(d, 0.100, 600.0, 120.0, 8.0)
    rec, rc = W.calibration(d)                                                      # 120 / 100 - 1 is 19.999999999999996 in floating point: the rounded value decides
    assert rc == 0 and rec["by_duration"]["difference_percent"] == 20.0


def test_a_reranking_arm_reads_the_duration_of_a_call(tmp_path):
    d = str(tmp_path / "arm")
    put(os.path.join(d, "calibration_own_client.json"), {"passes": [{"pairs_per_s": 700.0, "call_ms": {"calls": 393, "p50": 140.0}}]})
    put(os.path.join(d, "passages_100", "first_c1.json"), level(1, 7.0, 147.0, "2026-10-11T22:00:00+0000", items=100))
    rec, rc = W.calibration(d)
    assert rc == 0 and rec["shape"] == "passages_100" and abs(rec["by_duration"]["difference_percent"] - 5.0) < 1e-9 and rec["by_duration"]["own_client_requests_timed"] == 393


def test_a_missing_file_is_not_computable(tmp_path):
    d = str(tmp_path / "arm"); os.makedirs(d)
    rec, rc = W.calibration(d)
    assert rc == 2 and rec["calibration"] == "not computable"


def two_nights(tmp_path, sha2="a" * 64, errors2=()):
    n1, n2 = str(tmp_path / "night1"), str(tmp_path / "night2")
    put(os.path.join(n1, "events.jsonl"), "\n".join(json.dumps(e) for e in (
        {"kind": "gate", "at": "2026-10-12T04:00:00+0800", "card": {"driver": "111.11"}}, {"kind": "client", "end": "2026-10-12T04:30:00+0800"},
        {"kind": "gate", "at": "2026-10-12T07:00:00+0800", "card": {"driver": "222.22"}})) + "\n")
    put(os.path.join(n2, "events.jsonl"), json.dumps({"kind": "nim_ready", "at": "2026-10-13T03:00:00+0800", "card": {"driver": "333.33"}}) + "\n")
    for n in (n1, n2):
        put(os.path.join(n, "arm", "payloads.json"), {"model": "org/model"})
    put(os.path.join(n1, "arm", "query", "first_c1.json"), level(1, 100.0, 9.0, "2026-10-11T21:00:00+0000", items=1))      # 05:00 +08 on the 12th: after the first gate, before the second
    put(os.path.join(n1, "arm", "query", "first_c2.json"), level(2, 180.0, 10.0, "2026-10-11T23:30:00+0000", items=1))     # 07:30 +08: after the second gate
    put(os.path.join(n1, "arm", "query", "second_c2.json"), level(2, 999.0, 1.0, "2026-10-11T23:40:00+0000", items=1))     # a second container: not a row
    put(os.path.join(n2, "arm", "query", "first_c1.json"), level(1, 110.0, 8.1, "2026-10-12T19:30:00+0000", sha=sha2, errors=errors2, items=1))
    put(os.path.join(n2, "arm", "query", "first_c4.json"), level(4, 181.0, 20.0, "2026-10-12T19:40:00+0000", items=1))
    return n1, n2


def test_two_nights_side_by_side(tmp_path):
    n1, n2 = two_nights(tmp_path); T = W.table(n1, n2); rows = T["arms"]["arm"]["shapes"]["query"]
    assert sorted(rows) == [1, 4] and T["arms"]["arm"]["model"] == "org/model"
    a = rows[1]
    assert a["first_night"]["driver"] == "111.11" and a["first_night"]["date"] == "2026-10-12" and a["second_night"]["driver"] == "333.33" and a["second_night"]["date"] == "2026-10-13"
    assert a["same_request_bodies"] is True and a["difference_percent"] == {"requests_per_s": 10.0, "p50_ms": -10.0}
    assert rows[4]["first_night"] is None and rows[4]["difference_percent"] is None and rows[4]["same_request_bodies"] is None
    assert T["drivers_recorded"] == {"first": ["111.11", "222.22"], "second": ["333.33"]}
    second = W.levels(n1, "arm", "query", W.drivers(n1))[2]
    assert second["driver"] == "222.22" and second["requests_per_s"] == 180.0          # the first container's level, not the second container's
    assert os.path.isfile(os.path.join(n2, "two_nights.md")) and json.load(open(os.path.join(n2, "two_nights.json")))["nights"] == {"first": "night1", "second": "night2"}


def test_other_request_bodies_are_not_compared(tmp_path):
    n1, n2 = two_nights(tmp_path, sha2="b" * 64); r = W.table(n1, n2)["arms"]["arm"]["shapes"]["query"][1]
    assert r["same_request_bodies"] is False and r["difference_percent"] is None
    assert "other request bodies: not compared" in open(os.path.join(n2, "two_nights.md"), encoding="utf-8").read()


def test_a_level_with_errors_is_not_compared(tmp_path):
    n1, n2 = two_nights(tmp_path, errors2=[{"count": 3}]); r = W.table(n1, n2)["arms"]["arm"]["shapes"]["query"][1]
    assert r["second_night"]["errors"] == 3 and r["difference_percent"] is None


def test_no_driver_before_the_first_entry_of_the_log():
    log = [(W.when("2026-10-12T04:00:00+0800"), "111.11")]
    assert W.driver_at(log, W.when("2026-10-11T19:00:00+0000")) is None and W.driver_at(log, W.when("2026-10-11T20:00:00+0000")) == "111.11"


def test_a_level_is_held_or_not_or_not_readable(tmp_path):
    n = str(tmp_path / "n")
    put(os.path.join(n, "arm", "query", "first_c2.json"), level(2, 300.0, 5.0, "2026-10-12T19:30:00+0000", avg=5.0, items=1))       # 1.5 in flight of 2
    put(os.path.join(n, "arm", "query", "first_c4.json"), level(4, 400.0, 9.5, "2026-10-12T19:31:00+0000", avg=9.5, items=1))       # 3.8 of 4
    put(os.path.join(n, "arm", "query", "first_c64.json"), level(64, 4.0, 13000.0, "2026-10-12T19:32:00+0000", avg=13000.0, items=1))  # a request lasts a third of the level
    L = W.levels(n, "arm", "query", [])
    assert [L[c]["level_held"] for c in (2, 4, 64)] == [False, True, None] and L[2]["driver"] is None
