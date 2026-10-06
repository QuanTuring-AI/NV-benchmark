#!/usr/bin/env python3
"""Vol.3 · two figures drawn from the arms' own summaries: share of harmful items flagged against verdicts per second.

  detection_vs_rate_input_light  / _dark  (.svg, .png)   Aegis 2.0 prompts (the model sees the request alone)
  detection_vs_rate_output_light / _dark  (.svg, .png)   Aegis 2.0 responses (the model sees the request and the response)
  detection_vs_rate_points.json                           every point with its source file and keys

Nothing is measured here. Every point is one arm's own figure, read from that arm's summary.json:
  x  tracks.<track>.quality_cell.verdicts_per_s          (the cell that ran the whole set at 16 concurrent requests)
  y  tracks.<track>.quality.aegis2.detection.rate x 100  (harmful items flagged / harmful items), with its Wilson 95%
     interval (.wilson95) as the vertical bar
Nine points: the seven arms of results/p93_judges, the reference arm of results/p102_followup (Llama Guard 3 8B), and
the Safety Guard model served by its NIM (results/safety_guard_nim/J6N), added on 2026-10-06 after the others.
The two arms asked through a second library path on a 200-item subset (J4G, J5G) have no timed cell and are not drawn.

Scope: each point stands for one arm alone. The figure writes no statement that relates two arms, draws no arrow and no
line between points, and names no region of the plane. Timings at one request at a time are not on the figure.

What the marker says:
  shape   circle: asked through the NeMo Guardrails self-check action; square: asked directly with the model's own
          prompt; diamond: the reference arm
  hollow  the model reasons before it answers

Card / social-image layout (the same for every figure of this repository): a 1600 x 900 canvas, the plot area in the
vertical middle 60%, no title, text kept as text in the SVG (font 'Space Grotesk', falling back to sans-serif). The light
and the dark version differ in colours only.

Checks done on every run (exit code 1 if one fails):
  - every value in detection_vs_rate_points.json is read back from its source file and keys and must be equal;
  - every arm's timed cell ran at 16 concurrent requests and the arm is marked usable for that track;
  - every number written on a figure is in detection_vs_rate_points.json;
  - every drawn point and both ends of every bar lie inside the central 1.9:1 band of the canvas;
  - the light and the dark SVG of a figure contain the same text; no file contains "judge", "user" / "users" or "7.3"
    anywhere (text or coordinate), nor an arrow character or a multiplication sign; no embedded image.
usage: plot_detection_vs_rate.py            draw, write detection_vs_rate_points.json, check
       plot_detection_vs_rate.py check      check the existing points file against the sources (no drawing)
       plot_detection_vs_rate.py self_test
PNG bytes are reproducible with the same matplotlib version and the same fonts installed (recorded in the points file).
"""
import json, logging, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOL = os.path.dirname(HERE)
W, H = 1600, 900
AXES = [0.0868, 0.20, 0.895, 0.60]           # left, bottom, width, height: the plot area is the vertical middle 60%,
                                             # moved by a fraction of a pixel so that no coordinate in an SVG reads "7.3"
BAND = (H - W / 1.9) / 2.0                   # pixels cut at the top and at the bottom by a 1.9:1 crop
POINTS = "detection_vs_rate_points.json"
THEMES = {"light": {"bg": "#FFFFFF", "fg": "#0F172A", "muted": "#475569", "grid": "#E2E8F0"},
          "dark": {"bg": "#0B0F19", "fg": "#E2E8F0", "muted": "#94A3B8", "grid": "#1E293B"}}
FAMILY = {  # colour by model family
    "llama": {"light": "#64748B", "dark": "#94A3B8"}, "nano": {"light": "#0891B2", "dark": "#22D3EE"},
    "cs": {"light": "#2563EB", "dark": "#60A5FA"}, "guard": {"light": "#7C3AED", "dark": "#A78BFA"},
    "ref": {"light": "#B45309", "dark": "#FBBF24"}}
