#!/usr/bin/env python3
"""Vol.2 · P79 · host state: is this morning's slowdown the host (uptime), the configuration, or transient?
Diagnosis only; nothing here feeds a table.

One phase (T1 before the host reboot, T2 after) = three containers in this order: K8, K16, K8.
  K8   Nemotron 3 Nano, NIM 2.0.12, NVFP4 profile, NIM_MAX_MODEL_LEN 8192 (p55_concurrency_a2_256 main / P78 s256)
  K16  the same with NIM_MAX_MODEL_LEN 16384 (P78 G4's N3)
Both are started by p50_footprint.start (the docker run of P55 and P78 G6); only NIM_MAX_MODEL_LEN differs.
Per container, after READY: one short request, the 120 s c=1 warm-up level of P55 / P78 G6 (profile R, discarded), then
three 60 s cells with p53_concurrency_v2's AIPerf command unchanged (the command P55 ran): R c=1, C c=1, C c=128.
Recorded: nvidia-smi clocks / throttle reasons / power / utilization every 500 ms for the container's whole life; the WSL
kernel log's dxg line count and the WSL VM start time (both distributions) after READY; the container logs; per-process
GPU memory from the Windows counters every 10 s (nvidia-smi under WDDM does not show the compositor's share); G8 and the
host record per cell; sha256 of every P78 G6 result file before and after (they must not change).
G8 is one 10 s attempt per cell, recorded and not waited on: the 500 ms nvidia-smi logger the ticket requires lifts
the idle utilization reading from 2.0% to 2.5% (measured 2026-09-30 09:55, no container), over G8's 2% line, and the
cell runs either way (diagnosis, not a table).
usage: p79_host_state.py --phase T1|T2 --aiperf EXE --tokenizer-root DIR [--out DIR] [--test]
env: NGC_ENV_FILE (--env-file, never read) · NIM_CACHE_DIR
"""
import argparse, glob, hashlib, json, os, subprocess, sys, threading, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, "tools"))
from p50_footprint import ARMS, BASE, gpu, metrics_cache_config, now, sh, start, stop  # noqa: E402
import p53_concurrency_v2 as C2  # noqa: E402
import g8_gate as G  # noqa: E402
import host_gate as HG  # noqa: E402
import overwrite_gate as O  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_OUT = os.path.join(HERE, "..", "results", "p79_host_state")
G6_DIR = os.path.join(HERE, "..", "results", "p78_clean_rerun")
ORDER = [("K8", "8192"), ("K16", "16384"), ("K8", "8192")]
CELLS = [("R", 1), ("C", 1), ("C", 128)]
SMI_QUERY = "timestamp,clocks.sm,clocks.mem,clocks_throttle_reasons.active,power.draw,utilization.gpu"
WIN_COUNTERS = r"""
$o=@()
(Get-Counter '\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage').CounterSamples | Where-Object { $_.CookedValue -gt 20MB } | ForEach-Object {
  if ($_.InstanceName -match 'pid_(\d+)') { $o += ('P|' + (Get-Process -Id $matches[1] -EA SilentlyContinue).ProcessName + '|' + ($_.Path.Split('\')[-1] -replace ' usage','') + '|' + [math]::Round($_.CookedValue/1GB,3)) } }
(Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage','\GPU Adapter Memory(*)\Shared Usage').CounterSamples | Where-Object { $_.CookedValue -gt 20MB } | ForEach-Object {
  $o += ('A|adapter|' + ($_.Path.Split('\')[-1] -replace ' usage','') + '|' + [math]::Round($_.CookedValue/1GB,3)) }
$o -join "`n"
"""


def manifest(d):
    out = {}
    for p in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
        if os.path.isfile(p):
            out[os.path.relpath(p, d).replace(os.sep, "/")] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def win_gpu_memory():
    r = subprocess.run(["powershell", "-NoProfile", "-Command", WIN_COUNTERS], capture_output=True, text=True, encoding="mbcs", errors="replace", timeout=60)
    d = {}
    for line in r.stdout.splitlines():
        p = line.strip().split("|")
        if len(p) == 4:
            try:
                d[f"{p[1]}:{p[2]}"] = round(d.get(f"{p[1]}:{p[2]}", 0) + float(p[3]), 3)
            except ValueError:
                pass
    return d


def wsl_state():
    out = {}
    for distro in ("docker-desktop", None):
        cmd = ["wsl"] + (["-d", distro] if distro else []) + ["-e", "sh", "-c", "dmesg 2>&1 | grep -c dxg; dmesg 2>&1 | grep -c 'dxgkio_make_resident'; uptime -s; cat /proc/uptime"]
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        txt = r.stdout.decode("utf-8", "replace").replace("\x00", "").split("\n")
        out[distro or "default"] = {"dxg_lines": txt[0].strip() if txt else None, "make_resident_failures": txt[1].strip() if len(txt) > 1 else None,
                                    "wsl_vm_started": txt[2].strip() if len(txt) > 2 else None, "proc_uptime": txt[3].strip() if len(txt) > 3 else None,
                                    "rc": r.returncode}
    return out


