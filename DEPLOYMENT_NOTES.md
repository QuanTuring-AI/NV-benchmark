# Deployment Notes: NIM 1.13.1 on RTX 5090 (Windows + Docker)

Real-world blockers and fixes encountered during our E1/E2 benchmark setup.
Every issue below wasted at least 30 minutes — don't repeat them.

---

## 1. NIM Version: Use 1.13.1, NOT latest

**Problem:** NIM 2.0.1 (latest) requires CUDA 13.0.

```
nvidia-container-cli: requirement error: unsatisfied condition: cuda>=13.0, please update your driver to a newer version
```

RTX 5090 with driver 577.00 supports CUDA 12.9. That's not enough for NIM ≥1.15.0.

**Fix:** Pin to 1.13.1:

```bash
docker pull nvcr.io/nim/meta/llama-3.1-8b-instruct:1.13.1
```

**Version matrix:**

| NIM Version | Min CUDA | Works on RTX 5090 (CUDA 12.9) |
|-------------|----------|-------------------------------|
| 2.0.1       | 13.0     | No                            |
| 1.15.0      | 13.0     | No                            |
| 1.13.1      | 12.x     | **Yes**                       |
| 1.8.3       | 12.x     | Partially (TensorRT hangs)    |

---

## 2. TensorRT Profile Hangs on RTX 5090 — Force vLLM Profile

**Problem:** NIM 1.8.3 auto-selects a TensorRT-LLM profile for RTX 5090 (sm_120). The container starts but freezes at 0% CPU / 0MB memory — no error, no progress, forever.

Root cause: RTX 5090 uses CUDA compute capability sm_120 (Blackwell). TensorRT-LLM profile compilation for sm_120 either hangs or is unsupported in early NIM versions.

**Fix in NIM 1.13.1:** Force the vLLM profile using the exact profile hash:

```bash
docker run -d --name nim-llama \
  --gpus all -p 8000:8000 \
  -e "NGC_API_KEY=your_key_here" \
  -e "NIM_MODEL_PROFILE=4f904d571fe60ff24695b5ee2aa42da58cb460787a968f1e8a09f5a7e862728d" \
  nvcr.io/nim/meta/llama-3.1-8b-instruct:1.13.1
```

To find available profiles for your GPU:

```bash
docker run --rm --gpus all \
  -e "NGC_API_KEY=your_key_here" \
  nvcr.io/nim/meta/llama-3.1-8b-instruct:1.13.1 \
  list-model-profiles
```

Look for a profile with `backend: vllm` and `precision: bf16`. Avoid any profile marked `tensorrt_llm` if on RTX 5090.

> Note: `NIM_MANIFEST_PROFILE=vllm-bf16-tp1` (the human-readable name) does NOT work — you must use the full hash.

---

## 3. KV Cache OOM — Set `NIM_MAX_MODEL_LEN=8192`

**Problem:** NIM starts but crashes during model loading:

```
ValueError: To serve at least one request with max_seq_len (131072),
16.00 GiB KV cache is needed, only 10.62 GiB available.
```

Default `max_model_len=131072` (128K context) requires 16GB just for KV cache. After loading the BF16 model weights (~16GB), only ~10.6GB remains — not enough.

**Fix:** Cap the context window at 8192 tokens (sufficient for 99% of use cases):

```bash
-e "NIM_MAX_MODEL_LEN=8192"
```

**VRAM math (RTX 5090 32GB):**

| Component | VRAM |
|-----------|------|
| Llama 3.1 8B BF16 weights | ~16 GB |
| CUDA runtime + overhead | ~4 GB |
| Available for KV cache | ~12 GB |
| KV cache @ max_model_len=8192 | ~1.5 GB |
| KV cache @ max_model_len=131072 | ~16 GB (fails) |

---

## 4. NGC API Key — No Space After `=`

**Problem:** Authentication silently fails or gives generic errors.

**Root cause:** In PowerShell, copy-pasting `-e "NGC_API_KEY= nvapi-..."` with a space after `=` passes a key starting with a space character. NGC rejects this but the error message is misleading.

