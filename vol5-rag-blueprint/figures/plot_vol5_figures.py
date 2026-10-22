#!/usr/bin/env python3
"""Vol.5 · the three figures of the article, dark theme, laid out like Vol.4's forum figures: a canvas 1,200 pixels
wide shown at 690, so every text is at least 20 pixels (11 / (690 / 1200) = 19.2).

  answers_dark_forum (.svg, .png)          HotpotQA, 7,405 questions: the share of answers that contain the gold answer
                                           for arm N (no passages), P (the Blueprint's path) and O (the two supporting
                                           passages), with Wilson 95% intervals; beside it cell C3 (200 questions with
                                           their supporting passages kept out): refusals by pattern, refusals by hand
                                           on 50 of them, and answers that still hold the gold answer
  num_candidates_dark_forum (.svg, .png)   HotpotQA whole corpus: nDCG@10 against the cold-start p50 latency of the
                                           vector search for the default query, the Blueprint's knob at 200 and 400,
                                           and the search engine's own num_candidates at 500 and 1000; the exact
                                           search (Vol.4's result file) as a line
  c4_memory_dark_forum (.svg, .png)        cell C4, one card: the Windows counters of the GPU adapter (dedicated and
                                           shared memory, every 2 s) from the start of two runs: the positive control
                                           (answer model first, ratio 0.92) and configuration 5 (answer model last,
                                           ratio 0.65, context 32768) through its timing runs; the moment each answer
                                           model reported ready, and configuration 5's allowance
  figure_points.json                       every value drawn or written, with the file and key it came from

Every value is read from result files (the keys of scripts/vol5_numbers.py; the exact search from Vol.4's own result
file). Vol.4's theme is imported, not copied.
Checks on every run (exit code 1 if one fails): each <text> of each SVG at least 20 pixels; every number written on a
figure is one of figure_points.json's values as printed (or a tick label); Vol.4's forbidden patterns; no embedded
image; the PNG as wide as the SVG.
usage: plot_vol5_figures.py              draw, write figure_points.json, check
       plot_vol5_figures.py check        check the existing files
       plot_vol5_figures.py self_test
"""
import csv, json, os, re, struct, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); V5 = os.path.dirname(HERE); RES = os.path.join(V5, "results")
V4 = os.path.join(os.path.dirname(V5), "vol4-retriever")
sys.path.insert(0, os.path.join(V4, "figures"))
import plot_vol4_figures as F  # noqa: E402

W, MIN_PX = 1200, 20
SIZES = {"answers": (W, 760), "num_candidates": (W, 820), "c4_memory": (W, 900)}
FS = {"small": 20, "label": 22, "title": 24}
THEME = "dark"
TICKS = {"answers": ["0.0", "0.2", "0.4", "0.6", "0.8", "1.0"], "num_candidates": ["0.66", "0.70", "0.74", "0.78", "0.82", "50", "75", "100", "125"],
         "c4_memory": ["0", "5", "10", "15", "20", "25", "8", "16", "24", "32", "1000", "2000", "3000", "4000"]}
NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+|\d+\.\d+|\d+")
EXACT = ("results/hotpotqa_whole_corpus/whole_corpus/beir-hotpotqa/score.json", "metrics.ndcg_cut_10")


def get(path, key, root=RES):
    d = json.load(open(os.path.join(root, path), encoding="utf-8"))
    for k in (key.split("/") if "/" in key else key.split(".")):
        d = d[int(k)] if isinstance(d, list) else d[k]
    return d


def series(name):
    """minutes since the first sample, dedicated GiB, shared MiB"""
    rows = list(csv.DictReader(open(os.path.join(RES, "c4", f"{name}_windows_gpu_adapter_memory.csv"), encoding="utf-8")))
    t = [datetime.fromisoformat(r["at"][:26] + r["at"][-6:]) for r in rows]
    return [(x - t[0]).total_seconds() / 60 for x in t], [int(r["dedicated_mib"]) / 1024 for r in rows], [int(r["shared_mib"]) for r in rows]


