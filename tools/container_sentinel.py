#!/usr/bin/env python3
"""G9 container sentinel: is this container's GPU memory really on the card, and does it serve at its reference speed?

G8 only asks whether something else is using the GPU. It passed before every level on 2026-09-30 06:49-08:46 while the
same image, settings and AIPerf command ran 6-20x slower than on 2026-09-23 (P79). On this Windows host the GPU reaches
the containers through WSL's GPU path, and a container's allocations can end up in system memory instead of on the card:
the WSL kernel logs "dxgkio_make_resident: Ioctl failed: -12" (-12 is out of memory), and the Windows counter
"GPU Process Memory(pid_<vmwp>)\\Shared Usage" of the WSL VM process shows the part held in system memory. nvidia-smi
under WDDM does not see this (it does not show the desktop compositor's share either). Three layers:

  1 birth    after READY, before any cell: new make_resident failures since the launch baseline, and the container's
             shared (system-memory) usage against SYSMEM_MAX_GIB. RECORD ONLY, NOT A GATE: in P79 every one of 7 loads of
             Nemotron 3 Nano NIM 2.0.12 (T1 x3, T2 x3 after a reboot, and one voided T2 attempt) added exactly one failure
             and left 0.367 GiB in system memory, and all of them served at their reference speed
             (vol2-nemotron/results/p79_host_state/sentinel_replay.json). Used as a gate it would stop every good container.
  2 speed    a 30 s probe compared with the pre-registered reference: value <= SPEED_FACTOR x reference. Use a
             prefill-heavy probe (long input, c=1, TTFT p50): on 2026-09-30 the short-input c=1 ITL was within 10% of its
             reference (3.5 vs 3.2 ms) while the long-input c=1 TTFT was 20x (3,357 vs 156 ms). A short-input c=1 probe
             would have passed that morning.
  3 watch    around every cell: the same two signals again; a change during the cell marks it.
Plus the stop-time gate: no new cell once the stop time is reached (the morning deadline, HH:MM before noon).

The layer-1 limits were first drawn from two slow-looking starts on 2026-09-30 (09:23, 09:44); P79 then showed the same
signals on every normal start, so a layer-1 "fail" is kept as a record beside the speed probe, which is the gate.
usage (as a module): before = baseline(); ... READY ...; birth_check(before); speed_check(value, reference);
    watch(before_cell, after_cell); time_gate("08:00")
shell: python tools/container_sentinel.py baseline | snapshot | self_test
"""
import datetime, json, re, subprocess, sys

SYSMEM_MAX_GIB = 0.1
SPEED_FACTOR = 2.0
OTHER_DEDICATED_WARN_GIB = 1.2   # recorded only: the desktop compositor's commitment, not proven to be a cause
WSL_DISTRO = "docker-desktop"
MAKE_RESIDENT = re.compile(r"^\[\s*([\d.]+)\]\s+.*dxgkio_make_resident: Ioctl failed: (-?\d+)", re.M)
WIN_COUNTERS = r"""
$o=@()
(Get-Counter '\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage').CounterSamples | Where-Object { $_.CookedValue -gt 20MB } | ForEach-Object {
  if ($_.InstanceName -match 'pid_(\d+)') { $o += ('P|' + (Get-Process -Id $matches[1] -EA SilentlyContinue).ProcessName + '|' + ($_.Path.Split('\')[-1] -replace ' usage','') + '|' + [math]::Round($_.CookedValue/1GB,3)) } }
(Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage','\GPU Adapter Memory(*)\Shared Usage').CounterSamples | Where-Object { $_.CookedValue -gt 20MB } | ForEach-Object {
  $o += ('A|adapter|' + ($_.Path.Split('\')[-1] -replace ' usage','') + '|' + [math]::Round($_.CookedValue/1GB,3)) }
$o -join "`n"
"""


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def windows_gpu_memory():
    """GiB per 'process:dedicated|shared' and 'adapter:dedicated|shared' (processes above 20 MB)."""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", WIN_COUNTERS], capture_output=True, text=True,
                       encoding="mbcs", errors="replace", timeout=60)
    d = {}
    for line in r.stdout.splitlines():
        p = line.strip().split("|")
        if len(p) == 4:
            try:
                d[f"{p[1]}:{p[2]}"] = round(d.get(f"{p[1]}:{p[2]}", 0) + float(p[3]), 3)
            except ValueError:
                pass
    return d


