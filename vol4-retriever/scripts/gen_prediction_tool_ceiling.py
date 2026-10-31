#!/usr/bin/env python3
"""Vol.4 · writes the pre-registration of the tool-ceiling cell, with its .sha256 file: the load tool of the concurrency
sweep against a server that answers at once. Run once, before the first registered run; never changed afterwards.

The answer sizes are read from the load tool's own per-request export of the sweep (kept outside the repository, below
$VOL4_HOLD): the median bytes received per request at one request in flight, per NIM and request shape. The largest of
a shape is the size the server is given, so that the tool is tried on the largest answers it met.
usage: gen_prediction_tool_ceiling.py [--draft] [--earlier-run DIR]
"""
import hashlib, json, os, statistics, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE); REPO = os.path.dirname(VOL)
sys.path.insert(0, HERE)
import instant_answer_server as I  # noqa: E402
import tool_ceiling_table as C  # noqa: E402

RES = os.path.join(VOL, "results", "tool_ceiling"); OUT = os.path.join(RES, "prediction_tool_ceiling.json")
NIGHTS = [os.path.join(VOL, "results", "concurrency_sweep"), os.path.join(VOL, "results", "concurrency_sweep_second_night")]
HOLD = os.environ["VOL4_HOLD"]
EXPORTS = [("concurrency_sweep", os.path.join(HOLD, "vol4_concurrency", "artifacts"), ("n3", "e1b", "evl", "rr1b", "rr500")),
           ("concurrency_sweep_second_night", os.path.join(HOLD, "vol4_concurrency_second_night", "artifacts"), ("e300",))]
DRAFT = "--draft" in sys.argv
EARLIER = sys.argv[sys.argv.index("--earlier-run") + 1] if "--earlier-run" in sys.argv else None
LEVELS = [1, 2, 4, 8, 16, 32, 64]
BODIES = {"query": ("e300", "emb_query.inputs.json"), "passage": ("e300", "emb_passage.inputs.json"), "passages_100": ("rr500", "rank_100.inputs.json"), "passages_10": ("rr500", "rank_10.inputs.json")}


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def image_id(image):
    out = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:"):
        sys.exit(f"refused: no local image {image}")
    return out


def received():
    """Median bytes received per request at one in flight, per NIM and shape, from the tool's per-request export."""
    out = {s: {} for s in C.SHAPES}
    for night, root, arms in EXPORTS:
        for arm in arms:
            for shape in C.SHAPES:
                f = os.path.join(root, arm, shape, "first_c1", "profile_export.jsonl")
                if os.path.isfile(f):
                    kb = [json.loads(l)["metrics"]["http_req_data_received"]["value"] for l in open(f, encoding="utf-8")]
                    out[shape][arm] = {"night": night, "requests": len(kb), "median_bytes": round(statistics.median(kb) * 1024), "smallest_bytes": round(min(kb) * 1024), "largest_bytes": round(max(kb) * 1024)}
    return out


def records(folder, pattern):
    out = {}
    for shape in C.SHAPES:
        for c, r in C.level_files(os.path.join(folder, shape), pattern).items():
            out.setdefault(shape, {})[str(c)] = {k: r.get(k) for k in ("requests", "errors", "requests_per_s", "request_ms", "client_cpu", "duration_asked_s")}
    return out


seen = received()
targets = {s: max(v["median_bytes"] for v in seen[s].values()) for s in C.SHAPES}
bodies = I.table(targets)[1]
fastest = {s: {str(c): {k: v[k] for k in ("requests_per_s", "arm", "night")} for c, v in sorted(C.nim_best(NIGHTS, s).items()) if c in LEVELS} for s in C.SHAPES}
earlier = None
if EARLIER:
    earlier = {str(json.load(open(os.path.join(EARLIER, f), encoding="utf-8"))["concurrency"]): {k: json.load(open(os.path.join(EARLIER, f), encoding="utf-8")).get(k) for k in ("requests_per_s", "request_ms", "duration_asked_s")}
               for f in sorted(os.listdir(EARLIER)) if f.startswith("query_c") and f.endswith(".json")}

