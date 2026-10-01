#!/usr/bin/env python3
"""Vol.2 · P78 · the engines the P78 harnesses start, one container on the card at a time, always on port 8000.

  N3     NIM 2.0.12 · Nemotron 3 Nano · NVFP4 profile (p50_footprint's A2 image and profile)
  N2     NIM 1.12.2 · Nemotron Nano 9B v2 · bf16 profile, NIM_MAX_NUM_SEQS 32 (A1)
  V3B1   upstream vllm/vllm-openai:v0.27.1 (the vLLM inside NIM 2.0.12) on the NVFP4 snapshot N3 serves, given the model
         path only ("bare")
  V3B2   the same image and snapshot with NIM's own vLLM argument list for N3's configuration, read from the NIM image's
         `nim-serve --dry-run` (P54's method): only the model path, the backend port, the host and NIM's own middleware
         modules are changed (they are NIM server-layer pieces); every other argument is passed as NIM resolves it
  V2N    upstream vllm/vllm-openai at the newest stable tag found on 2026-09-29 (v0.30.0) on the bf16 snapshot N2 serves
         (G5, the other deployment option for N2; pulled 2026-09-29, image id sha256:8a69ffad…)
The upstream arms mount the NIM cache read-only at NIM's own mount point, so both engines read the same files; they get
VLLM_NO_USAGE_STATS / DO_NOT_TRACK and a persistent inductor cache (P54's parity settings), listed apart from the counted
flags. For every upstream start the four settings that decide quality or speed silently on this model family are read
from the start log: mamba_ssm_cache_dtype, the MoE backend, the CUDA-graph mode and max_num_seqs.
env: NGC_ENV_FILE (NIM containers only, passed to --env-file, never read) · NIM_CACHE_DIR · V_CACHE_DIR
"""
import json, os, re, shlex, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
import sys; sys.path.insert(0, HERE)  # noqa: E401,E702
from p50_footprint import ARMS as FP_ARMS, BASE, LOG_PATTERNS, docker_logs, gpu, log_lines, now, sh, stop  # noqa: E402,F401

READY_TIMEOUT_S = 1800
N3_SNAPSHOT_REL = "ngc/hub/models--nim--nvidia--nemotron-3-nano/snapshots/hf-nvfp4-bd1ffb1"
N2_SNAPSHOT_REL = "ngc/hub/models--nim--nvidia--nvidia-nemotron-nano-9b-v2/snapshots/v1.2.2-ga"
MOUNT = "/opt/nim/.cache"
V_PRIVACY_ENV = {"VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1"}
V_PARITY_ENV = {"TORCHINDUCTOR_CACHE_DIR": "/root/.cache/torchinductor"}
IMAGES = {
    "N3": {"image": FP_ARMS["A2"]["image"], "index_digest": FP_ARMS["A2"]["index_digest"], "profile": FP_ARMS["A2"]["profile"], "precision": "nvfp4",
           "engine": "NIM 2.0.12 (vLLM 0.27.1)", "bytes_per_token": 3590938272, "base_env": {}},
    "N2": {"image": FP_ARMS["A1"]["image"], "index_digest": FP_ARMS["A1"]["index_digest"], "profile": FP_ARMS["A1"]["profile"], "precision": "bf16",
           "engine": "NIM 1.12.2", "bytes_per_token": 17776454656, "base_env": {"NIM_MAX_NUM_SEQS": "32"}},
    "V3B1": {"image": "vllm/vllm-openai:v0.27.1", "digest": "sha256:0a51ea5b4ae2dc5d81890e5173f54203d2a3ae0cfffe51b8fd2afd4391bfd967",
             "snapshot": MOUNT + "/" + N3_SNAPSHOT_REL, "precision": "nvfp4", "engine": "vLLM 0.27.1 (upstream image), bare", "bytes_per_token": 3590938272},
    "V3B2": {"image": "vllm/vllm-openai:v0.27.1", "digest": "sha256:0a51ea5b4ae2dc5d81890e5173f54203d2a3ae0cfffe51b8fd2afd4391bfd967",
             "snapshot": MOUNT + "/" + N3_SNAPSHOT_REL, "precision": "nvfp4", "engine": "vLLM 0.27.1 (upstream image), NIM's arguments", "bytes_per_token": 3590938272},
    "V2N": {"image": "vllm/vllm-openai:v0.30.0", "digest": "sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90", "snapshot": MOUNT + "/" + N2_SNAPSHOT_REL, "precision": "bf16",
            "engine": "vLLM 0.30.0 (upstream image)", "bytes_per_token": 17776454656},
}
# the four silent settings, read from an upstream start log (the value as the log states it, or None)
# (patterns fitted to vLLM 0.27.1's own start log on this host, 2026-09-29 harness test: it sets the Mamba cache dtype
#  itself -- "Updating mamba_ssm_cache_dtype to 'float32' for NemotronH model" -- and names the NVFP4 MoE backend it picks;
#  max_num_seqs is printed only when it is passed, so None there means vLLM's default)
TRAPS = {
    "mamba_ssm_cache_dtype": re.compile(r"mamba_ssm_cache_dtype(?:['\"]?\s*[:=]\s*| to )['\"]?([\w.]+)"),
    "moe_backend": re.compile(r"Using '?(\w+)'? \w* ?MoE backend"),
    "cudagraph_mode": re.compile(r"cudagraph_mode['\"]?\s*[:=]\s*['\"]?<?(?:CUDAGraphMode\.)?(\w+)"),
    "max_num_seqs": re.compile(r"max_num_seqs['\"]?\s*[:=]\s*(\d+)"),
    "attention_backend": re.compile(r"Using (\w+) attention backend"),
    "kv_cache_dtype": re.compile(r"kv_cache_dtype=torch\.(\w+)"),
}
EXC_LINE = re.compile(r"^\s*(?:\(\w+ pid=\d+\)\s*)?[\w.]*(?:Error|Exception): .*$", re.M)
ERR_LINE = re.compile(r"^\s*(?:\(\w+ pid=\d+\)\s*)?ERROR[:\s].*$", re.M)
CAPTURE = re.compile(r"Capturing CUDA graphs \(([^)]*)\):\s*100%\S*\s*(\d+)/(\d+)")


