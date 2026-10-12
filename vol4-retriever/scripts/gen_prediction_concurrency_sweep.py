#!/usr/bin/env python3
"""Vol.4 · writes the pre-registration of the session of 2026-10-12, with its .sha256 file: the concurrency sweep of the
retrieval NIMs (N1), one content-safety model on a newer serving engine (N2), and the Blueprint's default embedding image
beside the newer image of the same model (N4). A supplement to the earlier pre-registrations of this volume: their
rules, data, metrics and method stay as they are. Run once, before the first serving container; never changed afterwards.
usage: gen_prediction_concurrency_sweep.py [--draft] [--n2-runner FILE]
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE); REPO = os.path.dirname(VOL)
RES = os.path.join(VOL, "results", "concurrency_sweep")
OUT = os.path.join(RES, "prediction_concurrency_sweep.json")
DRAFT = "--draft" in sys.argv
N2_RUNNER = sys.argv[sys.argv.index("--n2-runner") + 1] if "--n2-runner" in sys.argv else None


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def local_digest(image):
    """The digest the local image carries, read from Docker (not typed)."""
    out = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    if not out.startswith("sha256:") or len(out) != 71:
        sys.exit(f"refused: no local image {image}")
    return out


def load(*parts):
    return json.load(open(os.path.join(VOL, *parts), encoding="utf-8"))


fp = load("results", "first_batch", "prediction_first_batch.json")
V3 = os.path.join(REPO, "vol3-guardrails")
J4 = json.load(open(os.path.join(V3, "results", "p93_judges", "J4", "summary.json"), encoding="utf-8"))


def timing(tag):
    f = os.path.join("results", "whole_corpus_quality", "timing_container_and_host", tag, "container_1.json")
    return {"file": "../whole_corpus_quality/timing_container_and_host/" + tag + "/container_1.json", "passages_per_s_median": load(f)["passages_per_s_median"]}


def payloads(arm):
    p = load("results", "concurrency_sweep", arm, "payloads.json")
    return {"record": f"{arm}/payloads.json", "sha256_of_the_record": sha(os.path.join(RES, arm, "payloads.json")), "files": {k: {x: v[x] for x in ("requests", "items_per_request", "sha256")} for k, v in p["files"].items()}}


def probe(arm):
    out = {}
    d = os.path.join(RES, arm)
    for shape in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        for c in (1, 8):
            f = os.path.join(d, shape, f"probe_c{c}.json")
            if os.path.isfile(f):
                r = json.load(open(f, encoding="utf-8"))
                out[f"{shape}, {c} in flight"] = {k: r.get(k) for k in ("requests", "errors", "requests_per_s", "items_per_s", "request_ms", "client_cpu", "aiperf_rc")}
    return out or "not run"


E = fp["P2_other_embedding_nims"]["images"]; RR = fp["P3_reranking"]["images"]
ARMS = {
 "n3": {"image": "nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2", "image_digest": fp["P1_nim_same_task"]["image_digest"], "start": "NIM_ENGINE_PRECISION=fp16, weights from the NIM's own download", "kind": "embedding",
        "single_stream_before": timing("n3embed")},
 "rr1b": {**RR["llama-nemotron-rerank-1b-v2"], "start": "no profile set", "kind": "reranking",
          "single_stream_before": {"file": "../whole_corpus_quality/rerank_llama-nemotron-rerank-1b-v2/", "what": "one call of 100 passages after the other, zh: p50 about 153 ms"}},
 "e1b": {**E["llama-nemotron-embed-1b-v2"], "start": "no profile set (fp8, selected by the image)", "kind": "embedding", "single_stream_before": timing("embed1bv2")},
 "evl": {**E["llama-nemotron-embed-vl-1b-v2"], "start": "no profile set, weights from the NIM's own download", "kind": "embedding", "single_stream_before": timing("embedvl")},
 "rr500": {**RR["llama-nemotron-rerank-500m-v2"], "start": "no profile set", "kind": "reranking", "single_stream_before": {"file": "../whole_corpus_quality/rerank_llama-nemotron-rerank-500m-v2/"}},
 "e300": {**E["llama-nemotron-embed-300m-v2"], "start": "no profile set", "kind": "embedding", "single_stream_before": timing("embed300m")},
}
NEW = ["scripts/sweep_payloads.py", "scripts/sweep_level.py", "scripts/sweep_step.py", "scripts/gen_prediction_concurrency_sweep.py", "client_aiperf/Dockerfile"]
USED = ["scripts/run_step.py", "scripts/embed_cell.py", "scripts/rerank_latency.py", "scripts/rerank_cell.py", "scripts/nim_retrieval_clients.py", "scripts/retrieval_datasets.py", "client/Dockerfile"]
stab = {t: J4["tracks"][t]["stability"] for t in ("input", "output")}

pred = {
 "what": "Vol.4, session of 2026-10-12: the concurrency sweep of the retrieval NIMs (N1); Nemotron 3.5 Content Safety on a newer upstream vLLM (N2); the Blueprint's default embedding image 1.12.0 beside 2.3.0 of the same model (N4)",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"first_batch": {"file": "../first_batch/prediction_first_batch.json", "sha256": sha(os.path.join(VOL, "results", "first_batch", "prediction_first_batch.json"))},
                 "whole_corpus": {"file": "../whole_corpus_quality/prediction_whole_corpus.json", "sha256": sha(os.path.join(VOL, "results", "whole_corpus_quality", "prediction_whole_corpus.json"))}},
 "kept_from_them": "one container on the card at a time; the gate before every container and, with its timed form, before every timed step; no game launcher while a timed step runs; a timed step is one blocking command; every number carries its boundary; results are written as they come",
 "host": "one RTX 5090 (32 GB), Windows 11, Docker Desktop on WSL2; the driver version is recorded by every gate",
 "order": ["probes before this file was frozen (below)", "N2", "N1: n3, rr1b, e1b, evl, rr500, e300", "N4 if time is left"],
 "time_limit": "nothing is started that cannot end before 08:00 local time; an arm of N1 is not started with less than 40 minutes left. What is not run tonight is reported as not run.",

 "probes_before_the_freeze": {
  "why": "the load tool had only met this volume's stand-in server. Whether it sends the prepared bodies to a real NIM, reads the answer, and what its own start and export cost had to be seen on a real NIM before the design was fixed.",
  "what": "the reranking NIM (arm rr1b) and the embedding NIM (arm n3) each started once; per request shape 8 seconds at 1 and at 8 requests in flight through scripts/sweep_level.py. These containers ran before this file was frozen; their records are named probe_*.json and are not results of the sweep.",
  "rr1b": probe("rr1b"), "n3": probe("n3")},

 "N1_concurrency_sweep": {
  "question": "with one retrieval NIM alone on the card, how do the rate and the duration of a request change as more requests are in flight, and where does the rate stop rising",
  "arms": ARMS,
  "load": {"tool": "AIPerf 0.11.0 in the container vol4-aiperf:0.11.0 (client_aiperf/Dockerfile) on the NIM's Docker network; closed loop: a fixed number of requests in flight, a finished one replaced at once",
           "bodies": "written before the session by scripts/sweep_payloads.py with this volume's request builders and replayed verbatim (--endpoint-type raw, --custom-dataset-type inputs-json); --tokenizer builtin, so nothing is downloaded at run time",
           "shapes": {"embedding": {"query": "one query per request, input_type query: the 393 queries of the reduced MIRACL zh task", "passage": "64 passages per request, input_type passage: the first 4,096 passages of that corpus (the sample of every timed embedding cell of this volume)"},
                      "reranking": {"passages_100": "one query with the first 100 passages of its first-stage ranking (whole MIRACL zh corpus, 393 queries)", "passages_10": "the same with the first 10"}},
           "levels": [1, 2, 4, 8, 16, 32, 64], "one_more_level": "after 64, while the rate is more than 5% above the level before, the number in flight is doubled (128, then 256 at most)",
           "per_level": "the gate in its timed form, then 40 seconds at the level after a warm-up of twice the level in requests; one blocking command",
           "bodies_per_arm": {a: payloads(a) for a in ARMS}},
  "per_arm": ["a new container; the gate before it", "calibration: this volume's own client at one request in flight (embed_cell.py throughput: 64 per request, three passes; rerank_latency.py: 100 passages per call, one pass)",
              "the sweep of both shapes", "the container removed; a second new container; the two highest levels of each shape again; both runs are reported side by side, not pooled"],
  "calibration_rule": "AIPerf at one request in flight (passage shape, or 100 passages) against the own client's items per second: more than 20% apart stops the arm before its sweep, and the arm is reported as stopped. Nothing is adjusted.",
  "client_rule": "every level records what the load-tool container used of the CPU (its cgroup, start and export included). A level at which it used 85% or more of all the cores it can see is marked client-limited, and such a level is not called the NIM's saturation.",
  "reported": {"per_arm_and_shape": "one row per level: requests per second, items per second (requests per second x items per request), p50 / p90 / p99 of the duration of a request in ms, requests, errors, the client's CPU",
               "saturation": "the lowest level whose rate is at least 95% of the highest rate of that shape in that container",
               "described_not_judged": "the highest level whose p99 is at most 100 ms, and at most 500 ms. Two round numbers to read the table by: there is no published limit for these services, and nothing passes or fails here.",
               "errors": "a level with errors is reported with their count and is not used for the saturation"},
  "second_night": "one request in flight and the saturation level of every arm again on another night; not part of tonight",
  "expectation": {"calibration": "within 10% for every arm (same bodies, same network path, one kept connection each)",
                  "one_in_flight": "passage shape within 10% of the single-stream values named per arm above; 100 passages zh: p50 between 140 and 190 ms",
                  "shape_of_the_curve": "passage shape and 100 passages: the rate rises by less than 50% from 1 to 64 in flight (one request already fills a batch) and the duration of a request grows about in proportion; query shape and 10 passages: the rate rises at least fourfold before it flattens",
                  "client": "no level client-limited for the passage shape and for reranking; the query shape of the 300m encoder may be (its requests are the shortest)",
                  "confidence": "low for the shape of the curves: nothing in this volume was measured with more than one request in flight"},
  "not_claimed": ["a number of users: a level is a number of requests in flight", "two services on the card together", "requests of other sizes or languages", "a search service behind the encoder"]},

 "N2_content_safety_model_on_a_newer_engine": {
  "why": "the only serving engine Nemotron 3.5 Content Safety has run on here is upstream vLLM 0.20.2, and that image is kept on the disk for this model alone. Whether a newer image already on this machine serves it with the same verdicts decides whether the older image is still needed. This is not a cell of the published Vol.3 study and changes none of its figures.",
  "model_card": {"file": "README.md of the Hugging Face snapshot 35645ed3543b7e7ffaed2e788699e57a5051497c", "line": 'pip install "vllm>=0.11.0,<=0.20.2"', "reading": "0.20.2 is the newest version the card names; both newer images on this machine (0.27.1, 0.30.0) are outside that range"},
  "engine": {"image": "vllm/vllm-openai:v0.30.0", "digest": local_digest("vllm/vllm-openai:v0.30.0"), "outside_the_model_cards_range": True,
             "start_setting": {"VLLM_USE_V2_MODEL_RUNNER": "0"}, "why_that_setting": "on this host vLLM 0.27.1 needed it to start (Vol.3, generic-NIM cell); 0.30.0 is started with it for the same reason",
             "command": "the study's container command for this model (p102_run.vllm_command) with the image changed and the variable added; nothing else"},
  "cells": "the study's unchanged p93_judge.py --arm J4 (reasoning off), per track: precheck, the stability subset at 16 in flight (200 prompts, 100 responses), the whole track at 16 in flight",
  "reference": {"what": "the study's own new-container re-read of the same subsets on 0.20.2 (arm J4, 2026-10-02)", "prompts": {"same": stab["input"]["k"], "of": stab["input"]["n"]}, "responses": {"same": stab["output"]["k"], "of": stab["output"]["n"]},
                "verdicts_per_s_c16_on_0202": {"prompts": round(J4["tracks"]["input"]["quality_cell"]["verdicts_per_s"], 2), "responses": round(J4["tracks"]["output"]["quality_cell"]["verdicts_per_s"], 2)}},
  "reading": "the server starts and passes both prechecks, and on the stability subsets the number of items whose verdict differs from the 0.20.2 main run is not more than the reference's own (both tracks together) => 'replaceable': the 0.20.2 image becomes a candidate for removal, which its owner decides. Otherwise it stays. The whole-track differences and the rate are reported beside it and do not enter the reading.",
  "expectation": {"starts": "yes (moderate confidence)", "differing_on_the_subsets": "0 to 3 of 300; the reference is 0 of 300, so one differing item already means 'stays'",
                  "rate": "within 15% of the 0.20.2 figures, either way", "note": "for another model of this family the same step of engine version changed 0.4% of the verdicts; a rule of 'not more than 0' is strict on purpose: it is the model's own repeat on the old engine"},
  "results": "kept outside the repository (the driver and its files are not part of this volume); whether any of it is published is decided later",
  "runner_outside_the_repository_sha256": sha(N2_RUNNER) if N2_RUNNER else None},

 "N4_blueprint_default_embedding_image": {
  "why": "the RAG Blueprint's compose files name llama-nemotron-embed-vl-1b-v2:1.12.0; this volume measured the same model as 2.3.0. Whether the older image gives the same quality and at least the same speed decides whether it has to be kept.",
  "image": "nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:1.12.0", "image_digest": local_digest("nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:1.12.0"), "never_started_here": True,
  "cells": ["the quality cells of the first session for this model (SciFact, reduced MIRACL zh and ja), with the first session's programs and commands and the image changed", "the query shape of N1's sweep"],
  "against": "the 2.3.0 image: first-session quality, N1's query-shape results of arm evl",
  "reading": "nDCG@10 within 0.002 of the 2.3.0 value on each of the three data sets (the first session's two serving paths of one model agreed to 0.0011) and the rate at one request in flight not lower by more than 5% => the older image becomes a candidate for removal; otherwise it stays",
  "tonight": "last in the order and run only if time is left; its first start downloads the model",
  "expectation": "no guess is recorded for the quality difference; the older image is a different runtime (1.x) and its precision on this card is not known before it starts"},

 "harness_sha256": {f: sha(os.path.join(VOL, f)) for f in NEW + USED if not f.endswith("gen_prediction_concurrency_sweep.py")} | {"tools/g8_gate.py": sha(os.path.join(REPO, "tools", "g8_gate.py"))},
 "generator": "scripts/gen_prediction_concurrency_sweep.py (this file's writer; its SHA-256 is in the events file)",
 "programs_written_after_the_freeze": "scripts/sweep_table.py, which makes the tables from the level records, exists at the freeze but has not been run on a real record and may still change; the program of the figure is not written. The SHA-256 of each is recorded with its first use.",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
os.makedirs(RES, exist_ok=True)
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
