"""P17 · one closed-loop concurrency sweep with AIPerf against a running NIM container.
usage: p17_sweep.py --profile C|S|R --levels 1,4,... --out DIR --aiperf EXE --tokenizer DIR --data-dir DIR [--first-duration 60]

Per level, one `aiperf profile` process:
  --concurrency N (closed loop: a new request is issued as soon as one completes)
  --warmup-request-count N at the same concurrency (excluded by AIPerf)
  --benchmark-duration D, --benchmark-grace-period 0 (requests still running when D ends are not counted; the drain tail,
    where in-flight requests fall below N, is therefore excluded)
  D = min(600, max(60, 4 × E)), E = previous level's p99 request latency × N / N_prev (linear upper bound); first level 60 s.
  After the level: completed requests < 3 × N is flagged in the level record (not repeated, not extended).
Random seed 20260915 + N per level, so prompts differ between levels (the server keeps prefix caching on, its default).
Every level's AIPerf artifacts are written before the next level starts (levels.jsonl is appended per level)."""
import argparse, json, os, subprocess, time
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
MODEL = "meta/llama-3.1-8b-instruct"
PROFILE_ARGS = {
    "C": ["--isl", "200", "--isl-stddev", "50", "--osl", "200", "--osl-stddev", "50", "--extra-inputs", "ignore_eos:true"],
    "R": ["--isl", "3500", "--isl-stddev", "300", "--osl", "500", "--osl-stddev", "50", "--extra-inputs", "ignore_eos:true"],
    "S": ["--custom-dataset-type", "single-turn", "--dataset-sampling-strategy", "shuffle", "--osl", "128", "--export-level", "raw"],  # EOS respected; raw keeps outputs for ROUGE
}
SUMMARY_KEYS = ["time_to_first_token", "inter_token_latency", "request_latency", "output_token_throughput",
                "output_token_throughput_per_user", "request_throughput", "request_count", "error_request_count",
                "input_sequence_length", "output_sequence_length", "benchmark_duration"]


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def ctx():
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version",
                               "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:
        return f"nvidia-smi failed: {e!r}"


ap = argparse.ArgumentParser()
ap.add_argument("--profile", required=True, choices=["C", "S", "R"])
ap.add_argument("--levels", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--aiperf", required=True)
ap.add_argument("--tokenizer", required=True)
ap.add_argument("--data-dir", required=True)
ap.add_argument("--first-duration", type=int, default=60)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
levels = [int(x) for x in a.levels.split(",")]
log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8")

prev = None
for n in levels:
    if prev is None:
        dur = a.first_duration
    else:
        e = prev["request_latency_p99_ms"] / 1000 * n / prev["concurrency"] if prev.get("request_latency_p99_ms") else a.first_duration
        dur = int(min(600, max(60, 4 * e)))
    art = os.path.join(a.out, f"c{n:04d}")
    cmd = [a.aiperf, "profile", "-m", MODEL, "--endpoint-type", "chat", "--streaming", "-u", "http://localhost:8000",
           "--tokenizer", a.tokenizer, *PROFILE_ARGS[a.profile], "--extra-inputs", "temperature:0",
           "--concurrency", str(n), "--warmup-request-count", str(n), "--benchmark-duration", str(dur),
           "--benchmark-grace-period", "0", "--use-server-token-count", "--no-gpu-telemetry", "--ui-type", "none",
           "--random-seed", str(20260915 + n), "--artifact-dir", art]
    if a.profile == "S":
        cmd[cmd.index("--custom-dataset-type"):cmd.index("--custom-dataset-type")] = ["--input-file", os.path.join(a.data_dir, "S_cnn_dailymail_validation_mlperf_template.jsonl")]
    rec = {"profile": a.profile, "concurrency": n, "duration_s": dur, "start": now(), "ctx_start": ctx(), "command": cmd}
    print(f"level c={n} D={dur}s start {rec['start']}", flush=True)
    with open(art + "_console.txt", "w", encoding="utf-8") as con:
        rc = subprocess.run(cmd, stdout=con, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}).returncode
    rec.update({"rc": rc, "end": now(), "ctx_end": ctx()})
    summ_path = os.path.join(art, "profile_export_aiperf.json")
    if rc == 0 and os.path.exists(summ_path):
        s = json.load(open(summ_path, encoding="utf-8"))
        rec["summary"] = {k: s.get(k) for k in SUMMARY_KEYS}
        rec["error_summary"] = s.get("error_summary")
        rec["was_cancelled"] = s.get("was_cancelled")
        rec["aiperf_version"] = s.get("aiperf_version")
        cnt = (s.get("request_count") or {}).get("avg") or 0
        rec["completed"] = cnt
        rec["completed_ge_3N"] = cnt >= 3 * n
        rec["request_latency_p99_ms"] = (s.get("request_latency") or {}).get("p99")
    log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
    print(f"level c={n} rc={rc} completed={rec.get('completed')} end {rec['end']}", flush=True)
    prev = rec if rec.get("request_latency_p99_ms") else prev
    time.sleep(10)
print("sweep done", now(), flush=True)