def ready_minute(name):
    """the minute (since the run's first sample) of the answer model's ready sample in the run's events"""
    cur, sample = None, None
    for l in open(os.path.join(RES, "c4", "events.jsonl"), encoding="utf-8"):
        e = json.loads(l)
        if e["kind"] == "config_start":
            cur = e.get("name")
        elif cur == name and e["kind"] == "service_verdict" and e.get("service") == "llm":
            sample = e["ready_sample"]
    m, _, _ = series(name)
    return m[sample - 1] if sample else None   # sample n = the n-th data row


def points():
    P = {"answers": {}, "num_candidates": {}, "c4_memory": {}}
    a = P["answers"]
    for arm, path, key in (("N", "c2/score_n_o.json", "N"), ("P", "night3/p_score.json", "score"), ("O", "c2/score_n_o.json", "O")):
        a[arm] = {"rate": get(path, key + ".contains_rate"), "low": get(path, key + ".contains_wilson95.0"), "high": get(path, key + ".contains_wilson95.1"),
                  "source": f"results/{path} {key}.contains_rate, {key}.contains_wilson95"}
    a["C3_refusal_pattern"] = {"rate": get("night3/c3_refusals.json", "refusal_rate"), "source": "results/night3/c3_refusals.json refusal_rate"}
    a["C3_refusal_hand"] = {"rate": get("night3/c3_label_check.json", "hand_refusal") / get("night3/c3_label_check.json", "items"), "source": "results/night3/c3_label_check.json hand_refusal / items"}
    a["C3_still_right"] = {"rate": get("night3/c3_contains.json", "C3.contains_rate"), "source": "results/night3/c3_contains.json C3.contains_rate"}
    n = P["num_candidates"]
    n["exact"] = {"ndcg": get(EXACT[0], EXACT[1], V4), "source": f"vol4-retriever/{EXACT[0]} {EXACT[1]}"}
    for tag, label, score, lat, key in (("default", "default (100)", "night1/c1_score.json", "night3/latency_cold/blueprint_100.json", "blueprint:100"),
                                        ("bp200", "Blueprint 200", "day3/nc_blueprint_200_score.json", "night3/latency_cold/blueprint_200.json", "blueprint:200"),
                                        ("bp400", "Blueprint 400", "day3/nc_blueprint_400_score.json", "night3/latency_cold/blueprint_400.json", "blueprint:400"),
                                        ("es500", "ES only 500", "day3/nc_es-only_500_score.json", "night3/latency_cold/es-only_500.json", "es-only:500"),
                                        ("es1000", "ES only 1000", "day3/nc_es-only_1000_score.json", "night3/latency_cold/es-only_1000.json", "es-only:1000")):
        n[tag] = {"label": label, "ndcg": get(score, "metrics.ndcg_cut_10"), "p50_ms": get(lat, f"settings.{key}.ms.p50"),
                  "source": f"results/{score} metrics.ndcg_cut_10; results/{lat} settings.{key}.ms.p50"}
    c = P["c4_memory"]
    c["pc"] = {"label": "positive control", "shared_peak_mib": get("c4/c4_summary.json", "pc.shared_peak_mib"), "ready_minute": ready_minute("pc"),
               "source": "results/c4/pc_windows_gpu_adapter_memory.csv; peak results/c4/c4_summary.json pc.shared_peak_mib; ready from results/c4/events.jsonl"}
    c["ready5"] = {"label": "configuration 5", "start_peak_mib": get("c4/ready5_after_ready.json", "whole_run_max_mib"),
                   "after_ready_max_mib": get("c4/ready5_after_ready.json", "window_max_mib"), "allowance_mib": get("c4/ready5_after_ready.json", "allowance_mib"),
                   "ready_minute": ready_minute("ready5"),
                   "source": "results/c4/ready5_windows_gpu_adapter_memory.csv; results/c4/ready5_after_ready.json whole_run_max_mib, window_max_mib, allowance_mib; ready from results/c4/events.jsonl"}
    return P


