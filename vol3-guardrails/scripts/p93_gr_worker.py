#!/usr/bin/env python3
"""P93 · the Guardrails side of a cell. Runs in the NeMo Guardrails environment (the version is recorded, not assumed).

It calls the library's own rail action on stored text, one call per item, N calls in flight (closed loop: a finished call
is replaced at once). No answer is generated and the rails pipeline around the action is not run.
  kind self_check       library/self_check: self_check_input (the user's text) / self_check_output (text + response)
  kind content_safety   library/content_safety: content_safety_check_input / _output with $model=content_safety
The action's own model call is wrapped so that the raw completion can be read; the wrapper returns the library's object
unchanged. The library strips an inline <think>...</think> block from the answer before the wrapper sees it and keeps
the text in its reasoning-trace variable; the worker reads the reasoning from the response field or from that variable. Two things are recorded per item and kept apart:
  rail      what the library's action decided: allow / block, `failed` when the engine's fail-closed envelope produced
            the block, or raise:<exception> when the action raised (an unparseable answer in the content-safety rail)
  verdict   what this study's parser reads from the same completion (p93_parse.py): unsafe / safe / unreadable
The result line carries no text: SHA-256 and sizes of the completion, token counts, the duration. The completion and
the reasoning go to --raw (process bucket).

usage: p93_gr_worker.py --config DIR --kind self_check|content_safety --track input|output --texts FILE --ids FILE
                        --concurrency N --out FILE --raw FILE [--limit N]
  --texts  JSON lines {item_id, prompt, response}; --ids  JSON list of item ids, judged in that order
A first line {"ready": ...} and a last line {"done": ...} are printed as JSON; nothing else goes to stdout.
"""
import argparse, asyncio, contextvars, hashlib, importlib.metadata as md, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p93_parse import read_verdict  # noqa: E402

proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
os.dup2(2, 1)
sys.stdout = sys.stderr
BOX = contextvars.ContextVar("p93_box")


def versions():
    out = {"python": sys.version.split()[0]}
    for p in ("nemoguardrails", "httpx", "aiohttp", "openai", "langchain-core", "pydantic"):
        try:
            out[p] = md.version(p)
        except Exception:
            out[p] = None
    return out


def wrap(module):
    from nemoguardrails.context import reasoning_trace_var
    orig = module.llm_call

    async def wrapped(*a, **k):
        r = await orig(*a, **k)
        box = BOX.get(None)
        if box is not None:
            box["resp"] = r
            # the library moves inline <think> text out of the answer before it returns; it keeps it in this variable
            box["reasoning_trace"] = reasoning_trace_var.get(None)
        return r
    module.llm_call = wrapped


