#!/usr/bin/env python3
"""Vol.4 · the load tool's own ceiling beside the rates of the NIMs it measured.

Reads the level records of the tool against the server that answers at once (results/tool_ceiling: two runs, each
with a new server container) and the level records of the concurrency sweep on its nights, and sets them side by side
per request shape and level:
  tool          requests per second in each of the two runs; the lower one is used
  NIM           the highest requests per second any NIM of that shape reached at that level in a first container, on
                any of the given nights, with the NIM and the night it came from
  room          the tool's lower rate divided by that NIM rate
  reading       room of 2 or more: the tool could have sent at least twice what the fastest NIM took at that level, so
                the tool was not what held that level's rate. Below 2: the level is marked, and a NIM rate at it is
                to be read as "at least".
A tool level with errors is not used. Nothing here says how fast a NIM is; it says what the instrument could do.

usage: tool_ceiling_table.py TOOL_DIR NIGHT_DIR [NIGHT_DIR ...]     writes TOOL_DIR/table.json and table.md
"""
import hashlib, json, os, re, sys

SHAPES = ("query", "passage", "passages_100", "passages_10")
ROOM = 2.0


def level_files(d, label):
    out = {}
    for f in os.listdir(d) if os.path.isdir(d) else []:
        m = re.fullmatch(rf"{label}_c(\d+)\.json", f)
        if m:
            out[int(m.group(1))] = json.load(open(os.path.join(d, f), encoding="utf-8"))
    return dict(sorted(out.items()))


def errors(r):
    return sum(e.get("count", 1) if isinstance(e, dict) else 1 for e in (r.get("errors") or []))


def tool_levels(tool_dir, shape):
    """-> {level: {"first": row, "second": row, "lower": rate or None}}"""
    out = {}
    for label in ("first", "second"):
        for c, r in level_files(os.path.join(tool_dir, shape), label).items():
            q = r.get("request_ms") or {}
            out.setdefault(c, {})[label] = {"requests_per_s": r.get("requests_per_s"), "p50_ms": q.get("p50"), "p99_ms": q.get("p99"), "requests": r.get("requests"), "errors": errors(r),
                                            "tool_cores_used_mean": (r.get("client_cpu") or {}).get("cores_used_mean"), "inputs_sha256": (r.get("inputs") or {}).get("sha256")}
    for c, row in out.items():
        good = [row[k]["requests_per_s"] for k in ("first", "second") if k in row and not row[k]["errors"] and row[k]["requests_per_s"]]
        row["lower"] = min(good) if len(good) == 2 else None
    return dict(sorted(out.items()))


def nim_best(nights, shape):
    """-> {level: {"requests_per_s", "arm", "night", "model"}}: the fastest NIM of that shape at each level"""
    best = {}
    for night in nights:
        for arm in sorted(os.listdir(night)) if os.path.isdir(night) else []:
            for c, r in level_files(os.path.join(night, arm, shape), "first").items():
                if errors(r) or not r.get("requests_per_s"):
                    continue
                if c not in best or r["requests_per_s"] > best[c]["requests_per_s"]:
                    best[c] = {"requests_per_s": r["requests_per_s"], "arm": arm, "night": os.path.basename(os.path.normpath(night)), "model": r.get("model"), "inputs_sha256": (r.get("inputs") or {}).get("sha256")}
    return best


def table(tool_dir, nights):
    T = {"what": "the load tool against a server that answers at once, beside the fastest NIM of each request shape at each level", "room_rule": ROOM,
         "nights": [os.path.basename(os.path.normpath(n)) for n in nights], "shapes": {}}
    md = []
    for shape in SHAPES:
        tool = tool_levels(tool_dir, shape)
        if not tool:
            continue
        nim = nim_best(nights, shape); rows = {}
        md += [f"### {shape}", "", "| In flight | Tool, first run: requests/s | Tool, second run | Fastest NIM at that level: requests/s | Which | Room | Reading |", "|---|---|---|---|---|---|---|"]
        for c, t in tool.items():
            n = nim.get(c); room = round(t["lower"] / n["requests_per_s"], 2) if t["lower"] and n else None
            reading = None if room is None else "the tool had room" if room >= ROOM else "near the tool's ceiling: a NIM rate at this level is at least what was measured"
            rows[c] = {"tool": t, "fastest_nim": n, "room": room, "reading": reading}
            a, b = t.get("first"), t.get("second")
            md.append(f"| {c} | {a['requests_per_s'] if a else ''}{' (errors)' if a and a['errors'] else ''} | {b['requests_per_s'] if b else ''}{' (errors)' if b and b['errors'] else ''} | "
                      f"{n['requests_per_s'] if n else ''} | {(n['arm'] + ', ' + n['night']) if n else 'no NIM level'} | {room if room is not None else ''} | {reading or 'not read'} |")
        md.append("")
        read = [r for r in rows.values() if r["room"] is not None]
        T["shapes"][shape] = {"levels": rows, "lowest_room": min((r["room"] for r in read), default=None), "levels_near_the_tools_ceiling": [c for c, r in rows.items() if r["room"] is not None and r["room"] < ROOM]}
    T["program"] = {"file": "tool_ceiling_table.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}
    json.dump(T, open(os.path.join(tool_dir, "table.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    open(os.path.join(tool_dir, "table.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
    return T


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    T = table(sys.argv[1], sys.argv[2:])
    print(json.dumps({s: {"lowest_room": v["lowest_room"], "near": v["levels_near_the_tools_ceiling"]} for s, v in T["shapes"].items()}))