def wsl_kernel():
    """make_resident failures in the WSL kernel log (seconds since the WSL VM start, error code), and the VM's uptime."""
    r = subprocess.run(["wsl", "-d", WSL_DISTRO, "-e", "sh", "-c", "dmesg 2>&1; echo '@@UPTIME'; cat /proc/uptime"],
                       capture_output=True, timeout=60)
    txt = r.stdout.decode("utf-8", "replace").replace("\x00", "")
    log, _, up = txt.partition("@@UPTIME")
    return {"make_resident_failures": [(float(s), int(c)) for s, c in MAKE_RESIDENT.findall(log)],
            "vm_uptime_s": float(up.split()[0]) if up.split() else None, "rc": r.returncode}


def snapshot():
    mem = windows_gpu_memory(); k = wsl_kernel()
    other = round(sum(v for key, v in mem.items() if key.endswith(":dedicated") and not key.startswith(("vmwp:", "adapter:"))), 3)
    return {"at": now(), "container_sysmem_gib": mem.get("vmwp:shared", 0.0), "container_dedicated_gib": mem.get("vmwp:dedicated", 0.0),
            "other_dedicated_gib": other, "make_resident_failures": len(k["make_resident_failures"]),
            "make_resident_detail": k["make_resident_failures"][-5:], "wsl_vm_uptime_s": k["vm_uptime_s"], "windows": mem}


def baseline():
    """Call before the container is launched."""
    return snapshot()


def _judge_birth(before, after, sysmem_max=SYSMEM_MAX_GIB):
    new_fail = after["make_resident_failures"] - before["make_resident_failures"]
    if after.get("wsl_vm_uptime_s") is not None and before.get("wsl_vm_uptime_s") is not None and after["wsl_vm_uptime_s"] < before["wsl_vm_uptime_s"]:
        new_fail = after["make_resident_failures"]           # the WSL VM restarted in between: every failure is new
    reasons = []
    if new_fail > 0:
        reasons.append(f"{new_fail} new make_resident failure(s) since the launch baseline")
    if after["container_sysmem_gib"] > sysmem_max:
        reasons.append(f"container shared (system-memory) usage {after['container_sysmem_gib']} GiB > {sysmem_max}")
    return {"layer": "birth", "record_only": True, "pass": not reasons, "reasons": reasons, "new_make_resident_failures": new_fail,
            "container_sysmem_gib": after["container_sysmem_gib"], "other_dedicated_gib": after["other_dedicated_gib"],
            "other_dedicated_over_warn": after["other_dedicated_gib"] > OTHER_DEDICATED_WARN_GIB,
            "rule": f"0 new make_resident failures and container shared <= {sysmem_max} GiB", "before": before, "after": after}


def birth_check(before):
    """Call after READY, before any cell. Record only (see the module docstring); gate on speed_check."""
    return _judge_birth(before, snapshot())


def speed_check(value, reference, factor=SPEED_FACTOR, what="", source=""):
    """Layer 2: value and reference in the same unit, lower is better (a latency)."""
    ok = value is not None and value <= factor * reference
    return {"layer": "speed", "pass": ok, "value": value, "reference": reference, "limit": round(factor * reference, 3),
            "rule": f"value <= {factor} x reference", "what": what, "reference_source": source}


def watch(before_cell, after_cell, sysmem_max=SYSMEM_MAX_GIB):
    """Layer 3: the two birth signals around one cell; a change marks the cell (it is kept and reported, not dropped)."""
    j = _judge_birth(before_cell, after_cell, sysmem_max)
    return {"layer": "watch", "marked": not j["pass"], "reasons": j["reasons"], "new_make_resident_failures": j["new_make_resident_failures"],
            "container_sysmem_gib": j["container_sysmem_gib"]}


