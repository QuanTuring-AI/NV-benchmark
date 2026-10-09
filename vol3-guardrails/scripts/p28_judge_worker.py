#!/usr/bin/env python3
"""P28 judge worker: one process per rail config. Reads {"text": ...} lines on stdin, calls the library's
`self_check_output` action directly (no generation, no rails pipeline) and writes one JSON result line per call
on the ORIGINAL stdout. `llm_call` inside the action module is wrapped so the raw completion, its token counts and
its duration are recorded; the wrapper returns the library's own object unchanged.

Result fields: is_safe (the action's return: True = allow), first_word and completion_head of the raw verdict,
completion_tokens, duration_ms, truncation_warning (the library's warn_if_truncated message, counted per call)."""
import asyncio, json, os, sys, time, importlib.metadata as md

proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
os.dup2(2, 1)
sys.stdout = sys.stderr

CONFIG_DIR = os.environ["GR_CONFIG_DIR"]


def versions():
    out = {}
    for p in ("nemoguardrails", "langchain", "langchain-core", "langchain-nvidia-ai-endpoints", "openai", "httpx"):
        try:
            out[p] = md.version(p)
        except Exception:
            out[p] = None
    out["python"] = sys.version.split()[0]
    return out


class Counter:
    def __init__(self, stream):
        self.stream, self.trunc = stream, 0

    def write(self, s):
        self.trunc += s.count("returned empty content with finish_reason='length'")
        return self.stream.write(s)

    def flush(self):
        return self.stream.flush()


import logging
_counter = Counter(sys.stderr)
sys.stderr = _counter
for h in logging.root.handlers:
    if hasattr(h, "stream"):
        h.stream = _counter

from nemoguardrails import RailsConfig, LLMRails
import nemoguardrails.library.self_check.output_check.actions as oc

rails = LLMRails(RailsConfig.from_path(CONFIG_DIR))
_raw = []
_orig_llm_call = oc.llm_call


async def _wrapped(*args, **kwargs):
    r = await _orig_llm_call(*args, **kwargs)
    _raw.append(r)
    return r


oc.llm_call = _wrapped
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)
prompt_template = next((p.content for p in rails.config.prompts if str(getattr(p, "task", "")) .endswith("self_check_output")), None)
proto.write(json.dumps({"ready": True, "versions": versions(), "config_dir": os.path.basename(CONFIG_DIR.rstrip("/\\")),
                        "self_check_output_max_tokens_in_config": next((getattr(p, "max_tokens", None) for p in rails.config.prompts
                                                                        if str(getattr(p, "task", "")).endswith("self_check_output")), None),
                        "prompt_references_user_input": bool(prompt_template and "user_input" in prompt_template)}) + "\n")

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    if req.get("stop"):
        break
    _raw.clear(); t0 = _counter.trunc
    start = time.perf_counter()
    try:
        is_safe = LOOP.run_until_complete(oc.self_check_output(
            llm_task_manager=rails.runtime.llm_task_manager,
            context={"bot_message": req["text"]},
            llm=rails.llm, config=rails.config))
        dur = (time.perf_counter() - start) * 1000
    except Exception as e:
        proto.write(json.dumps({"error": f"{type(e).__name__}: {e}"[:400]}) + "\n"); continue
    r = _raw[-1] if _raw else None
    content = getattr(r, "content", r) or ""
    usage = getattr(r, "usage", None)
    tok = None
    for attr in ("completion_tokens", "total_completion_tokens", "output_tokens"):
        if usage is not None and getattr(usage, attr, None) is not None:
            tok = getattr(usage, attr); break
    proto.write(json.dumps({"is_safe": bool(is_safe), "first_word": (content.split() or [""])[0],
                            "completion_head": content[:200], "completion_tokens": tok,
                            "duration_ms": round(dur, 1), "truncation_warnings": _counter.trunc - t0}, ensure_ascii=False) + "\n")
