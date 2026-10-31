#!/usr/bin/env python3
"""Vol.4 · two figures drawn from the cells' own result files.

  whole_corpus_quality_light / _dark (.svg, .png)
        nDCG@10 (bars) and Recall@100 (dashes) of one encoder NIM on MIRACL zh, MIRACL ja and BEIR HotpotQA:
        the reduced corpus where one exists, every passage of the corpus, and those results reranked by two rerankers
  embedding_quality_vs_rate_light / _dark (.svg, .png)
        four embedding NIMs: nDCG@10 on BEIR SciFact and on the reduced MIRACL zh corpus against passages per second
  figure_points.json
        every drawn value with its source file and key

Nothing is measured here. Every value is one cell's own figure, read from that cell's file:
  nDCG@10, Recall@100   metrics.ndcg_cut_10, metrics.recall_100 of a score.json or score_after.json
  passages per second   passages_per_s_median of a throughput file (median of three timed passes over the first 4,096
                        passages of the reduced MIRACL zh corpus, 64 per request, one kept connection, the client in a
                        container on the NIM's Docker network)
Scope: each bar and each point is one cell alone. The figures draw no arrow, write no ratio and no statement that
relates one model to another. One line joins two points of the second figure: the same NIM image started twice in the
same session, once with each precision, nothing else changed (results/second_batch). The quality of its fp8 end is the
first session's cell of that image, which selected the same profile (checked on every run by the profile id).
A thin horizontal whisker on a point of the second figure reaches to the same NIM's second run from a container.

Card layout (the same for every figure of this repository): a 1600 x 900 canvas, the plot area in the vertical middle
60%, no title, text kept as text in the SVG (font 'Space Grotesk', falling back to sans-serif). The light and the dark
version differ in colours only. The model and its precision are in the line under the figure.

Checks done on every run (exit code 1 if one fails):
  - every value in figure_points.json is read back from its source file and key and must be equal;
  - first figure: the conditions of one corpus scored the same queries; reranking leaves Recall@100 unchanged; the
    whole-corpus nDCG@10 is not above the reduced-corpus one;
  - second figure: every timed cell used the same sample, request size and number of passes; the two ends of the
    joined pair are one image with two different profiles, and the fp8 end's profile is that of the quality cell;
  - every number written on a figure is in figure_points.json (or is part of a product's name);
  - the light and the dark SVG of a figure contain the same text; no arrow character, no multiplication sign, not the
    words 'user' / 'users', not '7.3' anywhere in a file; no embedded image.
usage: plot_vol4_figures.py            draw, write figure_points.json, check
       plot_vol4_figures.py check      check the existing points file against the sources (no drawing)
       plot_vol4_figures.py self_test
PNG bytes are reproducible with the same matplotlib version and the same fonts installed (recorded in the points file).
"""
import json, logging, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOL = os.path.dirname(HERE)
W, H = 1600, 900
BAND = (H - W / 1.9) / 2.0
POINTS = "figure_points.json"
THEMES = {"light": {"bg": "#FFFFFF", "fg": "#0F172A", "muted": "#475569", "grid": "#E2E8F0"},
          "dark": {"bg": "#0B0F19", "fg": "#E2E8F0", "muted": "#94A3B8", "grid": "#1E293B"}}
R = "results/"
WQ = R + "whole_corpus_quality/"; HQ = R + "hotpotqa_whole_corpus/"; FB = R + "first_batch/"; SB = R + "second_batch/"
PRE = WQ + "prediction_whole_corpus.json"
ADD = WQ + "addendum_second_reranker.json"

# ---- first figure -------------------------------------------------------------------------------------------------
CONDITIONS = [("reduced", "reduced corpus", {"light": "#64748B", "dark": "#94A3B8"}),
              ("whole", "whole corpus", {"light": "#0891B2", "dark": "#22D3EE"}),
              ("rerank_1b", "whole corpus + rerank 1b", {"light": "#2563EB", "dark": "#60A5FA"}),
              ("rerank_500m", "whole corpus + rerank 500m", {"light": "#7C3AED", "dark": "#A78BFA"})]