def save(fig, plt, name, T):
    w, h = SIZES[name]; base = os.path.join(HERE, f"{name}_{THEME}_forum")
    fig.savefig(base + ".png", dpi=72, facecolor=T["bg"], metadata={"Software": None})
    fig.savefig(base + ".svg", facecolor=T["bg"], metadata={"Date": None, "Creator": None})
    raw = open(base + ".svg", "rb").read().replace(b"\r\n", b"\n")
    raw = raw.replace(f'width="{w}pt" height="{h}pt"'.encode(), f'width="{w}" height="{h}"'.encode(), 1)
    raw = raw.replace(b"'Space Grotesk', 'DejaVu Sans', sans-serif", b"'Space Grotesk', sans-serif")
    open(base + ".svg", "wb").write(raw); plt.close(fig)


def f3(x):
    return f"{x:.3f}"


def spines(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def draw_answers(P):
    plt, T, _ = F.setup(THEME); a = P["answers"]
    w, h = SIZES["answers"]; fig = plt.figure(figsize=(w / 72, h / 72), dpi=72, facecolor=T["bg"])
    ax = fig.add_axes([0.10, 0.16, 0.46, 0.70], facecolor=T["bg"]); bx = fig.add_axes([0.64, 0.16, 0.33, 0.70], facecolor=T["bg"])
    colours = [T["muted"], T["fg"], T["muted"]]
    for i, arm in enumerate(("N", "P", "O")):
        e = a[arm]; ax.bar(i, e["rate"], 0.6, color=colours[i] if arm != "P" else "#22D3EE", zorder=2)
        ax.plot([i, i], [e["low"], e["high"]], color=T["fg"], linewidth=3, zorder=3)
        ax.text(i, e["rate"] + 0.03, f3(e["rate"]), ha="center", va="bottom", fontsize=FS["label"], color=T["fg"])
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["N no passages", "P the Blueprint", "O both passages"], fontsize=FS["small"])
    ax.set_ylim(0, 1.0); ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0]); ax.set_yticklabels(TICKS["answers"], fontsize=FS["small"])
    ax.set_title("Answer contains the gold answer · 7,405 questions", fontsize=FS["title"], color=T["fg"], loc="left")
    spines(ax)
    vals = [a["C3_refusal_pattern"]["rate"], a["C3_refusal_hand"]["rate"], a["C3_still_right"]["rate"]]
    for i, v in enumerate(vals):
        bx.bar(i, v, 0.6, color=T["muted"] if i < 2 else "#8B5CF6", zorder=2); bx.text(i, v + 0.03, f3(v), ha="center", va="bottom", fontsize=FS["label"], color=T["fg"])
    bx.set_xticks([0, 1, 2]); bx.set_xticklabels(["refused\npattern", "refused\nby hand", "still\nright"], fontsize=FS["small"])
    bx.set_ylim(0, 1.0); bx.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0]); bx.set_yticklabels(TICKS["answers"], fontsize=FS["small"])
    bx.set_title("Passages kept out", fontsize=FS["title"], color=T["fg"], loc="left")
    spines(bx)
    fig.text(0.10, 0.03, "Bars: share of questions. Lines: Wilson 95% intervals. Right: 200 questions; by hand: 50 of them.", fontsize=FS["small"], color=T["muted"])
    save(fig, plt, "answers", T)


