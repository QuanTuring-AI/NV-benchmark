#!/usr/bin/env python3
"""Vol.2 · two figures drawn from published concurrency sweeps: total output throughput against per-request output speed.

  pareto_chat_light / _dark  (.svg, .png)   chat-shaped requests (200 tokens in / 200 out)
  pareto_rag_light  / _dark  (.svg, .png)   RAG-shaped requests (3,500 in / 500 out)
  pareto_points.json                         every point with its source file, line and keys

Nothing is measured here. Every point is one row of a published levels.jsonl:
  x  per-request output speed = 1000 / summary.inter_token_latency.avg  (ms -> tok/s per request; AIPerf's mean)
  y  total output throughput = summary.output_token_throughput.avg       (tok/s)
A marker is hollow when summary.time_to_first_token.p99 > 2,000 ms (outside the MLPerf server target on TTFT). The
dashed vertical line is 10 tok/s per request, the speed that corresponds to 100 ms per output token; the target itself is
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

Card / social-image layout (the same for every figure of this repository): a 1600 x 900 canvas, the plot area in the
vertical middle 60%, no title (which figure is which is said by the file name and by the README), text kept as text in
the SVG (font 'Space Grotesk', falling back to sans-serif). The light and the dark version differ in colours only.

Checks done on every run (exit code 1 if one fails):
  - every point in pareto_points.json is read back from its source file, line and keys and must be equal;
  - the largest level inside the server target on each solid line equals the published ceiling (128, 8, 8, 4), read from
    the analysis files the README's table points to;
  - every number written on a figure is in pareto_points.json;
  - every drawn point lies inside the central 1.9:1 band of the canvas (what a 1200 x 630 crop keeps);
  - the light and the dark SVG of a figure contain the same text; neither file contains the word "user" (or "users", any case) or "7.3" anywhere
    (text or coordinate, so that a plain search of the file finds nothing); no embedded image.
usage: plot_pareto.py            draw, write pareto_points.json, check
       plot_pareto.py check      check the existing pareto_points.json against the sources (no drawing)
       plot_pareto.py self_test
PNG bytes are reproducible with the same matplotlib version and the same fonts installed (recorded in pareto_points.json).
"""
import json, logging, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOL = os.path.dirname(HERE)
RES = "results"
W, H = 1600, 900
AXES = [0.0865, 0.20, 0.895, 0.60]           # left, bottom, width, height: the plot area is the vertical middle 60%,
                                             # moved by a fraction of a pixel so that no coordinate in an SVG reads "7.3"
BAND = (H - W / 1.9) / 2.0                   # pixels cut at the top and at the bottom by a 1.9:1 crop
# The points file keeps its key names (per_user_tok_s, dashed_line_tok_s_per_user): they name the speed of one request's stream.
SLO_TTFT_MS, SLO_ITL_MS, SLO_USER_TOK_S = 2000.0, 100.0, 10.0
THEMES = {"light": {"bg": "#FFFFFF", "fg": "#0F172A", "muted": "#475569", "grid": "#E2E8F0"},
          "dark": {"bg": "#0B0F19", "fg": "#E2E8F0", "muted": "#94A3B8", "grid": "#1E293B"}}
MODELS = {"N3": {"label": "Nemotron 3 Nano (NVFP4, NIM 2.0.12, 256 sequences)", "color": {"light": "#22D3EE", "dark": "#22D3EE"}, "marker": "o"},
          "A1": {"label": "Nemotron Nano 9B v2 (bf16, NIM 1.12.2, 32 sequences)", "color": {"light": "#64748B", "dark": "#94A3B8"}, "marker": "s"}}
FIGURES = {"chat": {"what": "chat-shaped requests (200 tokens in / 200 out)", "profile": "C"},
           "rag": {"what": "RAG-shaped requests (3,500 tokens in / 500 out)", "profile": "R"}}
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
XLIM, YLIM = (8.5, 450), (40, 6000)              # both axes are logarithmic; room under the lowest points for the legend
LABEL_OFFSET = {  # (figure, model, concurrency) -> offset of the concurrency label in pixels; the default is (14, 12)
    ("chat", "N3", 256): (-8, 24), ("chat", "N3", 512): (-62, -8),
    ("rag", "N3", 1): (12, -32), ("rag", "N3", 2): (12, -32), ("rag", "N3", 4): (12, -32), ("rag", "N3", 8): (12, -32), ("rag", "N3", 16): (12, -32),
    ("rag", "N3", 32): (12, -32), ("rag", "N3", 64): (12, -32), ("rag", "N3", 128): (12, -32), ("rag", "N3", 256): (-4, -34), ("rag", "N3", 512): (-62, -8),
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
           "axis_ticks": {"x": X_TICKS, "y": Y_TICKS}, "canvas": {"width": W, "height": H, "axes": AXES, "xlim": XLIM, "ylim": YLIM, "scale": "log-log"}, "boundary": BOUNDARY, "series": []}
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
    """Every number written on one figure (concurrency labels, the exit notes, the dashed line's note) -> must be in the table."""
    nums = {str(int(SLO_USER_TOK_S)), str(int(SLO_ITL_MS))}
    for s in data["series"]:
        if s["figure"] == fig and s["role"] == "article":
            nums |= {str(p["concurrency"]) for p in s["points"]} | {str(e["concurrency"]) for e in s["engine_exits"]}
    return nums


