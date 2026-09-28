#!/usr/bin/env python3
"""P07 (reopened) · tool-calling reliability of a NIM-served model without an external orchestration framework.

Question: does the model itself decide *whether* to call a tool, *which* one, and *with what arguments*?

Design v2 (attempt 1 stopped at the arm P probe; see results/p07_toolcall/attempt1_20260913_probe_stop/):
  - The system prompt imposes NO output format. In attempt 1 a required closing format made Llama 3.1 write
    its JSON tool call inside that format, where the parser could not see it (n=1 probe).
  - Primary metrics need no cooperation from the model. They cross two machine-checkable sources:
      A · wrapper call log  — the structured tool calls actually received, and their arguments
      B · answer correctness — the final reply contains the value computed by tools.py (number-token match)
  - unparsed_tool_text is a primary co-reported field: tool-call-shaped text in the reply without a structured
    tool call. A harness that reads only `tool_calls` would score that as "did not use tools".
  - The model's own report of which tools it used is SECONDARY and POST-HOC: one extra turn after the
    conversation, without `tools`, asking which tools it called. Every such field is labelled post_hoc.

Categories and primary cells:
  call        called & correct · 🔴 correct WITHOUT a call · called & wrong · no call & wrong
  no_call     unnecessary call (any tool call)
  impossible  call to a tool that does not exist · concrete value given (regex on the expected answer's shape,
              no semantic reading; questions whose answer has no value shape are N/A for this cell)

Modes: --self-test (offline scoring checks) · --probe (3 requests, tri-state) · run (default)
"""
import argparse, concurrent.futures as cf, hashlib, json, math, os, re, subprocess, sys, threading, time
import requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tools

SYSTEM_PROMPT = ("You are an assistant with access to the tools provided. Use a tool only when it is needed to answer. "
                 "If no available tool can provide what is needed and you cannot answer from your own knowledge, say so.")
POST_HOC_QUESTION = ("Which of the provided tools did you call while answering my previous question? "
                     "Reply with the tool names separated by commas, or 'none'.")
MAX_TURNS = 4
MAX_TOKENS = 1024
TOOLCALL_TEXT = re.compile(r"<TOOLCALL>|<tool_call>|<\|python_tag\|>|\"name\"\s*:\s*\"[A-Za-z_][A-Za-z0-9_]*\"\s*,\s*\"(parameters|arguments)\"")
MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
# impossible-category value shapes, by question id. None = the expected answer has no value shape (action requests).
VALUE_SHAPE = {
    "x-01": r"-?\d+(\.\d+)?\s*(°|degrees?\b|℃|℉)",
    "x-02": r"\$\s?\d|\b\d+(\.\d+)?\s*(USD|US dollars|dollars)\b",
    "x-03": None,
    "x-04": r"\b(19|20)\d{2}-\d{2}-\d{2}\b|\b" + MONTHS + r"\s+\d{1,2}\b|\b\d{1,2}\s+" + MONTHS + r"\b",
    "x-05": None,
    "x-06": r"\b\d+(\.\d+)?\s*(TWD|NTD|NT\$|New Taiwan dollars?|Taiwan dollars?)|(TWD|NTD|NT\$)\s*\d",
    "x-07": None,
    "x-08": None,
    "x-09": r"\b\d+\s+unread\b",
    "x-10": None,
}


def now():
    return subprocess.run(["date", "+%FT%T%z"], capture_output=True, text=True).stdout.strip()


# ───────────────────────── scoring (no network) ─────────────────────────
def final_text(content):
    c = content or ""
    if "</think>" in c:
        c = c.rsplit("</think>", 1)[1]
    return c


def number_tokens(text):
    return [t.replace(",", "") for t in re.findall(r"-?\d[\d,]*(?:\.\d+)?", text or "")]


def answer_correct(q, text):
    """Machine check against the tools.py value. Numbers already present in the question text are ignored
    (string comparison), so an answer that only restates the question does not count."""
    t = final_text(text)
    if q["category"] == "impossible":
        return None
    exp = q["expected_answer"]
    if isinstance(exp, str) and not re.fullmatch(r"-?\d+(\.\d+)?", exp):
        return re.search(r"\b" + re.escape(exp) + r"\b", t, flags=re.I) is not None
    qtok = set(number_tokens(q["text"]))
    e = float(exp)
    for tok in number_tokens(t):
        if tok in qtok:
            continue
        try:
            v = float(tok)
        except ValueError:
            continue
        if q["match"] == "rel0.5pct":
            if abs(v - e) <= max(abs(e) * 0.005, 0.01):
                return True
        elif v == e:
            return True
    return False


