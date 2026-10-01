#!/usr/bin/env python3
"""Vol.1 · one figure drawn from published results: total output throughput against the number of concurrent requests.

  throughput_concurrency_light.svg / .png   white background
  throughput_concurrency_dark.svg  / .png   dark background (#0B0F19)
  throughput_concurrency_points.json        every point with its source file and key

Nothing is measured here. Llama 3.1 8B Instruct, chat profile (200 tokens in / 200 out), four configurations:
NIM FP8, NIM bf16, Ollama 4-bit (16 slots), Ollama 16-bit (8 slots).

What is drawn:
  line and round markers   the run the article's table uses: results/p59_nim_value/analysis.json,
                           levels.<arm>|C|main.<c>.total_tps at c = 1, 8, 16, 32, 64, 128. The line is dashed between
                           1 and 8, where this run has no level, and solid from 8
  diamonds, no line        a separate run that measured 1, 2 and 4: results/p62_levels/analysis.json (the source of
                           "the crossover is between 2 and 4")
  faint markers, no line   the clean-window rechecks: results/p70_clean_recheck/analysis.json (cells.<arm>|<c>) and
                           results/p78_fp8_clean/levels.jsonl (the FP8 arm, and bf16 at 128 in the same window)
  hollow marker            p99 time to first token above 2,000 ms (outside the MLPerf server target on TTFT)
What is not drawn, and listed under "not_drawn" in the points file: Ollama with its default slot count (O-Q4-def);
the separate run's levels 8 and above (the article's run has them); the FP8 cells of the 27 September recheck, which
are null in their own file.

Card / social-image layout (the same for every figure of this repository): a 1600 x 900 canvas, the plot area in the
vertical middle 60%, no title, text kept as text in the SVG (font 'Space Grotesk', falling back to sans-serif).
The two versions differ in colours only.

Checks done on every run (exit code 1 if one fails):
  - every point is read back from its source file and key and must be equal;
  - the 16 totals of the article's table (1 / 8 / 32 / 128 for the four configurations) are points of the lines;
  - the run of the lines has no level between 1 and 8 in its own file (what the dashed part of a line says);
  - every drawn point lies inside the central 1.9:1 band of the canvas (what a 1200 x 630 crop keeps);
  - the light and the dark SVG contain the same text; neither file contains "users" or "7.3" anywhere (text or
    coordinate, so that a plain search of the file finds nothing); no embedded image;
  - the versions written in the boundary line (NIM 2.0.12, vLLM 0.27.1, Ollama 0.34.4) occur in the result files.
usage: plot_throughput_concurrency.py            draw, write the points file, check
       plot_throughput_concurrency.py check      check the existing points file against the sources (no drawing)
       plot_throughput_concurrency.py self_test
PNG bytes are reproducible with the same matplotlib version and the same font; the points file records both
("matplotlib_version", "png_font": the font the PNG was drawn with, which is the fallback when 'Space Grotesk' is not installed).
"""
import json, logging, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOL = os.path.dirname(HERE)
RES = "results"
NAME = "throughput_concurrency"
W, H = 1600, 900
AXES = [0.085, 0.201, 0.895, 0.598]          # left, bottom, width, height: the plot area is the vertical middle 60%,
                                             # moved by a fraction of a pixel so that no coordinate in the SVG reads "7.3"
BAND = (H - W / 1.9) / 2.0                   # pixels cut at the top and at the bottom by a 1.9:1 crop
SLO_TTFT_MS = 2000.0
THEMES = {"light": {"bg": "#FFFFFF", "fg": "#0F172A", "muted": "#475569", "grid": "#E2E8F0"},
          "dark": {"bg": "#0B0F19", "fg": "#E2E8F0", "muted": "#94A3B8", "grid": "#1E293B"}}