def draw(data, fig_key, theme):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)   # 'Space Grotesk' may not be installed: the SVG names it, the PNG falls back
    T = THEMES[theme]
    plt.rcParams.update({"font.family": ["Space Grotesk", "sans-serif"], "font.sans-serif": ["DejaVu Sans"], "svg.fonttype": "none", "svg.hashsalt": "vol2-pareto",
                         "text.color": T["fg"], "axes.labelcolor": T["fg"], "axes.edgecolor": T["muted"], "xtick.color": T["fg"], "ytick.color": T["fg"]})
    fig = plt.figure(figsize=(W / 72.0, H / 72.0), dpi=72, facecolor=T["bg"])
    ax = fig.add_axes(AXES, facecolor=T["bg"])
    drawn = {str(int(SLO_USER_TOK_S)), str(int(SLO_ITL_MS))}
    ax.axvline(SLO_USER_TOK_S, color=T["muted"], linestyle="--", linewidth=2.2, zorder=1)
    ax.text(SLO_USER_TOK_S * 1.05, 5300, "10 tok/s per request\n(100 ms per output token)", fontsize=17, color=T["muted"], va="top", ha="left")
    series = [s for s in data["series"] if s["figure"] == fig_key]
    for s in series:
        m = MODELS[s["model"]]; col = m["color"][theme]; pts = s["points"]; solid = s["role"] == "article"
        if solid:
            ax.plot([p["per_user_tok_s"] for p in pts], [p["total_tok_s"] for p in pts], color=col, linewidth=4.0, zorder=2)
        for p in pts:
            ax.plot([p["per_user_tok_s"]], [p["total_tok_s"]], linestyle="none", marker=m["marker"], markersize=17 if solid else 14,
                    markerfacecolor=col if p["ttft_p99_ms"] <= SLO_TTFT_MS else T["bg"], markeredgecolor=col, markeredgewidth=3.0,
                    alpha=1.0 if solid else 0.38, zorder=3 if solid else 2.5)
            if solid:
                ax.annotate(str(p["concurrency"]), (p["per_user_tok_s"], p["total_tok_s"]), textcoords="offset points",
                            xytext=LABEL_OFFSET.get((fig_key, s["model"], p["concurrency"]), (14, 12)), fontsize=20, color=T["fg"])
                drawn.add(str(p["concurrency"]))
        if solid and s["engine_exits"] and pts:
            e = s["engine_exits"][0]; last = pts[-1]
            ax.annotate(f"× {e['concurrency']}: engine exit, no result", (last["per_user_tok_s"], last["total_tok_s"]), textcoords="offset points", xytext=(-24, -44),
                        fontsize=18, color=T["fg"], ha="right")
            drawn.add(str(e["concurrency"]))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(*XLIM); ax.set_ylim(*YLIM)
    plain = FuncFormatter(lambda v, _: f"{int(v):,}")
    ax.xaxis.set_major_locator(FixedLocator(X_TICKS)); ax.yaxis.set_major_locator(FixedLocator(Y_TICKS))
    ax.xaxis.set_minor_locator(NullLocator()); ax.yaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(plain); ax.yaxis.set_major_formatter(plain)
    ax.tick_params(labelsize=21, length=7, width=1.5)
    ax.grid(True, which="major", color=T["grid"], linewidth=1.5, zorder=0)
    for sp in ax.spines.values():
        sp.set_linewidth(1.5)
    ax.set_xlabel("Per-request output speed, tok/s per request  (1000 ÷ mean inter-token latency in ms)", fontsize=24, labelpad=12)
    ax.set_ylabel("Total output throughput, tok/s", fontsize=24, labelpad=12)
    h = [Line2D([], [], color=MODELS[k]["color"][theme], marker=MODELS[k]["marker"], markersize=14, linewidth=4.0, label=MODELS[k]["label"]) for k in ("N3", "A1")]
    h += [Line2D([], [], color=T["muted"], marker="o", markersize=12, linestyle="none", alpha=0.38, label="faint: the same sweep on another night"),
          Line2D([], [], color=T["muted"], marker="o", markersize=13, linestyle="none", markerfacecolor=T["bg"], markeredgewidth=3.0, label="hollow: p99 time to first token > 2 s")]
    leg = ax.legend(handles=h, loc="lower left", bbox_to_anchor=(0.045, 0.02), fontsize=18, frameon=True, framealpha=0.92, facecolor=T["bg"], edgecolor=T["grid"], labelcolor=T["fg"], borderpad=0.7,
                    title="The number beside a point: concurrent requests", title_fontsize=18, alignment="left")
    leg.get_title().set_color(T["fg"])
    leg.get_frame().set_linewidth(1.5)
    fig.text(0.5, 0.058, BOUNDARY, ha="center", va="bottom", fontsize=17, style="italic", color=T["muted"])
    fig.canvas.draw()
    outside = []
    for s in series:
        for p in s["points"]:
            x, y = ax.transData.transform((p["per_user_tok_s"], p["total_tok_s"]))
            if not (BAND <= y <= H - BAND and 0 <= x <= W):
                outside.append(f"{fig_key} {theme}: {s['model']} c={p['concurrency']} ({s['role']}) is outside the central 1.9:1 band")
    base = os.path.join(HERE, f"pareto_{fig_key}_{theme}")
    fig.savefig(base + ".png", dpi=72, facecolor=T["bg"], metadata={"Software": None})
    fig.savefig(base + ".svg", facecolor=T["bg"], metadata={"Date": None, "Creator": None})
    raw = open(base + ".svg", "rb").read().replace(b"\r\n", b"\n")   # the same bytes on every platform
    raw = raw.replace(b'width="1600pt" height="900pt"', b'width="1600" height="900"', 1)   # a 1600 x 900 pixel canvas in a browser
    raw = raw.replace(b"'Space Grotesk', 'DejaVu Sans', sans-serif", b"'Space Grotesk', sans-serif")   # the fallback used for the PNG is not named in the SVG
    open(base + ".svg", "wb").write(raw)
    plt.close(fig)
    return drawn, outside, matplotlib.__version__