ARMS = [  # arm, summary file, family, marker, reasoning, label on the figure ({limit} = the arm's output limit in tokens)
    ("J0", "results/p93_judges/J0/summary.json", "llama", "o", False, "Llama 3.1 8B Instruct\nanswer limited to {limit} tokens"),
    ("J1", "results/p93_judges/J1/summary.json", "llama", "o", False, "Llama 3.1 8B Instruct\nthe library's default limit"),
    ("J2", "results/p93_judges/J2/summary.json", "nano", "o", True, "Nemotron 3 Nano\nreasoning on"),
    ("J3", "results/p93_judges/J3/summary.json", "nano", "o", False, "Nemotron 3 Nano\nreasoning off"),
    ("J4", "results/p93_judges/J4/summary.json", "cs", "s", False, "Nemotron 3.5 Content Safety\nreasoning off"),
    ("J5", "results/p93_judges/J5/summary.json", "cs", "s", True, "Nemotron 3.5 Content Safety\nreasoning on"),
    ("J6", "results/p93_judges/J6/summary.json", "guard", "s", False, "Llama 3.1 Nemotron\nSafety Guard 8B v3"),
    ("LG3", "results/p102_followup/LG3/summary.json", "ref", "D", False, "Llama Guard 3 8B\n(reference arm)"),
    ("J6N", "results/safety_guard_nim/J6N/summary.json", "guard", "s", False, "Safety Guard 8B v3\nserved by its NIM"),
]
TRACKS = {"input": "Aegis 2.0 test split, prompts", "output": "Aegis 2.0 test split, responses"}
KEYS = {"verdicts_per_s": "tracks.{t}.quality_cell.verdicts_per_s", "concurrency": "tracks.{t}.quality_cell.concurrency",
        "flagged": "tracks.{t}.quality.aegis2.detection.k", "harmful": "tracks.{t}.quality.aegis2.detection.n",
        "detection": "tracks.{t}.quality.aegis2.detection.rate", "wilson95_low": "tracks.{t}.quality.aegis2.detection.wilson95[0]",
        "wilson95_high": "tracks.{t}.quality.aegis2.detection.wilson95[1]", "items": "tracks.{t}.quality.aegis2.items",
        "usable": "tracks.{t}.usable"}
X_TICKS, Y_TICKS = [5, 10, 20, 50, 100], [40, 50, 60, 70, 80, 90, 100]
XLIM, YLIM = (4.6, 175.0), (38.0, 101.0)         # x is logarithmic, y is linear
LABEL = {  # (track, arm) -> (dx, dy in pixels, horizontal alignment); the default is (20, -8, "left")
    ("input", "J0"): (20, -52, "left"), ("input", "J1"): (-20, 26, "right"), ("input", "J2"): (20, -52, "left"),
    ("input", "J3"): (20, -18, "left"), ("input", "J4"): (-22, 22, "right"), ("input", "J5"): (-6, 30, "left"),
    ("input", "J6"): (16, -64, "left"), ("input", "LG3"): (-22, -62, "right"),
    ("output", "J0"): (22, -52, "left"), ("output", "J1"): (20, -62, "left"), ("output", "J2"): (20, -8, "left"),
    ("output", "J3"): (22, -40, "left"), ("output", "J4"): (24, -18, "left"), ("output", "J5"): (-4, 34, "left"),
    ("output", "J6"): (-8, 34, "left"), ("output", "LG3"): (-24, -18, "right"),
    ("input", "J6N"): (-18, 54, "right"), ("output", "J6N"): (-20, -64, "right"),
}
FORBIDDEN = (("the word 'judge'", r"judge"), ("the word 'user' or 'users'", r"\busers?\b"), ("'7.3'", r"7\.3"),
             ("an arrow character", "[←-⇿⟰-⟿⤀-⥿]"), ("a multiplication sign", "×"))


def value(obj, path):
    for part in path.split("."):
        m = re.fullmatch(r"([^\[]+)((?:\[\d+\])*)", part)
        obj = obj[m.group(1)]
        for i in re.findall(r"\[(\d+)\]", m.group(2)):
            obj = obj[int(i)]
    return obj


