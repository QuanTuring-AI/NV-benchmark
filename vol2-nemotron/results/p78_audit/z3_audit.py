#!/usr/bin/env python3
"""Z3 audit: GPU state at the END of every measured cell of the Vol.2 runs p50_* / p53_* / p55_*.

Read-only. Every input is read from the committed tree (`git ls-files` + `git show HEAD:<path>`) of the repo given by
--repo (default: the repository this script sits in, three levels up). Outputs go to --out (default: this script's directory):
z3_audit.json (one row per cell) and z3_audit.md (tables + summaries).

Clean-window fingerprint (from tools/g8_gate.py's cited source window): util_pct == 0 AND 26 <= power_w <= 42.
  clean          end record exists, util == 0 and power in [26, 42]
  dirty          end record exists, util > 0 or power outside [26, 42] (reasons listed)
  undeterminable no end-of-cell record for that cell (a missing record is never treated as clean)

What counts as the end-of-cell record, per run format (each choice is printed per run):
  concurrency runs (levels.jsonl)  -> the level's own `gpu_end` (nvidia-smi taken right after AIPerf returned)
  per-request runs (requests.jsonl)-> `gpu_after` of the cell's LAST measured request (taken the instant it returned)
  footprint runs (configs.jsonl)   -> `gpu_after_probe` (right after the 3-question probe); a start that never
                                      probed has only `gpu_after_stop` (after container removal) -> undeterminable
  guardrails / judge runs          -> no per-cell GPU record (request arms interleave in one container) -> undeterminable
  runs with no GPU work            -> 0 cells
Run-level records (ctx.txt 'end' line, events.jsonl gpu_after_stop) are reported separately, never as a cell end.

Feeds: every draft citation is a (file, section, exact substring) triple; the script asserts each substring is present
in the committed file, so a feed cannot point at a number the draft does not contain.
"""
import argparse, collections, json, os, subprocess, sys

LO, HI = 26.0, 42.0
RES = "vol2-nemotron/results"
DRAFTS = {"BASELINE": "vol2-nemotron/BASELINE.md", "FOOTPRINT": "vol2-nemotron/FOOTPRINT.md",
          "VOL2README": "vol2-nemotron/README.md", "ROOTREADME": "README.md"}


# ------------------------------------------------------------------ classifier
def classify(rec):
    """rec: dict with util_pct and power_w, or None. Returns (classification, reasons)."""
    if not isinstance(rec, dict) or rec.get("util_pct") is None or rec.get("power_w") is None:
        return "undeterminable", ["no end-of-cell record"]
    u, p = float(rec["util_pct"]), float(rec["power_w"])
    why = []
    if u > 0:
        why.append(f"util {u:g}% > 0")
    if p < LO:
        why.append(f"power {p:g} W < {LO:g}")
    if p > HI:
        why.append(f"power {p:g} W > {HI:g}")
    return ("dirty", why) if why else ("clean", [])


def positive_control():
    cases = [("util 0 / 30 W", {"util_pct": 0, "power_w": 30.0}, "clean"),
             ("util 5 / 30 W", {"util_pct": 5, "power_w": 30.0}, "dirty"),
             ("util 0 / 60 W", {"util_pct": 0, "power_w": 60.0}, "dirty"),
             ("missing record", None, "undeterminable")]
    ok = True
    print("== positive control (classifier on synthetic records)")
    for name, rec, want in cases:
        got, why = classify(rec)
        ok &= got == want
        print(f"   {name:16s} -> {got:15s} expected {want:15s} {'OK' if got == want else 'FAIL'} {why}")
    if not ok:
        sys.exit("positive control failed")
    return [{"case": n, "record": r, "expected": w, "got": classify(r)[0]} for n, r, w in cases]


# ------------------------------------------------------------------ git access
class Repo:
    def __init__(self, root):
        self.root = root
        self.files = subprocess.run(["git", "ls-files", RES], cwd=root, capture_output=True, text=True,
                                    check=True).stdout.splitlines()
        self._cache = {}

    def text(self, path):
        if path not in self._cache:
            self._cache[path] = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=self.root, capture_output=True,
                                               check=True).stdout.decode("utf-8")
        return self._cache[path]

    def jsonl(self, path):
        return [(i + 1, json.loads(l)) for i, l in enumerate(self.text(path).splitlines()) if l.strip()]

    def has(self, path):
        return path in self.files


# ------------------------------------------------------------------ feeds
class Feeds:
    def __init__(self, repo):
        self.repo, self.checked = repo, 0

    def f(self, key, section, quote, gloss):
        path = DRAFTS[key]
        if quote not in self.repo.text(path):
            sys.exit(f"feed quote not found in {path}: {quote!r}")
        self.checked += 1
        return f"{path} {section}: {gloss}"