**Fix:** Ensure zero whitespace:

```powershell
# WRONG:
-e "NGC_API_KEY= nvapi-xxxxx"

# CORRECT:
-e "NGC_API_KEY=nvapi-xxxxx"
```

Also: NGC API keys require license acceptance on the model catalog page before use. Visit the model page and click "Accept License" in your browser before attempting to pull. The error message is:

```
Please accept license on the browser to be able to download
```

---

## 5. Windows PowerShell — Single-Line Commands Only

**Problem:** Multi-line Docker commands with backslash continuation fail in PowerShell:

```
-e: The term '-e' is not recognized as the name of a cmdlet...
```

PowerShell does not support bash-style `\` line continuation for arguments.

**Fix:** Write as a single line, or use a `.ps1` script file.

```powershell
# WRONG (PowerShell):
docker run -d --name nim-llama `
  --gpus all -p 8000:8000 `
  -e "NGC_API_KEY=xxx"

# CORRECT:
docker run -d --name nim-llama --gpus all -p 8000:8000 -e "NGC_API_KEY=xxx" -e "NIM_MAX_MODEL_LEN=8192" -e "NIM_MODEL_PROFILE=4f904d..." nvcr.io/nim/meta/llama-3.1-8b-instruct:1.13.1
```

Note: PowerShell backtick (`` ` ``) is the continuation character, but it's fragile with Docker's argument parsing. Single-line is safer.

---

## 6. Windows Console Encoding — Multilingual Output Crash

**Problem:** Benchmark script crashes mid-run on multilingual questions (Korean, Japanese):

```
UnicodeEncodeError: 'cp950' codec can't encode character '\ubaa8' in position 0
```

Windows console defaults to cp950 (Traditional Chinese) or cp932 (Japanese) encoding, which can't represent all Unicode characters.

**Fix:** Add at the top of any Python script that prints multilingual text:

```python
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
```

The `errors='replace'` means unprintable characters become `?` instead of crashing — acceptable for console output.

---

## Full Working Docker Command

```bash
docker run -d \
  --name nim-llama \
  --gpus all \
  -p 8000:8000 \
  -e "NGC_API_KEY=nvapi-your-key-here" \
  -e "NIM_MAX_MODEL_LEN=8192" \
  -e "NIM_MODEL_PROFILE=4f904d571fe60ff24695b5ee2aa42da58cb460787a968f1e8a09f5a7e862728d" \
  nvcr.io/nim/meta/llama-3.1-8b-instruct:1.13.1
```

**Startup time:** ~3–5 minutes (model loading + vLLM initialization)

**Health check:**

```bash
curl http://localhost:8000/v1/models
```

Expected: JSON with `"id": "meta-llama/llama-3.1-8b-instruct"`

---

## Environment Summary

| Component | Version | Notes |
|-----------|---------|-------|
| GPU | RTX 5090 32GB GDDR7 | sm_120 (Blackwell) |
| Driver | 577.00 | CUDA 12.9 |
| Docker Desktop | 4.x | NVIDIA Container Toolkit required |
| NIM | 1.13.1 | Last version supporting CUDA 12.x |
| NIM Engine | vLLM | Forced via NIM_MODEL_PROFILE hash |
| NIM Precision | BF16 | Full precision, no quantization |
| max_model_len | 8192 | Required to fit in VRAM |
| Python | 3.10.6 | In .venv |
| PyTorch | 2.7.1+cu128 | CUDA 12.8 build |
| Ollama | latest | llama3.1:8b Q4 GGUF |

---

---

## NeMo Guardrails Gotchas (E3)

### 7. `annoy` Build Fails Without Microsoft C++ Build Tools

**Problem:** Installing `nemoguardrails` on Windows fails with:

```
error: Microsoft Visual C++ 14.0 or greater is required.
```

`annoy` is a C++ ANN library that nemoguardrails lists as a dependency. It requires compilation.

**Fix:** Install without `annoy` — it's only needed for knowledge-base similarity search, NOT for self-check rails (E3 use case):