def sha(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True); ap.add_argument("--kind", required=True, choices=["self_check", "content_safety"])
    ap.add_argument("--track", required=True, choices=["input", "output"]); ap.add_argument("--texts", required=True); ap.add_argument("--ids", required=True)
    ap.add_argument("--concurrency", type=int, required=True); ap.add_argument("--out", required=True); ap.add_argument("--raw", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    from nemoguardrails import LLMRails, RailsConfig
    rails = LLMRails(RailsConfig.from_path(a.config))
    tm = rails.runtime.llm_task_manager
    params = rails.runtime.registered_action_params
    llms = params.get("llms", {})
    if a.kind == "self_check":
        import nemoguardrails.library.self_check.utils as mod
        from nemoguardrails.library.self_check.input_check.actions import self_check_input
        from nemoguardrails.library.self_check.output_check.actions import self_check_output
        wrap(mod); shape = "yes_no"

        async def call(prompt, response):
            if a.track == "input":
                return await self_check_input(llms=llms, llm_task_manager=tm, context={"user_message": prompt}, llm=rails.llm, config=rails.config, user_message=prompt)
            return await self_check_output(llms=llms, llm_task_manager=tm, context={"user_message": prompt, "bot_message": response}, llm=rails.llm, config=rails.config,
                                           user_message=prompt, bot_message=response)
    else:
        import nemoguardrails.library.content_safety.actions as mod
        wrap(mod); shape = "lines"

        async def call(prompt, response):
            if a.track == "input":
                return await mod.content_safety_check_input(llms=llms, llm_task_manager=tm, model_name="content_safety", context={}, user_message=prompt)
            return await mod.content_safety_check_output(llms=llms, llm_task_manager=tm, model_name="content_safety", context={}, user_message=prompt, bot_message=response)

    texts = {}
    for line in open(a.texts, encoding="utf-8"):
        if line.strip():
            r = json.loads(line); texts[r["item_id"]] = r
    ids = json.load(open(a.ids, encoding="utf-8"))
    if a.limit:
        ids = ids[: a.limit]
    missing = [i for i in ids if i not in texts]
    if missing:
        proto.write(json.dumps({"ready": False, "error": f"{len(missing)} item ids have no text"}) + "\n"); return 2
    tasks_in_config = sorted(str(p.task) for p in (rails.config.prompts or []))
    proto.write(json.dumps({"ready": True, "versions": versions(), "kind": a.kind, "track": a.track, "n": len(ids), "concurrency": a.concurrency,
                            "prompt_tasks_in_config": tasks_in_config, "model_types": sorted(llms), "main_model": getattr(rails.config.models[0], "model", None)}) + "\n")

    w0 = time.perf_counter()   # one discarded call before the cell (the first call of a new process sets up its client)
    try:
        await call("Hello.", "Hi there.")
    except Exception:
        pass
    warm_ms = round((time.perf_counter() - w0) * 1000, 1)
    out = open(a.out, "a", encoding="utf-8", newline="\n"); raw = open(a.raw, "a", encoding="utf-8", newline="\n")
    sem = asyncio.Semaphore(a.concurrency); t0 = time.perf_counter(); counts = {"ok": 0, "truncated": 0, "unreadable": 0, "error": 0}

    async def one(item_id):
        async with sem:
            t = texts[item_id]; box = {}; BOX.set(box); start = time.perf_counter(); rail = None; err = None
            try:
                o = await call(t["prompt"], t.get("response") or "")
                rail = getattr(getattr(o, "decision", None), "value", None) or str(o)
                if getattr(o, "failed", False):
                    rail += ":failed"
            except Exception as e:  # the content-safety rail raises on an answer it cannot parse
                rail = f"raise:{type(e).__name__}"; err = f"{type(e).__name__}: {e}"[:300]
            end = time.perf_counter()
            r = box.get("resp")
            row = {"item_id": item_id, "rail": rail, "latency_ms": round((end - start) * 1000, 1), "t_start_s": round(start - t0, 3), "t_end_s": round(end - t0, 3)}
            if r is None:
                row.update({"verdict": None, "status": "error", "error": err or "the action made no model call"})
            else:
                content = getattr(r, "content", None) or ""; reasoning = getattr(r, "reasoning", None) or box.get("reasoning_trace") or ""
                fin = getattr(r, "finish_reason", None); fin = getattr(fin, "value", fin)
                u = getattr(r, "usage", None)
                row.update(read_verdict(shape, a.track, content, reasoning, fin))
                row.update({"finish_reason": fin, "completion_tokens": getattr(u, "output_tokens", None), "prompt_tokens": getattr(u, "input_tokens", None),
                            "reasoning_tokens_reported": getattr(u, "reasoning_tokens", None), "completion_sha256": sha(content), "reasoning_sha256": sha(reasoning) if reasoning else None})
                if err:
                    row["rail_error"] = err
                raw.write(json.dumps({"item_id": item_id, "content": content, "reasoning": reasoning}, ensure_ascii=False) + "\n"); raw.flush()
            counts[row["status"]] += 1
            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()

    await asyncio.gather(*(asyncio.create_task(one(i)) for i in ids))
    wall = time.perf_counter() - t0
    out.close(); raw.close()
    proto.write(json.dumps({"done": True, "n": len(ids), "wall_s": round(wall, 3), "status_counts": counts, "warm_up_ms": warm_ms}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