ARMS = {  # arm -> label, colour per theme, marker of the solid line
    "N-FP8": {"label": "NIM FP8 (NIM's own choice on this card)", "color": {"light": "#22D3EE", "dark": "#22D3EE"}},
    "N-BF16": {"label": "NIM bf16", "color": {"light": "#2563EB", "dark": "#2563EB"}},
    "O-Q4": {"label": "Ollama 4-bit (16 slots)", "color": {"light": "#94A3B8", "dark": "#94A3B8"}},
    "O-FP16": {"label": "Ollama 16-bit (8 slots)", "color": {"light": "#64748B", "dark": "#CBD5E1"}},
}
DASHED_TO = 8                                # a line is dashed from 1 to this level: the run has no level in between
DASHES = (2.4, 1.7)                          # dash and gap, in units of the line width
LABELLED = ("N-FP8", "N-BF16")               # concurrency labels on the NIM lines only; the x axis gives the others
X_TICKS = [1, 2, 4, 8, 16, 32, 64, 128]
Y_TICKS = [100, 200, 500, 1000, 2000, 5000, 10000]
XLIM, YLIM = (0.78, 170), (60, 13000)             # both axes are logarithmic
ARTICLE_TABLE = {"O-Q4": [172, 175, 755, 741], "O-FP16": [79, 317, 390, 402], "N-BF16": [87, 607, 2262, 5458], "N-FP8": [151, 1099, 3817, 8713]}
BOUNDARY = "One RTX 5090 · Llama 3.1 8B Instruct · synthetic chat 200/200 · closed loop · NIM 2.0.12 (vLLM 0.27.1) / Ollama 0.34.4"
VERSIONS = [("2.0.12", "p59_nim_value/prediction_p59_nim_value.json"), ("0.34.4", "p59_nim_value/prediction_p59_nim_value.json"), ("0.27.1", "p54_engine/stack.json")]
_json = {}


def load(rel):
    p = os.path.join(VOL, rel)
    if p not in _json:
        _json[p] = json.load(open(p, encoding="utf-8"))
    return _json[p]


def read_point(src):
    """(total tok/s, p99 TTFT ms) of one point, from the place its 'source' names."""
    if "line" in src:
        rows = open(os.path.join(VOL, src["file"]), encoding="utf-8").read().splitlines()
        s = json.loads(rows[src["line"] - 1])["summary"]
        return s["output_token_throughput"]["avg"], s["time_to_first_token"]["p99"]
    node = load(src["file"])
    for k in src["path"]:
        node = node[k]
    return node["total_tps"], node["ttft_p99_ms"]


def build():
    series, not_drawn = [], []

    def add(arm, role, c, src):
        tot, ttft = read_point(src)
        series.append({"arm": arm, "label": ARMS[arm]["label"], "role": role, "concurrency": c, "total_tok_s": tot, "ttft_p99_ms": ttft,
                       "inside_server_target_on_ttft": ttft <= SLO_TTFT_MS, "source": src})
    p59, p62, p70 = f"{RES}/p59_nim_value/analysis.json", f"{RES}/p62_levels/analysis.json", f"{RES}/p70_clean_recheck/analysis.json"
    for arm in ARMS:
        for c in (1, 8, 16, 32, 64, 128):
            add(arm, "article", c, {"file": p59, "path": ["levels", f"{arm}|C|main", str(c)], "keys": "total_tps, ttft_p99_ms"})
        for c in (1, 2, 4):
            add(arm, "separate run", c, {"file": p62, "path": ["levels", f"{arm}|C|main", str(c)], "keys": "total_tps, ttft_p99_ms"})
        for c in sorted((int(k) for k in load(p62)["levels"][f"{arm}|C|main"] if int(k) >= 8)):
            not_drawn.append({"arm": arm, "concurrency": c, "source": {"file": p62, "path": ["levels", f"{arm}|C|main", str(c)]},
                              "reason": "the separate run is drawn at 1, 2 and 4 only; the article's run has the levels from 8"})
        for c in (1, 32, 128):
            cell = load(p70)["cells"][f"{arm}|{c}"]
            if cell.get("total_tps") is None:
                not_drawn.append({"arm": arm, "concurrency": c, "source": {"file": p70, "path": ["cells", f"{arm}|{c}"]}, "reason": "null in the recheck's own file"})
            else:
                add(arm, "clean-window recheck", c, {"file": p70, "path": ["cells", f"{arm}|{c}"], "keys": "total_tps, ttft_p99_ms"})
    fp8 = f"{RES}/p78_fp8_clean/levels.jsonl"
    for line, r in enumerate((json.loads(l) for l in open(os.path.join(VOL, fp8), encoding="utf-8") if l.strip()), 1):
        if r.get("warmup") or not r.get("summary"):
            continue
        add(r["arm"], "clean-window recheck", r["concurrency"], {"file": fp8, "line": line, "keys": "summary.output_token_throughput.avg, summary.time_to_first_token.p99"})
    for c in (1, 8, 16, 32, 64, 128):
        not_drawn.append({"arm": "O-Q4-def", "concurrency": c, "source": {"file": p59, "path": ["levels", "O-Q4-def|C|main", str(c)]},
                          "total_tok_s": load(p59)["levels"]["O-Q4-def|C|main"][str(c)]["total_tps"], "reason": "Ollama with its default slot count is not drawn"})
    return {"what": "the points of throughput_concurrency: x = concurrent requests, y = total output tok/s, hollow marker when p99 TTFT > 2000 ms",
            "slo": {"ttft_p99_ms": SLO_TTFT_MS}, "axis_ticks": {"x": X_TICKS, "y": Y_TICKS}, "canvas": {"width": W, "height": H, "axes": AXES, "xlim": XLIM, "ylim": YLIM, "scale": "log-log"},
            "boundary": BOUNDARY, "line_style": {"dashed": [1, DASHED_TO], "solid_from": DASHED_TO, "reason": "the run of the lines has no level between 1 and 8"},
            "points": series, "not_drawn": not_drawn}