def conc_sweep_feeds(F, run, arm, prof, cont, n, ladder):
    """Feeds for concurrency cells. `ladder` = sorted measured levels of that main sweep."""
    out = []
    B, R = "BASELINE", "ROOTREADME"
    def slo(S, I, qS, qI, sec):
        nxt = lambda x: min([l for l in ladder if l > x], default=None)
        if n <= S or n == nxt(S):
            out.append(F.f(B, sec, qS, f"largest c inside server SLO = {S}" + (" (this level is where it fails)" if n == nxt(S) else " (every level <= it must pass)")))
        if n <= I or n == nxt(I):
            out.append(F.f(B, sec, qI, f"largest c inside interactive SLO = {I}" + (" (this level is where it fails)" if n == nxt(I) else " (every level <= it must pass)")))
    if run == "p53_concurrency_v2":
        sec = "§C (second-run table)"
        if (arm, prof, cont) == ("A1", "C", "main"):
            slo(16, 16, "**16** (p99 TTFT 434 ms, p99 ITL 20.6 ms)", "**16** (p99 TTFT 434 ms, p99 ITL 20.6 ms) | **16** |", sec)
            if n == 16: out.append(F.f(B, sec, "777 tok/s", "A1·C throughput at c=16: 777 tok/s; p99 TTFT 434 ms, p99 ITL 20.6 ms"))
            if n == 32:
                out.append(F.f(B, sec, "**engine crash at c=32**", "A1 ceiling: engine crash at c=32"))
                out.append(F.f(R, "Headline results · Nemotron (Vol.2)", "where the dense option's engine crashes at 32", "dense option's engine crashes at 32"))
        if (arm, prof, cont) == ("A1", "C", "fresh") and n == 32:
            out.append(F.f(B, sec, "3 of 4 containers at 32, the fourth at 64", "crash count: 3 of 4 containers at 32"))
            out.append(F.f(R, "Headline results · Nemotron (Vol.2)", "where the dense option's engine crashes at 32", "dense option's engine crashes at 32"))
        if (arm, prof, cont) == ("A1", "R", "main"):
            slo(4, 1, "**4** (c=8: p99 TTFT 2.5 s)", "**1** (c=2: 631 ms)", sec)
            if n == 4: out.append(F.f(B, sec, "234 tok/s", "A1·R throughput at c=4: 234 tok/s"))
            if n == 32: out.append(F.f(B, sec, "3 of 4 containers at 32", "A1·R engine crash at c=32 (3 of 4 containers at 32)"))
        if (arm, prof, cont) == ("A1", "R", "fresh") and n in (32, 64):
            out.append(F.f(B, sec, "the fourth at 64", "the fourth container " + ("survived 32" if n == 32 else "crashed at 64")))
        if (arm, prof, cont) == ("A2", "C", "main"):
            slo(32, 32, "**32** (p99 TTFT 379 ms, p99 ITL 22.2 ms)", "**32** (p99 TTFT 379 ms, p99 ITL 22.2 ms) | **32** |", sec)
            if n == 32:
                out.append(F.f(B, sec, "**1,540 tok/s** · saturates at 32", "A2·C throughput 1,540 tok/s at c=32, saturation at 32"))
                out.append(F.f(B, "§C (cap table, row 32)", "| 32 (above, earlier session) | 32 · 32 | 1,540 · 1,540 | 8 · 4 |", "cap-32 row: 32 · 32; 1,540 · 1,540"))
            if n == 64:
                out.append(F.f(B, sec, "(1,490 at 64)", "1,490 tok/s at c=64"))
                out.append(F.f(B, sec, "reached at c=64: queueing (p99 TTFT 4.6 s, ITL unchanged)", "ceiling reached at c=64, p99 TTFT 4.6 s"))
        if (arm, prof, cont) == ("A2", "R", "main"):
            slo(8, 4, "**8** (p99 TTFT 1.0 s)", "**4** (492 ms)", sec)
            if n == 8: out.append(F.f(B, sec, "884 tok/s", "A2·R throughput at c=8: 884 tok/s"))
            if n == 16: out.append(F.f(B, sec, "reached at c=16 (p99 TTFT 2.1 s)", "A2·R ceiling reached at c=16 (p99 TTFT 2.1 s)"))
            if n in (32, 64): out.append(F.f(B, sec, "saturates at 32 (1,462 → 1,464)", "A2·R saturation 1,462 → 1,464 tok/s"))
            out.append(F.f(B, sec, "p99 ITL < 24 ms up to c=64", "A2·R p99 ITL < 24 ms up to c=64"))
        if arm == "A2" and cont == "fresh":
            out.append(F.f(B, "§C (text under second-run table)", "Fresh-container repeats agree with the main sweeps within 0.3–3.5% on A2", "fresh repeats within 0.3–3.5% of main"))
    elif run == "p53_concurrency":
        if arm == "A1" and n >= 32:
            out.append(F.f(B, "§C (intro)", "A1's engine crash broke its \"all levels clean\" rule", "[qualitative] first run: A1 crash broke its rule (the run's conclusions are null; no number quoted)"))
    elif run.startswith("p55_concurrency_a2_"):
        cap = int(run.rsplit("_", 1)[1])
        sec = f"§C (cap table, row {cap})"
        rows = {256: "| **256 (image default)** | **128 · 32** | **2,238 · 3,999** | **8 · 2** |",
                128: "| 128 | 128 · 32 | 1,738 · 2,679 | 8 · 2 |",
                64: "| 64 | 64 · 16 | 1,130 · 1,470 (fresh container 1,804) | 8 · 2 |"}
        q = rows[cap]
        if cont == "main" and prof == "C":
            S, I = {256: (128, 32), 128: (128, 32), 64: (64, 16)}[cap]
            slo(S, I, q, q, sec)
            if cap == 256 and (n <= 128 or n == 256):
                out.append(F.f(R, "Headline results · Nemotron (Vol.2)", "stays inside the server SLO up to 128 concurrent requests", "chat profile inside server SLO up to 128"))
            if n == 32: out.append(F.f(B, sec, q, f"C throughput at c=32: {dict([(256,'2,238'),(128,'1,738'),(64,'1,130')])[cap]} tok/s"))
            if cap == 256 and n == 256:
                out.append(F.f(B, sec, q, "peak 3,999 tok/s (c=256)"))
                out.append(F.f(B, sec, "146 running, 99.7% of 733 blocks", "KV block pool binds: 146 running, 99.7% of 733 blocks"))
            if cap == 256 and n == 512:
                out.append(F.f(B, "§C reading (2)", "the ceiling on this card is about 146 concurrent sequences", "about 146 concurrent sequences (gauge at c=256 and 512)"))
            if cap == 128 and n == 128:
                out.append(F.f(B, sec, q, "peak 2,679 tok/s (c=128)"))
                out.append(F.f(B, "§C reading (2)", "87.3% at 128", "KV gauge 87.3% at cap 128"))
            if cap == 64 and n == 64:
                out.append(F.f(B, "§C reading (2)", "42.4% at 64", "KV gauge 42.4% at cap 64"))
                out.append(F.f(B, "§C reading (3)", "containers of one configuration differed by up to 31% at c=64", "main vs fresh up to 31% at c=64"))
            if cap == 64 and n == 128: out.append(F.f(B, sec, q, "peak 1,470 tok/s (c=128, main)"))
        if cont == "main" and prof == "R":
            slo(8, 2, q, q, sec)
        if cap == 64 and cont == "fresh" and prof == "C":
            if n == 128: out.append(F.f(B, sec, q, "fresh container 1,804 tok/s (c=128)"))
            if n == 64: out.append(F.f(B, "§C reading (3)", "containers of one configuration differed by up to 31% at c=64", "main vs fresh up to 31% at c=64"))
    elif run == "p55_capture_control":
        if n in (16, 32):
            out.append(F.f(B, "§C reading (3)", "cut the chat-profile rate to 0.47× at c=32 and 0.49× at c=16", "capture-size control ratio " + ("0.47× at c=32" if n == 32 else "0.49× at c=16")))
    return out


