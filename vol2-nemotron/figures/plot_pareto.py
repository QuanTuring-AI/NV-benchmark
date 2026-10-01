#!/usr/bin/env python3
"""Vol.2 · two figures drawn from published concurrency sweeps: total output throughput against per-user output speed.

  pareto_chat.png / .svg   chat-shaped requests (200 tokens in / 200 out)
  pareto_rag.png  / .svg   RAG-shaped requests (3,500 in / 500 out)
  pareto_points.json       every point with its source file, line and keys

Nothing is measured here. Every point is one row of a published levels.jsonl:
  x  per-user output speed  = 1000 / summary.inter_token_latency.avg   (ms -> tok/s per user; AIPerf's mean)
  y  total output throughput = summary.output_token_throughput.avg       (tok/s)
A marker is hollow when summary.time_to_first_token.p99 > 2,000 ms (outside the MLPerf server target on TTFT). The
dashed vertical line is 10 tok/s per user, the speed that corresponds to 100 ms per output token; the target itself is
on the p99, the axis is the mean.

Which rows are points (the rules, applied by select()):
  - a measured level of the main container: not a discarded warm-up level, not a sentinel probe, not a fresh-container
    repeat, not a skipped-levels record;
  - in results/p80_rerun, a level run twice is taken from its second run, and a level that the run's arm-health rule
    made null (events.jsonl, kind level_null) is not drawn; it is listed under "not_drawn";
  - a level with no result because the engine had exited has no coordinates: it is listed under "engine_exits" and
    named in a note beside the last point of its line (the cross is in the note, not at a position).
  Runs that were stopped and not published are not in this repository and cannot be drawn.

Which sweep is the solid line: the one the Vol.2 README's table takes its number from (its claim-to-evidence table).
The same sweep on another night is drawn faint, without a line.
  Nemotron 3 Nano, chat and RAG   solid results/p55_concurrency_a2_256   faint results/p80_rerun (s256_C, s256_R)
  Nemotron Nano 9B v2, chat       solid results/p80_rerun (v2_A1_C)       faint results/p53_concurrency_v2
  Nemotron Nano 9B v2, RAG        solid results/p53_concurrency_v2        faint results/p80_rerun (v2_A1_R)

Checks done on every run (exit code 1 if one fails):
  - every point in pareto_points.json is read back from its source file, line and keys and must be equal;
  - the largest level inside the server target on each solid line equals the published ceiling (128, 8, 8, 4), read from
    the analysis files the README's table points to;
  - every number written on a figure is in pareto_points.json.
usage: plot_pareto.py            draw, write pareto_points.json, check
       plot_pareto.py check      check the existing pareto_points.json against the sources (no drawing)
       plot_pareto.py self_test
PNG bytes are reproducible with the same matplotlib version (recorded in pareto_points.json).
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOL = os.path.dirname(HERE)
RES = "results"
SLO_TTFT_MS, SLO_ITL_MS, SLO_USER_TOK_S = 2000.0, 100.0, 10.0
MODELS = {"N3": {"label": "Nemotron 3 Nano (NVFP4, NIM 2.0.12, 256 sequences)", "color": "#0072B2", "marker": "o"},
          "A1": {"label": "Nemotron Nano 9B v2 (bf16, NIM 1.12.2, 32 sequences)", "color": "#D55E00", "marker": "s"}}
FIGURES = {"chat": {"title": "Chat-shaped requests (200 tokens in / 200 out)", "profile": "C"},
           "rag": {"title": "RAG-shaped requests (3,500 tokens in / 500 out)", "profile": "R"}}
SERIES = [  # figure, model, role, run directory, row filter
    ("chat", "N3", "article", "p55_concurrency_a2_256", {"arm": "A2", "profile": "C"}),
    ("chat", "N3", "other night", "p80_rerun", {"group": "s256_C"}),
    ("chat", "A1", "article", "p80_rerun", {"group": "v2_A1_C"}),
    ("chat", "A1", "other night", "p53_concurrency_v2", {"arm": "A1", "profile": "C"}),
    ("rag", "N3", "article", "p55_concurrency_a2_256", {"arm": "A2", "profile": "R"}),
    ("rag", "N3", "other night", "p80_rerun", {"group": "s256_R"}),
    ("rag", "A1", "article", "p53_concurrency_v2", {"arm": "A1", "profile": "R"}),
    ("rag", "A1", "other night", "p80_rerun", {"group": "v2_A1_R"}),
]
PUBLISHED_CEILINGS = {  # (figure, model) -> (file, path to the published largest level inside the server target)
    ("chat", "N3"): ("p55_concurrency_a2_256/analysis.json", ["sweeps", "A2|C|main", "conclusions", "max_concurrency_within_server_slo"]),
    ("rag", "N3"): ("p55_concurrency_a2_256/analysis.json", ["sweeps", "A2|R|main", "conclusions", "max_concurrency_within_server_slo"]),
    ("chat", "A1"): ("p80_rerun/slo_ceilings.json", ["groups", "v2_A1_C", "p80", "conclusions", "max_concurrency_within_server_slo"]),
    ("rag", "A1"): ("p53_concurrency_v2/analysis.json", ["sweeps", "A1|R|main", "conclusions", "max_concurrency_within_server_slo"]),
}
X_TICKS, Y_TICKS = [10, 20, 50, 100, 200, 400], [50, 100, 200, 500, 1000, 2000, 5000]
LABEL_OFFSET = {  # (figure, model, concurrency) -> offset of the concurrency label in points; the default is (6, 6)
    ("chat", "N3", 256): (-4, 11), ("chat", "N3", 512): (-27, -4),
    ("rag", "N3", 1): (5, -14), ("rag", "N3", 2): (5, -14), ("rag", "N3", 4): (5, -14), ("rag", "N3", 8): (5, -14), ("rag", "N3", 16): (5, -14),
    ("rag", "N3", 32): (5, -14), ("rag", "N3", 64): (5, -14), ("rag", "N3", 128): (5, -14), ("rag", "N3", 256): (-2, -15), ("rag", "N3", 512): (-27, -4),
}
BOUNDARY = "One RTX 5090 · synthetic prompts · closed loop · NIM 2.0.12 (Nemotron 3 Nano, NVFP4) / NIM 1.12.2 (Nemotron Nano 9B v2, bf16)"
jl = lambda p: [(i, json.loads(l)) for i, l in enumerate(open(p, encoding="utf-8"), 1) if l.strip()]  # noqa: E731


def value(row, keys):
    v = row
    for k in keys:
        v = v[k]
    return v


def point_from(row):
    s = row["summary"]
    err = s.get("error_request_count")
    return {"per_user_tok_s": 1000.0 / s["inter_token_latency"]["avg"], "total_tok_s": s["output_token_throughput"]["avg"],
            "ttft_p99_ms": s["time_to_first_token"]["p99"], "itl_p99_ms": s["inter_token_latency"]["p99"],
            "failed_requests": (err.get("avg") if isinstance(err, dict) else err) or 0}


def select(run, flt, keep="last"):
    """The rows of one sweep that are points, the engine exits and the levels not drawn."""
    d = os.path.join(VOL, RES, run)
    rows = jl(os.path.join(d, "levels.jsonl"))
    nulls = set()
    if "group" in flt and os.path.exists(os.path.join(d, "events.jsonl")):
        nulls = {e["concurrency"] for _, e in jl(os.path.join(d, "events.jsonl")) if e.get("kind") == "level_null" and e.get("group") == flt["group"]}
    by_n, exits = {}, []
    for line, r in rows:
        if r.get("warmup") or r.get("sentinel") or "skipped_levels" in r or r.get("concurrency") is None:
            continue
        if r.get("container", "main") != "main" or any(r.get(k) != v for k, v in flt.items()):
            continue
        if not r.get("summary"):
            exits.append({"concurrency": r["concurrency"], "source": f"{RES}/{run}/levels.jsonl", "line": line,
                          "reason": "no result: the engine had exited" if r.get("engine_dead") else "no result"})
            continue
        if keep == "first" and r["concurrency"] in by_n:
            continue
        by_n[r["concurrency"]] = (line, r)
    not_drawn = [{"concurrency": n, "source": f"{RES}/{run}/levels.jsonl", "line": by_n[n][0], "reason": "null by the run's arm-health rule (events.jsonl, level_null)"} for n in sorted(nulls) if n in by_n]
    pts = []
    for n in sorted(by_n):
        if n in nulls:
            continue
        line, r = by_n[n]
        pts.append(dict({"concurrency": n, "source": f"{RES}/{run}/levels.jsonl", "line": line}, **point_from(r)))
    return pts, exits, not_drawn


def build():
    out = {"what": "the points of pareto_chat and pareto_rag; x = 1000 / summary.inter_token_latency.avg, y = summary.output_token_throughput.avg, hollow marker when summary.time_to_first_token.p99 > 2000 ms",
           "keys": {"per_user_tok_s": "1000 / summary.inter_token_latency.avg", "total_tok_s": "summary.output_token_throughput.avg",
                    "ttft_p99_ms": "summary.time_to_first_token.p99", "itl_p99_ms": "summary.inter_token_latency.p99", "failed_requests": "summary.error_request_count.avg"},
           "slo": {"ttft_p99_ms": SLO_TTFT_MS, "itl_p99_ms": SLO_ITL_MS, "dashed_line_tok_s_per_user": SLO_USER_TOK_S},
           "axis_ticks": {"x": X_TICKS, "y": Y_TICKS}, "series": []}
    for fig, model, role, run, flt in SERIES:
        pts, exits, nd = select(run, flt)
        for p in pts:
            p["inside_server_target_on_ttft"] = p["ttft_p99_ms"] <= SLO_TTFT_MS
        out["series"].append({"figure": fig, "model": model, "model_label": MODELS[model]["label"], "role": role, "run": f"{RES}/{run}", "filter": flt,
                              "points": pts, "engine_exits": exits, "not_drawn": nd})
    return out


def ceiling(points):
    ok = [p["concurrency"] for p in points if p["ttft_p99_ms"] <= SLO_TTFT_MS and p["itl_p99_ms"] <= SLO_ITL_MS and not p["failed_requests"]]
    return max(ok) if ok else 0


def check(data):
    """Read every point back from its source; compare the solid lines' ceilings with the published ones."""
    problems, cache, n = [], {}, 0
    for s in data["series"]:
        for p in s["points"]:
            path = os.path.join(VOL, p["source"])
            if path not in cache:
                cache[path] = dict(jl(path))
            want = point_from(cache[path][p["line"]])
            n += 1
            if cache[path][p["line"]].get("concurrency") != p["concurrency"]:
                problems.append(f"{p['source']} line {p['line']}: concurrency {cache[path][p['line']].get('concurrency')} != {p['concurrency']}")
            for k, v in want.items():
                if abs(v - p[k]) > 1e-9 * max(1.0, abs(v)):
                    problems.append(f"{p['source']} line {p['line']} {k}: source {v} != table {p[k]}")
        if s["role"] == "article":
            f, keys = PUBLISHED_CEILINGS[(s["figure"], s["model"])]
            pub = value(json.load(open(os.path.join(VOL, RES, f), encoding="utf-8")), keys)
            got = ceiling(s["points"])
            if got != pub:
                problems.append(f"{s['figure']} {s['model']}: largest level inside the server target from the points is {got}, published {pub} ({RES}/{f})")
    return n, problems