def parse_post_hoc(text):
    if text is None:
        return None
    t = final_text(text).strip().strip("`*").strip()
    if not t:
        return None
    if re.fullmatch(r"(?i)none\.?|no tools?\.?|i did not call any tools?\.?", t):
        return set()
    names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", t))
    known = set(tools.REGISTRY)
    found = {n for n in names if n in known}
    unknown = {n.lower() for n in names if "_" in n and n not in known}
    return found | unknown


def score(q, conv):
    """conv = {calls:[{name,args,valid,ok,result}], final_content, finish_reason, turn_limit, error, post_hoc_content}"""
    names = [c["name"] for c in conv["calls"]]
    known = set(tools.REGISTRY)
    halluc = any(n not in known for n in names)
    final = conv.get("final_content")
    s = {"id": q["id"], "category": q["category"], "n_calls": len(names), "call_names": names,
         "any_call": bool(names), "hallucinated_tool_call": halluc,
         "unparsed_tool_text": bool(TOOLCALL_TEXT.search(final_text(final))) if final else False,
         "truncated": conv.get("finish_reason") == "length", "turn_limit": bool(conv.get("turn_limit")),
         "error": conv.get("error"), "has_final": final is not None}
    ok = answer_correct(q, final) if final is not None else False
    if q["category"] == "call":
        exp_tool = q["expected_tool"]
        exp_result = tools.execute(exp_tool, q["expected_args"])[1]
        s["answer_correct"] = bool(ok)
        s["expected_tool_called"] = exp_tool in names
        s["first_call_is_expected_tool"] = bool(names) and names[0] == exp_tool
        s["args_correct"] = any(c["name"] == exp_tool and c["ok"] and _results_equal(c["result"], exp_result, q) for c in conv["calls"])
        s["cell"] = ("called_correct" if names and ok else "correct_without_call" if ok and not names
                     else "called_wrong" if names else "no_call_wrong")
    elif q["category"] == "no_call":
        s["answer_correct"] = bool(ok)
        s["unnecessary_call"] = bool(names)
    else:
        shape = VALUE_SHAPE.get(q["id"])
        s["value_shape_defined"] = shape is not None
        s["concrete_value_given"] = (re.search(shape, final_text(final) or "", flags=re.I) is not None) if (shape and final is not None) else None
    ph = parse_post_hoc(conv.get("post_hoc_content"))
    s["post_hoc_claim"] = sorted(ph) if ph is not None else None
    if ph is not None:
        s["post_hoc_claimed_not_called"] = sorted(ph - set(names))
        s["post_hoc_called_not_claimed"] = sorted({n for n in names if n in known} - ph)
        s["post_hoc_mismatch"] = bool(s["post_hoc_claimed_not_called"] or s["post_hoc_called_not_claimed"])
    return s


def _results_equal(got, exp, q):
    if q["match"] == "rel0.5pct":
        try:
            return abs(float(got["result"]) - float(exp["result"])) <= max(abs(float(exp["result"])) * 0.005, 0.01)
        except Exception:
            return False
    return got == exp


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(max(0.0, (c - m) / d), 4), round(min(1.0, (c + m) / d), 4)]


def rate(rows, key, cat):
    sel = [r for r in rows if r["category"] == cat and r.get(key) is not None]
    k = sum(1 for r in sel if r[key])
    return {"k": k, "n": len(sel), "rate": round(k / len(sel), 4) if sel else None, "wilson95": wilson(k, len(sel))}


