#!/usr/bin/env python3
"""Vol.4 · the two figures of the forum post, laid out again for a page that shows an image 690 pixels wide.

  whole_corpus_quality_dark_forum (.svg, .png)     the values of whole_corpus_quality_dark, from figure_points.json
  concurrency_sweep_dark_forum (.svg, .png)        the values of concurrency_sweep_dark, from concurrency_sweep_points.json,
                                                   the three panels one under the other
  forum_figures.json                               canvas, the smallest text, the tick labels, the positions tried

Nothing is measured and nothing new is drawn: every value comes from the points files of the repository's own figures,
which are read back from their sources first (the checks of plot_vol4_figures.py and plot_concurrency_sweep.py). The
repository's figures and their programs are not touched. Only the dark version is made (the one the post shows).
The rule of this layout: at 690 pixels of width the smallest text of the figure is at least 11 pixels high. The canvas
is 1,200 pixels wide, so every text is at least 11 / (690 / 1200) = 19.2 pixels: the smallest used is 20.

Checks done on every run (exit code 1 if one fails):
  - the two points files read back from their sources (the original programs' own check);
  - every <text> of each SVG: font size times 690 / width is at least 11;
  - every number written on a figure is one the original figure may write (its programs' list, plus this layout's
    tick labels); the forbidden patterns of plot_vol4_figures.py, in the text and outside it; no embedded image;
    the positive controls of the originals ('Recall@100', 'requests in flight');
  - the PNG is as wide as the SVG says.
usage: plot_forum_figures.py            draw, write forum_figures.json, check
       plot_forum_figures.py check      check the existing files (no drawing)
       plot_forum_figures.py self_test
"""
import json, math, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plot_vol4_figures as F  # noqa: E402
import plot_concurrency_sweep as C  # noqa: E402

SHOWN, MIN_SHOWN = 690, 11.0
W = 1200
SIZES = {"whole_corpus_quality": (W, 1000), "concurrency_sweep": (W, 2250)}
FS = {"small": 20, "label": 22, "title": 23}
META = "forum_figures.json"
THEME = "dark"


def out_base(name):
    return os.path.join(HERE, f"{name}_{THEME}_forum")


def save(fig, plt, name, T):
    w, h = SIZES[name]; base = out_base(name)
    fig.savefig(base + ".png", dpi=72, facecolor=T["bg"], metadata={"Software": None})
    fig.savefig(base + ".svg", facecolor=T["bg"], metadata={"Date": None, "Creator": None})
    raw = open(base + ".svg", "rb").read().replace(b"\r\n", b"\n")
    raw = raw.replace(f'width="{w}pt" height="{h}pt"'.encode(), f'width="{w}" height="{h}"'.encode(), 1)
    raw = raw.replace(b"'Space Grotesk', 'DejaVu Sans', sans-serif", b"'Space Grotesk', sans-serif")
    open(base + ".svg", "wb").write(raw)
    plt.close(fig)