def first_error_line(text):
    m = EXC_LINE.search(text or "") or ERR_LINE.search(text or "")
    return m.group(0).strip()[:400] if m else None


def traps_from_log(text):
    out = {}
    for k, rx in TRAPS.items():
        m = rx.findall(text or "")
        out[k] = m[-1] if m else None
    return out


def _scrub(text):
    return "\n".join(l for l in (text or "").splitlines() if "nvapi" not in l.lower()) + "\n"


def launch(arm, name, logdir, env=None, args=None):
    """Start `arm` on port 8000 and wait for READY. NIM arms get the profile pin and their base env; upstream arms get the
    snapshot as the positional model path, then `args`."""
    im = IMAGES[arm]; env = dict(env or {}); args = list(args or [])
    cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "8000:8000"]
    if arm in ("N3", "N2"):
        full_env = {"NIM_MODEL_PROFILE": im["profile"], **im["base_env"], **env}
        cmd += ["--env-file", os.environ["NGC_ENV_FILE"]]
        tail = ["-v", f"{os.environ['NIM_CACHE_DIR']}:{MOUNT}", im["image"]]
    else:
        full_env = {**V_PRIVACY_ENV, **V_PARITY_ENV, **env}
        tail = ["-v", f"{os.environ['NIM_CACHE_DIR']}:{MOUNT}:ro", "-v", f"{os.environ['V_CACHE_DIR']}:/root/.cache", im["image"], im["snapshot"], *args]
    for k, v in full_env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += tail
    t0 = time.time()
    r = sh(cmd, timeout=180)
    if r.returncode != 0:
        return {"ready": False, "reason": "docker run failed", "first_error_line": first_error_line(r.stderr) or r.stderr.strip()[:400],
                "env": full_env, "args": args, "seconds_to_verdict": round(time.time() - t0, 1)}
    ready = False; reason = None
    while time.time() - t0 < READY_TIMEOUT_S:
        L = docker_logs(name)
        if re.search(r"Uvicorn running|Application startup complete", L):
            ready = True; break
        if re.search(LOG_PATTERNS["kv_refusal"], L):
            reason = "engine refused: KV cache within the budget cannot hold max_model_len"; break
        if not sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=30).stdout.strip():
            reason = "container exited"; break
        time.sleep(5)
    L = docker_logs(name)
    open(os.path.join(logdir, f"{name}.startup.log.txt"), "w", encoding="utf-8", newline="\n").write(_scrub(L))
    out = {"ready": ready, "env": full_env, "args": args, "log_lines": log_lines(L), "seconds_to_verdict": round(time.time() - t0, 1),
           "captured_graph_sizes": {k: int(n) for k, n, _ in CAPTURE.findall(L)}}
    if arm not in ("N3", "N2"):
        out["traps"] = traps_from_log(L)
    if not ready:
        out.update({"reason": reason or f"not ready within {READY_TIMEOUT_S}s", "first_error_line": first_error_line(L)})
    return out


def served_model():
    return requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]


def alive(model):
    try:
        r = requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1}, timeout=120)
        return r.status_code == 200
    except Exception:
        return False


def container_running(name):
    return bool(sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=30).stdout.strip())


def save_logs(name, logdir):
    L = docker_logs(name)
    open(os.path.join(logdir, f"{name}.container.log.txt"), "w", encoding="utf-8", newline="\n").write(_scrub(L))
    return L


# ---------------------------------------------------------------- NIM dry-run -> the upstream arm's argument list (P54's method)
def dryrun(arm, env, path):
    im = IMAGES[arm]
    cmd = ["docker", "run", "--rm", "--gpus", "all", "--env-file", os.environ["NGC_ENV_FILE"]]
    for k, v in {"NIM_MODEL_PROFILE": im["profile"], **im["base_env"], **env}.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += ["-v", f"{os.environ['NIM_CACHE_DIR']}:{MOUNT}", im["image"], "nim-serve", "--dry-run"]
    r = sh(cmd, timeout=900)
    txt = _scrub(r.stdout + r.stderr)
    open(path, "w", encoding="utf-8", newline="\n").write(txt)
    return {"rc": r.returncode, **parse_dryrun(txt)}


