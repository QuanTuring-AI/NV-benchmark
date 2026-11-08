#!/usr/bin/env python3
"""Vol.5 · a stand-in for the three model services the Blueprint's RAG server calls, for arm P: like
capture_service.py, but every request body is written (answer model, embedding model and reranking model), so that
what the server sends the reranker and what it then sends the answer model can both be read without a card.

  POST .../chat/completions   body -> OUT_DIR/<n>_chat.json; a fixed short answer (streamed when asked)
  POST .../embeddings         body -> OUT_DIR/<n>_embeddings.json; one fixed unit vector of DIM numbers per input
  POST .../ranking            body -> OUT_DIR/<n>_ranking.json; every passage gets the logit
                              (sha256(passage text) mod 2000) / 100 - 10, so the server's order is not the input order
                              and can be checked against a sort by these logits
  GET  .../models             the model names given on the command line; anything else 200 {"status": "ok"}
<n> counts every POST from 1. Standard library only.
usage: capture_service_all.py OUT_DIR MODEL [MODEL ...] [--port 8000] [--dim 2048]
"""
import hashlib, http.server, json, os, sys, threading

args = sys.argv[1:]
PORT = int(args[args.index("--port") + 1]) if "--port" in args else 8000
DIM = int(args[args.index("--dim") + 1]) if "--dim" in args else 2048
pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--port", "--dim"))]
OUT, MODELS = pos[0], pos[1:]
os.makedirs(OUT, exist_ok=True)
LOCK, COUNT = threading.Lock(), [0]
ANSWER = "captured"


def logit(text):
    return (int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % 2000) / 100 - 10


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass

    def _save(self, kind, body):
        with LOCK:
            COUNT[0] += 1; n = COUNT[0]
        json.dump({"path": self.path, "body": body}, open(os.path.join(OUT, f"{n}_{kind}.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self._send(200, {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "capture"} for m in MODELS]})
        self._send(200, {"status": "ok"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        p = self.path.rstrip("/")
        if p.endswith("/chat/completions"):
            self._save("chat", body); model = body.get("model", "")
            if body.get("stream"):
                chunks = [{"id": "c", "object": "chat.completion.chunk", "model": model, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ANSWER}, "finish_reason": None}]},
                          {"id": "c", "object": "chat.completion.chunk", "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]
                return self._send(200, b"".join(b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks) + b"data: [DONE]\n\n", "text/event-stream")
            return self._send(200, {"id": "c", "object": "chat.completion", "model": model, "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}],
                                    "usage": {"prompt_tokens": 0, "completion_tokens": 1, "total_tokens": 1}})
        if p.endswith("/embeddings"):
            self._save("embeddings", body)
            inp = body.get("input"); inp = inp if isinstance(inp, list) else [inp]
            v = [1.0 / DIM ** 0.5] * DIM
            return self._send(200, {"object": "list", "model": body.get("model"), "data": [{"object": "embedding", "index": i, "embedding": v} for i in range(len(inp))],
                                    "usage": {"prompt_tokens": 0, "total_tokens": 0}})
        if p.endswith("/ranking") or p.endswith("/reranking"):
            self._save("ranking", body)
            ps = body.get("passages") or body.get("documents") or []
            texts = [x.get("text", "") if isinstance(x, dict) else str(x) for x in ps]
            ranks = sorted(({"index": i, "logit": logit(t)} for i, t in enumerate(texts)), key=lambda r: -r["logit"])
            return self._send(200, {"rankings": ranks})
        self._send(404, {"error": f"not served: {self.path}"})


http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
