"""Tests of extraction_smoke.py against a small stand-in server. They show that the program records counts and key
names and keeps no recognised text; they show nothing about a real NIM."""
import json, os, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROGRAM = os.path.join(HERE, "..", "scripts", "extraction_smoke.py")
PLANTED = "PLANTED-RECOGNISED-TEXT"
MODE = {"fail": False}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, status=200):
        raw = json.dumps(obj).encode(); self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        self._send({"ready": True})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if MODE["fail"]:
            return self._send({"error": "Failed to open the handle"}, 500)
        if self.path == "/v1/infer":
            return self._send({"data": [{"index": 0, "text_detections": [{"text_prediction": {"text": PLANTED, "confidence": 0.9}, "bounding_box": {"points": [{"x": 0.1, "y": 0.2}]}}] * 3,
                                         "bounding_boxes": {"table": [{"x_min": 0.1}], "title": []}}], "usage": {"images_size_mb": 0.1}})
        args = json.dumps([[{"bbox": {"xmin": 0.1}, "text": PLANTED, "type": "Text"}, {"bbox": {"xmin": 0.2}, "text": PLANTED + "!", "type": "Title"}]])
        self._send({"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [{"function": {"name": "markdown_bbox", "arguments": args}}]}}], "usage": {"total_tokens": 9}})


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def run(tmp_path, server, form, name):
    img = tmp_path / "one.png"; img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    out = tmp_path / name
    r = subprocess.run([sys.executable, PROGRAM, "--form", form, "--url", server, "--image", str(img), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.load(open(out, encoding="utf-8")), open(out, encoding="utf-8").read(), r.stdout


def test_infer_records_counts_and_no_text(tmp_path, server):
    MODE["fail"] = False
    d, raw, stdout = run(tmp_path, server, "infer", "a.json")
    posts = [x for x in d["requests"] if x.get("post")]
    assert [p["status"] for p in posts] == [200, 200]
    s = posts[0]["answer_shape"]["data"]["first"]
    assert s["text_detections"]["length"] == 3 and s["bounding_boxes"]["table"]["length"] == 1
    assert s["text_detections"]["first"]["text_prediction"]["text"] == {"string_characters": len(PLANTED)}
    assert PLANTED not in raw and PLANTED not in stdout


def test_parse_records_element_counts_and_no_text(tmp_path, server):
    MODE["fail"] = False
    d, raw, stdout = run(tmp_path, server, "parse", "b.json")
    s = [x for x in d["requests"] if x.get("post")][0]["answer_shape"]
    assert s["tool_calls"] == 1 and s["elements"] == 2 and s["element_types"] == {"Text": 1, "Title": 1}
    assert s["text_characters_total"] == 2 * len(PLANTED) + 1
    assert PLANTED not in raw and PLANTED not in stdout


def test_an_error_keeps_the_servers_message(tmp_path, server):
    MODE["fail"] = True
    d, raw, _ = run(tmp_path, server, "infer", "c.json")
    posts = [x for x in d["requests"] if x.get("post")]
    assert [p["status"] for p in posts] == [500, 500] and "Failed to open the handle" in posts[0]["body"]
    MODE["fail"] = False


def test_an_existing_result_is_not_overwritten(tmp_path, server):
    run(tmp_path, server, "infer", "d.json")
    img = tmp_path / "one.png"
    r = subprocess.run([sys.executable, PROGRAM, "--form", "infer", "--url", server, "--image", str(img), "--out", str(tmp_path / "d.json")], capture_output=True, text=True)
    assert r.returncode != 0 and "refused" in r.stderr
