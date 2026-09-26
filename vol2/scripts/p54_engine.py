#!/usr/bin/env python3
"""Vol.1-A revisit: one engine against itself. Llama 3.1 8B Instruct, bf16, on this card, served two ways from the same
weight files: arm N = the NIM container (NIM 2.0.12, which is built on vLLM v0.27.1) and arm V = the upstream vLLM
v0.27.1 container, pointed at the same snapshot in the NIM cache. Same model, same bytes, same precision, same card.

Subcommands (run in this order, one container on the card at a time):
  stack     zero GPU. Both images: id, repo digest, vLLM build commit and tag, OS, Python / vLLM / torch / CUDA and the
            versions of the libraries that decide kernels; the snapshot's file list with sizes and SHA-256 of every file
            both arms read. -> stack.json
  attempts  item B. Each arm walks a pre-registered ladder from zero flags, adding one step only after a failed start,
            until a start is READY and serves a probe request. Every attempt is one row of attempts.jsonl (time, arm,
            the flags passed, READY or failed with the first error line, seconds). Then the NIM dry-run of the measured
            configuration (the NIM image's own `nim-serve --dry-run`) is saved and parsed: its vLLM argument list is what
            arm V is given in the measured configuration (-> v_args.json), so the two arms run the same engine arguments
            by construction, not by hand. Nothing in that list is edited except the model path (NIM's workspace -> the
            snapshot the workspace points at) and the port (NIM's internal backend port -> 8000).
  single    item A, single stream. Blocks N, V, N, V on the 50 questions of the Vol.1-B sample, first two blocks on
            positions 0-24, last two on 25-49 (p50_speed's design); p53_answer's request (max_tokens 4096, temperature 0,
            top_p 0.9, stream with usage, 2 s between requests). Per block: READY, one discarded "Hello", three discarded
            questions from the sample's harness-test set, then the measured questions. Rows carry the labels the ticket
            lists (model, precision, engine and version, max_model_len, max_num_seqs, max_tokens). No response text.
  conc      item A, concurrency. p53_concurrency_v2's harness imported unchanged (AIPerf flags, profiles C and R, the
            discarded 120 s warm-up level, calibration after warm-up, engine-death detection, level durations, logs saved
            before removal); levels 1, 2, 4, ... 2S where S is the engine's max_num_seqs (vLLM's default on this card: no
            override on either arm); fresh container for the two highest levels. Order: C main N, C main V, R main N,
            R main V, then the fresh repeats in the same order.
usage: p54_engine.py {stack|attempts|single|conc} --out DIR [--aiperf EXE --tokenizer-root DIR] [--test] [--profiles C,R] [--levels ...]
env: NGC_ENV_FILE (passed to --env-file of arm N only, never read) · NIM_CACHE_DIR · V_CACHE_DIR (arm V's persistent cache)
"""
import argparse, hashlib, json, os, re, shlex, subprocess, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from p50_footprint import BASE, LOG_PATTERNS, docker_logs, gpu, log_lines, metrics_cache_config, now, sh, stop  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
QFILE = os.path.join(REPO, "benchmark", "questions.json")
SAMPLE = os.path.join(REPO, "vol1b", "results", "p20_coresidence", "sample.json")
READY_TIMEOUT_S = 1200