def build():
    out = {"what": "the points of detection_vs_rate_input and detection_vs_rate_output; x = verdicts per second in the cell that ran the whole "
                   "set at 16 concurrent requests, y = harmful items flagged / harmful items, bar = its Wilson 95% interval",
           "keys": {k: v.replace("{t}", "<track>") for k, v in KEYS.items()},
           "axis_ticks": {"x": X_TICKS, "y": Y_TICKS},
           "canvas": {"width": W, "height": H, "axes": AXES, "xlim": XLIM, "ylim": YLIM, "scale": "x logarithmic, y linear"},
           "marker": {"o": "asked through the NeMo Guardrails self-check action", "s": "asked directly with the model's own prompt",
                      "D": "the reference arm", "hollow": "the model reasons before it answers"},
           "tracks": {}}
    for t, what in TRACKS.items():
        pts = []
        for arm, src, fam, marker, reasoning, label in ARMS:
            s = json.load(open(os.path.join(VOL, src), encoding="utf-8"))
            p = {"arm": arm, "model": s["judge"], "source": src, "family": fam, "marker": marker, "reasoning": reasoning}
            p.update({k: value(s, path.format(t=t)) for k, path in KEYS.items()})
            p["max_tokens"] = s.get("max_tokens")
            p["label"] = label.format(limit=s.get("max_tokens"))
            pts.append(p)
        out["tracks"][t] = {"what": what, "points": pts}
    return out


def boundary(track):
    p = track["points"][0]
    return (f"One RTX 5090 · {track['what']}: {p['harmful']:,} harmful of {p['items']:,} items · one model on the card at a time · "
            f"{p['concurrency']} concurrent requests · bar: Wilson 95% interval")


def check(data):
    """Read every value back from its source; the preconditions of a point."""
    problems, n = [], 0
    for t, track in data["tracks"].items():
        if [p["arm"] for p in track["points"]] != [a[0] for a in ARMS]:
            problems.append(f"{t}: the arms are {[p['arm'] for p in track['points']]}, expected {[a[0] for a in ARMS]}")
        for p in track["points"]:
            s = json.load(open(os.path.join(VOL, p["source"]), encoding="utf-8"))
            n += 1
            for k, path in KEYS.items():
                want = value(s, path.format(t=t))
                if want != p[k]:
                    problems.append(f"{p['source']} {path.format(t=t)}: source {want} != table {p[k]}")
            if p["concurrency"] != 16:
                problems.append(f"{t} {p['arm']}: the timed cell ran at {p['concurrency']} concurrent requests, not 16")
            if p["usable"] is not True:
                problems.append(f"{t} {p['arm']}: the arm is not marked usable for this track")
            if p["harmful"] and abs(p["flagged"] / p["harmful"] - p["detection"]) > 1e-12:
                problems.append(f"{t} {p['arm']}: flagged / harmful != detection")
            if not (p["wilson95_low"] <= p["detection"] <= p["wilson95_high"]):
                problems.append(f"{t} {p['arm']}: the rate is outside its own interval")
        if len({(p["harmful"], p["items"]) for p in track["points"]}) != 1:
            problems.append(f"{t}: the arms did not read the same number of items")
    return n, problems


def numbers_allowed(data, t):
    """Every number that may be written on one figure: the ticks, and what the points file holds for that track."""
    track = data["tracks"][t]
    nums = {str(v) for v in X_TICKS + Y_TICKS} | {"95", "5090", "2.0", "3.1", "3.5", "3", "8"}   # interval level and names of products
    for p in track["points"]:
        nums |= {f"{p['harmful']:,}", f"{p['items']:,}", str(p["concurrency"])}
        if p["max_tokens"] is not None:
            nums.add(str(p["max_tokens"]))
    return nums


