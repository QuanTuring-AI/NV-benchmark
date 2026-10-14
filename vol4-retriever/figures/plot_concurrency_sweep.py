#!/usr/bin/env python3
"""Vol.4 · one figure drawn from the level records of the concurrency sweep (results/concurrency_sweep).

  concurrency_sweep_light / _dark (.svg, .png)
        three panels, one per request shape: items per second (x) against the p99 duration of a request (y, log) at
        every level of requests in flight; one line per NIM; filled markers are the first container, hollow markers the
        two highest levels again in a second new container
  concurrency_sweep_points.json
        every drawn value with its source file and key

Nothing is measured here. Every value is AIPerf's own figure of one level, as sweep_level.py kept it:
  items per second    items_per_s (requests per second times the items of one request)
  p99, ms             request_ms.p99 (AIPerf's request_latency, measured in the client)
Scope: a point is one level of one NIM alone on the card. The figure draws no arrow, writes no ratio and no statement
that relates one model to another, and names no number of people: a level is a number of requests in flight.
The NIM that the first night's calibration rule stopped before its sweep was swept on the second night; its line is
drawn from that night's records (results/concurrency_sweep_second_night), the points file names the night of every
line, and the note under the figure says which line is the later one.

Card layout as in plot_vol4_figures.py (1600 x 900, the plot area in the vertical middle 60%, no title, text kept as
text, light and dark differ in colours only). The positions of the axes are moved by a fraction of a pixel, found by
trial, until no coordinate of the SVG reads like a number this repository does not print on a figure; the amounts are
recorded in the points file.

Checks done on every run (exit code 1 if one fails):
  - every value in the points file is read back from its source file and key and must be equal;
  - every drawn level: no errors, the level in the file's name is the level in the file, one load-tool version and one
    asked duration for all, one set of request bodies (sha256) per line;
  - every number written on the figure is in the points file (or is part of a product's name);
  - the light and the dark SVG contain the same text; the forbidden patterns of plot_vol4_figures.py; no embedded image.
usage: plot_concurrency_sweep.py            draw, write the points file, check
       plot_concurrency_sweep.py check      check the existing points file against the sources (no drawing)
       plot_concurrency_sweep.py self_test
"""
import json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plot_vol4_figures as F  # noqa: E402

VOL, W, H = F.VOL, F.W, F.H
RES = "results/concurrency_sweep/"
PRE = RES + "prediction_concurrency_sweep.json"
POINTS = "concurrency_sweep_points.json"
NAME = "concurrency_sweep"
COLOURS = {"n3": {"light": "#0891B2", "dark": "#22D3EE"}, "evl": {"light": "#B45309", "dark": "#FBBF24"}, "e1b": {"light": "#2563EB", "dark": "#60A5FA"},
           "e300": {"light": "#7C3AED", "dark": "#A78BFA"}, "rr1b": {"light": "#2563EB", "dark": "#60A5FA"}, "rr500": {"light": "#7C3AED", "dark": "#A78BFA"}}
PANELS = [("query", "Embedding · one query per request", "Queries per second", ("n3", "e1b", "evl", "e300"), 0.078),
          ("passage", "Embedding · 64 passages per request", "Passages per second", ("n3", "e1b", "evl", "e300"), 0.402),
          ("passages_100", "Reranking · one query, 100 passages", "Pairs per second", ("rr1b", "rr500"), 0.726)]
PANEL_W, BOTTOM, HEIGHT = 0.250, 0.200, 0.600
KEYS = {"items_per_s": "items_per_s", "p99_ms": "request_ms.p99", "level": "concurrency", "errors": "errors", "asked_s": "duration_asked_s", "aiperf": "aiperf_version", "inputs_sha256": "inputs.sha256"}
NAME_NUMBERS = {"5090", "100", "64", "3", "1", "2", "300", "500", "99"}     # the card, the request shapes, digits inside model names, p99
CONTROL = "requests in flight"


LATER = {"e300": "results/concurrency_sweep_second_night/"}     # a line whose sweep is a later night's: the folder of its records


def levels(arm, shape, label):
    root = LATER.get(arm, RES)
    d = os.path.join(VOL, root, arm, shape); out = []
    for f in os.listdir(d) if os.path.isdir(d) else []:
        m = re.fullmatch(rf"{label}_c(\d+)\.json", f)
        if m:
            rel = f"{root}{arm}/{shape}/{f}"; e = {"file_level": int(m.group(1)), "source": rel}
            e.update({k: F.value(F.load(rel), p) for k, p in KEYS.items()}); out.append(e)
    return sorted(out, key=lambda e: e["file_level"])


