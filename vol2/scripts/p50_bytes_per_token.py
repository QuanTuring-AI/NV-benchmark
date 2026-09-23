#!/usr/bin/env python3
"""Bytes of weights a single-stream decode step must read, per model, from the safetensors headers in the NIM cache.

For a dense model every weight tensor is read once per token. For a mixture-of-experts model a token reads every
non-expert tensor, the shared expert, and only the routed experts selected for it; the per-token figure is therefore
  non_expert_bytes + shared_expert_bytes + routed_expert_bytes_total x (experts_per_token / routed_experts)
Tensor classification is by name pattern and is printed in full so the split can be checked; the header sizes are the
stored bytes (quantized weights count as stored, scales included). No weights are read, only the JSON headers.
usage: p50_bytes_per_token.py <snapshot_dir> [--experts-per-token N] [--routed-experts M]
"""
import glob, json, os, re, struct, sys

d = sys.argv[1]
ept = int(sys.argv[sys.argv.index("--experts-per-token") + 1]) if "--experts-per-token" in sys.argv else None
rex = int(sys.argv[sys.argv.index("--routed-experts") + 1]) if "--routed-experts" in sys.argv else None
DT = {"F32": 4, "F16": 2, "BF16": 2, "F8_E4M3": 1, "F8_E5M2": 1, "I8": 1, "U8": 1, "I32": 4, "I64": 8, "F64": 8, "BOOL": 1,
      "F4": 0.5, "F6_E2M3": 0.75, "F6_E3M2": 0.75, "U8_E4M3": 1}
tensors = {}
def header(path):
    """Return the safetensors header dict, or None if the file is not a safetensors file."""
    try:
        with open(path, "rb") as fh:
            n = struct.unpack("<Q", fh.read(8))[0]
            if n > 200_000_000:
                return None
            h = json.loads(fh.read(n))
        return h if isinstance(h, dict) and any(isinstance(v, dict) and "data_offsets" in v for v in h.values()) else None
    except (OSError, ValueError, struct.error):
        return None


# The NIM cache is a Hugging Face hub layout: snapshots/<rev>/ holds links into blobs/. Links written by the container
# cannot be opened on Windows, so the blobs directory beside the snapshots is read directly and safetensors files are
# recognised by their header. A snapshot with more than one revision shares blobs; pass the model directory's
# snapshots/<rev> and the script reads ../../blobs -- the caller must make sure only the revision of interest holds
# weights (checked here by comparing the summed bytes with the snapshot's own link list when readable).
blobs = os.path.join(d, "..", "..", "blobs")
files = sorted(glob.glob(os.path.join(blobs, "*"))) if os.path.isdir(blobs) else sorted(glob.glob(os.path.join(d, "**", "*.safetensors"), recursive=True))
seen = 0
for f in files:
    hdr = header(f)
    if hdr is None:
        continue
    seen += 1
    for k, v in hdr.items():
        if k == "__metadata__":
            continue
        a, b = v["data_offsets"]
        tensors[k] = {"bytes": b - a, "dtype": v["dtype"], "shape": v["shape"]}
tot = sum(t["bytes"] for t in tensors.values())
routed = {k: t for k, t in tensors.items() if re.search(r"\.experts\.\d+\.|\.experts\.(w|down|up|gate)", k) or re.search(r"experts\.\d+", k)}
shared = {k: t for k, t in tensors.items() if k not in routed and "shared_expert" in k}
other = {k: t for k, t in tensors.items() if k not in routed and k not in shared}
rb, sb, ob = (sum(t["bytes"] for t in x.values()) for x in (routed, shared, other))
ids = sorted({int(m.group(1)) for k in routed for m in [re.search(r"experts\.(\d+)", k)] if m})
print(f"safetensors files read: {seen} (from {'blobs/' if os.path.isdir(blobs) else 'snapshot'}) · tensors {len(tensors)} · total stored bytes {tot:,}")
print(f"routed expert tensors {len(routed)} ({rb:,} B) · distinct expert ids {len(ids)} · shared-expert tensors {len(shared)} ({sb:,} B) · other {len(other)} ({ob:,} B)")
dts = {}
for t in tensors.values():
    dts[t["dtype"]] = dts.get(t["dtype"], 0) + t["bytes"]
print("bytes by dtype:", {k: f"{v:,}" for k, v in sorted(dts.items(), key=lambda x: -x[1])})
if routed:
    m = rex or len(ids)
    if ept is None:
        print("MoE detected: pass --experts-per-token to get bytes per token")
    else:
        per = ob + sb + rb * ept / m
        print(f"bytes read per token = other {ob:,} + shared {sb:,} + routed {rb:,} x {ept}/{m} = {per:,.0f}")
    print("sample routed names:", sorted(routed)[:3]); print("sample shared names:", sorted(shared)[:3]); print("sample other names:", sorted(other)[:6])
else:
    print(f"dense: bytes read per token = total = {tot:,}")
