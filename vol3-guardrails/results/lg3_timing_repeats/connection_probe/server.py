"""A stand-in server for a host-side timing probe (no model, no GPU): every POST is answered after a fixed 40 ms.
Runs inside a Linux container, where the wait is not subject to the Windows timer tick."""
import json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        t = time.perf_counter()
        while time.perf_counter() - t < 0.040:      # a busy wait: exact, whatever the tick of the kernel
            pass
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "safe"}, "finish_reason": "stop"}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = b"ok"
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("0.0.0.0", 8011), H).serve_forever()