def draw_quality(data, shift):
    plt, T, version = F.setup(THEME)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.ticker import FixedLocator, NullLocator
    w, h = SIZES["whole_corpus_quality"]; Q = data["whole_corpus_quality"]
    fig = plt.figure(figsize=(w / 72.0, h / 72.0), dpi=72, facecolor=T["bg"])
    ax = fig.add_axes([0.105 + shift[0], 0.335 + shift[1], 0.875 + shift[2], 0.52 + shift[3]], facecolor=T["bg"])
    width = 0.2; ticks, labels = [], []
    for g, c in enumerate(Q["corpora"]):
        by = {e["condition"]: e for e in c["conditions"]}
        for j, (key, _, colour) in enumerate(F.CONDITIONS):
            x = g + (j - 1.5) * width
            if key in by:
                e = by[key]
                ax.bar(x, e["ndcg_cut_10"], width * 0.88, color=colour[THEME], zorder=2)
                ax.plot([x - width * 0.40, x + width * 0.40], [e["recall_100"]] * 2, color=T["fg"], linewidth=3.0, solid_capstyle="butt", zorder=3)
                ax.text(x, e["ndcg_cut_10"] - 0.03, F.f3(e["ndcg_cut_10"]), ha="center", va="top", fontsize=FS["small"], color=T["bg"], fontweight="bold", rotation=90, zorder=4)
                ax.text(x, e["recall_100"] + 0.015, F.f3(e["recall_100"]), ha="center", va="bottom", fontsize=FS["small"], color=T["muted"], rotation=90, zorder=4)
            else:
                ax.text(x, 0.03, c["not_drawn"][key].replace("\n", " "), ha="center", va="bottom", fontsize=FS["small"], color=T["muted"], style="italic", rotation=90, zorder=4)
        red = by.get("reduced")
        ticks.append(g)
        labels.append(f"{c['corpus']}\n{c['split']}, {by['whole']['queries']:,} queries\n" + (f"reduced {red['passages']:,} passages\n" if red else "\n") + f"whole {c['passages_whole']:,} passages")
    ax.set_xlim(-0.55, len(Q["corpora"]) - 0.45); ax.set_ylim(0.0, 1.30)
    ax.xaxis.set_major_locator(FixedLocator(ticks)); ax.set_xticklabels(labels, fontsize=FS["small"], linespacing=1.35)
    ax.yaxis.set_major_locator(FixedLocator([0, 0.2, 0.4, 0.6, 0.8, 1.0])); ax.yaxis.set_minor_locator(NullLocator())
    ax.tick_params(axis="y", labelsize=FS["label"], length=7, width=1.5); ax.tick_params(axis="x", length=0, pad=12)
    ax.grid(True, axis="y", which="major", color=T["grid"], linewidth=1.5, zorder=0)
    for sp in ax.spines.values():
        sp.set_linewidth(1.5)
    ax.set_ylabel("nDCG@10 (bars) · Recall@100 (dashes)", fontsize=FS["label"], labelpad=12)
    hd = [Patch(facecolor=colour[THEME], label=label) for _, label, colour in F.CONDITIONS] + [Line2D([], [], color=T["fg"], linewidth=3.0, label="dash: Recall@100 of the same results")]
    leg = fig.legend(handles=hd, loc="upper center", bbox_to_anchor=(0.5, 0.985), ncol=2, fontsize=FS["small"], frameon=True, framealpha=0.92, facecolor=T["bg"], edgecolor=T["grid"],
                     labelcolor=T["fg"], borderpad=0.6, columnspacing=1.6, handlelength=1.4)
    leg.get_frame().set_linewidth(1.5)
    enc = Q["encoder"]; rr = {k: v["value"].rsplit("/", 1)[1] for k, v in Q["rerankers"].items()}
    fig.text(0.5, 0.02, f"One RTX 5090 · encoder {enc['model']} NIM {enc['version']} at {enc['precision']}\n"
                        f"cosine of every query with every passage, no index\n"
                        f"rerankers {rr['rerank_1b']} and {rr['rerank_500m']}\n"
                        f"on the first 100 results of each query · one run per cell",
             ha="center", va="bottom", fontsize=FS["small"], style="italic", color=T["muted"], linespacing=1.4)
    fig.canvas.draw()
    tl = sorted({t.get_text() for t in ax.get_yticklabels() if t.get_text()})
    save(fig, plt, "whole_corpus_quality", T)
    return tl, version