pred = {
 "what": "Vol.4, the tool-ceiling cell: the load tool of the concurrency sweep (AIPerf 0.11.0 in its container, the sweep's request bodies) against a server that answers at once, to see what the tool itself reaches",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "why": "in the sweep, three different NIMs stopped at nearly the same rate for one query per request (384 to 419 requests per second). A check of the sweep (rate times mean duration against the level) shows that the tool sent on time, "
        "but it cannot show a tool that is slow to read an answer. Whether the tool could have gone faster is a question about the tool, and can be asked without a model.",
 "host": "the host of the sweep (Windows 11, Docker Desktop on WSL2). No model is loaded and the card is not used; another lane may use the card or the CPU while this runs, and what else runs on the host is noted with each server start",
 "server": {"program": "scripts/instant_answer_server.py", "image": "vol4-client:py312", "image_id": image_id("vol4-client:py312"),
            "what": "one asyncio process; every POST is read to its end and answered at once with one prepared body; on the tool's Docker network, as a NIM was",
            "answer_bytes": targets, "bodies_it_makes_for_those": bodies,
            "answer_sizes_seen_in_the_sweep": {"what": "bytes received per request at one request in flight in the first container, from the tool's per-request export (http_req_data_received; that export is kept outside the repository)", "per_shape_and_nim": seen,
                                               "rule": "per shape the largest median: the tool is tried on the largest answers it met"},
            "containers": "per run two new containers, one after the other: the first holds the query answer and the 100-passage ranking answer, the second the 64-passage answer and the 10-passage ranking answer (one server answers one shape per NIM path)"},
 "tool": {"image": "vol4-aiperf:0.11.0", "image_id": image_id("vol4-aiperf:0.11.0"), "program": "scripts/sweep_level.py, as in the sweep: closed loop, a fixed number of requests in flight",
          "request_bodies": {s: {"file": f"{a}/{f}", "sha256": json.load(open(os.path.join(NIGHTS[0], a, "payloads.json"), encoding="utf-8"))["files"][s]["sha256"], "record": f"../concurrency_sweep/{a}/payloads.json"} for s, (a, f) in BODIES.items()},
          "levels": LEVELS, "per_level": "20 seconds at the level after a warm-up of twice the level in requests (the sweep used 40 seconds; the tool's settings are otherwise the same)"},
 "runs": "two, called first and second; each is every shape at every level, with its own new server containers. Both are reported; the lower rate of the two is the one used.",
 "not_run_together_with": "any timed cell of this repository",
 "reading": {"program": "scripts/tool_ceiling_table.py",
             "room": "per shape and level: the tool's lower rate of the two runs, divided by the highest requests per second any NIM of that shape reached at that level in a first container on either night of the sweep",
             "rule": "room of 2 or more: the tool was not what held that level's rate. Below 2: the level is marked, and every NIM rate at that level is to be read as 'at least'. A tool level with errors in either run is not read.",
             "fastest_nim_per_level_as_of_now": fastest},
 "seen_before_this_file_was_frozen": {
   "an_unregistered_run_of_2026-10-13": {"what": "an earlier server of the same idea with a 45,019-byte answer, the query bodies of another arm, 15 seconds per level; kept outside the repository", "requests_per_s_by_level": earlier},
   "probes": {"what": "the driver of this cell was tried once: per shape 8 seconds at 1 and at 8 in flight against this server. A first try stopped at once because sweep_level.py takes only the NIM's two paths; the server was changed to answer on them. The probe records are named probe_*.json and are not results.",
              "records": records(RES, "probe")}},
 "expectation": {"query": "room of at least 2 at every level and of at least 8 from 8 in flight on", "passage": "room of at least 5 at every level", "ranking": "room of at least 20 at every level, both shapes",
                 "two_runs": "within 15% of each other at every level", "errors": "none",
                 "confidence": "high for 'room of at least 2': the probes and the earlier run already showed rates several times the NIMs'. That makes this a confirmation with a fixed rule, not a blind prediction."},
 "what_this_cannot_show": ["how fast a NIM is", "the tool beside a real NIM that also uses the host's CPU (the instant server uses almost none)", "a ceiling of the tool that is higher than this server's own: the figure is 'the tool reaches at least this'",
                           "answers larger than the ones the sweep met, or other request bodies"],
 "harness_sha256": {f: sha(os.path.join(VOL, f)) for f in ("scripts/instant_answer_server.py", "scripts/tool_ceiling_table.py", "scripts/sweep_level.py", "scripts/sweep_step.py", "scripts/run_step.py", "client/Dockerfile", "client_aiperf/Dockerfile")},
 "generator": "scripts/gen_prediction_tool_ceiling.py (this file's writer; its SHA-256 is in the events file of the cell)",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
os.makedirs(RES, exist_ok=True)
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