def parse_dryrun(txt):
    prof = re.search(r"^Selected profile:\s*([0-9a-f]{64})", txt, re.M)
    cfg = None
    m = re.search(r"Resolved Configuration \(JSON\)\n-+\n(\{.*?\n\})\n", txt, re.S)
    if m:
        try:
            cfg = json.loads(m.group(1))
        except json.JSONDecodeError:
            cfg = None
    args = None
    m = re.search(r"Backend Arguments\n-+\n(.*?)(?:\n\s*\n|\Z)", txt, re.S)
    if m:
        toks = shlex.split(m.group(1).replace("\\\n", " "))
        if len(toks) >= 2 and toks[1] == "serve":
            args = toks[2:]
    return {"selected_profile": prof.group(1) if prof else None, "resolved_config": cfg, "backend_args": args}


def upstream_args_from(backend_args, snapshot):
    """NIM's argument list -> the upstream arm's: model path -> the snapshot (passed positionally by launch()); backend
    port, host 127.0.0.1 and NIM's own middleware modules dropped; everything else verbatim. Returns (args, edits)."""
    out, edits, i = [], [], 0
    toks = list(backend_args)
    if toks and not toks[0].startswith("-"):
        edits.append({"model_path": [toks[0], snapshot]}); i = 1
    while i < len(toks):
        t = toks[i]
        if t == "--model" and i + 1 < len(toks):
            edits.append({"model_path": [toks[i + 1], snapshot]}); i += 2; continue
        if t == "--port" and i + 1 < len(toks):
            edits.append({"port_dropped": toks[i + 1]}); i += 2; continue
        if t.startswith("--port="):
            edits.append({"port_dropped": t.split("=", 1)[1]}); i += 1; continue
        if t == "--host" and i + 1 < len(toks):
            edits.append({"host_dropped": toks[i + 1]}); i += 2; continue
        if t == "--middleware" and i + 1 < len(toks) and toks[i + 1].startswith("nim_llm."):
            edits.append({"nim_middleware_dropped": toks[i + 1]}); i += 2; continue
        out.append(t); i += 1
    return out, edits


def self_test():
    """Offline: the dry-run parser and the argument translation on a synthetic dry-run text; the trap reader on synthetic
    log lines (positive: every value found; negative: a log without them gives None)."""
    txt = ("Selected profile: " + "a" * 64 + "\n\nBackend Arguments\n-----\n  vllm serve /opt/nim/workspace \\\n    --port 8001 --host 127.0.0.1 "
           "--max-model-len 16384 --middleware nim_llm.x.y --mamba_ssm_cache_dtype float32 --served-model-name nvidia/nemotron-3-nano\n\n")
    d = parse_dryrun(txt)
    args, edits = upstream_args_from(d["backend_args"], "/snap")
    ok1 = d["selected_profile"] == "a" * 64 and args == ["--max-model-len", "16384", "--mamba_ssm_cache_dtype", "float32", "--served-model-name", "nvidia/nemotron-3-nano"] and len(edits) == 4
    log = ("INFO 09-29 12:40:54 [config.py:676] Updating mamba_ssm_cache_dtype to 'float32' for NemotronH model\n"
           "INFO [nvfp4.py:285] Using 'FLASHINFER_CUTLASS' NvFp4 MoE backend out of potential backends: ['FLASHINFER_TRTLLM', 'MARLIN']\n"
           "INFO [cuda.py:482] Using FLASHINFER attention backend out of potential backends: ['FLASHINFER', 'TRITON_ATTN'].\n"
           "INFO config: ... compilation_config={'cudagraph_mode': <CUDAGraphMode.FULL_AND_PIECEWISE: (2, 1)>, ...}\n"
           "INFO non-default args: {'model': '/snap', 'max_num_seqs': 32}\nINFO FlashInfer resolved query dtypes: kv_cache_dtype=torch.float8_e4m3fn, arch=sm120\n")
    t = traps_from_log(log); t0 = traps_from_log("INFO nothing here\n")
    ok2 = (t["mamba_ssm_cache_dtype"] == "float32" and t["moe_backend"] == "FLASHINFER_CUTLASS" and t["cudagraph_mode"] == "FULL_AND_PIECEWISE"
           and t["max_num_seqs"] == "32" and t["attention_backend"] == "FLASHINFER" and t["kv_cache_dtype"] == "float8_e4m3fn" and all(v is None for v in t0.values()))
    return {"dryrun_parse_and_translate": ok1, "args": args, "edits": edits, "traps_positive_and_negative": ok2, "traps": t, "pass": ok1 and ok2}


if __name__ == "__main__":
    r = self_test(); print(json.dumps(r, indent=1)); raise SystemExit(0 if r["pass"] else 1)