def check(data):
    problems = []
    for p in data["points"]:
        tot, ttft = read_point(p["source"])
        if abs(tot - p["total_tok_s"]) > 1e-9 * max(1.0, abs(tot)) or abs(ttft - p["ttft_p99_ms"]) > 1e-9 * max(1.0, abs(ttft)):
            problems.append(f"{p['arm']} c={p['concurrency']} ({p['role']}): source {tot}, {ttft} != table {p['total_tok_s']}, {p['ttft_p99_ms']}")
    art = {(p["arm"], p["concurrency"]): p["total_tok_s"] for p in data["points"] if p["role"] == "article"}
    for arm, vals in ARTICLE_TABLE.items():
        for c, v in zip((1, 8, 32, 128), vals):
            got = art.get((arm, c))
            if got is None or abs(got - v) > 0.5 + 1e-6:
                problems.append(f"the article's {v} ({arm}, c={c}) is not a point of the line (found {got})")
    for arm in ARMS:
        between = sorted(int(k) for k in load(f"{RES}/p59_nim_value/analysis.json")["levels"][f"{arm}|C|main"] if 1 < int(k) < DASHED_TO)
        if between:
            problems.append(f"{arm}: the run of the line has levels {between} between 1 and {DASHED_TO}; the dashed part says it has none")
    for ver, rel in VERSIONS:
        if ver not in BOUNDARY or ver not in open(os.path.join(VOL, RES, rel), encoding="utf-8").read():
            problems.append(f"version {ver} of the boundary line is not in {RES}/{rel}")
    return len(data["points"]), problems


