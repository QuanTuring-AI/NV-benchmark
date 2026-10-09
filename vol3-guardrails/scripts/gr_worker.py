#!/usr/bin/env python3
"""NeMo Guardrails worker for the Vol.1-B 2×2 bridge. One process per Guardrails version (one venv each).

Protocol: one JSON object per line on stdin {"key": ..., "text": ...}; one JSON object per line on the ORIGINAL stdout.
Everything the library prints goes to stderr, so the protocol channel carries only results.

Timed region = Vol.1 `benchmark/run_e3_guardrails.py::benchmark_nim_with_guardrails` (lines 124-184), with ONE change:
  start → rails.generate_async(messages=[user]) on the worker's single persistent event loop → end
  🔴 Deviation from Vol.1: Vol.1 creates a new event loop per call and closes it. With nemoguardrails 0.23.0 that
  pattern logs "Retrying after stale event loop binding: Event loop is closed" on every request (45/45 in the mock
  test; 0/45 with 0.21.0) and roughly doubled per-request latency against the same mock server — a harness cost that
  would be charged to 0.23.0 only. One loop per worker is used for BOTH versions. Retry lines are counted per request.
  was_blocked by Vol.1's refusal-phrase list; exception containing "blocked"/"not allowed" → input-rail block.
Added OUTSIDE the timed region: rails.explain() → per LLM call: task, duration, token counts, the first 200
characters of the completion (for the self-check tasks this is the rail's yes/no verdict).
"""
import asyncio, json, os, sys, time, importlib.metadata as md

proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
os.dup2(2, 1)
sys.stdout = sys.stderr

CONFIG_DIR = os.environ["GR_CONFIG_DIR"]
BLOCKED_INDICATORS = ["I'm sorry", "I cannot", "I can't", "not able to help", "against my guidelines",
                      "refuse", "inappropriate", "not appropriate"]        # Vol.1 run_e3_guardrails.py:146-155


def versions():
    out = {}
    for p in ("nemoguardrails", "langchain", "langchain-core", "langchain-nvidia-ai-endpoints", "langchain-openai", "openai", "httpx"):
        try:
            out[p] = md.version(p)
        except Exception:
            out[p] = None
    out["python"] = sys.version.split()[0]
    return out


from nemoguardrails import RailsConfig, LLMRails

LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)


class RetryCounter:
    """Counts the library's stale-event-loop retry messages written to stderr (count only, stream unchanged)."""
    def __init__(self, stream):
        self.stream, self.n = stream, 0

    def write(self, s):
        self.n += s.count("stale event loop")
        return self.stream.write(s)

    def flush(self):
        return self.stream.flush()


import logging
_counter = RetryCounter(sys.stderr)
sys.stderr = _counter
for h in logging.root.handlers:
    if hasattr(h, "stream"):
        h.stream = _counter
rails = LLMRails(RailsConfig.from_path(CONFIG_DIR))
proto.write(json.dumps({"ready": True, "versions": versions(), "config_dir": os.path.basename(CONFIG_DIR.rstrip("/\\"))}) + "\n")


def explain_calls():
    try:
        info = rails.explain()
        calls = []
        for c in info.llm_calls or []:
            calls.append({"task": c.task, "duration_s": c.duration, "prompt_tokens": c.prompt_tokens,
                          "completion_tokens": c.completion_tokens, "total_tokens": c.total_tokens,
                          "completion_head": (c.completion or "")[:200]})
        return calls
    except Exception as e:
        return [{"explain_error": f"{type(e).__name__}: {e}"}]


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    if req.get("stop"):
        break
    question = req["text"]
    start = time.perf_counter()
    was_blocked = False
    full_response = ""
    block_reason = None
    row = {"key": req.get("key")}
    retries_before = _counter.n
    sys.__stderr__.write(f"##REQ {req.get('key')}\n"); sys.__stderr__.flush()     # marker: library log lines after it belong to this request
    try:
        result = LOOP.run_until_complete(rails.generate_async(messages=[{"role": "user", "content": question}]))
        end = time.perf_counter()
        full_response = result.get("content", "") if isinstance(result, dict) else str(result)
        if any(ind.lower() in full_response.lower() for ind in BLOCKED_INDICATORS):
            was_blocked = True
            block_reason = "output_self_check"
    except Exception as e:
        end = time.perf_counter()
        es = str(e)
        if "blocked" in es.lower() or "not allowed" in es.lower():
            was_blocked = True
            block_reason = "input_self_check"
            full_response = f"[BLOCKED BY INPUT RAIL] {es[:200]}"
        else:
            row.update({"error": es[:500]})
            proto.write(json.dumps(row) + "\n")
            continue
    total_sec = end - start
    token_count = len(full_response.split()) if full_response else 0
    row.update({"total_latency_ms": round(total_sec * 1000, 1), "tokens": token_count,
                "tps": round(token_count / total_sec, 1) if total_sec > 0 and token_count > 0 else 0,
                "response_full": full_response, "was_blocked": was_blocked, "block_reason": block_reason,
                "t_end_epoch": time.time(), "stale_loop_retries": _counter.n - retries_before, "llm_calls": explain_calls()})
    proto.write(json.dumps(row) + "\n")