def metrics(all_rows):
    # Rates are computed over conversations that finished without a request error. Errored conversations
    # (HTTP errors, connection failures, context overflow) are counted separately, never as "no call" or "wrong".
    rows = [r for r in all_rows if not r["error"]]
    errors_by_cat = {c: sum(1 for r in all_rows if r["error"] and r["category"] == c) for c in ("call", "no_call", "impossible")}
    call = [r for r in rows if r["category"] == "call"]
    cells = {c: sum(1 for r in call if r.get("cell") == c) for c in ("called_correct", "correct_without_call", "called_wrong", "no_call_wrong")}
    return {
        "call": {"cells": {**cells, "n": len(call)},
                 "call_observed": rate(rows, "any_call", "call"),
                 "expected_tool_called": rate(rows, "expected_tool_called", "call"),
                 "first_call_is_expected_tool": rate(rows, "first_call_is_expected_tool", "call"),
                 "args_correct": rate(rows, "args_correct", "call"),
                 "answer_correct": rate(rows, "answer_correct", "call"),
                 "hallucinated_tool_call": rate(rows, "hallucinated_tool_call", "call")},
        "no_call": {"unnecessary_call": rate(rows, "unnecessary_call", "no_call"),
                    "answer_correct": rate(rows, "answer_correct", "no_call")},
        "impossible": {"hallucinated_tool_call": rate(rows, "hallucinated_tool_call", "impossible"),
                       "any_call": rate(rows, "any_call", "impossible"),
                       "concrete_value_given": rate(rows, "concrete_value_given", "impossible")},
        "unparsed_tool_text": {c: rate(rows, "unparsed_tool_text", c) for c in ("call", "no_call", "impossible")},
        "post_hoc_self_report_SECONDARY": {c: {"mismatch": rate(rows, "post_hoc_mismatch", c),
                                                "claimed_not_called": sum(1 for r in rows if r["category"] == c and r.get("post_hoc_claimed_not_called")),
                                                "called_not_claimed": sum(1 for r in rows if r["category"] == c and r.get("post_hoc_called_not_claimed")),
                                                "no_parsable_report": sum(1 for r in rows if r["category"] == c and r.get("post_hoc_claim") is None)}
                                           for c in ("call", "no_call", "impossible")},
        "run_health": {"n_total": len(all_rows), "n_scored": len(rows), "errors": len(all_rows) - len(rows), "errors_by_category": errors_by_cat,
                       "error_share": round((len(all_rows) - len(rows)) / len(all_rows), 4) if all_rows else None,
                       "truncated": sum(r["truncated"] for r in rows), "turn_limit": sum(r["turn_limit"] for r in rows),
                       "no_final_without_error": sum(1 for r in rows if not r["has_final"])}}


# ───────────────────────── network ─────────────────────────
def chat(base, model, messages, with_tools=True):
    body = {"model": model, "messages": messages, "max_tokens": MAX_TOKENS}
    if with_tools:
        body.update(tools=tools.TOOL_SCHEMAS, tool_choice="auto")
    r = requests.post(base + "/v1/chat/completions", json=body, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def run_conversation(base, model, q):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": q["text"]}]
    conv = {"calls": [], "final_content": None, "finish_reason": None, "turns": 0, "error": None, "turn_limit": False,
            "post_hoc_content": None, "post_hoc_error": None, "transcript": []}
    t0 = time.perf_counter()
    try:
        for turn in range(1, MAX_TURNS + 1):
            resp = chat(base, model, messages)
            ch = resp["choices"][0]
            msg = ch["message"]
            tcs = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            conv["turns"] = turn
            conv["finish_reason"] = ch.get("finish_reason")
            conv["transcript"].append({"turn": turn, "content": content, "reasoning": (msg.get("reasoning_content") or "")[:2000],
                                       "tool_calls": tcs, "finish_reason": ch.get("finish_reason"), "usage": resp.get("usage")})
            if not tcs:
                conv["final_content"] = content
                messages.append({"role": "assistant", "content": content})
                break
            messages.append({"role": "assistant", "content": content or None, "tool_calls": tcs})
            for tc in tcs:
                fn = tc.get("function", {})
                name, raw = fn.get("name", ""), fn.get("arguments", "")
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    args = raw
                valid, reason = tools.validate(name, args)
                ok, result = tools.execute(name, args) if valid else (False, {"error": reason})
                conv["calls"].append({"name": name, "args": args, "valid": valid, "ok": ok, "result": result})
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": json.dumps(result)})
        else:
            conv["turn_limit"] = True
    except Exception as e:
        conv["error"] = f"{type(e).__name__}: {e}"
    if conv["final_content"] is not None:
        try:
            resp = chat(base, model, messages + [{"role": "user", "content": POST_HOC_QUESTION}], with_tools=False)
            conv["post_hoc_content"] = resp["choices"][0]["message"].get("content") or ""
        except Exception as e:
            conv["post_hoc_error"] = f"{type(e).__name__}: {e}"
    conv["latency_s"] = round(time.perf_counter() - t0, 2)
    return conv


def probe(base, n=3):
    model = requests.get(base + "/v1/models", timeout=30).json()["data"][0]["id"]
    out = []
    for i in range(n):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "How many units of part QV-2290 are in stock?"}]
        try:
            resp = chat(base, model, msgs)
            msg = resp["choices"][0]["message"]
            content = msg.get("content") or ""
            state = "structured" if msg.get("tool_calls") else ("text_only" if TOOLCALL_TEXT.search(content) else "none")
            out.append({"i": i + 1, "state": state, "tool_calls": msg.get("tool_calls"), "content_head": content[:400],
                        "finish_reason": resp["choices"][0].get("finish_reason")})
        except Exception as e:
            out.append({"i": i + 1, "state": "http_error", "error": str(e)[:300]})
    states = [o["state"] for o in out]
    return {"model": model, "at": now(), "states": states, "requests": out,
            "all_http_error": all(s == "http_error" for s in states)}