def svg_texts(fig_key, theme):
    s = open(os.path.join(HERE, f"pareto_{fig_key}_{theme}.svg"), encoding="utf-8").read()
    return [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<text[^>]*>(.*?)</text>", s, re.S)], s


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
    extra = []
    if mode == "check":
        data = json.load(open(table, encoding="utf-8"))
    else:
        data = build()
        written = {}
        for fig_key in FIGURES:
            for theme in THEMES:
                written[fig_key], outside, version = draw(data, fig_key, theme)
                extra += outside
        data["matplotlib_version"] = version
        data["numbers_on_figures"] = {k: sorted(v, key=int) for k, v in written.items()}
        json.dump(data, open(table, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    n, problems = check(data)
    problems += extra
    texts = 0
    for fig in FIGURES:
        more = set(data.get("numbers_on_figures", {}).get(fig, [])) - labels_on(data, fig)
        if more:
            problems.append(f"{fig}: numbers on the figure that are not in the table: {sorted(more)}")
        tl, sl = svg_texts(fig, "light"); td, sd = svg_texts(fig, "dark")
        texts = len(tl)
        if tl != td:
            problems.append(f"{fig}: the light and the dark SVG do not contain the same text")
        if len(tl) < 10:
            problems.append(f"{fig}: only {len(tl)} <text> elements: the text was not kept as text")
        for name, pattern in (("the word 'user' or 'users'", r"\busers?\b"), ("'7.3'", r"7\.3")):
            if any(re.search(pattern, x, re.I) for x in tl):
                problems.append(f"{fig}: a text of the figure contains {name}")
            elif re.search(pattern, sl, re.I) or re.search(pattern, sd, re.I):
                problems.append(f"{fig}: an SVG contains {name} outside its text (for '7.3', a coordinate: change the layout by a fraction of a pixel)")
        if "<image" in sl or "<image" in sd:
            problems.append(f"{fig}: an SVG embeds an image")
    for p in problems:
        print("  FAIL", p)
    print(f"{'drawn and ' if mode != 'check' else ''}checked: {n} points in {len(data['series'])} series, {texts} text elements per SVG, problems {len(problems)}")
    sys.exit(1 if problems else 0)