CORPORA = [
    ("MIRACL zh", "dev", {"reduced": FB + "nim_nemotron-3-embed-1b_auto/miracl-hn-zh/score.json", "whole": WQ + "whole_corpus/miracl-zh/score.json",
                          "rerank_1b": WQ + "rerank_llama-nemotron-rerank-1b-v2/miracl-zh/score_after.json", "rerank_500m": WQ + "rerank_llama-nemotron-rerank-500m-v2/miracl-zh/score_after.json"}, {}),
    ("MIRACL ja", "dev", {"reduced": FB + "nim_nemotron-3-embed-1b_auto/miracl-hn-ja/score.json", "whole": WQ + "whole_corpus/miracl-ja/score.json",
                          "rerank_1b": WQ + "rerank_llama-nemotron-rerank-1b-v2/miracl-ja/score_after.json", "rerank_500m": WQ + "rerank_llama-nemotron-rerank-500m-v2/miracl-ja/score_after.json"}, {}),
    ("BEIR HotpotQA", "test", {"whole": HQ + "whole_corpus/beir-hotpotqa/score.json", "rerank_1b": HQ + "rerank_llama-nemotron-rerank-1b-v2/beir-hotpotqa/score_after.json"},
     {"reduced": "no reduced\ntask, no\npublic value", "rerank_500m": "not run"}),
]
QKEYS = {"ndcg_cut_10": "metrics.ndcg_cut_10", "recall_100": "metrics.recall_100", "queries": "metrics.queries_scored"}
AXES1 = [0.0871, 0.2001, 0.895, 0.60]      # moved by a fraction of a pixel so that no coordinate in an SVG reads "7.3"

# ---- second figure ------------------------------------------------------------------------------------------------
TC = WQ + "timing_container_and_host/"
NIMS = [  # key in the timing cell, model, the first session's cell (quality), colour, label offsets per panel
    ("n3embed", "nemotron-3-embed-1b", FB + "nim_nemotron-3-embed-1b_auto", {"light": "#0891B2", "dark": "#22D3EE"}),
    ("embedvl", "llama-nemotron-embed-vl-1b-v2", FB + "nim_llama-nemotron-embed-vl-1b-v2_auto", {"light": "#B45309", "dark": "#FBBF24"}),
    ("embed1bv2", "llama-nemotron-embed-1b-v2", FB + "nim_llama-nemotron-embed-1b-v2_auto", {"light": "#2563EB", "dark": "#60A5FA"}),
    ("embed300m", "llama-nemotron-embed-300m-v2", FB + "nim_llama-nemotron-embed-300m-v2_auto", {"light": "#7C3AED", "dark": "#A78BFA"}),
]
PANELS = [("beir-scifact", "BEIR SciFact (test)", [0.0880, 0.2004, 0.405, 0.60], (0.690, 0.800), [0.70, 0.72, 0.74, 0.76, 0.78, 0.80]),
          ("miracl-hn-zh", "MIRACL zh, reduced corpus (dev)", [0.5780, 0.2004, 0.405, 0.60], (0.570, 0.680), [0.58, 0.60, 0.62, 0.64, 0.66, 0.68])]
XLIM2, XTICKS2 = (120.0, 900.0), [200, 400, 600, 800]
PAIR = {"model": "llama-nemotron-embed-1b-v2", "fp16": SB + "nim_llama-nemotron-embed-1b-v2_fp16", "fp8_rate": SB + "nim_llama-nemotron-embed-1b-v2_auto_same_night",
        "fp8_quality": FB + "nim_llama-nemotron-embed-1b-v2_auto"}
LABEL2 = {("beir-scifact", "n3embed"): (18, -44, "left"), ("beir-scifact", "embedvl"): (18, -52, "left"), ("beir-scifact", "embed1bv2"): (24, 2, "left"), ("beir-scifact", "embed300m"): (-18, 14, "right"),
          ("miracl-hn-zh", "n3embed"): (18, -6, "left"), ("miracl-hn-zh", "embedvl"): (16, 6, "left"), ("miracl-hn-zh", "embed1bv2"): (24, -52, "left"), ("miracl-hn-zh", "embed300m"): (-18, 14, "right")}
PAIR_LABEL = {("beir-scifact", "fp16"): (-12, 10, "right", "bottom"), ("beir-scifact", "fp8"): (2, -16, "center", "top"),
              ("miracl-hn-zh", "fp16"): (-10, -12, "right", "top"), ("miracl-hn-zh", "fp8"): (4, 14, "left", "bottom")}
SAMPLE_KEYS = {"sample_passages": "sample.passages", "batch": "batch", "reps": "reps"}
FORBIDDEN = (("the word 'user' or 'users'", r"\busers?\b"), ("'7.3'", r"7\.3"), ("an arrow character", "[←-⇿⟰-⟿⤀-⥿]"), ("a multiplication sign", "×"))
NAME_NUMBERS = {"5090", "10", "100", "3", "1", "2", "8", "16"}     # the card, the metrics' cut-offs, digits inside model names and precisions