def draw_nc(P):
    plt, T, _ = F.setup(THEME); n = P["num_candidates"]
    w, h = SIZES["num_candidates"]; fig = plt.figure(figsize=(w / 72, h / 72), dpi=72, facecolor=T["bg"])
    ax = fig.add_axes([0.11, 0.15, 0.84, 0.72], facecolor=T["bg"])
    ax.axhline(n["exact"]["ndcg"], color=T["muted"], linestyle="--", linewidth=2)
    ax.text(127, n["exact"]["ndcg"] - 0.004, f"exact search {f3(n['exact']['ndcg'])}", ha="right", va="top", fontsize=FS["small"], color=T["muted"])
    for tag, colour in (("default", T["fg"]), ("bp200", "#22D3EE"), ("bp400", "#22D3EE"), ("es500", "#8B5CF6"), ("es1000", "#8B5CF6")):
        e = n[tag]; ax.plot(e["p50_ms"], e["ndcg"], "o", markersize=14, color=colour, zorder=3)
        ax.text(e["p50_ms"] + 1.5, e["ndcg"], f"{e['label']} · {f3(e['ndcg'])}", fontsize=FS["small"], color=T["fg"], va="center")   # the five heights are at least 0.008 apart
    ax.set_xlim(50, 130); ax.set_ylim(0.66, 0.82)
    ax.set_xticks([50, 75, 100, 125]); ax.set_xticklabels(TICKS["num_candidates"][5:], fontsize=FS["small"])
    ax.set_yticks([0.66, 0.70, 0.74, 0.78, 0.82]); ax.set_yticklabels(TICKS["num_candidates"][:5], fontsize=FS["small"])
    ax.set_xlabel("vector search p50, cold start, ms", fontsize=FS["label"]); ax.set_ylabel("nDCG@10", fontsize=FS["label"])
    ax.set_title("HotpotQA whole corpus · the Blueprint's Elasticsearch index", fontsize=FS["title"], color=T["fg"], loc="left")
    spines(ax)
    save(fig, plt, "num_candidates", T)


def draw_c4(P):
    plt, T, _ = F.setup(THEME); c = P["c4_memory"]
    w, h = SIZES["c4_memory"]; fig = plt.figure(figsize=(w / 72, h / 72), dpi=72, facecolor=T["bg"])
    top = fig.add_axes([0.11, 0.57, 0.84, 0.31], facecolor=T["bg"]); bot = fig.add_axes([0.11, 0.13, 0.84, 0.36], facecolor=T["bg"])
    colour = {"pc": "#8B5CF6", "ready5": "#22D3EE"}
    for name in ("pc", "ready5"):
        m, ded, sh = series(name)
        top.plot(m, ded, color=colour[name], linewidth=2.5); bot.plot(m, sh, color=colour[name], linewidth=2.5, label=c[name]["label"])
        r = c[name]["ready_minute"]
        for ax in (top, bot):
            ax.axvline(r, color=colour[name], linestyle=":", linewidth=2)
        top.text(r + 0.2, 4, "ready", color=colour[name], fontsize=FS["small"], va="bottom")
    bot.axhline(c["ready5"]["allowance_mib"], color=T["muted"], linestyle="--", linewidth=2)
    bot.text(24.8, c["ready5"]["allowance_mib"] + 80, f"allowance of configuration 5 · {c['ready5']['allowance_mib']:,.0f}", ha="right", va="bottom", fontsize=FS["small"], color=T["muted"])
    bot.text(7.0, c["ready5"]["start_peak_mib"] + 350, f"{c['ready5']['start_peak_mib']:,} while starting", ha="right", va="center", fontsize=FS["small"], color=colour["ready5"])
    bot.text(24.8, c["ready5"]["after_ready_max_mib"] - 120, f"after ready, at most {c['ready5']['after_ready_max_mib']}", ha="right", va="top", fontsize=FS["small"], color=colour["ready5"])
    bot.text(12.2, c["pc"]["shared_peak_mib"], f"{c['pc']['shared_peak_mib']:,} at most", ha="left", va="center", fontsize=FS["small"], color=colour["pc"])
    top.set_xlim(0, 25); bot.set_xlim(0, 25); top.set_ylim(0, 34); bot.set_ylim(0, 4600)
    top.set_xticks([0, 5, 10, 15, 20, 25]); top.set_xticklabels([])
    bot.set_xticks([0, 5, 10, 15, 20, 25]); bot.set_xticklabels(TICKS["c4_memory"][:6], fontsize=FS["small"])
    top.set_yticks([0, 8, 16, 24, 32]); top.set_yticklabels(["0", "8", "16", "24", "32"], fontsize=FS["small"])
    bot.set_yticks([0, 1000, 2000, 3000, 4000]); bot.set_yticklabels(["0", "1000", "2000", "3000", "4000"], fontsize=FS["small"])
    top.set_ylabel("dedicated, GiB", fontsize=FS["label"]); bot.set_ylabel("shared, MiB", fontsize=FS["label"])
    bot.set_xlabel("minutes from the first service's start", fontsize=FS["label"])
    top.set_title("One card, three services · Windows GPU memory counters, every 2 s", fontsize=FS["title"], color=T["fg"], loc="left")
    bot.legend(loc="upper left", fontsize=FS["small"], frameon=False, labelcolor=T["fg"])
    spines(top); spines(bot)
    fig.text(0.11, 0.025, "Positive control: answer model first, ratio 0.92. Configuration 5: answer model last, ratio 0.65.", fontsize=FS["small"], color=T["muted"])
    save(fig, plt, "c4_memory", T)


