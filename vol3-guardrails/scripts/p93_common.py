#!/usr/bin/env python3
"""P93 · shared definitions: paths, the seven judge arms, the pinned inputs, small helpers.

The study asks one question per arm: on fixed text, how much harmful content does this judge flag, how much harmless
content does it flag, and what does each verdict cost in time and output tokens. No answer is generated anywhere: every
judge reads the same stored text.

Text handling (the rule the whole harness is built around):
  - the test sets' text lives only in the process bucket (P93_BUCKET, outside version control);
  - files under results/ carry item ids, SHA-256 of the text, lengths, labels and verdicts, never text;
  - a judge's raw completion and its reasoning go to the bucket; results carry their SHA-256 and their sizes.

Arms. A NIM arm is judged through NeMo Guardrails' self-check actions with the Vol.1 rail prompts; an upstream-vLLM arm
is asked directly, in the request shape its model card gives.
  J0  Llama 3.1 8B Instruct, NIM 2.0.12 bf16      self-check prompt, max_tokens 3
  J1  the same                                      self-check prompt, Guardrails' default (1,024 tokens)
  J2  Nemotron 3 Nano, NIM 2.0.12 NVFP4            self-check prompt, reasoning on, 1,024 tokens
  J3  the same                                      reasoning off (chat_template_kwargs.enable_thinking false)
  J4  Nemotron 3.5 Content Safety, upstream vLLM   the model's own taxonomy template, reasoning off, 100 tokens
  J5  the same                                      reasoning on, 1,024 tokens
  J6  Llama 3.1 Nemotron Safety Guard 8B v3, upstream vLLM (not a NIM)   the model card's prompt, 100 tokens
  J4G / J5G  J4 / J5 through Guardrails' content-safety rail, configured as the library's own example for this model
"""
import hashlib, json, math, os, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
VOL = os.path.dirname(HERE)
REPO = os.path.dirname(VOL)
RESULTS = os.environ.get("P93_RESULTS") or os.path.join(VOL, "results", "p93_judges")   # P93_RESULTS: harness tests write elsewhere
BUCKET = os.environ.get("P93_BUCKET") or os.path.join(REPO, "_internal", "p93_bucket")
BASE = "http://127.0.0.1:8000"
CONTEXT = 8192
TEMPERATURE = 0.0
C1, C16 = 1, 16
SEED = 93

DATASETS = {
    "aegis2": {"hf": "nvidia/Aegis-AI-Content-Safety-Dataset-2.0", "revision": "d86bb8bedff51d25ac834ab7838f1cc61acb7a2c", "file": "test.json",
               "local": "aegis2_test.json", "sha256": "b0a6d602260524866053cb34105194f074f2c2906e3691b68d43b9e6e9318f35", "license": "CC-BY-4.0"},
    "xstest": {"hf": "Paul/XSTest", "revision": "f600c994b256f12867dfa5b3eb3d545a3e62f8b5", "file": "xstest_prompts.csv",
               "local": "xstest_prompts.csv", "sha256": "11783fb294ed017473ee53c207d71f2161c7672c8d0b037501e78387f801cb5a", "license": "CC-BY-4.0"},
    "vol1": {"file": "benchmark/e3_questions.json", "sha256": "5d7eeeaa9408977e28366e7b31a6f01905695a0c8ce10a6c314fa40de4a1c3ea", "license": "this repository"},
}

NIM_LLAMA = {"image": "nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12",
             "index_digest": "sha256:d2c94c1d654c3e80b8bc08cc83298d2ba4e219dff41d1092555795edb93c6545",
             "profile": "092ed4213624e774d24cdaf84e3b6222839bab2008a21d3c214ab46626366f90", "precision": "bf16",
             "env": {"NIM_MAX_MODEL_LEN": str(CONTEXT), "VLLM_USE_V2_MODEL_RUNNER": "0"}}