def value(obj, path):
    for part in path.split("."):
        m = re.fullmatch(r"([^\[]+)((?:\[\d+\])*)", part)
        obj = obj[m.group(1)]
        for i in re.findall(r"\[(\d+)\]", m.group(2)):
            obj = obj[int(i)]
    return obj


_c = {}


def load(rel):
    if rel not in _c:
        _c[rel] = json.load(open(os.path.join(VOL, rel), encoding="utf-8"))
    return _c[rel]


def profile_of(throughput_rel):
    """What the server said about itself when the cell ran: image version, selected profile id, precision in a model file's name."""
    body = load(throughput_rel)["encoder"]["server"]["/v1/metadata"]["body"]
    names = " ".join(m.get("shortName", "") for m in body.get("modelInfo", []))
    prec = sorted(set(re.findall(r"\b(fp8|fp16|nvfp4|bf16)\b", names.replace("-", " "))))
    return {"version": body.get("version"), "profile_id": body.get("selectedModelProfileId"), "precision_in_the_model_files": prec[0] if len(prec) == 1 else None}


def build():
    enc = value(load(PRE), "vectors_used.whole_corpus.encoder")
    m = re.fullmatch(r"nvcr\.io/nim/nvidia/([\w.\-]+):([\d.]+) pinned to (fp\d+) .*", enc)
    out = {"what": "the values drawn on the two figures of this directory, each with its source file and key",
           "whole_corpus_quality": {"what": "nDCG@10 (bar) and Recall@100 (dash) of one encoder; one entry per corpus and condition",
                                    "encoder": {"source": PRE, "key": "vectors_used.whole_corpus.encoder", "value": enc, "model": m.group(1), "version": m.group(2), "precision": m.group(3)},
                                    "rerankers": {k: {"source": src, "key": key, "value": value(load(src), key)} for k, (src, key) in
                                                  (("rerank_1b", (PRE, "cell_D_reranking_the_whole_corpus_results.image")), ("rerank_500m", (ADD, "cell_D2.image")))},
                                    "keys": QKEYS, "canvas": {"width": W, "height": H, "axes": AXES1, "ylim": [0.0, 1.26]}, "corpora": []},
           "embedding_quality_vs_rate": {"what": "four embedding NIMs: nDCG@10 on two data sets against passages per second in the timed cell",
                                         "keys": {"passages_per_s": "passages_per_s_median", "ndcg_cut_10": "metrics.ndcg_cut_10", **SAMPLE_KEYS},
                                         "canvas": {"width": W, "height": H, "panels": {p[0]: {"axes": p[2], "ylim": list(p[3]), "yticks": p[4]} for p in PANELS}, "xlim": list(XLIM2), "xticks": XTICKS2},
                                         "points": [], "joined_pair": {}}}
    for name, split, files, absent in CORPORA:
        whole = load(files["whole"])
        c = {"corpus": name, "split": split, "passages_whole": value(whole, "source.passages"), "conditions": [], "not_drawn": absent}
        for key, label, _ in CONDITIONS:
            if key in files:
                s = load(files[key]); e = {"condition": key, "label": label, "source": files[key]}
                e.update({k: value(s, p) for k, p in QKEYS.items()})
                if key == "reduced":
                    e["passages"] = value(s, "source.passages")
                c["conditions"].append(e)
        out["whole_corpus_quality"]["corpora"].append(c)
    P = out["embedding_quality_vs_rate"]
    for key, model, cell, _ in NIMS:
        t1, t2 = TC + key + "/container_1.json", TC + key + "/container_2.json"
        p = {"nim": key, "model": model, "rate_source": t1, "second_run_source": t2, "passages_per_s": value(load(t1), "passages_per_s_median"),
             "passages_per_s_second_run": value(load(t2), "passages_per_s_median")}
        p.update({k: value(load(t1), q) for k, q in SAMPLE_KEYS.items()}); p.update(profile_of(t1))
        sk = f"cell_E_timing_from_two_places.nims.{model}.start"
        p["start"] = {"source": PRE, "key": sk, "value": value(load(PRE), sk)}
        p["quality"] = {ds: {"source": f"{cell}/{ds}/score.json", "ndcg_cut_10": value(load(f"{cell}/{ds}/score.json"), "metrics.ndcg_cut_10")} for ds, *_ in PANELS}
        p["quality_cell_profile_id"] = profile_of(f"{cell}/miracl-hn-zh/throughput.json")["profile_id"]
        P["points"].append(p)
    f16, f8 = PAIR["fp16"] + "/miracl-hn-zh/throughput.json", PAIR["fp8_rate"] + "/miracl-hn-zh/throughput.json"
    P["joined_pair"] = {"model": PAIR["model"], "what": "one NIM image started twice in the second session, once with each precision; nothing else changed",
                        "fp16": {"rate_source": f16, "passages_per_s": value(load(f16), "passages_per_s_median"), **profile_of(f16),
                                 "quality": {ds: {"source": f"{PAIR['fp16']}/{ds}/score.json", "ndcg_cut_10": value(load(f"{PAIR['fp16']}/{ds}/score.json"), "metrics.ndcg_cut_10")} for ds, *_ in PANELS}},
                        "fp8": {"rate_source": f8, "passages_per_s": value(load(f8), "passages_per_s_median"), **profile_of(f8),
                                "quality": {ds: {"source": f"{PAIR['fp8_quality']}/{ds}/score.json", "ndcg_cut_10": value(load(f"{PAIR['fp8_quality']}/{ds}/score.json"), "metrics.ndcg_cut_10")} for ds, *_ in PANELS},
                                "quality_cell_profile_id": profile_of(PAIR["fp8_quality"] + "/miracl-hn-zh/throughput.json")["profile_id"],
                                "note": "the fp8 start of the second session was timed and not scored; its quality is the first session's cell of the same image and profile"}}
    for end in ("fp16", "fp8"):
        P["joined_pair"][end].update({k: value(load(P["joined_pair"][end]["rate_source"]), q) for k, q in SAMPLE_KEYS.items()})
    return out


