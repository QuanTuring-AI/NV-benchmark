#!/usr/bin/env python3
"""Footprint addendum 2: Nemotron 3 Nano (NVFP4) with vLLM max_num_seqs set to 32 through NIM_PASSTHROUGH_ARGS.

The first addendum set NIM_MAX_BATCH_SIZE=32 and the engine still resolved max_num_seqs to 256: in NIM 2.0.12
max_num_seqs is a per-profile engine argument, and the image's user-override path for engine arguments is
NIM_PASSTHROUGH_ARGS (nim_llm/config/system_config.py). This addendum passes "--max-num-seqs 32" through it and
repeats the same sweep. The bound harness p50_footprint.py is imported, not modified.
usage: p50_footprint_addendum2.py --out DIR
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p50_footprint as fp  # noqa: E402

fp.ARMS["A2S32"] = dict(fp.ARMS["A2"], env={"NIM_MAX_MODEL_LEN": "4096", "NIM_PASSTHROUGH_ARGS": "--max-num-seqs 32"})
if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--arm", "A2S32"] + sys.argv[1:]
    raise SystemExit(fp.main())