def ledger(F, run):
    q = {"p53_concurrency": ("(`p53_concurrency`) | 4,995", "4,995 completed over 36 levels"),
         "p53_concurrency_v2": ("(`p53_concurrency_v2`) | 5,145", "5,145 completed over 33 levels"),
         "p50_speed": ("(`p50_speed`) | 100", "100 single-request points"),
         "p53_answer": ("(`p53_answer`) | 100", "100 single-request points"),
         "p53_longctx": ("(`p53_longctx`) | 40", "40 single-request points"),
         "p53_longctx_addendum": ("(`p53_longctx_addendum`; 68 warm-up rows recorded, not counted) | 25", "25 measured points"),
         "p53_guardrails": ("(`p53_guardrails`) | 810", "810 rows"),
         "p50_footprint": ("(`p50_footprint` 15, addenda 6 + 8) | 29", "29 container starts"),
         "p50_footprint_addendum": ("(`p50_footprint` 15, addenda 6 + 8) | 29", "29 container starts"),
         "p50_footprint_addendum2": ("(`p50_footprint` 15, addenda 6 + 8) | 29", "29 container starts")}.get(run)
    return [F.f("VOL2README", "Data-point ledger", q[0], "[ledger count] " + q[1])] if q else []


def request_feeds(F, run, cell):
    B, R, FP = "BASELINE", "ROOTREADME", "FOOTPRINT"
    arm = cell.split("_")[0].upper()
    out = []
    if run == "p50_speed":
        out += [F.f(B, "§B speed table", "72.9 | 305.1 | **4.14** [4.08, 4.19]", "generation rate A1 72.9 / A2 305.1 tok/s, A2/A1 4.14 [4.08, 4.19]"),
                F.f(B, "§B speed table", "72.4 | 292.8 | 4.01 [3.95, 4.07]", "tps ratio 4.01"),
                F.f(B, "§B speed table", "52.1 | 40.8 | 0.70 [0.58, 0.83]", "TTFT ratio 0.70"),
                F.f(B, "§B speed table", "42 / 50 | 37 / 50", "cut at 500 tokens 42/50, 37/50"),
                F.f(B, "§B speed table", "**72%**" if arm == "A1" else "**61%**", "arm health " + ("72%" if arm == "A1" else "61%")),
                F.f(R, "Headline results · Nemotron (Vol.2)", "the MoE option generates 4.14× faster per token", "4.14× faster per token")]
        if arm == "A1":
            out.append(F.f(FP, "§4 DGX Spark projection", "A1 generates at 72% of this card's peak bandwidth", "A1 at 72% of peak bandwidth"))
    elif run == "p53_answer":
        out += [F.f(B, "§B answer table", "**0.343** [0.307, 0.377] (≈ 2.9× faster per answer)", "answer time A1 19,814/20,102 vs A2 6,796/7,314 ms; ratio 0.343 (≈2.9×)"),
                F.f(B, "§B answer table", "1,405 / 1,421 | 2,017 / 2,145 | 1.44 [1.28, 1.58]", "completion tokens ratio 1.44"),
                F.f(B, "§B answer table", "0 / 50 | 6 / 50", "cut at 4,096: 0/50, 6/50"),
                F.f(B, "§B answer table", "71.1 | 298.9 | 4.15 [4.09, 4.20]", "generation rate 71.1 / 298.9, ratio 4.15"),
                F.f(B, "§B (text)", "health gate 70.5% / 59.9%", "health gate 70.5% / 59.9%"),
                F.f(R, "Headline results · Nemotron (Vol.2)", "finishes an answer about 2.9× sooner", "about 2.9× sooner per answer")]
    elif run == "p53_longctx":
        d = int(cell.split("_d")[1])
        if arm == "A1":
            q = {1024: ("| ~1,135 | 157 ms · 71.7 tok/s", "A1 ~1,135 tokens: 157 ms · 71.7 tok/s"),
                 4096: ("| ~3,770 | 408 ms · 71.6", "A1 ~3,770 tokens: 408 ms · 71.6 tok/s"),
                 16384: ("| ~14,215 | 1,398 ms · **44.7**", "A1 ~14,215 tokens: 1,398 ms · 44.7 tok/s"),
                 65536: ("| ~56,730 | 6,201 ms · **44.4**", "A1 ~56,730 tokens: 6,201 ms · 44.4 tok/s")}[d]
            out.append(F.f(B, "§D depth table", q[0], q[1]))
            if d in (4096, 16384):
                out.append(F.f(B, "§D (text)", "A1's generation rate steps down 38% between 4k and 16k", "A1 rate steps down 38% between 4k and 16k"))
        else:
            out.append("none found (A2 medians of this run are superseded by the addendum in BASELINE §D; not quoted numerically)")
        if d == 65536:
            out.append(F.f(B, "§D (intro)", "no context ceiling: both arms serve at `NIM_MAX_MODEL_LEN` 131,072", "no context ceiling at 131,072 (this container)"))
    elif run == "p53_longctx_addendum":
        d = int(cell.split("_d")[1])
        if arm == "A2":
            q = {1024: ("95 ms · **304.8**", "A2 ~1,135 tokens: 95 ms · 304.8 tok/s"),
                 4096: ("155 ms · **298.9**", "A2 ~3,770 tokens: 155 ms · 298.9 tok/s"),
                 16384: ("489 ms · **315.2**", "A2 ~14,215 tokens: 489 ms · 315.2 tok/s"),
                 65536: ("2,371 ms · **309.0**", "A2 ~56,730 tokens: 2,371 ms · 309.0 tok/s")}[d]
            out.append(F.f(B, "§D depth table", q[0], q[1]))
            if d in (1024, 65536):
                out.append(F.f(B, "§D (text)", "its TTFT grows sub-linearly (24.8× for 50× the tokens)", "A2 TTFT 24.8× for 50× the tokens"))
            if d == 1024:
                out.append(F.f(B, "§D (text)", "(304.8 → 308.4 tok/s", "A2 flat 304.8 → 308.4 tok/s (1k end)"))
        else:
            out.append(F.f(B, "§D depth table", "(addendum: 1,348 · 45.8)", "A1 16k addendum: 1,348 ms · 45.8 tok/s"))
    elif run == "p55_a1_capture":
        q = {"a1_4k_default": ("drops A1 from 76.4 to 52.3 tok/s", "A1 ~3.8k graphs on: 76.4 tok/s"),
             "a1_4k_eager": ("drops A1 from 76.4 to 52.3 tok/s", "A1 ~3.8k graphs off: 52.3 tok/s"),
             "a1_16k_default": ("at ~14k changes 55.7 to 51.7", "A1 ~14k default: 55.7 tok/s (also 'same session's 14k: 55.7' in the 120k row)"),
             "a1_16k_eager": ("at ~14k changes 55.7 to 51.7", "A1 ~14k graphs off: 51.7 tok/s")}.get(cell)
        out.append(F.f(B, "§D (text)", q[0], q[1]) if q else "none found (forward capture test, 51.5 tok/s, not cited in the drafts)")
    elif run == "p55_longctx_120k":
        if arm == "A2":
            out += [F.f(B, "§D depth table (~119,720 row)", "7,281 ms · **308.4**", "A2 ~120k: 7,281 ms · 308.4 tok/s"),
                    F.f(B, "§D (text)", "(304.8 → 308.4 tok/s", "A2 flat 304.8 → 308.4 tok/s (120k end)")]
        else:
            out.append(F.f(B, "§D depth table (~119,720 row)", "14,263 ms · **52.4**", "A1 ~120k: 14,263 ms · 52.4 tok/s"))
    return out