def labels_on(data, fig):
    """Every number written on one figure (concurrency labels, the exit notes, the dashed line) -> must be in the table."""
    nums = {str(int(SLO_USER_TOK_S))}
    for s in data["series"]:
        if s["figure"] == fig and s["role"] == "article":
            nums |= {str(p["concurrency"]) for p in s["points"]} | {str(e["concurrency"]) for e in s["engine_exits"]}
    return nums


def draw(data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.hashsalt": "vol2-pareto", "svg.fonttype": "path"})
    written = {}
    for fig_key, spec in FIGURES.items():
        fig, ax = plt.subplots(figsize=(8.0, 5.6), dpi=200)
        drawn = {str(int(SLO_USER_TOK_S))}
        ax.axvline(SLO_USER_TOK_S, color="0.35", linestyle="--", linewidth=1.0, zorder=1)
        ax.text(SLO_USER_TOK_S * 1.04, 5300, "10 tok/s per user\n(100 ms per output token)", fontsize=7.5, color="0.25", va="top", ha="left")
        for s in [x for x in data["series"] if x["figure"] == fig_key]:
            m = MODELS[s["model"]]; pts = s["points"]; solid = s["role"] == "article"
            alpha = 1.0 if solid else 0.35
            if solid:
                ax.plot([p["per_user_tok_s"] for p in pts], [p["total_tok_s"] for p in pts], color=m["color"], linewidth=1.6, zorder=2)
            for p in pts:
                inside = p["ttft_p99_ms"] <= SLO_TTFT_MS
                ax.plot([p["per_user_tok_s"]], [p["total_tok_s"]], linestyle="none", marker=m["marker"], markersize=7.5 if solid else 6.0,
                        markerfacecolor=m["color"] if inside else "white", markeredgecolor=m["color"], markeredgewidth=1.4, alpha=alpha, zorder=3 if solid else 2.5)
                if solid:
                    ax.annotate(str(p["concurrency"]), (p["per_user_tok_s"], p["total_tok_s"]), textcoords="offset points", xytext=LABEL_OFFSET.get((fig_key, s["model"], p["concurrency"]), (6, 6)), fontsize=8.5, color=m["color"])
                    drawn.add(str(p["concurrency"]))
            if solid and s["engine_exits"] and pts:
                e = s["engine_exits"][0]; last = pts[-1]
                ax.annotate(f"× {e['concurrency']}: engine exit, no result", (last["per_user_tok_s"], last["total_tok_s"]), textcoords="offset points", xytext=(-8, 14),
                            fontsize=8, color=m["color"], ha="right")
                drawn.add(str(e["concurrency"]))
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlim(8.5, 450); ax.set_ylim(20, 6000)  # room under the lowest points for the legend
        plain = FuncFormatter(lambda v, _: f"{int(v):,}")
        ax.xaxis.set_major_locator(FixedLocator(X_TICKS)); ax.yaxis.set_major_locator(FixedLocator(Y_TICKS))
        ax.xaxis.set_minor_locator(NullLocator()); ax.yaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_major_formatter(plain); ax.yaxis.set_major_formatter(plain)
        ax.grid(True, which="major", color="0.88", linewidth=0.7, zorder=0)
        ax.set_xlabel("Per-user output speed, tok/s per user  (1000 ÷ mean inter-token latency in ms)")
        ax.set_ylabel("Total output throughput, tok/s")
        ax.set_title(spec["title"] + " — each point is one concurrency level", fontsize=11)
        handles = [Line2D([], [], color=MODELS[k]["color"], marker=MODELS[k]["marker"], markersize=7, linewidth=1.6, label=MODELS[k]["label"]) for k in ("N3", "A1")]
        handles += [Line2D([], [], color="0.3", marker="o", markersize=6, linestyle="none", alpha=0.35, label="faint: the same sweep on another night"),
                    Line2D([], [], color="0.3", marker="o", markersize=7, linestyle="none", markerfacecolor="white", label="hollow: p99 time to first token > 2 s")]
        ax.legend(handles=handles, loc="lower right", fontsize=8, frameon=True, framealpha=0.95)
        fig.text(0.5, 0.012, BOUNDARY, ha="center", va="bottom", fontsize=7.2, style="italic", color="0.25")
        fig.subplots_adjust(left=0.10, right=0.975, top=0.93, bottom=0.135)
        fig.savefig(os.path.join(HERE, f"pareto_{fig_key}.png"), dpi=200, metadata={"Software": None})
        svg = os.path.join(HERE, f"pareto_{fig_key}.svg")
        fig.savefig(svg, metadata={"Date": None, "Creator": None})
        raw = open(svg, "rb").read().replace(b"\r\n", b"\n")  # the same bytes on every platform
        open(svg, "wb").write(raw)
        plt.close(fig)
        written[fig_key] = drawn
    return written, matplotlib.__version__


def self_test():
    ok = True

    def t(name, got, want):
        nonlocal ok
        good = got == want; ok = ok and good
        print(("  PASS " if good else "  FAIL ") + f"{name}: {got} (want {want})")
    data = build()
    n, problems = check(data)
    t("every point reads back from its source", (n > 0, problems), (True, []))
    bad = json.loads(json.dumps(data)); bad["series"][0]["points"][3]["total_tok_s"] += 1.0
    t("negative control: one value changed -> the check reports it", len(check(bad)[1]), 1)
    bad = json.loads(json.dumps(data)); bad["series"][0]["points"] = bad["series"][0]["points"][:7]
    t("negative control: the 128 point removed -> the ceiling no longer matches the published one", len(check(bad)[1]), 1)
    s = next(x for x in data["series"] if x["run"].endswith("p80_rerun") and x["filter"] == {"group": "v2_A1_R"})
    t("a level run twice is taken from its second run (v2_A1_R c=16 is line 65)", next(p["line"] for p in s["points"] if p["concurrency"] == 16), 65)
    first, _, _ = select("p80_rerun", {"group": "v2_A1_R"}, keep="first")
    t("mutation: keep the first run -> line 63", next(p["line"] for p in first if p["concurrency"] == 16), 63)
    t("the null level (32) is not a point and is listed", (32 in [p["concurrency"] for p in s["points"]], [x["concurrency"] for x in s["not_drawn"]]), (False, [32]))
    t("the engine exit of v2_A1_C is listed with no coordinates", [e["concurrency"] for e in next(x for x in data["series"] if x["filter"] == {"group": "v2_A1_C"})["engine_exits"]], [16])
    t("fresh-container repeats are not points (p55 chat has 10 levels)", len(data["series"][0]["points"]), 10)
    t("hollow rule: p55 chat c=128 inside, c=256 outside", [p["inside_server_target_on_ttft"] for p in data["series"][0]["points"] if p["concurrency"] in (128, 256)], [True, False])
    print("SELF-TEST " + ("PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "draw"
    if mode == "self_test":
        sys.exit(0 if self_test() else 1)
    table = os.path.join(HERE, "pareto_points.json")
    if mode == "check":
        data = json.load(open(table, encoding="utf-8"))
    else:
        data = build()
        written, version = draw(data)
        data["matplotlib_version"] = version
        data["numbers_on_figures"] = {k: sorted(v, key=int) for k, v in written.items()}
        json.dump(data, open(table, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    n, problems = check(data)
    for fig in FIGURES:  # every number written on a figure is in the table
        extra = set(data.get("numbers_on_figures", {}).get(fig, [])) - labels_on(data, fig)
        if extra:
            problems.append(f"{fig}: numbers on the figure that are not in the table: {sorted(extra)}")
    for p in problems:
        print("  FAIL", p)
    print(f"{'drawn and ' if mode != 'check' else ''}checked: {n} points in {len(data['series'])} series, problems {len(problems)}")
    sys.exit(1 if problems else 0)
