#!/usr/bin/env python3
"""Vol.4 · writes the supplementary pre-registration of the second night of the concurrency sweep (2026-10-13), with its
.sha256 file. It supplements results/concurrency_sweep/prediction_concurrency_sweep.json, which stays as it is: one
rule is added (the calibration read by the duration of a request), the arm that the first night's rule stopped is run,
the other five arms are run again at one request in flight and at the first night's saturation level, and one cell of
two serving engines for one content-safety model is added. Run once, before the first serving container of the night;
never changed afterwards.
usage: gen_prediction_second_night.py [--draft] [--judge-runner FILE]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE); REPO = os.path.dirname(VOL)
sys.path.insert(0, HERE)
import sweep_two_nights as W  # noqa: E402

N1 = os.path.join(VOL, "results", "concurrency_sweep"); RES = os.path.join(VOL, "results", "concurrency_sweep_second_night")
OUT = os.path.join(RES, "prediction_second_night.json")
DRAFT = "--draft" in sys.argv
RUNNER = sys.argv[sys.argv.index("--judge-runner") + 1] if "--judge-runner" in sys.argv else None
ORDER = ("n3", "rr1b", "e1b", "evl", "rr500")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def local_digest(image):
    """The digest the local image carries, read from Docker (not typed)."""
    out = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:") or len(out) != 71:
        sys.exit(f"refused: no local image {image}")
    return out


def driver_now():
    out = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    return out or None


first = json.load(open(os.path.join(N1, "prediction_concurrency_sweep.json"), encoding="utf-8"))
T1 = json.load(open(os.path.join(N1, "table.json"), encoding="utf-8"))
ARMS1 = first["N1_concurrency_sweep"]["arms"]
for a, A in ARMS1.items():                       # the images of the first night must still be the local ones
    if local_digest(A["image"]) != A["image_digest"].split("@")[-1]:      # written there as repository@sha256:...
        sys.exit(f"refused: the local image of arm {a} is not the one of the first night")
N2 = first["N2_content_safety_model_on_a_newer_engine"]

cal1 = {a: W.calibration(os.path.join(N1, a))[0] for a in ARMS1}
spread = max(abs(s["requests_per_s"] / A["shapes"][sh]["first_container"][c]["requests_per_s"] - 1) * 100
             for a, A in T1["arms"].items() if a in ARMS1 for sh in A["shapes"] for c, s in A["shapes"][sh]["second_container"].items())
repeats = {}
for a in ORDER:
    lv = {}
    for sh, S in T1["arms"][a]["shapes"].items():
        sat = S["reading_first_container"]["saturation_level"]
        lv[sh] = [1] if sat == 1 else [1, sat]
    repeats[a] = {"image": ARMS1[a]["image"], "image_digest": ARMS1[a]["image_digest"], "start": ARMS1[a]["start"], "levels": lv,
                  "first_night": {sh: {str(c): {k: T1["arms"][a]["shapes"][sh]["first_container"][str(c)][k] for k in ("requests_per_s", "items_per_s")} | {"p50_ms": T1["arms"][a]["shapes"][sh]["first_container"][str(c)]["request_ms"]["p50"],
                                                "level_held": T1["arms"][a]["shapes"][sh]["first_container"][str(c)]["level_held"]} for c in lv[sh]} for sh in lv}}


def own_client_sessions():
    """This volume's own client at one request in flight (64 passages per request) in earlier sessions, with the driver
    each session's run log recorded: the only figures of this volume that cross a driver change."""
    out = {}
    for arm, tag, cell in (("n3", "n3embed", "nim_nemotron-3-embed-1b_auto"), ("e1b", "embed1bv2", "nim_llama-nemotron-embed-1b-v2_auto"), ("evl", "embedvl", "nim_llama-nemotron-embed-vl-1b-v2_auto"),
                           ("e300", "embed300m", "nim_llama-nemotron-embed-300m-v2_auto")):
        rows = []
        for folder, rel in (("first_batch", f"{cell}/miracl-hn-zh/throughput.json"), ("whole_corpus_quality", f"timing_container_and_host/{tag}/container_1.json"),
                            ("whole_corpus_quality", f"timing_container_and_host/{tag}/container_2.json"), ("concurrency_sweep", f"{arm}/calibration_own_client.json")):
            f = os.path.join(VOL, "results", folder, rel); r = json.load(open(f, encoding="utf-8")); log = W.drivers(os.path.join(VOL, "results", folder))
            at = W.when(r["at"]); q = r.get("per_request_seconds") or {}
            rows.append({"file": f"../{folder}/{rel}", "date": at.astimezone(log[0][0].tzinfo).strftime("%Y-%m-%d"), "driver": W.driver_at(log, at), "passages_per_s_median": r["passages_per_s_median"],
                         "request_p50_ms": round(q["p50"] * 1000, 1) if q else None})
        rates = [x["passages_per_s_median"] for x in rows]
        out[arm] = {"sessions": rows, "largest_difference_between_two_sessions_percent": round((max(rates) / min(rates) - 1) * 100, 2)}
    return out