MODEL = "Llama 3.1 8B Instruct"
PRECISION = "bf16"
PROFILE = "092ed4213624e774d24cdaf84e3b6222839bab2008a21d3c214ab46626366f90"
SNAPSHOT_REL = "ngc/hub/models--nim--meta--llama-3.1-8b-instruct/snapshots/8c22764a7e3675c50d4c7c9a4edb474456022b16"
SNAPSHOT_IN = "/opt/nim/.cache/" + SNAPSHOT_REL          # the same path inside both containers (same mount point)
SERVED_NAME = "meta/llama-3.1-8b-instruct"              # NIM's served model id; arm V gets it from the dry-run argument list
IMAGES = {
    "N": {"image": "nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12",
          "digest": "sha256:d2c94c1d654c3e80b8bc08cc83298d2ba4e219dff41d1092555795edb93c6545", "engine": "NIM 2.0.12 (vLLM 0.27.1)"},
    "V": {"image": "vllm/vllm-openai:v0.27.1",
          "digest": "sha256:0a51ea5b4ae2dc5d81890e5173f54203d2a3ae0cfffe51b8fd2afd4391bfd967", "engine": "vLLM 0.27.1 (upstream image)"},
}
# Arm V never reports usage statistics to the vLLM project (the NIM image sets the same variable in its image env).
# Not needed for READY; passed on every V start and counted separately in attempts.jsonl.
V_PRIVACY_ENV = {"VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1"}
# Cache parity. The NIM image runs with HOME=/opt/nim, which is the mounted NIM cache, and its entrypoint sets
# TORCHINDUCTOR_CACHE_DIR=$HOME/.cache/torchinductor: compiled graphs, autotune results and kernels persist across starts.
# Arm V gets the same: a persistent host directory (env V_CACHE_DIR) mounted at its HOME cache (/root/.cache) and the
# same inductor variable. Not needed to start; passed on every V start and listed apart from the counted settings.
V_PARITY_ENV = {"TORCHINDUCTOR_CACHE_DIR": "/root/.cache/torchinductor"}
# B ladders, pre-registered. Each step is taken only if the previous start failed. The two ladders hold the same two
# settings in the same order: the context length NIM's own Vol.1-B configuration sets, then the model-runner switch that
# NIM 2.0.12 needed on this card in Vol.1-B.
LADDER = {
    "N": [{"env": {}, "args": []},
          {"env": {"NIM_MAX_MODEL_LEN": "8192"}, "args": []},
          {"env": {"NIM_MAX_MODEL_LEN": "8192", "VLLM_USE_V2_MODEL_RUNNER": "0"}, "args": []}],
    "V": [{"env": {}, "args": []},
          {"env": {}, "args": ["--max-model-len", "8192"]},
          {"env": {"VLLM_USE_V2_MODEL_RUNNER": "0"}, "args": ["--max-model-len", "8192"]}],
}
# The measured configuration of arm N: Vol.1-B's cell-4 configuration (the new Vol.1 baseline), profile pinned.
N_MEASURED_ENV = {"NIM_MODEL_PROFILE": PROFILE, "NIM_MAX_MODEL_LEN": "8192", "VLLM_USE_V2_MODEL_RUNNER": "0"}
# Environment variables of the NIM engine process that arm V receives too (the rest of the NIM image env is NIM's own
# server / nginx / cache settings or identical in both images; see stack.json).
V_MEASURED_ENV = {"VLLM_USE_V2_MODEL_RUNNER": "0"}
EXC_LINE = re.compile(r"^\s*(?:\(\w+ pid=\d+\)\s*)?[\w.]*(?:Error|Exception): .*$", re.M)
VLLM_DEFAULT_SEQS = 256
CAPTURE = re.compile(r"Capturing CUDA graphs \(([^)]*)\):\s*100%\S*\s*(\d+)/(\d+)")
ERR_LINE = re.compile(r"^\s*(?:\(\w+ pid=\d+\)\s*)?ERROR[:\s].*$", re.M)


def first_error_line(text):
    """The first line that states an exception ('XxxError: ...'), else the first ERROR log line, verbatim (trimmed), or None.
    Exceptions first: vLLM logs a generic 'EngineCore failed to start' ERROR line before the exception that caused it."""
    m = EXC_LINE.search(text or "") or ERR_LINE.search(text or "")
    return m.group(0).strip()[:400] if m else None