def build():
    arms = F.value(F.load(PRE), "N1_concurrency_sweep.arms")
    out = {"what": "the values drawn on the concurrency-sweep figure, each with its source file and key", "keys": KEYS, "panels": [], "not_drawn": {},
           "canvas": {"width": W, "height": H, "panel_width": PANEL_W, "bottom": BOTTOM, "height_share": HEIGHT, "lefts": {p[0]: p[4] for p in PANELS}}}
    for shape, title, unit, names, _ in PANELS:
        P = {"shape": shape, "title": title, "unit": unit, "lines": []}
        for arm in names:
            first = levels(arm, shape, "first")
            if len(first) < 2:
                out["not_drawn"][arm] = {"model": arms[arm]["image"].rsplit("/", 1)[1], "why": "no sweep on record"}
                continue
            key = f"N1_concurrency_sweep.arms.{arm}.image"; image = arms[arm]["image"]; model, version = image.rsplit("/", 1)[1].rsplit(":", 1)
            P["lines"].append({"arm": arm, "model": model, "version": version, "image": {"source": PRE, "key": key, "value": image}, "first": first, "second": levels(arm, shape, "second"),
                               **({"night": "second", "records": LATER[arm]} if arm in LATER else {})})
        out["panels"].append(P)
    return out


def check(data):
    problems, n = [], 0
    seen = set()
    for P in data["panels"]:
        for L in P["lines"]:
            n += 1
            if F.value(F.load(L["image"]["source"]), L["image"]["key"]) != L["image"]["value"]:
                problems.append(f"{L['arm']}: the image differs from the pre-registration")
            for label in ("first", "second"):
                for e in L[label]:
                    for k, p in KEYS.items():
                        n += 1; want = F.value(F.load(e["source"]), p)
                        if want != e[k]:
                            problems.append(f"{e['source']} {p}: source {want} != table {e[k]}")
                    if e["errors"]:
                        problems.append(f"{e['source']}: a drawn level has errors")
                    if e["level"] != e["file_level"]:
                        problems.append(f"{e['source']}: the level in the file is not the level in its name")
                    seen.add((e["aiperf"], e["asked_s"]))
            if len({e["inputs_sha256"] for label in ("first", "second") for e in L[label]}) != 1:
                problems.append(f"{L['arm']} {P['shape']}: the levels of one line did not replay one set of request bodies")
            if not set(e["level"] for e in L["second"]) <= set(e["level"] for e in L["first"]):
                problems.append(f"{L['arm']} {P['shape']}: the second container ran a level the first did not")
    if len(seen) != 1:
        problems.append(f"the drawn levels did not use one load-tool version and one asked duration: {sorted(seen)}")
    if not any(P["lines"] for P in data["panels"]):
        problems.append("nothing to draw")
    return n, problems


def numbers_allowed(data):
    nums = set(NAME_NUMBERS) | set(data["canvas"].get("tick_labels", []))
    for P in data["panels"]:
        for L in P["lines"]:
            nums |= {L["version"]} | {str(e["level"]) for e in L["first"]} | {str(e["asked_s"]) for e in L["first"]} | {e["aiperf"] for e in L["first"]}
    return nums