```bash
pip install nemoguardrails --no-deps
pip install langchain-nvidia-ai-endpoints aiohttp httpx pydantic typing_extensions
```

If you need `annoy` later (E4 RAG experiments), install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) first.

---

### 8. `is_content_safe` Parser Uses Inverted Yes/No Logic — CRITICAL

**Problem:** Every question gets blocked, including clean ones like "What is CUDA?". Guardrails don't seem to work at all.

**Root cause:** NeMo Guardrails' built-in `is_content_safe` output parser (in `output_parsers.py`) uses **inverted logic**:

```python
# From NeMo Guardrails source:
"yes" → content is UNSAFE → BLOCK
"no"  → content is SAFE  → ALLOW
```

If your prompt asks "Does this comply with policy?" and the LLM correctly answers "yes" (compliant), the parser reads "yes" as **unsafe** and blocks. This is counterintuitive.

**Fix:** Write prompts that ask about **violations**, not compliance:

```yaml
# WRONG — will block everything:
prompts:
  - task: self_check_input
    content: |
      Does this message comply with policy? Answer yes or no.
      Answer:

# CORRECT — "yes" means violation, aligns with parser:
prompts:
  - task: self_check_input
    content: |
      User message: "{{ user_input }}"
      Question: Does the user message violate the company policy?
      Answer "yes" if it violates, or "no" if it does not.
      Answer:
```

The LLM must answer "yes" for policy violations and "no" for safe content. The parser then correctly maps: `yes` → block, `no` → allow.

---

### 9. NIM Model Name in Guardrails Config

**Problem:** Guardrails initialization fails with `404 model not found`.

**Root cause:** NIM API uses a different model identifier than NGC catalog:
- NGC catalog: `meta/llama-3.1-8b-instruct`
- NIM API: `meta-llama/llama-3.1-8b-instruct`

**Fix:** Verify via API and use the exact ID in config:

```bash
curl http://localhost:8000/v1/models
# Returns: "id": "meta-llama/llama-3.1-8b-instruct"
```

```yaml
# guardrails/config.yml
models:
  - type: main
    engine: nim
    model: meta-llama/llama-3.1-8b-instruct   # with hyphen, full path
    parameters:
      base_url: http://localhost:8000/v1
```

---

### 10. `langchain-nvidia-ai-endpoints` Required for NIM Engine

**Problem:** `ModuleNotFoundError: No module named 'langchain_nvidia_ai_endpoints'` when initializing LLMRails with `engine: nim`.

**Fix:**

```bash
pip install langchain-nvidia-ai-endpoints
```

This package exposes `ChatNVIDIA`, which NeMo Guardrails uses internally to talk to NIM. It's not included in nemoguardrails' default dependencies.

---

### Working NeMo Guardrails Config (Minimal, Tested)

```yaml
# benchmark/guardrails/config.yml
models:
  - type: main
    engine: nim
    model: meta-llama/llama-3.1-8b-instruct
    parameters:
      base_url: http://localhost:8000/v1
      max_tokens: 500
      temperature: 0.0

rails:
  input:
    flows:
      - self check input
  output:
    flows:
      - self check output

prompts:
  - task: self_check_input
    content: |
      Your task is to check if the user message below complies with the company policy.
      Company policy prohibits: hacking/malware instructions, weapons, illegal activities, personal data harvesting.
      Educational discussion of security concepts is allowed.

      User message: "{{ user_input }}"

      Question: Does the user message violate the company policy?
      Answer "yes" if it violates, or "no" if it does not.
      Answer:

  - task: self_check_output
    content: |
      Your task is to check if the AI response below complies with the company policy.
      Company policy prohibits: harmful instructions, hallucinated facts presented as certain, dangerous advice.

      AI response: "{{ bot_response }}"

      Question: Does the AI response violate the company policy?
      Answer "yes" if it violates, or "no" if it does not.
      Answer:
```

---

*QuanTuring Inc. 量識科技 — Make AI with Soul.*