def check(data):
    """Read every value back from its source; the preconditions of each figure. -> (values read, problems)"""
    problems, n = [], 0

    def same(rel, path, have, what):
        nonlocal n
        n += 1; want = value(load(rel), path)
        if want != have:
            problems.append(f"{rel} {path}: source {want} != table {have} ({what})")

    Q = data["whole_corpus_quality"]
    same(Q["encoder"]["source"], Q["encoder"]["key"], Q["encoder"]["value"], "encoder")
    for k, r in Q["rerankers"].items():
        same(r["source"], r["key"], r["value"], k)
    if [c["corpus"] for c in Q["corpora"]] != [c[0] for c in CORPORA]:
        problems.append("first figure: the corpora are not the expected three")
    for c in Q["corpora"]:
        by = {e["condition"]: e for e in c["conditions"]}
        for e in c["conditions"]:
            for k, p in QKEYS.items():
                same(e["source"], p, e[k], f"{c['corpus']} {e['condition']}")
        if len({e["queries"] for e in c["conditions"]}) != 1:
            problems.append(f"{c['corpus']}: the conditions did not score the same number of queries")
        for k in ("rerank_1b", "rerank_500m"):
            if k in by and by[k]["recall_100"] != by["whole"]["recall_100"]:
                problems.append(f"{c['corpus']}: Recall@100 after {k} differs from the value before it")
        if "reduced" in by and by["whole"]["ndcg_cut_10"] > by["reduced"]["ndcg_cut_10"]:
            problems.append(f"{c['corpus']}: the whole-corpus nDCG@10 is above the reduced-corpus one")
        if set(by) | set(c["not_drawn"]) != {k for k, _, _ in CONDITIONS}:
            problems.append(f"{c['corpus']}: a condition is neither drawn nor named as not drawn")
    P = data["embedding_quality_vs_rate"]
    if [p["nim"] for p in P["points"]] != [x[0] for x in NIMS]:
        problems.append("second figure: the NIMs are not the expected four")
    cells = [(p["nim"], p) for p in P["points"]] + [("pair " + e, P["joined_pair"][e]) for e in ("fp16", "fp8")]
    for name, p in cells:
        same(p["rate_source"], "passages_per_s_median", p["passages_per_s"], name)
        for k, q in SAMPLE_KEYS.items():
            same(p["rate_source"], q, p[k], name)
        for ds, qv in p["quality"].items():
            same(qv["source"], "metrics.ndcg_cut_10", qv["ndcg_cut_10"], f"{name} {ds}")
        if profile_of(p["rate_source"]) != {k: p[k] for k in ("version", "profile_id", "precision_in_the_model_files")}:
            problems.append(f"{name}: what the server said about itself differs from the table")
    for p in P["points"]:
        same(p["second_run_source"], "passages_per_s_median", p["passages_per_s_second_run"], p["nim"] + " second run")
        same(p["start"]["source"], p["start"]["key"], p["start"]["value"], p["nim"] + " start")
        if p["quality_cell_profile_id"] != p["profile_id"]:
            problems.append(f"{p['nim']}: the timed cell and the quality cell report different profiles")
    if len({(p["sample_passages"], p["batch"], p["reps"]) for _, p in cells}) != 1:
        problems.append("second figure: the timed cells did not use one sample, request size and number of passes")
    a, b = P["joined_pair"]["fp16"], P["joined_pair"]["fp8"]
    if not (a["version"] == b["version"] and a["profile_id"] != b["profile_id"] and a["precision_in_the_model_files"] == "fp16" and b["precision_in_the_model_files"] == "fp8"):
        problems.append("joined pair: the two ends are not one image version with an fp16 and an fp8 profile")
    if b["quality_cell_profile_id"] != b["profile_id"]:
        problems.append("joined pair: the fp8 end's quality cell did not run the profile of its timed cell")
    return n, problems


