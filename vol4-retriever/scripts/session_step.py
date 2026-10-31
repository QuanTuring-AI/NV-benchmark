#!/usr/bin/env python3
"""Vol.4 · the steps of run_step.py for a later session, with that program imported unchanged.

run_step.py is bound by the pre-registration of the first session and names its containers and its Docker network after
that session. This wrapper sets, before any step runs:
  the container prefix and the network name   (environment VOL4_PREFIX, VOL4_NET; defaults p110_ and p110net)
  the results folder                          (environment VOL4_RESULTS, read by run_step.py itself)
  extra arguments of `docker run` for a NIM   (environment VOL4_DOCKER_ARGS, split on spaces; for example --pid=host)
Everything else — the gate, the start and stop of a NIM, the client container, the event log — is run_step.py's code.

usage: the same as run_step.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_step  # noqa: E402

run_step.PREFIX = os.environ.get("VOL4_PREFIX", "p110_")
run_step.NET = os.environ.get("VOL4_NET", "p110net")
EXTRA = [x for x in os.environ.get("VOL4_DOCKER_ARGS", "").split(" ") if x]
_sh = run_step.sh


def sh(cmd, timeout=600, env=None):
    if EXTRA and cmd[:3] == ["docker", "run", "-d"] and "--gpus" in cmd:
        cmd = cmd[:3] + EXTRA + cmd[3:]
        run_step.event(kind="docker_run_extra_arguments", arguments=EXTRA)
    return _sh(cmd, timeout=timeout, env=env)


run_step.sh = sh

if __name__ == "__main__":
    sys.exit(run_step.main())
