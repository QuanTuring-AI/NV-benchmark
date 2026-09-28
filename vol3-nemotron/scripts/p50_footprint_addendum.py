#!/usr/bin/env python3
"""Footprint addendum: Nemotron 3 Nano (NVFP4) with the batch limit lowered.

The main footprint run found A2's lower bound set not by the KV cache but by the Mamba state cache: at a 0.725 budget
vLLM refused with "max_num_seqs (256) exceeds available Mamba cache blocks (146)". That bound belongs to a server
sized for 256 concurrent sequences. A single-user deployment reserves far less, so this addendum repeats the same
sweep with NIM_MAX_BATCH_SIZE=32 (the NIM 2.0.12 variable that sets vLLM max_num_seqs), everything else unchanged.
The bound harness p50_footprint.py is imported, not modified: the extra arm is injected here.
usage: p50_footprint_addendum.py --out DIR
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p50_footprint as fp  # noqa: E402

fp.ARMS["A2B32"] = dict(fp.ARMS["A2"], env={"NIM_MAX_MODEL_LEN": "4096", "NIM_MAX_BATCH_SIZE": "32"})
if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--arm", "A2B32"] + sys.argv[1:]
    raise SystemExit(fp.main())
