#!/usr/bin/env python3
"""Per-cell wall-clock timeout for measured levels.

run(fn, timeout_s, artifact_dir) calls fn() in a thread. If fn has not returned when the timeout expires, every process
whose command line names the level's artifact directory (the AIPerf run of that level, and its worker processes) is
killed, so the harness function's own subprocess call returns and fn() finishes; the result is then marked hung.
The rule for the timeout: max(3 x the level's expected duration, 300 s), at most 900 s (timeout_for).
Nothing about the level function changes; only the load generator is stopped from outside.
self-test (python tools/cell_timeout.py --self-test): a socket that accepts connections and never answers stands in for a
server that hangs; AIPerf is pointed at it with a 20 s timeout and must be stopped and reported hung (positive control); a
function that returns at once must not be (negative control).
"""
import os, socket, subprocess, sys, threading, time

import psutil

MIN_S, MAX_S, FACTOR = 300, 900, 3


def timeout_for(expected_s):
    return int(min(MAX_S, max(MIN_S, FACTOR * (expected_s or 0))))


def _kill_matching(needle):
    killed = []
    me = os.getpid()
    for p in psutil.process_iter(["pid", "cmdline"]):
        if p.info["pid"] == me:
            continue
        cl = " ".join(p.info.get("cmdline") or [])
        if needle and needle in cl.replace("\\", "/"):
            try:
                for c in p.children(recursive=True):
                    c.kill(); killed.append(c.pid)
                p.kill(); killed.append(p.pid)
            except psutil.Error:
                pass
    return killed


def run(fn, timeout_s, artifact_dir):
    box = {}
    t0 = time.time()
    th = threading.Thread(target=lambda: box.__setitem__("r", fn()), daemon=True)
    th.start(); th.join(timeout_s)
    if not th.is_alive():
        return box.get("r"), {"hung": False, "elapsed_s": round(time.time() - t0, 1), "timeout_s": timeout_s}
    needle = os.path.abspath(artifact_dir).replace("\\", "/")
    killed = _kill_matching(needle)
    if not killed:   # the AIPerf command line may carry the path as given, not absolute
        killed = _kill_matching(artifact_dir.replace("\\", "/"))
    th.join(120)
    return box.get("r"), {"hung": True, "elapsed_s": round(time.time() - t0, 1), "timeout_s": timeout_s, "killed_pids": killed,
                          "function_returned_after_kill": not th.is_alive()}


def self_test():
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(64); port = srv.getsockname()[1]
    held = []
    stop = threading.Event()
    def accept():
        srv.settimeout(0.5)
        while not stop.is_set():
            try:
                c, _ = srv.accept(); held.append(c)   # accept and never answer
            except OSError:
                pass
    threading.Thread(target=accept, daemon=True).start()
    import tempfile
    art = os.path.join(tempfile.mkdtemp(prefix="cto_"), "c0001")
    aiperf = os.environ.get("AIPERF", "aiperf")
    cmd = [aiperf, "profile", "-m", "m", "--endpoint-type", "chat", "-u", f"http://127.0.0.1:{port}", "--tokenizer", os.environ.get("TOKENIZER", "gpt2"),
           "--concurrency", "1", "--request-count", "2", "--no-gpu-telemetry", "--ui-type", "none", "--artifact-dir", art]
    r, info = run(lambda: subprocess.run(cmd, capture_output=True, text=True).returncode, 20, art)
    ok1 = info["hung"] and info["function_returned_after_kill"] and 20 <= info["elapsed_s"] < 150
    r2, info2 = run(lambda: 7, 20, art)
    ok2 = not info2["hung"] and r2 == 7
    stop.set(); srv.close()
    for c in held:
        c.close()
    print(("PASS " if ok1 else "FAIL ") + f"positive control: AIPerf against an endpoint that never answers is stopped and reported hung {info}")
    print(("PASS " if ok2 else "FAIL ") + f"negative control: a function that returns at once is not hung {info2}")
    print(("PASS " if timeout_for(60) == 300 and timeout_for(200) == 600 and timeout_for(832) == 900 else "FAIL ") + "timeout rule: 60 s -> 300, 200 s -> 600, 832 s -> 900")
    return 0 if ok1 and ok2 else 1


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv else 0)