def f3(x):
    return f"{x:.3f}"


def nim_label(p):
    stated = re.search(r"\bfp\d+\b", (p.get("start") or {}).get("value", ""))     # a 2.x image's metadata names no precision: the start setting does
    prec = p["precision_in_the_model_files"] or (stated.group(0) if stated else None)
    return f"{p['model']}\n{p['version']}" + (f" · {prec}" if prec else "")


def numbers_allowed(data, fig):
    nums = set(NAME_NUMBERS)
    Q, P = data["whole_corpus_quality"], data["embedding_quality_vs_rate"]
    if fig == "whole_corpus_quality":
        nums |= {"0.0", "0.2", "0.4", "0.6", "0.8", "1.0", "500", Q["encoder"]["version"]} | set(re.findall(r"\d+", Q["encoder"]["precision"]))
        for r in Q["rerankers"].values():
            nums.add(r["value"].rsplit(":", 1)[1])
        for c in Q["corpora"]:
            nums.add(f"{c['passages_whole']:,}")
            for e in c["conditions"]:
                nums |= {f3(e["ndcg_cut_10"]), f3(e["recall_100"]), f"{e['queries']:,}"}
                if "passages" in e:
                    nums.add(f"{e['passages']:,}")
    else:
        nums |= {str(t) for t in XTICKS2} | {f"{t:.2f}" for p in PANELS for t in p[4]} | {"300", "500"}
        for p in P["points"] + [P["joined_pair"]["fp16"], P["joined_pair"]["fp8"]]:
            nums |= {p["version"], f"{p['sample_passages']:,}", str(p["batch"]), str(p["reps"])}
    return nums


def setup(theme):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    T = THEMES[theme]
    plt.rcParams.update({"font.family": ["Space Grotesk", "sans-serif"], "font.sans-serif": ["DejaVu Sans"], "svg.fonttype": "none", "svg.hashsalt": "vol4-figures",
                         "text.color": T["fg"], "axes.labelcolor": T["fg"], "axes.edgecolor": T["muted"], "xtick.color": T["fg"], "ytick.color": T["fg"]})
    return plt, T, matplotlib.__version__


def save(fig, plt, name, theme, T):
    base = os.path.join(HERE, f"{name}_{theme}")
    fig.savefig(base + ".png", dpi=72, facecolor=T["bg"], metadata={"Software": None})
    fig.savefig(base + ".svg", facecolor=T["bg"], metadata={"Date": None, "Creator": None})
    raw = open(base + ".svg", "rb").read().replace(b"\r\n", b"\n")
    raw = raw.replace(b'width="1600pt" height="900pt"', b'width="1600" height="900"', 1)
    raw = raw.replace(b"'Space Grotesk', 'DejaVu Sans', sans-serif", b"'Space Grotesk', sans-serif")
    open(base + ".svg", "wb").write(raw)
    plt.close(fig)


