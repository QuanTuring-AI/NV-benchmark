#!/usr/bin/env python3
"""Vol.4 · the steps of run_step.py for the concurrency sweep, with that program imported unchanged.

run_step.py is bound by the pre-registration of the first session. This wrapper sets, before any step runs:
  the container prefix and the network name   (environment VOL4_PREFIX, VOL4_NET; defaults p128_ and p128net)
  the image of the client container           (environment VOL4_CLIENT_IMAGE; default: the one of run_step.py)
  the results folder                          (environment VOL4_RESULTS, read by run_step.py itself)
Everything else (the gate, the start and stop of a NIM, the client container, the event log) is run_step.py's code.

usage: the same as run_step.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_step  # noqa: E402

run_step.PREFIX = os.environ.get("VOL4_PREFIX", "p128_")
run_step.NET = os.environ.get("VOL4_NET", "p128net")
run_step.CLIENT_IMAGE = os.environ.get("VOL4_CLIENT_IMAGE", run_step.CLIENT_IMAGE)

if __name__ == "__main__":
    sys.exit(run_step.main())