def draw(data, theme):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)   # 'Space Grotesk' may not be installed: the SVG names it, the PNG falls back
    T = THEMES[theme]
    plt.rcParams.update({"font.family": ["Space Grotesk", "sans-serif"], "font.sans-serif": ["DejaVu Sans"], "svg.fonttype": "none", "svg.hashsalt": NAME,
                         "text.color": T["fg"], "axes.labelcolor": T["fg"], "axes.edgecolor": T["muted"], "xtick.color": T["fg"], "ytick.color": T["fg"]})
    fig = plt.figure(figsize=(W / 72.0, H / 72.0), dpi=72, facecolor=T["bg"])
    ax = fig.add_axes(AXES, facecolor=T["bg"])
    drawn, pixels = set(), []
    for arm, spec in ARMS.items():
        col = spec["color"][theme]
        pts = [p for p in data["points"] if p["arm"] == arm]
        art = sorted((p for p in pts if p["role"] == "article"), key=lambda p: p["concurrency"])
        head, tail = [p for p in art if p["concurrency"] <= DASHED_TO], [p for p in art if p["concurrency"] >= DASHED_TO]
        ax.plot([p["concurrency"] for p in head], [p["total_tok_s"] for p in head], color=col, linewidth=4.0, zorder=2, dashes=DASHES, dash_capstyle="butt")
        ax.plot([p["concurrency"] for p in tail], [p["total_tok_s"] for p in tail], color=col, linewidth=4.0, zorder=2)
        for p in pts:
            solid = p["role"] == "article"
            marker, size, alpha, z = ("o", 17, 1.0, 4) if solid else (("D", 14, 1.0, 3) if p["role"] == "separate run" else ("o", 14, 0.38, 2.5))
            ax.plot([p["concurrency"]], [p["total_tok_s"]], linestyle="none", marker=marker, markersize=size, alpha=alpha, zorder=z,
                    markerfacecolor=col if p["inside_server_target_on_ttft"] else T["bg"], markeredgecolor=col, markeredgewidth=3.0)
            pixels.append(ax.transData.transform((p["concurrency"], p["total_tok_s"])))
            if solid and arm in LABELLED and p["concurrency"] > 1:   # at 1 four lines and three kinds of marker meet; the axis tick says 1
                ax.annotate(str(p["concurrency"]), (p["concurrency"], p["total_tok_s"]), textcoords="offset points", xytext=(-10, 14), ha="right", fontsize=20, color=T["fg"])
                drawn.add(str(p["concurrency"]))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(*XLIM); ax.set_ylim(*YLIM)
    plain = FuncFormatter(lambda v, _: f"{int(v):,}")
    ax.xaxis.set_major_locator(FixedLocator(X_TICKS)); ax.yaxis.set_major_locator(FixedLocator(Y_TICKS))
    ax.xaxis.set_minor_locator(NullLocator()); ax.yaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(plain); ax.yaxis.set_major_formatter(plain)
    ax.tick_params(labelsize=21, length=7, width=1.5)
    ax.grid(True, which="major", color=T["grid"], linewidth=1.5, zorder=0)
    for s in ax.spines.values():
        s.set_linewidth(1.5)
    ax.set_xlabel("Number of concurrent requests", fontsize=24, labelpad=12)
    ax.set_ylabel("Total output throughput, tok/s", fontsize=24, labelpad=12)
    h = [Line2D([], [], color=s["color"][theme], marker="o", markersize=14, linewidth=4.0, label=s["label"]) for s in ARMS.values()]
    h += [Line2D([], [], color=T["muted"], linewidth=4.0, dashes=DASHES, dash_capstyle="butt", label="dashed: no level between 1 and 8 in this run"),
          Line2D([], [], color=T["muted"], marker="D", markersize=12, linestyle="none", label="c = 1, 2, 4: separate run"),
          Line2D([], [], color=T["muted"], marker="o", markersize=12, linestyle="none", alpha=0.38, label="faint: clean-window recheck"),
          Line2D([], [], color=T["muted"], marker="o", markersize=13, linestyle="none", markerfacecolor=T["bg"], markeredgewidth=3.0, label="hollow: p99 time to first token > 2 s")]
    leg = ax.legend(handles=h, loc="upper left", fontsize=18, frameon=True, framealpha=0.92, facecolor=T["bg"], edgecolor=T["grid"], labelcolor=T["fg"], borderpad=0.7)
    leg.get_frame().set_linewidth(1.5)
    fig.text(0.5, 0.058, BOUNDARY, ha="center", va="bottom", fontsize=17, style="italic", color=T["muted"])
    fig.canvas.draw()
    pixels = [ax.transData.transform((p["concurrency"], p["total_tok_s"])) for p in data["points"]]
    outside = [p for p, (x, y) in zip(data["points"], pixels) if not (BAND <= y <= H - BAND and 0 <= x <= W)]
    base = os.path.join(HERE, f"{NAME}_{theme}")
    fig.savefig(base + ".png", dpi=72, facecolor=T["bg"], metadata={"Software": None})
    fig.savefig(base + ".svg", facecolor=T["bg"], metadata={"Date": None, "Creator": None})
    raw = open(base + ".svg", "rb").read().replace(b"\r\n", b"\n")   # the same bytes on every platform
    raw = raw.replace(b'width="1600pt" height="900pt"', b'width="1600" height="900"', 1)   # a 1600 x 900 pixel canvas in a browser
    raw = raw.replace(b"'Space Grotesk', 'DejaVu Sans', sans-serif", b"'Space Grotesk', sans-serif")   # the fallback used for the PNG is not named in the SVG
    open(base + ".svg", "wb").write(raw)
    plt.close(fig)
    from matplotlib import font_manager
    font = font_manager.get_font(font_manager.findfont(font_manager.FontProperties(family=plt.rcParams["font.family"]))).family_name
    return drawn, outside, matplotlib.__version__, font