def draw_quality(data, theme):
    plt, T, version = setup(theme)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.ticker import FixedLocator, NullLocator
    Q = data["whole_corpus_quality"]
    fig = plt.figure(figsize=(W / 72.0, H / 72.0), dpi=72, facecolor=T["bg"]); ax = fig.add_axes(AXES1, facecolor=T["bg"])
    width = 0.2; ticks, labels = [], []
    for g, c in enumerate(Q["corpora"]):
        by = {e["condition"]: e for e in c["conditions"]}
        for j, (key, _, colour) in enumerate(CONDITIONS):
            x = g + (j - 1.5) * width
            if key in by:
                e = by[key]
                ax.bar(x, e["ndcg_cut_10"], width * 0.86, color=colour[theme], zorder=2)
                ax.plot([x - width * 0.36, x + width * 0.36], [e["recall_100"]] * 2, color=T["fg"], linewidth=3.0, solid_capstyle="butt", zorder=3)
                ax.text(x, e["ndcg_cut_10"] - 0.035, f3(e["ndcg_cut_10"]), ha="center", va="top", fontsize=17, color=T["bg"], fontweight="bold", zorder=4)
                ax.text(x, e["recall_100"] + 0.012, f3(e["recall_100"]), ha="center", va="bottom", fontsize=15, color=T["muted"], zorder=4)
            else:
                ax.text(x - 0.02, 0.03, c["not_drawn"][key], ha="center", va="bottom", fontsize=14, color=T["muted"], style="italic", linespacing=1.3, zorder=4)
        red = by.get("reduced")
        ticks.append(g); labels.append(f"{c['corpus']} ({c['split']}, {by['whole']['queries']:,} queries)\n" + (f"reduced {red['passages']:,} · " if red else "") + f"whole {c['passages_whole']:,} passages")
    ax.set_xlim(-0.55, len(Q["corpora"]) - 0.45); ax.set_ylim(0.0, 1.26)
    ax.xaxis.set_major_locator(FixedLocator(ticks)); ax.set_xticklabels(labels, fontsize=17, linespacing=1.4)
    ax.yaxis.set_major_locator(FixedLocator([0, 0.2, 0.4, 0.6, 0.8, 1.0])); ax.yaxis.set_minor_locator(NullLocator())
    ax.tick_params(axis="y", labelsize=21, length=7, width=1.5); ax.tick_params(axis="x", length=0, pad=12)
    ax.grid(True, axis="y", which="major", color=T["grid"], linewidth=1.5, zorder=0)
    for sp in ax.spines.values():
        sp.set_linewidth(1.5)
    ax.set_ylabel("nDCG@10 (bars) · Recall@100 (dashes)", fontsize=22, labelpad=12)
    h = [Patch(facecolor=colour[theme], label=label) for _, label, colour in CONDITIONS] + [Line2D([], [], color=T["fg"], linewidth=3.0, label="dash: Recall@100 of the same results")]
    leg = ax.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, 0.985), ncol=5, fontsize=15.5, frameon=True, framealpha=0.92, facecolor=T["bg"], edgecolor=T["grid"], labelcolor=T["fg"],
                    borderpad=0.6, columnspacing=1.6, handlelength=1.4)
    leg.get_frame().set_linewidth(1.5)
    enc = Q["encoder"]; rr = {k: v["value"].rsplit("/", 1)[1] for k, v in Q["rerankers"].items()}
    fig.text(0.5, 0.036, f"One RTX 5090 · encoder {enc['model']} NIM {enc['version']} at {enc['precision']} · cosine of every query with every passage, no index\n"
                         f"rerankers {rr['rerank_1b']} and {rr['rerank_500m']} on the first 100 results of each query · one run per cell",
             ha="center", va="bottom", fontsize=17, style="italic", color=T["muted"], linespacing=1.45)
    fig.canvas.draw()
    save(fig, plt, "whole_corpus_quality", theme, T)
    return version