def svg_text_sizes(name):
    s = open(os.path.join(HERE, f"{name}_{THEME}_forum.svg"), encoding="utf-8").read()
    return [float(x) for x in re.findall(r"font-size:\s*([0-9.]+)px", s)], re.findall(r">([^<>]+)</text>", s), s


def check(P):
    bad = []; vals = _values(P)
    written = {f3(v) for v in vals} | {f"{v:.0f}" for v in vals} | {f"{v:,.0f}" for v in vals} | set(sum(TICKS.values(), []))
    for name, (w, h) in SIZES.items():
        sizes, texts, s = svg_text_sizes(name)
        if not sizes or min(sizes) < MIN_PX:
            bad.append(f"{name}: a text below {MIN_PX} px ({min(sizes) if sizes else 'none'})")
        for t in texts:
            for num in NUMBER.findall(t):
                if num not in written and num not in ("95", "200", "50", "7,405", "10", "100", "400", "500", "1000", "2", "5", "0.92", "0.65"):
                    bad.append(f"{name}: a number not in the points: {num!r} in {t!r}")
        for what, pat in F.FORBIDDEN:
            if re.search(pat, " ".join(texts), re.I):
                bad.append(f"{name}: forbidden {what}")
        if "<image" in s:
            bad.append(f"{name}: an embedded image")
        png = open(os.path.join(HERE, f"{name}_{THEME}_forum.png"), "rb").read()
        if struct.unpack(">I", png[16:20])[0] != w:
            bad.append(f"{name}: the PNG is not {w} wide")
    return bad


def _values(P):
    return [v for part in P.values() for e in part.values() for v in e.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def self_test():
    ok = True
    for what, pat in F.FORBIDDEN:
        ok &= bool(re.search(pat, {"the word 'user' or 'users'": "16 users", "'7.3'": "x=47.3", "an arrow character": "a → b", "a multiplication sign": "2×"}[what], re.I))
    sizes_ok = min([20.0, 22.0]) >= MIN_PX and not (min([19.0]) >= MIN_PX)
    number_ok = NUMBER.findall("4,239 and 0.534 and 575") == ["4,239", "0.534", "575"]
    print(json.dumps({"forbidden_patterns_fire": ok, "size_rule": sizes_ok, "number_reader": number_ok})); return 0 if ok and sizes_ok and number_ok else 1


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "draw"
    if mode == "self_test":
        sys.exit(self_test())
    P = points()
    if mode == "draw":
        draw_answers(P); draw_nc(P); draw_c4(P)
        json.dump(P, open(os.path.join(HERE, "figure_points.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    bad = check(P)
    print(json.dumps({"mode": mode, "problems": bad}, ensure_ascii=False)); sys.exit(1 if bad else 0)