def draw_sweep(data, shift):
    plt, T, version = F.setup(THEME)
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullLocator
    w, h = SIZES["concurrency_sweep"]
    fig = plt.figure(figsize=(w / 72.0, h / 72.0), dpi=72, facecolor=T["bg"]); ticks = set()
    bottoms = [0.708, 0.418, 0.128]; height = 0.235
    for i, (shape, title, unit, _, _) in enumerate(C.PANELS):
        P = data["panels"][i]
        ax = fig.add_axes([0.195 + shift[0], bottoms[i] + shift[1], 0.775 + shift[2], height + shift[3]], facecolor=T["bg"])
        ys, xs, handles = [], [], []
        for L in P["lines"]:
            col = C.COLOURS[L["arm"]][THEME]; x = [e["items_per_s"] for e in L["first"]]; y = [e["p99_ms"] for e in L["first"]]
            ax.plot(x, y, color=col, linewidth=2.6, marker="o", markersize=10, markerfacecolor=col, markeredgecolor=col, zorder=3)
            ax.plot([e["items_per_s"] for e in L["second"]], [e["p99_ms"] for e in L["second"]], linestyle="none", marker="o", markersize=17, markerfacecolor="none", markeredgecolor=col, markeredgewidth=2.2, zorder=4)
            for e, off, ha, va in ((L["first"][0], (-8, -8), "right", "top"), (L["first"][-1], (9, 6), "left", "bottom")):
                ax.annotate(str(e["level"]), (e["items_per_s"], e["p99_ms"]), textcoords="offset points", xytext=off, fontsize=FS["small"], color=T["muted"], ha=ha, va=va)
            xs += x + [e["items_per_s"] for e in L["second"]]; ys += y + [e["p99_ms"] for e in L["second"]]
            handles.append(Line2D([], [], color=col, linewidth=2.6, marker="o", markersize=10, label=f"{L['model']} {L['version']}"))
        if xs:
            lo, hi = 10 ** math.floor(math.log10(min(ys))), 10 ** (math.ceil(math.log10(max(ys))) + 2)
            ax.set_yscale("log"); ax.set_ylim(lo, hi); ax.set_xlim(0, max(xs) * 1.16)
            ax.yaxis.set_major_locator(FixedLocator([10 ** k for k in range(int(round(math.log10(lo))), int(math.floor(math.log10(hi))) + 1)])); ax.yaxis.set_minor_locator(NullLocator())
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6, integer=True, steps=[1, 2, 5, 10]))
        fmt = FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 1 else f"{v:g}")
        ax.xaxis.set_major_formatter(fmt); ax.yaxis.set_major_formatter(fmt)
        ax.tick_params(labelsize=FS["small"], length=7, width=1.5); ax.grid(True, which="major", color=T["grid"], linewidth=1.5, zorder=0)
        for sp in ax.spines.values():
            sp.set_linewidth(1.5)
        ax.set_xlabel(unit, fontsize=FS["label"], labelpad=8)
        ax.set_ylabel("p99 duration of a request,\nms (log scale)", fontsize=FS["label"], labelpad=10)
        ax.text(0.025, 0.965, title, transform=ax.transAxes, ha="left", va="top", fontsize=FS["title"], color=T["fg"], fontweight="bold")
        if handles:
            leg = ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.012, 0.88), fontsize=FS["small"], labelspacing=0.3, frameon=True, framealpha=0.92, facecolor=T["bg"], edgecolor=T["grid"],
                            labelcolor=T["fg"], borderpad=0.5, handlelength=1.6)
            leg.get_frame().set_linewidth(1.5)
        fig.canvas.draw()
        ticks |= {t.get_text() for t in ax.get_xticklabels() + ax.get_yticklabels() if t.get_text()}
    one = next(e for P in data["panels"] for L in P["lines"] for e in L["first"])
    later = sorted({L["model"] for P in data["panels"] for L in P["lines"] if L.get("night") == "second"})
    fig.text(0.5, 0.012, f"One RTX 5090 · one NIM on the card at a time · AIPerf {one['aiperf']}, closed loop, {one['asked_s']} s per level\n"
                         f"the load tool in a container on the NIM's network\n"
                         f"filled: every level in the first container\nhollow: the two highest levels in a second new container\n"
                         f"the number at the ends of a line: {C.CONTROL}"
                         + (f"\n{', '.join(later)}: swept on the second night, the other NIMs on the first" if later else ""),
             ha="center", va="bottom", fontsize=FS["small"], style="italic", color=T["muted"], linespacing=1.4)
    fig.canvas.draw()
    save(fig, plt, "concurrency_sweep", T)
    return sorted(ticks), version


def svg_texts_sizes(name):
    s = open(out_base(name) + ".svg", encoding="utf-8").read()
    texts = [(re.sub(r"<[^>]+>", "", m.group(2)), m.group(1)) for m in re.finditer(r"<text([^>]*)>(.*?)</text>", s, re.S)]
    sizes = []
    for _, attrs in texts:
        m = re.search(r"font-size:\s*([\d.]+)px", attrs)
        sizes.append(float(m.group(1)) if m else None)
    width = float(re.search(r'<svg[^>]*width="([\d.]+)"', s).group(1))
    return [t for t, _ in texts], sizes, width, s


def png_width(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">I", head[16:20])[0]


def figure_checks(name, allowed, control):
    problems = []
    tl, sizes, width, s = svg_texts_sizes(name)
    if len(tl) < 20:
        problems.append(f"{name}: only {len(tl)} <text> elements: the text was not kept as text")
    if any(z is None for z in sizes):
        problems.append(f"{name}: a <text> without a font size")
    shown = [round(z * SHOWN / width, 2) for z in sizes if z is not None]
    if min(shown) < MIN_SHOWN:
        problems.append(f"{name}: the smallest text is {min(shown)} px at {SHOWN} px of width (rule: at least {MIN_SHOWN})")
    written = set()
    for x in tl:
        written |= {m.rstrip(",") for m in re.findall(r"\d[\d,]*(?:\.\d+)*", x)}
    more = written - allowed
    if more:
        problems.append(f"{name}: numbers on the figure that the original may not write: {sorted(more)}")
    for what, pattern in F.FORBIDDEN:
        if any(re.search(pattern, x, re.I) for x in tl):
            problems.append(f"{name}: a text of the figure contains {what}")
        elif re.search(pattern, s, re.I):
            problems.append(f"{name}: the SVG contains {what} outside its text")
    if "<image" in s:
        problems.append(f"{name}: the SVG embeds an image")
    if not any(control in x for x in tl):
        problems.append(f"{name}: positive control: the words '{control}' are not in the figure's text")
    if png_width(out_base(name) + ".png") != int(width):
        problems.append(f"{name}: the PNG is not as wide as the SVG")
    return {"texts": len(tl), "smallest_font_px": min(z for z in sizes if z), "smallest_shown_px_at_690": min(shown)}, problems