NIM_N3 = {"image": "nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12",
          "index_digest": "sha256:bd38d2d5438950b49427ee41944ee04f84cd38383265add8df2230480539e6f9",
          "profile": "1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada", "precision": "nvfp4",
          "env": {"NIM_MAX_MODEL_LEN": str(CONTEXT)}}
VLLM = {"image": "vllm/vllm-openai:v0.20.2", "digest": "sha256:70a098d90dbab428a001d9e852fc0fc8d67da5beb03e7851a22247653bf35923"}
HF_N35 = {"repo": "nvidia/Nemotron-3.5-Content-Safety", "revision": "35645ed3543b7e7ffaed2e788699e57a5051497c", "served": "nemotron-3.5-content-safety"}
HF_SG8 = {"repo": "nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3", "revision": "8fdc246ba3d56db9c469d534233b9f582d3afafa", "served": "llama-3.1-nemotron-safety-guard-8b-v3"}

# arm -> how it is served and how it is asked. `path`: guardrails_self_check | guardrails_content_safety | direct_lines | direct_json
ARMS = {
    "J0": {"judge": "Llama 3.1 8B Instruct", "engine": "nim", "serve": NIM_LLAMA, "path": "guardrails_self_check", "max_tokens": 3, "thinking": None},
    "J1": {"judge": "Llama 3.1 8B Instruct", "engine": "nim", "serve": NIM_LLAMA, "path": "guardrails_self_check", "max_tokens": None, "thinking": None},
    "J2": {"judge": "Nemotron 3 Nano", "engine": "nim", "serve": NIM_N3, "path": "guardrails_self_check", "max_tokens": 1024, "thinking": True},
    "J3": {"judge": "Nemotron 3 Nano", "engine": "nim", "serve": NIM_N3, "path": "guardrails_self_check", "max_tokens": 1024, "thinking": False},
    "J4": {"judge": "Nemotron 3.5 Content Safety", "engine": "vllm", "serve": HF_N35, "path": "direct_lines", "max_tokens": 100, "thinking": False},
    "J5": {"judge": "Nemotron 3.5 Content Safety", "engine": "vllm", "serve": HF_N35, "path": "direct_lines", "max_tokens": 1024, "thinking": True},
    "J6": {"judge": "Llama 3.1 Nemotron Safety Guard 8B v3", "engine": "vllm", "serve": HF_SG8, "path": "direct_json", "max_tokens": 100, "thinking": None},
    "J4G": {"judge": "Nemotron 3.5 Content Safety", "engine": "vllm", "serve": HF_N35, "path": "guardrails_content_safety", "max_tokens": 100, "thinking": False},
    "J5G": {"judge": "Nemotron 3.5 Content Safety", "engine": "vllm", "serve": HF_N35, "path": "guardrails_content_safety", "max_tokens": 1024, "thinking": True},
}
# arms that share one container: started once, their cells run one after another
CONTAINERS = [("llama_nim", ["J0", "J1"]), ("n3_nim", ["J2", "J3"]), ("n35_vllm", ["J4", "J5", "J4G", "J5G"]), ("sg8_vllm", ["J6"])]
TRACKS = ("input", "output")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_text(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def wilson(k, n, z=1.959963984540054):
    """Wilson 95% interval for k of n; (None, None) when n is 0."""
    if n == 0:
        return None, None
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def percentile(xs, q):
    """Nearest-rank percentile (q in 0..100) of a non-empty list; None for an empty one."""
    if not xs:
        return None
    s = sorted(xs); k = max(1, math.ceil(q / 100.0 * len(s)))
    return s[k - 1]


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def sh(args, timeout=120):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def gpu():
    r = sh(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,driver_version", "--format=csv,noheader,nounits"], timeout=30)
    u, t, ut, tp, p, drv = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
    return {"used_mib": int(u), "total_mib": int(t), "util_pct": int(ut), "temp_c": int(tp), "power_w": float(p), "driver": drv}