SESSIONS = own_client_sessions()
OLD, NEW = "vllm/vllm-openai:v0.20.2", N2["engine"]["image"]
containers = [{"arm": "J4-night-0202-a", "step": "n35_0202_a", "engine": "0.20.2", "image": OLD, "digest": local_digest(OLD), "start_setting": {}},
              {"arm": "J4-night-0300", "step": "n35_0300", "engine": "0.30.0", "image": NEW, "digest": local_digest(NEW), "start_setting": dict(N2["engine"]["start_setting"])},
              {"arm": "J4-night-0202-b", "step": "n35_0202_b", "engine": "0.20.2", "image": OLD, "digest": local_digest(OLD), "start_setting": {}}]
if containers[1]["digest"] != N2["engine"]["digest"]:
    sys.exit("refused: the local 0.30.0 image is not the one of the first night")

pred = {
 "what": "Vol.4, second night of the concurrency sweep (2026-10-13): the calibration read by the duration of a request; the arm the first night's rule stopped; five arms again at one request in flight and at their saturation level; one content-safety model on two serving engines in one night",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"file": "../concurrency_sweep/prediction_concurrency_sweep.json", "sha256": sha(os.path.join(N1, "prediction_concurrency_sweep.json")),
                 "unchanged": "that file and every result of the first night stay as they are; its tool, request bodies, shapes, levels, duration per level, gates and what is reported are kept"},
 "host": "one RTX 5090 (32 GB), Windows 11, Docker Desktop on WSL2; the driver version is recorded by every gate",
 "driver": {"now": driver_now(), "first_night": T1.get("drivers") or sorted({d for _, d in W.drivers(N1)}),
            "what_follows": "if tonight's gates record the driver of the first night, the two nights are a repeat on one driver and say nothing about a driver change. What this volume has across drivers is its own client at one request in flight: "
                            "its rate and the duration of one request of 64 passages in the earlier sessions (below), beside tonight's; the table names the driver of every row.",
            "own_client_in_earlier_sessions": SESSIONS},
 "order": ["A: llama-nemotron-embed-300m-v2, the whole arm", "B: n3, rr1b, e1b, evl, rr500, one new container each", "C: the content-safety model on two engines, only if its first container can start before 06:30"],
 "time_limit": "nothing is started that cannot end before 08:00 local time: the whole arm is not started with less than 40 minutes left, a repeat not with less than 15. What is not run tonight is reported as not run.",
 "kept": "one container on the card at a time; the gate before every container and, in its timed form, before every timed step; no game launcher while a timed step runs; a timed step is one blocking command; results are written as they come; a command that does not end within its limit has its container stopped by name",

 "calibration_rule_added": {
  "rule": "AIPerf at one request in flight against this volume's own client, by the p50 of the duration of one request (64 passages per request for an embedding NIM, 100 passages per call for a reranking NIM): more than 20% apart, the difference rounded to two decimals, stops the arm before its sweep. scripts/sweep_two_nights.py computes it.",
  "why": "the first night's rule compared items per second. The own client's rate is items divided by the wall time of a pass, and that wall time also holds what the client does between two requests (it reads every returned number before it sends the next request); the duration of a request does not. "
         "On the first night the two instruments agreed on the duration of a request within 3% on all six arms, while their rates were up to 36% apart, most on the NIM whose requests are shortest. A rule on rates therefore measures the client's own time, not an error of the load tool.",
  "the_first_rule": "is not withdrawn: it is computed for every arm on both nights and reported beside the new one, with 'outside' where it is outside. It no longer stops an arm.",
  "first_night_by_both_rules": {a: {"by_duration": {k: r["by_duration"][k] for k in ("own_client_p50_ms", "aiperf_c1_p50_ms", "difference_percent", "within")},
                                    "by_rate": {k: r["by_rate"][k] for k in ("own_client_items_per_s", "aiperf_c1_items_per_s", "difference_percent", "within")}} for a, r in cal1.items()},
  "not_recomputed": "the first night's calibration.json files and its table stay as they were written"},

 "cell_A_the_arm_stopped_on_the_first_night": {
  "arm": "e300", "image": ARMS1["e300"]["image"], "image_digest": ARMS1["e300"]["image_digest"], "start": ARMS1["e300"]["start"],
  "what": "the whole arm as the first pre-registration describes an arm: a new container; the own client (64 per request, three passes); AIPerf at one in flight on the passage shape; the calibration by the new rule; both shapes at 1, 2, 4, 8, 16, 32, 64 in flight and one more level while the rate rises by more than 5% (256 at most); "
          "the container removed; a second new container and the two highest levels of each shape again",
  "bodies": "the first night's files, replayed as they are (their SHA-256 is in e300/payloads.json and in every level record)",
  "expectation": {"calibration": "within 5% by duration (first night: " + f"{cal1['e300']['by_duration']['difference_percent']:+.2f}%" + "); outside 20% by rate again",
                  "passage_shape": "the rate stops rising at 1 or 2 in flight; at one in flight between 1,000 and 1,250 passages per second (first night, one level: " + f"{cal1['e300']['by_rate']['aiperf_c1_items_per_s']}" + ")",
                  "query_shape": "the rate stops rising at 2 or 4 in flight; the levels 1 and 2 may be below 90% held, as on the two fastest arms of the first night (requests of a few milliseconds)",
                  "errors": "none", "confidence": "moderate: five arms of the same kind behaved so on the first night"}},

 "cell_B_second_night_repeats": {
  "what": "per arm one new container: the own client, then per shape one request in flight and the first night's saturation level (where that level is 1, only 1), 40 seconds each, the same request bodies; no second container",
  "arms": repeats,
  "reported": "both nights side by side per level: date, driver, requests and items per second, p50 and p99, the difference in percent; and the calibration of both nights by both rules (scripts/sweep_two_nights.py table). Nothing is pooled and no night is preferred.",
  "expectation": {"saturation_level": f"requests per second within 5% of the first night on every arm and shape (on the first night two containers of one arm were at most {spread:.2f}% apart at their two highest levels)",
                  "one_in_flight": "within 5% where the first night held the level; no guess where it did not (the query shape of n3 and evl at 1 and 2 in flight: those rates also hold the load tool's own time between requests)",
                  "confidence": "moderate at most: across the earlier sessions this volume's own client at one request in flight moved by up to " + f"{max(v['largest_difference_between_two_sessions_percent'] for v in SESSIONS.values()):.1f}% on one arm; a miss of the 5% by a few points would be of that kind",
                  "if_not": "a difference above 5% is reported as a difference between two nights. No cause is assigned from two nights, and neither night's figure is called the right one."},
  "not_claimed": "a ceiling. A saturation rate seen on two nights is the rate of two nights on this host and driver."},

 "cell_C_one_model_two_engines_one_night": {
  "why": "the first night found Nemotron 3.5 Content Safety on upstream vLLM 0.30.0 at between a sixth and a fifth fewer verdicts per second than the study's 0.20.2 figures of 2026-10-02. Those two were ten days and a driver change apart, so the engine cannot be told from the day. Both engines in one night can.",
  "does_not_decide": "which image is kept: 0.20.2 is the newest version the model card names and stays. This cell is not part of the published Vol.3 study and changes none of its figures.",
  "containers": containers, "order": "0.20.2, 0.30.0, 0.20.2 again: each new and alone on the card; the two 0.20.2 containers show how far apart two containers of one engine are tonight",
  "cells": "per container and track the study's unchanged p93_judge.py --arm J4 (reasoning off): precheck, then the whole track at 16 in flight (every prompt of the study's prompt track; every response of its response track)",
  "measure": "verdicts per second = items / wall seconds of the cell at 16 in flight, per track",
  "reading": "per track: 0.30.0 against the mean of the two 0.20.2 containers. 'Slower on the same night' if it is more than 5% below that mean, below both of them, and further from the mean than twice the difference between the two 0.20.2 containers; "
             "'faster' by the mirror of that; otherwise 'no difference that stands out from two containers of one engine'. Verdicts that differ from the study's main run are counted per container and reported; they do not enter the reading.",
  "expectation": "no guess between the two readings 'slower' and 'no difference': the first night's gap could be the engine or the day. The two 0.20.2 containers within 3% of each other.",
  "started_only_if": "its first container can start before 06:30; once started, all three containers are run",
  "results": "kept outside the repository, as the first night's cell of this model",
  "runner_outside_the_repository_sha256": sha(RUNNER) if RUNNER else None},

 "harness_sha256": {f: sha(os.path.join(VOL, f)) for f in ("scripts/sweep_level.py", "scripts/sweep_step.py", "scripts/run_step.py", "scripts/sweep_table.py", "scripts/sweep_two_nights.py", "scripts/embed_cell.py", "scripts/rerank_latency.py",
                                                            "scripts/nim_retrieval_clients.py", "client/Dockerfile", "client_aiperf/Dockerfile")} | {"tools/g8_gate.py": sha(os.path.join(REPO, "tools", "g8_gate.py"))},
 "generator": "scripts/gen_prediction_second_night.py (this file's writer; its SHA-256 is in the events file of the night)",
 "programs_that_may_still_change": "none of the measuring programs. scripts/sweep_two_nights.py makes the calibration records and the two-night table; its SHA-256 at the freeze is above, and each record it writes carries the SHA-256 of the version that wrote it.",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
os.makedirs(RES, exist_ok=True)
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