def load_points():
    q = json.load(open(os.path.join(HERE, F.POINTS), encoding="utf-8")); c = json.load(open(os.path.join(HERE, C.POINTS), encoding="utf-8"))
    return q, c


def checks(q, c, meta):
    n1, p1 = F.check(q); n2, p2 = C.check(c); problems = [f"figure_points.json: {p}" for p in p1] + [f"concurrency_sweep_points.json: {p}" for p in p2]
    a1 = F.numbers_allowed(q, "whole_corpus_quality") | set(meta["whole_corpus_quality"]["tick_labels"])
    a2 = C.numbers_allowed(c) | set(meta["concurrency_sweep"]["tick_labels"])
    r1, x1 = figure_checks("whole_corpus_quality", a1, "Recall@100"); r2, x2 = figure_checks("concurrency_sweep", a2, C.CONTROL)
    return n1 + n2, problems + x1 + x2, {"whole_corpus_quality": r1, "concurrency_sweep": r2}


def draw_all(q, c):
    pattern = "|".join(p for _, p in F.FORBIDDEN); meta = {}
    for name, fn, data in (("whole_corpus_quality", draw_quality, q), ("concurrency_sweep", draw_sweep, c)):
        tried = 0
        for shift in C.shifts():
            tried += 1
            ticks, version = fn(data, shift)
            if not re.search(pattern, open(out_base(name) + ".svg", encoding="utf-8").read(), re.I):
                break
        meta[name] = {"canvas": list(SIZES[name]), "axes_moved_by": list(shift), "positions_tried": tried, "tick_labels": ticks, "matplotlib_version": version}
    return meta


def self_test():
    ok = True

    def tt(label, got, want):
        nonlocal ok
        good = got == want; ok = ok and good
        print(("  PASS " if good else "  FAIL ") + f"{label}: {got} (want {want})")
    tt("the smallest font used is at least 11 px at 690 px of width", min(FS.values()) * SHOWN / W >= MIN_SHOWN, True)
    tt("the rule fails at the originals' smallest font (14.5 px on 1,600)", 14.5 * SHOWN / 1600 >= MIN_SHOWN, False)
    tmp = os.path.join(HERE, "_selftest_forum.svg")
    open(tmp, "w", encoding="utf-8").write('<svg width="1200" height="10"><text style="font-size: 18px">a</text><text style="font-size: 20px">b</text></svg>')
    s = open(tmp, encoding="utf-8").read(); os.remove(tmp)
    sizes = [float(m) for m in re.findall(r"font-size:\s*([\d.]+)px", s)]
    tt("negative control: a planted 18 px text on a 1,200 canvas is found below the rule", min(sizes) * SHOWN / 1200 < MIN_SHOWN, True)
    q, c = load_points()
    tt("the points files read back from their sources", (F.check(q)[1], C.check(c)[1]), ([], []))
    bad = json.loads(json.dumps(q)); bad["whole_corpus_quality"]["corpora"][0]["conditions"][1]["ndcg_cut_10"] += 0.001
    tt("negative control: a changed value in a points file is reported", len(F.check(bad)[1]), 1)
    print("SELF-TEST " + ("PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "draw"
    if mode == "self_test":
        sys.exit(0 if self_test() else 1)
    q, c = load_points(); mpath = os.path.join(HERE, META)
    if mode == "check":
        meta = json.load(open(mpath, encoding="utf-8"))
    else:
        meta = draw_all(q, c)
    n, problems, result = checks(q, c, meta)
    if mode != "check":
        for k in result:
            meta[k].update(result[k])
        meta = {"what": "the forum versions of two Vol.4 figures: canvas, the smallest text, tick labels, positions tried", "rule": f"smallest text at least {MIN_SHOWN} px when the image is shown {SHOWN} px wide", **meta}
        json.dump(meta, open(mpath, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    for p in problems:
        print("  FAIL", p)
    print(f"{'drawn and ' if mode != 'check' else ''}checked: {n} values read back, {json.dumps(result)}, problems {len(problems)}")
    sys.exit(1 if problems else 0)