def launch(arm, name, env, args, logdir):
    """docker run for either arm on port 8000 with the NIM cache mounted at the same path; wait for READY."""
    im = IMAGES[arm]["image"]
    cmd = ["docker", "run", "-d", "--name", name, "--gpus", "all", "-p", "8000:8000"]
    if arm == "N":
        cmd += ["--env-file", os.environ["NGC_ENV_FILE"]]
        full_env = dict(env)
        cmd_tail = ["-v", f"{os.environ['NIM_CACHE_DIR']}:/opt/nim/.cache", im]
    else:
        full_env = {**V_PRIVACY_ENV, **V_PARITY_ENV, **env}
        cmd_tail = ["-v", f"{os.environ['NIM_CACHE_DIR']}:/opt/nim/.cache:ro", "-v", f"{os.environ['V_CACHE_DIR']}:/root/.cache", im, SNAPSHOT_IN, *args]
    for k, v in full_env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += cmd_tail
    t_launch = time.time()
    r = sh(cmd, timeout=120)
    if r.returncode != 0:
        return {"ready": False, "reason": "docker run failed", "first_error_line": first_error_line(r.stderr) or r.stderr.strip()[:400],
                "env": full_env, "args": args, "seconds_to_verdict": round(time.time() - t_launch, 1)}
    ready = False; reason = None
    while time.time() - t_launch < READY_TIMEOUT_S:
        L = docker_logs(name)
        if re.search(r"Uvicorn running|Application startup complete", L):
            ready = True; break
        if re.search(LOG_PATTERNS["kv_refusal"], L):
            reason = "engine refused: KV cache within the budget cannot hold max_model_len"; break
        if not sh(["docker", "ps", "-q", "--filter", f"name={name}"], timeout=30).stdout.strip():
            reason = "container exited"; break
        time.sleep(5)
    L = docker_logs(name)
    open(os.path.join(logdir, f"{name}.startup.log.txt"), "w", encoding="utf-8", newline="\n").write(
        "\n".join(l for l in L.splitlines() if "nvapi" not in l.lower()) + "\n")
    out = {"ready": ready, "env": full_env, "args": args, "log_lines": log_lines(L), "seconds_to_verdict": round(time.time() - t_launch, 1),
           "captured_graph_sizes": {k: int(n) for k, n, _ in CAPTURE.findall(L)}}
    if not ready:
        out.update({"reason": reason or f"not ready within {READY_TIMEOUT_S}s", "first_error_line": first_error_line(L)})
    return out


def probe(model):
    """One short request that must answer HTTP 200 with finish_reason stop: READY is not enough, the start must serve."""
    try:
        r = requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "What is 2 + 2? Answer with one number."}],
                                                                "max_tokens": 16, "temperature": 0.0, "stream": False}, timeout=300)
        j = r.json() if r.status_code == 200 else {}
        ch = (j.get("choices") or [{}])[0]
        return {"http_status": r.status_code, "finish_reason": ch.get("finish_reason"), "completion_tokens": (j.get("usage") or {}).get("completion_tokens"),
                "ok": r.status_code == 200 and ch.get("finish_reason") == "stop"}
    except Exception as e:
        return {"http_status": None, "error": str(e)[:300], "ok": False}


def served_model():
    return requests.get(BASE + "/v1/models", timeout=30).json()["data"][0]["id"]


def refuse_if_busy():
    if sh(["docker", "ps", "-q"], timeout=30).stdout.strip():
        sys.exit("refused: a container is running")


def check_digests():
    for arm, im in IMAGES.items():
        d = sh(["docker", "image", "inspect", im["image"], "--format", "{{.Id}} {{json .RepoDigests}}"], timeout=30).stdout
        if im["digest"].split(":")[1] not in d:
            sys.exit(f"DIGEST-MISMATCH {arm} {im['image']}: {d.strip()}")