def draw_rate(data, theme):
    plt, T, version = setup(theme)
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    P = data["embedding_quality_vs_rate"]; colour = {k: c for k, _, _, c in NIMS}; pair = P["joined_pair"]; pc = colour["embed1bv2"][theme]
    fig = plt.figure(figsize=(W / 72.0, H / 72.0), dpi=72, facecolor=T["bg"]); outside = []
    for i, (ds, title, axes, ylim, yticks) in enumerate(PANELS):
        ax = fig.add_axes(axes, facecolor=T["bg"])
        xs = [pair["fp16"]["passages_per_s"], pair["fp8"]["passages_per_s"]]; ys = [pair["fp16"]["quality"][ds]["ndcg_cut_10"], pair["fp8"]["quality"][ds]["ndcg_cut_10"]]
        ax.plot(xs, ys, color=pc, linewidth=2.0, zorder=2)
        ax.plot(xs, ys, linestyle="none", marker="D", markersize=11, markerfacecolor=T["bg"], markeredgecolor=pc, markeredgewidth=2.2, zorder=5)
        for end, x_, y_ in (("fp16", xs[0], ys[0]), ("fp8", xs[1], ys[1])):
            dx, dy, ha, va = PAIR_LABEL[(ds, end)]
            ax.annotate(end, (x_, y_), textcoords="offset points", xytext=(dx, dy), fontsize=15, color=T["muted"], ha=ha, va=va)
        for p in P["points"]:
            col = colour[p["nim"]][theme]; x, y = p["passages_per_s"], p["quality"][ds]["ndcg_cut_10"]
            ax.plot([x, p["passages_per_s_second_run"]], [y, y], color=col, linewidth=2.2, solid_capstyle="butt", zorder=2)
            ax.plot([p["passages_per_s_second_run"]] * 2, [y - (ylim[1] - ylim[0]) * 0.012, y + (ylim[1] - ylim[0]) * 0.012], color=col, linewidth=2.2, zorder=2)
            ax.plot([x], [y], linestyle="none", marker="o", markersize=19, markerfacecolor=col, markeredgecolor=col, markeredgewidth=3.2, zorder=4)
            dx, dy, ha = LABEL2[(ds, p["nim"])]
            ax.annotate(nim_label(p), (x, y), textcoords="offset points", xytext=(dx, dy), fontsize=16, color=T["fg"], ha=ha, va="bottom", linespacing=1.25)
        ax.set_xlim(*XLIM2); ax.set_ylim(*ylim)
        for p in P["points"]:
            px, py = ax.transData.transform((p["passages_per_s"], p["quality"][ds]["ndcg_cut_10"]))
            if not (BAND <= py <= H - BAND and 0 <= px <= W):
                outside.append(f"{ds} {theme}: {p['nim']} is outside the central 1.9:1 band")
        ax.xaxis.set_major_locator(FixedLocator(XTICKS2)); ax.yaxis.set_major_locator(FixedLocator(yticks)); ax.xaxis.set_minor_locator(NullLocator()); ax.yaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v):,}")); ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.2f}"))
        ax.tick_params(labelsize=20, length=7, width=1.5); ax.grid(True, which="major", color=T["grid"], linewidth=1.5, zorder=0)
        for sp in ax.spines.values():
            sp.set_linewidth(1.5)
        ax.set_xlabel("Passages per second", fontsize=22, labelpad=10)
        ax.set_ylabel("nDCG@10", fontsize=22, labelpad=10)
        ax.text(0.03, 0.955, title, transform=ax.transAxes, ha="left", va="top", fontsize=19, color=T["fg"], fontweight="bold")
        if i == 1:
            h = [Line2D([], [], color=T["muted"], marker="o", markersize=12, linestyle="none", label="one NIM as its image starts on this card"),
                 Line2D([], [], color=T["muted"], marker="|", markersize=12, markeredgewidth=2.2, linewidth=2.2, label="whisker: its second run from a container"),
                 Line2D([], [], color=T["muted"], marker="D", markersize=9, markerfacecolor=T["bg"], markeredgewidth=2.0, linewidth=2.0, label="joined: one image, the same session,\nfp16 and fp8, nothing else changed")]
            leg = ax.legend(handles=h, loc="lower left", bbox_to_anchor=(0.02, 0.02), fontsize=15, labelspacing=0.4, frameon=True, framealpha=0.92, facecolor=T["bg"], edgecolor=T["grid"], labelcolor=T["fg"], borderpad=0.55)
            leg.get_frame().set_linewidth(1.5)
    s = P["points"][0]
    fig.text(0.5, 0.036, f"One RTX 5090 · one NIM on the card at a time · rate: the first {s['sample_passages']:,} passages of the reduced MIRACL zh corpus, {s['batch']} per request, one kept connection,\n"
                         f"no concurrent requests, the client in a container · median of {s['reps']} passes · nDCG@10: exact search, the first session's cells",
             ha="center", va="bottom", fontsize=17, style="italic", color=T["muted"], linespacing=1.45)
    fig.canvas.draw()
    save(fig, plt, "embedding_quality_vs_rate", theme, T)
    return outside, version