def draw(data, theme, shift):
    plt, T, version = F.setup(theme)
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullLocator
    fig = plt.figure(figsize=(W / 72.0, H / 72.0), dpi=72, facecolor=T["bg"]); ticks = set()
    for i, (shape, title, unit, _, left) in enumerate(PANELS):
        P = data["panels"][i]
        ax = fig.add_axes([left + shift[0], BOTTOM + shift[1], PANEL_W + shift[2], HEIGHT + shift[3]], facecolor=T["bg"])
        ys, xs, handles = [], [], []
        for L in P["lines"]:
            col = COLOURS[L["arm"]][theme]; x = [e["items_per_s"] for e in L["first"]]; y = [e["p99_ms"] for e in L["first"]]
            ax.plot(x, y, color=col, linewidth=2.4, marker="o", markersize=9, markerfacecolor=col, markeredgecolor=col, zorder=3)
            ax.plot([e["items_per_s"] for e in L["second"]], [e["p99_ms"] for e in L["second"]], linestyle="none", marker="o", markersize=15, markerfacecolor="none", markeredgecolor=col, markeredgewidth=2.0, zorder=4)
            for e, off, ha, va in ((L["first"][0], (-8, -8), "right", "top"), (L["first"][-1], (8, 6), "left", "bottom")):
                ax.annotate(str(e["level"]), (e["items_per_s"], e["p99_ms"]), textcoords="offset points", xytext=off, fontsize=15, color=T["muted"], ha=ha, va=va)
            xs += x + [e["items_per_s"] for e in L["second"]]; ys += y + [e["p99_ms"] for e in L["second"]]
            handles.append(Line2D([], [], color=col, linewidth=2.4, marker="o", markersize=9, label=f"{L['model']} {L['version']}"))
        if xs:
            lo, hi = 10 ** math.floor(math.log10(min(ys))), 10 ** (math.ceil(math.log10(max(ys))) + 1)     # one decade above the data, for the legend
            ax.set_yscale("log"); ax.set_ylim(lo, hi); ax.set_xlim(0, max(xs) * 1.16)
            ax.yaxis.set_major_locator(FixedLocator([10 ** k for k in range(int(round(math.log10(lo))), int(math.floor(math.log10(hi))) + 1)])); ax.yaxis.set_minor_locator(NullLocator())
            ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True, steps=[1, 2, 5, 10]))
        fmt = FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 1 else f"{v:g}")
        ax.xaxis.set_major_formatter(fmt); ax.yaxis.set_major_formatter(fmt)
        ax.tick_params(labelsize=16, length=7, width=1.5); ax.grid(True, which="major", color=T["grid"], linewidth=1.5, zorder=0)
        for sp in ax.spines.values():
            sp.set_linewidth(1.5)
        ax.set_xlabel(unit, fontsize=20, labelpad=10)
        if i == 0:
            ax.set_ylabel("p99 duration of a request, ms (log scale)", fontsize=20, labelpad=10)
        ax.text(0.04, 0.965, title, transform=ax.transAxes, ha="left", va="top", fontsize=17, color=T["fg"], fontweight="bold")
        if handles:
            leg = ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.02, 0.915), fontsize=14.5, labelspacing=0.35, frameon=True, framealpha=0.92, facecolor=T["bg"], edgecolor=T["grid"], labelcolor=T["fg"], borderpad=0.5, handlelength=1.6)
            leg.get_frame().set_linewidth(1.5)
        fig.canvas.draw()
        ticks |= {t.get_text() for t in ax.get_xticklabels() + ax.get_yticklabels() if t.get_text()}
    one = next(e for P in data["panels"] for L in P["lines"] for e in L["first"])
    later = sorted({L["model"] for P in data["panels"] for L in P["lines"] if L.get("night") == "second"})
    fig.text(0.5, 0.030 if later else 0.036, f"One RTX 5090 · one NIM on the card at a time · AIPerf {one['aiperf']}, closed loop, {one['asked_s']} s per level, the load tool in a container on the NIM's network\n"
                         f"filled: every level in the first container · hollow: the two highest levels in a second new container · the number at the ends of a line: {CONTROL}"
                         + (f"\n{', '.join(later)}: swept on the second night, the other NIMs on the first" if later else ""),
             ha="center", va="bottom", fontsize=16.5 if not later else 15.5, style="italic", color=T["muted"], linespacing=1.4)
    fig.canvas.draw()
    F.save(fig, plt, NAME, theme, T)
    return sorted(ticks), version


def figure_checks(data):
    problems = []
    tl, sl = F.svg_texts(NAME, "light"); td, sd = F.svg_texts(NAME, "dark")
    if tl != td:
        problems.append("the light and the dark SVG do not contain the same text")
    if len(tl) < 20:
        problems.append(f"only {len(tl)} <text> elements: the text was not kept as text")
    written = set()
    for x in tl:
        written |= {m.rstrip(",") for m in re.findall(r"\d[\d,]*(?:\.\d+)*", x)}
    more = written - numbers_allowed(data)
    if more:
        problems.append(f"numbers on the figure that are not in the points file: {sorted(more)}")
    for what, pattern in F.FORBIDDEN:
        if any(re.search(pattern, x, re.I) for x in tl):
            problems.append(f"a text of the figure contains {what}")
        elif re.search(pattern, sl, re.I) or re.search(pattern, sd, re.I):
            problems.append(f"an SVG contains {what} outside its text")
    if "<image" in sl or "<image" in sd:
        problems.append("an SVG embeds an image")
    if not any(CONTROL in x for x in tl):
        problems.append(f"positive control: the words '{CONTROL}' are not in the figure's text")
    return len(tl), problems


