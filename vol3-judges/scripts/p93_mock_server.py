#!/usr/bin/env python3
"""P93 · a stand-in server for harness tests only. It answers /v1/models and /v1/chat/completions in the shape of a
judge, by a fixed rule on the words of the request, so that the plumbing (files, counts, parsers, concurrency, the
Guardrails worker) can be exercised without a GPU.

What it can and cannot show: it shows that the harness reads and writes what it should. It shows nothing about a real
server: every behaviour the study depends on (how reasoning arrives, what finish_reason says, whether a switch is
honoured, whether usage is reported) is checked against the real server by the precheck of each arm.

Rule: a turn is "unsafe" when it contains one of WORDS. MOCK_TRUNCATE in the request cuts the answer (finish_reason
length); MOCK_GARBLE returns text without a verdict.
  --shape yes_no   "Yes" / "No" on the last quoted text of a self-check prompt
  --shape lines    "User Safety: ..." and, when the request ends with an assistant turn, "Response Safety: ..."
  --shape json     the same two fields as a JSON object
  --reasoning field|inline|none   where reasoning goes when the request sets chat_template_kwargs.enable_thinking true,
                                  or always with --think-default (a model that reasons unless told not to)
usage: p93_mock_server.py --shape lines [--port 8000] [--reasoning field] [--think-default]
"""
import argparse, json, random, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WORDS = ("hurt", "weapon", "threaten")
A = None


def unsafe(text):
    return any(w in (text or "").lower() for w in WORDS)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send({"object": "list", "data": [{"id": "mock-judge", "object": "model"}]} if self.path.startswith("/v1/models") else {"error": "not found"}, 200 if self.path.startswith("/v1/models") else 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        msgs = body.get("messages") or []
        text = lambda m: m.get("content") if isinstance(m.get("content"), str) else " ".join(p.get("text", "") for p in (m.get("content") or []) if isinstance(p, dict))  # noqa: E731
        allt = "\n".join(text(m) or "" for m in msgs)
        last_assistant = bool(msgs) and msgs[-1].get("role") == "assistant"
        think = (body.get("chat_template_kwargs") or {}).get("enable_thinking", A.think_default)
        time.sleep(random.uniform(0.005, 0.02))
        if A.shape == "yes_no":
            q = re.findall(r'"(.*?)"\s*\n\s*\n\s*Question:', allt, re.S)
            answer = "Yes" if unsafe(q[-1] if q else allt) else "No"
        else:
            user = "\n".join(text(m) or "" for m in msgs if m.get("role") == "user"); bot = text(msgs[-1]) if last_assistant else None
            if A.shape == "json" and "response: agent:" in user:
                user, bot = user.split("response: agent:", 1)
            f = {"User Safety": "unsafe" if unsafe(user) else "safe"}
            if bot is not None:
                f["Response Safety"] = "unsafe" if unsafe(bot) else "safe"
            answer = json.dumps(f) if A.shape == "json" else "\n".join(f"{k}: {v}" for k, v in f.items())
        reasoning = "The request is short. I compare it with each rule in turn and then state the result." if think and A.reasoning != "none" else ""
        finish = "stop"; ctoks = 3 + (20 if reasoning else 0)
        if "MOCK_GARBLE" in allt:
            answer = "It depends on the context."
        if "MOCK_TRUNCATE" in allt or (reasoning and (body.get("max_tokens") or 1024) < 20):
            answer = ""; finish = "length"; ctoks = body.get("max_tokens") or 1024
            reasoning = reasoning[: len(reasoning) // 2]
        msg = {"role": "assistant", "content": answer}
        if reasoning and A.reasoning == "field":
            msg["reasoning_content"] = reasoning
        elif reasoning and A.reasoning == "inline":
            msg["content"] = "<think>" + reasoning + ("</think>" if finish == "stop" else "") + answer
        self._send({"id": "mock", "object": "chat.completion", "model": "mock-judge", "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                    "usage": {"prompt_tokens": max(1, len(allt) // 4), "completion_tokens": ctoks, "total_tokens": max(1, len(allt) // 4) + ctoks}})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--shape", required=True, choices=["yes_no", "lines", "json"]); ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reasoning", default="field", choices=["field", "inline", "none"]); ap.add_argument("--think-default", action="store_true")
    A = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", A.port), H); srv.daemon_threads = True
    print(f"mock judge on 127.0.0.1:{A.port} shape={A.shape}", file=sys.stderr, flush=True)
    srv.serve_forever()