def svg_texts(theme):
    s = open(os.path.join(HERE, f"{NAME}_{theme}.svg"), encoding="utf-8").read()
    return [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<text[^>]*>(.*?)</text>", s, re.S)], s


def self_test():
    ok = True

    def t(name, got, want):
        nonlocal ok
        good = got == want; ok = ok and good
        print(("  PASS " if good else "  FAIL ") + f"{name}: {got} (want {want})")
    data = build()
    n, problems = check(data)
    t("every point reads back; the article's 16 totals are points; versions found", (n > 0, problems), (True, []))
    bad = json.loads(json.dumps(data)); bad["points"][5]["total_tok_s"] += 1.0
    t("negative control: one value changed -> reported", len(check(bad)[1]) >= 1, True)
    bad = json.loads(json.dumps(data)); bad["points"] = [p for p in bad["points"] if not (p["arm"] == "N-BF16" and p["role"] == "article" and p["concurrency"] == 128)]
    t("negative control: the 5,458 point removed -> the article's table check reports it", len(check(bad)[1]), 1)
    t("hollow rule: Ollama 4-bit at 1 inside, at 8 outside", [p["inside_server_target_on_ttft"] for p in data["points"] if p["arm"] == "O-Q4" and p["role"] == "article" and p["concurrency"] in (1, 8)], [True, False])
    t("the null FP8 cells of the 27 September recheck are not points", [d["concurrency"] for d in data["not_drawn"] if d["arm"] == "N-FP8" and "null" in d["reason"]], [1, 32, 128])
    t("FP8 in the clean window is a faint point at 128 (rounds to 9,062)", [round(p["total_tok_s"]) for p in data["points"] if p["arm"] == "N-FP8" and p["role"] == "clean-window recheck" and p["concurrency"] == 128], [9062])
    t("Ollama with default slots is listed, not drawn", (sum(d["arm"] == "O-Q4-def" for d in data["not_drawn"]), any(p["arm"] == "O-Q4-def" for p in data["points"])), (6, False))
    global DASHED_TO
    keep, DASHED_TO = DASHED_TO, 16
    t("negative control: a dashed part reaching 16 is reported for the four lines (the run has a level at 8)", len([x for x in check(data)[1] if "dashed" in x]), 4)
    DASHED_TO = keep
    t("the separate run has the levels 2 and 4 that the run of the lines lacks", sorted({p["concurrency"] for p in data["points"] if p["role"] == "separate run"}), [1, 2, 4])
    print("SELF-TEST " + ("PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "draw"
    if mode == "self_test":
        sys.exit(0 if self_test() else 1)
    table = os.path.join(HERE, f"{NAME}_points.json")
    extra = []
    if mode == "check":
        data = json.load(open(table, encoding="utf-8"))
    else:
        data = build()
        for theme in THEMES:
            drawn, outside, version, font = draw(data, theme)
            extra += [f"{theme}: {p['arm']} c={p['concurrency']} ({p['role']}) is outside the central 1.9:1 band" for p in outside]
        data["matplotlib_version"] = version
        data["png_font"] = font
        data["numbers_on_figure"] = sorted(drawn, key=int)
        json.dump(data, open(table, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    n, problems = check(data)
    problems += extra
    tl, sl = svg_texts("light"); td, sd = svg_texts("dark")
    if tl != td:
        problems.append("the light and the dark SVG do not contain the same text")
    if len(tl) < 10:
        problems.append(f"only {len(tl)} <text> elements: the text was not kept as text")
    for word in ("users", "7.3"):
        if any(word in x for x in tl):
            problems.append(f"a text of the figure contains {word!r}")
        elif word in sl or word in sd:
            problems.append(f"an SVG contains the characters {word!r} outside its text (a coordinate): move AXES by a fraction of a pixel")
    if "<image" in sl or "<image" in sd:
        problems.append("an SVG embeds an image")
    nums = {str(p["concurrency"]) for p in data["points"] if p["role"] == "article" and p["arm"] in LABELLED and p["concurrency"] > 1}
    if set(data.get("numbers_on_figure", [])) - nums:
        problems.append("a number on the figure is not in the points file")
    for p in problems:
        print("  FAIL", p)
    print(f"{'drawn and ' if mode != 'check' else ''}checked: {n} points, {len(tl)} text elements per SVG, problems {len(problems)}")
    sys.exit(1 if problems else 0)