def shifts():
    """(0, 0, 0, 0) first, then small fixed amounts (at most 3 px each way), the same on every run."""
    yield (0.0, 0.0, 0.0, 0.0)
    s = 20261012
    for _ in range(400):
        out = []
        for scale in (0.0019, 0.0033, 0.0019, 0.0033):
            s = (s * 1103515245 + 12345) % 2 ** 31; out.append(round((s / 2 ** 31 - 0.5) * 2 * scale, 6))
        yield tuple(out)


def self_test():
    ok = True

    def tt(name, got, want):
        nonlocal ok
        good = got == want; ok = ok and good
        print(("  PASS " if good else "  FAIL ") + f"{name}: {got} (want {want})")
    data = build(); n, problems = check(data)
    tt("every value reads back from its source", problems, [])
    tt("three panels", [P["shape"] for P in data["panels"]], [p[0] for p in PANELS])
    C = lambda: json.loads(json.dumps(data))
    line = next((i, j) for i, P in enumerate(data["panels"]) for j, L in enumerate(P["lines"]) if L["second"])
    bad = C(); bad["panels"][line[0]]["lines"][line[1]]["first"][0]["items_per_s"] += 1.0
    tt("negative control: one rate changed -> reported", len(check(bad)[1]), 1)
    bad = C(); bad["panels"][line[0]]["lines"][line[1]]["first"][1]["p99_ms"] += 0.5
    tt("negative control: one p99 changed -> reported", len(check(bad)[1]), 1)
    bad = C(); bad["panels"][line[0]]["lines"][line[1]]["first"][1]["errors"] = [{"count": 3}]
    tt("negative control: a level with errors -> reported twice (source, and the rule)", len(check(bad)[1]), 2)
    bad = C(); bad["panels"][line[0]]["lines"][line[1]]["first"][2]["level"] = 3
    tt("negative control: a level that is not its file's -> reported twice (source, and the rule)", len(check(bad)[1]), 2)
    bad = C(); bad["panels"][line[0]]["lines"][line[1]]["second"][0]["inputs_sha256"] = "0" * 64
    tt("negative control: other request bodies in the second container -> reported twice (source, and one set per line)", len(check(bad)[1]), 2)
    bad = C(); bad["panels"][line[0]]["lines"][line[1]]["first"][0]["asked_s"] = 60
    tt("negative control: one asked duration changed -> reported twice (source, and one duration for all)", len(check(bad)[1]), 2)
    bad = C(); bad["panels"][line[0]]["lines"][line[1]]["image"]["value"] += "x"
    tt("negative control: an image changed -> reported", len(check(bad)[1]), 1)
    tt("forbidden patterns fire on planted strings", [bool(re.search(pat, s, re.I)) for (_, pat), s in zip(F.FORBIDDEN, ("16 users", "x=47.3", "a → b", "2×"))], [True] * 4)
    tt("forbidden patterns stay silent on the figure's own words", [bool(re.search(pat, f"Passages per second · p99 duration of a request · {CONTROL}", re.I)) for _, pat in F.FORBIDDEN], [False] * 4)
    a, b = list(shifts())[:3], list(shifts())[:3]
    tt("the trial positions are the same on every run and start unmoved", (a == b, a[0]), (True, (0.0, 0.0, 0.0, 0.0)))
    print("SELF-TEST " + ("PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "draw"
    if mode == "self_test":
        sys.exit(0 if self_test() else 1)
    table = os.path.join(HERE, POINTS)
    if mode == "check":
        data = json.load(open(table, encoding="utf-8"))
    else:
        data = build(); pattern = "|".join(p for _, p in F.FORBIDDEN); tried = 0
        for shift in shifts():
            tried += 1
            ticks, version = draw(data, "dark", shift)
            if not re.search(pattern, open(os.path.join(HERE, NAME + "_dark.svg"), encoding="utf-8").read(), re.I):
                break
        draw(data, "light", shift)
        data["canvas"].update({"axes_moved_by": list(shift), "positions_tried": tried, "tick_labels": ticks}); data["matplotlib_version"] = version
        json.dump(data, open(table, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    n, problems = check(data)
    texts, more = figure_checks(data)
    problems += more
    for p in problems:
        print("  FAIL", p)
    print(f"{'drawn and ' if mode != 'check' else ''}checked: {n} values read back, {texts} text elements per SVG, problems {len(problems)}")
    sys.exit(1 if problems else 0)