# ---------------------------------------------------------------- stack (zero GPU)
def stack(a):
    out = {"at": now(), "images": {}, "snapshot": {}}
    for arm, im in IMAGES.items():
        rec = {"image": im["image"]}
        rec["id_and_digests"] = sh(["docker", "image", "inspect", im["image"], "--format", "{{.Id}} {{json .RepoDigests}} {{.Created}}"], timeout=30).stdout.strip()
        envs = json.loads(sh(["docker", "image", "inspect", im["image"], "--format", "{{json .Config.Env}}"], timeout=30).stdout)
        rec["image_env_vllm_cuda"] = sorted(e for e in envs if e.startswith(("VLLM_", "CUDA_VERSION", "TORCH_CUDA_ARCH", "NIM_MODEL_NAME")))
        py = "/opt/nim/.venv/bin/python" if arm == "N" else "python3"
        script = ("import sys,importlib.metadata as m\n"
                  "print('PY', sys.version.split()[0])\n"
                  "import vllm, torch\n"
                  "print('VLLM', vllm.__version__, vllm.__file__)\n"
                  "print('TORCH', torch.__version__, torch.version.cuda)\n"
                  "for p in ('flashinfer-python','flashinfer-cubin','flashinfer-jit-cache','triton','transformers','nvidia-cublas','nvidia-cudnn-cu13','nvidia-nccl-cu13','xgrammar'):\n"
                  "    try: print('PKG', p, m.version(p))\n"
                  "    except Exception: print('PKG', p, None)\n")
        r = sh(["docker", "run", "--rm", "--entrypoint", "sh", im["image"], "-c", f"head -2 /etc/os-release; {py} -c \"$0\"", script], timeout=300)
        rec["probe_stdout"] = [l for l in r.stdout.splitlines() if l.strip()]
        rec["probe_rc"] = r.returncode
        out["images"][arm] = rec
    # The snapshot's entries are links into ../../blobs written inside a container; Windows cannot open them. They are
    # hashed inside a container instead, through the same read-only mount point both arms use, so the record is of the
    # bytes as the engines see them (links followed; the link target is recorded beside each file).
    script = ('cd "$0" && find -L . -type f | sort | while read -r f; do '
              'printf "%s\t%s\t%s\t%s\n" "$f" "$(stat -L -c %s "$f")" "$(sha256sum < "$f" | cut -d" " -f1)" "$(readlink "$f")"; done')
    r = sh(["docker", "run", "--rm", "--entrypoint", "sh", "-v", f"{os.environ['NIM_CACHE_DIR']}:/opt/nim/.cache:ro", IMAGES["V"]["image"],
            "-c", script, SNAPSHOT_IN], timeout=1800)
    files = []
    for line in r.stdout.splitlines():
        parts = line.split("	")
        if len(parts) == 4:
            files.append({"path": parts[0][2:] if parts[0].startswith("./") else parts[0], "bytes": int(parts[1]), "sha256": parts[2], "link_target": parts[3] or None})
            print("  hashed", files[-1]["path"], files[-1]["bytes"], flush=True)
    if r.returncode != 0 or not files:
        sys.exit(f"snapshot hashing failed rc={r.returncode}: {r.stderr[-400:]}")
    out["snapshot"] = {"path_in_both_containers": SNAPSHOT_IN, "files": files}
    json.dump(out, open(os.path.join(a.out, "stack.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return 0


# ---------------------------------------------------------------- dry-run of arm N (the NIM image resolves its own config)
def dryrun(env, path):
    cmd = ["docker", "run", "--rm", "--gpus", "all", "--env-file", os.environ["NGC_ENV_FILE"]]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += ["-v", f"{os.environ['NIM_CACHE_DIR']}:/opt/nim/.cache", IMAGES["N"]["image"], "nim-serve", "--dry-run"]
    r = sh(cmd, timeout=900)
    txt = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "nvapi" not in l.lower())
    open(path, "w", encoding="utf-8", newline="\n").write(txt + "\n")
    return {"rc": r.returncode, **parse_dryrun(txt)}


def parse_dryrun(txt):
    """Selected profile, the resolved-configuration JSON, and the backend argument list as NIM prints it:
    '  vllm serve <arg> \\\\\\n    <arg> ...' under the 'Backend Arguments' header."""
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
        body = m.group(1).replace("\\\n", " ")
        toks = shlex.split(body)
        if len(toks) >= 2 and toks[1] == "serve":
            args = toks[2:]
    return {"selected_profile": prof.group(1) if prof else None, "resolved_config": cfg, "backend_args": args}


def v_args_from(backend_args):
    """NIM's vLLM argument list -> arm V's: model path -> the snapshot; '--port <backend>' and '--host 127.0.0.1' dropped
    (V listens on 8000 on all interfaces, vLLM's defaults, as NIM's nginx does); '--middleware nim_llm.*' dropped (NIM's
    own server-layer modules, absent from the upstream image); everything else verbatim. Returns (args, edits)."""
    out, edits, i = [], [], 0
    toks = list(backend_args)
    if toks and not toks[0].startswith("-"):
        edits.append({"model_path": [toks[0], SNAPSHOT_IN]}); out.append(SNAPSHOT_IN); i = 1
    while i < len(toks):
        t = toks[i]
        if t in ("--model",) and i + 1 < len(toks):
            edits.append({"model_path": [toks[i + 1], SNAPSHOT_IN]}); out += [t, SNAPSHOT_IN]; i += 2; continue
        if t == "--port" and i + 1 < len(toks):
            edits.append({"port_dropped": toks[i + 1]}); i += 2; continue
        if t.startswith("--port="):
            edits.append({"port_dropped": t.split("=", 1)[1]}); i += 1; continue
        if t == "--host" and i + 1 < len(toks):
            edits.append({"host_dropped": toks[i + 1]}); i += 2; continue
        if t == "--middleware" and i + 1 < len(toks) and toks[i + 1].startswith("nim_llm."):
            # NIM's own ASGI middlewares (redirect, request id): NIM server-layer modules, not present in the upstream image
            edits.append({"nim_middleware_dropped": toks[i + 1]}); i += 2; continue
        out.append(t); i += 1
    if out and out[0] == SNAPSHOT_IN:
        out = out[1:]       # launch() passes the model path as the positional argument
    return out, edits


def attempts(a):
    refuse_if_busy(); check_digests()
    logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    af = open(os.path.join(a.out, "attempts.jsonl"), "a", encoding="utf-8", newline="\n")
    # which profile would NIM choose with nothing set? If it is the target, the ladder starts with zero variables;
    # otherwise the profile pin is part of every step and is counted (it is how NIM is told which weights to serve).
    d0 = dryrun({}, os.path.join(logdir, "dryrun_N_zero.txt"))
    pin = {} if d0.get("selected_profile") == PROFILE else {"NIM_MODEL_PROFILE": PROFILE}
    af.write(json.dumps({"kind": "dryrun", "arm": "N", "at": now(), "env": {}, "selected_profile": d0.get("selected_profile"),
                         "profile_pin_needed": bool(pin), "rc": d0.get("rc")}, ensure_ascii=False) + "\n"); af.flush()
    summary = {}
    for arm in ("N", "V"):
        summary[arm] = None
        for k, step in enumerate(LADDER[arm]):
            env = {**(pin if arm == "N" else {}), **step["env"]}
            name = f"p54-attempt-{arm.lower()}{k}"
            t0 = now(); before = gpu()
            st_ = launch(arm, name, env, step["args"], logdir)
            pr = None
            if st_["ready"]:
                time.sleep(5)
                try:
                    pr = probe(served_model())
                except Exception as e:
                    pr = {"ok": False, "error": str(e)[:300]}
            cc = metrics_cache_config() if st_["ready"] else None
            stop(name)
            flags = [f"{k2}={v2}" for k2, v2 in env.items()] + step["args"]
            row = {"kind": "start", "arm": arm, "step": k, "at": t0, "image": IMAGES[arm]["image"], "flags": flags, "flag_count": len(flags),
                   "not_counted": {**V_PRIVACY_ENV, **V_PARITY_ENV, "mount": "V_CACHE_DIR -> /root/.cache"} if arm == "V" else None,
                   "result": "READY" if (st_["ready"] and pr and pr.get("ok")) else ("READY, probe failed" if st_["ready"] else "failed"),
                   "reason": st_.get("reason"), "first_error_line": st_.get("first_error_line"), "seconds": st_["seconds_to_verdict"],
                   "probe": pr, "cache_config": cc, "gpu_before": before, "log": f"logs/{name}.startup.log.txt"}
            af.write(json.dumps(row, ensure_ascii=False) + "\n"); af.flush()
            print(f"  {arm} step {k} flags={flags} -> {row['result']} ({row['seconds']} s) {row['first_error_line'] or ''}", flush=True)
            if row["result"] == "READY":
                summary[arm] = {"step": k, "flags": flags}; break
    # the measured configuration: NIM's dry-run of it, and arm V's argument list derived from it
    dm = dryrun(N_MEASURED_ENV, os.path.join(logdir, "dryrun_N_measured.txt"))
    vargs, edits = v_args_from(dm["backend_args"] or [])
    rec = {"at": now(), "n_env": N_MEASURED_ENV, "n_dryrun_rc": dm["rc"], "n_selected_profile": dm["selected_profile"],
           "n_backend_args": dm["backend_args"], "v_args": vargs, "v_edits": edits, "v_env": V_MEASURED_ENV, "v_privacy_env": V_PRIVACY_ENV, "v_parity_env": V_PARITY_ENV,
           "n_resolved_config": dm["resolved_config"], "ladder_result": summary}
    json.dump(rec, open(os.path.join(a.out, "v_args.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print("  N backend args:", dm["backend_args"]); print("  V args:", vargs, "edits:", edits)
    return 0 if dm["backend_args"] else 3


def measured(a):
    """(env, args) per arm for the measured configuration; V's from v_args.json written by `attempts`."""
    p = os.path.join(a.vargs or os.path.join(a.out, "v_args.json"))
    rec = json.load(open(p, encoding="utf-8"))
    if not rec.get("n_backend_args"):
        sys.exit("v_args.json has no NIM backend argument list")
    return {"N": (N_MEASURED_ENV, []), "V": (V_MEASURED_ENV, rec["v_args"])}, rec


def labels(arm, seqs, max_tokens, mml):
    return {"model": MODEL, "precision": PRECISION, "engine": IMAGES[arm]["engine"], "image": IMAGES[arm]["image"],
            "max_model_len": mml, "max_num_seqs": seqs, "max_tokens": max_tokens}


def effective(rec):
    """max_model_len and max_num_seqs of the measured configuration, from NIM's resolved configuration (the only
    place that records max_num_seqs before the engine runs); None where the dry-run does not state it."""
    cfg = ((rec.get("n_resolved_config") or {}).get("config")) or {}
    g = lambda k: (cfg.get(k) or {}).get("value")
    args = rec.get("n_backend_args") or []

    def arg(flag):
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None
    mml = arg("--max-model-len") or g("max_model_len")
    seqs = arg("--max-num-seqs") or g("max_num_seqs")
    # Neither NIM's argument list nor its resolved configuration sets max_num_seqs for this model: both arms then run
    # vLLM's own default, 256 on a card under 70 GiB (vllm/engine/arg_utils.py, OPENAI_API_SERVER). The startup log's
    # decode CUDA-graph count checks it per container (35 sizes = capture up to 256).
    return (int(mml) if mml else None), (int(seqs) if seqs else VLLM_DEFAULT_SEQS)


# ---------------------------------------------------------------- single stream
def single(a):
    from p53_answer import MAX_TOKENS, request as answer_request   # p53_answer's request, unchanged (max_tokens 4096)
    from p50_speed import COOLDOWN
    refuse_if_busy(); check_digests()
    cfgs, rec = measured(a)
    mml, seqs = effective(rec)
    logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    req_f = open(os.path.join(a.out, "requests.jsonl"), "a", encoding="utf-8", newline="\n")
    ev_f = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")

    def event(**kw):
        kw["at"] = now(); ev_f.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev_f.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "block", "at")}, flush=True)
    s = json.load(open(SAMPLE, encoding="utf-8"))
    bank = {q["id"]: q for q in json.load(open(QFILE, encoding="utf-8"))}
    ids = [x["id"] for x in (s["harness_test_questions"] if a.test else s["run_order"])]
    warm_ids = [x["id"] for x in s["harness_test_questions"]][:3]
    order = [(i, bank[x]) for i, x in enumerate(ids)]
    half = (len(order) + 1) // 2
    for b, (arm, h) in enumerate([("N", 0), ("V", 0), ("N", 1), ("V", 1)]):
        part = order[:half] if h == 0 else order[half:]
        name = f"p54-single-{arm.lower()}-b{b}"
        env, args = cfgs[arm]
        before = gpu()
        st_ = launch(arm, name, env, args, logdir)
        if not st_["ready"]:
            event(kind="block_failed", arm=arm, block=b, reason=st_.get("reason"), first_error_line=st_.get("first_error_line"))
            stop(name); continue
        time.sleep(5)
        model = served_model(); cc = metrics_cache_config()
        warm = [answer_request(model, "Hello", 16)] + [answer_request(model, bank[q]["text"], 256) for q in warm_ids]
        event(kind="block_start", arm=arm, block=b, half=h, image=IMAGES[arm]["image"], env=st_["env"], args=st_["args"],
              gpu_before_launch=before, gpu_ready=gpu(), seconds_to_ready=st_["seconds_to_verdict"], log_lines=st_["log_lines"],
              cache_config=cc, captured_graph_sizes=st_["captured_graph_sizes"], served_model=model, labels=labels(arm, seqs, MAX_TOKENS, mml),
              warmup=[{k: w.get(k) for k in ("ttft_ms", "total_latency_ms", "completion_tokens", "finish_reason", "http_status", "error")} for w in warm])
        time.sleep(COOLDOWN)
        for pos, q in part:
            gb = gpu(); at = now()
            r = answer_request(model, q["text"])
            r.update({"arm": arm, "block": b, "pos": pos, "question_id": q["id"], "category": q["category"], "at": at, "served_model": model,
                      **labels(arm, seqs, MAX_TOKENS, mml), "gpu_before": gb, "gpu_after": gpu(),
                      "docker_ps_before": sh(["docker", "ps", "--format", "{{.Names}}"], timeout=30).stdout.split()})
            req_f.write(json.dumps(r, ensure_ascii=False) + "\n"); req_f.flush()
            print(f"  {arm} b{b} {q['id']} ttft {r.get('ttft_ms')} total {r.get('total_latency_ms')} ct {r.get('completion_tokens')} {r.get('finish_reason')} {r.get('error', '')}", flush=True)
            time.sleep(COOLDOWN)
        saved = save_container_log(name, logdir)
        stop(name)
        event(kind="block_end", arm=arm, block=b, gpu_after_stop=gpu(), container_log=saved)
    return 0


def save_container_log(name, logdir):
    from p53_concurrency_v2 import save_logs
    return save_logs(name, logdir)


# ---------------------------------------------------------------- concurrency
def ladder(seqs):
    lv, n = [], 1
    while n <= 2 * seqs:
        lv.append(n); n *= 2
    return lv


def conc(a):
    from p53_concurrency_v2 import calibrate, run_level, save_logs, sweep
    refuse_if_busy(); check_digests()
    cfgs, rec = measured(a)
    mml, seqs = effective(rec)
    seqs_for_ladder = seqs
    levels = [int(x) for x in a.levels.split(",")] if a.levels else ladder(seqs_for_ladder)
    first_duration = 20 if a.test else 60
    warm_duration = 20 if a.test else 120
    logdir = os.path.join(a.out, "logs"); os.makedirs(logdir, exist_ok=True)
    log = open(os.path.join(a.out, "levels.jsonl"), "a", encoding="utf-8", newline="\n")
    ev = open(os.path.join(a.out, "events.jsonl"), "a", encoding="utf-8", newline="\n")

    def event(**kw):
        kw["at"] = now(); ev.write(json.dumps(kw, ensure_ascii=False) + "\n"); ev.flush()
        print("  event", {k: kw[k] for k in kw if k in ("kind", "arm", "profile", "container", "at")}, flush=True)
    profs = a.profiles.split(",")
    plan = [(p, arm, "main", levels) for p in profs for arm in ("N", "V")]
    if not a.test:
        plan += [(p, arm, "fresh", levels[-2:]) for p in profs for arm in ("N", "V")]
    for prof, arm, tag, lv in plan:
        name = f"p54-conc-{arm.lower()}-{prof.lower()}-{tag}"
        env, args = cfgs[arm]
        st_ = launch(arm, name, env, args, logdir)
        if not st_["ready"]:
            event(kind="container_failed", arm=arm, profile=prof, container=tag, reason=st_.get("reason"), first_error_line=st_.get("first_error_line"))
            save_logs(name, logdir); stop(name); continue
        time.sleep(5)
        model = served_model(); cc = metrics_cache_config()
        requests.post(BASE + "/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 16, "stream": False}, timeout=120)
        warm = run_level(a, model, arm, prof, 1, warm_duration, os.path.join(a.out, f"{arm}_{prof}_{tag}", "warmup", "c0001"), tag, log, {"warmup": True})
        cal = calibrate(model, prof) if (tag == "main" and not warm["engine_dead"]) else None
        env_rec = dict(st_["env"])
        if arm == "V":
            env_rec["VLLM_ARGS"] = " ".join(args)
        event(kind="container_start", arm=arm, profile=prof, container=tag, levels=lv, image=IMAGES[arm]["image"], env=env_rec,
              labels=labels(arm, seqs, None, mml), seconds_to_ready=st_["seconds_to_verdict"], gpu_ready=gpu(), cache_config=cc,
              captured_graph_sizes=st_["captured_graph_sizes"],
              log_lines=st_["log_lines"], served_model=model, warmup_level={k: warm.get(k) for k in ("rc", "completed", "engine_dead", "summary")}, calibration=cal)
        if not warm["engine_dead"]:
            sweep(a, arm, prof, model, lv, tag, log, first_duration)
        saved = save_logs(name, logdir)
        stop(name)
        event(kind="container_end", arm=arm, profile=prof, container=tag, gpu_after_stop=gpu(), container_log=saved)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("stack", "attempts", "single", "conc"))
    ap.add_argument("--out", required=True); ap.add_argument("--vargs", default=None)
    ap.add_argument("--aiperf"); ap.add_argument("--tokenizer-root"); ap.add_argument("--profiles", default="C,R")
    ap.add_argument("--levels", default=""); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    return {"stack": stack, "attempts": attempts, "single": single, "conc": conc}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
