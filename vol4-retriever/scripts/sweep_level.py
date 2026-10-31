#!/usr/bin/env python3
"""Vol.4 · one level of a concurrency sweep: AIPerf replays prepared request bodies against one NIM at a fixed number
of requests in flight (closed loop: a finished request is replaced at once), for a fixed time, and this program keeps
a short record of what AIPerf exported.

Runs inside the load-tool container on the NIM's Docker network (no host port in between). The request bodies are the
ones sweep_payloads.py wrote; AIPerf sends them as they are (`--endpoint-type raw`, `--custom-dataset-type inputs-json`)
and takes its token counts from nowhere (`--tokenizer builtin`, no download at run time).

  discarded   --warmup requests before the timed phase (AIPerf's warm-up phase)
  timed       --duration seconds at --concurrency requests in flight
  kept        requests per second, items per second (requests per second x items per request), the duration of a
              request (AIPerf's request_latency: p50, p90, p99, mean, min, max, in ms), the number of requests and of
              errors, the share of requests on a reused connection, and what this container itself used of the CPU
              during the run (from its cgroup), so that a level limited by the client can be told from one limited by
              the NIM. AIPerf's own files (one line per request) go to --artifacts, outside the repository.

usage: sweep_level.py --url URL --endpoint /v1/embeddings|/v1/ranking --model NAME --inputs FILE --items N
                      --concurrency C --out FILE.json --artifacts DIR [--duration 45] [--warmup 0=2xC]
"""
import argparse, hashlib, json, os, subprocess, sys, time


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def cpu_usec():
    try:
        for line in open("/sys/fs/cgroup/cpu.stat", encoding="utf-8"):
            if line.startswith("usage_usec"):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--endpoint", required=True, choices=["/v1/embeddings", "/v1/ranking"]); ap.add_argument("--model", required=True)
    ap.add_argument("--inputs", required=True); ap.add_argument("--items", type=int, required=True); ap.add_argument("--concurrency", type=int, required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--artifacts", required=True); ap.add_argument("--duration", type=int, default=45); ap.add_argument("--warmup", type=int, default=0)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    warm = a.warmup or 2 * a.concurrency
    cmd = ["aiperf", "profile", "--model", a.model, "--url", a.url, "--endpoint-type", "raw", "--custom-endpoint", a.endpoint, "--custom-dataset-type", "inputs-json", "--input-file", a.inputs,
           "--concurrency", str(a.concurrency), "--benchmark-duration", str(a.duration), "--warmup-request-count", str(warm), "--tokenizer", "builtin", "--use-server-token-count",
           "--ui", "none", "--artifact-dir", a.artifacts, "--no-gpu-telemetry", "--no-server-metrics"]
    os.makedirs(os.path.dirname(a.out), exist_ok=True); os.makedirs(a.artifacts, exist_ok=True)
    start = now(); c0 = cpu_usec(); t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=a.duration + 300); rc = r.returncode; tail = (r.stdout or "")[-600:] + (r.stderr or "")[-600:]
    except subprocess.TimeoutExpired:
        rc, tail = 124, "no end within the time limit"
    wall = time.time() - t0; c1 = cpu_usec()
    rec = {"what": "one level of a closed-loop concurrency sweep, replayed by AIPerf", "start": start, "end": now(), "url": a.url, "endpoint": a.endpoint, "model": a.model,
           "inputs": {"file": os.path.basename(a.inputs), "sha256": hashlib.sha256(open(a.inputs, "rb").read()).hexdigest()}, "items_per_request": a.items, "concurrency": a.concurrency,
           "duration_asked_s": a.duration, "warmup_requests": warm, "aiperf_rc": rc, "command": cmd}
    exp = os.path.join(a.artifacts, "profile_export_aiperf.json")
    if rc == 0 and os.path.isfile(exp):
        d = json.load(open(exp, encoding="utf-8")); lat = d["request_latency"]; rps = d["request_throughput"]["avg"]
        rec.update({"aiperf_version": d.get("aiperf_version"), "requests": int(d["request_count"]["avg"]), "errors": d.get("error_summary") or [], "was_cancelled": d.get("was_cancelled"),
                    "benchmark_duration_s": round(d["benchmark_duration"]["avg"], 3), "requests_per_s": round(rps, 3), "items_per_s": round(rps * a.items, 1),
                    "request_ms": {k: round(lat[k], 3) for k in ("p50", "p90", "p99", "avg", "min", "max")},
                    "connection_reused_share": round((d.get("http_req_connection_reused") or {}).get("avg", float("nan")), 4)})
    else:
        rec["note"] = "AIPerf did not end with an export"; rec["output_tail"] = tail[-800:]
    cores = os.cpu_count()
    rec["client_cpu"] = None if c0 is None or c1 is None else {"cores_visible": cores, "cpu_seconds": round((c1 - c0) / 1e6, 2), "wall_s": round(wall, 2), "cores_used_mean": round((c1 - c0) / 1e6 / wall, 2),
                                                                "share_of_all_cores": round((c1 - c0) / 1e6 / wall / cores, 3), "includes": "AIPerf's start and its export, not only the timed phase"}
    rec["program"] = {"file": "sweep_level.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: rec.get(k) for k in ("concurrency", "requests", "requests_per_s", "items_per_s", "request_ms", "errors", "client_cpu", "aiperf_rc", "note")}))
    return 0 if rc == 0 and "requests_per_s" in rec and not rec["errors"] else 7


if __name__ == "__main__":
    sys.exit(main())