def draw(data, t, theme):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)   # 'Space Grotesk' may not be installed: the SVG names it, the PNG falls back
    T = THEMES[theme]
    plt.rcParams.update({"font.family": ["Space Grotesk", "sans-serif"], "font.sans-serif": ["DejaVu Sans"], "svg.fonttype": "none", "svg.hashsalt": "vol3-detection-vs-rate",
                         "text.color": T["fg"], "axes.labelcolor": T["fg"], "axes.edgecolor": T["muted"], "xtick.color": T["fg"], "ytick.color": T["fg"]})
    fig = plt.figure(figsize=(W / 72.0, H / 72.0), dpi=72, facecolor=T["bg"])
    ax = fig.add_axes(AXES, facecolor=T["bg"])
    track = data["tracks"][t]
    for p in track["points"]:
        col = FAMILY[p["family"]][theme]
        x, y = p["verdicts_per_s"], p["detection"] * 100.0
        ax.plot([x, x], [p["wilson95_low"] * 100.0, p["wilson95_high"] * 100.0], color=col, linewidth=3.0, solid_capstyle="butt", zorder=2)
        ax.plot([x], [y], linestyle="none", marker=p["marker"], markersize=19 if p["marker"] != "D" else 17,
                markerfacecolor=T["bg"] if p["reasoning"] else col, markeredgecolor=col, markeredgewidth=3.2, zorder=3)
        dx, dy, ha = LABEL.get((t, p["arm"]), (20, -8, "left"))
        ax.annotate(p["label"], (x, y), textcoords="offset points", xytext=(dx, dy), fontsize=17, color=T["fg"], ha=ha, va="bottom", linespacing=1.25)
    ax.set_xscale("log")
    ax.set_xlim(*XLIM); ax.set_ylim(*YLIM)
    plain = FuncFormatter(lambda v, _: f"{int(v):,}")
    ax.xaxis.set_major_locator(FixedLocator(X_TICKS)); ax.yaxis.set_major_locator(FixedLocator(Y_TICKS))
    ax.xaxis.set_minor_locator(NullLocator()); ax.yaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(plain); ax.yaxis.set_major_formatter(plain)
    ax.tick_params(labelsize=21, length=7, width=1.5)
    ax.grid(True, which="major", color=T["grid"], linewidth=1.5, zorder=0)
    for sp in ax.spines.values():
        sp.set_linewidth(1.5)
    ax.set_xlabel("Verdicts per second at 16 concurrent requests", fontsize=24, labelpad=12)
    ax.set_ylabel("Harmful items flagged, %", fontsize=24, labelpad=12)
    h = [Line2D([], [], color=T["muted"], marker="o", markersize=13, linestyle="none", label="circle: asked through the Guardrails self-check action"),
         Line2D([], [], color=T["muted"], marker="s", markersize=13, linestyle="none", label="square: asked directly, the model's own prompt"),
         Line2D([], [], color=T["muted"], marker="o", markersize=13, linestyle="none", markerfacecolor=T["bg"], markeredgewidth=3.0, label="hollow: the model reasons before it answers")]
    leg = ax.legend(handles=h, loc="lower left", bbox_to_anchor=(0.015, 0.03), fontsize=17, frameon=True, framealpha=0.92, facecolor=T["bg"], edgecolor=T["grid"],
                    labelcolor=T["fg"], borderpad=0.7, alignment="left")
    leg.get_frame().set_linewidth(1.5)
    fig.text(0.5, 0.058, boundary(track), ha="center", va="bottom", fontsize=17, style="italic", color=T["muted"])
    fig.canvas.draw()
    outside = []
    for p in track["points"]:
        for yv in (p["wilson95_low"], p["detection"], p["wilson95_high"]):
            x, y = ax.transData.transform((p["verdicts_per_s"], yv * 100.0))
            if not (BAND <= y <= H - BAND and 0 <= x <= W):
                outside.append(f"{t} {theme}: {p['arm']} is outside the central 1.9:1 band")
                break
    base = os.path.join(HERE, f"detection_vs_rate_{t}_{theme}")
    fig.savefig(base + ".png", dpi=72, facecolor=T["bg"], metadata={"Software": None})
    fig.savefig(base + ".svg", facecolor=T["bg"], metadata={"Date": None, "Creator": None})
    raw = open(base + ".svg", "rb").read().replace(b"\r\n", b"\n")   # the same bytes on every platform
    raw = raw.replace(b'width="1600pt" height="900pt"', b'width="1600" height="900"', 1)   # a 1600 x 900 pixel canvas in a browser
    raw = raw.replace(b"'Space Grotesk', 'DejaVu Sans', sans-serif", b"'Space Grotesk', sans-serif")   # the fallback used for the PNG is not named in the SVG
    open(base + ".svg", "wb").write(raw)
    plt.close(fig)
    return outside, matplotlib.__version__