def footprint_feeds(F, run, arm, label):
    B, FP, R = "BASELINE", "FOOTPRINT", "ROOTREADME"
    k = (run, arm, label)
    table = {
        ("p50_footprint", "A1", "default"): [(B, "§A table", "29,420 MiB", "A1 level after default budget 29,420 MiB"), (FP, "§2 table", "29,420 (default 0.90 → 29,348 budget)", "A1 default level 29,420")],
        ("p50_footprint", "A1", "pct0.70"): [(B, "§A table", "0.70 → 22,825 MiB (22,909 in use)", "A1 smallest passing budget 0.70 → 22,825 (22,909 in use)"),
                                             (FP, "§2 table", "**22,375** (22,909 in use)", "A1 added at READY 22,375"),
                                             (FP, "§4 table", "| Memory in use at the smallest passing budget | 22,909 MiB | 21,872 MiB |", "A1 22,909 MiB in use"),
                                             (FP, "§4 text", "A2 needs about 1,600 MiB less budget than A1", "~1,600 MiB difference (A1 side)"),
                                             (R, "Headline results · Nemotron (Vol.2)", "22,909 / 25,972 MiB in use", "fit: 22,909 MiB (A1)")],
        ("p50_footprint", "A1", "pct0.675"): [(B, "§A table", "0.675 · KV blocks", "A1 largest failing budget 0.675"), (FP, "§2 table", "0.675 → 22,010: `No available memory for the cache blocks`", "A1 0.675 → 22,010 refusal"),
                                              (FP, "§4 table", "22,010 – 22,825 MiB", "A1 bracket 22,010 – 22,825")],
        ("p50_footprint", "A2", "default"): [(B, "§A table", "31,468 MiB", "A2 level after default budget 31,468 MiB"), (FP, "§2 table", "31,468 (default 0.92 → 29,998 budget, no clamp)", "A2 default level 31,468")],
        ("p50_footprint", "A2", "pct0.75"): [(B, "§A table", "0.75 → 24,455 MiB (25,972 in use)", "A2 smallest passing budget 0.75 → 24,455 (25,972 in use)"),
                                             (FP, "§2 table", "**25,835** (25,972 in use)", "A2 added at READY 25,835"),
                                             (FP, "§3 text", "about 14.6 MiB (3,260 MiB of budget over 224 sequences)", "14.6 MiB per sequence (24,455 − 21,195)"),
                                             (R, "Headline results · Nemotron (Vol.2)", "22,909 / 25,972 MiB in use", "fit: 25,972 MiB (A2)")],
        ("p50_footprint", "A2", "pct0.725"): [(B, "§A table", "0.725 · **Mamba state for 256 sequences**", "A2 largest failing 0.725 (Mamba state)"), (FP, "§2 table", "0.725 → 23,640: `max_num_seqs (256) exceeds available Mamba cache blocks (213)`", "A2 0.725 refusal (213 blocks)")],
        ("p50_footprint", "A2", "pct0.70"): [(FP, "§3 text", "146 at 0.70", "Mamba cache blocks 146 at 0.70")],
        ("p50_footprint", "A2FP8", "default"): [(B, "§A table", "never READY", "FP8 negative control never READY"), (FP, "§2 table", "did not reach READY: the default attempt spent its 20-minute window downloading the FP8 weights", "FP8 default attempt did not reach READY")],
        ("p50_footprint", "A2FP8", "pct0.85"): [(B, "§A table", "0.85 · KV blocks; weights alone exceed the card", "FP8 0.85 refused"), (B, "§F table", "start refused at 0.85 budget, never READY", "FP8 refused at 0.85")],
        ("p50_footprint_addendum2", "A2S32", "default"): [(B, "§A table", "29,850 MiB", "A2 seqs 32 level after default budget 29,850"), (FP, "§2 table", "29,850", "A2 seqs 32 default level 29,850")],
        ("p50_footprint_addendum2", "A2S32", "pct0.65"): [(B, "§A table", "0.65 → 21,195 MiB (21,872 in use)", "A2 seqs 32 smallest passing 0.65 → 21,195 (21,872 in use)"),
                                                         (FP, "§2 table", "**21,519** (21,872 in use)", "A2 seqs 32 added at READY 21,519"),
                                                         (FP, "§4 table", "| Memory in use at the smallest passing budget | 22,909 MiB | 21,872 MiB |", "A2 21,872 MiB in use"),
                                                         (B, "§A text", "A2 needs about 1,600 MiB less than A1", "~1,600 MiB difference (A2 side)"),
                                                         (FP, "§3 text", "about 14.6 MiB (3,260 MiB of budget over 224 sequences)", "14.6 MiB per sequence (24,455 − 21,195)")],
        ("p50_footprint_addendum2", "A2S32", "pct0.625"): [(B, "§A table", "0.625 · KV blocks", "A2 seqs 32 largest failing 0.625"), (FP, "§2 table", "0.625 → 20,379: `No available memory for the cache blocks`", "0.625 → 20,379 refusal"),
                                                          (FP, "§4 table", "20,379 – 21,195 MiB", "A2 bracket 20,379 – 21,195")],
    }
    out = [F.f(*t) for t in table.get(k, [])]
    if run == "p50_footprint_addendum":
        out.append(F.f(FP, "§3 text", "The first addendum tried `NIM_MAX_BATCH_SIZE=32` and reproduced the main run exactly", "[qualitative] 'reproduced the main run exactly' (no number quoted)"))
    return out or ["none found"]


