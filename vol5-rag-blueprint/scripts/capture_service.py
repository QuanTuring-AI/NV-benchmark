#!/usr/bin/env python3
"""Vol.5 · a stand-in for the three model services the Blueprint's RAG server calls (answer model, embedding model,
reranking model), so that the exact request the server sends to the answer model can be read without a card.

  POST .../chat/completions   the request body is written to OUT_DIR/<n>.json (n counts from 1) and a fixed short
                              answer is returned, streamed as server-sent events when the request asks for a stream
  POST .../embeddings         one fixed unit vector of DIM numbers per input (retrieval order is then the stored
                              vectors' order of similarity to it; the capture reads the order the server used)
  POST .../ranking            every passage in the order given, logits decreasing
  GET  .../models             the model names given on the command line
  GET  anything else          200 {"status": "ok"} (health checks)

Standard library only. usage: capture_service.py OUT_DIR MODEL [MODEL ...] [--port 8000] [--dim 2048] [--delay SECONDS]
"""
import http.server, json, os, sys, threading

args = [a for a in sys.argv[1:]]
PORT = int(args[args.index("--port") + 1]) if "--port" in args else 8000
DIM = int(args[args.index("--dim") + 1]) if "--dim" in args else 2048
DELAY = float(args[args.index("--delay") + 1]) if "--delay" in args else 0.0   # seconds before each answer (dry runs)
pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--port", "--dim", "--delay"))]
OUT, MODELS = pos[0], pos[1:]
os.makedirs(OUT, exist_ok=True)
LOCK, COUNT = threading.Lock(), [0]
ANSWER = "captured"


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self._send(200, {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "capture"} for m in MODELS]})
        self._send(200, {"status": "ok"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        p = self.path.rstrip("/")
        if p.endswith("/chat/completions"):
            with LOCK:
                COUNT[0] += 1; n = COUNT[0]
            json.dump({"path": self.path, "body": body}, open(os.path.join(OUT, f"{n}.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
            model = body.get("model", "")
            if DELAY:
                import time; time.sleep(DELAY)
            if body.get("stream"):
                chunks = [{"id": "c", "object": "chat.completion.chunk", "model": model, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ANSWER}, "finish_reason": None}]},
                          {"id": "c", "object": "chat.completion.chunk", "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]
                data = b"".join(b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks) + b"data: [DONE]\n\n"
                return self._send(200, data, "text/event-stream")
            return self._send(200, {"id": "c", "object": "chat.completion", "model": model,
                                    "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}],
                                    "usage": {"prompt_tokens": 0, "completion_tokens": 1, "total_tokens": 1}})
        if p.endswith("/embeddings"):
            inp = body.get("input"); inp = inp if isinstance(inp, list) else [inp]
            v = [1.0 / DIM ** 0.5] * DIM
            return self._send(200, {"object": "list", "model": body.get("model"), "data": [{"object": "embedding", "index": i, "embedding": v} for i in range(len(inp))],
                                    "usage": {"prompt_tokens": 0, "total_tokens": 0}})
        if p.endswith("/ranking") or p.endswith("/reranking"):
            n = len(body.get("passages") or body.get("documents") or [])
            return self._send(200, {"rankings": [{"index": i, "logit": float(-i)} for i in range(n)]})
        self._send(404, {"error": f"not served: {self.path}"})


http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
