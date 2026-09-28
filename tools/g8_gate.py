#!/usr/bin/env python3
"""G8 environment gate: is the GPU otherwise idle before a measured cell?

Samples the GPU for 10 s at 1 Hz with nvidia-smi (utilization.gpu, power.draw). The gate passes when the median
utilization is <= 2% and the median power is <= 45 W. The thresholds come from a window with no other GPU load on this
desktop: P66's R1024 arm (2026-09-27 12:52-13:21), where every level ended at 0% utilization and 26-42 W
(P66 results, p66_rails_under_load/levels.jsonl, gpu_end). If a check fails, it is repeated every 60 s for up to 15 min;
every attempt's ten samples are recorded, passed or not. The GPU's own compute processes (nvidia-smi
--query-compute-apps) are recorded as counts beside each attempt.
usage (as a module): gate() -> record; sample() -> one attempt. From the shell: python tools/g8_gate.py [--once]
"""
import json, statistics, subprocess, sys, time

UTIL_MAX, POWER_MAX = 2.0, 45.0
SAMPLES, RETRY_S, MAX_WAIT_S = 10, 60, 900
SOURCE = ("P66 R1024 arm, 2026-09-27 12:52-13:21, a window with no other GPU load: every level ended at 0% utilization and "
          "26-42 W (P66 results, p66_rails_under_load/levels.jsonl, gpu_end)")


def _smi(args):
    r = subprocess.run(["nvidia-smi", *args], capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def sample():
    rows = []
    for _ in range(SAMPLES):
        line = _smi(["--query-gpu=utilization.gpu,power.draw", "--format=csv,noheader,nounits"]).splitlines()[0]
        u, p = [x.strip() for x in line.split(",")]
        rows.append({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "util_pct": float(u), "power_w": float(p)})
        time.sleep(1.0)
    apps = [l for l in _smi(["--query-compute-apps=pid,process_name", "--format=csv,noheader"]).splitlines() if l.strip()]
    up = statistics.median(r["util_pct"] for r in rows); pp = statistics.median(r["power_w"] for r in rows)
    return {"samples": rows, "util_pct_p50": up, "power_w_p50": pp, "compute_processes_listed": len(apps),
            "pass": up <= UTIL_MAX and pp <= POWER_MAX}


def gate(max_wait_s=MAX_WAIT_S, retry_s=RETRY_S):
    t0 = time.time(); attempts = []
    while True:
        a = sample(); attempts.append(a)
        if a["pass"] or time.time() - t0 + retry_s > max_wait_s:
            break
        time.sleep(retry_s)
    return {"gate": "G8", "rule": f"util p50 <= {UTIL_MAX} % and power p50 <= {POWER_MAX} W over {SAMPLES} samples at 1 Hz; retry every {retry_s} s up to {max_wait_s} s",
            "source": SOURCE, "attempts": attempts, "waited_s": round(time.time() - t0, 1), "pass": attempts[-1]["pass"]}


if __name__ == "__main__":
    print(json.dumps(sample() if "--once" in sys.argv else gate(), indent=1))