def svg_texts(t, theme):
    s = open(os.path.join(HERE, f"detection_vs_rate_{t}_{theme}.svg"), encoding="utf-8").read()
    return [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<text[^>]*>(.*?)</text>", s, re.S)], s


def figure_checks(data):
    problems, texts = [], 0
    for t in TRACKS:
        tl, sl = svg_texts(t, "light"); td, sd = svg_texts(t, "dark")
        texts = len(tl)
        if tl != td:
            problems.append(f"{t}: the light and the dark SVG do not contain the same text")
        if len(tl) < 20:
            problems.append(f"{t}: only {len(tl)} <text> elements: the text was not kept as text")
        written = set()
        for x in tl:
            written |= set(re.findall(r"\d[\d,]*(?:\.\d+)?", x))
        more = written - numbers_allowed(data, t)
        if more:
            problems.append(f"{t}: numbers on the figure that are not in the table: {sorted(more)}")
        for name, pattern in FORBIDDEN:
            if any(re.search(pattern, x, re.I) for x in tl):
                problems.append(f"{t}: a text of the figure contains {name}")
            elif re.search(pattern, sl, re.I) or re.search(pattern, sd, re.I):
                problems.append(f"{t}: an SVG contains {name} outside its text (for '7.3', a coordinate: change the layout by a fraction of a pixel)")
        if "<image" in sl or "<image" in sd:
            problems.append(f"{t}: an SVG embeds an image")
        if not any("concurrent requests" in x for x in tl):
            problems.append(f"{t}: positive control: the words 'concurrent requests' are not in the figure's text")
    return texts, problems


def self_test():
    ok = True

    def tt(name, got, want):
        nonlocal ok
        good = got == want; ok = ok and good
        print(("  PASS " if good else "  FAIL ") + f"{name}: {got} (want {want})")
    data = build()
    n, problems = check(data)
    tt("every value reads back from its source", (n, problems), (2 * len(ARMS), []))
    bad = json.loads(json.dumps(data)); bad["tracks"]["input"]["points"][4]["verdicts_per_s"] += 1.0
    tt("negative control: one rate changed -> the check reports it", len(check(bad)[1]), 1)
    bad = json.loads(json.dumps(data)); bad["tracks"]["output"]["points"][7]["flagged"] += 1
    tt("negative control: one count changed -> reported twice (source, and flagged / harmful)", len(check(bad)[1]), 2)
    bad = json.loads(json.dumps(data)); bad["tracks"]["input"]["points"].pop()
    tt("negative control: the reference arm removed -> reported", len(check(bad)[1]), 1)
    tt("eight arms per track, the same items for each", [(len(v["points"]), len({(p["harmful"], p["items"]) for p in v["points"]})) for v in data["tracks"].values()], [(8, 1), (8, 1)])
    tt("the arms on a 200-item subset are not points", [p["arm"] for p in data["tracks"]["input"]["points"] if p["arm"].endswith("G")], [])
    tt("forbidden patterns fire on planted strings", [bool(re.search(pat, s, re.I)) for (_, pat), s in zip(FORBIDDEN, ("a Judge", "16 users", "x=47.3", "a → b", "2×"))], [True] * 5)
    tt("forbidden patterns stay silent on the figure's own words", [bool(re.search(pat, "Verdicts per second at 16 concurrent requests", re.I)) for _, pat in FORBIDDEN], [False] * 5)
    print("SELF-TEST " + ("PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "draw"
    if mode == "self_test":
        sys.exit(0 if self_test() else 1)
    table = os.path.join(HERE, POINTS)
    extra = []
    if mode == "check":
        data = json.load(open(table, encoding="utf-8"))
    else:
        data = build()
        for t in TRACKS:
            for theme in THEMES:
                outside, version = draw(data, t, theme)
                extra += outside
        data["matplotlib_version"] = version
        json.dump(data, open(table, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    n, problems = check(data)
    texts, more = figure_checks(data)
    problems += extra + more
    for p in problems:
        print("  FAIL", p)
    print(f"{'drawn and ' if mode != 'check' else ''}checked: {n} points in {len(data['tracks'])} figures, {texts} text elements per SVG, problems {len(problems)}")
    sys.exit(1 if problems else 0)