# ------------------------------------------------------------------ runs
def ctx_end(repo, run):
    p = f"{RES}/{run}/ctx.txt"
    if not repo.has(p):
        return None
    lines = [l for l in repo.text(p).splitlines() if "| end |" in l or "| after " in l]
    return lines[-1] if lines else None


def audit(repo, F):
    runs = sorted({p.split("/")[2] for p in repo.files if p.split("/")[2][:4] in ("p50_", "p53_", "p55_")})
    cells, runinfo = [], {}
    for run in runs:
        base = f"{RES}/{run}"
        info = {"run": run, "format": None, "cells": 0, "with_end_record": 0, "warmup_levels": 0, "skipped_records": 0,
                "run_level_records": [], "note": ""}
        rows = []
        if repo.has(f"{base}/levels.jsonl"):
            info["format"] = "concurrency: levels.jsonl gpu_end per level"
            recs = repo.jsonl(f"{base}/levels.jsonl")
            ladders = collections.defaultdict(list)
            for ln, r in recs:
                if r.get("concurrency") is not None and not r.get("warmup"):
                    ladders[(r["arm"], r["profile"], r["container"])].append(r["concurrency"])
            for ln, r in recs:
                if r.get("concurrency") is None:
                    info["skipped_records"] += 1
                    continue
                wu = bool(r.get("warmup"))
                cid = f"{r['arm']}_{r['profile']}_{r['container']}_c{r['concurrency']:04d}" + ("_warmup" if wu else "")
                notes = []
                if r.get("rc") not in (0, None): notes.append(f"level rc={r.get('rc')} (engine dead: no measurement)")
                ge = r.get("gpu_end")
                if ge and ge.get("used_mib", 1e9) < 2000: notes.append(f"gpu_end memory {ge['used_mib']} MiB: engine no longer resident")
                feeds = [] if wu else conc_sweep_feeds(F, run, r["arm"], r["profile"], r["container"], r["concurrency"],
                                                      sorted(ladders[(r["arm"], r["profile"], "main")]))
                if not wu: feeds += ledger(F, run)
                rows.append({"cell": cid, "kind": "warmup (discarded)" if wu else "measured", "end": ge,
                             "source": f"{base}/levels.jsonl:{ln}:gpu_end", "end_at": r.get("end"), "notes": notes,
                             "feeds": feeds or ["none found"]})
        elif repo.has(f"{base}/requests.jsonl"):
            info["format"] = "per-request: gpu_after of the cell's last measured request"
            recs = repo.jsonl(f"{base}/requests.jsonl")
            if run in ("p50_speed", "p53_answer"):
                key = lambda r: f"{r['arm']}_block{r['block']}"
            elif run in ("p53_longctx", "p53_longctx_addendum"):
                key = lambda r: f"{r['arm']}_d{r['depth_target']}"
            else:
                key = lambda r: r["condition"]
            groups, wcount = collections.OrderedDict(), 0
            for ln, r in recs:
                if r.get("warmup"):
                    wcount += 1
                    continue
                groups.setdefault(key(r), []).append((ln, r))
            info["warmup_levels"] = wcount
            for cid, g in groups.items():
                g.sort(key=lambda x: x[1]["at"])
                ln, last = g[-1]
                rows.append({"cell": cid, "kind": f"measured ({len(g)} requests)", "end": last.get("gpu_after"),
                             "source": f"{base}/requests.jsonl:{ln}:gpu_after", "end_at": last.get("at"),
                             "notes": ["sampled the instant the last request returned (engine still at load); the fingerprint was defined on AIPerf level ends"],
                             "feeds": (request_feeds(F, run, cid) + ledger(F, run)) or ["none found"]})
        elif repo.has(f"{base}/configs.jsonl"):
            info["format"] = "footprint: gpu_after_probe per container start"
            for ln, r in repo.jsonl(f"{base}/configs.jsonl"):
                cid = f"{r['arm']}_{r['label']}"
                end = r.get("gpu_after_probe")
                notes = []
                if end is None:
                    st = r.get("gpu_after_stop") or {}
                    notes.append(f"never probed (start refused / not READY); only post-removal gpu_after_stop util {st.get('util_pct')}% / {st.get('power_w')} W, not a cell end")
                else:
                    notes.append("sampled right after the 3-question probe; the measured quantity is memory at READY (gpu_ready)")
                rows.append({"cell": cid, "kind": "measured (one container start)", "end": end,
                             "source": f"{base}/configs.jsonl:{ln}:gpu_after_probe" if end else "none",
                             "end_at": None, "notes": notes,
                             "feeds": footprint_feeds(F, run, r["arm"], r["label"]) + ledger(F, run)})
        elif repo.has(f"{base}/rows_public.jsonl"):
            info["format"] = "guardrails/judge: no per-cell GPU record"
            gr = collections.OrderedDict()
            for ln, r in repo.jsonl(f"{base}/rows_public.jsonl"):
                if not r.get("warmup"):
                    gr.setdefault(("L2_" if run == "p55_judge_thinking" else "") + f"{r['arm']}_{r['request_arm']}", 0)
                    gr[("L2_" if run == "p55_judge_thinking" else "") + f"{r['arm']}_{r['request_arm']}"] += 1
            if repo.has(f"{base}/l1_calls.jsonl"):
                for ln, r in repo.jsonl(f"{base}/l1_calls.jsonl"):
                    gr.setdefault(f"L1_{r['cond']}", 0)
                    gr[f"L1_{r['cond']}"] += 1
            for cid, n in gr.items():
                rows.append({"cell": cid, "kind": f"measured ({n} rows, interleaved with other cells in one container)",
                             "end": None, "source": "none", "end_at": None,
                             "notes": ["request arms rotate per question inside one container: no per-cell GPU record exists"],
                             "feeds": judge_feeds(F, run, cid) + ledger(F, run)})
        else:
            info["format"] = "no GPU run (query / analysis of existing records)"
            info["note"] = "no measured cells: " + ", ".join(p.split("/", 3)[3] for p in repo.files if p.startswith(base + "/") and "/raw/" not in p)
        # run-level records (never a cell end)
        if repo.has(f"{base}/events.jsonl"):
            for ln, e in repo.jsonl(f"{base}/events.jsonl"):
                st = e.get("gpu_after_stop")
                if st:
                    tag = " ".join(str(e[k]) for k in ("arm", "profile", "container", "block", "condition", "max_model_len") if k in e)
                    info["run_level_records"].append(f"events.jsonl:{ln} {e.get('kind')} {tag}: gpu_after_stop util {st.get('util_pct')}% · {st.get('power_w')} W · {st.get('used_mib')} MiB (after container removal)")
        ce = ctx_end(repo, run)
        if ce:
            info["run_level_records"].append("ctx.txt last line: " + ce)
        for c in rows:
            cls, why = classify(c["end"])
            if c["end"] is None and c["notes"]:
                why = [why[0] + ": " + c["notes"][0]]
            c.update({"run": run, "util_pct": (c["end"] or {}).get("util_pct"), "power_w": (c["end"] or {}).get("power_w"),
                      "used_mib": (c["end"] or {}).get("used_mib"), "classification": cls, "reasons": why})
            del c["end"]
        info["cells"] = len(rows)
        info["with_end_record"] = sum(1 for c in rows if c["classification"] != "undeterminable")
        runinfo[run] = info
        cells += rows
    return runs, cells, runinfo


