"""tool_ceiling_table.py: the lower of two tool runs, the fastest NIM of a shape at a level over the nights, the room
between them and its reading. Small made-up folders with known answers."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import tool_ceiling_table as C  # noqa: E402


def put(path, rps, errors=(), model="org/m"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"requests_per_s": rps, "requests": int(rps * 40), "request_ms": {"p50": 1.0, "p99": 2.0}, "errors": list(errors), "client_cpu": {"cores_used_mean": 2.0}, "inputs": {"sha256": "a" * 64}, "model": model}, f)


def build(tmp_path):
    tool, n1, n2 = str(tmp_path / "tool"), str(tmp_path / "night1"), str(tmp_path / "night2")
    put(os.path.join(tool, "query", "first_c1.json"), 1300.0); put(os.path.join(tool, "query", "second_c1.json"), 1200.0)
    put(os.path.join(tool, "query", "first_c8.json"), 700.0); put(os.path.join(tool, "query", "second_c8.json"), 900.0)
    put(os.path.join(tool, "query", "first_c64.json"), 8000.0); put(os.path.join(tool, "query", "second_c64.json"), 8100.0, errors=[{"count": 2}])
    put(os.path.join(tool, "query", "first_c2.json"), 2000.0)                                         # one run only
    put(os.path.join(n1, "a", "query", "first_c1.json"), 290.0, model="org/a"); put(os.path.join(n1, "b", "query", "first_c1.json"), 110.0, model="org/b")
    put(os.path.join(n2, "a", "query", "first_c1.json"), 300.0, model="org/a")
    put(os.path.join(n1, "a", "query", "first_c8.json"), 418.0); put(os.path.join(n1, "b", "query", "first_c8.json"), 999.0, errors=[{"count": 1}])
    put(os.path.join(n1, "a", "query", "second_c8.json"), 5000.0)                                    # a second container: not used
    put(os.path.join(n1, "a", "query", "first_c64.json"), 420.0); put(os.path.join(n1, "a", "query", "first_c2.json"), 400.0)
    put(os.path.join(n1, "a", "passage", "first_c1.json"), 5.0)                                      # a shape the tool was not run on
    return tool, n1, n2


def test_room_and_reading(tmp_path):
    tool, n1, n2 = build(tmp_path); T = C.table(tool, [n1, n2]); L = T["shapes"]["query"]["levels"]
    assert list(T["shapes"]) == ["query"] and sorted(L) == [1, 2, 8, 64]
    assert L[1]["tool"]["lower"] == 1200.0 and L[1]["fastest_nim"]["requests_per_s"] == 300.0 and L[1]["fastest_nim"]["night"] == "night2" and L[1]["fastest_nim"]["arm"] == "a"
    assert L[1]["room"] == 4.0 and L[1]["reading"] == "the tool had room"
    assert L[8]["tool"]["lower"] == 700.0 and L[8]["fastest_nim"]["requests_per_s"] == 418.0 and L[8]["room"] == 1.67 and L[8]["reading"].startswith("near the tool's ceiling")
    assert L[64]["tool"]["lower"] is None and L[64]["room"] is None and L[64]["reading"] is None            # one run had errors
    assert L[2]["tool"]["lower"] is None and L[2]["room"] is None                                           # one run only
    assert T["shapes"]["query"]["lowest_room"] == 1.67 and T["shapes"]["query"]["levels_near_the_tools_ceiling"] == [8]
    md = open(os.path.join(tool, "table.md"), encoding="utf-8").read()
    assert "(errors)" in md and "not read" in md and "a, night2" in md
    assert json.load(open(os.path.join(tool, "table.json"), encoding="utf-8"))["nights"] == ["night1", "night2"]


def test_exactly_twice_is_room(tmp_path):
    tool, n1 = str(tmp_path / "tool"), str(tmp_path / "n")
    put(os.path.join(tool, "passages_10", "first_c1.json"), 100.0); put(os.path.join(tool, "passages_10", "second_c1.json"), 120.0)
    put(os.path.join(n1, "r", "passages_10", "first_c1.json"), 50.0)
    r = C.table(tool, [n1])["shapes"]["passages_10"]["levels"][1]
    assert r["room"] == 2.0 and r["reading"] == "the tool had room"


def test_no_nim_level_is_not_read(tmp_path):
    tool, n1 = str(tmp_path / "tool"), str(tmp_path / "n")
    put(os.path.join(tool, "query", "first_c4.json"), 100.0); put(os.path.join(tool, "query", "second_c4.json"), 100.0); os.makedirs(n1)
    T = C.table(tool, [n1])
    assert T["shapes"]["query"]["levels"][4]["room"] is None and T["shapes"]["query"]["lowest_room"] is None
