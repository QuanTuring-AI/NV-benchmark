#!/usr/bin/env python3
"""Vol.5 preparation: the smallest memory budget with which Nemotron 3 Nano (NVFP4, NIM 2.0.12) starts and answers,
at a context of 8,192 and of 16,384 tokens.

The method is the one of Vol.2's footprint harness (vol2-nemotron/scripts/p50_footprint.py), which is imported and not
modified, in the form of its second addendum: max_num_seqs 32 through NIM_PASSTHROUGH_ARGS. Only NIM_MAX_MODEL_LEN
changes between the Vol.2 arm (4,096) and the two arms here.

One thing differs from the Vol.2 sweep and is not absorbed: with --sweep-from the stepping down starts at a lower
budget than 0.85 (each start of this NIM takes six to seven minutes). The minimum that is found is the same kind of
figure; the levels above the starting point are not measured.

Written after the pre-registration of the session was frozen, as that file says; its SHA-256 goes into the events file
before its first container.
usage: nano_context_footprint.py --context 8192|16384 --out DIR [--sweep-from 0.80] [--only-default]
env: NGC_ENV_FILE (passed to --env-file, never read) · NIM_CACHE_DIR
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "vol2-nemotron", "scripts"))
import p50_footprint as fp  # noqa: E402

ARM = {8192: "A2S32C8K", 16384: "A2S32C16K"}
for ctx, name in ARM.items():
    fp.ARMS[name] = dict(fp.ARMS["A2"], env={"NIM_MAX_MODEL_LEN": str(ctx), "NIM_PASSTHROUGH_ARGS": "--max-num-seqs 32"})

if __name__ == "__main__":
    argv = sys.argv[1:]
    ctx = int(argv[argv.index("--context") + 1]); del argv[argv.index("--context"):argv.index("--context") + 2]
    if "--sweep-from" in argv:
        start = float(argv[argv.index("--sweep-from") + 1]); del argv[argv.index("--sweep-from"):argv.index("--sweep-from") + 2]
        fp.SWEEP = [s for s in fp.SWEEP if s <= start + 1e-9]
    sys.argv = [sys.argv[0], "--arm", ARM[ctx]] + argv
    raise SystemExit(fp.main())
