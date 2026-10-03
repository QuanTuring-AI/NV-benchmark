#!/usr/bin/env python3
"""A stand-in for the embedding and reranking NIMs, for harness tests only. It answers /v1/embeddings, /v1/ranking,
/v1/models and /v1/health/ready with the field names of the published OpenAPI files and refuses what those files do not
allow (a missing required field, a value outside an enumeration, too many items, an empty string).

What it can and cannot show: it shows that the harness builds the requests it means to build and reads the answers the
way it means to read them. It shows nothing about a real NIM. Every assumption about the server (which fields it really
needs, how it orders its answer, what it does with a long input, what an error looks like) is this file's assumption
until a real NIM has answered.

Its vectors and scores are made from the text by a fixed rule, so tests can know the expected answer:
  embedding   8 numbers from the SHA-256 of "<input_type>:<text>" (so query mode and passage mode differ);
              the `data` list is returned in reverse order, to check that the harness sorts by `index`
  ranking     logit = number of words the passage shares with the query; `rankings` is sorted by logit, highest first
A text that contains MOCK_TOO_LONG stands for an input longer than the model takes: with truncate NONE the request is
answered with HTTP 400, with END or START it is accepted.

usage: mock_nim_server.py [--port 8000] [--model mock/embed]
"""
import argparse, hashlib, json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

A = None
LOG = []   # every request body the server accepted or refused, for the tests


def vector(input_type, text):
    h = hashlib.sha256(f"{input_type}:{text}".encode("utf-8")).digest()
    return [round(b / 255.0, 6) for b in h[:8]]


def overlap(query, passage):
    return float(len(set(query.lower().split()) & set(passage.lower().split())))


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _refuse(self, code, detail):
        self._send({"object": "error", "message": detail, "detail": detail, "type": "invalid_request_error"}, code)

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            return self._send({"object": "list", "data": [{"id": A.model, "object": "model"}]})
        if self.path.startswith("/v1/health/ready"):
            return self._send({"object": "health-response", "message": "Service is ready."})
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        except ValueError:
            return self._refuse(400, "the body is not JSON")
        LOG.append({"path": self.path, "body": body})
        if self.path == "/v1/embeddings":
            for k in ("input", "model"):
                if k not in body:
                    return self._refuse(422, f"field required: {k}")
            unknown = set(body) - {"input", "model", "input_type", "encoding_format", "embedding_type", "dimensions", "modality", "user", "truncate"}
            if unknown:
                return self._refuse(422, f"extra fields not permitted: {sorted(unknown)}")
            texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
            if not 1 <= len(texts) <= 8192 or any(not isinstance(t, str) or not t for t in texts):
                return self._refuse(422, "input must be 1 to 8192 non-empty strings")
            it = body.get("input_type")
            if it not in ("query", "passage"):
                return self._refuse(422, "input_type must be query or passage for this model")
            tr = body.get("truncate", "NONE")
            if tr not in ("NONE", "END", "START"):
                return self._refuse(422, "truncate must be NONE, END or START")
            if tr == "NONE" and any("MOCK_TOO_LONG" in t for t in texts):
                return self._refuse(400, "input is longer than the maximum token length and truncate is NONE")
            data = [{"index": i, "embedding": vector(it, t), "object": "embedding"} for i, t in enumerate(texts)]
            return self._send({"object": "list", "data": data[::-1], "model": body["model"], "usage": {"prompt_tokens": sum(len(t.split()) for t in texts), "total_tokens": sum(len(t.split()) for t in texts)}})
        if self.path == "/v1/ranking":
            for k in ("model", "query", "passages"):
                if k not in body:
                    return self._refuse(422, f"field required: {k}")
            unknown = set(body) - {"model", "query", "passages", "truncate"}
            if unknown:
                return self._refuse(422, f"extra fields not permitted: {sorted(unknown)}")
            q = body["query"]; ps = body["passages"]
            if not isinstance(q, dict) or set(q) != {"text"} or not isinstance(q["text"], str) or not q["text"]:
                return self._refuse(422, "query must be an object with one non-empty text field")
            if not isinstance(ps, list) or not 1 <= len(ps) <= 512 or any(not isinstance(p, dict) or not isinstance(p.get("text"), str) or not p["text"] for p in ps):
                return self._refuse(422, "passages must be 1 to 512 objects with a non-empty text field")
            tr = body.get("truncate", "NONE")
            if tr not in ("NONE", "END"):
                return self._refuse(422, "truncate must be NONE or END")
            if tr == "NONE" and ("MOCK_TOO_LONG" in q["text"] or any("MOCK_TOO_LONG" in p["text"] for p in ps)):
                return self._refuse(400, "input is longer than the maximum token length and truncate is NONE")
            ranks = sorted(({"index": i, "logit": overlap(q["text"], p["text"])} for i, p in enumerate(ps)), key=lambda r: (-r["logit"], r["index"]))
            return self._send({"rankings": ranks, "usage": {"prompt_tokens": 0, "total_tokens": 0}})
        self._send({"error": "not found"}, 404)


def serve(port=8000, model="mock/embed"):
    global A
    A = argparse.Namespace(port=port, model=model)
    srv = ThreadingHTTPServer(("127.0.0.1", port), H); srv.daemon_threads = True
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8000); ap.add_argument("--model", default="mock/embed")
    a = ap.parse_args()
    s = serve(a.port, a.model)
    print(f"stand-in NIM on 127.0.0.1:{a.port} (model id {a.model})", file=sys.stderr, flush=True)
    s.serve_forever()