def judge_feeds(F, run, cid):
    B = "BASELINE"
    if run == "p53_guardrails":
        arm, ra = cid.split("_")
        m = {("A1", "G"): ("**60/60 · 30/30 · 45/45** — the judge answers with 214 tokens of reasoning (2.9 s)", "A1 G: 60/60·30/30·45/45, 214 tokens (2.9 s)"),
             ("A2", "G"): ("79 tokens (415 ms)", "A2 G: 60/60·30/30·45/45, 79 tokens (415 ms)"),
             ("A1", "H"): ("**0/60 · 0/30 · 45/45** — one-word verdicts (3 and 5 tokens)", "A1 H: 0/60·0/30·45/45; rail cost ~250 ms; overhead −0.2%"),
             ("A2", "H"): ("the message has no effect on this model's judge (78 tokens)", "A2 H: 60/60·30/30·45/45, 78 tokens"),
             ("A1", "N"): ("H: **−0.2%** avg; paired −0.25% [−0.49%, −0.02%]", "A1 N is the baseline of the −0.2% overhead"),
             ("A2", "N"): ("not measurable: no rail row answered", "A2 N: overhead not measurable")}
        q = m[(arm, ra)]
        out = [F.f(B, "§E table", q[0], q[1])]
        if (arm, ra) == ("A1", "H"):
            out.append(F.f(B, "§E table", "H: input check 113 ms / 3 tokens · output check 135 ms / 5 tokens ≈ 250 ms", "A1 H rail cost ≈ 250 ms"))
            out.append(F.f(B, "§E table", "H: **−0.2%** avg; paired −0.25% [−0.49%, −0.02%]", "A1 H overhead −0.2%"))
        if (arm, ra) in (("A2", "G"), ("A2", "H")):
            out.append(F.f(B, "§E table", "input check 415–426 ms / 78–79 tokens", "A2 judge 415–426 ms"))
        return out
    m = {"L1_IN_F": ("one word in 2 tokens, ~106 ms", "L1 input check with switch: 2 tokens, ~106 ms; yes on 0·0·45"),
         "L1_OUT_F": ("one word in 2 tokens, ~106 ms", "L1 output check with switch: 2 tokens, ~106 ms"),
         "L1_IN_T": ("(without it: 67–79 tokens of reasoning, never yes/no)", "L1 input check without switch: 67 tokens p50"),
         "L1_OUT_T": ("(without it: 67–79 tokens of reasoning, never yes/no)", "L1 output check without switch: 79 tokens p50"),
         "L2_A2_J": ("**+16.8%** [+16.2%, +17.4%] (1,698 → 1,983 ms", "L2 J: +16.8% overhead (1,983 ms), 0/60·0/30·45/45, input 113 / output 87 ms"),
         "L2_A2_N": ("**+16.8%** [+16.2%, +17.4%] (1,698 → 1,983 ms", "L2 N: baseline 1,698 ms of the +16.8%")}
    if cid not in m:
        return ["none found (L1 answer-generation calls for the output check; not quoted)"]
    out = [F.f(B, "§E judge table", *m[cid])]
    if cid == "L1_IN_F":
        out.append(F.f(B, "§E judge table", "input check yes on 0 · 0 · 45 of 60 · 30 · 45", "yes on 0·0·45"))
    if cid == "L2_A2_J":
        out.append(F.f(B, "§E judge table", "blocked 0/60 · 0/30 · **45/45**", "blocked 0/60·0/30·45/45"))
        out.append(F.f(B, "§E judge table", "input check 113 ms, output check 87 ms, 2 tokens each", "judge 113 / 87 ms"))
    return out