def time_gate(stop_hhmm, at=None):
    """False once the stop time is reached. Stop times are morning deadlines: an evening start (hour >= 12) is before it."""
    t = at or datetime.datetime.now()
    return not (t.hour < 12 and t.strftime("%H:%M") >= stop_hhmm)


def self_test():
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want; ok &= good
        print(f"  {'PASS' if good else 'FAIL'} {name}: {got} (want {want})")
    snap = lambda shared, fails, up=1000.0: {"container_sysmem_gib": shared, "container_dedicated_gib": 30.6, "other_dedicated_gib": 8.4,  # noqa: E731
                                             "make_resident_failures": fails, "wsl_vm_uptime_s": up}
    # layer 1: positive control = P79 T1 container 1 (2026-09-30 09:41 baseline 1 failure; 09:47 READY 2 failures, shared 0.367)
    pc = _judge_birth(snap(0.0, 1, 1374.0), snap(0.367, 2, 1750.0))
    check("birth: positive control (P79 T1 container 1) fails", pc["pass"], False)
    check("birth: its two reasons", len(pc["reasons"]), 2)
    check("birth: clean start passes", _judge_birth(snap(0.0, 1), snap(0.0, 1, 1300.0))["pass"], True)
    check("birth: failure only", _judge_birth(snap(0.0, 1), snap(0.0, 2, 1300.0))["pass"], False)
    check("birth: shared only", _judge_birth(snap(0.0, 1), snap(0.2, 1, 1300.0))["pass"], False)
    check("birth: WSL restarted between (uptime went down) -> all failures are new", _judge_birth(snap(0.0, 3, 5000.0), snap(0.0, 1, 200.0))["new_make_resident_failures"], 1)
    # mutation: a shared limit of 1 GiB alone still fails the positive control on the failure count; with the failure
    # rule also broken (baseline taken after READY) the positive control passes -> the test notices the broken rule
    check("mutation: shared limit 1.0 -> positive control still fails", _judge_birth(snap(0.0, 1, 1374.0), snap(0.367, 2, 1750.0), sysmem_max=1.0)["pass"], False)
    check("mutation: baseline taken after READY and limit 1.0 -> positive control would pass (rule broken)",
          _judge_birth(snap(0.367, 2, 1750.0), snap(0.367, 2, 1750.0), sysmem_max=1.0)["pass"], True)
    # layer 2
    check("speed: this morning s256_R c=1 TTFT p50 3,356.9 ms vs 156 fails", speed_check(3356.9, 156.0)["pass"], False)
    check("speed: P55 R c=1 157.7 ms passes", speed_check(157.7, 156.0)["pass"], True)
    check("speed: short-input c=1 ITL 3.5 vs 3.2 ms passes (why the probe must be prefill-heavy)", speed_check(3.5, 3.2)["pass"], True)
    check("speed: missing value fails", speed_check(None, 156.0)["pass"], False)
    check("mutation: factor 50 -> this morning passes (rule broken)", speed_check(3356.9, 156.0, factor=50.0)["pass"], True)
    # layer 3
    check("watch: shared grows during a cell -> marked", watch(snap(0.0, 2), snap(0.4, 2, 1300.0))["marked"], True)
    check("watch: unchanged -> not marked", watch(snap(0.0, 2), snap(0.0, 2, 1300.0))["marked"], False)
    # stop-time gate
    d = datetime.datetime
    check("time: 07:59 before 08:00 -> open", time_gate("08:00", d(2026, 9, 30, 7, 59)), True)
    check("time: 08:00 -> closed", time_gate("08:00", d(2026, 9, 30, 8, 0)), False)
    check("time: 08:03 -> closed (the s256_R cells opened at 08:03-08:47 would not have started)", time_gate("08:00", d(2026, 9, 30, 8, 3)), False)
    check("time: 23:00 the evening before -> open", time_gate("08:00", d(2026, 9, 29, 23, 0)), True)
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    if cmd == "self_test":
        raise SystemExit(self_test())
    print(json.dumps(baseline() if cmd == "baseline" else snapshot(), ensure_ascii=False, indent=1))
