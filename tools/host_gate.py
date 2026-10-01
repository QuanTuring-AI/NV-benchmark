#!/usr/bin/env python3
"""Host-side record for measured cells (added 2026-09-29, P78). G8 (tools/g8_gate.py) checks the GPU only; P69 showed a
server-side cell can run slower with the GPU idle because the host's CPU was in a different state. This module records the
host, it does not gate on it: the threshold for "the host is not the same" has no measured basis yet.

calibrate()   before a run: a fixed unit of CPU work (SHA-256 over 16 MiB, 16 times, in this process) timed in wall
              seconds and in this process's CPU seconds, three repeats; the processor model, logical cores, psutil's
              frequency reading and the active power plan.
cell_start()  / cell_end(h): per cell, the wall time, the system-wide CPU busy share over the cell (psutil cpu_times
              delta), this process's CPU seconds and share, the CPU seconds of this process's children still alive at the
              end, and one work probe (the calibration unit, SHA-256 over 16 MiB x 16) timed at the end of the cell.
Without psutil every field that needs it is None and `psutil` says so; nothing raises.
usage: python tools/host_gate.py [--self-test]
"""
import hashlib, json, os, platform, subprocess, sys, time

try:
    import psutil
except Exception:          # the lm-eval venv has no psutil; the record says so instead of failing
    psutil = None

BLOCK = os.urandom(16 * 1024 * 1024)


def _work(n):
    t0, c0 = time.perf_counter(), time.process_time()
    for _ in range(n):
        hashlib.sha256(BLOCK).digest()
    return {"wall_s": round(time.perf_counter() - t0, 4), "cpu_s": round(time.process_time() - c0, 4)}


def _power_plan():
    try:
        return subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, encoding="mbcs", errors="replace", timeout=20).stdout.strip()[:200] or None
    except Exception:
        return None


def calibrate():
    reps = [_work(16) for _ in range(3)]
    rec = {"unit": "SHA-256 over 16 MiB x 16, in this process", "repeats": reps,
           "wall_s_median": sorted(r["wall_s"] for r in reps)[1], "processor": platform.processor(),
           "logical_cpus": os.cpu_count(), "power_plan": _power_plan(), "psutil": bool(psutil)}
    if psutil:
        f = psutil.cpu_freq()
        rec["cpu_freq_mhz"] = {"current": f.current, "max": f.max} if f else None
        rec["cpu_percent_1s"] = psutil.cpu_percent(interval=1.0)
    return rec


def cell_start():
    h = {"t": time.time(), "own_cpu": time.process_time()}
    if psutil:
        h["sys"] = psutil.cpu_times()
    return h


def _busy(a, b):
    ta, tb = sum(a), sum(b)
    idle = (getattr(b, "idle", 0) - getattr(a, "idle", 0))
    return round(1 - idle / (tb - ta), 4) if tb > ta else None


def cell_end(h):
    wall = time.time() - h["t"]; own = time.process_time() - h["own_cpu"]
    rec = {"wall_s": round(wall, 2), "own_cpu_s": round(own, 2), "own_cpu_share_of_one_core": round(own / wall, 4) if wall > 0 else None,
           "probe_end": _work(16), "psutil": bool(psutil)}
    if psutil:
        rec["system_busy_share"] = _busy(h["sys"], psutil.cpu_times())
        try:
            kids = psutil.Process().children(recursive=True)
            rec["children_alive_cpu_s"] = round(sum(sum(k.cpu_times()[:2]) for k in kids), 2)
        except Exception:
            rec["children_alive_cpu_s"] = None
        f = psutil.cpu_freq()
        rec["cpu_freq_mhz_current"] = f.current if f else None
    return rec


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        c = calibrate()
        h = cell_start(); _work(8); e = cell_end(h)
        # positive control: a cell that burns CPU in this process must show own CPU share > 0.5 of a core
        ok = e["own_cpu_share_of_one_core"] is not None and e["own_cpu_share_of_one_core"] > 0.5
        h2 = cell_start(); time.sleep(1.0); e2 = cell_end(h2)
        # negative control: a cell that sleeps must show a share < the positive one
        ok2 = e2["own_cpu_share_of_one_core"] < e["own_cpu_share_of_one_core"]
        print(json.dumps({"calibration": c, "busy_cell": e, "idle_cell": e2, "positive_control": ok, "negative_control": ok2}, indent=1))
        sys.exit(0 if ok and ok2 else 1)
    print(json.dumps(calibrate(), indent=1))