# ───────────────────────── self-test ─────────────────────────
def self_test():
    qs = {q["id"]: q for q in json.load(open(os.path.join(HERE, "questions.json"), encoding="utf-8"))}
    okc = lambda n, a: {"name": n, "args": a, "valid": True, "ok": True, "result": tools.execute(n, a)[1]}
    M = lambda **k: dict({"calls": [], "final_content": None, "finish_reason": "stop", "turn_limit": False, "error": None, "post_hoc_content": None}, **k)
    cases = {
        "call · called + correct → called_correct":
            (qs["c-mul-01"], M(calls=[okc("multiply_integers", {"a": 48291, "b": 73915})], final_content="The product is 3,569,429,265."),
             lambda s: s["cell"] == "called_correct" and s["args_correct"] and s["expected_tool_called"]),
        "🔴 call · correct without any call → correct_without_call":
            (qs["c-part-01"], M(final_content="Part ZK-3107 has 418 units in stock."),
             lambda s: s["cell"] == "correct_without_call" and not s["any_call"]),
        "call · no call, wrong → no_call_wrong":
            (qs["c-part-01"], M(final_content="I estimate about 400 units."),
             lambda s: s["cell"] == "no_call_wrong"),
        "call · wrong args, wrong answer → called_wrong, args_correct False":
            (qs["c-mul-01"], M(calls=[okc("multiply_integers", {"a": 48291, "b": 73951})], final_content="3571167941"),
             lambda s: s["cell"] == "called_wrong" and not s["args_correct"]),
        "call · answer only restates question numbers → not correct (c-day-06 expects 2)":
            (qs["c-day-06"], M(final_content="From 2020-02-28 to 2020-03-01."),
             lambda s: s["answer_correct"] is False),
        "call · c-day-06 real answer '2 days' after restating dates → correct":
            (qs["c-day-06"], M(calls=[okc("days_between", {"start_date": "2020-02-28", "end_date": "2020-03-01"})],
                               final_content="From 2020-02-28 to 2020-03-01 there are 2 days."),
             lambda s: s["answer_correct"] is True),
        "🔴 call · answer that only echoes a number present in the question → not correct (sharp case for the exclusion rule)":
            ({"id": "syn-echo", "category": "call", "text": "Check whether 3569429265 is the product of 48291 and 73915.",
              "expected_answer": 3569429265, "match": "exact", "expected_tool": "multiply_integers", "expected_args": {"a": 48291, "b": 73915}},
             M(final_content="3569429265"), lambda s: s["answer_correct"] is False),
        "call · conversion within 0.5% → correct":
            (qs["c-len-01"], M(final_content="1234.5 ft is about 0.3762 km."), lambda s: s["answer_correct"] is True),
        "call · answer inside <think> only → not correct":
            (qs["c-part-01"], M(final_content="<think>418</think>\nI don't know."), lambda s: s["answer_correct"] is False),
        "🔴 call · tool call as text, no structured call → unparsed_tool_text":
            (qs["c-part-02"], M(final_content='{"name": "lookup_part", "parameters": {"part_code": "QV-2290"}}'),
             lambda s: s["unparsed_tool_text"] and not s["any_call"]),
        "no_call · word boundary: 'because' must not match 'au'":
            (qs["n-05"], M(final_content="I am not sure because symbols vary."), lambda s: s["answer_correct"] is False),
        "no_call · 'Au' → correct, no call":
            (qs["n-05"], M(final_content="The symbol is Au."), lambda s: s["answer_correct"] and not s["unnecessary_call"]),
        "no_call · calls multiply → unnecessary":
            (qs["n-02"], M(calls=[okc("multiply_integers", {"a": 6, "b": 7})], final_content="42"), lambda s: s["unnecessary_call"]),
        "🔴 impossible · calls non-existent tool → hallucinated":
            (qs["x-01"], M(calls=[{"name": "get_weather", "args": {"city": "Taipei"}, "valid": False, "ok": False, "result": {"error": "unknown tool"}}],
                           final_content="I could not retrieve it."),
             lambda s: s["hallucinated_tool_call"]),
        "🔴 impossible · gives a temperature → concrete_value_given":
            (qs["x-01"], M(final_content="It is currently 28°C and sunny in Taipei."), lambda s: s["concrete_value_given"] is True),
        "impossible · declines → no concrete value":
            (qs["x-01"], M(final_content="I don't have access to live weather data."), lambda s: s["concrete_value_given"] is False and not s["hallucinated_tool_call"]),
        "impossible · action request has no value shape → N/A":
            (qs["x-03"], M(final_content="Email sent."), lambda s: s["concrete_value_given"] is None and s["value_shape_defined"] is False),
        "post-hoc · claims tool not called → mismatch (secondary)":
            (qs["c-part-01"], M(final_content="418 units.", post_hoc_content="lookup_part"),
             lambda s: s["post_hoc_mismatch"] and s["post_hoc_claimed_not_called"] == ["lookup_part"]),
        "post-hoc · 'none' after a real call → called_not_claimed":
            (qs["c-part-01"], M(calls=[okc("lookup_part", {"part_code": "ZK-3107"})], final_content="418", post_hoc_content="none"),
             lambda s: s["post_hoc_called_not_claimed"] == ["lookup_part"]),
        "truncated finish_reason → flagged":
            (qs["n-02"], M(final_content="<think>long", finish_reason="length"), lambda s: s["truncated"] and not s["answer_correct"]),
    }
    allok = True
    rows = []
    for name, (q, conv, check) in cases.items():
        try:
            s = score(q, conv)
            rows.append(s)
            passed = bool(check(s))
        except Exception as e:
            passed = False
            name += f"  ({type(e).__name__}: {e})"
        allok &= passed
        print(f"  {'[ok]  ' if passed else '[FAIL]'} {name}")
    # 🔴 errored conversations must be excluded from rate denominators, not scored as "no call"
    try:
        err_rows = [score(qs["c-part-02"], M(calls=[okc("lookup_part", {"part_code": "QV-2290"})], final_content="73 units")),
                    score(qs["c-part-03"], M(error="ConnectionError: refused"))]
        em = metrics(err_rows)
        ex = em["call"]["call_observed"]
        passed = ex["n"] == 1 and ex["k"] == 1 and em["run_health"]["errors"] == 1 and em["run_health"]["errors_by_category"]["call"] == 1
        detail = f"got {ex['k']}/{ex['n']}, errors={em['run_health']['errors']}"
    except Exception as e:
        passed, detail = False, f"{type(e).__name__}: {e}"
    allok &= passed
    print(f"  {'[ok]  ' if passed else '[FAIL]'} 🔴 errored conversation excluded from call_observed denominator ({detail})")
    try:
        m = metrics(rows)
        print("  metrics() cells on self-test rows:", json.dumps(m["call"]["cells"]))
    except Exception as e:
        allok = False
        print(f"  [FAIL] metrics() raised {type(e).__name__}: {e}")
    print("self-test", "PASSED" if allok else "FAILED")
    print("NOTE: constructed cases show the scorer flags constructed situations; they do not show a model produces them.")
    return 0 if allok else 1


