"""Host-side timing probe (no model, no GPU). The server answers every POST after exactly 40 ms; this client times the
call the way the judge harness does (wall time around requests.post) and prints the distribution, in three settings:
  new      a new connection per call (what the harness does), default timer
  new+1ms  the same, after asking Windows for a 1 ms timer resolution in this process
  reused   one kept-alive connection for all calls, default timer
Prints counts only. usage: client.py [N per setting, default 300]"""
import collections, ctypes, math, sys, time

import requests

URL = "http://127.0.0.1:8011/v1/chat/completions"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
BODY = {"model": "probe", "messages": [{"role": "user", "content": "x" * 800}], "max_tokens": 100, "temperature": 0.0}


def nr(v, p):
    v = sorted(v); return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def run(label, session=None):
    post = session.post if session else requests.post
    for _ in range(5):
        post(URL, json=BODY, timeout=30)
    v = []
    for _ in range(N):
        t = time.perf_counter(); r = post(URL, json=BODY, timeout=30); v.append((time.perf_counter() - t) * 1000)
        assert r.status_code == 200
    h = collections.Counter(int(x // 2) * 2 for x in v)
    main = nr(v, 10)
    print(f"{label:8} n={len(v)} p10 {nr(v, 10):.1f} p50 {nr(v, 50):.1f} p90 {nr(v, 90):.1f} p99 {nr(v, 99):.1f} | calls more than 10 ms above p10: {sum(x > main + 10 for x in v)}"
          f" | 2 ms bins: " + " ".join(f"{b}:{h[b]}" for b in sorted(h)))


print("probe started", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
run("new")
ctypes.windll.winmm.timeBeginPeriod(1)
run("new+1ms")
ctypes.windll.winmm.timeEndPeriod(1)
run("new")                       # back to the default timer: the first setting again, to see it is not an order effect
s = requests.Session(); run("reused", s); s.close()