# ------------------------------------------------------------------ output
def is_measured_feed(s):
    return not s.startswith("none") and "[ledger count]" not in s and "[qualitative]" not in s


def write_md(path, runs, cells, runinfo, pc):
    L = ["# Z3 audit · GPU state at the end of each cell (Vol.2 runs p50_* / p53_* / p55_*)", "",
         f"Fingerprint (clean window): util == 0 % and {LO:g} <= power <= {HI:g} W, applied to the end-of-cell record. "
         "Missing record = undeterminable, never clean. Generated by `z3_audit.py` from the committed tree (read-only).", "",
         "## Positive control", "", "| case | expected | got |", "|---|---|---|"]
    L += [f"| {c['case']} | {c['expected']} | {c['got']} |" for c in pc]
    L += ["", "## Per-run summary", "",
          "| run | end-of-cell record used | cells | with end record | clean | dirty | undeterminable | warm-up levels/rows (not cells) | skipped records |",
          "|---|---|---|---|---|---|---|---|---|"]
    tot = collections.Counter()
    for run in runs:
        i = runinfo[run]; cs = [c for c in cells if c["run"] == run]
        k = collections.Counter(c["classification"] for c in cs if not c["kind"].startswith("warmup"))
        kw = collections.Counter(c["classification"] for c in cs if c["kind"].startswith("warmup"))
        nm = sum(1 for c in cs if not c["kind"].startswith("warmup"))
        tot.update({"cells": nm, "clean": k["clean"], "dirty": k["dirty"], "und": k["undeterminable"]})
        wu = i["warmup_levels"] + len([c for c in cs if c["kind"].startswith("warmup")])
        wtxt = f"{wu}" + (f" (levels: {kw['clean']} clean / {kw['dirty']} dirty)" if kw else "")
        L.append(f"| {run} | {i['format']} | {nm} | {sum(1 for c in cs if not c['kind'].startswith('warmup') and c['classification'] != 'undeterminable')} | "
                 f"{k['clean']} | {k['dirty']} | {k['undeterminable']} | {wtxt} | {i['skipped_records']} |")
    L.append(f"| **total** | | **{tot['cells']}** | | **{tot['clean']}** | **{tot['dirty']}** | **{tot['und']}** | | |")
    L += ["", "Counts are measured cells; warm-up levels are listed in the cell table but not counted.", "",
          "Dirty measured cells by reason: " + ", ".join(f"{k}: {v}" for k, v in sorted(collections.Counter(
              ("util>0" if any(r.startswith("util") for r in c["reasons"]) else "util=0") + " & " +
              ("power>42" if any("> 42" in r for r in c["reasons"]) else "power<26" if any("< 26" in r for r in c["reasons"]) else "power in band")
              for c in cells if c["classification"] == "dirty" and not c["kind"].startswith("warmup")).items())), "",
          "## Dirty cells that feed a draft number", "",
          "| run | cell | util % | power W | why dirty | feeds |", "|---|---|---|---|---|---|"]
    for c in cells:
        if c["classification"] == "dirty" and not c["kind"].startswith("warmup") and any(is_measured_feed(f) for f in c["feeds"]):
            fs = "<br>".join(f for f in c["feeds"] if is_measured_feed(f))
            L.append(f"| {c['run']} | {c['cell']} | {c['util_pct']} | {c['power_w']} | {'; '.join(c['reasons'])} | {fs} |")
    L += ["", "## Undeterminable cells that feed a draft number", "", "| run | cell | why | feeds |", "|---|---|---|---|"]
    for c in cells:
        if c["classification"] == "undeterminable" and any(is_measured_feed(f) for f in c["feeds"]):
            L.append(f"| {c['run']} | {c['cell']} | {'; '.join(c['reasons'])} | {'<br>'.join(f for f in c['feeds'] if is_measured_feed(f))} |")
    L += ["", "## Runs without per-cell end records", ""]
    for run in runs:
        i = runinfo[run]; cs = [c for c in cells if c["run"] == run]
        if not cs or all(c["classification"] == "undeterminable" for c in cs):
            L.append(f"- **{run}** — {i['format']}. {i['note']}")
            for r in i["run_level_records"]:
                L.append(f"  - run-level: {r}")
    L += ["", "## All cells", "", "| run | cell | kind | end-record source | end at | util % | power W | class | reasons | notes | feeds |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in cells:
        L.append(f"| {c['run']} | {c['cell']} | {c['kind']} | `{c['source'].replace(RES + '/', '')}` | {c['end_at'] or ''} | {'' if c['util_pct'] is None else c['util_pct']} | "
                 f"{'' if c['power_w'] is None else c['power_w']} | {c['classification']} | {'; '.join(c['reasons'])} | {'; '.join(c['notes'])} | {'<br>'.join(c['feeds'])} |")
    L += ["", "## Run-level records (not cell ends)", ""]
    for run in runs:
        rl = runinfo[run]["run_level_records"]
        if rl:
            L.append(f"- **{run}**")
            L += [f"  - {r}" for r in rl]
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()
    pc = positive_control()
    repo = Repo(a.repo)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=a.repo, capture_output=True, text=True).stdout.strip()
    F = Feeds(repo)
    runs, cells, runinfo = audit(repo, F)
    print(f"== repo HEAD {head}; {len(runs)} runs; {F.checked} draft quotes verified present")
    for run in runs:
        i = runinfo[run]; cs = [c for c in cells if c["run"] == run]
        m = [c for c in cs if not c["kind"].startswith("warmup")]
        k = collections.Counter(c["classification"] for c in m)
        print(f"   {run:26s} cells {len(m):3d} · with end record {sum(1 for c in m if c['classification'] != 'undeterminable'):3d} · "
              f"clean {k['clean']:3d} dirty {k['dirty']:3d} undeterminable {k['undeterminable']:3d} · "
              f"warm-up {i['warmup_levels'] + len(cs) - len(m)} · skipped {i['skipped_records']} · {i['format']}")
    out = {"head": head, "fingerprint": {"util_pct": 0, "power_w": [LO, HI]}, "positive_control": pc,
           "runs": runinfo, "cells": [{k: c[k] for k in ("run", "cell", "kind", "source", "end_at", "util_pct", "power_w",
                                                        "used_mib", "classification", "reasons", "notes", "feeds")} for c in cells]}
    json.dump(out, open(os.path.join(a.out, "z3_audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_md(os.path.join(a.out, "z3_audit.md"), runs, cells, runinfo, pc)
    print("wrote z3_audit.json, z3_audit.md")


if __name__ == "__main__":
    main()