class Sampler(threading.Thread):
    """Windows GPU memory counters every 10 s into a JSONL file, until stopped."""
    def __init__(self, path):
        super().__init__(daemon=True); self.path = path; self.stop_ev = threading.Event()

    def run(self):
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            while not self.stop_ev.is_set():
                try:
                    f.write(json.dumps({"at": now(), "gib": win_gpu_memory()}) + "\n"); f.flush()
                except Exception as e:  # noqa: BLE001
                    f.write(json.dumps({"at": now(), "error": str(e)[:200]}) + "\n"); f.flush()
                self.stop_ev.wait(10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["T1", "T2"]); ap.add_argument("--aiperf", required=True)
    ap.add_argument("--tokenizer-root", required=True); ap.add_argument("--out", default=DEFAULT_OUT); ap.add_argument("--test", action="store_true")
    a = ap.parse_args(); a.out = os.path.abspath(a.out)
    pdir = os.path.join(a.out, a.phase); os.makedirs(pdir, exist_ok=True); logdir = os.path.join(pdir, "logs"); os.makedirs(logdir, exist_ok=True)
    O.SCOPES = O.SCOPES + sorted(d for d in os.listdir(REPO) if d.startswith("vol") and d not in O.SCOPES)
    snap = O.snapshot(REPO, [os.path.relpath(a.out.split(os.sep + "harness_test")[0], REPO).replace(os.sep, "/")])
    ev = open(os.path.join(pdir, "events.jsonl"), "a", encoding="utf-8", newline="\n")
    log = open(os.path.join(pdir, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    event = lambda **kw: (ev.write(json.dumps({**kw, "phase": a.phase, "at": now()}, ensure_ascii=False) + "\n"), ev.flush())  # noqa: E731
    g6_before = manifest(G6_DIR)
    json.dump(g6_before, open(os.path.join(pdir, "g6_sha256_before.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
    steam = subprocess.run(["tasklist"], capture_output=True, text=True, encoding="mbcs", errors="replace").stdout.lower().count("steam")
    event(kind="run_start", test=a.test, host_calibration=HG.calibrate(), steam_lines=steam, docker_ps=sh(["docker", "ps", "-q"], timeout=30).stdout.strip(),
          windows_boot=subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('s')"], capture_output=True, text=True, encoding="mbcs", errors="replace").stdout.strip(),
          gpu_memory_windows=win_gpu_memory(), wsl=wsl_state(), g6_files=len(g6_before))
    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        event(kind="refused", reason="a container is running"); return 3
    sampler = Sampler(os.path.join(pdir, "windows_gpu_memory.jsonl")); sampler.start()
    rc = 0
    for seq, (setting, maxlen) in enumerate(ORDER, 1):
        name = f"p79_{a.phase.lower()}_{seq}_{setting.lower()}"
        smi_f = open(os.path.join(pdir, f"smi_{name}.csv"), "w", encoding="utf-8", newline="\n")
        smi = subprocess.Popen(["nvidia-smi", f"--query-gpu={SMI_QUERY}", "--format=csv", "-lms", "500"], stdout=smi_f, stderr=subprocess.STDOUT)
        ARMS["A2"] = dict(ARMS["A2"], env={"NIM_MAX_MODEL_LEN": maxlen})
        event(kind="container_launch", container_seq=seq, setting=setting, name=name, env=ARMS["A2"]["env"], gpu_memory_windows=win_gpu_memory())
        st_ = start("A2", name, None, logdir)
        if not st_["ready"]:
            event(kind="container_failed", container_seq=seq, setting=setting, reason=st_.get("reason"))
            C2.save_logs(name, logdir); stop(name); smi.terminate(); smi_f.close(); rc = 2; continue
        time.sleep(5)
        model = requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]
        requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 16, "stream": False}, timeout=120)
        event(kind="container_ready", container_seq=seq, setting=setting, env=st_["env"], seconds_to_ready=st_.get("seconds_to_ready"),
              cache_config=metrics_cache_config(), wsl=wsl_state(), gpu_memory_windows=win_gpu_memory(), gpu=gpu(), image=ARMS["A2"]["image"], profile_id=ARMS["A2"]["profile"])
        tag = {"phase": a.phase, "container_seq": seq, "setting": setting}
        warm = C2.run_level(a, model, "A2", "R", 1, 20 if a.test else 120, os.path.join(pdir, name, "warmup", "R_c0001"), "main", log, {"warmup": True, **tag})
        for prof, n in CELLS:
            if warm["engine_dead"]:
                break
            g8 = G.gate(max_wait_s=0); event(kind="g8", container_seq=seq, profile=prof, concurrency=n, **g8)   # one 10 s attempt, recorded (see docstring)
            hg = HG.cell_start()
            mem0 = win_gpu_memory()
            rec = C2.run_level(a, model, "A2", prof, n, 20 if a.test else 60, os.path.join(pdir, name, f"{prof}_c{n:04d}"), "main", log,
                               {**tag, "g8_pass": g8["pass"], "gpu_memory_windows_start": mem0})
            event(kind="cell_end", container_seq=seq, profile=prof, concurrency=n, host=HG.cell_end(hg), gpu_memory_windows_end=win_gpu_memory(), engine_dead=rec["engine_dead"])
            ov = O.check(snap); event(kind="overwrite_check", container_seq=seq, **ov)
            if not ov["pass"]:
                rc = 4; break
            if rec["engine_dead"]:
                break
        event(kind="container_before_stop", container_seq=seq, wsl=wsl_state())
        C2.save_logs(name, logdir); stop(name)
        smi.terminate(); smi.wait(timeout=30); smi_f.close()
        event(kind="container_end", container_seq=seq, setting=setting, gpu_after_stop=gpu())
        if rc == 4:
            break
    sampler.stop_ev.set(); sampler.join(timeout=30)
    g6_after = manifest(G6_DIR)
    json.dump(g6_after, open(os.path.join(pdir, "g6_sha256_after.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
    event(kind="run_end", g6_unchanged=g6_before == g6_after, rc=rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