def svg_texts(name, theme):
    s = open(os.path.join(HERE, f"{name}_{theme}.svg"), encoding="utf-8").read()
    return [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<text[^>]*>(.*?)</text>", s, re.S)], s


def figure_checks(data):
    problems, texts = [], {}
    for name, control in (("whole_corpus_quality", "Recall@100"), ("embedding_quality_vs_rate", "no concurrent requests")):
        tl, sl = svg_texts(name, "light"); td, sd = svg_texts(name, "dark"); texts[name] = len(tl)
        if tl != td:
            problems.append(f"{name}: the light and the dark SVG do not contain the same text")
        if len(tl) < 20:
            problems.append(f"{name}: only {len(tl)} <text> elements: the text was not kept as text")
        written = set()
        for x in tl:
            written |= {m.rstrip(",") for m in re.findall(r"\d[\d,]*(?:\.\d+)*", x)}
        more = written - numbers_allowed(data, name)
        if more:
            problems.append(f"{name}: numbers on the figure that are not in the table: {sorted(more)}")
        for what, pattern in FORBIDDEN:
            if any(re.search(pattern, x, re.I) for x in tl):
                problems.append(f"{name}: a text of the figure contains {what}")
            elif re.search(pattern, sl, re.I) or re.search(pattern, sd, re.I):
                problems.append(f"{name}: an SVG contains {what} outside its text (for '7.3', a coordinate: change the layout by a fraction of a pixel)")
        if "<image" in sl or "<image" in sd:
            problems.append(f"{name}: an SVG embeds an image")
        if not any(control in x for x in tl):
            problems.append(f"{name}: positive control: the words '{control}' are not in the figure's text")
    return texts, problems


def self_test():
    ok = True

    def tt(name, got, want):
        nonlocal ok
        good = got == want; ok = ok and good
        print(("  PASS " if good else "  FAIL ") + f"{name}: {got} (want {want})")
    data = build(); n, problems = check(data)
    tt("every value reads back from its source", problems, [])
    tt("three corpora; conditions drawn per corpus", [len(c["conditions"]) for c in data["whole_corpus_quality"]["corpora"]], [4, 4, 2])
    tt("four NIMs and a joined pair", (len(data["embedding_quality_vs_rate"]["points"]), sorted(data["embedding_quality_vs_rate"]["joined_pair"])[:2]), (4, ["fp16", "fp8"]))
    C = lambda: json.loads(json.dumps(data))
    bad = C(); bad["whole_corpus_quality"]["corpora"][0]["conditions"][1]["ndcg_cut_10"] += 0.001
    tt("negative control: one nDCG@10 changed -> reported", len(check(bad)[1]), 1)
    bad = C(); bad["whole_corpus_quality"]["corpora"][1]["conditions"][2]["recall_100"] -= 0.01
    tt("negative control: Recall@100 after reranking changed -> reported twice (source, and the rule)", len(check(bad)[1]), 2)
    bad = C(); bad["whole_corpus_quality"]["corpora"][0]["conditions"][0]["ndcg_cut_10"] = 0.5
    tt("negative control: reduced below whole -> reported twice (source, and the rule)", len(check(bad)[1]), 2)
    bad = C(); bad["whole_corpus_quality"]["corpora"][2]["not_drawn"].pop("rerank_500m")
    tt("negative control: a condition neither drawn nor named -> reported", len(check(bad)[1]), 1)
    bad = C(); bad["embedding_quality_vs_rate"]["points"][3]["passages_per_s"] += 1.0
    tt("negative control: one rate changed -> reported", len(check(bad)[1]), 1)
    bad = C(); bad["embedding_quality_vs_rate"]["points"][0]["batch"] = 32
    tt("negative control: one request size changed -> reported twice (source, and one sample for all)", len(check(bad)[1]), 2)
    bad = C(); bad["embedding_quality_vs_rate"]["joined_pair"]["fp8"]["profile_id"] = bad["embedding_quality_vs_rate"]["joined_pair"]["fp16"]["profile_id"]
    tt("negative control: the pair's two ends given one profile -> reported", len(check(bad)[1]) >= 2, True)
    bad = C(); bad["embedding_quality_vs_rate"]["points"][2]["quality_cell_profile_id"] = "x"
    tt("negative control: quality cell with another profile -> reported", len(check(bad)[1]), 1)
    tt("a 2.x image's label takes its precision from the start setting; one with no stated precision has none",
       [nim_label(p).split("\n")[1] for p in data["embedding_quality_vs_rate"]["points"]], ["2.2.2 · fp16", "2.3.0", "1.13.0 · fp8", "1.13.0 · fp8"])
    bad = C(); bad["embedding_quality_vs_rate"]["points"][0]["start"]["value"] = "NIM_ENGINE_PRECISION=fp8"
    tt("negative control: one start setting changed -> reported", len(check(bad)[1]), 1)
    tt("forbidden patterns fire on planted strings", [bool(re.search(pat, s, re.I)) for (_, pat), s in zip(FORBIDDEN, ("16 users", "x=47.3", "a → b", "2×"))], [True] * 4)
    tt("forbidden patterns stay silent on the figures' own words", [bool(re.search(pat, "Passages per second · no concurrent requests · nDCG@10", re.I)) for _, pat in FORBIDDEN], [False] * 4)
    print("SELF-TEST " + ("PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "draw"
    if mode == "self_test":
        sys.exit(0 if self_test() else 1)
    table = os.path.join(HERE, POINTS); extra = []
    if mode == "check":
        data = json.load(open(table, encoding="utf-8"))
    else:
        data = build()
        for theme in THEMES:
            version = draw_quality(data, theme)
            outside, version = draw_rate(data, theme); extra += outside
        data["matplotlib_version"] = version
        json.dump(data, open(table, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    n, problems = check(data)
    texts, more = figure_checks(data)
    problems += extra + more
    for p in problems:
        print("  FAIL", p)
    print(f"{'drawn and ' if mode != 'check' else ''}checked: {n} values read back, text elements per SVG {texts}, problems {len(problems)}")
    sys.exit(1 if problems else 0)