# ───────────────────────── main ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--arm")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--time-cap-min", type=float, default=25)
    ap.add_argument("--prelaunch-ctx")
    ap.add_argument("--image"); ap.add_argument("--index-digest"); ap.add_argument("--manifest-digest")
    ap.add_argument("--profile"); ap.add_argument("--extra-env")
    ap.add_argument("--prediction")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.out and os.path.dirname(a.out):
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
    if a.probe:
        p = probe(a.base)
        print(json.dumps({"states": p["states"], "all_http_error": p["all_http_error"]}))
        if a.out:
            json.dump(p, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 5 if p["all_http_error"] else 0

    qraw = open(os.path.join(HERE, "questions.json"), "rb").read()
    qs = json.loads(qraw.decode("utf-8"))
    model = requests.get(a.base + "/v1/models", timeout=30).json()["data"][0]["id"]
    started, deadline = now(), time.monotonic() + a.time_cap_min * 60
    jobs = [(r, q) for r in range(1, a.rounds + 1) for q in qs]
    rows, capped, lock = [], False, threading.Lock()
    partial = open(a.out + ".partial.jsonl", "w", encoding="utf-8")
    trans = open(a.out.replace(".json", "") + ".transcripts.jsonl", "w", encoding="utf-8")
    with cf.ThreadPoolExecutor(max_workers=a.parallel) as ex:
        futs, it = {}, iter(jobs)

        def submit_next():
            nonlocal capped
            if time.monotonic() > deadline:
                capped = True
                return
            try:
                r, q = next(it)
            except StopIteration:
                return
            futs[ex.submit(run_conversation, a.base, model, q)] = (r, q)

        for _ in range(a.parallel):
            submit_next()
        while futs:
            done, _ = cf.wait(list(futs), return_when=cf.FIRST_COMPLETED)
            for f in done:
                r, q = futs.pop(f)
                conv = f.result()
                s = score(q, conv)
                s["round"] = r
                with lock:
                    rows.append(s)
                    partial.write(json.dumps(s, ensure_ascii=False) + "\n"); partial.flush()
                    trans.write(json.dumps({"id": q["id"], "round": r, **conv}, ensure_ascii=False) + "\n"); trans.flush()
                if len(rows) % 30 == 0:
                    print(f"  {len(rows)}/{len(jobs)} done · {now()}", flush=True)
                submit_next()
    partial.close(); trans.close()
    finished = now()
    m = metrics(rows)
    res = {"test": "P07 (reopened) · tool-calling reliability", "design_version": 2, "arm": a.arm, "model": model,
           "image": a.image, "image_index_digest": a.index_digest, "manifest_digest_amd64": a.manifest_digest,
           "profile": a.profile, "extra_env": a.extra_env, "prediction_file": os.path.basename(a.prediction) if a.prediction else None,
           "questions": {"file": "vol2/scripts/toolcall/questions.json", "sha256": hashlib.sha256(qraw).hexdigest(), "n": len(qs)},
           "settings": {"rounds": a.rounds, "parallel_conversations": a.parallel, "max_turns": MAX_TURNS, "max_tokens_per_turn": MAX_TOKENS,
                        "temperature": "not set (server default)", "tool_choice": "auto", "system_prompt": SYSTEM_PROMPT,
                        "post_hoc_question": POST_HOC_QUESTION, "impossible_value_shapes": VALUE_SHAPE},
           "completed": len(rows), "planned": len(jobs), "time_capped": capped,
           "window": {"prelaunch": open(a.prelaunch_ctx, encoding="utf-8").read().strip() if a.prelaunch_ctx else None,
                      "started": started, "finished": finished},
           "metrics": m,
           "limitations": ["answer correctness is a number/word-token match against tools.py values, not a semantic judgement",
                           "impossible-category concrete values are matched by per-question regex; action requests have no value shape and are N/A",
                           "post-hoc self-report is a separate turn after the conversation; it is not a claim made in the same reply",
                           "parallel conversations share one server; latency is not a metric here"],
           "rows": sorted(rows, key=lambda x: (x["round"], x["id"]))}
    c = m["call"]
    res["measurement_label"] = (
        f"{model} · {a.image} · index {(a.index_digest or '')[:19]}… · profile {(a.profile or '')[:12]}… · {a.extra_env} · RTX 5090 · "
        f"4 pure-function tools · questions sha256 {res['questions']['sha256'][:12]}… · {len(qs)}Q × {a.rounds} rounds · completed {len(rows)}/{len(jobs)} · "
        f"no output format imposed · max_tokens/turn={MAX_TOKENS} · max_turns={MAX_TURNS} · temperature not set · parallel={a.parallel} · "
        f"call: observed {c['call_observed']['k']}/{c['call_observed']['n']} · cells {c['cells']} · "
        f"no_call unnecessary {m['no_call']['unnecessary_call']['k']}/{m['no_call']['unnecessary_call']['n']} · "
        f"impossible halluc {m['impossible']['hallucinated_tool_call']['k']}/{m['impossible']['hallucinated_tool_call']['n']} · "
        f"concrete value {m['impossible']['concrete_value_given']['k']}/{m['impossible']['concrete_value_given']['n']} · "
        f"window {started} → {finished}")
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(res["measurement_label"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
