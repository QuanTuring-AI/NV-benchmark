"""Tests of ocr_text_smoke.py against a small stand-in server: the request body of each form, the character counts
against an expected text, and that only the first 50 recognised characters are kept. Nothing about a real OCR service."""
import json, os, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROGRAM = os.path.join(HERE, "..", "scripts", "ocr_text_smoke.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
SEEN = []
ANSWER = {"texts": []}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, status=200):
        raw = json.dumps(obj).encode(); self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        self._send({"ready": True})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        SEEN.append((self.path, sorted(body.keys()), body.get("merge_levels")))
        self._send({"model": "stand-in", "data": [{"index": 0, "text_detections": [{"text_prediction": {"text": t, "confidence": 0.9}, "bounding_box": {"points": []}} for t in ANSWER["texts"]]}]})


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def run(tmp_path, server, form, name, expected=None, extra=()):
    img = tmp_path / "one.png"; img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    cmd = [sys.executable, PROGRAM, "--form", form, "--url", server, "--image", str(img), "--out", str(tmp_path / name), *extra]
    if expected is not None:
        e = tmp_path / "expected.txt"; e.write_text(expected, encoding="utf-8"); cmd += ["--expected", str(e)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.load(open(tmp_path / name, encoding="utf-8")), open(tmp_path / name, encoding="utf-8").read()


def test_the_two_request_forms(tmp_path, server):
    SEEN.clear(); ANSWER["texts"] = ["a"]
    run(tmp_path, server, "ocr", "a.json", extra=("--merge-level", "paragraph"))
    run(tmp_path, server, "infer", "b.json")
    assert SEEN[0] == ("/v1/ocr", ["input", "merge_levels"], ["paragraph"]) and SEEN[2] == ("/v1/infer", ["input"], None)


def test_characters_are_counted_against_the_expected_text(tmp_path, server):
    ANSWER["texts"] = ["特制定本法", "abc 12"]                       # 5 CJK characters and 5 others; "c" is not expected
    d, _ = run(tmp_path, server, "ocr", "c.json", expected="特制定本法。\nab 12 本\n")
    o = [x for x in d["requests"] if x.get("post")][0]["against_the_expected_text"]
    assert o["expected_characters"] == 11 and o["expected_cjk_characters"] == 6
    assert o["found"] == 9 and o["cjk_found"] == 5 and o["share_of_cjk_found"] == round(5 / 6, 4)
    assert o["returned_characters"] == 10 and o["returned_not_in_expected"] == 1


def test_only_the_first_50_recognised_characters_are_kept(tmp_path, server):
    long = "字" * 60 + "TAIL-NOT-KEPT"
    ANSWER["texts"] = [long]
    d, raw = run(tmp_path, server, "ocr", "d.json")
    post = [x for x in d["requests"] if x.get("post")][0]
    assert post["characters_returned"] == len(long) and post["first_50_characters"] == "字" * 50
    assert "TAIL-NOT-KEPT" not in raw
