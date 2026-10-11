#!/usr/bin/env python3
"""P93 · the rail configuration of each arm that goes through NeMo Guardrails. Written to results/, one directory per arm.

Self-check arms (J0-J3) start from the published Vol.1 rail config, benchmark/guardrails/config.yml, read at run time and
never copied by hand. The derivation is the one the Vol.3 baseline cells used (BASELINE.md section 2), plus one line per arm:
  all    the model name is replaced by the id the server reports; `top_p: 0.9` is added under the main model's parameters;
         the base URL points to 127.0.0.1:8000
  J0     `max_tokens: 3` on the self_check_input and self_check_output prompt entries
  J1     nothing more: the library's own default applies (1,024 tokens since 0.23.0)
  J2     `chat_template_kwargs: {enable_thinking: true}` under the main model's parameters
  J3     `chat_template_kwargs: {enable_thinking: false}` under the main model's parameters
The two prompts themselves are the Vol.1 texts, unchanged, for all four.

Content-safety arms (J4G, J5G) follow the library's own example for this model, examples/configs/nemotron-3.5-content-safety
at tag v0.24.1 (commit 5d81d6700e713018e3b74065f8b1f56d1051f290): model type `content_safety`, the rail flows
`content safety check input / output $model=content_safety`, message prompts that carry only the turns to classify, and the
parsers nemotron_content_safety_parse_prompt_safety / _response_safety. Changes from the example, all of them the ones its
README names for a local server: engine `openai` with `base_url`, the model id the local server reports, and the main model
pointed at the same server (no answer is generated in this study, so the main model is never called). J5G sets
enable_thinking true and max_tokens 1,024, as the README says to do before enabling thinking.
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p93_common import ARMS, BASE, REPO, sha256_file, sha256_text  # noqa: E402

RAIL_CONFIG = os.path.join(REPO, "benchmark", "guardrails", "config.yml")
TOP_P = 0.9
EXAMPLE = {"path": "examples/configs/nemotron-3.5-content-safety", "tag": "v0.24.1", "commit": "5d81d6700e713018e3b74065f8b1f56d1051f290"}


def self_check_config(arm, model):
    src = open(RAIL_CONFIG, encoding="utf-8").read()
    m = re.search(r"^(\s*model:\s*)(\S+)\s*$", src, flags=re.M)
    if not m:
        sys.exit("rail config: no model line")
    src = src[:m.start(2)] + model + src[m.end(2):]
    b = re.search(r"^(\s*base_url:\s*)(\S+)\s*$", src, flags=re.M)
    if not b:
        sys.exit("rail config: no base_url line")
    src = src[:b.start(2)] + BASE + "/v1" + src[b.end(2):]
    t = re.search(r"^(\s*)temperature:\s*0\.0\s*$", src, flags=re.M)
    if not t or "top_p:" in src or "max_tokens: 3" in src or "chat_template_kwargs" in src:
        sys.exit("rail config: expected one 'temperature: 0.0' line and none of top_p / max_tokens: 3 / chat_template_kwargs")
    extra = f"\n{t.group(1)}top_p: {TOP_P}"
    think = ARMS[arm]["thinking"]
    if think is not None:
        extra += f"\n{t.group(1)}chat_template_kwargs:\n{t.group(1)}  enable_thinking: {'true' if think else 'false'}"
    src = src[:t.end()] + extra + src[t.end():]
    n = 0
    if ARMS[arm]["max_tokens"] == 3:
        src, n = re.subn(r"^(\s*)- task: (self_check_input|self_check_output)\s*$", lambda mm: f"{mm.group(0)}\n{mm.group(1)}  max_tokens: 3", src, flags=re.M)
        if n != 2:
            sys.exit(f"rail config: expected exactly 2 self-check prompt entries, found {n}")
    return {"config.yml": src}, {"source": "benchmark/guardrails/config.yml", "source_sha256": sha256_file(RAIL_CONFIG), "model": model, "top_p_added": TOP_P,
                                 "enable_thinking": think, "self_check_max_tokens_set": 3 if n else None}


def content_safety_config(arm, model):
    think = "true" if ARMS[arm]["thinking"] else "false"; mt = ARMS[arm]["max_tokens"]
    config = f"""models:
  - type: main
    engine: openai
    model: {model}
    parameters:
      base_url: {BASE}/v1
      api_key: "none"

  - type: content_safety
    engine: openai
    model: {model}
    parameters:
      base_url: {BASE}/v1
      api_key: "none"
      chat_template_kwargs:
        enable_thinking: {think}
        request_categories: "/categories"

rails:
  input:
    flows:
      - content safety check input $model=content_safety
  output:
    flows:
      - content safety check output $model=content_safety
"""
    prompts = f"""prompts:
  - task: content_safety_check_input $model=content_safety
    messages:
      - type: user
        content: "{{{{ user_input }}}}"
    output_parser: nemotron_content_safety_parse_prompt_safety
    max_tokens: {mt}
    max_length: 128000

  - task: content_safety_check_output $model=content_safety
    messages:
      - type: user
        content: "{{{{ user_input }}}}"
      - type: assistant
        content: "{{{{ bot_response }}}}"
    output_parser: nemotron_content_safety_parse_response_safety
    max_tokens: {mt}
    max_length: 128000
"""
    return {"config.yml": config, "prompts.yml": prompts}, {"source": EXAMPLE, "model": model, "enable_thinking": ARMS[arm]["thinking"], "max_tokens": mt}


def write_config(arm, model, out_dir):
    """Write the arm's rail config under out_dir and return a record of what was written (file names and SHA-256)."""
    path = ARMS[arm]["path"]
    files, rec = self_check_config(arm, model) if path == "guardrails_self_check" else content_safety_config(arm, model)
    os.makedirs(out_dir, exist_ok=True)
    for name, text in files.items():
        open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n").write(text)
    rec["files"] = {name: sha256_text(text) for name, text in files.items()}
    rec["kind"] = "self_check" if path == "guardrails_self_check" else "content_safety"
    return rec


if __name__ == "__main__":
    import json, tempfile
    d = tempfile.mkdtemp(prefix="p93cfg_")
    for arm in ("J0", "J1", "J2", "J3", "J4G", "J5G"):
        print(arm, json.dumps(write_config(arm, "model-id", os.path.join(d, arm)))[:260])
