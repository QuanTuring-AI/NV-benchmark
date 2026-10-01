#!/usr/bin/env python3
"""Vol.2 · P78 harness test only: a stand-in OpenAI-compatible server on 127.0.0.1, so that p78_quality.py's plumbing
(proxy changes, chunks, join, scoring, engine exit and resume) can be run without a GPU. It verifies plumbing, not the
engines: what a real engine returns is checked on the first real chunk (see the harness test record).
Behaviour: reasoning on -> a paragraph that states a wrong answer in the task's format, then the answer "42" / "A" in the
format; every 7th request instead returns content null with a reasoning channel and finish_reason "length". Reasoning off
(chat_template_kwargs.enable_thinking false, or a "/no_think" system message) -> one line with the answer. It records every
request body it received (--log) so the test can check what the proxy sent. --die-after N: the process exits after N
requests (an engine exit).
usage: p78_mock_openai.py --port P [--die-after N] [--log FILE]
"""
import argparse, http.server, json, os, socketserver, threading

a = None
count = {"n": 0}
lock = threading.Lock()


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *x):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send(200, {"data": [{"id": "mock"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
        with lock:
            count["n"] += 1; n = count["n"]
            if a.log:
                with open(a.log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(body, ensure_ascii=False) + "\n")
        if a.die_after and n > a.die_after:
            os._exit(3)
        msgs = body.get("messages") or []
        mmlu = "best answer" in json.dumps(msgs)
        off = (body.get("chat_template_kwargs") or {}).get("enable_thinking") is False or (msgs and msgs[0].get("role") == "system" and msgs[0].get("content") == "/no_think")
        ans = "The best answer is A" if mmlu else "The final answer is 42"
        wrong = "The best answer is C" if mmlu else "The final answer is 17"
        msg = {"role": "assistant"}
        if off:
            msg["content"] = ans; fin = "stop"; comp = 12
        elif n % 7 == 0:
            msg["content"] = None; msg["reasoning_content"] = "Thinking about it at length, " + wrong + " maybe"; fin = "length"; comp = body.get("max_tokens")
        else:
            msg["content"] = "Let me reason. At first " + wrong + ". Checking again. " + ans; fin = "stop"; comp = 300
        self._send(200, {"choices": [{"index": 0, "message": msg, "finish_reason": fin}], "usage": {"prompt_tokens": 500, "completion_tokens": comp, "total_tokens": 500 + (comp or 0)}})


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, required=True); ap.add_argument("--die-after", type=int, default=0); ap.add_argument("--log")
    a = ap.parse_args()
    S(("127.0.0.1", a.port), H).serve_forever()
